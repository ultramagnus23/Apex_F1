"""Case study 01: 2026 United States GP qualifying, Q3: ANT lap 14 (pole) vs VER lap 8.

Runs fully offline from the committed fixture. Writes docs/case_study_01/:
figures, tables, gate results, sensitivity results and tagged claims.

    uv run python examples/case_study_01.py
"""

from __future__ import annotations

from pathlib import Path

from apex.analysis.claims_build import Stability, build_claims
from apex.analysis.compare import build_context, compare
from apex.analysis.sensitivity import (
    pair_sensitivity,
    reference_contexts,
    summarise_events,
    summarise_segments,
)
from apex.core.laps import classify_laps
from apex.core.session import load_parquet
from apex.report.claims_report import write_claims
from apex.report.export import write_comparison

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "case_study_01"
ANT, VER = 12, 3


def main(out: Path = OUT) -> None:
    session = load_parquet(ROOT / "tests" / "fixtures" / "openf1_11392")
    classified = classify_laps(session)
    ctx = build_context(session, classified)
    cmp = compare(session, (ANT, 14), (VER, 8), ctx=ctx)
    write_comparison(
        cmp,
        session.drivers,
        out,
        "Case study 01: 2026 United States GP, Q3: ANT lap 14 vs VER lap 8",
    )

    ctxs = reference_contexts(session, classified)
    sens = pair_sensitivity(session, ctxs, ANT, VER, k=3)
    seg = summarise_segments(sens.segments)
    ev = summarise_events(sens.events)
    seg.to_csv(
        out / "sensitivity_segments.csv", index=False, float_format="%.6f", lineterminator="\n"
    )
    ev.to_csv(out / "sensitivity_events.csv", index=False, float_format="%.6f", lineterminator="\n")
    sens.segments.to_csv(
        out / "sensitivity_raw_segments.csv", index=False, float_format="%.6f", lineterminator="\n"
    )

    claims = build_claims(cmp, Stability(seg, ev), st_speeds=_st_speeds(session))
    write_claims(claims, out / "claims.md", "Case study 01: tagged claims")
    print(
        f"wrote {out} ({sens.n_pairs} pairings, {sens.n_ref_sets} reference sets, "
        f"{len(claims)} claims)"
    )


def _st_speeds(session) -> tuple[float, float]:  # type: ignore[no-untyped-def]
    laps = session.laps.set_index(["driver_number", "lap_number"])
    return (float(laps.loc[(ANT, 14), "st_speed"]), float(laps.loc[(VER, 8), "st_speed"]))


if __name__ == "__main__":
    main()
