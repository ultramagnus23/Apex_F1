# Case study 01: 2026 United States GP, Q3: ANT lap 14 vs VER lap 8

**ANT 0.179 s faster than VER; biggest official sector gap S2 (-0.178 s, ANT−VER)**

- Lap A: ANT lap 14, 94.035 s (official)
- Lap B: VER lap 8, 94.214 s (official)
- Alignment: `hybrid`, sector-anchored; reference line 5417.8 m

## Validation gate

| Lap | lap-time z | sector errors before anchoring [ms] | tolerance [ms] | anchor shift [m] (z) | result |
|---|---|---|---|---|---|
| 12:14 | -0.07 | -10, +71, -61 | 148, 229, 174 | -0.5 (-0.16), +3.3 (+1.06) | PASS |
| 3:8 | -0.15 | +51, +14, -65 | 150, 232, 177 | +3.2 (+1.03), +3.5 (+1.12) | PASS |

## Sectors

| Sector | official Δ [s] (OBSERVED) | telemetry-only Δ [s] | anchored Δ [s] |
|---|---|---|---|
| S1 | +0.056 | -0.004 | +0.056 |
| S2 | -0.178 | -0.122 | -0.178 |
| S3 | -0.057 | -0.053 | -0.057 |

## Corner segments (ANT−VER; negative = ANT faster)

| Segment | from–to [m] | Δ [s] | ±2σ [s] | |
|---|---|---|---|---|
| C1 | 0–730 | -0.002 | 0.136 | within noise |
| C2 | 730–970 | -0.066 | 0.093 | within noise |
| C3 | 970–1211 | +0.056 | 0.061 | within noise |
| C4 | 1211–1407 | +0.074 | 0.057 | exceeds 2σ |
| C5 | 1407–1594 | -0.002 | 0.060 | within noise |
| C6 | 1594–1766 | -0.021 | 0.073 | within noise |
| C7 | 1766–1996 | -0.140 | 0.082 | exceeds 2σ |
| C8 | 1996–2332 | -0.038 | 0.081 | within noise |
| C9 | 2332–3125 | +0.031 | 0.088 | within noise |
| C10 | 3125–3830 | -0.009 | 0.079 | within noise |
| C11 | 3830–4078 | -0.078 | 0.090 | within noise |
| C12 | 4078–4366 | -0.103 | 0.084 | exceeds 2σ |
| C13 | 4366–4560 | -0.036 | 0.064 | within noise |
| C14 | 4560–4786 | +0.033 | 0.061 | within noise |
| C15 | 4786–5116 | -0.038 | 0.072 | within noise |
| C16 | 5116–5418 | +0.161 | 0.076 | exceeds 2σ |

## Braking corners (raw-sample events; resolution = half the sample spacing)

| Corner | v_min ANT/VER [km/h] | brake-on Δs [m] (±res) | throttle pickup Δs [m] | exit speed Δ [km/h]* |
|---|---|---|---|---|
| C1 | 84/83 | -15.4 (±20) | – | +10.8 |
| C7 | 147/145 | +43.1 (±12) | – | +6.5 |
| C9 | 75/76 | -7.1 (±15) | -6.1 | +4.3 |
| C10 | 89/88 | +8.1 (±18) | – | +3.8 |
| C11 | 99/98 | -10.4 (±10) | -21.4 | +0.9 |
| C12 | 83/81 | +1.3 (±9) | – | +8.6 |
| C15 | 202/194 | +30.3 (±15) | – | +3.6 |
| C16 | 103/100 | +3.8 (±13) | – | -7.4 |

Δs < 0 means ANT's event happens earlier on track. *Exit speed is interpolated at apex + 100 m, not observed. Corner labels C1… are Apex's own numbering, not official turn numbers.

Uncertainty here is a provisional, conservative model (independent 3 m distance error per lap at each segment end). Phase 3 replaces it with measured stability.
