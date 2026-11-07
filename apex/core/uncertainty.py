"""Calibrated timing uncertainty for distance-aligned laps.

Error model (see docs/METHODOLOGY.md §8)
---------------------------------------
A lap's distance s(t) comes from integrating speed, so its error behaves like a
random walk in distance: variance grows ∝ distance travelled. Every official
timing point the lap is pinned to (lap start/end, and with sector anchoring the
two sector lines) forces that error back to ~zero. Between two consecutive pins
k0 < k1 the distance error is therefore modelled as a **Brownian bridge**:

    Var[δs(s)]          = σ_rw² (s − k0)(k1 − s) / (k1 − k0)
    Cov[δs(s1), δs(s2)] = σ_rw² (s1 − k0)(k1 − s2) / (k1 − k0),   s1 ≤ s2 in one piece
    (zero across pieces)

and a distance error δs becomes a time error δs / w(s), w = ds/dt. σ_rw is
calibrated from the measured distance errors at the sector lines of
lap-constrained, *unanchored* laps (where the bridge spans [0, L]).

Two resolution terms are added independently per lap:
  * official timing rounding at each pin: (1 ms)/√12, applied as a constant
    floor (each pinned time carries it);
  * the telemetry sample interval: inside a sample interval Apex assumes speed
    is linear in time. The worst-case distance error of that assumption is
    Δt·|Δw|/8; treating it as uniform gives σ = Δt·|Δw|/(8√3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import numpy as np
import numpy.typing as npt
import pandas as pd

from apex.core.align import AlignedLap

FloatArray = npt.NDArray[np.float64]

OFFICIAL_RESOLUTION_SIGMA_S = 0.001 / np.sqrt(12.0)


@dataclass(frozen=True)
class NoiseModel:
    sigma_rw: float  # m / sqrt(m)
    official_sigma_s: float = OFFICIAL_RESOLUTION_SIGMA_S
    calibration: dict[str, Any] = field(default_factory=dict)


def pins_of(lap: AlignedLap) -> FloatArray:
    """Distances at which this lap is pinned to official timing."""
    pins = [0.0, lap.ref_length]
    if lap.params.get("sector_anchored") and lap.knots is not None:
        pins += list(np.asarray(lap.knots[1], dtype=np.float64))
    return np.unique(np.asarray(pins, dtype=np.float64))


def _bridge_var(s: FloatArray, pins: FloatArray, sigma_rw: float) -> FloatArray:
    j = np.clip(np.searchsorted(pins, s, side="right") - 1, 0, len(pins) - 2)
    k0, k1 = pins[j], pins[j + 1]
    v = sigma_rw**2 * np.clip(s - k0, 0, None) * np.clip(k1 - s, 0, None) / (k1 - k0)
    out: FloatArray = v
    return out


def _bridge_cov(s1: FloatArray, s2: FloatArray, pins: FloatArray, sigma_rw: float) -> FloatArray:
    lo, hi = np.minimum(s1, s2), np.maximum(s1, s2)
    j1 = np.clip(np.searchsorted(pins, lo, side="right") - 1, 0, len(pins) - 2)
    j2 = np.clip(np.searchsorted(pins, hi, side="right") - 1, 0, len(pins) - 2)
    k0, k1 = pins[j1], pins[j1 + 1]
    c = sigma_rw**2 * np.clip(lo - k0, 0, None) * np.clip(k1 - hi, 0, None) / (k1 - k0)
    out: FloatArray = np.where(j1 == j2, c, 0.0)
    return out


def _sampling_sigma_t(lap: AlignedLap, s: FloatArray) -> FloatArray:
    t, sv, w = lap.t_rel, lap.s, lap.w
    i = np.clip(np.searchsorted(sv, s, side="right") - 1, 0, len(sv) - 2)
    dt = t[i + 1] - t[i]
    dw = np.abs(w[i + 1] - w[i])
    ws = np.maximum(np.interp(s, sv, w), 1e-6)
    out: FloatArray = dt * dw / (8.0 * np.sqrt(3.0)) / ws
    return out


def lap_sigma(lap: AlignedLap, s: FloatArray, model: NoiseModel) -> FloatArray:
    """1σ uncertainty of this lap's time at distance s [s]."""
    s = np.asarray(s, dtype=np.float64)
    w = np.maximum(np.interp(s, lap.s, lap.w), 1e-6)
    var = _bridge_var(s, pins_of(lap), model.sigma_rw) / w**2
    var += _sampling_sigma_t(lap, s) ** 2 + model.official_sigma_s**2
    out: FloatArray = np.sqrt(var)
    return out


def delta_sigma(a: AlignedLap, b: AlignedLap, s: FloatArray, model: NoiseModel) -> FloatArray:
    """1σ uncertainty of Δt(s) = t_A(s) − t_B(s), laps independent."""
    out: FloatArray = np.sqrt(lap_sigma(a, s, model) ** 2 + lap_sigma(b, s, model) ** 2)
    return out


def _segment_var_one(lap: AlignedLap, s0: FloatArray, s1: FloatArray, m: NoiseModel) -> FloatArray:
    pins = pins_of(lap)
    w0 = np.maximum(np.interp(s0, lap.s, lap.w), 1e-6)
    w1 = np.maximum(np.interp(s1, lap.s, lap.w), 1e-6)
    v = (
        _bridge_var(s0, pins, m.sigma_rw) / w0**2
        + _bridge_var(s1, pins, m.sigma_rw) / w1**2
        - 2.0 * _bridge_cov(s0, s1, pins, m.sigma_rw) / (w0 * w1)
    )
    v = np.maximum(v, 0.0)
    v += _sampling_sigma_t(lap, s0) ** 2 + _sampling_sigma_t(lap, s1) ** 2
    v += 2 * m.official_sigma_s**2
    out: FloatArray = v
    return out


def segment_sigma(
    a: AlignedLap,
    b: AlignedLap,
    s0: Sequence[float] | FloatArray,
    s1: Sequence[float] | FloatArray,
    model: NoiseModel,
) -> FloatArray:
    """1σ of a segment-time delta [(t_A(s1)−t_A(s0)) − (t_B(s1)−t_B(s0))]."""
    s0a = np.asarray(s0, dtype=np.float64)
    s1a = np.asarray(s1, dtype=np.float64)
    out: FloatArray = np.sqrt(
        _segment_var_one(a, s0a, s1a, model) + _segment_var_one(b, s0a, s1a, model)
    )
    return out


def calibrate(
    laps: Sequence[AlignedLap],
    official: pd.DataFrame,
    boundaries: dict[str, tuple[float, float]],
) -> NoiseModel:
    """Fit σ_rw from sector-line errors of lap-constrained, unanchored laps.

    ``official``: indexed by lap key with duration_sector_1/2. ``boundaries``:
    per lap key, the (s1, s2) sector lines estimated *without* that lap.
    For each lap and line, δs = (t_tel(line) − t_official)·w(line); under the
    bridge over [0, L], E[δs²] = σ_rw² s(L−s)/L. σ_rw² is the mean of the
    normalised squares (not a robust estimator: tails count).
    """
    norm, raw = [], []
    for lap in laps:
        if lap.params.get("sector_anchored"):
            raise ValueError("calibrate on unanchored laps")
        key = lap.tel.lap.key
        b1, b2 = boundaries[key]
        o1 = float(cast(float, official.loc[key, "duration_sector_1"]))
        o2 = o1 + float(cast(float, official.loc[key, "duration_sector_2"]))
        t = lap.time_at(np.array([0.0, b1, b2]))
        L = lap.ref_length
        for line, tt, oo in ((b1, t[1] - t[0], o1), (b2, t[2] - t[0], o2)):
            ds = (tt - oo) * float(np.interp(line, lap.s, lap.w))
            raw.append(ds)
            norm.append(ds**2 / (line * (L - line) / L))
    sig = float(np.sqrt(np.mean(norm)))
    r = np.asarray(raw)
    return NoiseModel(
        sig,
        calibration={
            "n_laps": len(laps),
            "n_points": len(raw),
            "distance_error_rms_m": float(np.sqrt(np.mean(r**2))),
            "distance_error_mad_sd_m": float(1.4826 * np.median(np.abs(r - np.median(r)))),
            "estimator": "sqrt(mean(ds^2 / (s(L-s)/L)))",
        },
    )
