"""Pandera schemas for raw source frames, as observed (see docs/DATA_CONTRACT.md).

These describe what the sources *deliver*, including quirks such as the 104
sentinel. They are deliberately permissive on values and strict on structure,
so a schema failure means the upstream format changed.
"""

from __future__ import annotations

import pandera.pandas as pa

_DATE = pa.Column(str, pa.Check.str_matches(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"))

OPENF1_CAR_DATA = pa.DataFrameSchema(
    {
        "date": _DATE,
        "session_key": pa.Column(int),
        "meeting_key": pa.Column(int),
        "driver_number": pa.Column(int),
        "speed": pa.Column(int, pa.Check.in_range(0, 400)),
        "rpm": pa.Column(int, pa.Check.in_range(0, 16000)),
        "n_gear": pa.Column(int, pa.Check.in_range(0, 8)),
        "throttle": pa.Column(int, pa.Check.in_range(0, 104)),
        "brake": pa.Column(int, pa.Check.isin([0, 100, 104])),
        # Null for every sample in 2026 sessions (no DRS under 2026 rules).
        "drs": pa.Column(object, nullable=True),
    },
    strict=True,
)

OPENF1_LOCATION = pa.DataFrameSchema(
    {
        "date": _DATE,
        "session_key": pa.Column(int),
        "meeting_key": pa.Column(int),
        "driver_number": pa.Column(int),
        # Decimetres in an arbitrary circuit frame.
        "x": pa.Column(int),
        "y": pa.Column(int),
        "z": pa.Column(int),
    },
    strict=True,
)

OPENF1_LAPS = pa.DataFrameSchema(
    {
        "meeting_key": pa.Column(int),
        "session_key": pa.Column(int),
        "driver_number": pa.Column(int),
        "lap_number": pa.Column(int, pa.Check.ge(1)),
        "date_start": pa.Column(str, nullable=True),
        "duration_sector_1": pa.Column(float, nullable=True),
        "duration_sector_2": pa.Column(float, nullable=True),
        "duration_sector_3": pa.Column(float, nullable=True),
        "i1_speed": pa.Column(float, nullable=True, coerce=True),
        "i2_speed": pa.Column(float, nullable=True, coerce=True),
        "st_speed": pa.Column(float, nullable=True, coerce=True),
        "is_pit_out_lap": pa.Column(bool),
        "lap_duration": pa.Column(float, nullable=True),
        "segments_sector_1": pa.Column(object, nullable=True),
        "segments_sector_2": pa.Column(object, nullable=True),
        "segments_sector_3": pa.Column(object, nullable=True),
    },
    strict=True,
)
