"""Per-lap raw telemetry extraction with provenance.

Values are the raw OpenF1 values with exactly two documented transformations
(DATA_CONTRACT §9): the 104 sentinel becomes NaN in throttle/brake, and
(0, 0, 0) positions are dropped (counted in ``n_pos_dropouts``). Every row
keeps ``raw_index``, its index in the session-level frame.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from apex.core.quality import OPENF1_SENTINEL
from apex.core.session import SessionData


@dataclass(frozen=True)
class LapRef:
    driver_number: int
    lap_number: int
    t0: pd.Timestamp  # OpenF1 date_start (±~0.1 s estimate of the line crossing)
    lap_duration: float  # official, exact to 1 ms

    @property
    def key(self) -> str:
        return f"{self.driver_number}:{self.lap_number}"


@dataclass(frozen=True)
class LapTelemetry:
    lap: LapRef
    car: (
        pd.DataFrame
    )  # t [s rel. t0], speed [km/h], rpm, gear, throttle [%], brake {0,1}, raw_index
    pos: pd.DataFrame  # t [s rel. t0], x, y, z [m], raw_index
    pad_s: float
    n_pos_dropouts: int
    n_sentinel: int


def _rel_seconds(t: pd.Series, t0: pd.Timestamp) -> np.ndarray:
    return (t - t0).dt.total_seconds().to_numpy(dtype=np.float64)


def lap_ref(session: SessionData, driver_number: int, lap_number: int) -> LapRef:
    row = session.laps[
        (session.laps["driver_number"] == driver_number)
        & (session.laps["lap_number"] == lap_number)
    ]
    if len(row) != 1:
        raise LookupError(f"lap {driver_number}:{lap_number} not found")
    r = row.iloc[0]
    if pd.isna(r["lap_duration"]) or pd.isna(r["t0"]):
        raise ValueError(f"lap {driver_number}:{lap_number} has no time or start")
    return LapRef(driver_number, lap_number, r["t0"], float(r["lap_duration"]))


def extract_lap(session: SessionData, lap: LapRef, pad_s: float = 3.0) -> LapTelemetry:
    """Raw samples in [t0 - pad, t0 + lap_duration + pad].

    Padding is needed because no sample falls exactly on the lap boundaries;
    boundary values are later interpolated from samples on both sides.
    """
    lo = lap.t0 - pd.to_timedelta(pad_s, unit="s")
    hi = lap.t0 + pd.to_timedelta(lap.lap_duration + pad_s, unit="s")
    car = session.car
    c = car[(car["driver_number"] == lap.driver_number) & (car["t"] >= lo) & (car["t"] <= hi)]
    thr = c["throttle"].astype(float)
    brk = c["brake"].astype(float)
    sentinel = (c["throttle"] == OPENF1_SENTINEL) | (c["brake"] == OPENF1_SENTINEL)
    car_df = pd.DataFrame(
        {
            "t": _rel_seconds(c["t"], lap.t0),
            "speed": c["speed"].astype(float).to_numpy(),
            "rpm": c["rpm"].astype(float).to_numpy(),
            "gear": c["n_gear"].where(c["n_gear"].between(0, 8)).astype(float).to_numpy(),
            "throttle": thr.where(c["throttle"] != OPENF1_SENTINEL).to_numpy(),
            "brake": (brk.where(c["brake"] != OPENF1_SENTINEL) / 100.0).to_numpy(),
            "raw_index": c.index.to_numpy(),
        }
    )
    loc = session.location
    if loc.empty:  # car-only sessions: no position stream was loaded
        loc = pd.DataFrame(
            {
                "driver_number": pd.Series(dtype="int64"),
                "x": pd.Series(dtype="float64"),
                "y": pd.Series(dtype="float64"),
                "z": pd.Series(dtype="float64"),
                "t": pd.Series(dtype="datetime64[ns, UTC]"),
            }
        )
    p = loc[(loc["driver_number"] == lap.driver_number) & (loc["t"] >= lo) & (loc["t"] <= hi)]
    zero = (p["x"] == 0) & (p["y"] == 0) & (p["z"] == 0)
    pg = p[~zero]
    pos_df = pd.DataFrame(
        {
            "t": _rel_seconds(pg["t"], lap.t0),
            "x": pg["x"].to_numpy(dtype=float) / 10.0,
            "y": pg["y"].to_numpy(dtype=float) / 10.0,
            "z": pg["z"].to_numpy(dtype=float) / 10.0,
            "raw_index": pg.index.to_numpy(),
        }
    )
    if len(car_df) < 10 or car_df["t"].iloc[0] > 0 or car_df["t"].iloc[-1] < lap.lap_duration:
        raise ValueError(f"lap {lap.key}: car data does not bracket the lap")
    return LapTelemetry(lap, car_df, pos_df, pad_s, int(zero.sum()), int(sentinel.sum()))
