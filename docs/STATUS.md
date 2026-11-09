# Project status and roadmap

Last updated: 2026-11-09. Branch `phase-3/uncertainty-claims`.

## Summary

Apex is a research toolkit at **Phase 3 of 5**. It can ingest OpenF1 data, validate laps against
official timing, align and compare laps, estimate uncertainty, stress-test conclusions and tag claims.
It cannot yet simulate laps, model stints or fuel, or present results in an app.

## Done

| Phase | Delivered |
|---|---|
| 0 | Architecture, risk register, three decision records (alignment, delta sign convention, cache policy). |
| 1 | OpenF1 client with immutable raw cache, FastF1 adapter (needs F1TV credentials), data-quality metrics, and a [data contract](DATA_CONTRACT.md) measured from the 2026 US GP qualifying session. |
| 2 | Session container, lap validity engine, reference line, hybrid distance alignment, deltas, validation gate, per-corner metrics, figures, `apex compare` CLI, [case study 01](CASE_STUDY_01.md). |
| 3 | Calibrated Brownian-bridge noise model, 81-configuration sensitivity analysis, claims engine, [85-lap validation](VALIDATION.md), and the [2025 season study](season_2025/README.md) (23 of 24 sessions). |
| Tests | 57 tests (unit, property-based, golden regression) run offline. CI runs lint, strict type-checking of `apex/core`, tests, and a reproducibility check of case study 01. |

## Remaining in Phase 3

- [ ] Open a pull request from `phase-3/uncertainty-claims` into `master`.
- [ ] Retry the Baku 2025 qualifying session. OpenF1 returned no laps for it, so it is recorded as a failure.
- [ ] Investigate Spa-Francorchamps, which has 35 of the 109 sign flips in the season study. Weather and track evolution are untested explanations.
- [ ] Extend the study beyond qualifying (race sessions) and beyond 2025.
- [ ] Regenerate local `out/` outputs (git-ignored) so they no longer say "provisional model".

## Not started

| Phase | Scope | Notes |
|---|---|---|
| 4 | Lap simulator (`apex/sim/`) | Files exist as one-line stubs. Public data has no vehicle parameters, so outputs would be mostly assumptions. Any output would be labelled MODEL OUTPUT. |
| 5 | Fuel and stint modelling (`apex/analysis/stint.py`) | Fuel mass is not in public data, so it would be a configurable assumption. |
| n/a | App or UI (`apex/app/`) | Empty. A static report or notebook gallery may be enough. |
| n/a | `benchmarks/` | Empty. |

## Known gaps

- Sector-line positions are estimated, not published. Their cross-lap scatter (3.1 m) is measured, their absolute position is not.
- Corner event locations (brake-on, lift, pickup) have no independent reference. Only sample-spacing resolution is known.
- FastF1 cross-validation is not possible without F1TV credentials.
- Cause is never established. Telemetry shows differences, not why they occurred.

## Direction under discussion

The strongest result so far is that roughly half of single-session corner conclusions are not stable.
Options for what to do with that (publish it, extend to races and seasons, or build the simulator) are
still open. This file will be updated when a direction is chosen.
