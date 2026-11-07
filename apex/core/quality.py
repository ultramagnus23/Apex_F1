"""Data-quality measurements on raw streams.

These functions measure; they never modify their input.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

# OpenF1 car_data uses 104 in both ``throttle`` and ``brake`` when the car is
# stationary / not transmitting (measured on 2026 USA Q, see DATA_CONTRACT.md).
OPENF1_SENTINEL: Final = 104

_QUANTUM_CANDIDATES_S: Final = (0.2, 0.1, 0.08, 0.05, 0.04, 0.02, 0.01, 0.005, 0.002, 0.001)


@dataclass(frozen=True)
class IntervalStats:
    """Distribution of time between consecutive samples, in seconds."""

    n_samples: int
    n_duplicates: int
    n_backwards: int
    n_gaps: int
    gap_threshold_s: float
    min_s: float
    p01_s: float
    p05_s: float
    median_s: float
    mean_s: float
    p95_s: float
    p99_s: float
    max_s: float
    std_s: float
    effective_hz: float
    quantum_s: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def detect_time_quantum(
    intervals_s: npt.ArrayLike,
    candidates: Sequence[float] = _QUANTUM_CANDIDATES_S,
    tol_s: float = 0.0015,
    min_fraction: float = 0.99,
) -> float | None:
    """Largest candidate step such that >= ``min_fraction`` of intervals are multiples of it.

    Used to discover the clock grid a stream is sampled on. Returns ``None``
    when no candidate fits.
    """
    dt = np.asarray(intervals_s, dtype=np.float64)
    dt = dt[np.isfinite(dt) & (dt > 0)]
    if dt.size == 0:
        return None
    for q in sorted(candidates, reverse=True):
        resid = np.abs(dt / q - np.round(dt / q)) * q
        if float(np.mean(resid <= tol_s)) >= min_fraction:
            return q
    return None


def interval_stats(times: pd.Series, gap_threshold_s: float = 1.0) -> IntervalStats:
    """Measure sampling intervals of a timestamp series in its recorded order.

    Duplicates (dt == 0) and backwards steps (dt < 0) are counted, not fixed.
    Distribution statistics are computed over strictly positive intervals at
    or below ``gap_threshold_s``; larger steps are reported as gaps.
    """
    if len(times) < 2:
        raise ValueError("need at least two timestamps")
    t = pd.to_datetime(times, utc=True)
    dt = t.diff().dt.total_seconds().to_numpy()[1:]
    pos = dt[(dt > 0) & (dt <= gap_threshold_s)]
    if pos.size == 0:
        raise ValueError("no positive intervals below gap threshold")
    median = float(np.median(pos))
    return IntervalStats(
        n_samples=len(t),
        n_duplicates=int(np.sum(dt == 0)),
        n_backwards=int(np.sum(dt < 0)),
        n_gaps=int(np.sum(dt > gap_threshold_s)),
        gap_threshold_s=gap_threshold_s,
        min_s=float(pos.min()),
        p01_s=float(np.percentile(pos, 1)),
        p05_s=float(np.percentile(pos, 5)),
        median_s=median,
        mean_s=float(pos.mean()),
        p95_s=float(np.percentile(pos, 95)),
        p99_s=float(np.percentile(pos, 99)),
        max_s=float(pos.max()),
        std_s=float(pos.std()),
        effective_hz=1.0 / median,
        quantum_s=detect_time_quantum(pos),
    )


def missingness(df: pd.DataFrame) -> dict[str, float]:
    """Fraction of null values per column."""
    return {str(c): float(df[c].isna().mean()) for c in df.columns}
