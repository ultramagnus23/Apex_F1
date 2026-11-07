"""One visual style for every Apex figure: dark, calm, legible."""

from __future__ import annotations

from typing import Final

import matplotlib as mpl

BG: Final = "#0f1115"
PANEL: Final = "#151922"
GRID: Final = "#262c38"
TEXT: Final = "#d7dce5"
MUTED: Final = "#8a93a6"
NOISE: Final = "#4a5163"  # bars/values within measurement noise
FALLBACK_A: Final = "#4fa3ff"
FALLBACK_B: Final = "#ff8a3d"


def apply() -> None:
    mpl.rcParams.update(
        {
            "figure.facecolor": BG,
            "axes.facecolor": PANEL,
            "axes.edgecolor": GRID,
            "axes.labelcolor": TEXT,
            "axes.titlecolor": TEXT,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": TEXT,
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "legend.facecolor": PANEL,
            "legend.edgecolor": GRID,
            "savefig.facecolor": BG,
            "savefig.dpi": 150,
            # deterministic PNG output
            "svg.hashsalt": "apex",
            "path.simplify": False,
        }
    )


def team_color(hex_no_hash: object, fallback: str) -> str:
    s = str(hex_no_hash or "").strip().lstrip("#")
    if len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s):
        return f"#{s}"
    return fallback


def distinct(c1: str, c2: str) -> tuple[str, str]:
    """Keep teammates (same colour) distinguishable."""
    if c1.lower() == c2.lower():
        return c1, FALLBACK_B
    return c1, c2
