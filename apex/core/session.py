"""Source-agnostic session container and the OpenF1 loader.

Raw source columns are never modified. Parsed helper columns are added with
fixed names (``t`` / ``t0``: tz-aware UTC timestamps) and are pure functions of
the raw ``date`` / ``date_start`` strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from apex.core.schemas import OPENF1_CAR_DATA, OPENF1_LAPS, OPENF1_LOCATION
from apex.core.sources.openf1 import OpenF1Client


def parse_utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="ISO8601", utc=True)


@dataclass(frozen=True)
class PhaseWindow:
    phase: int
    start: pd.Timestamp
    end: pd.Timestamp


@dataclass(frozen=True)
class SessionData:
    """Everything Apex needs from one session, as raw-as-delivered frames."""

    session_key: int
    meta: dict[str, Any]
    drivers: pd.DataFrame
    laps: pd.DataFrame
    race_control: pd.DataFrame
    car: pd.DataFrame
    location: pd.DataFrame
    pit: pd.DataFrame = field(default_factory=pd.DataFrame)
    stints: pd.DataFrame = field(default_factory=pd.DataFrame)

    def driver_number(self, code: str) -> int:
        hit = self.drivers[self.drivers["name_acronym"] == code.upper()]
        if hit.empty:
            raise KeyError(f"no driver {code!r} in session {self.session_key}")
        return int(hit["driver_number"].iloc[0])

    def driver_code(self, number: int) -> str:
        hit = self.drivers[self.drivers["driver_number"] == number]
        return str(hit["name_acronym"].iloc[0]) if not hit.empty else str(number)

    def phase_windows(self) -> list[PhaseWindow]:
        """Qualifying phases from race-control SessionStatus messages."""
        rc = self.race_control
        st = rc[rc["category"] == "SessionStatus"].copy()
        if st.empty or "qualifying_phase" not in st or st["qualifying_phase"].isna().all():
            return []
        st["t"] = parse_utc(st["date"])
        out = []
        for ph, g in st.groupby("qualifying_phase"):
            start = g[g["message"].str.contains("STARTED")]["t"].min()
            end = g[g["message"].str.contains("FINISHED")]["t"].max()
            out.append(PhaseWindow(int(float(str(ph))), start, end))
        return sorted(out, key=lambda w: w.phase)

    def subset(self, driver_numbers: list[int]) -> SessionData:
        keep = self.drivers["driver_number"].isin(driver_numbers)
        return SessionData(
            self.session_key,
            self.meta,
            self.drivers[keep].reset_index(drop=True),
            self.laps[self.laps["driver_number"].isin(driver_numbers)].reset_index(drop=True),
            self.race_control,
            self.car[self.car["driver_number"].isin(driver_numbers)].reset_index(drop=True),
            self.location[self.location["driver_number"].isin(driver_numbers)].reset_index(
                drop=True
            ),
            self.pit,
            self.stints,
        )


def _with_time(df: pd.DataFrame, raw: str, parsed: str) -> pd.DataFrame:
    df = df.copy()
    df[parsed] = parse_utc(df[raw])
    return df


def load_openf1(
    session_key: int,
    cache_dir: Path | str,
    *,
    offline: bool = False,
    include_location: bool = True,
) -> SessionData:
    c = OpenF1Client(cache_dir, offline=offline)
    q = {"session_key": session_key}
    meta = {str(k): v for k, v in c.frame("sessions", q).iloc[0].to_dict().items()}
    drivers = c.frame("drivers", q)
    raw_laps = c.frame("laps", q)
    if raw_laps.empty:
        raise ValueError(f"OpenF1 has no laps for session {session_key}")
    laps = OPENF1_LAPS.validate(raw_laps)
    cars, locs = [], []
    for d in drivers["driver_number"]:
        cars.append(OPENF1_CAR_DATA.validate(c.frame("car_data", q | {"driver_number": int(d)})))
        if include_location:
            locs.append(
                OPENF1_LOCATION.validate(c.frame("location", q | {"driver_number": int(d)}))
            )
    return SessionData(
        session_key=session_key,
        meta=meta,
        drivers=drivers,
        laps=_with_time(laps, "date_start", "t0"),
        race_control=c.frame("race_control", q),
        car=_with_time(pd.concat(cars, ignore_index=True), "date", "t"),
        location=(
            _with_time(pd.concat(locs, ignore_index=True), "date", "t")
            if include_location
            else _empty_timed(["driver_number"], "date", "t")
        ),
        pit=c.frame("pit", q),
        stints=c.frame("stints", q),
    )


def _empty_timed(columns: list[str], raw: str, parsed: str) -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="float64") for c in columns})
    df[raw] = pd.Series(dtype="object")
    df[parsed] = pd.Series(dtype="datetime64[ns, UTC]")
    return df


def load_openf1_laps_only(
    session_key: int, cache_dir: Path | str, *, offline: bool = False
) -> SessionData:
    """Like :func:`load_openf1` but without car and position streams.

    Enough for lap-time analysis (race pace). ``car`` and ``location`` are empty.
    """
    c = OpenF1Client(cache_dir, offline=offline)
    q = {"session_key": session_key}
    meta = {str(k): v for k, v in c.frame("sessions", q).iloc[0].to_dict().items()}
    raw_laps = c.frame("laps", q)
    if raw_laps.empty:
        raise ValueError(f"OpenF1 has no laps for session {session_key}")
    return SessionData(
        session_key=session_key,
        meta=meta,
        drivers=c.frame("drivers", q),
        laps=_with_time(OPENF1_LAPS.validate(raw_laps), "date_start", "t0"),
        race_control=c.frame("race_control", q),
        car=_empty_timed(["driver_number"], "date", "t"),
        location=_empty_timed(["driver_number"], "date", "t"),
        pit=c.frame("pit", q),
        stints=c.frame("stints", q),
    )


def find_session_key(
    year: int, event: str, session_name: str, cache_dir: Path | str, *, offline: bool = False
) -> int:
    """Resolve e.g. (2026, "Austin", "Qualifying") to an OpenF1 session key.

    ``event`` matches circuit short name, location, country or meeting name
    (case-insensitive substring). Ambiguity is an error, not a guess.
    """
    c = OpenF1Client(cache_dir, offline=offline)
    aliases = {"Q": "Qualifying", "R": "Race", "SQ": "Sprint Qualifying", "S": "Sprint"}
    name = aliases.get(session_name.upper(), session_name)
    s = c.frame("sessions", {"year": year, "session_name": name})
    if s.empty:
        raise KeyError(f"no {name} sessions in {year}")
    needle = event.lower()
    cols = [k for k in ("circuit_short_name", "location", "country_name") if k in s]
    mask = pd.Series(False, index=s.index)
    for k in cols:
        mask |= s[k].astype(str).str.lower().str.contains(needle, regex=False)
    hits = s[mask]
    if len(hits) != 1:
        found = hits[cols].to_dict("records")
        raise KeyError(f"{event!r} matched {len(hits)} {name} sessions in {year}: {found}")
    return int(hits["session_key"].iloc[0])


_FRAMES = ("drivers", "laps", "race_control", "car", "location", "pit", "stints")
_PARSED = {"laps": ("date_start", "t0"), "car": ("date", "t"), "location": ("date", "t")}


def save_parquet(session: SessionData, directory: Path | str) -> Path:
    """Write the raw frames (without parsed helper columns) as Parquet + meta JSON.

    Parsed columns are dropped and re-derived on load, so the files contain
    only source values.
    """
    import json

    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    for name in _FRAMES:
        df = getattr(session, name)
        if name in _PARSED:
            df = df.drop(columns=[_PARSED[name][1]])
        df.reset_index(drop=True).to_parquet(d / f"{name}.parquet", compression="zstd", index=False)
    meta = {"session_key": session.session_key, "meta": session.meta}
    (d / "meta.json").write_text(
        json.dumps(meta, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    return d


def load_parquet(directory: Path | str) -> SessionData:
    import json

    d = Path(directory)
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    frames: dict[str, pd.DataFrame] = {}
    for name in _FRAMES:
        df = pd.read_parquet(d / f"{name}.parquet")
        if name in _PARSED:
            df = _with_time(df, *_PARSED[name])
        frames[name] = df
    return SessionData(session_key=int(meta["session_key"]), meta=meta["meta"], **frames)


def window_subset(
    session: SessionData, windows: list[tuple[int, pd.Timestamp, pd.Timestamp]]
) -> SessionData:
    """Keep car/location rows inside (driver, start, end) windows; other frames whole."""

    def keep(df: pd.DataFrame) -> pd.DataFrame:
        m = pd.Series(False, index=df.index)
        for drv, a, b in windows:
            m |= (df["driver_number"] == drv) & (df["t"] >= a) & (df["t"] <= b)
        return df[m].reset_index(drop=True)

    return SessionData(
        session.session_key,
        session.meta,
        session.drivers,
        session.laps,
        session.race_control,
        keep(session.car),
        keep(session.location),
        session.pit,
        session.stints,
    )
