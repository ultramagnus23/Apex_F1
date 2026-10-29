"""Two-lap comparison pipeline (Phase 2 case study engine)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from apex.analysis.corner import CornerMetricsConfig, compare_corners
from apex.core.align import (
    AlignedLap,
    AlignMethod,
    align_lap,
    anchor_to_sectors,
    distance_grid,
)
from apex.core.delta import (
    GateResult,
    SectorBoundaries,
    add_segment_sigma,
    cumulative_delta,
    estimate_sector_boundaries,
    minisector_boundaries,
    segment_deltas,
    validation_gate,
)
from apex.core.laps import classify_laps
from apex.core.session import SessionData
from apex.core.telemetry import LapTelemetry, extract_lap, lap_ref
from apex.core.track import Corner, CornerConfig, ReferenceLine, detect_corners, reference_from_laps

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class TrackModel:
    line: ReferenceLine
    grid: FloatArray
    v_ref_kmh: FloatArray
    kappa: FloatArray
    corners: list[Corner]
    lap_keys: list[str]  # valid flying laps available for calibration
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Comparison:
    session_key: int
    method: AlignMethod
    a: AlignedLap
    b: AlignedLap
    code_a: str
    code_b: str
    track: TrackModel
    grid: FloatArray
    delta: FloatArray
    sectors: pd.DataFrame
    minisectors: pd.DataFrame
    corner_segments: pd.DataFrame
    corners: pd.DataFrame
    gate: tuple[GateResult, GateResult]
    boundaries: SectorBoundaries
    unanchored: tuple[AlignedLap, AlignedLap]


def flying_laps(classified: pd.DataFrame, max_ratio: float = 1.07) -> pd.DataFrame:
    """Valid laps within ``max_ratio`` of the session's fastest valid lap (push laps)."""
    v = classified[classified["valid"]]
    fastest = float(v["lap_duration"].min())
    return v[v["lap_duration"] <= fastest * max_ratio].sort_values("lap_duration")


def build_track_model(
    session: SessionData,
    classified: pd.DataFrame,
    *,
    n_ref_laps: int = 10,
    n_speed_laps: int = 20,
    grid_step: float = 1.0,
    corner_cfg: CornerConfig | None = None,
) -> tuple[TrackModel, dict[str, LapTelemetry]]:
    corner_cfg = corner_cfg or CornerConfig()
    fl = flying_laps(classified)
    tels: dict[str, LapTelemetry] = {}
    for r in fl.itertuples():
        tel = extract_lap(session, lap_ref(session, int(r.driver_number), int(r.lap_number)))
        tels[tel.lap.key] = tel
    keys = list(tels)
    line = reference_from_laps([tels[k] for k in keys[:n_ref_laps]])
    grid = distance_grid(line.length, grid_step)
    speed_laps = [align_lap(tels[k], line) for k in keys[:n_speed_laps]]
    v_ref = np.median(np.array([a.channel("speed", grid) for a in speed_laps]), axis=0)
    kappa = np.interp(grid, line.s, line.curvature(corner_cfg.curvature_window_m))
    corners = detect_corners(grid, v_ref, kappa, line.length, corner_cfg)
    params = {
        "n_ref_laps": min(n_ref_laps, len(keys)),
        "n_speed_laps": len(speed_laps),
        "grid_step_m": grid_step,
        "corner_cfg": corner_cfg.__dict__,
    }
    return TrackModel(line, grid, v_ref, kappa, corners, keys, params), tels


def compare(
    session: SessionData,
    lap_a: tuple[int, int],
    lap_b: tuple[int, int],
    *,
    method: AlignMethod = "hybrid",
    n_minisectors: int = 25,
    anchor_sectors: bool = True,
    classified: pd.DataFrame | None = None,
    track: TrackModel | None = None,
    tels: dict[str, LapTelemetry] | None = None,
) -> Comparison:
    classified = classified if classified is not None else classify_laps(session)
    if track is None or tels is None:
        track, tels = build_track_model(session, classified)
    line = track.line
    for key in (lap_a, lap_b):
        k = f"{key[0]}:{key[1]}"
        if k not in tels:
            tels[k] = extract_lap(session, lap_ref(session, *key))
    ka, kb = f"{lap_a[0]}:{lap_a[1]}", f"{lap_b[0]}:{lap_b[1]}"
    a = align_lap(tels[ka], line, method)
    b = align_lap(tels[kb], line, method)

    # sector boundaries from the other flying laps (leave the two compared laps out)
    laps = session.laps.copy()
    laps["key"] = laps["driver_number"].astype(str) + ":" + laps["lap_number"].astype(str)
    sec = laps.set_index("key")
    cal = [align_lap(tels[k], line, "hybrid") for k in track.lap_keys if k not in (ka, kb)]
    bnd = estimate_sector_boundaries(cal, sec)
    official = {
        k: tuple(
            float(x)
            for x in sec.loc[k, ["duration_sector_1", "duration_sector_2", "duration_sector_3"]]
        )
        for k in (ka, kb)
    }
    gate = (validation_gate(a, official[ka], bnd), validation_gate(b, official[kb], bnd))  # type: ignore[arg-type]
    unanchored = (a, b)
    if anchor_sectors and method != "xy":
        sig = max(bnd.sd_s1, bnd.sd_s2)
        a = anchor_to_sectors(a, (bnd.s1, bnd.s2), (official[ka][0], sum(official[ka][:2])), sig)
        b = anchor_to_sectors(b, (bnd.s1, bnd.s2), (official[kb][0], sum(official[kb][:2])), sig)
    knots_s = np.array([0.0, bnd.s1, bnd.s2, line.length])
    ta, tb = np.diff(a.time_at(knots_s)), np.diff(b.time_at(knots_s))
    ta_u = np.diff(unanchored[0].time_at(knots_s))
    tb_u = np.diff(unanchored[1].time_at(knots_s))

    sector_rows = []
    for i, name in enumerate(("S1", "S2", "S3")):
        sector_rows.append(
            {
                "anchored_a": float(ta[i]),
                "anchored_b": float(tb[i]),
                "unanchored_delta": float(ta_u[i] - tb_u[i]),
                "sector": name,
                "official_a": official[ka][i],
                "official_b": official[kb][i],
                "official_delta": official[ka][i] - official[kb][i],
                "telemetry_a": gate[0].telemetry[i],
                "telemetry_b": gate[1].telemetry[i],
                "telemetry_delta": gate[0].telemetry[i] - gate[1].telemetry[i],
                "tolerance_a": gate[0].tolerance[i],
                "tolerance_b": gate[1].tolerance[i],
            }
        )
    sectors = pd.DataFrame(sector_rows)
    sectors["delta_error_unanchored"] = sectors["telemetry_delta"] - sectors["official_delta"]
    sectors["delta_error_anchored"] = (
        sectors["anchored_a"] - sectors["anchored_b"] - sectors["official_delta"]
    )

    grid = track.grid
    delta = cumulative_delta(a, b, grid)
    mini = segment_deltas(a, b, minisector_boundaries(line.length, n_minisectors))
    cb = [c.s_start for c in track.corners] + [line.length]
    corner_seg = segment_deltas(a, b, cb, [c.label for c in track.corners])
    sigma_s = max(bnd.sd_s1, bnd.sd_s2)
    pinned = [0.0, line.length] + ([bnd.s1, bnd.s2] if anchor_sectors and method != "xy" else [])
    mini = add_segment_sigma(mini, a, b, sigma_s, pinned)
    corner_seg = add_segment_sigma(corner_seg, a, b, sigma_s, pinned)
    corner_df = compare_corners(a, b, track.corners, CornerMetricsConfig())
    zone_sigma = []
    for _, r in corner_df.iterrows():
        for z in ("braking", "apex", "exit"):
            z0, z1 = r[f"{z}_zone"]
            sg = add_segment_sigma(
                pd.DataFrame({"s_start": [z0], "s_end": [z1], "delta": [r[f"{z}_delta_s"]]}),
                a,
                b,
                sigma_s,
                pinned,
            )
            zone_sigma.append((r.name, z, float(sg["sigma"].iloc[0])))
    for idx, z, sg in zone_sigma:
        corner_df.loc[idx, f"{z}_sigma_s"] = sg
    return Comparison(
        session.session_key,
        method,
        a,
        b,
        session.driver_code(lap_a[0]),
        session.driver_code(lap_b[0]),
        track,
        grid,
        delta,
        sectors,
        mini,
        corner_seg,
        corner_df,
        gate,
        bnd,
        unanchored,
    )
