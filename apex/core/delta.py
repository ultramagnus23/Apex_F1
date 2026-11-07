"""Distance-domain deltas and the official-timing validation gate.

Sign convention (ADR 0002): Δt(s) = t_A(s) − t_B(s); negative ⇒ A faster.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
import numpy.typing as npt
import pandas as pd

from apex.core.align import AlignedLap

FloatArray = npt.NDArray[np.float64]

# 1 ms official resolution => rounding error uniform in ±0.5 ms.
OFFICIAL_RESOLUTION_S = 0.001


def cumulative_delta(a: AlignedLap, b: AlignedLap, s_grid: FloatArray) -> FloatArray:
    out: FloatArray = a.time_at(s_grid) - b.time_at(s_grid)
    return out


def segment_times(lap: AlignedLap, boundaries: Sequence[float] | FloatArray) -> FloatArray:
    """Time spent in each [boundaries[i], boundaries[i+1]]."""
    t = lap.time_at(np.asarray(boundaries, dtype=np.float64))
    out: FloatArray = np.diff(t)
    return out


def minisector_boundaries(length: float, n: int = 25) -> FloatArray:
    out: FloatArray = np.linspace(0.0, length, n + 1)
    return out


def segment_deltas(
    a: AlignedLap, b: AlignedLap, boundaries: Sequence[float], labels: Sequence[str] | None = None
) -> pd.DataFrame:
    bnd = np.asarray(boundaries, dtype=np.float64)
    ta, tb = segment_times(a, bnd), segment_times(b, bnd)
    labels = list(labels) if labels is not None else [f"M{i + 1}" for i in range(len(ta))]
    return pd.DataFrame(
        {
            "segment": labels,
            "s_start": bnd[:-1],
            "s_end": bnd[1:],
            "time_a": ta,
            "time_b": tb,
            "delta": ta - tb,
        }
    )


@dataclass(frozen=True)
class SectorBoundaries:
    s1: float
    s2: float
    sd_s1: float  # robust scatter of per-lap estimates [m]
    sd_s2: float
    n_laps: int


def _robust_sd(x: FloatArray) -> float:
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def estimate_sector_boundaries(
    laps: Sequence[AlignedLap], sectors: pd.DataFrame, exclude: Sequence[str] = ()
) -> SectorBoundaries:
    """Locate the S1/S2 timing lines on the reference line.

    OpenF1 does not publish their positions. For each lap, s_k is where the
    telemetry time equals the official cumulative sector time; the boundary is
    the median over laps (excluding ``exclude`` keys, for leave-one-out use).
    ``sectors``: indexed by lap key, columns duration_sector_1/2.
    """
    est = []
    for lap in laps:
        key = lap.tel.lap.key
        if key in exclude:
            continue
        s1 = float(cast(float, sectors.loc[key, "duration_sector_1"]))
        s2 = float(cast(float, sectors.loc[key, "duration_sector_2"]))
        grid = np.linspace(0, lap.ref_length, int(lap.ref_length * 2) + 1)
        tt = lap.time_at(grid)
        est.append((np.interp(s1, tt, grid), np.interp(s1 + s2, tt, grid)))
    e = np.asarray(est)
    if len(e) < 3:
        raise ValueError("need at least 3 laps to estimate sector boundaries")
    return SectorBoundaries(
        float(np.median(e[:, 0])),
        float(np.median(e[:, 1])),
        _robust_sd(e[:, 0]),
        _robust_sd(e[:, 1]),
        len(e),
    )


@dataclass(frozen=True)
class GateResult:
    lap_key: str
    official: tuple[float, float, float]
    telemetry: tuple[float, float, float]
    tolerance: tuple[float, float, float]
    lap_time_z: float | None
    lap_z_limit: float

    @property
    def errors(self) -> tuple[float, float, float]:
        o, t = self.official, self.telemetry
        return (t[0] - o[0], t[1] - o[1], t[2] - o[2])

    @property
    def sectors_pass(self) -> bool:
        return all(abs(e) <= tol for e, tol in zip(self.errors, self.tolerance, strict=True))

    @property
    def lap_pass(self) -> bool:
        return self.lap_time_z is None or abs(self.lap_time_z) <= self.lap_z_limit

    @property
    def passed(self) -> bool:
        return self.sectors_pass and self.lap_pass


def validation_gate(
    lap: AlignedLap,
    official_sectors: tuple[float, float, float],
    boundaries: SectorBoundaries,
    *,
    k_sigma: float = 3.0,
    lap_z_limit: float = 3.0,
) -> GateResult:
    """Compare telemetry-derived sector times with official ones.

    Tolerance per sector = k·sqrt((σ_s/v_start)² + (σ_s/v_end)² + σ_res²), where
    σ_s is the measured scatter of boundary estimates across laps (the
    along-track distance uncertainty of a single lap), v the lap's speed at
    each sector boundary, and σ_res = 1 ms/√12 (official rounding). The lap
    gate is the z-score of the unconstrained telemetry lap time.
    """
    L = lap.ref_length
    b = np.array([0.0, boundaries.s1, boundaries.s2, L])
    t = lap.time_at(b)
    tel = (float(t[1] - t[0]), float(t[2] - t[1]), float(t[3] - t[2]))
    v = np.interp(b, lap.s, lap.w)
    sd = np.array([max(boundaries.sd_s1, boundaries.sd_s2)] * 4)
    sd[0] = sd[3] = 0.0  # lap ends are pinned by the official lap time (constrained fit)
    if not lap.params.get("lap_time_constrained", False):
        sd[0] = sd[3] = sd[1]
    pt = sd / v
    res = OFFICIAL_RESOLUTION_S / np.sqrt(12)
    tol = tuple(float(k_sigma * np.sqrt(pt[i] ** 2 + pt[i + 1] ** 2 + res**2)) for i in range(3))
    z = lap.params.get("lap_time_z")
    return GateResult(
        lap.tel.lap.key,
        official_sectors,
        tel,
        tol,  # type: ignore[arg-type]
        None if z is None else float(z),
        lap_z_limit,
    )


def provisional_sigma(
    laps: Sequence[AlignedLap], s_query: FloatArray, sigma_s_m: float, pinned: Sequence[float]
) -> FloatArray:
    """Provisional 1σ timing uncertainty [s] of a single time-at-distance value,
    combined over ``laps`` (independent): sqrt(Σ (σ_s / w_lap(s))²).

    Model (Phase 2, superseded by the Phase 3 study): each lap's distance has an
    independent random error of σ_s metres (the measured cross-lap scatter of
    sector-line estimates), except at ``pinned`` positions (lap ends, anchored
    sector lines) where it is zero.
    """
    s_query = np.asarray(s_query, dtype=np.float64)
    var = np.zeros_like(s_query)
    for lap in laps:
        var += (sigma_s_m / np.interp(s_query, lap.s, lap.w)) ** 2
    pin = np.zeros(len(s_query), dtype=bool)
    for p in pinned:
        pin |= np.abs(s_query - p) < 1e-6
    out: FloatArray = np.where(pin, 0.0, np.sqrt(var))
    return out


def add_segment_sigma(
    seg: pd.DataFrame, a: AlignedLap, b: AlignedLap, sigma_s_m: float, pinned: Sequence[float]
) -> pd.DataFrame:
    """Attach provisional σ of each segment delta and a ``within_noise`` flag (|Δ| < 2σ)."""
    s0 = provisional_sigma([a, b], seg["s_start"].to_numpy(float), sigma_s_m, pinned)
    s1 = provisional_sigma([a, b], seg["s_end"].to_numpy(float), sigma_s_m, pinned)
    out = seg.copy()
    out["sigma"] = np.sqrt(s0**2 + s1**2)
    out["within_noise"] = out["delta"].abs() < 2 * out["sigma"]
    return out
