"""Assemble tagged claims for one comparison.

Observations come from the data and carry stability from sensitivity analysis.
Hypotheses are explicit, rule-based and always list their confounders. Unknowns
name what public data cannot show, so readers see the limits next to the results.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from apex.analysis.compare import Comparison
from apex.core.claims import Claim, Kind, downgrade_if_unstable

BRAKE_CONFOUNDERS = (
    "entry line and corner-entry speed (lateral position is not observable)",
    "brake-pressure and on/off sampling at ~4 Hz (brake is binary here)",
    "tyre age and compound (both laps on the same compound in this case)",
    "traffic or a tow from the car ahead (gap not computed in this version)",
)
PICKUP_CONFOUNDERS = (
    "pedal-to-torque maps differ between power units; equal pedal % is not equal torque",
    "exit speed and corner-exit line",
    "driver throttle-modulation style",
)
MIN_SPEED_CONFOUNDERS = (
    "racing line through the apex",
    "traffic or a tow on the approach",
    "tyre temperature and grip (not observed)",
)
TRACK_EVOLUTION = ("the grip level of the track changes over a session; the later lap may benefit",)
UNKNOWNS = (
    ("Tyre surface and carcass temperatures and pressures", "not in either feed"),
    ("Fuel mass", "not in either feed; a configurable assumption in Phase 5"),
    ("ERS state of charge and deployment", "not in either feed"),
    ("Active-aero mode and wing levels", "not in either feed; drs channel is empty in 2026"),
    ("Car setup (ride height, springs, diff, brake balance)", "not in either feed"),
    ("Driver intent and team instructions", "not in either feed"),
    ("Slipstream and dirty air", "gap to the car ahead is not computed in this version"),
)


@dataclass(frozen=True)
class Stability:
    segments: pd.DataFrame  # output of summarise_segments
    events: pd.DataFrame  # output of summarise_events


def _seg_row(stab: Stability, name: str) -> pd.Series | None:
    hit = stab.segments[stab.segments["segment"] == name]
    return hit.iloc[0] if len(hit) else None


def _event_row(stab: Stability, name: str) -> pd.Series | None:
    hit = stab.events[stab.events["corner"] == name]
    return hit.iloc[0] if len(hit) else None


def _segment_text(name: str, s0: float, s1: float, consensus: str, a: str, b: str) -> str:
    span = f"{name} ({s0:.0f}–{s1:.0f} m)"
    if consensus == "none":
        return f"{span}: no reliable difference"
    leader = a if consensus == "A" else b
    return f"{span}: {leader} is usually faster, but not stably enough to claim"


def _stab(ev: pd.Series | None, col: str) -> float | None:
    if ev is None or ev.get(col) is None or pd.isna(ev.get(col)):
        return None
    return float(ev[col])


def _event_claims(r: Any, ev: pd.Series | None, a: str, b: str) -> list[Claim]:
    """Observed event differences (gated on stability), then hypotheses built on them."""
    out: list[Claim] = []
    name = r.corner
    kind = r.kind

    def observed(
        diff: float, res: float, stab: float | None, what: str, unit: str, scale: float
    ) -> Claim | None:
        if not (isinstance(diff, float) and abs(diff) > res):
            return None
        earlier = a if diff < 0 else b
        claim = Claim(
            Kind.OBSERVED,
            f"{earlier} {what} {name} by {abs(diff) * scale:.0f} {unit}",
            evidence=(f"raw-sample event, resolution ±{res * scale:.0f} {unit}",),
            magnitude=diff * scale,
            magnitude_sigma=res * scale,
            unit=f"{unit} (A − B)",
            stability=stab,
        )
        return downgrade_if_unstable(claim)

    if kind == "braking":
        c = observed(
            r.brake_on_s_diff,
            r.brake_on_resolution_m,
            _stab(ev, "brake_diff_stability"),
            "brakes earlier into",
            "m",
            1.0,
        )
        if c is not None:
            out.append(c)
            if c.kind is Kind.OBSERVED:
                earlier = a if r.brake_on_s_diff < 0 else b
                out.append(
                    Claim(
                        Kind.HYPOTHESIS,
                        f"consistent with a deliberate earlier brake point into {name} "
                        f"by {earlier}",
                        evidence=(f"brake onset difference {r.brake_on_s_diff:+.0f} m",),
                        confounders=BRAKE_CONFOUNDERS,
                    )
                )

    c = observed(
        r.pickup_s_diff,
        r.pickup_resolution_m,
        _stab(ev, "pickup_diff_stability"),
        "reaches 20% throttle earlier after the apex of",
        "m",
        1.0,
    )
    if c is not None:
        out.append(c)
        if c.kind is Kind.OBSERVED:
            earlier = a if r.pickup_s_diff < 0 else b
            out.append(
                Claim(
                    Kind.HYPOTHESIS,
                    f"{earlier}'s earlier throttle pickup at {name} is consistent with earlier "
                    "traction",
                    evidence=(f"throttle pickup difference {r.pickup_s_diff:+.0f} m",),
                    confounders=PICKUP_CONFOUNDERS,
                )
            )

    vd = r.v_min_kmh_diff
    if isinstance(vd, float) and abs(vd) >= 3.0:
        lower = a if vd < 0 else b
        stab = _stab(ev, "vmin_diff_stability")
        claim = downgrade_if_unstable(
            Claim(
                Kind.OBSERVED,
                f"{lower} has the lower minimum speed through {name}",
                evidence=(f"minimum raw speed differs by {abs(vd):.0f} km/h (raw samples)",),
                magnitude=vd,
                unit="km/h (A − B)",
                stability=stab,
            )
        )
        out.append(claim)
        if claim.kind is Kind.OBSERVED:
            out.append(
                Claim(
                    Kind.HYPOTHESIS,
                    f"{lower} carries less speed through {name}; the cause is not established",
                    evidence=(f"minimum speed difference {vd:+.0f} km/h",),
                    confounders=MIN_SPEED_CONFOUNDERS,
                )
            )
    return out


def build_claims(cmp: Comparison, stab: Stability, st_speeds: tuple[float, float]) -> list[Claim]:
    """``st_speeds``: OpenF1 speed-trap values (km/h) for lap A and lap B."""
    a, b = cmp.code_a, cmp.code_b
    la, lb = cmp.a.tel.lap, cmp.b.tel.lap
    out: list[Claim] = []

    # --- official timing: exact, so stability 1 --------------------------------
    lap_gap = la.lap_duration - lb.lap_duration
    faster = a if lap_gap < 0 else b
    out.append(
        Claim(
            Kind.OBSERVED,
            f"{faster} set the faster lap ({a} lap {la.lap_number} vs {b} lap {lb.lap_number})",
            evidence=("OpenF1 lap_duration, 1 ms resolution",),
            magnitude=lap_gap,
            magnitude_sigma=0.0,
            unit="s (A − B)",
            stability=1.0,
        )
    )
    for r in cmp.sectors.itertuples():
        out.append(
            Claim(
                Kind.OBSERVED,
                f"{r.sector} official gap, {a} − {b}",
                evidence=("OpenF1 sector time, 1 ms resolution",),
                magnitude=r.official_delta,
                magnitude_sigma=0.0,
                unit="s",
                stability=1.0,
                note=f"telemetry-only estimate before anchoring: {r.unanchored_delta:+.3f} s",
            )
        )

    # --- segment deltas: from sensitivity, not from one lap pair ---------------
    for r in cmp.corner_segments.itertuples():
        row = _seg_row(stab, r.segment)
        if row is None:
            continue
        mag = float(row["delta_base"])
        sig = float(row["sigma_base"])
        if row["kind"] == Kind.OBSERVED.value:
            who = a if mag < 0 else b
            out.append(
                downgrade_if_unstable(
                    Claim(
                        Kind.OBSERVED,
                        f"{who} is faster through {r.segment} ({r.s_start:.0f}–{r.s_end:.0f} m)",
                        evidence=(f"segment time, {int(row['n_configs'])} configurations",),
                        magnitude=mag,
                        magnitude_sigma=sig,
                        unit="s (A − B)",
                        stability=float(row["stability"]),
                    )
                )
            )
        else:
            out.append(
                Claim(
                    Kind.INCONCLUSIVE,
                    _segment_text(r.segment, r.s_start, r.s_end, row["consensus"], a, b),
                    evidence=(f"segment time, {int(row['n_configs'])} configurations",),
                    magnitude=mag,
                    magnitude_sigma=sig,
                    unit="s (A − B)",
                    stability=float(row["stability"]),
                    note=str(row["why"]),
                )
            )

    # --- corner events: observed first, hypotheses only from stable observations ---
    for r in cmp.corners.itertuples():
        ev = _event_row(stab, r.corner)
        out.extend(_event_claims(r, ev, a, b))

    # --- speed trap: one lap-level number, so no stability ----------------------
    st_a, st_b = st_speeds
    if st_a == st_a and st_b == st_b and abs(st_a - st_b) >= 3:
        higher = a if st_a > st_b else b
        out.append(
            Claim(
                Kind.OBSERVED,
                f"{higher} has the higher speed-trap value",
                evidence=("OpenF1 st_speed, one reading per lap",),
                magnitude=st_a - st_b,
                unit="km/h (A − B)",
                stability=None,
            )
        )
        out.append(
            Claim(
                Kind.HYPOTHESIS,
                f"consistent with lower drag, higher deployment, or a slipstream "
                f"benefit for {higher}",
                evidence=(f"speed-trap difference {abs(st_a - st_b):.0f} km/h",),
                confounders=(
                    "active-aero and ERS state (not observed)",
                    "slipstream from the car ahead (gap not computed)",
                    "single speed reading at one point on the lap",
                ),
            )
        )

    # --- track evolution -----------------------------------------------------------
    gap = (lb.t0 - la.t0).total_seconds()
    later = b if gap > 0 else a
    out.append(
        Claim(
            Kind.HYPOTHESIS,
            f"track evolution may bias the comparison towards {later}, which was set "
            f"{abs(gap):.0f} s after the other lap",
            evidence=(f"lap start times differ by {gap:+.1f} s",),
            confounders=TRACK_EVOLUTION,
        )
    )

    for what, why in UNKNOWNS:
        out.append(Claim(Kind.UNKNOWN, what, note=why))
    return out
