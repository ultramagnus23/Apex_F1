"""Two-lap comparison pipeline.

``SessionContext`` holds everything computed once per session (track model,
aligned push laps, per-lap sector-line estimates, calibrated noise model);
``compare`` then aligns and compares two laps against it.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    cumulative_delta,
    minisector_boundaries,
    segment_deltas,
    validation_gate,
)
from apex.core.laps import classify_laps
from apex.core.session import SessionData
from apex.core.telemetry import LapTelemetry, extract_lap, lap_ref
from apex.core.track import Corner, CornerConfig, ReferenceLine, detect_corners, reference_from_laps
from apex.core.uncertainty import NoiseModel, calibrate, delta_sigma, segment_sigma

FloatArray = npt.NDArray[np.float64]
LapKey = tuple[int, int]


def key_of(lap: LapKey) -> str:
    return f"{lap[0]}:{lap[1]}"


@dataclass(frozen=True)
class TrackModel:
    line: ReferenceLine
    grid: FloatArray
    v_ref_kmh: FloatArray
    kappa: FloatArray
    corners: list[Corner]
    lap_keys: list[str]  # valid push laps available for calibration
    params: dict[str, Any] = field(default_factory=dict)


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
        try:
            tel = extract_lap(session, lap_ref(session, int(r.driver_number), int(r.lap_number)))
        except ValueError:
            continue  # car data does not bracket the lap: skip, never guess
        tels[tel.lap.key] = tel
    keys = list(tels)
    if len(keys) < 5:
        raise ValueError(f"only {len(keys)} usable push laps; cannot build a track model")
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


def _robust_sd(x: FloatArray) -> float:
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


@dataclass
class SessionContext:
    session: SessionData
    classified: pd.DataFrame
    track: TrackModel
    tels: dict[str, LapTelemetry]
    official: pd.DataFrame  # indexed by lap key
    unanchored: dict[str, AlignedLap]  # hybrid, lap-time constrained
    line_estimates: dict[str, tuple[float, float]]  # per-lap sector-line estimate
    noise: NoiseModel

    def boundaries(self, exclude: Iterable[str] = ()) -> SectorBoundaries:
        ex = set(exclude)
        e = np.array([v for k, v in self.line_estimates.items() if k not in ex])
        if len(e) < 3:
            raise ValueError("fewer than 3 laps left to estimate sector lines")
        return SectorBoundaries(
            float(np.median(e[:, 0])),
            float(np.median(e[:, 1])),
            _robust_sd(e[:, 0]),
            _robust_sd(e[:, 1]),
            len(e),
        )

    def official_sectors(self, key: str) -> tuple[float, float, float]:
        r = self.official.loc[key]
        return (
            float(r["duration_sector_1"]),
            float(r["duration_sector_2"]),
            float(r["duration_sector_3"]),
        )

    def telemetry(self, key: str) -> LapTelemetry:
        if key not in self.tels:
            d, n = (int(x) for x in key.split(":"))
            self.tels[key] = extract_lap(self.session, lap_ref(self.session, d, n))
        return self.tels[key]

    def prepare(
        self,
        key: str,
        method: AlignMethod = "hybrid",
        anchor: bool = True,
        bnd: SectorBoundaries | None = None,
    ) -> tuple[AlignedLap, AlignedLap, GateResult]:
        """(aligned [anchored if requested], unanchored, gate) for one lap."""
        bnd = bnd or self.boundaries(exclude=[key])
        if method == "hybrid" and key in self.unanchored:
            un = self.unanchored[key]
        else:
            un = align_lap(self.telemetry(key), self.track.line, method)
        off = self.official_sectors(key)
        gate = validation_gate(un, off, bnd)
        lap = un
        if anchor and method != "xy":
            lap = anchor_to_sectors(
                un, (bnd.s1, bnd.s2), (off[0], off[0] + off[1]), max(bnd.sd_s1, bnd.sd_s2)
            )
        return lap, un, gate


def _line_estimate(lap: AlignedLap, s1: float, s2: float) -> tuple[float, float]:
    grid = np.linspace(0, lap.ref_length, int(lap.ref_length * 2) + 1)
    tt = lap.time_at(grid)
    return float(np.interp(s1, tt, grid)), float(np.interp(s1 + s2, tt, grid))


def build_context(session: SessionData, classified: pd.DataFrame | None = None) -> SessionContext:
    classified = classified if classified is not None else classify_laps(session)
    track, tels = build_track_model(session, classified)
    laps = session.laps.copy()
    laps["key"] = laps["driver_number"].astype(str) + ":" + laps["lap_number"].astype(str)
    official = laps.set_index("key")
    un = {k: align_lap(tels[k], track.line, "hybrid") for k in track.lap_keys}
    est = {
        k: _line_estimate(
            un[k],
            float(official.loc[k, "duration_sector_1"]),
            float(official.loc[k, "duration_sector_2"]),
        )
        for k in track.lap_keys
    }
    ctx = SessionContext(session, classified, track, tels, official, un, est, NoiseModel(0.0))
    loo = {}
    for k in track.lap_keys:
        b = ctx.boundaries(exclude=[k])
        loo[k] = (b.s1, b.s2)
    ctx.noise = calibrate(list(un.values()), official, loo)
    return ctx


@dataclass(frozen=True)
class Comparison:
    session_key: int
    method: AlignMethod
    anchored: bool
    a: AlignedLap
    b: AlignedLap
    code_a: str
    code_b: str
    track: TrackModel
    grid: FloatArray
    delta: FloatArray
    delta_sigma: FloatArray
    sectors: pd.DataFrame
    minisectors: pd.DataFrame
    corner_segments: pd.DataFrame
    corners: pd.DataFrame
    gate: tuple[GateResult, GateResult]
    boundaries: SectorBoundaries
    unanchored: tuple[AlignedLap, AlignedLap]
    noise: NoiseModel


def with_sigma(seg: pd.DataFrame, a: AlignedLap, b: AlignedLap, noise: NoiseModel) -> pd.DataFrame:
    out = seg.copy()
    out["sigma"] = segment_sigma(
        a, b, out["s_start"].to_numpy(float), out["s_end"].to_numpy(float), noise
    )
    out["within_noise"] = out["delta"].abs() < 2 * out["sigma"]
    return out


def compare(
    session: SessionData,
    lap_a: LapKey,
    lap_b: LapKey,
    *,
    method: AlignMethod = "hybrid",
    n_minisectors: int = 25,
    anchor_sectors: bool = True,
    classified: pd.DataFrame | None = None,
    ctx: SessionContext | None = None,
) -> Comparison:
    ctx = ctx or build_context(session, classified)
    line = ctx.track.line
    ka, kb = key_of(lap_a), key_of(lap_b)
    # sector lines from the other push laps (both compared laps left out)
    bnd = ctx.boundaries(exclude=[ka, kb])
    a, ua, ga = ctx.prepare(ka, method, anchor_sectors, bnd)
    b, ub, gb = ctx.prepare(kb, method, anchor_sectors, bnd)
    gate = (ga, gb)
    off = {ka: ctx.official_sectors(ka), kb: ctx.official_sectors(kb)}

    knots_s = np.array([0.0, bnd.s1, bnd.s2, line.length])
    ta, tb = np.diff(a.time_at(knots_s)), np.diff(b.time_at(knots_s))
    ta_u, tb_u = np.diff(ua.time_at(knots_s)), np.diff(ub.time_at(knots_s))
    sector_rows = []
    for i, name in enumerate(("S1", "S2", "S3")):
        sector_rows.append(
            {
                "sector": name,
                "official_a": off[ka][i],
                "official_b": off[kb][i],
                "official_delta": off[ka][i] - off[kb][i],
                "anchored_a": float(ta[i]),
                "anchored_b": float(tb[i]),
                "unanchored_delta": float(ta_u[i] - tb_u[i]),
                "telemetry_a": ga.telemetry[i],
                "telemetry_b": gb.telemetry[i],
                "telemetry_delta": ga.telemetry[i] - gb.telemetry[i],
                "tolerance_a": ga.tolerance[i],
                "tolerance_b": gb.tolerance[i],
            }
        )
    sectors = pd.DataFrame(sector_rows)
    sectors["delta_error_unanchored"] = sectors["telemetry_delta"] - sectors["official_delta"]
    sectors["delta_error_anchored"] = (
        sectors["anchored_a"] - sectors["anchored_b"] - sectors["official_delta"]
    )

    grid = ctx.track.grid
    delta = cumulative_delta(a, b, grid)
    dsig = delta_sigma(a, b, grid, ctx.noise)
    mini = with_sigma(
        segment_deltas(a, b, minisector_boundaries(line.length, n_minisectors)), a, b, ctx.noise
    )
    corners = ctx.track.corners
    cb = [c.s_start for c in corners] + [line.length]
    corner_seg = with_sigma(segment_deltas(a, b, cb, [c.label for c in corners]), a, b, ctx.noise)
    corner_df = compare_corners(a, b, corners, CornerMetricsConfig())
    for z in ("braking", "apex", "exit"):
        z0 = np.array([r[0] for r in corner_df[f"{z}_zone"]])
        z1 = np.array([r[1] for r in corner_df[f"{z}_zone"]])
        corner_df[f"{z}_sigma_s"] = segment_sigma(a, b, z0, z1, ctx.noise)
    return Comparison(
        session.session_key,
        method,
        anchor_sectors and method != "xy",
        a,
        b,
        session.driver_code(lap_a[0]),
        session.driver_code(lap_b[0]),
        ctx.track,
        grid,
        delta,
        dsig,
        sectors,
        mini,
        corner_seg,
        corner_df,
        gate,
        bnd,
        (ua, ub),
        ctx.noise,
    )
