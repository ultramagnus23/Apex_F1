"""Full-throttle deceleration ("clipping") study over qualifying sessions.

For every qualifying session of a season: take each driver's best valid laps, detect
full-throttle deceleration events (``apex.analysis.ers``), and record where they happen,
how strong they are, and how well they repeat. With two seasons it also compares the
eras (2025 cars against 2026 cars) with a bootstrap over sessions.

Outputs under ``docs/ers_study/``: ``<year>/events.csv``, ``<year>/laps.csv``,
``<year>/sessions.csv`` and ``summary.json`` (all years run so far).

    uv run python scripts/fetch_season.py --year 2025 --session Qualifying --no-location
    uv run python scripts/ers_study.py --year 2025 --parquet cache/parquet
    uv run python scripts/ers_study.py --year 2026 --parquet cache/parquet_2026q

Reading the result as electrical deployment is a HYPOTHESIS. This study measures the
speed-trace feature only (see ``apex.analysis.ers.CONFOUNDERS``).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apex.analysis.ers import CONFOUNDERS, ClipConfig, LapClip, lap_clipping, repeatability_lift
from apex.core.laps import classify_laps
from apex.core.session import load_parquet

ROOT = Path(__file__).resolve().parents[1]
LAPS_PER_DRIVER = 3
N_BINS = 100
BOOT = 4000
WET_SHARE = 0.2  # stints on intermediate or wet tyres above this share: wet session


def study_session(directory: Path, cfg: ClipConfig) -> tuple[dict, list[dict], list[dict], int]:
    session = load_parquet(directory)
    classified = classify_laps(session)
    valid = classified[classified["valid"]].sort_values("lap_duration")
    best = valid.groupby("driver_number", sort=False).head(LAPS_PER_DRIVER)
    laps: list[LapClip] = []
    skipped = 0
    for r in best.itertuples():
        try:
            laps.append(lap_clipping(session, int(r.driver_number), int(r.lap_number), cfg))
        except (ValueError, LookupError):
            skipped += 1
    if best.shape[0] and skipped > 0.5 * best.shape[0]:
        raise RuntimeError(f"{skipped} of {best.shape[0]} laps could not be analysed")
    lap_rows, event_rows = [], []
    for lc in laps:
        lap_rows.append(
            {
                "driver": session.driver_code(lc.driver_number),
                "lap": lc.lap_number,
                "events": len(lc.events),
                "clip_s": lc.clip_s,
                "full_throttle_s": lc.full_throttle_s,
                "exposure_fast_s": lc.exposure_fast_s,
                "clip_share": lc.clip_share,
            }
        )
        for e in lc.events:
            event_rows.append(
                {
                    "driver": session.driver_code(lc.driver_number),
                    "lap": lc.lap_number,
                    "frac_start": e.frac_start,
                    "frac_end": e.frac_end,
                    "duration_s": e.duration_s,
                    "v_start_kmh": e.v_start_kmh,
                    "speed_lost_kmh": e.speed_lost_kmh,
                    "decel_ms2": e.decel_ms2,
                    "decel_se_ms2": e.decel_se_ms2,
                }
            )
    n = max(len(laps), 1)
    wet_share = float(
        session.stints["compound"].astype(str).str.upper().isin(["INTERMEDIATE", "WET"]).mean()
    )
    lift = repeatability_lift(laps, n_bins=N_BINS)
    bins = Counter(int(e["frac_start"] * N_BINS) for e in event_rows)
    top5 = sum(c for _, c in bins.most_common(5))
    total_events = sum(bins.values())
    shares = [lc.clip_share for lc in laps if np.isfinite(lc.clip_share)]
    row = {
        "location": session.meta.get("location"),
        "date": str(session.meta.get("date_start"))[:10],
        "session_key": session.session_key,
        "wet_share": wet_share,
        "wet": wet_share > WET_SHARE,
        "laps": len(laps),
        "laps_skipped": skipped,
        "laps_with_event": sum(1 for lc in laps if lc.events),
        "events_per_lap": total_events / n,
        "clip_share_mean": float(np.mean(shares)) if shares else float("nan"),
        "repeat_rate": lift["observed_repeat_rate"],
        "repeat_chance": lift["chance_repeat_rate"],
        "repeat_lift": lift["lift"],
        "top5_bin_share": top5 / total_events if total_events else float("nan"),
        "median_decel_ms2": float(np.median([e["decel_ms2"] for e in event_rows]))
        if event_rows
        else float("nan"),
    }
    for e in event_rows:
        e["session_key"] = session.session_key
        e["location"] = session.meta.get("location")
    for lr in lap_rows:
        lr["session_key"] = session.session_key
        lr["location"] = session.meta.get("location")
    return row, lap_rows, event_rows, skipped


def bootstrap_diff(a: np.ndarray, b: np.ndarray, seed: int = 0) -> dict[str, float]:
    """Mean(b) - mean(a) with a 95% bootstrap interval, resampling sessions."""
    rng = np.random.default_rng(seed)
    d = np.array([rng.choice(b, len(b)).mean() - rng.choice(a, len(a)).mean() for _ in range(BOOT)])
    return {
        "diff": float(b.mean() - a.mean()),
        "lo": float(np.quantile(d, 0.025)),
        "hi": float(np.quantile(d, 0.975)),
        "p_b_greater": float((d > 0).mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--parquet", default=None)
    ap.add_argument("--summary-only", action="store_true", help="recompute summary.json only")
    ap.add_argument("--out", default=str(ROOT / "docs" / "ers_study"))
    args = ap.parse_args()
    out = Path(args.out)
    (out / str(args.year)).mkdir(parents=True, exist_ok=True)
    if args.summary_only:
        summary = summarise(out)
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
        )
        print(json.dumps(summary.get("paired_circuits", {}), indent=2)[:600])
        return
    if args.parquet is None:
        ap.error("--parquet is required unless --summary-only")
    cfg = ClipConfig()

    sessions, laps, events, failures = [], [], [], []
    for d in sorted(p for p in Path(args.parquet).iterdir() if p.is_dir()):
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))["meta"]
        if meta.get("year") != args.year or meta.get("session_name") != "Qualifying":
            continue
        try:
            row, lr, er, _ = study_session(d, cfg)
        except Exception as exc:  # recorded, never hidden
            failures.append(
                {"location": meta.get("location"), "reason": f"{type(exc).__name__}: {exc}"}
            )
            print(f"FAILED {meta.get('location')}: {exc}", flush=True)
            continue
        sessions.append(row)
        laps += lr
        events += er
        print(
            f"{row['location']}: {row['laps']} laps, {row['events_per_lap']:.2f} events/lap, "
            f"share {row['clip_share_mean']:.3f}, repeat lift {row['repeat_lift']:.1f}",
            flush=True,
        )

    yd = out / str(args.year)
    pd.DataFrame(sessions).sort_values("date").to_csv(
        yd / "sessions.csv", index=False, float_format="%.4f", lineterminator="\n", encoding="utf-8"
    )
    pd.DataFrame(laps).to_csv(
        yd / "laps.csv", index=False, float_format="%.4f", lineterminator="\n", encoding="utf-8"
    )
    pd.DataFrame(events).to_csv(
        yd / "events.csv", index=False, float_format="%.4f", lineterminator="\n", encoding="utf-8"
    )
    (yd / "failures.json").write_text(
        json.dumps(failures, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"year {args.year}: {len(sessions)} sessions, {len(failures)} failed")
    summary = summarise(out)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary["years"], indent=2))


CIRCUIT_ALIASES = {"Monte Carlo": "Monaco"}


def paired_circuits(a: pd.DataFrame, b: pd.DataFrame) -> dict[str, Any]:
    """Same circuit in both years: how often is 2026 higher, and is the shift consistent?"""
    from scipy import stats

    x = a.assign(key=a["location"].replace(CIRCUIT_ALIASES))
    y = b.assign(key=b["location"].replace(CIRCUIT_ALIASES))
    m = x.merge(y, on="key", suffixes=("_2025", "_2026"))
    d = (m["events_per_lap_2026"] - m["events_per_lap_2025"]).to_numpy()
    return {
        "circuits": len(m),
        "higher_in_2026": int((d > 0).sum()),
        "equal": int((d == 0).sum()),
        "lower_in_2026": int((d < 0).sum()),
        "mean_difference_events_per_lap": float(d.mean()),
        "wilcoxon_p": float(stats.wilcoxon(d).pvalue),
        "rows": [
            {
                "circuit": r.key,
                "events_per_lap_2025": float(r.events_per_lap_2025),
                "events_per_lap_2026": float(r.events_per_lap_2026),
            }
            for r in m.itertuples()
        ],
    }


def summarise(out: Path) -> dict[str, Any]:
    """Combine every ``<year>/sessions.csv`` found into ``summary.json``."""
    years = sorted(int(p.name) for p in out.iterdir() if p.is_dir() and p.name.isdigit())
    per_year: dict[str, Any] = {}
    frames = {}
    for y in years:
        all_s = pd.read_csv(out / str(y) / "sessions.csv", encoding="utf-8")
        s = all_s[~all_s["wet"]].reset_index(drop=True)
        frames[y] = s
        per_year[str(y)] = {
            "sessions_all": len(all_s),
            "sessions_wet_excluded": [str(x) for x in all_s.loc[all_s["wet"], "location"]],
            "wet_sessions_events_per_lap": (
                float(all_s.loc[all_s["wet"], "events_per_lap"].mean())
                if all_s["wet"].any()
                else None
            ),
            "sessions": len(s),
            "laps": int(s["laps"].sum()),
            "events_per_lap": float(s["events_per_lap"].mean()),
            "share_laps_with_event": float(s["laps_with_event"].sum() / s["laps"].sum()),
            "clip_share_mean": float(s["clip_share_mean"].mean()),
            "median_decel_ms2": float(s["median_decel_ms2"].median()),
            "repeat_lift_median": float(s["repeat_lift"].median()),
            "repeat_lift_min": float(s["repeat_lift"].min()),
            "top5_bin_share_median": float(s["top5_bin_share"].median()),
        }
    summary: dict[str, Any] = {
        "years": per_year,
        "detector": ClipConfig().__dict__,
        "confounders": list(CONFOUNDERS),
        "tag": (
            "OBSERVED: the speed-trace feature. "
            "HYPOTHESIS: that it is electrical deployment ending."
        ),
    }
    if 2025 in frames and 2026 in frames:
        a, b = frames[2025], frames[2026]
        summary["era_contrast_2026_minus_2025"] = {
            "events_per_lap": bootstrap_diff(
                a["events_per_lap"].to_numpy(), b["events_per_lap"].to_numpy()
            ),
            "clip_share": bootstrap_diff(
                a["clip_share_mean"].to_numpy(), b["clip_share_mean"].to_numpy(), seed=1
            ),
            "median_decel_ms2": bootstrap_diff(
                a["median_decel_ms2"].dropna().to_numpy(),
                b["median_decel_ms2"].dropna().to_numpy(),
                seed=2,
            ),
            "unit": "dry sessions only; sessions are the resampling unit",
        }
        summary["paired_circuits"] = paired_circuits(a, b)
    return summary


if __name__ == "__main__":
    main()
