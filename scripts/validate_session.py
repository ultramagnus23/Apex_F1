"""Session-wide validation of distance alignment against official timing.

For every valid flying lap: align it (each method), estimate the sector lines
from all *other* flying laps (leave-one-out), and compare telemetry-derived
lap and sector times with official ones. Writes JSON evidence for
docs/VALIDATION.md.

Usage:
    uv run python scripts/validate_session.py --session-key 11392 \
        --out docs/data/validation_11392.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apex.analysis.compare import build_track_model
from apex.core.align import align_lap, anchor_to_sectors
from apex.core.delta import estimate_sector_boundaries, validation_gate
from apex.core.laps import classify_laps
from apex.core.session import load_openf1


def q(x: pd.Series) -> dict[str, float]:
    d = x.describe(percentiles=[0.05, 0.5, 0.95])
    return {k: round(float(v), 6) for k, v in d.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-key", type=int, required=True)
    ap.add_argument("--cache", default="cache/openf1")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    session = load_openf1(args.session_key, args.cache, offline=True)
    classified = classify_laps(session)
    track, tels = build_track_model(session, classified)
    laps = session.laps.copy()
    laps["key"] = laps["driver_number"].astype(str) + ":" + laps["lap_number"].astype(str)
    sec = laps.set_index("key")
    keys = track.lap_keys
    hyb = {k: align_lap(tels[k], track.line, "hybrid") for k in keys}

    rows: list[dict[str, Any]] = []
    for k in keys:
        bnd = estimate_sector_boundaries([hyb[j] for j in keys], sec, exclude=[k])
        off = tuple(
            float(x)
            for x in sec.loc[k, ["duration_sector_1", "duration_sector_2", "duration_sector_3"]]
        )
        row: dict[str, Any] = {
            "lap": k,
            "lap_duration": float(sec.loc[k, "lap_duration"]),
            "s1_line": bnd.s1,
            "s2_line": bnd.s2,
        }
        for method in ("hybrid", "speed", "xy"):
            lap = hyb[k] if method == "hybrid" else align_lap(tels[k], track.line, method)
            g = validation_gate(lap, off, bnd)  # type: ignore[arg-type]
            row |= {f"{method}_e{i + 1}": e for i, e in enumerate(g.errors)}
            row[f"{method}_lap_err"] = lap.lap_time_telemetry - off[0] - off[1] - off[2]
            if method == "hybrid":
                row |= {f"tol{i + 1}": t for i, t in enumerate(g.tolerance)}
                row["lap_z"] = g.lap_time_z
                row["lap_err_unconstrained"] = (
                    lap.params["lap_time_unconstrained_s"] - row["lap_duration"]
                )
                row["sigma_lap_pred"] = lap.params["sigma_lap_time_s"]
                row["b"] = lap.params["b"]
                row["resid_rms_m"] = lap.params["resid_rms_m"]
                row["sectors_pass"] = g.sectors_pass
                row["lap_pass"] = g.lap_pass
                anc = anchor_to_sectors(
                    lap, (bnd.s1, bnd.s2), (off[0], off[0] + off[1]), max(bnd.sd_s1, bnd.sd_s2)
                )
                t = anc.time_at(np.array([0.0, bnd.s1, bnd.s2, track.line.length]))
                row |= {f"anchored_e{i + 1}": float(np.diff(t)[i] - off[i]) for i in range(3)}
                row |= {f"warp_z{i + 1}": z for i, z in enumerate(anc.params["sector_warp_z"])}
        rows.append(row)
    df = pd.DataFrame(rows)

    report: dict[str, Any] = {
        "session_key": args.session_key,
        "n_laps": len(df),
        "reference_line_m": track.line.length,
        "reference_line_params": track.line.params,
        "corners": [c.__dict__ for c in track.corners],
        "hybrid": {
            "lap_err_unconstrained_s": q(df["lap_err_unconstrained"]),
            "sigma_lap_pred_s": q(df["sigma_lap_pred"]),
            "lap_z": q(df["lap_z"]),
            "lap_z_abs_gt3": int((df["lap_z"].abs() > 3).sum()),
            "scale_b": q(df["b"]),
            "position_resid_rms_m": q(df["resid_rms_m"]),
            "sector_err_s": {f"S{i}": q(df[f"hybrid_e{i}"]) for i in (1, 2, 3)},
            "tolerance_s": {f"S{i}": q(df[f"tol{i}"]) for i in (1, 2, 3)},
            "sectors_pass": int(df["sectors_pass"].sum()),
            "lap_pass": int(df["lap_pass"].sum()),
            "both_pass": int((df["sectors_pass"] & df["lap_pass"]).sum()),
            "anchored_sector_err_max_abs_s": float(
                df[["anchored_e1", "anchored_e2", "anchored_e3"]].abs().max().max()
            ),
            "warp_z": q(pd.concat([df["warp_z1"], df["warp_z2"]])),
            "warp_z_abs_gt3": int(((df["warp_z1"].abs() > 3) | (df["warp_z2"].abs() > 3)).sum()),
        },
        "speed": {
            "lap_err_s": q(df["speed_lap_err"]),
            "sector_err_s": {f"S{i}": q(df[f"speed_e{i}"]) for i in (1, 2, 3)},
        },
        "xy": {
            "lap_err_s": q(df["xy_lap_err"]),
            "sector_err_s": {f"S{i}": q(df[f"xy_e{i}"]) for i in (1, 2, 3)},
        },
        "failures": df[~(df["sectors_pass"] & df["lap_pass"])][
            ["lap", "lap_z", "hybrid_e1", "hybrid_e2", "hybrid_e3", "tol1", "tol2", "tol3"]
        ]
        .round(4)
        .to_dict("records"),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, default=float) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("corners", "reference_line_params")},
            indent=1,
            default=float,
        )
    )


if __name__ == "__main__":
    main()
