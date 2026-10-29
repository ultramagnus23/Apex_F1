"""Static figures for a two-lap comparison. Every title states the takeaway."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from apex.analysis.compare import Comparison
from apex.core.delta import provisional_sigma
from apex.report import style


def _colors(cmp: Comparison, drivers: object) -> tuple[str, str]:
    import pandas as pd

    d = drivers if isinstance(drivers, pd.DataFrame) else pd.DataFrame()

    def col(num: int, fb: str) -> str:
        if d.empty:
            return fb
        hit = d[d["driver_number"] == num]
        return style.team_color(hit["team_colour"].iloc[0] if len(hit) else None, fb)

    return style.distinct(
        col(cmp.a.tel.lap.driver_number, style.FALLBACK_A),
        col(cmp.b.tel.lap.driver_number, style.FALLBACK_B),
    )


def takeaway(cmp: Comparison) -> str:
    total = cmp.a.tel.lap.lap_duration - cmp.b.tel.lap.lap_duration
    faster, slower = (cmp.code_a, cmp.code_b) if total < 0 else (cmp.code_b, cmp.code_a)
    sec = cmp.sectors
    i = int(np.argmax(np.abs(sec["official_delta"].to_numpy())))
    return (
        f"{faster} {abs(total):.3f} s faster than {slower}; biggest official sector gap "
        f"{sec['sector'].iloc[i]} ({sec['official_delta'].iloc[i]:+.3f} s, "
        f"{cmp.code_a}−{cmp.code_b})"
    )


def overlay(cmp: Comparison, drivers: object, path: Path) -> Path:
    style.apply()
    ca, cb = _colors(cmp, drivers)
    g = cmp.grid
    fig, axes = plt.subplots(
        5, 1, figsize=(13, 10), sharex=True, gridspec_kw={"height_ratios": [3, 1.2, 0.8, 1, 1.6]}
    )
    for lap, c, code in ((cmp.a, ca, cmp.code_a), (cmp.b, cb, cmp.code_b)):
        axes[0].plot(g, lap.channel("speed", g), color=c, lw=1.1, label=code)
        axes[0].plot(lap.s, lap.tel.car["speed"], ".", color=c, ms=1.6, alpha=0.6)
        axes[1].plot(g, lap.channel("throttle", g), color=c, lw=1.0)
        axes[2].step(g, lap.channel("brake", g), where="post", color=c, lw=1.0)
        axes[3].step(g, lap.channel("gear", g), where="post", color=c, lw=1.0)
    axes[0].set_ylabel("Speed [km/h]")
    axes[1].set_ylabel("Throttle [%]")
    axes[2].set_ylabel("Brake")
    axes[2].set_yticks([0, 1], ["off", "on"])
    axes[3].set_ylabel("Gear")
    axes[0].legend(loc="lower right", ncols=2, fontsize=8)
    axes[0].text(
        0.005,
        0.03,
        "dots = raw samples (OBSERVED); lines = interpolated",
        transform=axes[0].transAxes,
        color=style.MUTED,
        fontsize=7,
    )

    bnd = cmp.boundaries
    pinned = [0.0, cmp.track.line.length, bnd.s1, bnd.s2]
    sig = provisional_sigma([cmp.a, cmp.b], g, max(bnd.sd_s1, bnd.sd_s2), pinned)
    ax = axes[4]
    ax.fill_between(
        g,
        cmp.delta - 2 * sig,
        cmp.delta + 2 * sig,
        color=style.NOISE,
        alpha=0.5,
        lw=0,
        label="±2σ (provisional noise model)",
    )
    ax.plot(g, cmp.delta, color=style.TEXT, lw=1.2)
    ax.axhline(0, color=style.MUTED, lw=0.6)
    ax.set_ylabel(f"Δt [s]\n{cmp.code_a}−{cmp.code_b}")
    ax.text(
        0.005,
        0.05,
        f"negative = {cmp.code_a} ahead",
        transform=ax.transAxes,
        color=style.MUTED,
        fontsize=7,
    )
    ax.legend(loc="upper left", fontsize=7)
    ax.set_xlabel("Distance along reference line [m]")

    vmax = float(np.nanmax(cmp.track.v_ref_kmh))
    for c in cmp.track.corners:
        for a_ in axes:
            a_.axvline(c.s_apex, color=style.GRID, lw=0.6, zorder=0)
        axes[0].text(
            c.s_apex,
            vmax + 8,
            c.label,
            ha="center",
            fontsize=7,
            color=style.TEXT if c.kind == "braking" else style.MUTED,
        )
    for sb, name in ((bnd.s1, "S1|S2"), (bnd.s2, "S2|S3")):
        for a_ in axes:
            a_.axvline(sb, color=style.MUTED, lw=0.9, ls="--")
        axes[4].text(
            sb, axes[4].get_ylim()[1], name, ha="center", va="bottom", fontsize=7, color=style.MUTED
        )
    axes[0].set_ylim(top=vmax + 25)
    fig.suptitle(takeaway(cmp), x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, metadata={"Software": None})
    plt.close(fig)
    return path


def corner_bars(cmp: Comparison, path: Path) -> Path:
    style.apply()
    df = cmp.corner_segments
    fig, ax = plt.subplots(figsize=(13, 4.2))
    x = np.arange(len(df))
    colors = [
        style.NOISE if n else (style.FALLBACK_A if d < 0 else style.FALLBACK_B)
        for d, n in zip(df["delta"], df["within_noise"], strict=True)
    ]
    ax.bar(x, df["delta"], color=colors, yerr=2 * df["sigma"], ecolor=style.MUTED, capsize=2)
    ax.axhline(0, color=style.MUTED, lw=0.6)
    ax.set_xticks(x, df["segment"])
    ax.set_ylabel(f"Segment Δt [s] ({cmp.code_a}−{cmp.code_b})")
    sig = df[~df["within_noise"]]
    if sig.empty:
        title = (
            f"No corner segment differs by more than 2σ: the {cmp.code_a}–{cmp.code_b} gap "
            "cannot be localised to individual corners at this resolution"
        )
    else:
        parts = ", ".join(f"{r.segment} ({r.delta:+.3f} s)" for r in sig.itertuples())
        title = (
            f"{len(sig)} of {len(df)} corner segments exceed 2σ: {parts} "
            f"[{cmp.code_a}−{cmp.code_b}]; the rest are within noise"
        )
    fig.suptitle(title, x=0.01, ha="left", fontsize=12, fontweight="bold")
    ax.text(
        0.005,
        0.03,
        "grey = within ±2σ of zero (not distinguishable from noise); error bars = ±2σ provisional",
        transform=ax.transAxes,
        color=style.MUTED,
        fontsize=7,
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, metadata={"Software": None})
    plt.close(fig)
    return path
