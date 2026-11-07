import numpy as np
import pytest

from apex.analysis.corner import corner_metrics
from apex.core.delta import add_segment_sigma, minisector_boundaries, segment_deltas
from apex.core.track import Corner
from tests.conftest import synthetic_lap


def test_segment_deltas_sum_to_total() -> None:
    a = synthetic_lap(lambda s: 210 + 60 * np.cos(s / 200), 4000.0)
    b = synthetic_lap(lambda s: 205 + 60 * np.cos(s / 200), 4000.0)
    seg = segment_deltas(a, b, minisector_boundaries(4000.0, 25))
    assert len(seg) == 25
    assert seg["delta"].sum() == pytest.approx(
        a.lap_time_telemetry - b.lap_time_telemetry, abs=1e-9
    )


def test_provisional_sigma_is_zero_at_pinned_points() -> None:
    a = synthetic_lap(lambda s: 200.0, 2000.0)
    seg = segment_deltas(a, a, [0.0, 1000.0, 2000.0])
    out = add_segment_sigma(seg, a, a, 3.0, pinned=[0.0, 2000.0])
    # each segment has exactly one free end: sigma = sqrt(2) * 3 m / v
    v = 200 / 3.6
    np.testing.assert_allclose(out["sigma"], np.sqrt(2) * 3.0 / v, rtol=1e-6)
    assert out["within_noise"].all()


def test_corner_events_are_bracketed_by_raw_samples() -> None:
    lap = synthetic_lap(lambda s: 300 - 220 * np.exp(-0.5 * ((s - 1500) / 60) ** 2), 3000.0)
    car = lap.tel.car
    # brake on for samples in [1300, 1500] m, throttle 0 there, pick up after 1530 m
    on = (lap.s > 1300) & (lap.s < 1500)
    car.loc[on, "brake"] = 1.0
    car.loc[(lap.s > 1290) & (lap.s < 1530), "throttle"] = 0.0
    c = Corner(1, "C1", 1500.0, 0.0, 3000.0, 80.0, 0.02, "L", "braking")
    m = corner_metrics(lap, c)
    first_on = lap.s[on][0]
    last_off = lap.s[np.where(on)[0][0] - 1]
    assert m["brake_on_s"] == pytest.approx((first_on + last_off) / 2)
    assert m["brake_on_resolution_m"] == pytest.approx((first_on - last_off) / 2)
    assert 1290 - 30 < m["lift_s"] < 1300
    assert m["pickup_s"] > 1500
    assert m["s_v_min"] == pytest.approx(1500, abs=40)
