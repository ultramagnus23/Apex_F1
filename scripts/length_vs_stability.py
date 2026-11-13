"""Does circuit length explain how stable segment conclusions are? (2025 season follow-up)

Spa-Francorchamps had far more sign flips than any other 2025 qualifying session. One untested
idea was that long circuits are noisier, because the calibrated noise model grows with the distance
between official timing points. This script measures each circuit's lap length from the fastest
valid lap and correlates it with the mean stability in ``season_2025/conclusion_flips.csv``.

    uv run python scripts/length_vs_stability.py

Writes ``docs/season_2025/circuit_length_vs_stability.csv`` and ``length_vs_stability.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from apex.core.laps import classify_laps
from apex.core.session import load_parquet
from apex.core.telemetry import extract_lap, lap_ref

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "season_2025"
PARQUET = ROOT / "cache" / "parquet"


def lap_length_m(directory: Path) -> tuple[float, float]:
    """Length (integrated speed) and time of the session's fastest valid lap."""
    s = load_parquet(directory)
    c = classify_laps(s)
    best = c[c["valid"]].sort_values("lap_duration").iloc[0]
    car = extract_lap(s, lap_ref(s, int(best["driver_number"]), int(best["lap_number"]))).car
    car = car[(car["t"] >= 0) & (car["t"] <= best["lap_duration"])]
    return float(np.trapezoid(car["speed"].to_numpy() / 3.6, car["t"].to_numpy())), float(
        best["lap_duration"]
    )


def main() -> None:
    flips = pd.read_csv(OUT / "conclusion_flips.csv", encoding="utf-8")
    stab = flips.groupby("location")["stability"].mean()
    flip_any = flips.groupby("location")["flips_any"].mean()
    fetch = json.loads((PARQUET / "fetch_2025_Qualifying.json").read_text(encoding="utf-8"))
    rows = []
    for r in fetch:
        if r["status"] not in ("ok", "cached") or r["location"] not in stab.index:
            continue
        length, secs = lap_length_m(PARQUET / str(r["session_key"]))
        rows.append((r["location"], length, secs, stab[r["location"]], flip_any[r["location"]]))
    df = pd.DataFrame(rows, columns=["location", "length_m", "lap_s", "stability", "flip_any"])
    df = df.sort_values("length_m")
    df.to_csv(
        OUT / "circuit_length_vs_stability.csv",
        index=False,
        float_format="%.4f",
        lineterminator="\n",
        encoding="utf-8",
    )
    rho_s = stats.spearmanr(df["length_m"], df["stability"])
    rho_f = stats.spearmanr(df["length_m"], df["flip_any"])
    spa = flips[flips["location"].str.startswith("Spa")]
    ref_flips = spa[spa["flips_with_reference"]]
    # which rival laps carry the reference-set flips
    rivals = ref_flips["pair"].str.split("|").str[1].value_counts().to_dict()
    result = {
        "circuits": len(df),
        "spearman_stability_vs_length": {"rho": float(rho_s.statistic), "p": float(rho_s.pvalue)},
        "spearman_flip_rate_vs_length": {"rho": float(rho_f.statistic), "p": float(rho_f.pvalue)},
        "spa_mean_stability": float(spa["stability"].mean()),
        "all_mean_stability": float(flips["stability"].mean()),
        "spa_reference_flips_by_rival_lap": rivals,
        "conclusion": (
            "Circuit length does not explain Spa: the correlation is weak and not significant."
        ),
    }
    (OUT / "length_vs_stability.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
