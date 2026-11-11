"""Build the static dashboard from the committed study outputs.

Reads ``docs/pace_study/<year>/`` and ``docs/ers_study/``, writes one self-contained page,
``docs/dashboard/index.html`` (no external requests).

    uv run python scripts/build_dashboard.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HIST_BINS = 50


def load_pace() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for ydir in sorted((DOCS / "pace_study").glob("[0-9]*")):
        races = []
        for f in sorted((ydir / "races").glob("*.json")):
            r = json.loads(f.read_text(encoding="utf-8"))
            # round the matrix and drop what the page does not use, to keep the file small
            r["prob_faster"]["matrix"] = [
                [round(x, 2) for x in row] for row in r["prob_faster"]["matrix"]
            ]
            for d in r["drivers"]:
                for k in ("mean_s", "lo_s", "hi_s", "rank_mean"):
                    d[k] = round(d[k], 4)
            races.append(r)
        races.sort(key=lambda r: str(r["meta"]["date"]))
        out[ydir.name] = races
    return out


def load_ers() -> dict[str, Any]:
    base = DOCS / "ers_study"
    sessions: list[dict[str, Any]] = []
    hist: dict[str, list[int]] = {}
    for ydir in sorted(p for p in base.iterdir() if p.is_dir() and p.name.isdigit()):
        s = pd.read_csv(ydir / "sessions.csv", encoding="utf-8")
        ev = pd.read_csv(ydir / "events.csv", encoding="utf-8")
        for rec in s.to_dict("records"):
            rec["year"] = int(ydir.name)
            rec["wet"] = bool(rec["wet"])
            sessions.append(
                {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in rec.items()}
            )
            e = ev[ev["session_key"] == rec["session_key"]]
            counts, _ = np.histogram(e["frac_start"], bins=HIST_BINS, range=(0, 1))
            hist[f"{ydir.name}|{rec['location']}"] = [int(c) for c in counts]
    summary = json.loads((base / "summary.json").read_text(encoding="utf-8"))
    return {
        "sessions": sessions,
        "hist": hist,
        "summary": summary,
        "confounders": summary["confounders"],
    }


def main() -> None:
    data = {
        "pace": load_pace(),
        "ers": load_ers(),
        "built": date.today().isoformat(),
        "note": (
            "Pace: laps-only OpenF1 data. "
            "ERS: qualifying car data, best three valid laps per driver."
        ),
    }
    template = (ROOT / "scripts" / "dashboard_template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, separators=(",", ":"), default=float).replace("</", "<\\/")
    app = (ROOT / "scripts" / "dashboard_app.js").read_text(encoding="utf-8")
    html = template.replace("%%APP%%", app).replace("%%DATA%%", payload)
    out = DOCS / "dashboard"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8", newline="\n")
    print(f"wrote {out / 'index.html'} ({len(html) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
