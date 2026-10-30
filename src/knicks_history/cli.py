import argparse
import importlib.metadata
import json
import time
from pathlib import Path
from .pipeline import KINDS, archive, build, check_season


def fetch_raw(season, kind):
    from nba_api.stats.endpoints.leaguegamelog import LeagueGameLog
    from requests.exceptions import ConnectionError, Timeout
    for attempt in range(3):
        try:
            endpoint = LeagueGameLog(season=season, season_type_all_star=kind,
                                     player_or_team_abbreviation='T', league_id='00', timeout=30)
            return endpoint.get_json().encode('utf-8')
        except (Timeout, ConnectionError):
            if attempt == 2:
                raise
            time.sleep(5 * (2 ** attempt))
    raise RuntimeError('No response')


def main():
    parser = argparse.ArgumentParser(description='Reproducible Knicks team-game ETL')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('ingest', 'fetch'):
        p = commands.add_parser(name)
        p.add_argument('--season', required=True, type=check_season)
        p.add_argument('--season-type', choices=KINDS, default='Regular Season')
        p.add_argument('--root', type=Path, required=True)
        p.add_argument('--allow-empty', action='store_true')
        if name == 'ingest':
            p.add_argument('--input', type=Path, required=True)
            p.add_argument('--synthetic', action='store_true')
    p = commands.add_parser('build')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--expected', type=Path)
    p.add_argument('--parquet', action='store_true')
    args = parser.parse_args()
    if args.command == 'build':
        print(build(args.root, args.expected, args.parquet))
        return
    if args.command == 'fetch':
        raw = fetch_raw(args.season, args.season_type)
        source = {'endpoint': 'LeagueGameLog', 'nba_api_version': importlib.metadata.version('nba_api'),
                  'LeagueID': '00', 'PlayerOrTeam': 'T', 'Season': args.season, 'SeasonType': args.season_type}
        synthetic = False
    else:
        raw, source, synthetic = args.input.read_bytes(), {'input': str(args.input)}, args.synthetic
    result = archive(args.root, raw, args.season, args.season_type, synthetic, source, args.allow_empty)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
