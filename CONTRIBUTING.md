# Contributing to Apex

Thanks for your interest. Apex is a research project, so the main rule is about honesty: a change must
not make the output claim more than the data supports.

## Setup

```bash
git clone https://github.com/ultramagnus23/Apex_F1.git
cd Apex_F1
uv sync --locked
uv run pre-commit install
```

## Before you open a pull request

CI runs these, and so should you:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy apex/core
uv run pytest -m "not network"
uv run python scripts/check_case_study.py
uv run python scripts/check_docs.py
uv run python scripts/build_dashboard.py --check
```

Tests must not need the network. Use the offline fixture in `tests/fixtures/`. Mark anything that does
need it with `@pytest.mark.network`.

## Conventions

- **Claim tags.** Anything that states a finding uses OBSERVED, HYPOTHESIS, INCONCLUSIVE or UNKNOWN
  (see the [glossary](docs/GLOSSARY.md)). A new OBSERVED claim must pass the stability test.
- **Delta sign.** Δ = T_A − T_B. Negative means A is faster ([ADR 0002](docs/decisions/0002-time-delta-convention.md)).
- **Data rules.** Follow [DATA_CONTRACT §9](docs/DATA_CONTRACT.md#9-rules-derived-from-this-contract), for example
  `104` in throttle or brake means missing, and brake is never interpolated.
- **Types.** `apex/core` is checked with strict mypy.
- **Decisions.** A change that alters a method or convention gets a decision record in `docs/decisions/`.
- **Golden numbers.** Case study 01 is frozen in `tests/regression/`. If a change moves those numbers,
  explain why in the pull request, and update the golden file and the documents deliberately.
- **Style.** Line length 100, ruff-formatted.
- **Commits.** Short imperative subject, conventional prefixes (`feat`, `fix`, `docs`, `test`, `chore`).

## Good first contributions

- Run the season study on another year or on race sessions, and report what changes.
- Look into the Spa-Francorchamps outlier in the 2025 study.
- Add tests, or improve documentation clarity.
- Report a data quirk with a minimal reproduction.

Larger items (lap simulator, stint modelling, an app) are not started. Open an issue to discuss
before starting one. See [docs/STATUS.md](docs/STATUS.md).

## Reporting issues

Use the issue templates. For a suspected wrong result, include the session, drivers, laps and the
command you ran.

## Data and credentials

Do not commit raw data, `cache/` contents, or credentials. Apex never asks for F1 account details.
