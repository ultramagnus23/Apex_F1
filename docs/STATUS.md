# Project status and roadmap

Last updated: 2026-11-11. Branch `phase-3/uncertainty-claims`.

## Summary

Apex is a research toolkit at **Phase 4 of 5**. It ingests OpenF1 data, validates laps against official timing,
aligns and compares laps, estimates uncertainty, stress-tests conclusions, tags claims, infers race pace with
posteriors, detects full-throttle deceleration, and presents results on a static dashboard. It cannot yet simulate
laps or model fuel and stints explicitly.

## Done

| Phase | Delivered |
|---|---|
| 0 | Architecture, risk register, three decision records (alignment, delta sign convention, cache policy). |
| 1 | OpenF1 client with immutable raw cache, FastF1 adapter (needs F1TV credentials), data-quality metrics, and a [data contract](DATA_CONTRACT.md) measured from the 2026 US GP qualifying session. |
| 2 | Session container, lap validity engine, reference line, hybrid distance alignment, deltas, validation gate, per-corner metrics, figures, `apex compare` CLI, [case study 01](CASE_STUDY_01.md). |
| 3 | Calibrated Brownian-bridge noise model, 81-configuration sensitivity analysis, claims engine, [85-lap validation](VALIDATION.md), and the [2025 season study](season_2025/README.md) (23 of 24 sessions). |
| 4 | [Race-pace inference](RACE_PACE.md) (42 races, 2025 and 2026), [ERS clipping detection](ERS_CLIPPING.md) (41 dry qualifying sessions, 2025 and 2026), `apex pace` and `apex ers` commands, and the [dashboard](dashboard/index.html). |
| Tests | 83 tests (unit, property-based, golden regression) run offline. CI runs lint, strict type-checking of `apex/core`, tests, and a reproducibility check of case study 01. |

## Open housekeeping

- [x] Pull request open (#4).
- [x] Baku 2025 qualifying re-checked on 2026-11-13: OpenF1 still has no lap data for it. This is an external data gap, recorded as a failure.
- [x] Spa-Francorchamps investigated: not weather, not circuit length; all reference-set flips come from two rival laps. Cause still unknown ([VALIDATION §5](VALIDATION.md#5-season-wide-sensitivity-2025)).
- [x] Race sessions covered by the pace study (2025 and 2026).
- [ ] Extend ERS analysis to race running and to seasons before 2025.
- [x] `out/` is git-ignored local scratch space. It is not part of the repository, so stale files there do not matter.

## Not started

| Phase | Scope | Notes |
|---|---|---|
| 5 | Lap simulator (`apex/sim/`) | Files exist as one-line stubs. Public data has no vehicle parameters, so outputs would be mostly assumptions. Any output would be labelled MODEL OUTPUT. |
| 5 | Explicit fuel and stint modelling (`apex/analysis/stint.py`) | Fuel mass is not in public data, so it would be a configurable assumption. The pace model already absorbs fuel and track evolution in one trend. |
| n/a | Interactive app (`apex/app/`) | Empty. The static dashboard covers presentation for now. |
| n/a | `benchmarks/` | Empty. |

## Known gaps

- Sector-line positions are estimated, not published. Their cross-lap scatter (3.1 m) is measured, their absolute position is not.
- Corner event locations (brake-on, lift, pickup) have no independent reference. Only sample-spacing resolution is known.
- FastF1 cross-validation is not possible without F1TV credentials.
- Cause is never established. Telemetry shows differences, not why they occurred.

## Open questions from the new products

- **Race pace:** forward prediction under-covers (as low as 52% against 90%), so it is a descriptive tool, not a forecast. Traffic is handled only by excluding outlier laps; gaps to the car ahead are not ingested.
- **ERS:** the cause is a hypothesis. Testing it further needs a second signal, for example speed-trap values, or comparison against known energy-management behaviour.
- The wet-session flag for ERS comes from tyre compounds and can miss a drying track.

## Direction

What is left and in what order: [ROADMAP.md](ROADMAP.md).

The aim is team-grade methods that teams can use if they want, packaged for technical analysts. The two products above are the first of these.

## Still to decide

Whether to extend the evidence (race running for ERS, more seasons), build the simulator, or add an interactive app. The
stability finding (about half of single-session corner conclusions are not stable) remains the strongest standalone result.
