# Race pace inference

Estimates each driver's race pace from public lap times, adjusted for tyre wear, a shared lap-number
trend and stint effects, and reports it as a **posterior distribution** rather than a single number.

Code: [`apex/analysis/pace.py`](../apex/analysis/pace.py). Study: [`scripts/pace_study.py`](../scripts/pace_study.py).
Results: [`pace_study/`](pace_study/2025/summary.json) and the [dashboard](dashboard/index.html).

## Question it answers

*Which driver was faster in this race when running unimpeded, how sure are we, and what is the chance that
driver A's pace was better than driver B's?*

It does not tell you why, and it does not forecast.

## Model

For each clean lap `i` of driver `d`, stint `k`, compound `c`:

    lap time = pace[d] + stint[d,k] + offset[c] + trend × (lap − L_ref) + degradation[c] × tyre_age + noise

| Term | Meaning |
|---|---|
| `pace[d]` | The quantity of interest: lap time on the reference compound, with a fresh tyre, at mid-race. |
| `stint[d,k]` | A shrunk random effect per stint. It absorbs what a stint shares (fuel mode, setup change, traffic regime), so one stint cannot decide a comparison. |
| `offset[c]` | Compound offset against the most-used compound, at tyre age 0. |
| `trend` | Net lap-number trend. **Fuel burn and track evolution move together and cannot be separated in public data**, so it is reported as one number and never called a fuel effect. |
| `degradation[c]` | Seconds per lap of tyre age, one per compound. |

The posterior is the conjugate Normal-Inverse-Gamma, so it is exact (no sampler). The stint-effect scale is chosen
by marginal likelihood. Outputs are 90% credible intervals and a matrix of `P(driver A's pace is faster than B's)`.

### Which laps are used

A lap is excluded, with a recorded reason, if it is: missing a time, the start lap, a pit in-lap or out-lap, under a
yellow, red, safety-car or virtual-safety-car period (track-wide, so conservative), or an outlier against its stint's
rolling median (traffic, errors, lock-ups). The model therefore describes **unimpeded** pace, which can differ from the
pace a driver showed in traffic.

### When it refuses

A race is marked **NOT MODELLED** if more than 10% of clean laps are on wet-weather tyres, the lap-time noise exceeds
1.5 s, or fewer than 200 clean laps remain. The numbers are still shown for transparency, with a banner.
2025: Melbourne, Silverstone and Spa-Francorchamps. 2026: São Paulo.

## How it was checked

Three held-out tests per race. The score is the share of held-out laps that fall inside the model's 90% predictive
interval (a calibrated model scores about 90%).

| Test | What is held out | 2025 mean (min) | 2026 mean (min) |
|---|---|---|---|
| Random laps | 20% of clean laps | 90% (83%) | 90% (84%) |
| **Whole stints** | 20% of stints, so their stint effect is unseen | **93% (86%)** | **92% (86%)** |
| Forward | Fit the first 80% of the race, predict the rest | 77% (52%) | 81% (67%) |

Races modelled: 21 of 24 (2025) and 17 of 18 (2026). Means are over modelled races.

Reading the result:

- **Calibrated where it matters.** Whole-stint holdout is the test that matches a driver comparison, because it includes
  stint-to-stint variation. It slightly over-covers (93% against 90%), so intervals are on the cautious side.
- **Not a forecast tool.** Predicting the end of a race from its start under-covers (worst 52%), because late-race
  events (strategy, degradation cliffs, restarts) are outside the model. Use it to describe a race that happened.
- **Synthetic recovery.** On simulated races with known truth, the 90% interval holds the true pace 80% to 98% of the
  time (tested in `tests/unit/test_pace.py`), and the trend and degradation are recovered.

Median lap-time noise after adjustment is 0.41 s (2025) and 0.50 s (2026). The median spread between fastest and slowest
driver's pace is 2.0 s (2025) and 4.0 s (2026). Across all driver pairs, 65% (2025) and 76% (2026) are separated with
at least 90% probability.

## Example

`uv run apex pace 2025 Monza R` ranks Norris and Piastri first, with the McLarens clearly ahead of the next group, and
reports a lap-number trend of about −0.06 s per lap. Intervals for neighbouring drivers overlap, and the probability matrix
says so.

## Limits

- Public data has no traffic, fuel mass or tyre temperature. The trend is not a fuel correction.
- Only races with dry running are modelled.
- Forward prediction is unreliable (see above).
- Validated on 2025 and 2026 races only, using OpenF1 lap data.
- The check uses the same data the model is fitted on, so it tests calibration, not agreement with team-internal pace
  estimates, which are not available.

## Reproduce

```bash
uv run python scripts/fetch_season.py --year 2025 --session Race --laps-only
uv run python scripts/pace_study.py --year 2025
```

Race fetches are small (laps, stints, pit stops and race control only).
