"""Case study 01: 2026 United States GP qualifying, Q3: ANT lap 14 (pole) vs VER lap 8 (P2).

Runs fully offline from the committed fixture and writes docs/case_study_01/.

    uv run python examples/case_study_01.py
"""

from __future__ import annotations

from pathlib import Path

from apex.analysis.compare import compare
from apex.core.session import load_parquet
from apex.report.export import write_comparison

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    session = load_parquet(ROOT / "tests" / "fixtures" / "openf1_11392")
    cmp = compare(session, (12, 14), (3, 8))
    out = write_comparison(
        cmp,
        session.drivers,
        ROOT / "docs" / "case_study_01",
        "Case study 01 — 2026 United States GP, Q3: ANT lap 14 vs VER lap 8",
    )
    print(f"wrote {out}")
