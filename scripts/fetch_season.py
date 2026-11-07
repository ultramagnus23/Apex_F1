"""Download every session of one type for a season into the raw cache, and
store a Parquet copy of each for fast reloads.

Usage:
    uv run python scripts/fetch_season.py --year 2025 --session Qualifying
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from apex.core.session import load_openf1, save_parquet
from apex.core.sources.openf1 import OpenF1Client


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--session", default="Qualifying")
    ap.add_argument("--cache", default="cache/openf1")
    ap.add_argument("--parquet", default="cache/parquet")
    args = ap.parse_args()

    c = OpenF1Client(args.cache)
    sessions = c.frame("sessions", {"year": args.year, "session_name": args.session})
    sessions = sessions.sort_values("date_start")
    log = []
    for r in sessions.itertuples():
        key = int(r.session_key)
        out = Path(args.parquet) / str(key)
        t = time.time()
        status = "cached"
        if not (out / "meta.json").exists():
            try:
                save_parquet(load_openf1(key, args.cache), out)
                status = "ok"
            except Exception as exc:  # recorded, not hidden
                status = f"error: {type(exc).__name__}: {exc}"
        log.append(
            {
                "session_key": key,
                "location": r.location,
                "date": r.date_start,
                "status": status,
                "seconds": round(time.time() - t, 1),
            }
        )
        print(json.dumps(log[-1]), flush=True)
    Path(args.parquet).mkdir(parents=True, exist_ok=True)
    (Path(args.parquet) / f"fetch_{args.year}_{args.session}.json").write_text(
        json.dumps(log, indent=2, default=str) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
