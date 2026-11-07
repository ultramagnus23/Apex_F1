import pandas as pd

from apex.core.laps import Reason, classify_laps, deleted_laps, fastest_valid
from apex.core.session import SessionData


def _with_rc(session: SessionData, messages: list[str]) -> SessionData:
    rc = pd.DataFrame(
        {
            "date": "2026-10-24T22:00:00+00:00",
            "category": "Other",
            "flag": None,
            "scope": None,
            "sector": None,
            "qualifying_phase": None,
            "message": messages,
            "meeting_key": 1,
            "session_key": 1,
            "driver_number": None,
            "lap_number": None,
        }
    )
    return SessionData(
        session.session_key,
        session.meta,
        session.drivers,
        session.laps,
        rc,
        session.car,
        session.location,
    )


def test_deleted_laps_match_by_quoted_time_not_lap_number(austin: SessionData) -> None:
    d = deleted_laps(austin)
    nor = d[d["driver_number"] == 1]
    # race control says LAP 15; the 1:34.379 lap is OpenF1 lap 14 (DATA_CONTRACT §4)
    assert nor["lap_number"].tolist() == [14]
    assert (nor["assumption"] == "").all()


def test_deletion_without_time_falls_back_with_recorded_assumption(austin: SessionData) -> None:
    s = _with_rc(austin, ["CAR 5 (BOR) LAP DELETED - TRACK LIMITS AT TURN 11 LAP 9 16:29:31"])
    d = deleted_laps(s)
    assert d["lap_number"].tolist() == [8]
    assert "rc_lap - 1" in d["assumption"].iloc[0]


def test_classification_of_case_study_and_known_laps(austin: SessionData) -> None:
    c = classify_laps(austin).set_index(["driver_number", "lap_number"])
    assert c.loc[(12, 14), "valid"]  # ANT pole lap
    # (the fixture holds telemetry for flying laps only, so other reasons may co-occur)
    assert Reason.DELETED in c.loc[(1, 14), "reasons"]
    # HAD's Q3 lap has sentinel rows while moving: a warning, not an exclusion
    assert c.loc[(6, 8), "valid"]
    assert Reason.SENTINEL_WHILE_MOVING in c.loc[(6, 8), "warnings"]
    out_laps = c[[Reason.PIT_OUT in r for r in c["reasons"]]]
    assert not out_laps["valid"].any()


def test_fastest_valid_per_phase_matches_official_q3_order(austin: SessionData) -> None:
    c = classify_laps(austin)
    assert fastest_valid(c, 12, phase=3)["lap_duration"] == 94.035
    assert fastest_valid(c, 3, phase=3)["lap_duration"] == 94.214
