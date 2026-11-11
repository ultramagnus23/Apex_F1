from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apex.analysis.ers import (
    CONFOUNDERS,
    ClipConfig,
    ClipEvent,
    LapClip,
    detect_clipping,
    lap_clipping,
    repeatability_lift,
)
from apex.core.laps import classify_laps
from apex.core.session import SessionData


def trace(
    rng: np.random.Generator,
    *,
    decay_ms2: float = 0.0,
    decay_s: float = 2.0,
    v_top: float = 300.0,
    brake_after: bool = True,
    shift_dip: bool = False,
    lift_during_decay: bool = False,
    brake_during_decay: bool = False,
) -> pd.DataFrame:
    """Irregularly sampled (~0.24 s), 1 km/h quantised full-throttle straight.

    Phases: accelerate towards ``v_top``, decay at ``decay_ms2`` for ``decay_s``, hold
    for one second, then (optionally) brake hard.
    """
    t = np.cumsum(rng.uniform(0.2, 0.28, 90))
    v = np.empty_like(t)
    thr = np.full_like(t, 100.0)
    brk = np.zeros_like(t)
    gear = np.full_like(t, 8.0)
    t_acc, t_dec, t_hold = 4.0, decay_s, 1.0
    v_dec_start = None
    v_hold = None
    for i, ti in enumerate(t):
        if ti < t_acc:
            v[i] = v_top - (v_top - 200.0) * np.exp(-ti / 1.4)
        elif ti < t_acc + t_dec:
            if v_dec_start is None:
                v_dec_start = v[i - 1]
            v[i] = v_dec_start - decay_ms2 * 3.6 * (ti - t_acc)
            if lift_during_decay:
                thr[i] = 60.0
            if brake_during_decay:
                brk[i] = 1.0
        elif ti < t_acc + t_dec + t_hold:
            if v_hold is None:
                v_hold = v[i - 1]
            v[i] = v_hold
        else:
            if brake_after:
                thr[i] = 0.0
                brk[i] = 1.0
                v[i] = v[i - 1] - 8.0 * 3.6 * (ti - t[i - 1])
            else:
                v[i] = v[i - 1]
    if shift_dip:
        k = 8
        gear[k:] = 7.0
        v[k] -= 9.0  # a transient dip at the shift
        gear[:k] = 6.0
    v = np.round(v + rng.normal(0.0, 0.15, len(v)))  # sensor jitter, then 1 km/h quantisation
    return pd.DataFrame({"t": t, "speed": v, "throttle": thr, "brake": brk, "gear": gear})


def test_detects_a_planted_decay() -> None:
    rng = np.random.default_rng(0)
    found = 0
    for _ in range(30):
        ev = detect_clipping(trace(rng, decay_ms2=1.5))
        found += len(ev) == 1
        if len(ev) == 1:
            e = ev[0]
            assert 1.0 <= e.duration_s <= 2.6
            assert e.decel_ms2 == pytest.approx(1.5, abs=0.5)
            assert e.decel_se_ms2 < 0.3
            assert e.v_start_kmh > 280
            assert not e.ends_run
    assert found >= 27  # power: nearly always found


def test_no_events_on_clean_acceleration_with_quantisation_noise() -> None:
    """False-positive rate: a trace that never decelerates should almost never trigger."""
    rng = np.random.default_rng(1)
    n_bad = sum(bool(detect_clipping(trace(rng, decay_ms2=0.0))) for _ in range(300))
    assert n_bad <= 3  # at most 1%


def test_braking_is_not_clipping() -> None:
    rng = np.random.default_rng(2)
    assert all(
        not detect_clipping(trace(rng, decay_ms2=3.0, brake_during_decay=True)) for _ in range(20)
    )


def test_throttle_lift_is_not_clipping() -> None:
    rng = np.random.default_rng(3)
    assert all(
        not detect_clipping(trace(rng, decay_ms2=3.0, lift_during_decay=True)) for _ in range(20)
    )


def test_sentinel_throttle_is_not_full_throttle() -> None:
    rng = np.random.default_rng(4)
    df = trace(rng, decay_ms2=2.0)
    df["throttle"] = 104.0  # the feed's missing-value sentinel
    assert detect_clipping(df) == []


def test_gear_shift_transient_is_ignored() -> None:
    rng = np.random.default_rng(5)
    hits = sum(bool(detect_clipping(trace(rng, decay_ms2=0.0, shift_dip=True))) for _ in range(100))
    assert hits <= 3


def test_event_ending_with_full_throttle_is_flagged_and_dropped_by_default() -> None:
    rng = np.random.default_rng(6)
    # decay runs straight into the braking zone: the event ends where full throttle ends
    df = trace(rng, decay_ms2=1.5, decay_s=2.5)
    df = df[df["t"] < 4.0 + 2.5 + 0.01].reset_index(drop=True)
    df.loc[df.index[-3:], ["throttle", "brake"]] = [0.0, 1.0]
    assert detect_clipping(df) == []
    kept = detect_clipping(df, ClipConfig(drop_run_end_events=False))
    assert kept
    assert all(e.ends_run for e in kept)


def test_confounders_are_listed() -> None:
    joined = " ".join(CONFOUNDERS).lower()
    for word in ("gradient", "wind", "slipstream", "ers"):
        assert word in joined


def _lap(driver: int, n: int, positions: list[float]) -> LapClip:
    ev = tuple(
        ClipEvent(0, 1, 1.0, 300, 290, 10, 1.5, 0.1, 4, False, p, p + 0.01) for p in positions
    )
    return LapClip(driver, n, ev, 30.0, 20.0, float(len(ev)))


def test_repeatability_lift_high_when_events_repeat_and_near_one_when_random() -> None:
    same = [_lap(1, k, [0.1, 0.4, 0.7]) for k in range(4)]
    assert repeatability_lift(same)["observed_repeat_rate"] == 1.0
    assert repeatability_lift(same)["lift"] > 5
    rng = np.random.default_rng(7)
    rand = [_lap(1, k, list(rng.uniform(0, 1, 3))) for k in range(40)]
    assert 0.4 < repeatability_lift(rand)["lift"] < 2.0


def test_repeatability_needs_laps_of_the_same_driver() -> None:
    lone = [_lap(d, 1, [0.2]) for d in range(5)]
    assert repeatability_lift(lone)["pairs"] == 0


def test_real_lap_has_events_in_range(austin: SessionData) -> None:
    classified = classify_laps(austin)
    row = classified[(classified["driver_number"] == 12) & (classified["lap_number"] == 14)].iloc[0]
    lc = lap_clipping(austin, int(row["driver_number"]), int(row["lap_number"]))
    assert lc.full_throttle_s > 20
    assert lc.events
    for e in lc.events:
        assert 0.0 <= e.frac_start < e.frac_end <= 1.0
        assert e.decel_ms2 > 0.3
        assert e.speed_lost_kmh >= 3
    assert 0 < lc.clip_share < 0.5


def test_works_without_a_position_stream(austin: SessionData) -> None:
    """Car-only sessions (no location frames) must analyse, not silently skip every lap."""
    car_only = SessionData(
        austin.session_key,
        austin.meta,
        austin.drivers,
        austin.laps,
        austin.race_control,
        austin.car,
        austin.location.iloc[0:0].drop(columns=["x", "y", "z"]),
        austin.pit,
        austin.stints,
    )
    full = lap_clipping(austin, 12, 14)
    lean = lap_clipping(car_only, 12, 14)
    assert len(lean.events) == len(full.events) > 0
