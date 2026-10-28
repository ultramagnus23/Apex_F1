"""Empirically inspect one OpenF1 session and write measurements to JSON.

Every number quoted in docs/DATA_CONTRACT.md comes from the JSON this script
writes, so the contract can be regenerated and audited.

Usage:
    uv run python scripts/inspect_openf1_session.py --session-key 11392 \
        --season 2026 --round 18 --out docs/data/inspection_11392.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apex.core.quality import OPENF1_SENTINEL, interval_stats, missingness
from apex.core.schemas import OPENF1_CAR_DATA, OPENF1_LAPS, OPENF1_LOCATION
from apex.core.sources.openf1 import OpenF1Client

DELETED_RE = re.compile(
    r"CAR (?P<car>\d+) \((?P<code>\w+)\) (?:TIME (?P<min>\d+):(?P<sec>\d+\.\d+) |LAP )DELETED"
    r".*?LAP (?P<lap>\d+)"
)


def utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="ISO8601", utc=True)


def col_summary(df: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in df.columns:
        s = df[c]
        info: dict[str, Any] = {"dtype": str(s.dtype), "null_fraction": float(s.isna().mean())}
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            info |= {"min": float(s.min()), "max": float(s.max()), "n_unique": int(s.nunique())}
        out[str(c)] = info
    return out


def phase_windows(rc: pd.DataFrame) -> list[dict[str, Any]]:
    st = rc[rc.category == "SessionStatus"].copy()
    st["t"] = utc(st.date)
    wins = []
    for ph, g in st.groupby("qualifying_phase"):
        start = g[g.message.str.contains("STARTED")].t.min()
        end = g[g.message.str.contains("FINISHED")].t.max()
        wins.append({"phase": int(ph), "start": start, "end": end})
    return sorted(wins, key=lambda w: w["phase"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-key", type=int, required=True)
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--cache", default="cache/openf1")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    c = OpenF1Client(args.cache)
    key = args.session_key
    q = {"session_key": key}
    report: dict[str, Any] = {"session_key": key, "source": "OpenF1 /v1", "season": args.season}

    session = c.frame("sessions", q).iloc[0].to_dict()
    report["session"] = {
        k: session[k]
        for k in ("session_name", "date_start", "date_end", "circuit_short_name", "location")
    }
    drivers = c.frame("drivers", q)
    report["n_drivers"] = len(drivers)
    rc = c.frame("race_control", q)
    wins = phase_windows(rc)
    report["phase_windows"] = [{**w, "start": str(w["start"]), "end": str(w["end"])} for w in wins]
    win_lo = wins[0]["start"] - pd.Timedelta(minutes=5)
    win_hi = wins[-1]["end"] + pd.Timedelta(minutes=10)

    # ---- car_data and location, all drivers -----------------------------------
    car_stats, loc_stats, car_sess, loc_sess = [], [], [], []
    shared_ts_frac, sentinel = [], []
    dates_ref: pd.Series | None = None
    same_clock = True
    car_all, loc_all = [], []
    zero_xyz = 0
    for d in drivers.driver_number:
        car = c.frame("car_data", q | {"driver_number": int(d)})
        loc = c.frame("location", q | {"driver_number": int(d)})
        OPENF1_CAR_DATA.validate(car)
        OPENF1_LOCATION.validate(loc)
        if dates_ref is None:
            dates_ref = car.date
        else:
            same_clock &= len(car) == len(dates_ref) and bool(
                (car.date.to_numpy() == dates_ref.to_numpy()).all()
            )
        car["t"], loc["t"] = utc(car.date), utc(loc.date)
        car_stats.append(interval_stats(car.t).as_dict())
        loc_stats.append(interval_stats(loc.t).as_dict())
        cw = car[(car.t >= win_lo) & (car.t <= win_hi)]
        lw = loc[(loc.t >= win_lo) & (loc.t <= win_hi)]
        cw_on = cw[(cw.throttle != OPENF1_SENTINEL) & (cw.speed > 0)]
        car_sess.append(interval_stats(cw_on.t).as_dict())
        loc_sess.append(interval_stats(lw.t).as_dict())
        shared_ts_frac.append(len(set(car.t) & set(loc.t)) / len(car))
        s_thr, s_brk = car.throttle == OPENF1_SENTINEL, car.brake == OPENF1_SENTINEL
        sentinel.append(
            {
                "driver": int(d),
                "frac_rows": float(s_thr.mean()),
                "throttle_and_brake_both": int((s_thr & s_brk).sum()),
                "throttle_only": int((s_thr & ~s_brk).sum()),
                "brake_only": int((~s_thr & s_brk).sum()),
                "frac_with_speed_zero": float((car.speed[s_thr] == 0).mean())
                if s_thr.any()
                else None,
                "max_speed_during": float(car.speed[s_thr].max()) if s_thr.any() else None,
            }
        )
        zero_xyz += int(((loc.x == 0) & (loc.y == 0) & (loc.z == 0)).sum())
        car_all.append(car)
        loc_all.append(loc)

    car_df = pd.concat(car_all, ignore_index=True)
    loc_df = pd.concat(loc_all, ignore_index=True)

    def agg(stats: list[dict[str, Any]]) -> dict[str, Any]:
        df = pd.DataFrame(stats)
        return {
            "per_driver_median_s": {"min": df.median_s.min(), "max": df.median_s.max()},
            "pooled_median_of_medians_s": float(df.median_s.median()),
            "p05_s_range": [df.p05_s.min(), df.p05_s.max()],
            "p95_s_range": [df.p95_s.min(), df.p95_s.max()],
            "p99_s_range": [df.p99_s.min(), df.p99_s.max()],
            "max_s_range": [df.max_s.min(), df.max_s.max()],
            "std_s_range": [df.std_s.min(), df.std_s.max()],
            "effective_hz_range": [df.effective_hz.min(), df.effective_hz.max()],
            "quantum_s_values": sorted({x for x in df.quantum_s if x is not None}),
            "n_duplicates_total": int(df.n_duplicates.sum()),
            "n_backwards_total": int(df.n_backwards.sum()),
            "n_gaps_over_1s_range": [int(df.n_gaps.min()), int(df.n_gaps.max())],
            "n_samples_range": [int(df.n_samples.min()), int(df.n_samples.max())],
        }

    dt_on = []
    for car in car_all:
        cw = car[(car.t >= win_lo) & (car.t <= win_hi) & (car.throttle != OPENF1_SENTINEL)]
        dt_on.append(cw.t.diff().dt.total_seconds().dropna())
    dt_hist = pd.concat(dt_on).round(3).value_counts(normalize=True).head(12)

    report["car_data"] = {
        "columns": col_summary(car_df.drop(columns=["t"])),
        "missingness": missingness(car_df),
        "intervals_full_stream": agg(car_stats),
        "intervals_on_track_in_session": agg(car_sess),
        "interval_histogram_on_track_top12": {str(k): float(v) for k, v in dt_hist.items()},
        "stream_span_utc": [str(car_df.t.min()), str(car_df.t.max())],
        "all_drivers_share_identical_timestamps": bool(same_clock),
        "brake_values": sorted(int(x) for x in car_df.brake.unique()),
        "n_gear_values": sorted(int(x) for x in car_df.n_gear.unique()),
        "throttle_values_above_100": sorted(
            int(x) for x in car_df.throttle[car_df.throttle > 100].unique()
        ),
        "drs_non_null_count": int(car_df.drs.notna().sum()),
        "sentinel_104": sentinel,
    }
    report["location"] = {
        "columns": col_summary(loc_df.drop(columns=["t"])),
        "intervals_full_stream": agg(loc_stats),
        "intervals_in_session": agg(loc_sess),
        "rows_all_zero_xyz": zero_xyz,
        "fraction_car_timestamps_also_in_location": {
            "min": min(shared_ts_frac),
            "max": max(shared_ts_frac),
        },
    }

    # ---- laps ----------------------------------------------------------------
    laps = c.frame("laps", q)
    OPENF1_LAPS.validate(laps)
    laps = laps.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)
    laps["t0"] = utc(laps.date_start)
    sectors = laps[["duration_sector_1", "duration_sector_2", "duration_sector_3"]]
    ssum = sectors.sum(axis=1, min_count=3)
    resid = (ssum - laps.lap_duration).dropna()
    ms = laps.lap_duration.dropna() * 1000
    nxt = laps.groupby("driver_number").t0.shift(-1)
    chain = (nxt - (laps.t0 + pd.to_timedelta(laps.lap_duration, unit="s"))).dt.total_seconds()
    nxt_out = laps.groupby("driver_number").is_pit_out_lap.shift(-1)
    chain_ok = chain[(nxt_out == False) & chain.notna()]  # noqa: E712
    seg_codes = pd.Series(
        [
            v
            for col in ("segments_sector_1", "segments_sector_2", "segments_sector_3")
            for row in laps[col].dropna()
            for v in row
        ]
    ).value_counts()
    po = laps[laps.is_pit_out_lap]
    report["laps"] = {
        "n_laps": len(laps),
        "columns": col_summary(laps.drop(columns=["t0"])),
        "pit_out_laps": {
            "n": len(po),
            "sector1_null_fraction": float(po.duration_sector_1.isna().mean()),
            "lap_duration_null_fraction": float(po.lap_duration.isna().mean()),
        },
        "non_pit_out_sector1_null": int(laps[~laps.is_pit_out_lap].duration_sector_1.isna().sum()),
        "lap_duration_is_whole_ms": bool(np.allclose(ms, ms.round(), atol=1e-6)),
        "sector_sum_minus_lap_s": {
            "n": len(resid),
            "n_abs_le_1ms": int((resid.abs() <= 0.0015).sum()),
            "outliers": [
                {
                    "driver": int(laps.driver_number[i]),
                    "lap": int(laps.lap_number[i]),
                    "lap_duration": float(laps.lap_duration[i]),
                    "sector_sum": float(ssum[i]),
                }
                for i in resid.index[resid.abs() > 0.0015]
            ],
        },
        "chain_next_start_minus_this_end_s": {
            "n": len(chain_ok),
            "median": float(chain_ok.median()),
            "p05": float(chain_ok.quantile(0.05)),
            "p95": float(chain_ok.quantile(0.95)),
            "min": float(chain_ok.min()),
            "max": float(chain_ok.max()),
        },
        "segment_code_counts": {str(k): int(v) for k, v in seg_codes.items()},
        "null_date_start": laps[laps.date_start.isna()][["driver_number", "lap_number"]].to_dict(
            "records"
        ),
    }

    # ---- race control: deleted laps & numbering offset -------------------------
    dels = []
    for msg in rc.message:
        m = DELETED_RE.search(msg)
        if not m:
            continue
        car_no, rc_lap = int(m["car"]), int(m["lap"])
        t = int(m["min"]) * 60 + float(m["sec"]) if m["min"] else None
        match = []
        if t is not None:
            hit = laps[(laps.driver_number == car_no) & ((laps.lap_duration - t).abs() < 5e-4)]
            match = hit.lap_number.astype(int).tolist()
        dels.append(
            {
                "car": car_no,
                "rc_lap": rc_lap,
                "time_s": t,
                "openf1_laps_with_time": match,
                "message": msg,
            }
        )
    offsets = sorted(
        {
            d["rc_lap"] - d["openf1_laps_with_time"][0]
            for d in dels
            if len(d["openf1_laps_with_time"]) == 1
        }
    )
    report["race_control"] = {
        "n_messages": len(rc),
        "category_counts": rc.category.value_counts().to_dict(),
        "flag_counts": rc.flag.value_counts().to_dict(),
        "date_has_subsecond_fraction": float(rc.date.str.contains(r"\.").mean()),
        "deleted_laps": dels,
        "rc_lap_minus_openf1_lap_offsets": offsets,
    }

    # ---- weather ----------------------------------------------------------------
    w = c.frame("weather", q)
    report["weather"] = {
        "n": len(w),
        "columns": col_summary(w),
        "intervals": interval_stats(utc(w.date), gap_threshold_s=600).as_dict(),
    }

    for ep in ("stints", "pit", "session_result"):
        df = c.frame(ep, q)
        report[ep] = {"n": len(df), "columns": col_summary(df)}
    report["stints"]["compound_values"] = (
        c.frame("stints", q).compound.value_counts(dropna=False).rename(index=str).to_dict()
    )

    # ---- cross-check: OpenF1 vs Jolpica official qualifying times --------------
    import fastf1
    from fastf1.ergast import Ergast

    fastf1.Cache.configure(cache_dir="cache/fastf1")
    jq = Ergast().get_qualifying_results(args.season, args.round).content[0]
    sr = c.frame("session_result", q)
    deleted = {
        (d["car"], d["openf1_laps_with_time"][0])
        for d in dels
        if len(d["openf1_laps_with_time"]) == 1
    }
    rows, n_cmp, n_eq_sr, n_eq_laps = [], 0, 0, 0
    for _, j in jq.iterrows():
        num = int(j["number"])
        srow = sr[sr.driver_number == num].iloc[0]
        for ph, w_ in enumerate(wins, start=1):
            jt = j[f"Q{ph}"]
            if pd.isna(jt):
                continue
            jt_s = round(jt.total_seconds(), 3)
            sr_t = srow.duration[ph - 1] if isinstance(srow.duration, list) else None
            dl = laps[
                (laps.driver_number == num)
                & (laps.t0 >= w_["start"])
                & (laps.t0 <= w_["end"])
                & laps.lap_duration.notna()
            ]
            dl = dl[[(num, int(n)) not in deleted for n in dl.lap_number]]
            best = round(float(dl.lap_duration.min()), 3) if len(dl) else None
            n_cmp += 1
            n_eq_sr += sr_t is not None and abs(sr_t - jt_s) < 5e-4
            n_eq_laps += best is not None and abs(best - jt_s) < 5e-4
            if sr_t is None or abs(sr_t - jt_s) >= 5e-4 or best is None or abs(best - jt_s) >= 5e-4:
                rows.append(
                    {
                        "driver": num,
                        "phase": ph,
                        "jolpica": jt_s,
                        "openf1_session_result": sr_t,
                        "openf1_best_valid_lap": best,
                    }
                )
    report["cross_check_jolpica"] = {
        "n_compared": n_cmp,
        "session_result_exact_match": int(n_eq_sr),
        "best_valid_lap_exact_match": int(n_eq_laps),
        "mismatches": rows,
    }

    # ---- units check: XY path length vs speed-integrated distance -------------
    ratios = []
    for d in drivers.driver_number:
        car = car_df[car_df.driver_number == d]
        loc = loc_df[loc_df.driver_number == d]
        dl = laps[
            (laps.driver_number == d)
            & ~laps.is_pit_out_lap
            & laps.lap_duration.notna()
            & (laps.lap_duration < 100)
        ]
        for _, lap in dl.iterrows():
            t1 = lap.t0 + pd.Timedelta(seconds=float(lap.lap_duration))
            cw = car[(car.t >= lap.t0) & (car.t <= t1)]
            lw = loc[(loc.t >= lap.t0) & (loc.t <= t1)]
            if len(cw) < 50 or len(lw) < 50:
                continue
            ts = (cw.t - lap.t0).dt.total_seconds().to_numpy()
            dist = float(np.trapezoid(cw.speed.to_numpy() / 3.6, ts))
            # Compare like with like: both integrals over the same covered time span.
            lts = (lw.t - lap.t0).dt.total_seconds().to_numpy()
            path = float(np.hypot(np.diff(lw.x), np.diff(lw.y)).sum())
            span_c, span_l = ts[-1] - ts[0], lts[-1] - lts[0]
            ratios.append(
                {
                    "driver": int(d),
                    "lap": int(lap.lap_number),
                    "lap_s": float(lap.lap_duration),
                    "speed_dist_m": dist,
                    "xy_path_units": path,
                    "ratio_units_per_m": path / dist * (span_c / span_l),
                    "car_coverage_s": span_c,
                    "loc_coverage_s": span_l,
                }
            )
    rdf = pd.DataFrame(ratios)
    report["units_check_xy"] = {
        "n_laps": len(rdf),
        "ratio_units_per_m": {
            k: float(v)
            for k, v in rdf.ratio_units_per_m.describe(percentiles=[0.05, 0.5, 0.95]).items()
        },
        "speed_integrated_lap_distance_m": {
            k: float(v) for k, v in rdf.speed_dist_m.describe(percentiles=[0.05, 0.5, 0.95]).items()
        },
        "uncovered_time_at_lap_ends_s": {
            "car_median": float((rdf.lap_s - rdf.car_coverage_s).median()),
            "loc_median": float((rdf.lap_s - rdf.loc_coverage_s).median()),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
