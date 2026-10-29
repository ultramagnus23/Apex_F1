import numpy as np
import pytest

from apex.core.track import (
    CornerConfig,
    build_reference_line,
    detect_corners,
    project,
)
from tests.conftest import circle_line


def test_curvature_of_circle_is_one_over_radius() -> None:
    line = circle_line(radius=400.0)
    k = line.curvature(window_m=60.0)
    np.testing.assert_allclose(k, 1 / 400.0, rtol=1e-3)


def test_projection_on_circle_returns_arc_length_and_offset() -> None:
    line = circle_line(radius=300.0)
    ang = np.array([0.5, 2.0, 4.0])
    pts = np.c_[305 * np.cos(ang), 305 * np.sin(ang)]
    s, lat = project(pts, line)
    np.testing.assert_allclose(s, 300 * ang, atol=0.05)
    np.testing.assert_allclose(lat, 5.0, atol=0.05)


def test_windowed_projection_avoids_nearby_track_section() -> None:
    # Hairpin: two parallel straights 10 m apart; a point on the lower one must
    # stay there when the guess says so, even if it is ambiguous globally.
    x = np.r_[
        np.arange(0, 200, 1.0), 200 + 5 * np.sin(np.linspace(0, np.pi, 16)), np.arange(200, 0, -1.0)
    ]
    y = np.r_[np.zeros(200), 5 - 5 * np.cos(np.linspace(0, np.pi, 16)), np.full(200, 10.0)]
    from apex.core.track import ReferenceLine, _arc_length

    cum = _arc_length(np.c_[x, y], closed=True)
    grid = np.arange(0, cum[-1], 1.0)
    line = ReferenceLine(
        grid, np.interp(grid, cum[:-1], x), np.interp(grid, cum[:-1], y), float(cum[-1]), 1.0
    )
    pt = np.array([[100.0, 4.9]])  # closer to the lower straight, barely
    s_low, _ = project(pt, line, s_guess=np.array([100.0]), window_m=50)
    assert s_low[0] == pytest.approx(100.0, abs=1.0)


def test_reference_line_from_noisy_laps_recovers_circle() -> None:
    rng = np.random.default_rng(1)
    r = 250.0
    laps = []
    for _ in range(5):
        ang = np.sort(rng.uniform(0, 2 * np.pi, 400))
        laps.append(np.c_[r * np.cos(ang), r * np.sin(ang)] + rng.normal(0, 0.5, (400, 2)))
    line = build_reference_line(laps, np.array([r, 0.0]), spacing=1.0, sigma=6.0)
    assert line.length == pytest.approx(2 * np.pi * r, rel=2e-3)
    # origin at (r, 0)
    assert line.x[0] == pytest.approx(r, abs=1.0)
    assert abs(line.y[0]) < 1.0


def test_detect_corners_finds_speed_minima_with_curvature() -> None:
    s = np.arange(0.0, 3000.0, 1.0)
    v = (
        300
        - 200 * np.exp(-0.5 * ((s - 800) / 40) ** 2)
        - 120 * np.exp(-0.5 * ((s - 2000) / 50) ** 2)
    )
    k = 1 / 30 * np.exp(-0.5 * ((s - 805) / 20) ** 2) - 1 / 60 * np.exp(
        -0.5 * ((s - 1995) / 25) ** 2
    )
    cs = detect_corners(s, v, k, 3000.0, CornerConfig(include_flat=False))
    assert [c.kind for c in cs] == ["braking", "braking"]
    assert cs[0].s_apex == pytest.approx(800, abs=2)
    assert [c.direction for c in cs] == ["L", "R"]
    assert cs[0].s_start == 0.0
    assert cs[-1].s_end == 3000.0
    assert cs[0].s_end == pytest.approx(cs[1].s_start)
