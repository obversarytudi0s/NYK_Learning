"""Sequential, resumable season backfill. Run only after a one-season live check."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from knicks_history.pipeline import KINDS, season_label

parser = argparse.ArgumentParser()
parser.add_argument('--start', type=int, required=True)
parser.add_argument('--end', type=int, required=True)
parser.add_argument('--root', type=Path, default=Path('data/live'))
parser.add_argument('--season-type', choices=KINDS, default='Regular Season')
parser.add_argument('--refresh', action='store_true')
args = parser.parse_args()
if not 1946 <= args.start <= args.end <= 2100:
    parser.error('Use ascending starting years, for example --start 2020 --end 2024')
accepted = set()
for path in (args.root / 'runs').glob('*.json'):
    manifest = json.loads(path.read_text())
    if manifest['status'] == 'accepted':
        accepted.add((manifest['season'], manifest['season_type']))
failures = []
for year in range(args.start, args.end + 1):
    season = season_label(year)
    if (season, args.season_type) in accepted and not args.refresh:
        print('Already archived:', season, args.season_type, flush=True)
        continue
    result = subprocess.run([sys.executable, '-m', 'knicks_history.cli', 'fetch',
                             '--season', season, '--season-type', args.season_type,
                             '--root', str(args.root)])
    if result.returncode:
        failures.append(season)
    time.sleep(5)  # Conservative pacing, not an official API quota guarantee.
if failures:
    print('Unresolved seasons:', ', '.join(failures), file=sys.stderr)
    sys.exit(1)
