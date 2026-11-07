# Apex Risk Register & Mitigation Strategy

This document identifies core technical, mathematical, and data-engineering risks inherent in Formula 1 telemetry processing and defines explicit mitigation mechanisms implemented in Apex.

---

## 1. Data Ingestion & Network Risks

| Risk ID | Description | Impact | Probability | Mitigation in Apex |
|---|---|---|---|---|
| **R-NET-01** | Ergast / FastF1 API downtime or rate-limiting. | High | Medium | Persistent local caching (`requests_cache` / FastF1 cache), offline fixture mode, clear error boundaries. |
| **R-NET-02** | Telemetry channel absence in specific sessions. | Medium | High | Channel availability detection, graceful degradation with warnings, typed data quality reporting. |
| **R-DAT-01** | Non-monotonic or duplicate timestamps in raw stream. | High | Medium | Telemetry cleaning pipeline: duplicate deduplication, strict monotonicity enforcement, timestamp sorting. |
| **R-DAT-02** | Irregular sampling rates across distinct CAN channels (e.g. speed vs gear). | High | High | Explicit distance-based resampling grid; discrete channels use zero-order hold (nearest), continuous channels use linear interpolation. |

---

## 2. Mathematical & Alignment Risks

| Risk ID | Description | Impact | Probability | Mitigation in Apex |
|---|---|---|---|---|
| **R-MTH-01** | Arbitrary or inconsistent sign convention for time delta. | High | High | Standardized global convention: $\Delta T(s) = T_A(s) - T_B(s)$. Negative = Lap A is faster (spent less elapsed time). Fixed across CLI, API, UI, and exports. |
| **R-MTH-02** | Telemetry extrapolation past shared lap distance boundaries. | Critical | High | Overlapping domain calculation: $s \in [\max(s_{0,A}, s_{0,B}), \min(s_{\max,A}, s_{\max,B})]$. Rigid rejection of extrapolations. |
| **R-MTH-03** | Conflating official timing duration with numerical telemetry integration. | High | High | Explicit dual validation: compare derived integral duration with official FIA timing sector and lap times, reporting absolute and percentage error. |
| **R-MTH-04** | Discretization errors in numerical time computation. | Medium | Medium | Adaptive resolution testing (1.0m vs 0.5m vs 2.0m) and sensitivity tracking. |

---

## 3. Scientific & Inferential Risks

| Risk ID | Description | Impact | Probability | Mitigation in Apex |
|---|---|---|---|---|
| **R-SCI-01** | Conflating measured speed difference with causal driver intent or setup. | Critical | High | Mandatory claim labels: **OBSERVED**, **HYPOTHESIS**, **UNKNOWN**, **INCONCLUSIVE** (stability below threshold); simulator outputs are additionally labelled **MODEL OUTPUT**. *(Amended 2026-10-29: the earlier OBSERVED/DERIVED/SIMULATED taxonomy is superseded.)* Telemetry identifies differences, not causal explanations. |
| **R-SCI-02** | Simulation assumptions mistaken for real vehicle physics. | Critical | Medium | Simulator isolated in dedicated module; inputs, lateral acceleration caps, and aerodynamic assumptions are documented as idealized longitudinal models. |
| **R-SCI-03** | Single reference lap bias leading to brittle conclusions. | High | Medium | Automated reference lap sensitivity analysis and conclusion stability metrics across candidate reference laps. |

---

## 4. Risks identified in Phases 1–2 (2026-10-29)

| Risk ID | Description | Impact | Probability | Mitigation in Apex |
|---|---|---|---|---|
| **R-SRC-01** | FastF1 livetiming needs an F1TV token (401 otherwise). | High | Certain | OpenF1 primary; FastF1 adapter fails loudly; Jolpica for official times. |
| **R-ALN-01** | Lap boundary in telemetry only ±0.1 s, giving distance-origin error and ~0.25 s spurious deltas in slow corners. | Critical | Certain | Hybrid alignment plus official lap/sector constraints (METHODOLOGY §3). |
| **R-ALN-02** | Single-lap segment timing noise (~70 ms) exceeds many real gaps, so the sign can flip. | Critical | High | Sector anchoring, provisional σ and within-noise flags; Phase 3 stability study. |
| **R-DAT-03** | Race-control lap numbers offset by +1 from OpenF1. | High | Certain | Deletions matched by quoted time. |
| **R-DAT-04** | Positions possibly map-matched, so racing line isn't observable. | Medium | Likely | Never claim lateral-line differences; tagged HYPOTHESIS. |
