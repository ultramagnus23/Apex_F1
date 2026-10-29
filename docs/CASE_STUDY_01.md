# Case study 01: where was pole won?

**2026 United States GP qualifying, Q3: Antonelli (ANT, lap 14, 94.035 s, pole) vs
Verstappen (VER, lap 8, 94.214 s, P2).**

Reproduce offline from the committed fixture: `uv run python examples/case_study_01.py`
(outputs in [`docs/case_study_01/`](case_study_01/)), or from the live cache:
`uv run apex compare 2026 Austin Q ANT VER --phase 3`.

Every statement is tagged:
- **OBSERVED**: recorded data, beyond its stated resolution.
- **HYPOTHESIS**: consistent with the data, not established.
- **INCONCLUSIVE**: a difference exists but is within measurement noise.
- **UNKNOWN**: can't be established from public data.

Phase 3 will generate these tags automatically. Here they were applied by hand under the
same rules.

![Overlay](case_study_01/overlay.png)

## 1. Validation first

| Lap | lap-time z | sector error before anchoring [ms] | tolerance [ms] | anchor shift [m] (z) | gate |
|---|---|---|---|---|---|
| ANT 14 | −0.07 | −10 / +71 / −61 | 148 / 229 / 174 | −0.5 (−0.16), +3.3 (+1.06) | **PASS** |
| VER 8 | −0.15 | +51 / +14 / −65 | 150 / 232 / 177 | +3.2 (+1.03), +3.5 (+1.12) | **PASS** |

Both laps' telemetry is consistent with their official lap and sector times within the
stated tolerance ([METHODOLOGY §5.1](METHODOLOGY.md#51-validation-gate-and-its-tolerance)).
After anchoring, the analysis reproduces the official lap gap (−0.179 s) and all three
official sector gaps exactly.

## 2. What the data says

| # | Tag | Statement |
|---|---|---|
| 1 | OBSERVED | ANT's lap was **0.179 s** faster (official). |
| 2 | OBSERVED | By sector (official, ANT − VER): **S1 +0.056 s**, **S2 −0.178 s**, **S3 −0.057 s**. ANT lost time in S1 and won pole in S2. |
| 3 | OBSERVED (method finding) | From telemetry alone, without official sector anchoring, S1 reads −0.004 s: the **wrong sign**. Single-lap telemetry noise (~70 ms per sector, [VALIDATION §2](VALIDATION.md)) exceeds this sector's real gap. That is why Apex anchors to official sector times. |
| 4 | INCONCLUSIVE | Where in S2 the 0.178 s came from. No single corner segment in S2 exceeds 2σ. The largest is C7 (−0.140 ± 0.223 s, 2σ). The gain is spread across S2 or concentrated somewhere the 4 Hz feed can't resolve. |
| 5 | OBSERVED | One segment exceeds 2σ: **C16 (final corner to the line), ANT +0.161 ± 0.132 s (2σ) slower**. Official S3 is still −0.057 s in ANT's favour, so ANT gained back elsewhere in S3 (individually within noise). |
| 6 | OBSERVED | Into **C7**, ANT's brake-on comes **43 m later** than VER's (event resolution ±12 m). Into **C15**, 30 m later (±15 m, marginal). |
| 7 | HYPOTHESIS | Claim 6 at C7 is consistent with part of ANT's S2 advantage (C7 segment −0.140 s). Confounders: different entry lines (lateral position isn't observable, see METHODOLOGY §2), brake-signal sampling (on/off at ~4 Hz), different braking-zone speeds from a different C6 exit. |
| 8 | OBSERVED | ANT's throttle pickup (first sample ≥ 20% after the minimum) comes **earlier in 6 of 8 braking corners**, by 10–27 m. In 4 of them (C1, C10, C11, C12) it is a genuine throttle event, earlier by 10–22 m against a resolution of ±2–6 m. In C7 and C15, throttle was already ≥ 20% at the minimum-speed sample, so there the difference only reflects where the speed minimum fell. C9 and C16 are within resolution. |
| 9 | HYPOTHESIS | Claim 8 *could* reflect earlier traction or a different corner-exit approach. **Strong confounder:** throttle is *pedal* position, and pedal-to-torque maps differ between teams (Mercedes vs Red Bull power units). Equal pedal % doesn't mean equal torque. |
| 10 | OBSERVED | Minimum speeds in braking corners agree within 1–3 km/h, except C15 (ANT +8 km/h). These are raw-sample minima at ~4 Hz; the true minimum can be lower than any sample. |
| 11 | OBSERVED | Speed traps: ANT 328 vs VER 326 km/h (st), i1 equal (226), i2 184 vs 183. |
| 12 | OBSERVED | Same compound and age: both on **new SOFTs**, first push lap of the stint. Both laps started on the same Q3 run, **7.8 s apart** (ANT first). Track evolution between them is negligible, and 7.8 s is too far for a tow. |
| 13 | UNKNOWN | Tyre temperatures and pressures, fuel load, ERS state of charge and deployment, active-aero mode, setup, and driver intent. Any of these could drive claims 5–10, and none is in the public data ([DATA_CONTRACT §8](DATA_CONTRACT.md#8-what-public-data-cannot-tell-us)). |

![Corner segments](case_study_01/corners.png)

## 3. What this case study shows about the method

- **Official timing is the strongest signal.** It shows pole was won in S2 (−0.178 s) after
  a loss in S1 (+0.056 s). Telemetry alone can't even get the sign of S1 right.
- **Corner-level attribution is mostly below the noise floor** of a 4 Hz public feed: 15 of
  16 corner segments are within the provisional ±2σ. The provisional σ is an upper bound
  ([METHODOLOGY §8](METHODOLOGY.md#8-uncertainty-provisional-phase-3-replaces-it)), so
  Phase 3's measured stability may resolve more, or may not.
- **Event locations are more robust than segment times.** Brake points and throttle pickups
  carry explicit sample-spacing resolution. Several differences exceed it.

## Outputs

[`summary.md`](case_study_01/summary.md) · [`sectors.csv`](case_study_01/sectors.csv) ·
[`minisectors.csv`](case_study_01/minisectors.csv) ·
[`corner_segments.csv`](case_study_01/corner_segments.csv) ·
[`corners.csv`](case_study_01/corners.csv) · [`gate.json`](case_study_01/gate.json)

Corner labels `C1…C16` are Apex's numbering, **not** official turn numbers (METHODOLOGY §6).
