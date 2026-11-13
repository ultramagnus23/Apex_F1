# Full-throttle deceleration ("ERS clipping")

Detects stretches where a car decelerates while the throttle is fully open and the brake is off, measures them with
uncertainty, and tests whether they are a real, repeatable feature of the speed trace.

Code: [`apex/analysis/ers.py`](../apex/analysis/ers.py). Study: [`scripts/ers_study.py`](../scripts/ers_study.py).
Results: [`ers_study/`](ers_study/summary.json) and the [dashboard](dashboard/index.html).

## What is claimed and what is not

| Tag | Statement |
|---|---|
| **OBSERVED** | Cars decelerate significantly at full throttle with the brake off, at the same places lap after lap, far more often in 2026 than in 2025. |
| **HYPOTHESIS** | The cause is deployment of stored electrical energy ending (clipping), which the larger electrical share of the 2026 power units would make more common. |
| **UNKNOWN** | Battery state, deployment maps, harvesting, engine mode. None are in public data. |

Confounders that travel with every claim: road gradient, headwind or tailwind, slipstream, engine or fuel mode,
active-aero or DRS state changes, gear-shift transients, and ERS deployment ending (the hypothesis itself).

## Detector

Public car data gives integer km/h speed at irregular intervals (about 0.24 s). For each sample at full throttle
(99% or more, never the feed's 104 missing-value sentinel), with the brake off and above 150 km/h, a local least-squares
slope over ±0.5 s is computed, with a standard error derived from the 1 km/h quantisation. A sample counts only if the
slope is below −0.4 m/s² at the 95% level. Consecutive samples form an event if it lasts at least 0.7 s and loses at
least 3 km/h. Samples within one sample of a gear change are ignored.

Events that end exactly where full throttle ends are **flagged and dropped by default**. They are most likely a
braking onset seen through slightly misaligned throttle, brake and speed channels. On the 2026 Austin laps this removed
about a third of raw events and left the pattern intact.

## How it was checked

| Check | Result |
|---|---|
| Planted a 1.5 m/s² decay in simulated, quantised, irregularly sampled traces | Found in at least 90% of runs; deceleration recovered within 0.5 m/s² |
| False positives on traces that never decelerate | At most 1% |
| Braking, throttle lifts, sentinel values, gear-shift dips | Not counted as events |
| **Repeatability** on real laps | Events repeat at the same lap position far more often than chance. Median lift 14× (2025) and 7.6× (2026) over chance, minimum 6.8× and 3.7× |
| **Concentration** | In 2026, a median 78% of a session's events fall in just 5 of 100 lap-position bins |
| Car-only sessions (no position stream) | Same events as with positions (regression test) |

Repeating at the same places lap after lap, across drivers, is what a real track-and-car feature does and noise does not.

## Era comparison, 2025 against 2026

Qualifying, each driver's best three valid laps. Wet sessions (more than 20% of stints on intermediate or wet tyres)
are excluded from the comparison and listed separately.

| | 2025 | 2026 |
|---|---|---|
| Dry sessions | 22 | 19 |
| Events per lap | 0.27 | 1.23 |
| Laps with at least one event | 17% | 65% |
| Share of full-throttle time decelerating | 0.6% | 5.4% |
| Median deceleration at the event | 1.4 m/s² | 1.6 m/s² |

2026 minus 2025: **+0.96 events per lap** (95% interval +0.49 to +1.51, resampling sessions).

**Same circuit, both years** (16 circuits): 2026 is higher at 14 and equal at 2 (both at zero), never lower
(Wilcoxon p = 0.001). The circuit ranking is similar in both years: Spa-Francorchamps, Silverstone and Suzuka are the
highest, and Monaco, Marina Bay and Budapest are at or near zero in both. That pattern fits high-speed circuits where
power is the limit, but it is a hypothesis; gradient and wind differ by circuit.

The change in median deceleration (+0.3 m/s²) is not distinguishable from zero.

## Limits

- Qualifying only, 2025 and 2026 only. Race running (traffic, tow, different energy use) is not covered.
- The wet-session flag comes from tyre compounds in stint data. A drying track can slip through, so a few high 2025 values
  (Spa, Silverstone) could include reduced-grip running. The paired comparison does not depend on them.
- Speed is quantised to 1 km/h and sampled at about 4 Hz. Short or gentle events are missed, which makes counts a lower
  bound.
- The feature is not an energy measurement. Do not read the share of time as battery use.

## Reproduce

```bash
uv run python scripts/fetch_season.py --year 2025 --session Qualifying --no-location
uv run python scripts/fetch_season.py --year 2026 --session Qualifying --no-location --parquet cache/parquet_2026q
uv run python scripts/ers_study.py --year 2025 --parquet cache/parquet
uv run python scripts/ers_study.py --year 2026 --parquet cache/parquet_2026q
```

The 2025 qualifying cache at `cache/parquet` also contains position data; the study does not need it.
