"""Season-wide sensitivity study: how often do segment conclusions flip?

For every qualifying session of one season (from the Parquet cache written by
fetch_season.py): take the pole driver's fastest valid laps and compare them with
P2 and P3 drivers' fastest laps, under every reference-line set and alignment
method. For each corner segment with a non-"none" majority verdict it records
whether the verdict flips with the reference-line choice (method fixed) and
with the method choice (reference fixed).

Outputs (under docs/season_2025/ by default): per-session and overall tables,
and a JSON summary. Sessions that fail are recorded with the reason.

    uv run python scripts/season_study.py --year 2025
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apex.analysis.sensitivity import pair_sensitivity, reference_contexts
from apex.core.laps import classify_laps, fastest_valid
from apex.core.session import load_parquet

ROOT = Path(__file__).resolve().parents[1]


def flip_flags(raw: pd.DataFrame) -> pd.DataFrame:
    """Per (pair, segment): consensus verdict and whether it flips across choices."""
    rows = []
    for (pair, seg), g in raw.groupby(["pair", "segment"], sort=False):
        hyb = g[g["method"] == "hybrid"]
        base = g[g["ref"] == "baseline"]
        v_all = g["verdict"]
        consensus = str(v_all.value_counts().idxmax())
        if consensus == "none":
            continue  # only conclusions are judged

        # A sign flip: some configuration says A is faster beyond noise and another
        # says B is. Losing significance without a sign change is not counted here.
        def sign_flip(v: pd.Series) -> bool:
            return {"A", "B"} <= set(v)

        rows.append(
            {
                "pair": pair,
                "segment": seg,
                "consensus": consensus,
                "flips_with_reference": sign_flip(hyb["verdict"]),  # method fixed
                "flips_with_method": sign_flip(base["verdict"]),  # reference fixed
                "flips_any": sign_flip(v_all),
                "stability": float((v_all == consensus).mean()),
            }
        )
    return pd.DataFrame(rows)


def study_session(data_dir: Path, year: int, session_key: int) -> dict[str, Any]:
    session = load_parquet(data_dir / str(session_key))
    classified = classify_laps(session)
    v = classified[classified["valid"]].sort_values("lap_duration")
    best = v.groupby("driver_number", sort=False).head(1).sort_values("lap_duration")
    pole = int(best["driver_number"].iloc[0])
    ctxs = reference_contexts(session, classified)
    flags_all, pairs_meta = [], []
    for rival in [int(x) for x in best["driver_number"].iloc[1:3]]:
        sens = pair_sensitivity(session, ctxs, pole, rival, k=3)
        f = flip_flags(sens.segments)
        f["driver_a"], f["driver_b"] = sens.driver_a, sens.driver_b
        flags_all.append(f)
        pairs_meta.append(
            {
                "driver_a": sens.driver_a,
                "driver_b": sens.driver_b,
                "pairings": sens.n_pairs,
                "reference_sets": sens.n_ref_sets,
                "corner_set_mismatch": sens.corner_set_mismatch,
                "lap_gap_s": float(
                    fastest_valid(classified, pole)["lap_duration"]
                    - fastest_valid(classified, rival)["lap_duration"]
                ),
            }
        )
    flags = pd.concat(flags_all, ignore_index=True) if flags_all else pd.DataFrame()
    n = len(flags)
    return {
        "session_key": session_key,
        "pole": session.driver_code(pole),
        "pairs": pairs_meta,
        "conclusions": n,
        "flip_with_reference": int(flags["flips_with_reference"].sum()) if n else 0,
        "flip_with_method": int(flags["flips_with_method"].sum()) if n else 0,
        "flip_any": int(flags["flips_any"].sum()) if n else 0,
        "flags": flags,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--session", default="Qualifying")
    ap.add_argument("--parquet", default=str(ROOT / "cache" / "parquet"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    data_dir = Path(args.parquet)
    out = Path(args.out) if args.out else ROOT / "docs" / f"season_{args.year}"
    out.mkdir(parents=True, exist_ok=True)

    fetch = json.loads(
        (data_dir / f"fetch_{args.year}_{args.session}.json").read_text(encoding="utf-8")
    )
    results, failures = [], []
    for row in fetch:
        if row["status"] not in ("ok", "cached"):
            failures.append({"location": row["location"], "reason": row["status"]})
            continue
        t = time.time()
        try:
            r = study_session(data_dir, args.year, int(row["session_key"]))
        except Exception as exc:  # recorded, never hidden
            failures.append(
                {
                    "location": row["location"],
                    "reason": f"study failed: {type(exc).__name__}: {exc}",
                }
            )
            print(f"FAILED {row['location']}: {exc}", flush=True)
            continue
        r["location"] = row["location"]
        results.append(r)
        print(
            f"{row['location']}: {r['conclusions']} conclusions, "
            f"ref flips {r['flip_with_reference']}, method flips {r['flip_with_method']} "
            f"({time.time() - t:.0f} s)",
            flush=True,
        )

    flags = pd.concat(
        [r.pop("flags").assign(location=r["location"]) for r in results], ignore_index=True
    )
    flags.to_csv(
        out / "conclusion_flips.csv", index=False, float_format="%.6f", lineterminator="\n"
    )
    per_session = pd.DataFrame([{k: v for k, v in r.items() if k != "pairs"} for r in results])
    per_session.to_csv(out / "per_session.csv", index=False, lineterminator="\n")

    n = len(flags)
    summary = {
        "year": args.year,
        "session": args.session,
        "sessions_studied": len(results),
        "sessions_failed": failures,
        "conclusions": n,
        "flip_with_reference_rate": float(flags["flips_with_reference"].mean()) if n else None,
        "flip_with_method_rate": float(flags["flips_with_method"].mean()) if n else None,
        "flip_any_rate": float(flags["flips_any"].mean()) if n else None,
        "median_stability": float(np.median(flags["stability"])) if n else None,
        "by_consensus": (
            flags.groupby("consensus")[["flips_with_reference", "flips_with_method"]]
            .mean()
            .round(3)
            .to_dict("index")
            if n
            else {}
        ),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps({k: v for k, v in summary.items() if k != "by_consensus"}, indent=2, default=str)
    )


if __name__ == "__main__":
    main()
