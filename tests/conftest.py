from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from apex.core.align import AlignedLap, align_lap
from apex.core.session import SessionData, load_parquet
from apex.core.telemetry import LapRef, LapTelemetry
from apex.core.track import ReferenceLine

FIXTURE = Path(__file__).parent / "fixtures" / "openf1_11392"

# Case study 01: 2026 United States GP Q3, ANT lap 14 (pole) vs VER lap 8 (P2).
CASE_A = (12, 14)
CASE_B = (3, 8)


@pytest.fixture(scope="session")
def austin() -> SessionData:
    return load_parquet(FIXTURE)


@pytest.fixture(scope="session")
def case_study(austin: SessionData):  # type: ignore[no-untyped-def]
    from apex.analysis.compare import compare

    return compare(austin, CASE_A, CASE_B)


def circle_line(radius: float = 500.0, spacing: float = 1.0) -> ReferenceLine:
    length = 2 * np.pi * radius
    n = round(length / spacing)
    s = np.arange(n) * (length / n)
    return ReferenceLine(
        s, radius * np.cos(s / radius), radius * np.sin(s / radius), length, length / n
    )


def synthetic_lap(
    speed_kmh_fn,  # type: ignore[no-untyped-def]
    length: float,
    *,
    dt: float = 0.24,
    jitter: np.ndarray | None = None,
    driver: int = 1,
    lap_number: int = 1,
) -> AlignedLap:
    """A lap whose speed is a function of distance, sampled in time like the feed.

    The official lap time is computed by fine integration of the same profile,
    so the lap is self-consistent; aligned with the ``speed`` method.
    """
    # integrate ds/dt = v(s) finely
    h = 0.001
    # start 2 s before the line
    s_cur, t_cur = -2.0 * speed_kmh_fn(0.0) / 3.6, -2.0
    ts, ss = [t_cur], [s_cur]
    while s_cur < length + 3.0 * speed_kmh_fn(length) / 3.6:
        v = speed_kmh_fn(s_cur) / 3.6
        s_cur += v * h
        t_cur += h
        ts.append(t_cur)
        ss.append(s_cur)
    ts_a, ss_a = np.array(ts), np.array(ss)
    lap_time = float(np.interp(length, ss_a, ts_a) - np.interp(0.0, ss_a, ts_a))
    t0 = float(np.interp(0.0, ss_a, ts_a))
    n = int((ts_a[-1] - ts_a[0]) / dt)
    tq = ts_a[0] + np.arange(n) * dt
    if jitter is not None:
        tq = tq + jitter[: len(tq)]
        tq = np.sort(tq)
    sq = np.interp(tq, ts_a, ss_a)
    v = np.array([speed_kmh_fn(x) for x in sq])
    car = pd.DataFrame(
        {
            "t": tq - t0,
            "speed": v,
            "rpm": v * 30,
            "gear": np.clip(v // 45, 1, 8),
            "throttle": np.full_like(v, 100.0),
            "brake": np.zeros_like(v),
            "raw_index": np.arange(len(v)),
        }
    )
    ref = LapRef(driver, lap_number, pd.Timestamp("2026-01-01", tz="UTC"), lap_time)
    tel = LapTelemetry(ref, car, pd.DataFrame(columns=["t", "x", "y", "z", "raw_index"]), 2.0, 0, 0)
    line = ReferenceLine(np.array([0.0, length / 2]), np.zeros(2), np.zeros(2), length, 0.0)
    return align_lap(tel, line, "speed")
