"""Write a Comparison to disk: figures, tables, gate results and a markdown summary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apex.analysis.compare import Comparison
from apex.report.figures import corner_bars, overlay, takeaway


def _fmt(x: Any, nd: int = 3) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    return f"{x:+.{nd}f}" if isinstance(x, float) else str(x)


def gate_dict(cmp: Comparison) -> dict[str, Any]:
    out: dict[str, Any] = {"sector_boundaries": cmp.boundaries.__dict__, "laps": []}
    for g, lap in zip(cmp.gate, (cmp.a, cmp.b), strict=True):
        out["laps"].append(
            {
                "lap": g.lap_key,
                "official_sectors_s": g.official,
                "telemetry_sectors_unanchored_s": g.telemetry,
                "errors_s": g.errors,
                "tolerance_s": g.tolerance,
                "lap_time_z": g.lap_time_z,
                "sector_warp_shift_m": lap.params.get("sector_shift_m"),
                "sector_warp_z": lap.params.get("sector_warp_z"),
                "passed": g.passed,
            }
        )
    return out


def write_comparison(cmp: Comparison, drivers: pd.DataFrame, out: Path, title: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    overlay(cmp, drivers, out / "overlay.png")
    corner_bars(cmp, out / "corners.png")
    cmp.sectors.to_csv(out / "sectors.csv", index=False, float_format="%.6f", lineterminator="\n")
    cmp.minisectors.to_csv(
        out / "minisectors.csv", index=False, float_format="%.6f", lineterminator="\n"
    )
    cmp.corner_segments.to_csv(
        out / "corner_segments.csv", index=False, float_format="%.6f", lineterminator="\n"
    )
    cmp.corners.to_csv(out / "corners.csv", index=False, float_format="%.4f", lineterminator="\n")
    gate = gate_dict(cmp)
    (out / "gate.json").write_text(
        json.dumps(gate, indent=2, default=float) + "\n", encoding="utf-8", newline="\n"
    )

    a, b = cmp.code_a, cmp.code_b
    la, lb = cmp.a.tel.lap, cmp.b.tel.lap
    lines = [
        f"# {title}",
        "",
        f"**{takeaway(cmp)}**",
        "",
        f"- Lap A: {a} lap {la.lap_number}, {la.lap_duration:.3f} s (official)",
        f"- Lap B: {b} lap {lb.lap_number}, {lb.lap_duration:.3f} s (official)",
        f"- Alignment: `{cmp.method}`, sector-anchored; reference line "
        f"{cmp.track.line.length:.1f} m",
        "",
        "## Validation gate",
        "",
        "| Lap | lap-time z | sector errors before anchoring [ms] | tolerance [ms] | "
        "anchor shift [m] (z) | result |",
        "|---|---|---|---|---|---|",
    ]
    for g in gate["laps"]:
        errs = ", ".join(f"{e * 1000:+.0f}" for e in g["errors_s"])
        tols = ", ".join(f"{t * 1000:.0f}" for t in g["tolerance_s"])
        sh = ", ".join(
            f"{s:+.1f} ({z:+.2f})"
            for s, z in zip(g["sector_warp_shift_m"] or [], g["sector_warp_z"] or [], strict=True)
        )
        lines.append(
            f"| {g['lap']} | {g['lap_time_z']:+.2f} | {errs} | {tols} | {sh} | "
            f"{'PASS' if g['passed'] else 'FAIL'} |"
        )
    lines += [
        "",
        "## Sectors",
        "",
        "| Sector | official Δ [s] (OBSERVED) | telemetry-only Δ [s] | anchored Δ [s] |",
        "|---|---|---|---|",
    ]
    for r in cmp.sectors.itertuples():
        lines.append(
            f"| {r.sector} | {r.official_delta:+.3f} | {r.unanchored_delta:+.3f} | "
            f"{r.anchored_a - r.anchored_b:+.3f} |"
        )
    lines += [
        "",
        f"## Corner segments ({a}−{b}; negative = {a} faster)",
        "",
        "| Segment | from–to [m] | Δ [s] | ±2σ [s] | |",
        "|---|---|---|---|---|",
    ]
    for r in cmp.corner_segments.itertuples():
        tag = "within noise" if r.within_noise else "exceeds 2σ"
        lines.append(
            f"| {r.segment} | {r.s_start:.0f}–{r.s_end:.0f} | {r.delta:+.3f} | "
            f"{2 * r.sigma:.3f} | {tag} |"
        )
    lines += [
        "",
        "## Braking corners (raw-sample events; resolution = half the sample spacing)",
        "",
        f"| Corner | v_min {a}/{b} [km/h] | brake-on Δs [m] (±res) | throttle pickup Δs [m] | "
        "exit speed Δ [km/h]* |",
        "|---|---|---|---|---|",
    ]
    for r in cmp.corners[cmp.corners["kind"] == "braking"].itertuples():
        res = r.brake_on_resolution_m
        lines.append(
            f"| {r.corner} | {r.v_min_kmh_A:.0f}/{r.v_min_kmh_B:.0f} | "
            f"{_fmt(r.brake_on_s_diff, 1)} (±{res:.0f}) | {_fmt(r.pickup_s_diff, 1)} | "
            f"{_fmt(r.v_exit_kmh_diff, 1)} |"
            if isinstance(res, float)
            else f"| {r.corner} | {r.v_min_kmh_A:.0f}/{r.v_min_kmh_B:.0f} | – | "
            f"{_fmt(r.pickup_s_diff, 1)} | {_fmt(r.v_exit_kmh_diff, 1)} |"
        )
    lines += [
        "",
        f"Δs < 0 means {a}'s event happens earlier on track. *Exit speed is interpolated "
        "at apex + 100 m, not observed. Corner labels C1… are Apex's own numbering, not "
        "official turn numbers.",
        "",
        "Uncertainty here is a provisional, conservative model (independent 3 m distance error "
        "per lap at each segment end). Phase 3 replaces it with measured stability.",
        "",
    ]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return out
