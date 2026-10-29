"""Distance-domain alignment of laps.

Three methods map each car-data sample to distance s along the reference line:

``speed``   Integrate speed from the lap start (``date_start``) and scale so the
            lap spans exactly the reference length. Time origin = ``date_start``,
            so the telemetry lap time equals the official one *by construction*.
``xy``      Project position samples onto the reference line; car samples get s
            by interpolating s(t) of the position stream. Noisy (~5 m/sample).
``hybrid``  (default) Shape from integrated speed, origin and scale from a
            robust affine fit to the projected positions over the whole lap:
            s = a + b·s_int(t). Time origin = interpolated crossing of s = 0.
            The unconstrained telemetry lap time t(L) − t(0) is independent
            of the official time; its z-score against it is the lap gate.
            By default (a, b) are then updated by constrained GLS so that
            t(L) − t(0) equals the official lap time exactly.

Conventions: s in metres, t in seconds relative to the lap's own s = 0
crossing (``t_rel``). See docs/METHODOLOGY.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
from scipy.interpolate import PchipInterpolator

from apex.core.telemetry import LapTelemetry
from apex.core.track import ReferenceLine, project

FloatArray = npt.NDArray[np.float64]
AlignMethod = Literal["hybrid", "speed", "xy"]
Resample = Literal["linear", "pchip", "previous"]

CONTINUOUS = ("speed", "rpm", "throttle")
DISCRETE = ("gear", "brake")


def integrate_speed(t: FloatArray, v_kmh: FloatArray) -> FloatArray:
    """Cumulative distance [m] by the trapezoid rule (exact for piecewise-linear v)."""
    v = v_kmh / 3.6
    out: FloatArray = np.r_[0.0, np.cumsum(np.diff(t) * (v[1:] + v[:-1]) / 2.0)]
    return out


def invert_trapezoid(
    t: FloatArray, s: FloatArray, w: FloatArray, s_query: FloatArray
) -> FloatArray:
    """Exact time at distance for piecewise-linear speed w(t) [distance units/s].

    Within [t_i, t_i+1]: s(τ) = s_i + w_i τ + (w_i+1 − w_i) τ² / (2Δ). Solves the
    quadratic for τ. Requires s non-decreasing and w ≥ 0.
    """
    s_query = np.asarray(s_query, dtype=np.float64)
    i = np.clip(np.searchsorted(s, s_query, side="right") - 1, 0, len(s) - 2)
    dt = t[i + 1] - t[i]
    w0, w1 = w[i], w[i + 1]
    ds = s_query - s[i]
    acc = (w1 - w0) / dt  # dw/dτ
    with np.errstate(divide="ignore", invalid="ignore"):
        disc = np.maximum(w0 * w0 + 2.0 * acc * ds, 0.0)
        tau_quad = (-w0 + np.sqrt(disc)) / acc
        tau_lin = ds / w0
    small = np.abs(acc) * dt < 1e-9 * np.maximum(w0, 1e-9)
    tau = np.where(small, tau_lin, tau_quad)
    tau = np.where(np.isfinite(tau), tau, dt * ds / np.maximum(s[i + 1] - s[i], 1e-12))
    out: FloatArray = t[i] + np.clip(tau, 0.0, dt)
    return out


def _newey_west_cov(x: FloatArray, resid: FloatArray, lags: int) -> FloatArray:
    """HAC covariance of OLS coefficients (Bartlett kernel)."""
    n = len(resid)
    xtx_inv = np.linalg.inv(x.T @ x)
    u = x * resid[:, None]
    s = u.T @ u
    for k in range(1, min(lags, n - 1) + 1):
        w = 1.0 - k / (lags + 1.0)
        g = u[k:].T @ u[:-k]
        s += w * (g + g.T)
    cov: FloatArray = xtx_inv @ s @ xtx_inv
    return cov


@dataclass(frozen=True)
class AlignedLap:
    tel: LapTelemetry
    method: AlignMethod
    ref_length: float
    t_rel: FloatArray  # car sample times rel. to s = 0 crossing
    s: FloatArray  # car sample distances [m]
    w: FloatArray  # ds/dt at car samples [m/s along the reference line]
    t_zero_from_t0: float  # crossing time minus date_start [s]
    params: dict[str, Any] = field(default_factory=dict)
    # Extra (t, s, w) samples used only by time_at, e.g. sector-anchor knots,
    # so that every car interval lies within one linear warp piece.
    knots: tuple[FloatArray, FloatArray, FloatArray] | None = None

    def _time_samples(self) -> tuple[FloatArray, FloatArray, FloatArray]:
        if self.knots is None:
            return self.t_rel, self.s, self.w
        t = np.r_[self.t_rel, self.knots[0]]
        o = np.argsort(t, kind="stable")
        return t[o], np.r_[self.s, self.knots[1]][o], np.r_[self.w, self.knots[2]][o]

    @property
    def lap_time_telemetry(self) -> float:
        t = self.time_at(np.array([0.0, self.ref_length]))
        return float(t[1] - t[0])

    def time_at(self, s_query: FloatArray) -> FloatArray:
        t, s, w = self._time_samples()
        if self.method == "xy":
            return np.interp(s_query, s, t)
        return invert_trapezoid(t, s, w, s_query)

    def channel(self, name: str, s_grid: FloatArray, how: Resample | None = None) -> FloatArray:
        """Resample a car channel onto ``s_grid``.

        Discrete channels (gear, brake) always use previous-value. NaN raw
        values (sentinels) stay NaN for every grid point they influence.
        """
        car = self.tel.car
        vals = car[name].to_numpy(dtype=np.float64)
        if name in DISCRETE:
            how = "previous"
        how = how or "linear"
        s = self.s
        if how == "previous":
            j = np.clip(np.searchsorted(s, s_grid, side="right") - 1, 0, len(s) - 1)
            return vals[j]
        ok = np.isfinite(vals)
        if how == "linear":
            out = np.interp(s_grid, s[ok], vals[ok])
        else:
            out = PchipInterpolator(s[ok], vals[ok], extrapolate=False)(s_grid)
        # poison grid points whose bracketing raw samples include a NaN
        j = np.clip(np.searchsorted(s, s_grid, side="right") - 1, 0, len(s) - 2)
        bad = ~ok[j] | ~ok[j + 1]
        out = np.where(bad, np.nan, out)
        result: FloatArray = out
        return result

    def sample_spacing_at(self, s_grid: FloatArray) -> FloatArray:
        """Distance [m] between the raw samples bracketing each grid point."""
        j = np.clip(np.searchsorted(self.s, s_grid, side="right") - 1, 0, len(self.s) - 2)
        out: FloatArray = self.s[j + 1] - self.s[j]
        return out


def _unwrap_to_guess(s_proj: FloatArray, guess: FloatArray, length: float) -> FloatArray:
    d = (s_proj - guess + length / 2) % length - length / 2
    out: FloatArray = guess + d
    return out


def align_lap(
    tel: LapTelemetry,
    line: ReferenceLine,
    method: AlignMethod = "hybrid",
    *,
    hac_lags: int = 10,
    outlier_sigma: float = 4.0,
    constrain_lap_time: bool = True,
) -> AlignedLap:
    car = tel.car
    t = car["t"].to_numpy(dtype=np.float64)
    v = car["speed"].to_numpy(dtype=np.float64)
    s_int = integrate_speed(t, v)
    v_ms = v / 3.6
    L = line.length
    T = tel.lap.lap_duration
    params: dict[str, Any] = {
        "lap_length_speed_integrated_m": float(np.interp(T, t, s_int) - np.interp(0.0, t, s_int))
    }

    if method == "speed":
        s0 = float(np.interp(0.0, t, s_int))
        scale = L / params["lap_length_speed_integrated_m"]
        s = (s_int - s0) * scale
        params |= {"scale": scale, "time_origin": "date_start"}
        return AlignedLap(tel, method, L, t, s, v_ms * scale, 0.0, params)

    pos = tel.pos
    tp = pos["t"].to_numpy(dtype=np.float64)
    inside = (tp > t[0]) & (tp < t[-1])
    tp = tp[inside]
    xy = pos[["x", "y"]].to_numpy(dtype=np.float64)[inside]
    s_int_p = np.interp(tp, t, s_int)
    guess = (s_int_p - np.interp(0.0, t, s_int)) * (L / params["lap_length_speed_integrated_m"])
    s_proj, lateral = project(xy, line, s_guess=guess)
    s_proj = _unwrap_to_guess(s_proj, guess, L)
    params |= {"n_pos": len(tp), "lateral_median_m": float(np.median(lateral))}

    if method == "xy":
        s_mono = np.maximum.accumulate(s_proj)
        s_car = np.interp(t, tp, s_mono)
        t_zero = float(np.interp(0.0, s_mono, tp))
        w = np.gradient(s_car, t)
        params |= {"n_nonmonotone_pos": int(np.sum(np.diff(s_proj) < 0))}
        return AlignedLap(tel, method, L, t - t_zero, s_car, w, t_zero, params)

    # hybrid: robust OLS s_proj = a + b*s_int, then HAC covariance
    x = np.c_[np.ones_like(s_int_p), s_int_p]
    keep = np.ones(len(tp), dtype=bool)
    for _ in range(3):
        coef, *_ = np.linalg.lstsq(x[keep], s_proj[keep], rcond=None)
        r = s_proj - x @ coef
        sd = float(np.std(r[keep]))
        keep = np.abs(r) <= outlier_sigma * sd
    resid = (s_proj - x @ coef)[keep]
    cov = _newey_west_cov(x[keep], resid, hac_lags)
    theta = np.array([float(coef[0]), float(coef[1])])

    def crossings(th: FloatArray) -> tuple[float, float, FloatArray, FloatArray]:
        s_ = th[0] + th[1] * s_int
        w_ = th[1] * v_ms
        tz, te = invert_trapezoid(t, s_, w_, np.array([0.0, L]))
        # ∂t/∂a = −1/w, ∂t/∂b = −s_int/w at a fixed s
        gz = -np.array([1.0, np.interp(tz, t, s_int)]) / np.interp(tz, t, w_)
        ge = -np.array([1.0, np.interp(te, t, s_int)]) / np.interp(te, t, w_)
        return float(tz), float(te), gz, ge

    tz, te, gz, ge = crossings(theta)
    jac = ge - gz
    sigma_lap = float(np.sqrt(jac @ cov @ jac))
    params |= {
        "a_fit_m": float(theta[0]),
        "b_fit": float(theta[1]),
        "resid_rms_m": float(np.sqrt(np.mean(resid**2))),
        "n_outliers": int((~keep).sum()),
        "cov_ab_fit": cov.tolist(),
        "sigma_t_zero_s": float(np.sqrt(gz @ cov @ gz)),
        "sigma_lap_time_s": sigma_lap,
        "lap_time_unconstrained_s": te - tz,
        "lap_time_z": (te - tz - T) / sigma_lap,
    }
    if constrain_lap_time:
        # Linearised equality-constrained GLS: enforce t(L) − t(0) = official T,
        # moving (a, b) as little as their covariance allows.
        for _ in range(4):
            tz, te, gz, ge = crossings(theta)
            jac = ge - gz
            resid_c = te - tz - T
            k = cov @ jac / (jac @ cov @ jac)
            theta = theta - k * resid_c
        cov = cov - np.outer(k, jac @ cov)
        tz, te, gz, ge = crossings(theta)
        params["constraint_residual_s"] = te - tz - T
    a, b = float(theta[0]), float(theta[1])
    s = a + b * s_int
    w = b * v_ms
    params |= {
        "a_m": a,
        "b": b,
        "cov_ab": cov.tolist(),
        "lap_time_constrained": constrain_lap_time,
        "time_origin": "crossing of s=0 from affine fit",
    }
    return AlignedLap(tel, method, L, t - tz, s, w, tz, params)


def distance_grid(length: float, step: float = 1.0) -> FloatArray:
    n = int(np.floor(length / step))
    g = np.arange(n + 1, dtype=np.float64) * step
    if n * step < length:
        g = np.r_[g, length]
    return g


def anchor_to_sectors(
    lap: AlignedLap,
    boundaries_s: tuple[float, ...],
    official_cumulative_s: tuple[float, ...],
    sigma_s_m: float,
) -> AlignedLap:
    """Warp distance piecewise-linearly so the lap crosses each sector line at
    its official cumulative time.

    ``boundaries_s``: sector-line positions on the reference line, estimated
    from *other* laps (so shared by every compared lap). ``official_cumulative_s``:
    official S1, S1+S2, ... Lap ends stay fixed, so the lap must already be
    constrained to its official lap time. Each correction relative to
    ``sigma_s_m`` is reported as ``sector_warp_z``; |z| > 3 means the lap's
    telemetry does not fit the noise model.

    Knot samples are inserted at the crossings so each car interval lies inside
    one linear piece and the trapezoid inverse stays valid. The speed at a knot
    takes the slope of the piece that starts there; the resulting error is of
    order (slope - 1) x interval time, far below 1 ms for the ~3 m corrections
    observed (checked in tests).
    """
    if lap.method == "xy":
        raise ValueError("sector anchoring is defined for speed-shaped methods only")
    if lap.method == "hybrid" and not lap.params.get("lap_time_constrained", False):
        raise ValueError("anchor_to_sectors needs a lap-time-constrained alignment")
    L = lap.ref_length
    cum = np.asarray(official_cumulative_s, dtype=np.float64)
    t, s, w = lap._time_samples()
    cur = np.interp(cum, t, s)  # current distance at the official crossing times
    knots_old = np.r_[0.0, cur, L]
    knots_new = np.r_[0.0, np.asarray(boundaries_s, dtype=np.float64), L]
    if np.any(np.diff(knots_old) <= 0) or np.any(np.diff(knots_new) <= 0):
        raise ValueError("sector anchoring produced non-monotone knots")
    slope = np.diff(knots_new) / np.diff(knots_old)

    def warp(sv: FloatArray, wv: FloatArray) -> tuple[FloatArray, FloatArray]:
        piece = np.clip(np.searchsorted(knots_old, sv, side="right") - 1, 0, len(slope) - 1)
        return knots_new[piece] + (sv - knots_old[piece]) * slope[piece], wv * slope[piece]

    s_new, w_new = warp(lap.s, lap.w)
    ks, kw = warp(cur, np.interp(cum, t, w))
    if lap.knots is not None:
        ps, pw = warp(lap.knots[1], lap.knots[2])
        knots = (np.r_[lap.knots[0], cum], np.r_[ps, ks], np.r_[pw, kw])
    else:
        knots = (cum, ks, kw)
    shifts = np.asarray(boundaries_s) - cur
    params = dict(lap.params) | {
        "sector_anchored": True,
        "sector_shift_m": shifts.tolist(),
        "sector_warp_z": (shifts / sigma_s_m).tolist(),
        "sector_scale": slope.tolist(),
    }
    return AlignedLap(
        lap.tel, lap.method, L, lap.t_rel, s_new, w_new, lap.t_zero_from_t0, params, knots
    )
