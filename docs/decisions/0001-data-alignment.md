# ADR 0001: Distance-Based Telemetry Alignment & Interpolation Policy

## Status
Accepted

## Context
Formula 1 timing and telemetry data emitted from cars arrives on disparate timebases and irregular sampling intervals depending on the CAN bus channel (e.g., speed and throttle at ~10 Hz, GPS position at ~4 Hz). Directly comparing Lap A and Lap B on an elapsed time axis $t$ aligns different spatial locations on track, making corner-by-corner analysis impossible.

## Decision
1. **Primary Coordinate**: Apex aligns telemetry on the **Distance along lap** coordinate $s \in [0, S_{\max}]$.
2. **Overlapping Domain**: The shared evaluation grid $s_{\text{grid}}$ is strictly restricted to the valid intersection:
   $$s \in [\max(s_{0,A}, s_{0,B}), \min(s_{\max,A}, s_{\max,B})]$$
   Extrapolation outside this interval is strictly disallowed.
3. **Continuous Channels**: Speed, Throttle, RPM, and cumulative elapsed time are interpolated onto the regular grid using 1D piecewise linear interpolation.
4. **Discrete / Categorical Channels**: Gear and binary Brake status are resampled using zero-order hold (nearest / step interpolation) to prevent synthetic fractional gears (e.g., gear 5.4).
5. **Grid Resolution**: The default grid resolution is $\Delta s = 1.0\text{ m}$. Robustness checks evaluate sensitivity against alternate resolutions (e.g., $0.5\text{ m}$ and $2.0\text{ m}$).

## Consequences
- Enables spatially synchronized delta and trace comparisons across corners and straights.
- Does not imply identical environmental or vehicle states at identical spatial locations.
- Interpolation introduces minor discretization error, which is audited in the official timing validation report.
