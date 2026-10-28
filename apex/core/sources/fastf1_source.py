"""FastF1 adapter.

Since FastF1 3.9, livetiming.formula1.com requires an F1TV subscription token
for all sessions (observed 2026-10-29: HTTP 401 without one, for 2024-2026).
FastF1 reads credentials from ``F1_USERNAME`` / ``F1_PASSWORD``. Apex never
handles those values; this adapter only reports whether loading succeeded.
"""

from __future__ import annotations

import os
from pathlib import Path

import fastf1
from fastf1.core import Session


class FastF1UnavailableError(RuntimeError):
    """FastF1 loaded no timing data (usually: no F1 account token)."""


def has_credentials() -> bool:
    return bool(os.environ.get("F1_USERNAME") and os.environ.get("F1_PASSWORD"))


def load_session(year: int, event: str | int, session: str, cache_dir: Path | str) -> Session:
    """Load a FastF1 session with laps, telemetry, weather and messages.

    Raises :class:`FastF1UnavailableError` instead of returning a half-loaded
    session, because FastF1 itself only logs a warning and leaves ``laps``
    unset when the timing feed is refused.
    """
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    fastf1.Cache.configure(cache_dir=str(cache_dir))
    sess = fastf1.get_session(year, event, session)
    # Without credentials FastF1 would prompt on stdin; never block on that.
    if not has_credentials():
        raise FastF1UnavailableError(
            "FastF1 needs F1_USERNAME/F1_PASSWORD (F1TV account) to reach livetiming; "
            "use the OpenF1 source instead."
        )
    sess.load(laps=True, telemetry=True, weather=True, messages=True)
    try:
        _ = sess.laps
    except fastf1.exceptions.DataNotLoadedError as exc:
        raise FastF1UnavailableError(f"FastF1 loaded no timing data for {sess}") from exc
    return sess
