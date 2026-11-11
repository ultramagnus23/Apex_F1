# Apex: Motorsport Performance Intelligence

[![CI](https://github.com/ultramagnus23/Apex_F1/actions/workflows/ci.yml/badge.svg)](https://github.com/ultramagnus23/Apex_F1/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Stage: Phase 4 of 5](https://img.shields.io/badge/stage-phase%204%20of%205-orange)

**Apex turns public Formula 1 timing and telemetry into analysis you can reproduce, and it tells you
which conclusions are strong enough to believe.**

Most "driver A gained 0.1 s through turn 7" claims come from comparing two laps. Apex measures how
often such a claim survives when you change the choices behind it (which laps you pair, which
reference line you use, which alignment method). Every output is tagged:

| Tag | Meaning |
|---|---|
| **OBSERVED** | The recorded data shows it, beyond measurement noise, and it is stable across analysis choices (at least 80% of configurations agree). |
| **HYPOTHESIS** | Consistent with the data, but the cause is not established. Alternative explanations are listed. |
| **INCONCLUSIVE** | Within noise, or not stable. It replaces any claim that fails the stability test. |
| **UNKNOWN** | Public data cannot establish it (tyre temperature, fuel, ERS state, setup, driver intent). The missing input is named. |

> Unofficial project. Not associated with Formula 1 companies. Data comes from
> [OpenF1](https://openf1.org) and [FastF1](https://docs.fastf1.dev).

## Two inference products

Apex is aimed at technical readers: analysts, researchers and, if they want them, teams. Teams hold far more data about
their own car, but for rivals they see mostly what the public feed shows. That regime, inference from partial data with
honest uncertainty, is what Apex is built for.

| Product | Question | Result so far |
|---|---|---|
| **[Race pace](docs/RACE_PACE.md)** | How fast was each driver when running unimpeded, how sure are we, and what is the chance A was faster than B? | 42 races (2025 and 2026). Intervals cover 93% of held-out stints against a 90% target. Wet or noisy races are refused. |
| **[ERS clipping](docs/ERS_CLIPPING.md)** | Where, and how often, do cars decelerate at full throttle with the brake off? | 1.23 events per lap in 2026 qualifying against 0.27 in 2025. Higher at 14 of 16 shared circuits, lower at none. Events repeat at the same places lap after lap. |

Both are on the **[dashboard](docs/dashboard/index.html)**. Cause is never claimed: ERS deployment ending is a labelled
hypothesis for the second product.

## Where the project stands

**Phase 4 of 5 is done.** Measurement, uncertainty, claims, race pace, ERS detection and the dashboard work and are
tested. The lap simulator, fuel and stint modelling are not built. See [docs/STATUS.md](docs/STATUS.md) for the full
breakdown.

| Phase | Scope | State |
|---|---|---|
| 0 | Architecture, risk register, decision records | Done |
| 1 | Data layer: OpenF1 client, cache, data contract | Done |
| 2 | Lap validation, distance alignment, deltas, corner metrics, `apex compare` CLI | Done |
| 3 | Calibrated uncertainty, sensitivity analysis, claims engine, 2025 season study | Done |
| 4 | Race-pace inference, ERS clipping detection, studies and dashboard | Done |
| 5 | Lap simulator, fuel and stint modelling (`apex/sim/`, `stint.py`) | Not started (stubs only) |

## Headline findings so far

- **Telemetry alone gets small sector gaps wrong.** In the first case study, telemetry put the S1 gap at the wrong sign.
  Single-lap timing noise is about 70 ms per sector. Apex anchors to official sector times for that reason.
- **Many corner-level differences do not hold up.** Over 23 qualifying sessions of 2025 (1,801 segment conclusions),
  only **52%** reached the 80% stability bar. Sign flips were rare (reference line 0.6%, alignment method 4.3%),
  so the problem is mostly that results fall below the noise level, not that they reverse.
- **Event-level measurements were sturdier than segment times in case study 01.** Brake points and minimum speeds,
  compared against their sample-spacing resolution, survived there while no corner segment did. This has not yet
  been tested across the season.
- **Race-pace intervals are calibrated for driver comparisons.** Holding out whole stints, the 90% intervals contained
  93% of laps in 2025 and 92% in 2026. They are not forecasts: predicting the end of a race from its start under-covers.
- **Full-throttle deceleration is much more common in the 2026 cars.** 65% of 2026 qualifying laps contain at least one
  event against 17% in 2025, and the shift is consistent circuit by circuit.
- **An earlier claim was withdrawn.** Case study 01 originally called one corner difference OBSERVED. Sensitivity
  analysis showed it was not stable, and the page records the correction.

Details: [Case study 01](docs/CASE_STUDY_01.md), [Validation](docs/VALIDATION.md).

## Quick start

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ultramagnus23/Apex_F1.git
cd Apex_F1
uv sync --locked
```

Reproduce case study 01 offline (no network, uses the committed fixture):

```bash
uv run python examples/case_study_01.py
```

Compare two drivers' fastest laps in a session (downloads from OpenF1 on first use, then cached):

```bash
uv run apex compare 2026 Austin Q ANT VER --phase 3
uv run apex pace 2025 Monza R
uv run apex ers 2026 Austin Q
```

More in [Getting started](docs/GETTING_STARTED.md).

## How it works, briefly

1. **Ingest** raw OpenF1 telemetry, positions and lap times, cached byte for byte.
2. **Validate** each lap: reconstruct its time from telemetry and check it against the official time
   (the validation gate).
3. **Align** laps by distance around a reference line, anchored to official sector times.
4. **Compare** to get time deltas and per-corner metrics (brake point, minimum speed, throttle pickup).
5. **Quantify uncertainty** with a noise model calibrated on 85 laps.
6. **Stress-test** each conclusion over 81 configurations (lap pairings, reference sets, alignment methods).
7. **Tag** every statement as OBSERVED, HYPOTHESIS, INCONCLUSIVE or UNKNOWN.

Full detail: [Methodology](docs/METHODOLOGY.md).

## Repository map

| Path | What it holds |
|---|---|
| `apex/core/` | Data sources, sessions, lap validity, alignment, deltas, uncertainty, claims. Type-checked strictly. |
| `apex/analysis/` | Comparison pipeline, corner metrics, sensitivity study, claim building. |
| `apex/report/` | Figures, tables and report export. |
| `apex/analysis/pace.py`, `ers.py` | Race-pace posterior model and the full-throttle deceleration detector. |
| `apex/sim/`, `apex/app/` | Reserved for later phases. Currently empty stubs. |
| `scripts/` | Season fetch and studies (stability, pace, ERS), dashboard builder, session validation, fixture builder. |
| `examples/` | Case study 01, reproducible offline. |
| `tests/` | Unit, property-based and golden regression tests on an offline fixture. |
| `docs/` | Methodology, validation, data contract, case study, decision records, risk register. |

## Documentation

- [Getting started](docs/GETTING_STARTED.md) and [FAQ](docs/FAQ.md)
- [Glossary](docs/GLOSSARY.md)
- [Project status and roadmap](docs/STATUS.md)
- [Methodology](docs/METHODOLOGY.md), [Validation](docs/VALIDATION.md), [Data contract](docs/DATA_CONTRACT.md)
- [Race pace](docs/RACE_PACE.md), [ERS clipping](docs/ERS_CLIPPING.md), [Dashboard](docs/dashboard/index.html)
- [Case study 01](docs/CASE_STUDY_01.md), [2025 season study](docs/season_2025/README.md)
- [Decision records](docs/decisions/) and [risk register](docs/risk_register.md)

## Known limits

- Race pace uses races from 2025 and 2026. ERS analysis uses qualifying from 2025 and 2026. No other seasons or session types.
- FastF1 cross-checking needs F1TV credentials, which the project does not use.
- Sector-line positions and corner event locations have no independent reference.
- Public data does not include tyre temperature, fuel load, ERS state or setup. Apex names these as UNKNOWN
  rather than guessing.

## Contributing

Issues and pull requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
