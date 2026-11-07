"""Lap validity rules and lap selection.

Every exclusion carries a machine-readable reason code; every inference that
is not directly recorded in the data (e.g. a deletion matched by lap number
only) is listed under ``assumptions``. Nothing is silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, cast

import numpy as np
import pandas as pd

from apex.core.quality import OPENF1_SENTINEL
from apex.core.session import SessionData, parse_utc


class Reason(StrEnum):
    NO_LAP_TIME = "NO_LAP_TIME"
    PIT_OUT = "PIT_OUT"
    PIT_IN = "PIT_IN"
    DELETED = "DELETED"
    SECTOR_MISMATCH = "SECTOR_MISMATCH"
    SECTOR_MISSING = "SECTOR_MISSING"
    FLAG = "FLAG"  # yellow / double yellow / SC / VSC / red active during the lap
    TELEMETRY_GAP = "TELEMETRY_GAP"
    SENTINEL_WHILE_MOVING = "SENTINEL_WHILE_MOVING"
    POSITION_DROPOUT = "POSITION_DROPOUT"


@dataclass(frozen=True)
class ValidityConfig:
    # 1 ms timing resolution, each of 3 sectors rounded => sum can differ by 1.5 ms.
    sector_sum_tol_s: float = 0.0015
    # Clean flying laps (2026 USA Q, n=91): max in-lap car gap median 0.92 s,
    # p99 1.92 s; position gaps up to 2.0 s. Gaps are normal for this feed, so
    # only reject beyond anything observed on a clean lap. Local sample spacing
    # is propagated into per-corner uncertainty instead (DATA_CONTRACT §1).
    max_car_gap_s: float = 2.5
    max_pos_gap_s: float = 2.5
    max_pos_dropouts: int = 0


_DELETED_RE: Final = re.compile(
    r"CAR (?P<car>\d+) \(\w+\) (?:TIME (?P<min>\d+):(?P<sec>\d+\.\d+) |LAP )DELETED"
    r".*?LAP (?P<lap>\d+)"
)
_BAD_FLAGS: Final = {"YELLOW", "DOUBLE YELLOW", "RED"}


def deleted_laps(session: SessionData) -> pd.DataFrame:
    """Parse deletions from race control and map them to OpenF1 lap numbers.

    Primary match: car + quoted lap time (exact to the ms). Fallback when no
    time is quoted: ``openf1_lap = rc_lap - 1`` (offset measured in
    DATA_CONTRACT §4), recorded as an assumption.
    """
    rows = []
    laps = session.laps
    for msg in session.race_control["message"].astype(str):
        m = _DELETED_RE.search(msg)
        if not m:
            continue
        car, rc_lap = int(m["car"]), int(m["lap"])
        lap_no: int | None = None
        assumption = ""
        if m["min"]:
            t = int(m["min"]) * 60 + float(m["sec"])
            hit = laps[(laps["driver_number"] == car) & ((laps["lap_duration"] - t).abs() < 5e-4)]
            if len(hit) == 1:
                lap_no = int(hit["lap_number"].iloc[0])
        if lap_no is None:
            lap_no = rc_lap - 1
            assumption = "deletion matched by lap number (rc_lap - 1), not by time"
        rows.append(
            {"driver_number": car, "lap_number": lap_no, "assumption": assumption, "message": msg}
        )
    return pd.DataFrame(
        rows, columns=["driver_number", "lap_number", "assumption", "message"]
    ).drop_duplicates(["driver_number", "lap_number"])


def flag_intervals(session: SessionData) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    """Intervals during which a yellow/red/SC/VSC condition was active somewhere.

    Sector flags end at the matching CLEAR for that marshal sector; track-wide
    conditions end at the next GREEN/CLEAR track message. An unterminated flag
    runs to the end of the data.
    """
    rc = session.race_control.copy()
    rc["t"] = parse_utc(rc["date"])
    rc = rc.sort_values("t")
    end_of_data = session.car["t"].max()
    open_: dict[str, pd.Timestamp] = {}
    out: list[tuple[pd.Timestamp, pd.Timestamp, str]] = []
    for _, r in rc.iterrows():
        flag = str(r.get("flag") or "")
        msg = str(r.get("message") or "")
        is_sc = r.get("category") == "SafetyCar" or "SAFETY CAR" in msg
        key = f"S{int(r['sector'])}" if pd.notna(r.get("sector")) else "TRACK"
        if flag in _BAD_FLAGS or (is_sc and "DEPLOYED" in msg):
            open_.setdefault(key, r["t"])
        elif flag in {"CLEAR", "GREEN"} or (is_sc and ("ENDING" in msg or "IN THIS LAP" in msg)):
            keys = list(open_) if key == "TRACK" else [key]
            for k in keys:
                if k in open_:
                    out.append((open_.pop(k), r["t"], k))
    out.extend((t0, end_of_data, k) for k, t0 in open_.items())
    return out


def classify_laps(session: SessionData, cfg: ValidityConfig | None = None) -> pd.DataFrame:
    """One row per lap: ``valid``, ``reasons`` (exclusions), ``warnings``, ``assumptions``."""
    cfg = cfg or ValidityConfig()
    laps = session.laps.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)
    phases = session.phase_windows()
    dels = deleted_laps(session)
    del_map = {
        (int(d), int(n)): str(a)
        for d, n, a in zip(
            dels["driver_number"], dels["lap_number"], dels["assumption"], strict=True
        )
    }
    flags = flag_intervals(session)
    next_out = laps.groupby("driver_number")["is_pit_out_lap"].shift(-1).to_list()

    car_by_drv = {d: g for d, g in session.car.groupby("driver_number")}
    loc_by_drv = {d: g for d, g in session.location.groupby("driver_number")}

    records: list[dict[str, object]] = []
    for i, (_, lap) in enumerate(laps.iterrows()):
        reasons: list[str] = []
        warnings: list[str] = []
        assumptions: list[str] = []
        drv, n = int(lap["driver_number"]), int(lap["lap_number"])
        dur = lap["lap_duration"]
        t0 = lap["t0"]
        if pd.isna(dur) or pd.isna(t0):
            reasons.append(Reason.NO_LAP_TIME)
        if bool(lap["is_pit_out_lap"]):
            reasons.append(Reason.PIT_OUT)
        if pd.isna(next_out[i]):
            reasons.append(Reason.PIT_IN)
            assumptions.append("last recorded lap of the driver treated as an in-lap")
        elif bool(next_out[i]):
            reasons.append(Reason.PIT_IN)
        if (drv, n) in del_map:
            reasons.append(Reason.DELETED)
            if del_map[(drv, n)]:
                assumptions.append(del_map[(drv, n)])
        secs = lap[["duration_sector_1", "duration_sector_2", "duration_sector_3"]]
        if secs.isna().any():
            reasons.append(Reason.SECTOR_MISSING)
        elif pd.notna(dur) and abs(float(secs.sum()) - float(dur)) > cfg.sector_sum_tol_s:
            reasons.append(Reason.SECTOR_MISMATCH)

        phase = None
        if pd.notna(t0) and pd.notna(dur):
            t1 = t0 + pd.to_timedelta(float(dur), unit="s")
            phase = next((w.phase for w in phases if w.start <= t0 <= w.end), None)
            if any(a < t1 and b > t0 for a, b, _ in flags):
                reasons.append(Reason.FLAG)
            car = car_by_drv.get(drv)
            if car is not None:
                cw = car[(car["t"] >= t0) & (car["t"] <= t1)]
                gaps = np.diff(cw["t"].to_numpy()).astype("timedelta64[us]").astype(float) / 1e6
                if (
                    len(cw) < 2
                    or gaps.max(initial=np.inf if len(cw) < 2 else 0) > cfg.max_car_gap_s
                ):
                    reasons.append(Reason.TELEMETRY_GAP)
                moving_sentinel = (
                    (cw["throttle"] == OPENF1_SENTINEL) | (cw["brake"] == OPENF1_SENTINEL)
                ) & (cw["speed"] > 0)
                if moving_sentinel.any():
                    # Timing is unaffected; pedal channels are missing there.
                    warnings.append(Reason.SENTINEL_WHILE_MOVING)
            loc = loc_by_drv.get(drv)
            if loc is not None:
                lw = loc[(loc["t"] >= t0) & (loc["t"] <= t1)]
                zero = (lw["x"] == 0) & (lw["y"] == 0) & (lw["z"] == 0)
                good = lw[~zero]
                gaps = np.diff(good["t"].to_numpy()).astype("timedelta64[us]").astype(float) / 1e6
                if int(zero.sum()) > cfg.max_pos_dropouts or (
                    len(good) < 2 or gaps.max(initial=0) > cfg.max_pos_gap_s
                ):
                    reasons.append(Reason.POSITION_DROPOUT)

        records.append(
            {
                "driver_number": drv,
                "lap_number": n,
                "phase": phase,
                "lap_duration": dur,
                "valid": not reasons,
                "reasons": tuple(str(r) for r in reasons),
                "warnings": tuple(str(w) for w in warnings),
                "assumptions": tuple(assumptions),
            }
        )
    return pd.DataFrame.from_records(records)


def fastest_valid(
    classified: pd.DataFrame, driver_number: int, phase: int | None = None
) -> pd.Series:
    c = classified[(classified["driver_number"] == driver_number) & classified["valid"]]
    if phase is not None:
        c = c[c["phase"] == phase]
    if c.empty:
        raise LookupError(f"no valid lap for driver {driver_number} (phase={phase})")
    return cast(pd.Series, c.loc[c["lap_duration"].idxmin()])


def best_per_driver(classified: pd.DataFrame, phase: int | None = None) -> pd.DataFrame:
    c = classified[classified["valid"]]
    if phase is not None:
        c = c[c["phase"] == phase]
    idx = c.groupby("driver_number")["lap_duration"].idxmin()
    return c.loc[idx].sort_values("lap_duration").reset_index(drop=True)
