---
title: "NYK Learning — ETL foundation and first validated season"
date: 2026-10-30
tags: [nyk-learning, data-engineering, etl, python, sqlite, git]
status: completed-milestone
---

# NYK Learning: ETL foundation and first validated season

We built a Python pipeline, ran it against synthetic data, ingested the Knicks' 2024–25 regular season, checked its game count against an external reference, and merged the implementation into the public GitHub repository.

This is a session record, not a script to rerun from top to bottom. Commands below reproduce the workflow we followed. Where terminal output was not supplied, that limit is noted.

## 1. Project and environment

| Component | Value |
|---|---|
| Repository | NYK_Learning (organization-hosted GitHub repository) |
| Local checkout | Clone the repository to any preferred directory |
| Python environment | `.venv-knicks` |
| Observed Python version | `3.12.3`, recorded in the live release manifest |
| Python distribution / import | `knicks-history` / `knicks_history` |
| Command-line entry point | `knicks` |
| Source-control workflow | Feature branch → pull request → merge → local fast-forward |

The project runs inside a Distrobox development environment on Fedora Silverblue. The exact container distribution was not shown in the session output. Earlier instructions offered Debian/Ubuntu and Fedora package-manager alternatives; those alternatives are not evidence that both were run.

The public repository is the project home. No GitHub Pages deployment was required or performed as part of this milestone.

## 2. Code added to the repository

The starter was introduced on `feature/knicks-pipeline-foundation` in commit `fd9448f`.

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, Python requirement, optional dependencies and `knicks` entry point |
| `src/knicks_history/cli.py` | Parse `ingest`, `fetch` and `build`; make optional live NBA requests |
| `src/knicks_history/pipeline.py` | Parse responses, validate rows, join opponents, archive snapshots and build releases |
| `tests/test_pipeline.py` | Twenty tests covering replay, corrections, schemas, nulls, checksums and export failures |
| `fixtures/league-demo.json` | Explicitly invented two-game teaching dataset |
| `config/expected-demo.csv` | Expected synthetic game count |
| `config/expected-live.csv` | Independently checked real-season game count, added during the session |
| `config/coverage-plan.csv` | Historical review checklist; not proof of completed ingestion |
| `sql/analysis.sql` | Season summaries, home/away analysis and prior-game feature queries |
| `scripts/backfill.py` | Sequential, resumable season fetching |
| `scripts/stage_release.py` | Copy a completed release into a new staging directory |
| `.github/workflows/tests.yml` | GitHub Actions fixture tests and Parquet build |
| `.gitignore` | Keep environments, caches and generated datasets out of Git |
| `docs/START_HERE.md` | Repository-specific local setup instructions |
| `docs/DATASET-template.md` | Template for documenting a released dataset |

### How the implementation works

1. **Extract:** `fetch_raw()` calls `LeagueGameLog` with the requested season, season type, league `00` and team mode `T`.
2. **Archive:** `archive()` preserves the response under its SHA-256 hash and writes an accepted or rejected ingestion record.
3. **Transform:** `normalize()` reads columns by header name, selects Knicks team ID `1610612752`, preserves game IDs as strings, and joins opponent rows by game ID.
4. **Validate:** duplicate keys, malformed required fields, invalid counts and inconsistent scores fail validation. Missing optional statistics remain null.
5. **Build:** `build()` chooses the latest accepted snapshot for each season/type and reconstructs a new release.
6. **Promote:** the `CURRENT` pointer changes only after the release exports complete successfully.

The core fact table has one Knicks row per completed game, keyed by `(season, season_type, game_id, team_id)`. Regular Season and Playoffs remain separate partitions.

The key reliability choice is rebuilding from selected snapshots rather than appending the same games repeatedly. Re-ingestion can produce a new run and release without duplicating fact rows. Earlier snapshots remain available for investigating corrections.

## 3. Python package setup

The setup commands supplied were:

```bash
cd /path/to/NYK_Learning
python3 -m venv .venv-knicks
source .venv-knicks/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[live,columnar,notebook]'
```

Setup was reported complete; a full installation log was not pasted. The later prompt confirms the environment was active, and the live manifest records Python 3.12.3.

| Extra | Packages | Job |
|---|---|---|
| `live` | `nba-api==1.11.4` and its dependencies | NBA source access |
| `columnar` | Polars 1.x | Typed Parquet exports |
| `notebook` | JupyterLab and ipykernel | Interactive exploration |

`-e` installs the project in editable mode: the installed CLI imports the repository's source code. Python's standard library supplies `sqlite3` and `unittest`; the separate `sqlite3` shell command is an OS package.

Verification commands supplied during setup:

```bash
python -m pip check
python -c "import nba_api, polars, jupyterlab, ipykernel; print('Imports OK')"
knicks --help
python -m unittest discover -s tests -v
```

Nineteen tests passed in the assistant's preparation environment; its Parquet test was skipped because Polars was unavailable there. The user's complete local test summary and GitHub Actions result were not supplied. The subsequent live manifest does confirm that a Parquet export was generated locally.

## 4. First end-to-end run: synthetic data

The fixture workflow supplied was:

```bash
knicks ingest \
  --input fixtures/league-demo.json \
  --synthetic \
  --season 2024-25 \
  --root data/demo

knicks build \
  --root data/demo \
  --expected config/expected-demo.csv \
  --parquet
```

The following command and its result were explicitly pasted from the local terminal:

```bash
knicks_release="$(cat data/demo/CURRENT)"

sqlite3 -header -column \
  "data/demo/releases/$knicks_release/knicks.sqlite" \
  "SELECT * FROM season_summary;"
```

| Season | Type | Games | Wins | Losses | Points/game | Mean margin | Margin games |
|---|---|---:|---:|---:|---:|---:|---:|
| 2024-25 | Regular Season | 2 | 1 | 1 | 102.5 | 2.0 | 2 |

These are invented games. This result established that the pipeline could produce a release and that SQLite could query its summary view.

`knicks_release="$(cat ...)"` reads the release ID into a shell variable. `-header` prints SQL column names; `-column` formats aligned output. `margin_games` counts games with enough opponent information to calculate a margin.

## 5. First live season

The live commands supplied were:

```bash
knicks fetch \
  --season 2024-25 \
  --season-type "Regular Season" \
  --root data/live

knicks build \
  --root data/live \
  --parquet
```

The user then ran and pasted:

```bash
knicks_release="$(cat data/live/CURRENT)"

sqlite3 -header -column \
  "data/live/releases/$knicks_release/knicks.sqlite" \
  "SELECT * FROM season_summary;"
```

| Season | Type | Games | Wins | Losses | Points/game | Mean margin | Margin games |
|---|---|---:|---:|---:|---:|---:|---:|
| 2024-25 | Regular Season | 82 | 51 | 31 | 115.78 | 4.098 | 82 |

Unlike the fixture, this release came from a live source request. All 82 games had opponent scores available for margin calculation.

## 6. Provenance and release inspection

The requested inspection commands were:

```bash
cat "data/live/releases/$knicks_release/coverage.csv"
cat "data/live/releases/$knicks_release/manifest.json"
```

The pasted manifest recorded:

| Field | Observed value |
|---|---|
| Release ID | `20261030T223854364464Z-64107be1` |
| Built at | `2026-10-30T22:38:54.623123+00:00` |
| Source retrieved at | `2026-10-30T22:38:40.732795+00:00` |
| Synthetic | `false` |
| Python | `3.12.3` |
| Code commit | `fd9448fb7267238b61c0da38e437390c06121355` |
| Working tree dirty | `false` |
| Source endpoint | `LeagueGameLog` |
| Client version | `nba_api 1.11.4` |
| Rows | `82` |
| Selected ingestion run | `20261030T223840732726Z-39b61c45` |

The manifest also included hashes for the raw response and the CSV, SQLite, Parquet and coverage exports. These are fingerprints for integrity checks; recording hashes alone does not prove the source statistics are correct.

This manifest describes the initial live release. The later rebuild after adding the expected count creates another release; its new release ID was not pasted. Later Git commits do not retroactively change the code SHA recorded in the initial release.

## 7. Turn the expected game count into a validation rule

Initially, coverage reported:

```csv
season,season_type,observed_games,expected_games,status,count_source,missing_opponent_rows
2024-25,Regular Season,82,,unverified_count,,0
```

We checked the 82-game, 51–31 record against [Basketball Reference's 2024–25 Knicks season page](https://www.basketball-reference.com/teams/NYK/2025.html), then added `config/expected-live.csv`:

```csv
season,season_type,expected_games,source
2024-25,Regular Season,82,https://www.basketball-reference.com/teams/NYK/2025.html
```

The rebuild command supplied was:

```bash
knicks build \
  --root data/live \
  --expected config/expected-live.csv \
  --parquet
```

This rebuild uses archived input; it does not require another NBA request.

The user confirmed the resulting coverage with:

```bash
knicks_release="$(cat data/live/CURRENT)"
cat "data/live/releases/$knicks_release/coverage.csv"
```

```csv
season,season_type,observed_games,expected_games,status,count_source,missing_opponent_rows
2024-25,Regular Season,82,82,count_matches,https://www.basketball-reference.com/teams/NYK/2025.html,0
```

`count_matches` means the observed count equals the configured expectation. It is not a claim that every individual game statistic has been independently reconciled. The builder's overall manifest field `coverage_status` remains `review_required` by design.

## 8. Obstacle: “No accepted snapshots”

During the rebuild, the user received:

```text
ValueError: No accepted snapshots
```

The exception came from `build()`: no accepted run manifests were found under the selected root. An existing SQLite export is not an ingestion manifest and cannot substitute for `runs/*.json`.

Diagnostics supplied:

```bash
cd /path/to/NYK_Learning
pwd
ls data/live
ls data/live/runs
```

```bash
python - <<'PY'
import json
from pathlib import Path

root = Path('data/live').resolve()
print('Looking in:', root)
for path in sorted((root / 'runs').glob('*.json')):
    run = json.loads(path.read_text())
    print(path.name, run.get('status'), run.get('season'))
PY
```

An absolute-path retry was also supplied:

```bash
knicks build \
  --root "$PWD/data/live" \
  --expected "$PWD/config/expected-live.csv" \
  --parquet
```

**Outcome:** a later coverage report showed `count_matches`. The diagnostic output and exact successful retry were not pasted, so the original cause remains unconfirmed. A working-directory/root mismatch was a hypothesis, not an established finding.

## 9. Commit and push the validation rule

These commands and their output were explicitly pasted:

```bash
git status --short --branch
git add config/expected-live.csv
git diff --cached
git commit -m "Validate 2024-25 Knicks regular-season game count"
git push
```

Result: commit `8103d79` was created on `feature/knicks-pipeline-foundation` and pushed successfully. It added one file containing the two-line validation rule.

| Command | Purpose |
|---|---|
| `git status --short --branch` | Compact working-tree and branch status |
| `git add FILE` | Stage the intended file |
| `git diff --cached` | Review what the next commit will contain |
| `git commit -m ...` | Record the staged change locally |
| `git push` | Send committed branch history to GitHub |

The dataset remained under ignored `data/`. The commit preserved the expectation used to validate it.

## 10. Obstacle: untracked directories after switching to main

The user ran:

```bash
git branch
git switch main
git status
```

Git then listed `.venv-knicks/`, `data/`, `src/` and `tests/` as untracked.

At that point, `main` had not received the feature branch. Switching branches changed the tracked files, including removing the feature branch's `.gitignore` from the working tree. Local generated files remained on disk and became visible to Git.

The remaining contents of `src/` and `tests/` were not inspected; Python caches were a plausible explanation, not a confirmed inventory.

The guidance was to return to the feature branch, preserve the directories, and complete the pull-request workflow. The key distinction: **switching to a branch does not merge another branch into it.**

## 11. Merge and synchronize local main

The implementation and validation rule were integrated through pull request #1.

The user then ran:

```bash
git switch main
git pull --ff-only
git status --short --branch
```

The terminal confirmed:

```text
Updating c9f5f9f..5a79bd1
Fast-forward
19 files changed, 1154 insertions(+), 1 deletion(-)
## main...origin/main
```

`--ff-only` allowed the local branch pointer to advance to the remote history without creating another local merge commit. It would refuse if the histories had diverged.

The final status had no changed or untracked entries. Local `main` matched `origin/main`, and the project's ignore rules were present again.

## 12. First SQL analysis: largest and smallest scoring margins

The user created the analysis branch successfully:

```bash
git switch -c analysis/2024-25-season
```

```text
Switched to a new branch 'analysis/2024-25-season'
```

Both margin queries were then executed against the local live-data release. This advances the project from building and validating the dataset to using it for descriptive basketball analysis.

### Ten largest margins

```bash
knicks_release="$(cat data/live/CURRENT)"

sqlite3 -header -column \
  "data/live/releases/$knicks_release/knicks.sqlite" \
  "SELECT game_date, matchup, wl, pts, opponent_pts, point_margin
   FROM team_games
   ORDER BY point_margin DESC
   LIMIT 10;"
```

Observed terminal results:

| Game date | Matchup | W/L | Knicks points | Opponent points | Margin |
|---|---|---|---:|---:|---:|
| 2025-01-27 | NYK vs. MEM | W | 143 | 106 | +37 |
| 2025-01-12 | NYK vs. MIL | W | 140 | 106 | +34 |
| 2024-12-01 | NYK vs. NOP | W | 118 | 85 | +33 |
| 2024-11-01 | NYK @ DET | W | 128 | 98 | +30 |
| 2025-03-10 | NYK @ SAC | W | 133 | 104 | +29 |
| 2024-11-18 | NYK vs. WAS | W | 134 | 106 | +28 |
| 2024-11-25 | NYK @ DEN | W | 145 | 118 | +27 |
| 2024-12-19 | NYK @ MIN | W | 133 | 107 | +26 |
| 2024-10-25 | NYK vs. IND | W | 123 | 98 | +25 |
| 2024-12-05 | NYK vs. CHA | W | 125 | 101 | +24 |

### Ten smallest margins

The user also ran the ascending version:

```bash
sqlite3 -header -column \
  "data/live/releases/$knicks_release/knicks.sqlite" \
  "SELECT game_date, matchup, wl, pts, opponent_pts, point_margin
   FROM team_games
   ORDER BY point_margin ASC
   LIMIT 10;"
```

Observed terminal results:

| Game date | Matchup | W/L | Knicks points | Opponent points | Margin |
|---|---|---|---:|---:|---:|
| 2025-02-21 | NYK @ CLE | L | 105 | 142 | −37 |
| 2025-02-08 | NYK vs. BOS | L | 104 | 131 | −27 |
| 2025-01-10 | NYK vs. OKC | L | 101 | 126 | −25 |
| 2024-10-22 | NYK @ BOS | L | 109 | 132 | −23 |
| 2025-04-02 | NYK @ CLE | L | 105 | 124 | −19 |
| 2025-01-17 | NYK vs. MIN | L | 99 | 116 | −17 |
| 2025-03-20 | NYK @ CHA | L | 98 | 115 | −17 |
| 2025-02-01 | NYK vs. LAL | L | 112 | 128 | −16 |
| 2024-11-23 | NYK @ UTA | L | 106 | 121 | −15 |
| 2024-11-27 | NYK @ DAL | L | 114 | 129 | −15 |

### What the queries establish

- `point_margin = pts - opponent_pts`: positive values indicate wins; negative values indicate losses for these completed games.
- `DESC` puts the largest positive margins first. `ASC` puts the most negative margins first; it does not select the closest games.
- The largest observed win was **+37 against Memphis on January 27, 2025**.
- The largest observed loss was **−37 at Cleveland on February 21, 2025**.
- These are descriptive results from the ingested dataset, not independently rechecked box scores or an explanation of why those outcomes occurred.

The commands select from the entire `team_games` table. At this checkpoint it contains only the 2024–25 Regular Season. After backfilling other partitions, add an explicit filter:

```sql
WHERE season = '2024-25'
  AND season_type = 'Regular Season'
```

The executed queries sort only by margin. Tied margins, such as −17 and −15, have no explicit secondary ordering. For repeatable ordering in a saved analysis, use:

```sql
ORDER BY point_margin ASC, game_date ASC, game_id ASC
```

That refinement was not part of the pasted execution. The tables above preserve the user's actual output order.

## 13. Checkpoint and next work

### Confirmed at this checkpoint

- Public repository populated with the pipeline, configuration, tests and documentation.
- Synthetic pipeline output queried successfully.
- Real 2024–25 Regular Season extract built: 82 games, 51 wins, 31 losses.
- Zero missing opponent rows in the release coverage report.
- Expected-count validation passed with a recorded reference URL.
- Validation rule committed and pushed.
- Changes integrated into `main` and pulled locally with a clean working tree at that point.
- New local branch `analysis/2024-25-season` created.
- Both the ten largest and ten smallest scoring-margin queries executed successfully.

### Not yet established

- Full local twenty-test output or the GitHub Actions result.
- Independent reconciliation of every game and statistic.
- Multi-season historical completeness, playoff ingestion or player-game ingestion.
- Structured observation ingestion, ML models or a deployed website.
- A commit or push of the new analysis branch, or a saved SQL file containing these two queries.

Suggested next documentation step: save the season-filtered, deterministically ordered queries in `sql/season_2024_25_margins.sql`, then commit that file and this project log on the analysis branch. This is a proposed next step, not a completed action.

This milestone establishes the project's first data-engineering and analysis foundation: a source response can be archived, transformed, checked, queried and traced back to the code and input used to build it.
