# ADR 0001: Distance-Based Telemetry Alignment & Interpolation Policy

## Status
Accepted, amended 2026-10-29 (Phase 2)

## Context
Formula 1 timing and telemetry data arrives on two independent, irregular timebases. Measured on OpenF1 (DATA_CONTRACT §1–2): car data (speed, throttle, brake, gear, RPM) at a median **4.17 Hz** on a 40 ms grid, position at a median **3.86 Hz** on a 20 ms grid, sharing only 0.4% of timestamps. *(The original text said ~10 Hz car data; that was not measured and is wrong for this feed.)* Directly comparing Lap A and Lap B on an elapsed time axis $t$ aligns different spatial locations on track, making corner-by-corner analysis impossible.

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

## Amendment (2026-10-29, Phase 2)

Measurement showed that the distance coordinate itself is the dominant error source. The
lap start is only known to ±~0.1 s, which shifts the distance origin by ~8 m and produces
delta errors of ~0.25 s in slow corners. Decisions added:

6. **Distance mapping:** `hybrid` by default. The profile shape comes from integrated
   speed; origin and scale come from a robust affine fit to positions projected onto a
   reference line (HAC covariance). `speed` and `xy` remain available for sensitivity
   studies.
7. **Official timing as constraints:** the official lap time (constrained GLS) and sector
   times (piecewise-linear warp to sector lines estimated leave-one-out) pin the mapping.
   The size of each correction is reported as a z-score gate.
8. **Times are computed at exact distances** via the exact inverse of trapezoid-integrated
   distance. The 1 m grid is for display and channel comparison only, so grid resolution
   no longer affects any reported time (decision 5's sensitivity check is now moot for
   times).
9. Continuous channels may also use PCHIP. Discrete channels stay previous-value only.

See [METHODOLOGY.md](../METHODOLOGY.md) §2–4 and [VALIDATION.md](../VALIDATION.md).
