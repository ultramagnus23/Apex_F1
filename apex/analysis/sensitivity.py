"""Sensitivity of comparison conclusions to analysis choices.

A conclusion is only OBSERVED if it survives the choices Apex had to make:

* pairing: which top-k laps of each driver are compared (k x k pairings);
* reference set: which laps build the reference line and speed profile;
* method: distance alignment (hybrid anchored, speed anchored, xy unanchored).

Each (segment, configuration) gets a verdict: "A" (A faster beyond noise),
"B" (B faster beyond noise) or "none" (within 2 sigma). A segment's stability is
the share of configurations agreeing with the majority verdict. A bootstrap over
the pairings gives a resampling interval for the mean delta.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from apex.analysis.compare import Comparison, SessionContext, build_context, compare
from apex.core.claims import Kind
from apex.core.session import SessionData

METHODS: tuple[tuple[str, bool], ...] = (("hybrid", True), ("speed", True), ("xy", False))
SIGMA_LEVEL = 2.0
STABILITY_MIN = 0.8


def verdict(delta: float, sigma: float) -> str:
    if abs(delta) < SIGMA_LEVEL * sigma:
        return "none"
    return "A" if delta < 0 else "B"


def top_keys(ctx: SessionContext, driver: int, k: int) -> list[str]:
    c = ctx.classified
    v = c[c["valid"] & (c["driver_number"] == driver)].nsmallest(k, "lap_duration")
    return [f"{driver}:{int(n)}" for n in v["lap_number"]]


def reference_contexts(
    session: SessionData, classified: pd.DataFrame, n: int = 10
) -> dict[str, SessionContext]:
    """Baseline context plus alternative reference sets built from other push laps."""
    base = build_context(session, classified)
    keys = base.track.lap_keys
    out = {"baseline": base}
    for name, rk in {"mid": keys[n // 2 : n // 2 + n], "late": keys[-n:]}.items():
        if len(rk) >= 5 and rk != keys[:n]:
            out[name] = build_context(session, classified, ref_keys=rk)
    return out


@dataclass(frozen=True)
class Sensitivity:
    session_key: int
    driver_a: str
    driver_b: str
    segments: pd.DataFrame  # one row per (configuration, segment)
    events: pd.DataFrame  # one row per (configuration, corner)
    n_ref_sets: int
    n_pairs: int
    corner_set_mismatch: int


def pair_sensitivity(
    session: SessionData,
    contexts: dict[str, SessionContext],
    driver_a: int,
    driver_b: int,
    k: int = 3,
) -> Sensitivity:
    labels = [c.label for c in contexts["baseline"].track.corners]
    seg_rows: list[dict[str, object]] = []
    ev_rows: list[dict[str, object]] = []
    mismatch = 0
    n_pairs = 0
    for ref_name, ctx in contexts.items():
        for ka in top_keys(ctx, driver_a, k):
            for kb in top_keys(ctx, driver_b, k):
                n_pairs += 1
                la = (int(ka.split(":")[0]), int(ka.split(":")[1]))
                lb = (int(kb.split(":")[0]), int(kb.split(":")[1]))
                for method, anchor in METHODS:
                    c: Comparison = compare(
                        session, la, lb, method=method, anchor_sectors=anchor, ctx=ctx
                    )
                    cfg = f"{ref_name}|{method}"
                    pair = f"{ka}|{kb}"
                    cs = c.corner_segments
                    if list(cs["segment"]) != labels:
                        mismatch += 1  # corner set differs under this reference line
                        continue
                    for r in cs.itertuples():
                        seg_rows.append(
                            {
                                "config": cfg,
                                "pair": pair,
                                "ref": ref_name,
                                "method": method,
                                "segment": r.segment,
                                "delta": r.delta,
                                "sigma": r.sigma,
                                "verdict": verdict(r.delta, r.sigma),
                            }
                        )
                    for r in c.corners.itertuples():
                        ev_rows.append(
                            {
                                "config": cfg,
                                "pair": pair,
                                "ref": ref_name,
                                "method": method,
                                "corner": r.corner,
                                "kind": r.kind,
                                "brake_diff": r.brake_on_s_diff,
                                "brake_res": r.brake_on_resolution_m,
                                "pickup_diff": r.pickup_s_diff,
                                "pickup_res": r.pickup_resolution_m,
                                "vmin_diff": r.v_min_kmh_diff,
                                "vexit_diff": r.v_exit_kmh_diff,
                            }
                        )
    return Sensitivity(
        session.session_key,
        str(session.driver_code(driver_a)),
        str(session.driver_code(driver_b)),
        pd.DataFrame(seg_rows),
        pd.DataFrame(ev_rows),
        len(contexts),
        n_pairs,
        mismatch,
    )


def summarise_segments(seg: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Per segment: consensus verdict, stability, mean delta, bootstrap interval, kind."""
    rng = np.random.default_rng(seed)
    base = seg[(seg["ref"] == "baseline") & (seg["method"] == "hybrid")]
    rows = []
    for name, g in seg.groupby("segment", sort=False):
        consensus = str(g["verdict"].value_counts().idxmax())
        stability = float((g["verdict"] == consensus).mean())
        deltas = base.loc[base["segment"] == name, "delta"].to_numpy(dtype=float)
        boots = rng.choice(deltas, size=(n_boot, len(deltas)), replace=True).mean(axis=1)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        if consensus == "none":
            kind, why = Kind.INCONCLUSIVE, "within 2 sigma noise in most configurations"
        elif stability >= STABILITY_MIN:
            kind = Kind.OBSERVED
            why = f"beyond 2 sigma in {stability:.0%} of configurations"
        else:
            kind = Kind.INCONCLUSIVE
            why = f"verdict flips across configurations (stability {stability:.0%})"
        rows.append(
            {
                "segment": name,
                "consensus": consensus,
                "stability": stability,
                "n_configs": len(g),
                "delta_base": float(deltas.mean()),
                "delta_mean_all": float(g["delta"].mean()),
                "sigma_base": float(base.loc[base["segment"] == name, "sigma"].mean()),
                "boot_lo": float(lo),
                "boot_hi": float(hi),
                "kind": kind.value,
                "why": why,
            }
        )
    return pd.DataFrame(rows)


def summarise_events(ev: pd.DataFrame) -> pd.DataFrame:
    """Stability of brake-point and pickup differences per corner.

    A difference counts only when it exceeds the event's resolution. Stability is
    the share of configurations, among those where it is resolved, that agree on
    the sign of the majority direction.
    """
    rows = []
    for name, g in ev.groupby("corner", sort=False):
        out: dict[str, object] = {"corner": name, "kind": g["kind"].iloc[0]}
        for col, res in (
            ("brake_diff", "brake_res"),
            ("pickup_diff", "pickup_res"),
            ("vmin_diff", None),
        ):
            d = g[col].astype(float)
            # minimum speed has no sample-based resolution here: use 3 km/h
            r = g[res].astype(float) if res else pd.Series(3.0, index=g.index)
            ok = d.notna() & r.notna()
            if not ok.any():
                out[f"{col}_stability"] = None
                out[f"{col}_median"] = None
                continue
            beyond = ok & (d.abs() > r)
            if not beyond.any():
                out[f"{col}_stability"] = 0.0
                out[f"{col}_median"] = float(d[ok].median())
                continue
            majority = float(np.sign(d[beyond]).mode().iloc[0])
            agree = int((beyond & (np.sign(d) == majority)).sum())
            out[f"{col}_stability"] = agree / int(ok.sum())
            out[f"{col}_median"] = float(d[ok].median())
        rows.append(out)
    return pd.DataFrame(rows)
