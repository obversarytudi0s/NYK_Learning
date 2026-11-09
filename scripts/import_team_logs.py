"""Import published NBA team-game Parquet seasons into the project archive format."""
import argparse
import json
import urllib.request
from datetime import date
from pathlib import Path

import polars as pl

from knicks_history.pipeline import archive, season_label

BASE = 'https://basketball-data.billmill.org/nba/stats/team_game_logs/season={year}/data.parquet'
TEAM_ID = 1610612752
STAT_FIELDS = ('fgm', 'fga', 'fg3m', 'fg3a', 'ftm', 'fta', 'oreb', 'dreb',
               'reb', 'ast', 'stl', 'blk', 'tov', 'pf')
HEADERS = ['TEAM_ID', 'GAME_ID', 'GAME_DATE', 'MATCHUP', 'WL', 'PTS', *[x.upper() for x in STAT_FIELDS]]


def import_season(year, root):
    # This source uses the ending year (2018 = 2017-18); this project uses
    # the starting year in its season labels (2017-18).
    season = season_label(year - 1)
    with urllib.request.urlopen(BASE.format(year=year), timeout=90) as response:
        data = response.read()
    source_path = Path('/tmp') / f'knicks-team-game-logs-{year}.parquet'
    source_path.write_bytes(data)
    frame = pl.read_parquet(source_path).filter(pl.col('season') == year)
    knicks = frame.filter(pl.col('team_id') == str(TEAM_ID))
    games = {}
    for row in knicks.iter_rows(named=True):
        game_id = row['game_id']
        # NBA game IDs encode regular season as 002; playoffs as 004.
        if not game_id.startswith('002'):
            continue
        opponent = frame.filter(pl.col('game_id') == game_id).filter(pl.col('team_id') == row['opp_team_id'])
        if opponent.is_empty():
            raise ValueError(f'{season} {game_id}: missing opponent row')
        opp = opponent.row(0, named=True)
        matchup = 'NYK vs. OPP' if row['home'] else 'NYK @ OPP'
        for team_row in (row, opp):
            team_id = int(team_row['team_id'])
            team_matchup = matchup if team_id == TEAM_ID else ('OPP @ NYK' if row['home'] else 'OPP vs. NYK')
            values = [team_id, game_id, team_row['game_date'].isoformat(), team_matchup,
                      'W' if team_row['win'] else 'L', team_row['pts']]
            values.extend(team_row[field] for field in STAT_FIELDS)
            games.setdefault(game_id, []).append(values)
    payload = {'resultSets': [{'name': 'LeagueGameLog', 'headers': HEADERS,
                               'rowSet': [r for _, pair in sorted(games.items()) for r in pair]}]}
    manifest = archive(root, json.dumps(payload, separators=(',', ':')).encode(), season,
                       'Regular Season', False,
                       {'dataset': 'team_game_logs', 'source': 'NBA Stats via basketball-data.billmill.org',
                        'source_url': BASE.format(year=year), 'season_end_year': year})
    if manifest['row_count'] != 82 and year not in (2020, 2021, 2022, 2023, 2024, 2025):
        raise ValueError(f'{season}: expected 82 Knicks regular-season games, got {manifest["row_count"]}')
    print(f'Imported {season}: {manifest["row_count"]} games', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, default=2018, help='first season end year (2018 means 2017-18)')
    parser.add_argument('--end', type=int, default=2026, help='last season end year')
    parser.add_argument('--root', type=Path, default=Path('data/live'))
    args = parser.parse_args()
    for year in range(args.start, args.end + 1):
        import_season(year, args.root)


if __name__ == '__main__':
    main()
