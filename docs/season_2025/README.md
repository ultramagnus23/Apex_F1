# 2025 season study

Question: how often does a segment-level conclusion change when the analysis choices change?

## Method

For each 2025 qualifying session, the pole driver's fastest valid laps are compared with the P2 and P3
drivers. Every comparison runs under 81 configurations (lap pairings, reference-line sets, alignment
methods). A conclusion is any segment whose majority verdict is not "none". It **flips** if some
configurations say A is faster beyond noise and others say B is. Full definition:
[METHODOLOGY §9](../METHODOLOGY.md#9-phase-3-calibrated-uncertainty-sensitivity-and-claims).

Reproduce:

```bash
uv run python scripts/fetch_season.py --year 2025 --session Qualifying
uv run python scripts/season_study.py --year 2025
```

## Results

| | |
|---|---|
| Sessions studied | 23 of 24 (Baku: OpenF1 has no laps for session 9900) |
| Conclusions judged | 1,801 |
| Flip with reference set (method fixed) | 0.6% (10) |
| Flip with alignment method (reference fixed) | 4.3% (77) |
| Flip with either | 6.1% (109) |
| Stability, median / mean | 100% / 83% |
| Reach the 80% OBSERVED bar | 52% |

Spa-Francorchamps accounts for all 10 reference-set flips and 35 of the 109 overall. Jeddah, Montreal,
Austin, Mexico City, Las Vegas and Yas Island have none. The explanation for Spa is a hypothesis
(changing conditions) that has not been tested.

Interpretation and limits: [VALIDATION §5](../VALIDATION.md#5-season-wide-sensitivity-2025).

## Files

| File | Contents |
|---|---|
| `summary.json` | Overall rates, failed sessions, rates by consensus driver. |
| `per_session.csv` | One row per session: conclusions and flip counts. |
| `conclusion_flips.csv` | One row per judged segment: consensus verdict, stability, which choices flip it. |
