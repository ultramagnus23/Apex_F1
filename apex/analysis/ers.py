"""Full-throttle deceleration ("clipping") detection from public car data.

Signature: the car is decelerating while the throttle is fully open and the brake is
off. With a lot of power available that should not happen at the speeds where it is
detected, so it points to deployment tapering off (battery or power limit). The
2026 rules raise the electrical share of power, which makes this easier to see.

**What this measures and what it does not.** The detector reports an OBSERVED
speed-trace feature: where, how fast, for how long and how hard the car decelerates
at full throttle, with uncertainty. It does **not** observe ERS state. Reading the
feature as electrical deployment ending is a HYPOTHESIS; the confounders are listed
in :data:`CONFOUNDERS` and must travel with any claim.

Uncertainty: speed is an integer in km/h (quantisation σ = 1/√12 km/h) and samples
are irregular (about 0.24 s). Local slopes come from least squares inside a window
and carry the standard error implied by the quantisation. An event needs the
slope to be below a threshold at the 95% level, so quantisation noise alone does
not create events (see the false-positive test).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from apex.core.session import SessionData
from apex.core.telemetry import extract_lap, lap_ref

QUANT_SIGMA_MS = (1.0 / np.sqrt(12.0)) / 3.6  # speed quantisation, m/s

CONFOUNDERS = (
    "road gradient (uphill reduces acceleration)",
    "headwind or tailwind change along the straight",
    "slipstream from a car ahead",
    "engine or fuel mode set by the team",
    "active-aero or DRS state change (drag step)",
    "gear-shift transients (excluded within one sample of a shift)",
    "ERS deployment ending: the hypothesis, not observed",
)


@dataclass(frozen=True)
class ClipConfig:
    throttle_min: float = 99.0  # % ; 104 is the feed's missing-value sentinel
    speed_min_kmh: float = 150.0
    window_s: float = 0.5  # half-width of the local slope window
    decel_threshold_ms2: float = 0.4  # slope must be below -threshold ...
    z: float = 1.645  # ... at this many standard errors (one-sided 95%)
    min_duration_s: float = 0.7
    min_speed_loss_kmh: float = 3.0
    max_gap_samples: int = 1  # bridge single samples that miss the criterion
    max_dt_s: float = 0.6  # larger sample gaps break a run
    # An event that ends where full throttle ends is probably a braking onset seen through
    # slightly misaligned throttle/brake/speed channels. Flagged, and dropped by default.
    drop_run_end_events: bool = True


@dataclass(frozen=True)
class ClipEvent:
    t_start: float
    t_end: float
    duration_s: float
    v_start_kmh: float
    v_end_kmh: float
    speed_lost_kmh: float
    decel_ms2: float  # positive number = deceleration
    decel_se_ms2: float
    n_samples: int
    ends_run: bool = False  # ends exactly where full throttle ends (see ClipConfig)
    frac_start: float = float("nan")  # position along the lap, 0..1 (from integrated speed)
    frac_end: float = float("nan")


@dataclass(frozen=True)
class LapClip:
    driver_number: int
    lap_number: int
    events: tuple[ClipEvent, ...]
    full_throttle_s: float  # time at full throttle above ``speed_min``
    exposure_fast_s: float  # full-throttle time above 250 km/h
    clip_s: float

    @property
    def clip_share(self) -> float:
        return self.clip_s / self.full_throttle_s if self.full_throttle_s > 0 else float("nan")


def _local_slope(t: np.ndarray, v: np.ndarray, idx: np.ndarray, w: float) -> tuple[float, float]:
    """OLS slope (m/s²) of v over the samples ``idx`` and its standard error."""
    tt = t[idx]
    if len(idx) < 3:
        return float("nan"), float("nan")
    tc = tt - tt.mean()
    sxx = float((tc**2).sum())
    if sxx <= 0:
        return float("nan"), float("nan")
    slope = float((tc * (v[idx] - v[idx].mean())).sum() / sxx)
    return slope, QUANT_SIGMA_MS / np.sqrt(sxx)


def detect_clipping(car: pd.DataFrame, cfg: ClipConfig | None = None) -> list[ClipEvent]:
    """Find full-throttle deceleration events in one lap's car data.

    ``car`` needs ``t`` (seconds, increasing), ``speed`` (km/h), ``throttle`` (%),
    ``brake`` (0 or 1) and ``gear``.
    """
    cfg = cfg or ClipConfig()
    c = car.sort_values("t").reset_index(drop=True)
    t = c["t"].to_numpy(float)
    kmh = c["speed"].to_numpy(float)
    v = kmh / 3.6
    gear = c["gear"].to_numpy(float)
    full = (
        (c["throttle"].to_numpy(float) >= cfg.throttle_min)
        & (c["throttle"].to_numpy(float) < 104)
        & (c["brake"].to_numpy(float) == 0)
    )
    ok = full & (kmh >= cfg.speed_min_kmh)
    shift = np.zeros(len(c), dtype=bool)
    ch = np.where(np.diff(gear) != 0)[0]
    for i in ch:  # a shift disturbs the sample before and after the change
        shift[max(0, i - 1) : min(len(c), i + 3)] = True
    ok &= ~shift
    # break runs at gaps in sampling
    brk = np.r_[True, np.diff(t) > cfg.max_dt_s]

    sig = np.zeros(len(c), dtype=bool)
    slope = np.full(len(c), np.nan)
    run_id = np.cumsum(brk & True)
    for i in np.where(ok)[0]:
        near = np.where((np.abs(t - t[i]) <= cfg.window_s) & ok & (run_id == run_id[i]))[0]
        s, se = _local_slope(t, v, near, cfg.window_s)
        slope[i] = s
        if np.isfinite(s) and s + cfg.z * se < -cfg.decel_threshold_ms2:
            sig[i] = True

    events: list[ClipEvent] = []
    i, n = 0, len(c)
    while i < n:
        if not sig[i]:
            i += 1
            continue
        j = i
        gap = 0
        k = i + 1
        while k < n and (sig[k] or (gap < cfg.max_gap_samples and ok[k])):
            gap = 0 if sig[k] else gap + 1
            if sig[k]:
                j = k
            k += 1
        block = np.arange(i, j + 1)
        block = block[ok[block]]
        if len(block) >= 3:
            dur = float(t[j] - t[i])
            lost = float(kmh[i] - kmh[j])
            s, se = _local_slope(t, v, block, cfg.window_s)
            ends_run = j + 1 >= n or not full[j + 1]
            keep = not (cfg.drop_run_end_events and ends_run)
            if keep and dur >= cfg.min_duration_s and lost >= cfg.min_speed_loss_kmh:
                events.append(
                    ClipEvent(
                        t_start=float(t[i]),
                        t_end=float(t[j]),
                        duration_s=dur,
                        v_start_kmh=float(kmh[i]),
                        v_end_kmh=float(kmh[j]),
                        speed_lost_kmh=lost,
                        decel_ms2=-s,
                        decel_se_ms2=se,
                        n_samples=len(block),
                        ends_run=ends_run,
                    )
                )
        i = j + 1
    return events


def _exposure(car: pd.DataFrame, cfg: ClipConfig) -> tuple[float, float]:
    c = car.sort_values("t")
    t = c["t"].to_numpy(float)
    kmh = c["speed"].to_numpy(float)
    full = (
        (c["throttle"].to_numpy(float) >= cfg.throttle_min)
        & (c["throttle"].to_numpy(float) < 104)
        & (c["brake"].to_numpy(float) == 0)
    )
    dt = np.diff(t, append=t[-1])
    dt = np.where(dt > cfg.max_dt_s, 0.0, dt)
    return (
        float(dt[full & (kmh >= cfg.speed_min_kmh)].sum()),
        float(dt[full & (kmh >= 250.0)].sum()),
    )


def lap_clipping(
    session: SessionData, driver_number: int, lap_number: int, cfg: ClipConfig | None = None
) -> LapClip:
    """Clipping events for one lap, with positions along the lap as a 0..1 fraction."""
    cfg = cfg or ClipConfig()
    lap = lap_ref(session, driver_number, lap_number)
    tel = extract_lap(session, lap)
    car = tel.car
    car = car[(car["t"] >= 0.0) & (car["t"] <= lap.lap_duration)].reset_index(drop=True)
    if len(car) < 20:
        return LapClip(driver_number, lap_number, (), 0.0, 0.0, 0.0)
    t = car["t"].to_numpy(float)
    v = car["speed"].to_numpy(float) / 3.6
    s = np.r_[0.0, np.cumsum(0.5 * (v[1:] + v[:-1]) * np.diff(t))]
    total = s[-1] if s[-1] > 0 else 1.0
    events = []
    for e in detect_clipping(car, cfg):
        a = float(np.interp(e.t_start, t, s) / total)
        b = float(np.interp(e.t_end, t, s) / total)
        events.append(ClipEvent(**{**e.__dict__, "frac_start": a, "frac_end": b}))
    full, fast = _exposure(car, cfg)
    return LapClip(
        driver_number,
        lap_number,
        tuple(events),
        full,
        fast,
        float(sum(e.duration_s for e in events)),
    )


def repeatability_lift(
    laps: list[LapClip], n_bins: int = 100, tol_bins: int = 2
) -> dict[str, float]:
    """How much more often an event repeats at the same place than chance predicts.

    For every ordered pair of laps (A, B) of the same driver: take each event start
    in A and ask whether B has an event within ``tol_bins`` of that position. The
    chance rate is the share of the lap that lies within that tolerance of *any* B
    event, taken from B's own events placed at random: ``2 * tol_bins + 1`` bins per
    event over ``n_bins``. ``lift`` is observed repeat rate over chance rate.
    """
    obs = exp = pairs = 0.0
    by_drv: dict[int, list[LapClip]] = {}
    for lc in laps:
        by_drv.setdefault(lc.driver_number, []).append(lc)
    for group in by_drv.values():
        for a in group:
            for b in group:
                if a is b or not a.events:
                    continue
                pb = np.array([e.frac_start for e in b.events]) * n_bins
                cover = min(1.0, len(pb) * (2 * tol_bins + 1) / n_bins)
                for e in a.events:
                    pos = e.frac_start * n_bins
                    hit = bool(len(pb) and np.min(np.abs(pb - pos)) <= tol_bins)
                    obs += hit
                    exp += cover
                    pairs += 1
    return {
        "pairs": pairs,
        "observed_repeat_rate": obs / pairs if pairs else float("nan"),
        "chance_repeat_rate": exp / pairs if pairs else float("nan"),
        "lift": (obs / exp) if exp > 0 else float("nan"),
    }
