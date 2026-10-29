"""Property-based tests of the delta machinery on synthetic laps."""

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apex.core.delta import cumulative_delta
from apex.core.track import CornerConfig, detect_corners
from tests.conftest import synthetic_lap

LENGTH = 2500.0
GRID = np.linspace(0.0, LENGTH, 1001)

profile = st.tuples(
    st.floats(150, 260),  # base speed km/h
    st.floats(0, 80),  # amplitude
    st.floats(150, 600),  # wavelength-ish [m]
    st.floats(0, 6.28),  # phase
)
SETTINGS = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def _lap(p: tuple[float, float, float, float], seed: int = 0):  # type: ignore[no-untyped-def]
    base, amp, wl, ph = p
    rng = np.random.default_rng(seed)
    jitter = rng.choice([0.0, 0.04, -0.04], size=2000) * 0.5
    return synthetic_lap(lambda s: base + amp * np.sin(s / wl + ph), LENGTH, jitter=jitter)


@SETTINGS
@given(profile)
def test_delta_of_lap_with_itself_is_zero(p) -> None:  # type: ignore[no-untyped-def]
    a = _lap(p)
    np.testing.assert_array_equal(cumulative_delta(a, a, GRID), 0.0)


@SETTINGS
@given(profile, profile)
def test_delta_is_antisymmetric(p, q) -> None:  # type: ignore[no-untyped-def]
    a, b = _lap(p), _lap(q, seed=1)
    np.testing.assert_allclose(
        cumulative_delta(a, b, GRID), -cumulative_delta(b, a, GRID), atol=1e-12
    )


@SETTINGS
@given(profile, profile)
def test_delta_at_lap_end_equals_lap_time_difference(p, q) -> None:  # type: ignore[no-untyped-def]
    a, b = _lap(p), _lap(q, seed=2)
    d = cumulative_delta(a, b, np.array([LENGTH]))[0]
    official = a.tel.lap.lap_duration - b.tel.lap.lap_duration
    # speed method pins the end to the official lap time up to the inversion error
    assert abs(d - official) < 3e-3


@SETTINGS
@given(profile)
def test_resampling_then_integrating_preserves_lap_time(p) -> None:  # type: ignore[no-untyped-def]
    a = _lap(p)
    g = np.linspace(0.0, LENGTH, 2501)  # 1 m grid
    v = a.channel("speed", g) / 3.6 * (LENGTH / a.params["lap_length_speed_integrated_m"])
    t_int = float(np.trapezoid(1.0 / v, g))
    assert abs(t_int - a.lap_time_telemetry) / a.lap_time_telemetry < 2e-3


@SETTINGS
@given(st.integers(0, 10_000))
def test_corner_detection_is_stable_under_small_noise(seed: int) -> None:
    rng = np.random.default_rng(seed)
    s = np.arange(0.0, 4000.0, 1.0)
    v = (
        300
        - 210 * np.exp(-0.5 * ((s - 700) / 45) ** 2)
        - 150 * np.exp(-0.5 * ((s - 2100) / 50) ** 2)
        - 100 * np.exp(-0.5 * ((s - 3300) / 60) ** 2)
    )
    k = (
        1 / 25 * np.exp(-0.5 * ((s - 705) / 20) ** 2)
        - 1 / 40 * np.exp(-0.5 * ((s - 2095) / 25) ** 2)
        + 1 / 70 * np.exp(-0.5 * ((s - 3300) / 30) ** 2)
    )
    cfg = CornerConfig(include_flat=False)
    base = detect_corners(s, v, k, 4000.0, cfg)
    noisy = detect_corners(
        s, v + rng.normal(0, 1.5, len(s)), k + rng.normal(0, 2e-4, len(s)), 4000.0, cfg
    )
    assert len(noisy) == len(base) == 3
    for c0, c1 in zip(base, noisy, strict=True):
        assert abs(c0.s_apex - c1.s_apex) < 25
        assert c0.direction == c1.direction
