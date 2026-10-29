import numpy as np
import pandas as pd
import pytest

from apex.core.align import (
    align_lap,
    anchor_to_sectors,
    integrate_speed,
    invert_trapezoid,
)
from tests.conftest import CASE_A, synthetic_lap


def test_integrate_speed_constant() -> None:
    t = np.array([0.0, 0.2, 0.5, 1.0])
    s = integrate_speed(t, np.full(4, 36.0))  # 10 m/s
    np.testing.assert_allclose(s, 10 * t)


def test_invert_trapezoid_is_exact_for_constant_acceleration() -> None:
    # v = 10 + 4 t  (m/s), s = 10 t + 2 t^2
    t = np.array([0.0, 0.3, 0.7, 1.2, 2.0])
    w = 10 + 4 * t
    s = 10 * t + 2 * t**2
    tq = np.linspace(0, 2, 41)
    sq = 10 * tq + 2 * tq**2
    np.testing.assert_allclose(invert_trapezoid(t, s, w, sq), tq, atol=1e-12)


def test_speed_method_reproduces_lap_time_by_construction() -> None:
    lap = synthetic_lap(lambda s: 200 + 80 * np.sin(s / 300), 3000.0)
    assert lap.lap_time_telemetry == pytest.approx(lap.tel.lap.lap_duration, abs=2e-3)


def test_discrete_channels_never_take_fractional_values() -> None:
    lap = synthetic_lap(lambda s: 120 + 150 * (s % 1000) / 1000, 3000.0)
    g = np.linspace(0, 3000, 3001)
    gear = lap.channel("gear", g)
    assert np.all(gear == np.round(gear))
    assert set(np.unique(lap.channel("brake", g))) <= {0.0, 1.0}


def test_sentinel_nan_poisons_only_neighbouring_grid_points() -> None:
    lap = synthetic_lap(lambda s: 200.0, 2000.0)
    car = lap.tel.car
    i = len(car) // 2
    car.loc[i, "throttle"] = np.nan
    g = np.linspace(0, 2000, 2001)
    thr = lap.channel("throttle", g)
    bad = np.isnan(thr)
    assert bad.any()
    # only grid points between the neighbours of the NaN sample are poisoned
    assert g[bad].min() >= lap.s[i - 1] - 1e-9
    assert g[bad].max() <= lap.s[i + 1] + 1e-9


def test_hybrid_lap_time_constraint_and_sector_anchor(austin, case_study) -> None:  # type: ignore[no-untyped-def]
    a = case_study.a
    official = austin.laps.set_index(["driver_number", "lap_number"]).loc[CASE_A]
    # constrained lap time is exact
    assert a.lap_time_telemetry == pytest.approx(official["lap_duration"], abs=1e-9)
    # anchored sector crossings are exact
    b = case_study.boundaries
    t = a.time_at(np.array([b.s1, b.s2]))
    assert t[0] == pytest.approx(official["duration_sector_1"], abs=1e-6)
    assert t[1] == pytest.approx(
        official["duration_sector_1"] + official["duration_sector_2"], abs=1e-6
    )
    # per-sample arrays stay aligned with the raw car rows (provenance)
    assert len(a.s) == len(a.tel.car)


def test_anchor_rejects_unconstrained_hybrid(case_study) -> None:  # type: ignore[no-untyped-def]
    lap = align_lap(case_study.a.tel, case_study.track.line, "hybrid", constrain_lap_time=False)
    with pytest.raises(ValueError, match="constrained"):
        anchor_to_sectors(lap, (1000.0, 3000.0), (20.0, 50.0), 3.0)


def test_unwrap_handles_samples_before_the_line(case_study) -> None:  # type: ignore[no-untyped-def]
    a = case_study.a
    pre = a.t_rel < 0
    assert pre.any()
    assert np.all(a.s[pre] < 0)  # padding samples before the line have negative distance
    assert np.all(np.diff(a.s) > 0)


def test_extract_lap_padding_brackets_the_lap(case_study) -> None:  # type: ignore[no-untyped-def]
    car = case_study.a.tel.car
    assert car["t"].iloc[0] < 0 < car["t"].iloc[-1] - case_study.a.tel.lap.lap_duration
    assert isinstance(car["raw_index"].iloc[0], (int, np.integer))
    assert not pd.isna(car["speed"]).any()
