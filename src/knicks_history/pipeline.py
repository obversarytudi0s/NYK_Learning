"""One-season snapshots to a versioned Knicks dataset. Python 3.11+."""
import csv
import hashlib
import html
import json
import re
import platform
import os
import shutil
import subprocess
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

TEAM_ID = 1610612752
KINDS = ('Regular Season', 'Playoffs')
STATS = ('FGM', 'FGA', 'FG3M', 'FG3A', 'FTM', 'FTA', 'OREB', 'DREB',
         'REB', 'AST', 'STL', 'BLK', 'TOV', 'PF')
FIELDS = ['season', 'season_type', 'game_id', 'team_id', 'game_date',
          'matchup', 'venue_side', 'wl', 'pts', 'opponent_id', 'opponent_pts',
          'point_margin'] + [s.lower() for s in STATS] + ['source_sha256']
INTEGER_FIELDS = {'team_id', 'pts', 'opponent_id', 'opponent_pts', 'point_margin'} | {s.lower() for s in STATS}


def season_label(year):
    return f'{year}-{(year + 1) % 100:02d}'


def check_season(season):
    if not re.fullmatch(r'\d{4}-\d{2}', season) or season_label(int(season[:4])) != season:
        raise ValueError('Use a season such as 2024-25')
    return season


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def integer(value, field, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise ValueError(f'{field}: boolean is not a count')
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'{field}: expected integer') from exc
    if isinstance(value, float) and result != value:
        raise ValueError(f'{field}: fractional count')
    if result < 0:
        raise ValueError(f'{field}: negative count')
    return result


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError('GAME_DATE must be text')
    for fmt in ('%Y-%m-%d', '%b %d, %Y', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f'Unknown date format: {value}')


def response_rows(payload):
    sets = payload.get('resultSets', payload.get('resultSet'))
    if isinstance(sets, dict):
        sets = [sets]
    if not isinstance(sets, list):
        raise ValueError('Missing resultSets')
    matches = [s for s in sets if s.get('name') == 'LeagueGameLog']
    if len(matches) != 1:
        raise ValueError('Expected exactly one LeagueGameLog dataset')
    headers = matches[0]['headers']
    if len(set(headers)) != len(headers):
        raise ValueError('Duplicate column headers')
    required = {'TEAM_ID', 'GAME_ID', 'GAME_DATE', 'MATCHUP', 'WL', 'PTS'}
    if not required.issubset(headers):
        raise ValueError(f'Missing columns: {sorted(required - set(headers))}')
    rows = []
    for values in matches[0]['rowSet']:
        if len(values) != len(headers):
            raise ValueError('Row width does not match headers')
        rows.append(dict(zip(headers, values)))
    return rows


def normalize(payload, season, kind, raw_hash):
    check_season(season)
    if kind not in KINDS:
        raise ValueError('Unsupported season type')
    games, seen = defaultdict(list), set()
    for row in response_rows(payload):
        game_id = row['GAME_ID']
        if not isinstance(game_id, str) or not re.fullmatch(r'\d{10}', game_id):
            raise ValueError('GAME_ID must remain a ten-digit string')
        team_id = integer(row['TEAM_ID'], 'TEAM_ID')
        key = (game_id, team_id)
        if key in seen:
            raise ValueError(f'Duplicate team/game key: {key}')
        seen.add(key)
        row['TEAM_ID'] = team_id
        games[game_id].append(row)
    output = []
    for game_id, sides in sorted(games.items()):
        ours = [r for r in sides if r['TEAM_ID'] == TEAM_ID]
        if not ours:
            continue
        if len(sides) > 2:
            raise ValueError('More than two teams for a game')
        row = ours[0]
        if row['WL'] not in ('W', 'L'):
            raise ValueError('Only completed games with W/L are accepted')
        matchup = row['MATCHUP']
        if not isinstance(matchup, str):
            raise ValueError('MATCHUP must be text')
        side = 'away' if ' @ ' in matchup else 'home' if ' vs. ' in matchup else 'unknown'
        game_date = parse_date(row['GAME_DATE'])
        year = int(season[:4])
        if not date(year, 7, 1) <= date.fromisoformat(game_date) <= date(year + 1, 12, 31):
            raise ValueError('Game date is outside the broad season window')
        # Wide window permits the displaced 2019-20 schedule; not a completeness test.
        pts = integer(row['PTS'], 'PTS')
        opponent = next((r for r in sides if r['TEAM_ID'] != TEAM_ID), None)
        opp_pts = integer(opponent['PTS'], 'opponent PTS') if opponent else None
        if opponent:
            if parse_date(opponent['GAME_DATE']) != game_date:
                raise ValueError('Opponent game date differs')
            expected = 'W' if pts > opp_pts else 'L' if pts < opp_pts else None
            if expected != row['WL'] or opponent['WL'] != ('L' if row['WL'] == 'W' else 'W'):
                raise ValueError('Scores and win/loss disagree')
        record = dict(season=season, season_type=kind, game_id=game_id, team_id=TEAM_ID,
                      game_date=game_date, matchup=matchup, venue_side=side, wl=row['WL'], pts=pts,
                      opponent_id=opponent['TEAM_ID'] if opponent else None,
                      opponent_pts=opp_pts, point_margin=pts - opp_pts if opponent else None)
        for name in STATS:
            record[name.lower()] = integer(row.get(name), name, nullable=True)
        for made, attempted in [('fgm', 'fga'), ('fg3m', 'fg3a'), ('ftm', 'fta')]:
            if record[made] is not None and record[attempted] is not None and record[made] > record[attempted]:
                raise ValueError(f'{made} exceeds {attempted}')
        if all(record[k] is not None for k in ('fgm', 'fg3m', 'ftm')):
            if 2 * record['fgm'] + record['fg3m'] + record['ftm'] != pts:
                raise ValueError('Points do not reconcile with made shots')
        record['source_sha256'] = raw_hash
        output.append(record)
    return sorted(output, key=lambda r: (r['game_date'], r['game_id']))


def archive(root, raw, season, kind, synthetic, source, allow_empty=False):
    """Validate before marking a snapshot successful; keep original JSON bytes."""
    check_season(season)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / 'mode.json'
    if marker.exists() and json.loads(marker.read_text())['synthetic'] != synthetic:
        raise ValueError('Use separate roots for synthetic and real data')
    if not marker.exists():
        dump(marker, {'synthetic': synthetic})
    for folder in ('raw', 'runs', 'releases'):
        (root / folder).mkdir(exist_ok=True)
    sha = digest(raw)
    raw_path = root / 'raw' / (sha + '.json')
    if not raw_path.exists():
        raw_path.write_bytes(raw)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid4().hex[:8]
    manifest = dict(run_id=run_id, retrieved_at=now(), season=season, season_type=kind,
                    synthetic=synthetic, source=source, raw_sha256=sha,
                    raw_file=str(raw_path.relative_to(root)), schema_version=1)
    try:
        payload = json.loads(raw)
        if payload.get('synthetic') is True and not synthetic:
            raise ValueError('Synthetic fixture requires --synthetic')
        rows = normalize(payload, season, kind, sha)
        if not rows and not allow_empty:
            raise ValueError('Zero Knicks rows; investigate before accepting an empty season')
        manifest.update(status='accepted', row_count=len(rows))
    except Exception as exc:
        manifest.update(status='rejected', error=str(exc))
        dump(root / 'runs' / (run_id + '.json'), manifest)
        raise
    dump(root / 'runs' / (run_id + '.json'), manifest)
    return manifest


def csv_write(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build(root, expected_path=None, parquet=False):
    """Build a fresh immutable release; update CURRENT only after all exports succeed."""
    root = Path(root)
    latest = {}
    for path in sorted((root / 'runs').glob('*.json')):
        manifest = json.loads(path.read_text())
        if manifest['status'] == 'accepted':
            key = (manifest['season'], manifest['season_type'])
            if key not in latest or manifest['retrieved_at'] > latest[key]['retrieved_at']:
                latest[key] = manifest
    if not latest:
        raise ValueError('No accepted snapshots')
    modes = {m['synthetic'] for m in latest.values()}
    if len(modes) != 1:
        raise ValueError('Mixed data modes')
    rows = []
    for key, m in sorted(latest.items()):
        raw = (root / m['raw_file']).read_bytes()
        if digest(raw) != m['raw_sha256']:
            raise ValueError('Raw snapshot checksum mismatch')
        rows.extend(normalize(json.loads(raw), *key, m['raw_sha256']))
    keys = [(r['season'], r['season_type'], r['game_id'], r['team_id']) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate fact key')
    expectations = {}
    if expected_path:
        with Path(expected_path).open(newline='') as stream:
            for e in csv.DictReader(stream):
                check_season(e['season'])
                key = (e['season'], e['season_type'])
                if e['season_type'] not in KINDS or key in expectations:
                    raise ValueError('Invalid/duplicate coverage partition')
                e['expected_games'] = integer(e['expected_games'], 'expected_games')
                expectations[key] = e
    coverage = []
    for key in sorted(set(latest) | set(expectations)):
        subset = [r for r in rows if (r['season'], r['season_type']) == key]
        e = expectations.get(key)
        observed = len(subset) if key in latest else None
        status = 'not_ingested' if observed is None else 'unverified_count'
        if observed is not None and e:
            status = 'count_matches' if observed == e['expected_games'] else 'count_mismatch'
        coverage.append(dict(season=key[0], season_type=key[1], observed_games=observed,
                             expected_games=e['expected_games'] if e else None, status=status,
                             count_source=e['source'] if e else '',
                             missing_opponent_rows=sum(r['opponent_id'] is None for r in subset)))
    mismatches = [c for c in coverage if c['status'] == 'count_mismatch']
    if mismatches:
        raise ValueError(f'Coverage count mismatch: {mismatches}')
    release_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid4().hex[:8]
    release = root / 'releases' / release_id
    release.mkdir(parents=True, exist_ok=False)
    csv_write(release / 'team_games.csv', FIELDS, rows)
    csv_write(release / 'coverage.csv', list(coverage[0]), coverage)
    columns = ', '.join(f'{field} {"INTEGER" if field in INTEGER_FIELDS else "TEXT"}' for field in FIELDS)
    connection = sqlite3.connect(release / 'knicks.sqlite')
    try:
        with connection:
            connection.execute(f'CREATE TABLE team_games ({columns}, PRIMARY KEY (season, season_type, game_id, team_id))')
            connection.executemany(f'INSERT INTO team_games VALUES ({",".join("?" for _ in FIELDS)})',
                                   [[r[k] for k in FIELDS] for r in rows])
            connection.execute('''CREATE VIEW season_summary AS
                SELECT season, season_type, COUNT(*) games,
                SUM(CASE WHEN wl='W' THEN 1 ELSE 0 END) wins,
                SUM(CASE WHEN wl='L' THEN 1 ELSE 0 END) losses,
                ROUND(AVG(pts), 3) points_per_game,
                ROUND(AVG(point_margin), 3) mean_margin,
                SUM(CASE WHEN point_margin IS NOT NULL THEN 1 ELSE 0 END) margin_games
                FROM team_games GROUP BY season, season_type''')
    finally:
        connection.close()
    if parquet:
        import polars as pl
        schema = {name: pl.Int64 if name in INTEGER_FIELDS else pl.String for name in FIELDS}
        pl.DataFrame(rows, schema=schema).write_parquet(release / 'team_games.parquet', compression='zstd')
    code_sha, code_dirty = os.environ.get('GITHUB_SHA') or os.environ.get('CI_COMMIT_SHA'), None
    if shutil.which('git'):
        repo = Path(__file__).resolve().parents[2]
        git = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        dirty = subprocess.run(['git', '-C', str(repo), 'status', '--porcelain'], capture_output=True, text=True)
        if git.returncode == 0:
            code_sha = git.stdout.strip()
        if dirty.returncode == 0:
            code_dirty = bool(dirty.stdout)
    manifest = dict(release_id=release_id, built_at=now(), schema_version=1, synthetic=modes.pop(),
                    python=platform.python_version(),
                    git_sha=code_sha, git_dirty=code_dirty,
                    team_id=TEAM_ID, rows=len(rows),
                    selected_runs=[m['run_id'] for _, m in sorted(latest.items())],
                    snapshots=[{'season': m['season'], 'season_type': m['season_type'],
                                'retrieved_at': m['retrieved_at'], 'source': m['source']}
                               for _, m in sorted(latest.items())],
                    raw_sha256=sorted({m['raw_sha256'] for m in latest.values()}),
                    coverage_status='review_required',
                    files={p.name: digest(p.read_bytes()) for p in sorted(release.iterdir()) if p.is_file()})
    dump(release / 'manifest.json', manifest)
    dump(release / 'checksums.json', {p.name: digest(p.read_bytes()) for p in sorted(release.iterdir()) if p.is_file()})
    mode = 'SYNTHETIC DEMO — NOT HISTORICAL RESULTS' if manifest['synthetic'] else 'Historical extract — coverage requires review'
    links = ''.join(f'<li><a href="{html.escape(p.name)}">{html.escape(p.name)}</a></li>' for p in sorted(release.iterdir()) if p.is_file())
    (release / 'index.html').write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Knicks dataset</title><h1>Knicks dataset</h1><p>{mode}</p><p>Release {release_id}; {len(rows)} rows.</p><ul>{links}</ul></html>', encoding='utf-8')
    temporary = root / ('CURRENT.' + uuid4().hex + '.tmp')
    temporary.write_text(release_id + '\n')
    temporary.replace(root / 'CURRENT')
    return release
