# Getting started

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (the lockfile pins every dependency)
- Network access for any command that downloads new sessions. The case study and the tests run offline.

## Install

```bash
git clone https://github.com/ultramagnus23/Apex_F1.git
cd Apex_F1
uv sync --locked
```

## Check it works

```bash
uv run apex version
uv run apex sources
```

`apex sources` reports which data sources are usable. OpenF1 needs no sign-in. FastF1 is listed as
unavailable unless you set `F1_USERNAME` and `F1_PASSWORD` in your own shell.

## Reproduce case study 01 (offline)

```bash
uv run python examples/case_study_01.py
```

It writes figures, tables, sensitivity results and tagged claims into `docs/case_study_01/`. To check
that your output matches the committed copy:

```bash
uv run python scripts/check_case_study.py
```

## Compare two drivers

```bash
uv run apex compare 2026 Austin Q ANT VER --phase 3
```

Arguments: year, circuit, session (`Q`, `R`, `SQ`, `S`), driver A, driver B. Useful options:
`--lap-a`, `--lap-b` (pick specific laps), `--phase` (qualifying phase 1 to 3), `--method`
(`hybrid`, `speed` or `xy`), `--out` (default `out/`) and `--cache` (default `cache/openf1`). Run
`uv run apex compare --help` for the full list. Output goes to `out/`, which is git-ignored.

Delta convention: negative means driver A is faster.

## Race pace and ERS deceleration

```bash
uv run apex pace 2025 Monza R
uv run apex ers 2026 Austin Q
```

`pace` prints each driver's pace with a 90% interval, the model parameters and a holdout check, and writes JSON to
`out/`. `ers` lists full-throttle deceleration events per driver and how well they repeat. Both download from OpenF1 on
first use. See [Race pace](RACE_PACE.md) and [ERS clipping](ERS_CLIPPING.md).

## Rebuild the dashboard

```bash
uv run python scripts/build_dashboard.py
```

This writes `docs/dashboard/index.html` from the committed study outputs. It makes no external requests.

## Reproduce the 2025 season study

```bash
uv run python scripts/fetch_season.py --year 2025 --session Qualifying
uv run python scripts/season_study.py --year 2025
```

The fetch step downloads every 2025 qualifying session into `cache/` (large, git-ignored). The study
takes roughly 14 minutes. Results go to `docs/season_2025/`.

## Run the checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy apex/core
uv run pytest -m "not network"
```

The test suite takes a few minutes. Tests marked `network` need internet access and are skipped in CI.

## Where to read next

1. [Case study 01](CASE_STUDY_01.md): a worked example from start to claims.
2. [Methodology](METHODOLOGY.md): how each step works.
3. [Validation](VALIDATION.md): how the numbers were checked.
4. [FAQ](FAQ.md) and [Glossary](GLOSSARY.md).
