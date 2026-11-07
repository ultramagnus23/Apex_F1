"""Build the offline regression fixture: car/location rows around every flying lap.

Usage:
    uv run python scripts/make_fixture.py --session-key 11392 --out tests/fixtures/openf1_11392
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from apex.analysis.compare import flying_laps
from apex.core.laps import classify_laps
from apex.core.session import load_openf1, save_parquet, window_subset


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-key", type=int, required=True)
    ap.add_argument("--cache", default="cache/openf1")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pad-s", type=float, default=4.0)
    args = ap.parse_args()

    s = load_openf1(args.session_key, args.cache, offline=True)
    fl = flying_laps(classify_laps(s))
    laps = s.laps.set_index(["driver_number", "lap_number"])
    pad = pd.to_timedelta(args.pad_s, unit="s")
    windows = []
    for r in fl.itertuples():
        row = laps.loc[(r.driver_number, r.lap_number)]
        windows.append(
            (
                int(r.driver_number),
                row["t0"] - pad,
                row["t0"] + pd.to_timedelta(float(row["lap_duration"]), unit="s") + pad,
            )
        )
    sub = window_subset(s, windows)
    save_parquet(sub, args.out)
    print(
        f"{len(windows)} laps, car rows {len(sub.car)}, "
        f"location rows {len(sub.location)} -> {args.out}"
    )


if __name__ == "__main__":
    main()
