"""Race-pace study: fit every race of a season and check the posterior against held-out laps.

Reads the laps-only Parquet cache written by ``fetch_season.py --laps-only``. For each
race it writes the full result as JSON and records four held-out checks:

* ``random``   interpolation: hold out 20% of laps
* ``stint``    hold out whole stints (tests the stint-to-stint variation in the intervals)
* ``forward``  extrapolation: fit the first 80% of the race, predict the rest

Outputs go to ``docs/pace_study/<year>/``:
``races/<location>.json``, ``summary.csv`` and ``summary.json``.

    uv run python scripts/fetch_season.py --year 2025 --session Race --laps-only
    uv run python scripts/pace_study.py --year 2025
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apex.analysis.pace import (
    PaceConfig,
    codes_for,
    cross_validate,
    fit_pace,
    race_lap_table,
)
from apex.core.session import load_parquet

ROOT = Path(__file__).resolve().parents[1]
STINT_REPEATS = 5


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def study_race(directory: Path, cfg: PaceConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    session = load_parquet(directory)
    table = race_lap_table(session, cfg)
    result = fit_pace(table, codes_for(session), cfg, session_key=session.session_key)
    random_cv = cross_validate(table, cfg, scheme="random")
    forward_cv = cross_validate(table, cfg, scheme="forward")
    stint_cvs = [cross_validate(table, cfg, scheme="stint", seed=k) for k in range(STINT_REPEATS)]
    payload = result.to_dict()
    payload["meta"] = {
        "location": session.meta.get("location"),
        "date": session.meta.get("date_start"),
        "year": session.meta.get("year"),
    }
    payload["validation"] = {
        "random": random_cv.__dict__,
        "forward": forward_cv.__dict__,
        "stint": {
            "scheme": "stint",
            "repeats": STINT_REPEATS,
            "coverage": float(np.mean([c.coverage for c in stint_cvs])),
            "nominal": cfg.ci,
            "mae_s": float(np.mean([c.mae_s for c in stint_cvs])),
        },
    }
    pf = result.prob_faster.to_numpy()
    iu = np.triu_indices_from(pf, k=1)
    decided = np.maximum(pf[iu], 1 - pf[iu])
    row = {
        "location": session.meta.get("location"),
        "date": str(session.meta.get("date_start"))[:10],
        "session_key": session.session_key,
        "status": result.status,
        "status_reasons": "; ".join(result.status_reasons),
        "drivers": len(result.drivers),
        "clean_laps": result.n_clean,
        "excluded_flag": result.exclusions["FLAG"],
        "excluded_outlier": result.exclusions["OUTLIER"],
        "sigma_s": result.sigma_s,
        "stint_sd_s": result.stint_sd_s,
        "pace_spread_s": float(result.drivers["mean_s"].max() - result.drivers["mean_s"].min()),
        "pairs": len(decided),
        "pairs_p90": int((decided >= 0.9).sum()),
        "cov_random": random_cv.coverage,
        "cov_stint": payload["validation"]["stint"]["coverage"],
        "cov_forward": forward_cv.coverage,
        "mae_random_s": random_cv.mae_s,
        "mae_forward_s": forward_cv.mae_s,
    }
    return payload, row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--parquet", default=str(ROOT / "cache" / "parquet_laps"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = Path(args.out) if args.out else ROOT / "docs" / "pace_study" / str(args.year)
    (out / "races").mkdir(parents=True, exist_ok=True)
    cfg = PaceConfig()

    rows, failures = [], []
    dirs = sorted(p for p in Path(args.parquet).iterdir() if p.is_dir())
    for d in dirs:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))["meta"]
        if meta.get("year") != args.year:
            continue
        try:
            payload, row = study_race(d, cfg)
        except Exception as exc:  # recorded, never hidden
            failures.append(
                {"location": meta.get("location"), "reason": f"{type(exc).__name__}: {exc}"}
            )
            print(f"FAILED {meta.get('location')}: {exc}", flush=True)
            continue
        rows.append(row)
        name = slug(str(meta["location"]))
        (out / "races" / f"{name}.json").write_text(
            json.dumps(payload, indent=1, default=float) + "\n", encoding="utf-8", newline="\n"
        )
        print(
            f"{row['location']}: {row['status']} clean={row['clean_laps']} "
            f"cov random/stint/forward = {row['cov_random']:.2f}/"
            f"{row['cov_stint']:.2f}/{row['cov_forward']:.2f}",
            flush=True,
        )

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df.to_csv(
        out / "summary.csv", index=False, float_format="%.4f", lineterminator="\n", encoding="utf-8"
    )
    ok = df[df["status"] == "OK"]
    summary = {
        "year": args.year,
        "races_fitted": len(df),
        "races_ok": len(ok),
        "races_not_modelled": df.loc[df["status"] != "OK", ["location", "status_reasons"]].to_dict(
            "records"
        ),
        "failures": failures,
        "ci": cfg.ci,
        "coverage_mean": {k: float(ok[f"cov_{k}"].mean()) for k in ("random", "stint", "forward")},
        "coverage_min": {k: float(ok[f"cov_{k}"].min()) for k in ("random", "stint", "forward")},
        "mae_s": {
            "random": float(ok["mae_random_s"].mean()),
            "forward": float(ok["mae_forward_s"].mean()),
        },
        "median_noise_sigma_s": float(ok["sigma_s"].median()),
        "median_pace_spread_s": float(ok["pace_spread_s"].median()),
        "share_of_pairs_decided_90": float(ok["pairs_p90"].sum() / ok["pairs"].sum()),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
