# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.11+ ETL learning project using a `src/` layout. Core ingestion, validation, and release-building logic lives in `src/knicks_history/pipeline.py`; `cli.py` exposes the `knicks` command. Keep offline tests in `tests/`, synthetic inputs in `fixtures/`, coverage expectations in `config/`, consumer queries in `sql/`, operational helpers in `scripts/`, and setup or dataset documentation in `docs/`. Generated snapshots and staged releases belong under ignored `data/` and `build/` directories, never in source control.

## Build, Test, and Development Commands

Create an isolated environment and install the editable package:

```bash
python3 -m venv .venv-knicks
source .venv-knicks/bin/activate
python -m pip install -e '.[columnar]'
```

Run `python -m unittest discover -s tests -v` for the full suite. Exercise the offline workflow with:

```bash
knicks ingest --input fixtures/league-demo.json --synthetic --season 2024-25 --root data/demo
knicks build --root data/demo --expected config/expected-demo.csv --parquet
```

Use `python scripts/stage_release.py data/demo build/preview-demo` to stage the current release. Live fetching requires the `live` extra and should follow a successful synthetic run.

## Coding Style & Naming Conventions

Follow standard Python conventions: four-space indentation, `snake_case` for functions and variables, `PascalCase` for test classes, and uppercase constants. Prefer `pathlib.Path`, small single-purpose functions, and explicit validation errors. Preserve game IDs as strings so leading zeros survive. No formatter or linter is configured; match the existing concise style and keep imports grouped with the standard library first.

## Testing Guidelines

Tests use the standard-library `unittest` framework. Add methods named `test_<behavior>` to `tests/test_pipeline.py`, or create `test_*.py` modules as coverage grows. Tests must be deterministic and offline: use invented fixtures, temporary directories, and mocks for failures. Cover validation, replay/idempotency, corrections, null handling, and failed-release preservation. The Parquet test may skip unless `.[columnar]` is installed.

## Commit & Pull Request Guidelines

Recent history uses short, imperative subjects such as `Add Knicks ETL foundation` and `Validate 2024-25 Knicks regular-season game count`. Keep each commit focused. Pull requests should explain the data-contract change, list verification commands and results, link relevant issues, and call out schema, coverage, or source-permission implications. Include screenshots only for rendered release previews.

## Data Safety & Configuration

Never commit credentials, `.env` files, virtual environments, raw third-party archives, or generated datasets. Keep synthetic and live roots separate. Document source provenance and redistribution permission before publishing real NBA data, and treat empty API responses as failures requiring investigation rather than evidence of zero games.
