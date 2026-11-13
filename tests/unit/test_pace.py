from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apex.analysis.pace import (
    PaceConfig,
    cross_validate,
    fit_pace,
    race_lap_table,
)
from apex.core.session import SessionData, parse_utc

# ---------------------------------------------------------------- synthetic races

N_DRIVERS = 8
N_LAPS = 60
GAMMA = -0.05  # s/lap (fuel burn + track evolution)
DEG = {"MEDIUM": 0.08, "HARD": 0.04}
OFFSET = {"MEDIUM": 0.0, "HARD": 0.3}  # MEDIUM is the majority compound (reference)
STINT_SD = 0.15
NOISE = 0.3


def synthetic_table(seed: int) -> tuple[pd.DataFrame, np.ndarray]:
    """A clean race with known parameters. Returns (table, true driver pace)."""
    rng = np.random.default_rng(seed)
    ref_lap = round(N_LAPS / 2)
    true_pace = 90.0 + np.sort(rng.uniform(0.0, 1.2, N_DRIVERS))
    rows = []
    for d in range(N_DRIVERS):
        pit = int(rng.integers(22, 38))
        for stint, (lo, hi, comp) in enumerate(
            [(2, pit, "MEDIUM"), (pit + 1, N_LAPS, "HARD" if d % 4 == 0 else "MEDIUM")], start=1
        ):
            eff = rng.normal(0.0, STINT_SD)
            for lap in range(lo, hi + 1):
                age = lap - lo
                y = (
                    true_pace[d]
                    + eff
                    + OFFSET[comp]
                    + GAMMA * (lap - ref_lap)
                    + DEG[comp] * age
                    + rng.normal(0.0, NOISE)
                )
                rows.append((d + 1, lap, stint, comp, float(age), y))
    t = pd.DataFrame(
        rows,
        columns=[
            "driver_number",
            "lap_number",
            "stint_number",
            "compound",
            "tyre_age",
            "lap_duration",
        ],
    )
    t["clean"] = True
    t["reason"] = ""
    return t, true_pace


def test_recovers_trend_degradation_and_driver_pace() -> None:
    table, truth = synthetic_table(1)
    res = fit_pace(table, n_draws=2000, seed=1)
    p = res.params.set_index("name")
    trend = p.loc["lap-number trend"]
    assert trend["lo"] < GAMMA < trend["hi"]
    deg = p.loc["degradation MEDIUM"]
    assert deg["lo"] < DEG["MEDIUM"] < deg["hi"]
    d = res.drivers.set_index("driver_number")
    err = np.abs(d.loc[np.arange(1, N_DRIVERS + 1), "mean_s"].to_numpy() - truth)
    assert err.max() < 0.35


def test_driver_pace_intervals_are_calibrated() -> None:
    """Over many simulated races the 90% interval holds the true pace about 90% of the time."""
    hits = total = 0
    for seed in range(30):
        table, truth = synthetic_table(100 + seed)
        res = fit_pace(table, n_draws=600, seed=seed)
        d = res.drivers.set_index("driver_number").loc[np.arange(1, N_DRIVERS + 1)]
        hits += int(((d["lo_s"].to_numpy() <= truth) & (truth <= d["hi_s"].to_numpy())).sum())
        total += N_DRIVERS
    assert 0.80 <= hits / total <= 0.98


def test_probability_ranks_clear_gaps() -> None:
    table, _ = synthetic_table(3)
    # make driver 1 clearly the fastest and driver 2 clearly the slowest
    table.loc[table["driver_number"] == 1, "lap_duration"] -= 1.5
    table.loc[table["driver_number"] == 2, "lap_duration"] += 1.5
    res = fit_pace(table, {1: "AAA", 2: "BBB"}, n_draws=2000)
    assert res.prob_faster.loc["AAA", "BBB"] > 0.99
    assert res.drivers.iloc[0]["code"] == "AAA"
    assert res.drivers.iloc[-1]["code"] == "BBB"
    assert (np.diag(res.prob_faster.to_numpy()) == 0.5).all()


def test_pace_is_deterministic_for_a_seed() -> None:
    table, _ = synthetic_table(4)
    a = fit_pace(table, n_draws=500, seed=7).drivers["mean_s"].to_numpy()
    b = fit_pace(table, n_draws=500, seed=7).drivers["mean_s"].to_numpy()
    assert np.array_equal(a, b)


def test_cross_validation_coverage_near_nominal() -> None:
    table, _ = synthetic_table(5)
    for scheme in ("random", "stint"):
        cv = cross_validate(table, scheme=scheme, frac=0.25, n_draws=800)
        assert 0.80 <= cv.coverage <= 0.99, scheme
        assert cv.n_test > 20


def test_cross_validation_rejects_unknown_scheme() -> None:
    table, _ = synthetic_table(6)
    with pytest.raises(ValueError, match="unknown scheme"):
        cross_validate(table, scheme="nope")


def test_wet_race_is_flagged_not_modelled() -> None:
    table, _ = synthetic_table(7)
    table["compound"] = "INTERMEDIATE"
    res = fit_pace(table, n_draws=300)
    assert res.status == "NOT MODELLED"
    assert any("wet-weather" in r for r in res.status_reasons)


def test_dry_race_is_ok() -> None:
    table, _ = synthetic_table(8)
    assert fit_pace(table, n_draws=300).status == "OK"


def test_no_clean_laps_is_an_error() -> None:
    table, _ = synthetic_table(9)
    table["clean"] = False
    with pytest.raises(ValueError, match="no driver has enough clean laps"):
        fit_pace(table)


def test_trend_is_not_called_a_fuel_effect() -> None:
    table, _ = synthetic_table(10)
    res = fit_pace(table, n_draws=300)
    row = res.params[res.params["name"] == "lap-number trend"].iloc[0]
    assert "not separable" in row["note"]


# ------------------------------------------------------------------ lap filtering


def _session() -> SessionData:
    """Two drivers, 12 laps each. Driver 1 pits at the end of lap 6."""
    t_start = pd.Timestamp("2026-05-03T17:00:00Z")
    laps = []
    for drv in (1, 2):
        t = t_start
        for lap in range(1, 13):
            dur = 90.0 + 0.01 * lap + (0.0 if drv == 1 else 0.5)
            if drv == 1 and lap == 7:
                dur += 20.0  # out lap
            if drv == 1 and lap == 6:
                dur += 15.0  # in lap
            if drv == 2 and lap == 9:
                dur = 105.0  # an isolated slow lap (traffic or error)
            laps.append(
                {
                    "driver_number": drv,
                    "lap_number": lap,
                    "lap_duration": dur,
                    "is_pit_out_lap": drv == 1 and lap == 7,
                    "t0": t,
                }
            )
            t = t + pd.Timedelta(seconds=dur)
    laps_df = pd.DataFrame(laps)
    # A yellow flag overlapping driver 2's lap 3 only.
    lap3 = laps_df[(laps_df.driver_number == 2) & (laps_df.lap_number == 3)].iloc[0]
    flag_t = (lap3["t0"] + pd.Timedelta(seconds=10)).isoformat()
    clear_t = (lap3["t0"] + pd.Timedelta(seconds=40)).isoformat()
    rc = pd.DataFrame(
        [
            {"date": flag_t, "category": "Flag", "flag": "YELLOW", "sector": 2.0, "message": "Y"},
            {"date": clear_t, "category": "Flag", "flag": "CLEAR", "sector": 2.0, "message": "C"},
        ]
    )
    pit = pd.DataFrame({"driver_number": [1], "lap_number": [6]})
    stints = pd.DataFrame(
        {
            "driver_number": [1, 1, 2],
            "stint_number": [1, 2, 1],
            "lap_start": [1, 7, 1],
            "lap_end": [6, 12, 12],
            "compound": ["MEDIUM", "HARD", "MEDIUM"],
            "tyre_age_at_start": [0, 0, 0],
        }
    )
    empty = pd.DataFrame({"driver_number": pd.Series(dtype=int), "t": pd.to_datetime([], utc=True)})
    return SessionData(
        session_key=1,
        meta={},
        drivers=pd.DataFrame({"driver_number": [1, 2], "name_acronym": ["AAA", "BBB"]}),
        laps=laps_df,
        race_control=rc,
        car=empty,
        location=empty,
        pit=pit,
        stints=stints,
    )


def test_lap_table_excludes_with_reasons() -> None:
    t = race_lap_table(_session(), PaceConfig())
    r = t.set_index(["driver_number", "lap_number"])["reason"]
    assert r[(1, 1)] == "START"
    assert r[(1, 6)] == "PIT_IN"
    assert r[(1, 7)] == "PIT_OUT"
    assert r[(2, 3)] == "FLAG"
    assert r[(2, 9)] == "OUTLIER"
    assert r[(1, 3)] == "FLAG"  # the flag is track-wide: it hits every car on track
    assert r[(1, 9)] == ""
    assert r[(2, 5)] == ""


def test_lap_table_tyre_age_and_compound() -> None:
    t = race_lap_table(_session(), PaceConfig()).set_index(["driver_number", "lap_number"])
    assert t.loc[(1, 4), "tyre_age"] == 3
    assert t.loc[(1, 9), "tyre_age"] == 2  # new stint starts at lap 7
    assert t.loc[(1, 9), "compound"] == "HARD"
    assert t.loc[(2, 12), "compound"] == "MEDIUM"


def test_lap_table_missing_lap_time() -> None:
    s = _session()
    laps = s.laps.copy()
    laps.loc[(laps.driver_number == 2) & (laps.lap_number == 5), "lap_duration"] = np.nan
    s2 = SessionData(1, {}, s.drivers, laps, s.race_control, s.car, s.location, s.pit, s.stints)
    t = race_lap_table(s2).set_index(["driver_number", "lap_number"])
    assert t.loc[(2, 5), "reason"] == "NO_TIME"


def test_parse_utc_exported() -> None:
    assert parse_utc(pd.Series(["2026-01-01T00:00:00+00:00"])).iloc[0].year == 2026
