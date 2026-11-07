"""Per-corner, per-lap metrics.

Event locations (brake onset, lift, throttle pickup, minimum speed) are taken
from *raw* samples and reported as an interval: the event happened somewhere
between the last sample before it and the first sample showing it. At the
feed's ~4 Hz this interval is typically 10-20 m; its midpoint is the point
estimate and half its width the resolution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from apex.core.align import AlignedLap
from apex.core.track import Corner


@dataclass(frozen=True)
class CornerMetricsConfig:
    full_throttle_pct: float = 95.0
    pickup_throttle_pct: float = 20.0
    approach_m: float = 400.0  # search for braking up to this far before apex
    exit_offset_m: float = 100.0  # exit speed measured at apex_ref + this
    apex_halfwidth_m: float = 20.0


@dataclass(frozen=True)
class Event:
    s_before: float  # last raw sample without the event
    s_after: float  # first raw sample with the event

    @property
    def s(self) -> float:
        return 0.5 * (self.s_before + self.s_after)

    @property
    def resolution_m(self) -> float:
        return 0.5 * (self.s_after - self.s_before)


def _transition(s: np.ndarray, flag: np.ndarray, start: int, step: int) -> Event | None:
    """Walk from ``start`` in direction ``step`` to the first index where flag is True."""
    i = start
    while 0 <= i + step < len(s):
        if flag[i + step] and not flag[i]:
            a, b = sorted((s[i], s[i + step]))
            return Event(float(a), float(b))
        i += step
    return None


def corner_metrics(
    lap: AlignedLap,
    corner: Corner,
    cfg: CornerMetricsConfig | None = None,
    s_floor: float | None = None,
) -> dict[str, float | str | None]:
    """Metrics for one corner. ``s_floor`` bounds the backward search for
    braking/lift (normally just after the previous corner's apex) so events
    belonging to the previous corner are never attributed to this one."""
    cfg = cfg or CornerMetricsConfig()
    car = lap.tel.car
    s = lap.s
    speed = car["speed"].to_numpy(float)
    thr = car["throttle"].to_numpy(float)
    brk = car["brake"].to_numpy(float)
    lo = corner.s_apex - cfg.approach_m
    if s_floor is not None:
        lo = max(lo, s_floor)
    hi = corner.s_apex + cfg.exit_offset_m + 50
    win = np.where((s >= lo) & (s <= hi))[0]
    out: dict[str, float | str | None] = {"corner": corner.label, "lap": lap.tel.lap.key}
    if len(win) < 4:
        return out | {"note": "too few samples"}
    near = win[np.abs(s[win] - corner.s_apex) <= 80]
    i_min = int(near[np.argmin(speed[near])]) if len(near) else int(win[np.argmin(speed[win])])
    out |= {
        "v_min_kmh": float(speed[i_min]),
        "s_v_min": float(s[i_min]),
        "s_v_min_resolution_m": float(0.5 * (s[min(i_min + 1, len(s) - 1)] - s[max(i_min - 1, 0)])),
    }
    # braking onset: walking backwards from the minimum, the first brake-off sample
    pre = win[win <= i_min]
    if np.isnan(brk[pre]).any():
        out["brake_note"] = "brake sentinel in approach; onset not determined"
    else:
        onset = None
        for i in range(i_min, int(pre[0]), -1):
            if brk[i] == 1 and brk[i - 1] == 0:
                onset = Event(float(s[i - 1]), float(s[i]))
                break
        if onset:
            out |= {
                "brake_on_s": onset.s,
                "brake_on_resolution_m": onset.resolution_m,
                "v_entry_kmh": float(speed[np.searchsorted(s, onset.s_before)]),
            }
    # throttle lift: walking backwards from the minimum, last sample at full throttle
    if not np.isnan(thr[pre]).any():
        full = thr >= cfg.full_throttle_pct
        lift = None
        for i in range(i_min, int(pre[0]), -1):
            if full[i - 1] and not full[i]:
                lift = Event(float(s[i - 1]), float(s[i]))
                break
        if lift:
            out |= {"lift_s": lift.s, "lift_resolution_m": lift.resolution_m}
    # throttle pickup after the minimum
    post = win[win >= i_min]
    if not np.isnan(thr[post]).any():
        on = thr >= cfg.pickup_throttle_pct
        # If the throttle is already >= threshold at the minimum, the pickup has no
        # location after it: it is not located, rather than placed at the minimum.
        pick = _transition(s, on, i_min, +1) if not on[i_min] else None
        if pick and pick.s <= hi:
            out |= {"pickup_s": pick.s, "pickup_resolution_m": pick.resolution_m}
    s_exit = corner.s_apex + cfg.exit_offset_m
    out["v_exit_kmh"] = float(np.interp(s_exit, s, speed))  # interpolated, not observed
    return out


def zone_boundaries(
    corner: Corner, brake_ref_s: float | None, cfg: CornerMetricsConfig | None = None
) -> dict[str, tuple[float, float]]:
    """Braking / apex / exit zones, defined on the *reference* lap so both laps
    are timed over identical distance intervals."""
    cfg = cfg or CornerMetricsConfig()
    a0 = corner.s_apex - cfg.apex_halfwidth_m
    a1 = corner.s_apex + cfg.apex_halfwidth_m
    b0 = brake_ref_s if brake_ref_s is not None and brake_ref_s < a0 else a0 - 100.0
    return {"braking": (b0, a0), "apex": (a0, a1), "exit": (a1, corner.s_apex + cfg.exit_offset_m)}


def compare_corners(
    a: AlignedLap,
    b: AlignedLap,
    corners: list[Corner],
    cfg: CornerMetricsConfig | None = None,
) -> pd.DataFrame:
    """One row per corner: metrics of A and B, differences A − B, zone deltas.

    Zones use lap B's brake point as the reference.
    """
    cfg = cfg or CornerMetricsConfig()
    rows = []
    for i, c in enumerate(corners):
        floor = corners[i - 1].s_apex + cfg.apex_halfwidth_m if i > 0 else None
        ma, mb = corner_metrics(a, c, cfg, floor), corner_metrics(b, c, cfg, floor)
        row: dict[str, object] = {
            "corner": c.label,
            "kind": c.kind,
            "s_apex_ref": c.s_apex,
            "direction": c.direction,
        }
        for k in (
            "v_min_kmh",
            "s_v_min",
            "brake_on_s",
            "lift_s",
            "pickup_s",
            "v_entry_kmh",
            "v_exit_kmh",
        ):
            va, vb = ma.get(k), mb.get(k)
            row[f"{k}_A"], row[f"{k}_B"] = va, vb
            row[f"{k}_diff"] = (
                (va - vb) if isinstance(va, float) and isinstance(vb, float) else None
            )
        for k in ("brake_on_resolution_m", "lift_resolution_m", "pickup_resolution_m"):
            ra, rb = ma.get(k), mb.get(k)
            row[k] = (
                float(np.hypot(ra, rb)) if isinstance(ra, float) and isinstance(rb, float) else None
            )
        brake_ref = mb.get("brake_on_s")
        zones = zone_boundaries(c, brake_ref if isinstance(brake_ref, float) else None, cfg)
        for z, (z0, z1) in zones.items():
            ta = a.time_at(np.array([z0, z1]))
            tb = b.time_at(np.array([z0, z1]))
            row[f"{z}_zone"] = (z0, z1)
            row[f"{z}_delta_s"] = float((ta[1] - ta[0]) - (tb[1] - tb[0]))
        row["notes"] = "; ".join(
            str(m[k]) for m in (ma, mb) for k in ("brake_note", "note") if k in m
        )
        rows.append(row)
    return pd.DataFrame(rows)


__all__ = [
    "CornerMetricsConfig",
    "Event",
    "asdict",
    "compare_corners",
    "corner_metrics",
    "zone_boundaries",
]
