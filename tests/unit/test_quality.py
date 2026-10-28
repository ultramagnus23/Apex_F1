import numpy as np
import pandas as pd
import pytest

from apex.core.quality import detect_time_quantum, interval_stats


def _ts(offsets_s: list[float]) -> pd.Series:
    t0 = pd.Timestamp("2026-10-24T21:00:00Z")
    return pd.Series([t0 + pd.Timedelta(seconds=o) for o in offsets_s])


def test_interval_stats_counts_duplicates_backwards_and_gaps() -> None:
    # intervals: 0.2, 0.2, 0 (dup), -0.1 (backwards), 0.3, 5.0 (gap), 0.2
    offsets = [0.0, 0.2, 0.4, 0.4, 0.3, 0.6, 5.6, 5.8]
    s = interval_stats(_ts(offsets), gap_threshold_s=1.0)
    assert s.n_samples == 8
    assert s.n_duplicates == 1
    assert s.n_backwards == 1
    assert s.n_gaps == 1
    # statistics use only the positive, sub-threshold intervals: 0.2, 0.2, 0.3, 0.2
    assert s.median_s == pytest.approx(0.2)
    assert s.max_s == pytest.approx(0.3)
    assert s.effective_hz == pytest.approx(5.0)


def test_detect_time_quantum_recovers_40ms_grid_despite_jitter() -> None:
    rng = np.random.default_rng(0)
    dt = rng.integers(4, 13, size=5000) * 0.04  # 0.16 .. 0.48 s, like OpenF1 car_data
    dt[:40] += 0.001  # <1 % of intervals 1 ms off-grid, as observed
    assert detect_time_quantum(dt) == pytest.approx(0.04)
    # A 20 ms grid must not be mistaken for 40 ms.
    assert detect_time_quantum(rng.integers(6, 25, size=5000) * 0.02) == pytest.approx(0.02)
