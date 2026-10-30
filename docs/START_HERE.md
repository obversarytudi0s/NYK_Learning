# NYK_Learning — local setup and first successful run

Repository: https://github.com/obversarytudi0s/NYK_Learning

Local checkout: `~/Projects/DataScience/knics_perfomance_hub/NYK_Learning`.

Keep this spelling as it exists on your machine. The Python distribution is `knicks-history`, the import is `knicks_history`, and the CLI is `knicks`; these need not match the repository name.

## 1. Bring the starter into your existing checkout

On your host:

```bash
cd ~/Projects/DataScience/knics_perfomance_hub/NYK_Learning
pwd
git status --short --branch
git remote -v
```

Confirm `origin` points to the repository above. Preserve uncommitted work before switching. Then:

```bash
git fetch origin
git switch --track origin/feature/knicks-pipeline-foundation
```

If this local branch already exists, use `git switch feature/knicks-pipeline-foundation`. After the PR is merged, use `git switch main` and `git pull --ff-only` with a clean working tree.

Do not initialize Git again or copy a repository inside this checkout. These instructions do not remotely change your laptop.

## 2. Select the runtime

On Fedora Silverblue:

```bash
distrobox list
```

Reuse an appropriate Python development container. If you want the dedicated Debian environment from the earlier manual and `knicks-dev` is absent:

```bash
distrobox create --name knicks-dev --image docker.io/library/debian:12
distrobox enter knicks-dev
```

Inside that Debian container only:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git sqlite3 ca-certificates
cd ~/Projects/DataScience/knics_perfomance_hub/NYK_Learning
python3 --version
```

The project requires Python 3.11+. CI uses 3.11. Distrobox shares host resources; it is a development environment, not a security sandbox.

## 3. Create the project environment

Inspect/reuse `.venv-knicks` if it already exists; otherwise create it:

```bash
python3 -m venv .venv-knicks
source .venv-knicks/bin/activate
python -m pip install -e .
python -c "import sys; print(sys.executable)"
knicks --help
```

The base pipeline uses standard-library modules. Installation may still need network access for build tools. PyCharm or VSCodium can edit the host checkout; run commands in the container terminal unless the IDE interpreter is explicitly wired to that runtime.

## 4. First complete dataset build

```bash
python -m unittest discover -s tests -v
knicks ingest --input fixtures/league-demo.json --synthetic --season 2024-25 --root data/demo
knicks build --root data/demo --expected config/expected-demo.csv
knicks_release="$(cat data/demo/CURRENT)"
sqlite3 -header -column "data/demo/releases/$knicks_release/knicks.sqlite" < sql/analysis.sql
```

Expected: two invented Knicks rows, one win and one loss, 102.5 mean points and +2.0 mean margin. The Parquet test skips until its dependency is installed. Re-ingesting must still produce two rows.

## 5. Parquet and dependency recording

```bash
python -m pip install -e '.[columnar]'
python -m unittest discover -s tests -v
knicks build --root data/demo --expected config/expected-demo.csv --parquet
python -m pip freeze --all --exclude-editable > requirements-local.txt
```

All 20 tests should now run without a Parquet skip. Record your Python version alongside the dependency snapshot. The initial Actions workflow uses bounded package requirements, not this local snapshot; migrate CI to a reviewed lockfile after the first working run.

## 6. Preview the plain file index

```bash
python scripts/stage_release.py data/demo build/preview-demo
python -m http.server 8000 --bind 127.0.0.1 --directory build/preview-demo
```

Open http://127.0.0.1:8000. Check the synthetic label and links. Stop with Ctrl+C. Use a fresh staging directory name for later previews; the script refuses to overwrite a prior preview.

## 7. First real-data milestone

After the fixture works:

```bash
python -m pip install -e '.[live]'
knicks fetch --season 2024-25 --season-type "Regular Season" --root data/live
knicks build --root data/live --parquet
```

The live adapter is opt-in; no scheduled NBA job is installed. Inspect the source response, run manifest and coverage. Endpoint access and historical accuracy require live verification. Zero rows are not proof of zero games. Keep synthetic and real roots separate.

For controlled backfills, read `python scripts/backfill.py --help`. Begin with a few seasons. `config/coverage-plan.csv` is an audit checklist, not a completeness claim.

## 8. GitHub workflow

The earlier manual's GitLab remote and `.gitlab-ci.yml` sections are superseded here. Use `.github/workflows/tests.yml` and the pull request's Checks tab.

Make a feature branch per milestone, inspect `git diff`, stage intended files, commit and push. Keep environments, raw archives, credentials and private notes out of Git. Generated `data/` and the project environment are ignored.

## 9. Public repository versus GitHub Pages

The repository's GitHub URL is already public. Your `~/Projects/...` path is the local working copy, not a web address. GitHub Pages is a separate hosting setting and is not enabled by this change.

First establish a tested public repository. Later, deploy the reviewed static dataset index if desired; synthetic scores must stay clearly labeled and private archives must stay out of public exports.

## 10. Next milestones

1. Green GitHub Actions checks including Parquet.
2. One real season reconciled against source evidence.
3. Historical coverage audit and controlled backfill.
4. Game-observation records: game ID, observation timestamp, period/game clock, evidence, interpretation and confidence as separate fields.
5. Leakage-aware features and chronological ML evaluation.

The observation and ML layers are planned, not implemented in this starter.
