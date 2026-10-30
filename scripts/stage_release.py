"""Copy only the completed CURRENT release into a new staging directory."""
import re
import shutil
import sys
from pathlib import Path

root, destination = map(Path, sys.argv[1:])
release_id = (root / 'CURRENT').read_text().strip()
if not re.fullmatch(r'[0-9TZ]+-[a-f0-9]{8}', release_id):
    raise ValueError('Malformed release ID')
if destination.exists():
    raise FileExistsError('Use an empty destination; do not mix releases')
shutil.copytree(root / 'releases' / release_id, destination)
print(destination.resolve())
