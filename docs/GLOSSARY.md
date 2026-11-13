# Glossary

| Term | Meaning in Apex |
|---|---|
| **OBSERVED** | A claim the recorded data shows beyond resolution, stable in at least 80% of analysis configurations. |
| **HYPOTHESIS** | A claim consistent with the data whose cause is not established. Always lists confounders. |
| **INCONCLUSIVE** | A claim within noise or unstable across configurations. |
| **UNKNOWN** | A quantity public data cannot give, with the missing input named. |
| **Stability** | Share of the 81 configurations that agree with the majority verdict for a segment. |
| **Configuration** | One combination of lap pairing, reference set and alignment method. |
| **Pairing** | One choice of lap from driver A and one from driver B. The sensitivity study uses each driver's top 3 laps, giving 9 pairings. |
| **Reference line** | The track centreline used to turn x/y positions into distance around the lap. |
| **Reference set** | The group of laps used to build the reference line. |
| **Alignment** | Matching two laps by distance so speed and time can be compared at the same point on track. |
| **Hybrid alignment** | Apex's default method, combining speed integration and position data. Others are `speed` and `xy`. |
| **Sector anchoring** | Forcing the reconstructed time at the sector lines to match the official sector times. |
| **Delta (Δ)** | Time difference between laps. Convention: Δ = T_A − T_B, so negative means A is faster. See [ADR 0002](decisions/0002-time-delta-convention.md). |
| **Segment** | A stretch of track around a corner (braking, apex, exit) in which a delta is measured. |
| **Corner labels C1…C16** | Apex's own numbering, not official turn numbers. |
| **Validation gate** | Pass/fail test that a lap's reconstructed time agrees with the official time within a 3σ tolerance. |
| **σ (sigma)** | Standard deviation of the estimated error. A difference smaller than 2σ is treated as within noise. |
| **Brownian bridge** | The noise model: distance error is zero at the official timing points and grows between them. |
| **Sign flip** | Some configurations say A is faster beyond noise, others say B. |
| **Push lap** | A lap run at full effort, here a valid lap within 107% of the fastest. |
| **OpenF1** | Open API for F1 timing and telemetry. Apex's primary source. |
| **FastF1** | Python library for F1 data. Needs an F1TV account for live-timing data. |
| **Jolpica** | Successor to the Ergast results API. Used as an independent check on official times. |
| **MODEL OUTPUT** | Reserved tag for simulator results (Phase 4, not built). |
