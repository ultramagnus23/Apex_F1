# Case study 01: tagged claims

Tags: OBSERVED 7, HYPOTHESIS 4, INCONCLUSIVE 24, UNKNOWN 7.

## Observed (data shows it, stable across configurations)

- **OBSERVED** [stability 100%]: ANT set the faster lap (ANT lap 14 vs VER lap 8) (-0.179 ± 0.000 s (A − B))
  - evidence: OpenF1 lap_duration, 1 ms resolution
- **OBSERVED** [stability 100%]: S1 official gap, ANT − VER (+0.056 ± 0.000 s)
  - evidence: OpenF1 sector time, 1 ms resolution
  - note: telemetry-only estimate before anchoring: -0.004 s
- **OBSERVED** [stability 100%]: S2 official gap, ANT − VER (-0.178 ± 0.000 s)
  - evidence: OpenF1 sector time, 1 ms resolution
  - note: telemetry-only estimate before anchoring: -0.122 s
- **OBSERVED** [stability 100%]: S3 official gap, ANT − VER (-0.057 ± 0.000 s)
  - evidence: OpenF1 sector time, 1 ms resolution
  - note: telemetry-only estimate before anchoring: -0.053 s
- **OBSERVED** [stability 81%]: ANT reaches 20% throttle earlier after the apex of C11 by 21 m (-21.399 ± 5.486 m (A − B))
  - evidence: raw-sample event, resolution ±5 m
- **OBSERVED** [stability 89%]: VER brakes earlier into C15 by 30 m (+30.314 ± 15.459 m (A − B))
  - evidence: raw-sample event, resolution ±15 m
- **OBSERVED** [stability 100%]: VER has the lower minimum speed through C15 (+8.000 km/h (A − B))
  - evidence: minimum raw speed differs by 8 km/h (raw samples)

## Hypotheses (consistent with the data; not established)

- **HYPOTHESIS**: ANT's earlier throttle pickup at C11 is consistent with earlier traction
  - evidence: throttle pickup difference -21 m
  - could also explain this: pedal-to-torque maps differ between power units; equal pedal % is not equal torque; exit speed and corner-exit line; driver throttle-modulation style
- **HYPOTHESIS**: consistent with a deliberate earlier brake point into C15 by VER
  - evidence: brake onset difference +30 m
  - could also explain this: entry line and corner-entry speed (lateral position is not observable); brake-pressure and on/off sampling at ~4 Hz (brake is binary here); tyre age and compound (both laps on the same compound in this case); traffic or a tow from the car ahead (gap not computed in this version)
- **HYPOTHESIS**: VER carries less speed through C15; the cause is not established
  - evidence: minimum speed difference +8 km/h
  - could also explain this: racing line through the apex; traffic or a tow on the approach; tyre temperature and grip (not observed)
- **HYPOTHESIS**: track evolution may bias the comparison towards VER, which was set 8 s after the other lap
  - evidence: lap start times differ by +7.8 s
  - could also explain this: the grip level of the track changes over a session; the later lap may benefit

## Inconclusive (within noise, or not stable)

- **INCONCLUSIVE** [stability 93%]: C1 (0–730 m): no reliable difference (+0.019 ± 0.070 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 64%]: C2 (730–970 m): no reliable difference (-0.074 ± 0.048 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 62%]: C3 (970–1211 m): no reliable difference (+0.053 ± 0.031 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 56%]: C4 (1211–1407 m): no reliable difference (+0.055 ± 0.029 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 63%]: C5 (1407–1594 m): no reliable difference (-0.011 ± 0.030 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 80%]: C6 (1594–1766 m): no reliable difference (-0.005 ± 0.037 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 64%]: C7 (1766–1996 m): ANT is usually faster, but not stably enough to claim (-0.125 ± 0.042 s (A − B))
  - evidence: segment time, 81 configurations
  - note: verdict flips across configurations (stability 64%)
- **INCONCLUSIVE** [stability 89%]: C8 (1996–2332 m): no reliable difference (-0.039 ± 0.041 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 56%]: C9 (2332–3125 m): no reliable difference (-0.047 ± 0.044 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 65%]: C10 (3125–3830 m): no reliable difference (-0.079 ± 0.039 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 89%]: C11 (3830–4078 m): no reliable difference (-0.033 ± 0.045 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 48%]: C12 (4078–4366 m): no reliable difference (-0.039 ± 0.042 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 89%]: C13 (4366–4560 m): no reliable difference (-0.029 ± 0.032 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 85%]: C14 (4560–4786 m): no reliable difference (+0.032 ± 0.031 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 81%]: C15 (4786–5116 m): no reliable difference (-0.021 ± 0.036 s (A − B))
  - evidence: segment time, 81 configurations
  - note: within 2 sigma noise in most configurations
- **INCONCLUSIVE** [stability 52%]: C16 (5116–5418 m): VER is usually faster, but not stably enough to claim (+0.068 ± 0.038 s (A − B))
  - evidence: segment time, 81 configurations
  - note: verdict flips across configurations (stability 52%)
- **INCONCLUSIVE** [stability 68%]: VER has the lower minimum speed through C2 (+18.000 km/h (A − B))
  - evidence: minimum raw speed differs by 18 km/h (raw samples)
  - note: downgraded from OBSERVED: stability 68% < 80%
- **INCONCLUSIVE** [stability 7%]: ANT has the lower minimum speed through C3 (-5.000 km/h (A − B))
  - evidence: minimum raw speed differs by 5 km/h (raw samples)
  - note: downgraded from OBSERVED: stability 7% < 80%
- **INCONCLUSIVE** [stability 73%]: ANT has the lower minimum speed through C4 (-11.000 km/h (A − B))
  - evidence: minimum raw speed differs by 11 km/h (raw samples)
  - note: downgraded from OBSERVED: stability 73% < 80%
- **INCONCLUSIVE** [stability 41%]: VER brakes earlier into C7 by 43 m (+43.121 ± 12.221 m (A − B))
  - evidence: raw-sample event, resolution ±12 m
  - note: downgraded from OBSERVED: stability 41% < 80%
- **INCONCLUSIVE** [stability 70%]: ANT reaches 20% throttle earlier after the apex of C9 by 6 m (-6.092 ± 4.578 m (A − B))
  - evidence: raw-sample event, resolution ±5 m
  - note: downgraded from OBSERVED: stability 70% < 80%
- **INCONCLUSIVE** [stability 48%]: ANT brakes earlier into C11 by 10 m (-10.373 ± 10.242 m (A − B))
  - evidence: raw-sample event, resolution ±10 m
  - note: downgraded from OBSERVED: stability 48% < 80%
- **INCONCLUSIVE** [stability 78%]: VER has the lower minimum speed through C14 (+6.000 km/h (A − B))
  - evidence: minimum raw speed differs by 6 km/h (raw samples)
  - note: downgraded from OBSERVED: stability 78% < 80%
- **INCONCLUSIVE** [stability 33%]: VER has the lower minimum speed through C16 (+3.000 km/h (A − B))
  - evidence: minimum raw speed differs by 3 km/h (raw samples)
  - note: downgraded from OBSERVED: stability 33% < 80%

## Unknown (public data cannot establish this)

- **UNKNOWN**: Tyre surface and carcass temperatures and pressures
  - note: not in either feed
- **UNKNOWN**: Fuel mass
  - note: not in either feed; a configurable assumption in Phase 5
- **UNKNOWN**: ERS state of charge and deployment
  - note: not in either feed
- **UNKNOWN**: Active-aero mode and wing levels
  - note: not in either feed; drs channel is empty in 2026
- **UNKNOWN**: Car setup (ride height, springs, diff, brake balance)
  - note: not in either feed
- **UNKNOWN**: Driver intent and team instructions
  - note: not in either feed
- **UNKNOWN**: Slipstream and dirty air
  - note: gap to the car ahead is not computed in this version

