# Methodology

How Apex turns two laps into distance-domain comparisons, and why each choice was made.
Numbers quoted come from the 2026 United States GP qualifying session (OpenF1 `11392`):
[`docs/data/inspection_11392.json`](data/inspection_11392.json) (raw data) and
[`docs/data/validation_11392.json`](data/validation_11392.json) (85-lap validation study).
See [VALIDATION.md](VALIDATION.md) for results and [DATA_CONTRACT.md](DATA_CONTRACT.md) for
what the raw data is.

Conventions: distance `s` in metres along the **reference line**, from the estimated
timing line. Time `t` in seconds. Delta sign follows ADR 0002:
**Δt(s) = t_A(s) − t_B(s), negative ⇒ A ahead.**

---

## 1. Lap validity (`apex/core/laps.py`)

Every lap gets `valid`, a tuple of **reasons** (exclusions), **warnings** and
**assumptions**. Nothing is dropped silently.

| Reason | Rule | Evidence |
|---|---|---|
| `NO_LAP_TIME` | `lap_duration` or `date_start` null | |
| `PIT_OUT` | `is_pit_out_lap` | its duration includes garage time (contract §3) |
| `PIT_IN` | next lap is a pit-out lap; driver's last lap is treated as an in-lap (**assumption**, recorded) | `/pit.lap_number` = the out-lap's number |
| `DELETED` | race-control deletion matched **by car + quoted time**; fallback `rc_lap − 1` recorded as an assumption | +1 offset measured (contract §4) |
| `SECTOR_MISSING` / `SECTOR_MISMATCH` | any sector null / \|ΣS − lap\| > 1.5 ms (3 × ±0.5 ms rounding) | 192/193 laps within 1 ms |
| `FLAG` | yellow, double yellow, red, SC or VSC active anywhere on track during the lap (conservative: marshal sectors aren't mapped to distance) | |
| `TELEMETRY_GAP` / `POSITION_DROPOUT` | an in-lap car/position gap > 2.5 s, or any `(0,0,0)` position | clean flying laps: max car gap median 0.92 s, p99 1.92 s |
| warning `SENTINEL_WHILE_MOVING` | 104 sentinel while speed > 0. Pedal data missing there, timing unaffected | |

*Push laps* for calibration are valid laps within 107% of the session's fastest valid lap.

## 2. Reference line (`apex/core/track.py`)

1. Take the 10 fastest valid laps' position samples (decimetres → metres, `(0,0,0)` dropped).
2. Project every point onto a seed polyline (the first lap), then average the points along
   arc length with a **Gaussian kernel (σ = 6 m)** onto a uniform grid, periodically padded.
   Repeat 3×, re-projecting onto the new line each time.
3. Re-parameterise by arc length on an **exactly uniform closed grid** (n = round(L/1 m)
   points, so the periodic filters see no short closing segment).
4. Origin s = 0: the median position at the laps' `date_start` instants. That origin
   inherits `date_start`'s ±~0.1 s scatter as a **common** offset: deltas are insensitive
   to it, absolute positions ("brake at 2 104 m") are not.

Result for Austin: **L = 5 417.8 m**. This is the *mean driven line*, not the official
centreline. Points from 10 laps by different drivers sit a median 0.09 m from it, which
suggests OpenF1 positions are map-matched to a track model **[HYPOTHESIS]**. If so, the
lateral position (racing line) isn't observable, only progress along the track.

Projection of a lap's samples is **windowed** (±250 m around a speed-integrated guess) so a
point can't snap onto a nearby part of the circuit.

## 3. Distance alignment (`apex/core/align.py`)

The core problem: the lap boundary in telemetry time is only known to ±~0.1 s
(`date_start`; contract §3). A start error ε moves the distance origin by v₀ε (~8 m), and
the delta error at a corner taken at speed v is ≈ ε(v₀/v − 1), around **0.25 s** in a
slow corner. That's more than the whole pole margin. Anchoring on one noisy instant
doesn't work. Measured alternatives:

| Method | How s is obtained | Lap-time check vs official (85 laps) |
|---|---|---|
| `speed` | ∫v dt from `date_start`, scaled to L | 0.6 ms, **by construction** (no information) |
| `xy` | positions projected onto the line; car samples interpolated | σ 62 ms, bias +26 ms |
| **`hybrid`** (default) | shape from ∫v dt; origin and scale from a robust affine fit s_proj = a + b·∫v dt over all ~370 position samples | **σ 39 ms, bias +1.6 ms** (independent) |

*Why hybrid works:* the speed integral gives a smooth, internally consistent profile. The
position stream gives absolute anchoring, with per-sample noise of ≈5 m that averages down
over the lap. Details:

- Distance from speed uses the **trapezoid rule**. Time-at-distance is its **exact inverse**
  (quadratic within each sample interval), not a linear interpolation.
- Fit: OLS, 3 passes rejecting |r| > 4σ. Covariance of (a, b) is **Newey-West (HAC, 10
  lags)**, because residuals are autocorrelated (ρ ≈ 0.55 at lag 1, 0.3 at lag 10).
- **Stream clocks:** a lag scan (−0.4 … +0.2 s) minimises the residual between −0.05 and
  0 s. Car and position clocks agree to within about ±25 ms, so no lag correction is applied.
- **Scale b = 0.9947 ± 0.0019:** speed-integrated distance runs 0.53% longer than the
  reference line. **[HYPOTHESIS]** wheel-speed overread and/or chord shortening of the
  ~4 Hz position path.
- **Residual structure:** 3.3 m RMS is *systematic* (the same shape on every lap) and 3.1 m
  random. The systematic part is common to all laps and cancels in deltas. It does limit
  absolute positions.

### 3.1 Lap-time constraint (default on)

The official lap time T is exact to 1 ms, far more precise than the fit. (a, b) are
updated by **linearised equality-constrained GLS** so that t(L) − t(0) = T, moving (a, b)
as little as their covariance allows:
θ ← θ − Σ J (JᵀΣJ)⁻¹ g, where g = t(L) − t(0) − T and J = ∂g/∂θ (4 iterations, residual < 1e-13 s).
The pre-constraint mismatch, as a z-score `lap_time_z = g/√(JᵀΣJ)`, is the **lap gate**.

### 3.2 Sector anchoring (default on)

OpenF1 doesn't publish where the sector lines are. For every *other* push lap, Apex finds
the distance at which its telemetry time equals its official S1 (and S1+S2) and takes the
median (**leave-one-out**). Austin: S1 at 1 626 m, S2 at 3 852 m, cross-lap scatter
σ_s ≈ 3.1 m (robust).

The compared lap's distance is then warped **piecewise-linearly** (fixed at 0 and L) so it
crosses each line at its official time. Knot samples are inserted so the exact inverse
stays valid. The **warp size relative to σ_s** is a second gate (`sector_warp_z`).

*Why:* without anchoring, a single lap's sector times carry ~70 ms noise (§ VALIDATION).
In case study 01 that flips the sign of the S1 delta. Official sector times are
observations, and the telemetry should be made consistent with them, with the size of the
correction reported.

## 4. Resampling onto the distance grid

- Grid: **1 m**. Raw samples are 10–20 m apart (4 Hz at 150–300 km/h), so 1 m oversamples
  the data and adds no information. It is used for display and channel comparison only.
  **Time deltas and segment times are computed at exact distances via the exact inverse,
  never read off the grid**, so the grid step doesn't affect any reported time.
- Continuous channels (speed, rpm, throttle): linear (default) or PCHIP (monotone cubic).
  A grid point whose bracketing raw samples include a NaN (sentinel) becomes NaN.
- Discrete channels (gear, brake): **previous-value only**. A fractional gear can't occur.
- Every `AlignedLap` keeps per-sample arrays in one-to-one correspondence with the raw car
  rows (`raw_index`), so every value traces back to a source sample.

## 5. Deltas (`apex/core/delta.py`)

- Cumulative Δt(s) on the grid. **Segment deltas** (sectors, N = 25 equal mini-sectors,
  corner segments) = differences of exact crossing times at the segment ends.
- Lap end: Δt(L) equals the official lap-time difference (exact, by §3.1).
- Sectors: anchored sector deltas equal the official ones (exact, by §3.2). The
  *unanchored* telemetry-only deltas are reported next to them for transparency.

### 5.1 Validation gate and its tolerance

Per lap:
1. **Lap gate:** |`lap_time_z`| ≤ 3.
2. **Sector gate** (unanchored telemetry vs official): |error| ≤ 3σ, where
   σ² = (σ_s/v_start)² + (σ_s/v_end)² + (1 ms/√12)².
   - σ_s = 3.1 m, the measured cross-lap scatter of the sector-line estimates (the
     along-track distance uncertainty of one lap).
   - v is the lap's speed at each line.
   - 1 ms/√12 is the official rounding error.
   - The lap ends are pinned by §3.1 and add nothing.

   For Austin this gives tolerances of 148–240 ms. They are dominated by the **telemetry**
   distance uncertainty; the 1 ms timing resolution is negligible beside it.
3. Anchoring diagnostics: |`sector_warp_z`| ≤ 3.

## 6. Track model and corners

- Curvature κ(s) from **periodic Savitzky-Golay** derivatives (cubic, 60 m window).
  Signed: + = left.
- Corners combine two signals:
  - A **braking** corner is a reference-speed minimum (median of the 20 fastest laps) with
    prominence ≥ 15 km/h and a curvature peak within 80 m.
  - A **flat** corner is a curvature peak (R ≤ 150 m, prominence ≥ half that,
    separation ≥ 80 m) with no such speed minimum.
- The 40–80 m window choice was scanned. Peak sets were stable at 16–18 for R ≤ 150 m,
  while 20–30 m windows produced spurious kinks on straights.
- Austin: **16 corners, 8 braking**.
- Segment boundaries are midpoints between apexes.
- **Numbering:** Apex labels corners `C1…Cn`. Matching official turn numbers needs official
  turn positions, which aren't in the data. `apply_numbering_override` reads a per-circuit
  TOML (`[[turn]] official, s, tolerance_m`). None ships yet, and none will be guessed.

## 7. Per-corner metrics (`apex/analysis/corner.py`)

Events come from **raw samples** and are reported as the interval between the last sample
without the event and the first sample with it. Midpoint = estimate, half-width = resolution.

| Metric | Definition |
|---|---|
| Minimum speed | lowest raw speed sample within ±80 m of the reference apex |
| Brake-on | walking back from the minimum, the off→on transition of `brake` |
| Lift | walking back from the minimum, the last sample with throttle ≥ 95% |
| Throttle pickup | first sample after the minimum with throttle ≥ 20% |
| Entry speed | raw speed at the last brake-off sample |
| Exit speed | **interpolated** at reference apex + 100 m (labelled as not observed) |
| Zone times | braking [B's brake-on, apex − 20 m], apex [±20 m], exit [apex + 20, apex + 100 m], all defined on lap B so both laps are timed over identical distances |

Backward searches are bounded by the previous corner's apex, so one corner's braking is
never attributed to the next.

Resolution is typically **±8–20 m** at ~4 Hz. Brake is on/off only (no pressure), and
throttle is pedal position, not torque. Teams' pedal maps differ, so throttle thresholds
aren't comparable across teams in absolute terms.

## 8. Uncertainty (provisional; Phase 3 replaces it)

Phase 2 attaches a **provisional, conservative** σ to every segment delta. It assumes an
independent σ_s = 3.1 m distance error per lap at each segment end, and zero at pinned
points (lap ends, anchored sector lines): σ_seg² = Σ_laps Σ_ends (σ_s/v)².

Because residuals are positively correlated over hundreds of metres, both ends of a short
segment tend to shift together. **This σ is therefore an upper bound.** A segment is
flagged "within noise" if |Δ| < 2σ. Phase 3 measures stability empirically
(reference-lap, method and bootstrap sensitivity).
