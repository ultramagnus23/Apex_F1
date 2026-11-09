## What changed and why

## Checks

- [ ] `uv run ruff check .` and `uv run ruff format --check .`
- [ ] `uv run mypy apex/core`
- [ ] `uv run pytest -m "not network"`
- [ ] `uv run python scripts/check_case_study.py`

## Claims and numbers

- [ ] No new OBSERVED claim without passing the stability test
- [ ] If golden numbers or docs changed, I explain why below
- [ ] If a method or convention changed, I added or amended a decision record

## Notes for reviewers
