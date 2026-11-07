# Validation

How we know the numbers are right, and where they stop being right.

| | |
|---|---|
| Session | 2026 United States GP qualifying, OpenF1 `11392` |
| Laps | **85** valid push laps (≤ 107% of the fastest valid lap), 22 drivers |
| Evidence | [`docs/data/validation_11392.json`](data/validation_11392.json) |
| Reproduce | `uv run python scripts/validate_session.py --session-key 11392 --out docs/data/validation_11392.json` |
| Official reference | OpenF1 lap and sector times. Lap totals were cross-checked 47/47 exact against Jolpica (DATA_CONTRACT §6) |

Each lap is validated against sector lines estimated from the **other 84 laps**
(leave-one-out), so no lap calibrates its own test.

## 1. Lap times reconstructed from telemetry

Hybrid alignment, **before** the lap-time constraint (an independent reconstruction):

| | value |
|---|---|
| error vs official, mean | **+1.6 ms** |
| error, σ | **39.3 ms** |
| error, 5–95% | −52 … +66 ms |
| model-predicted σ (median) | 35.4 ms |
| z = error / predicted σ | mean 0.15, **σ 1.23** |
| \|z\| > 3 | 3 / 85 |

The telemetry agrees with official timing without bias. The noise model underestimates the
real scatter by ~23% (z-spread 1.23 instead of 1.0) and has heavier tails.

## 2. Sector times reconstructed from telemetry (before sector anchoring)

Error = telemetry − official, ms (mean / σ / 5% / 95%):

| Method | S1 | S2 | S3 |
|---|---|---|---|
| **hybrid** | +5 / 73 / −81 / +108 | −9 / 79 / −115 / +114 | +3 / 63 / −79 / +116 |
| speed | +10 / 76 / −77 / +124 | +1 / 78 / −112 / +125 | −12 / 70 / −101 / +112 |
| xy | **−98** / 58 / −196 / −12 | **−55** / 58 / −156 / +36 | **+181** / 67 / +63 / +283 |

**The key limitation:** from this public ~4 Hz feed, a single lap's time at a given track
position is known to about **±70 ms (1σ)**, roughly ±0.11 s at 95%. That's the
measurement floor for any segment-level claim.

`xy` has less scatter but large, sector-dependent bias. A bias common to both laps cancels
in a delta, so `xy` may be competitive for deltas. Phase 3's method-sensitivity study will
decide that rather than assume it.

## 3. Gate outcome (3σ tolerance; [METHODOLOGY §5.1](METHODOLOGY.md#51-validation-gate-and-its-tolerance))

| | laps |
|---|---|
| lap gate pass (\|z\| ≤ 3) | 82 / 85 |
| sector gate pass | 80 / 85 |
| **both** | **77 / 85 (91%)** |
| sector anchoring corrections with \|z\| > 3 | 4 of 170 sector lines |
| after anchoring: max \|sector error\| | 4 × 10⁻¹⁴ s (exact by construction) |

A calibrated 3σ gate would pass ~99%. 91% is consistent with the ~23% under-estimate in §1.
The tolerance is **not** retuned to make more laps pass. Failing laps are flagged in every
output. Failures:

| lap | lap z | S1 / S2 / S3 error [ms] |
|---|---|---|
| 77:2 | +4.47 | +10 / −132 / +121 |
| 11:2 | +3.16 | −5 / −113 / +118 |
| 44:2 | +3.01 | −5 / −48 / +53 |
| 6:2 | +2.29 | +109 / −264 / +155 |
| 30:2 | +0.15 | +390 / −279 / −111 |
| 41:8 | +0.54 | +194 / −153 / −41 |
| 11:5 | −0.56 | −196 / +89 / +107 |
| 1:11 | −0.67 | +35 / +164 / −199 |

**Observation:** 5 of the 8 failures are **lap 2**, the first flying lap of Q1. Reference
line and sector lines are built mostly from later (Q2/Q3) laps. Track evolution, different
lines on a green track, or early-session feed behaviour could each explain it
**[HYPOTHESIS, untested]**. To investigate in Phase 3.

## 4. Numerical correctness (tests)

| Property | Test |
|---|---|
| Exact trapezoid inverse: t(s) recovers t to 1e-12 s under constant acceleration | `tests/unit/test_align.py` |
| `speed` method reproduces lap time by construction (< 2 ms) | unit |
| Lap-time constraint exact (< 1e-9 s); anchored sector crossings exact (< 1e-6 s) | unit, on real data |
| Discrete channels never fractional; sentinel NaN poisons only neighbouring grid points | unit |
| Curvature of a circle = 1/R (≤ 0.1%); projection onto a circle exact | `tests/unit/test_track.py` |
| Windowed projection doesn't jump to a parallel straight 10 m away | unit |
| Δ(A,A) = 0; Δ(A,B) = −Δ(B,A); Δ(L) = lap-time difference | `tests/property` (Hypothesis) |
| Resample → integrate 1/v preserves lap time (< 0.2%) | property |
| Corner detection stable under speed/curvature noise | property |
| Case study 01 numbers frozen | `tests/regression` (golden, 1e-9) |

## 5. Season-wide sensitivity (2025)

`scripts/season_study.py` compares the pole driver's fastest valid lap with P2 and P3 in every
2025 qualifying session, under all reference sets and alignment methods
([METHODOLOGY §9.4](METHODOLOGY.md#94-season-study-scriptsseason_studypy)). Results are in
[`season_2025/`](season_2025/).

- **Coverage:** 23 of 24 sessions. Baku failed because OpenF1 has no lap data for session 9900.
- **Conclusions judged:** 1,801 segment conclusions (non-"none" majority verdict).
- **Sign flips** (A faster in one configuration, B in another):

| Choice varied | Conclusions that flip |
|---|---|
| Reference set (method fixed) | 0.6% (10) |
| Alignment method (reference fixed) | 4.3% (77) |
| Either | 6.1% (109) |

- **Stability:** median 100%, mean 83%. Only 52% of conclusions reach the 80% OBSERVED threshold,
  so about half of the segment verdicts would be downgraded to INCONCLUSIVE.
- **Concentration:** all 10 reference-set flips and 35 of the 109 flips overall are at
  Spa-Francorchamps. Jeddah, Montreal, Austin, Mexico City, Las Vegas and Yas Island have no
  flips. **[HYPOTHESIS, untested]** that Spa's changing conditions across its long lap explain
  this; no weather or track-evolution analysis has been done.
- **Reading:** the choice of reference line almost never changes the sign. The alignment method
  does, so the method must stay part of the stability test.

Limits: one season, one session type, and only the pole driver against P2 and P3.

## 6. What is *not* validated

- **Sector-line positions** are estimated, not published. Their cross-lap scatter (3.1 m)
  is measured; their absolute position isn't.
- **Corner event locations** (brake-on, lift, pickup) have no independent reference.
  Only their sample-spacing resolution is known.
- **FastF1 comparison:** not possible without F1TV credentials (DATA_CONTRACT §0).
- The season study covers 2025 qualifying only, and Baku is missing.
