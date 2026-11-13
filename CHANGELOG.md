# Changelog

## Unreleased (branch `phase-3/uncertainty-claims`, PR #4)

### Added
- Calibrated Brownian-bridge uncertainty model, 81-configuration sensitivity analysis and a four-tag claims engine
  (OBSERVED, HYPOTHESIS, INCONCLUSIVE, UNKNOWN).
- 2025 season stability study (23 of 24 qualifying sessions) and a Spa-Francorchamps follow-up.
- Race-pace inference (`apex pace`): per-driver pace posteriors, pairwise probabilities, held-out calibration checks;
  42 races across 2025 and 2026.
- Full-throttle deceleration detector (`apex ers`) and a 2025 versus 2026 qualifying study.
- Static dashboard (`docs/dashboard/index.html`, no external requests).
- Laps-only and car-only data loaders; `fetch_season.py --laps-only` and `--no-location`.
- Newcomer documentation: README, STATUS, ROADMAP, FAQ, glossary, getting started, methodology sections, CONTRIBUTING,
  issue and PR templates, MIT LICENSE file.
- CI guards: documentation links and anchors, and dashboard freshness.

### Changed
- Case study 01 corrected: the earlier C16 and C7 claims are withdrawn as INCONCLUSIVE.
- `flag_intervals` accepts `end_of_data`; `extract_lap` tolerates sessions without a position stream.

### Fixed
- Corner-zone export now writes fixed 4-decimal tuples; lint error in that change.
- Season study reads and writes UTF-8 explicitly.

### Known limits
- Race-pace forward prediction under-covers (it describes, not forecasts).
- ERS analysis covers qualifying only; attribution to ERS deployment is a hypothesis.
- Baku 2025 qualifying has no lap data in OpenF1.
