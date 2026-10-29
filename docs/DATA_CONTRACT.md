# Data Contract

What Apex's data sources actually deliver, established by inspection, not from memory.

| | |
|---|---|
| Reference session | 2026 United States GP, Qualifying (Austin), OpenF1 `session_key=11392` |
| Inspected on | 2026-10-29 |
| Evidence | [`docs/data/inspection_11392.json`](data/inspection_11392.json), produced by [`scripts/inspect_openf1_session.py`](../scripts/inspect_openf1_session.py) |
| Reproduce | `uv run python scripts/inspect_openf1_session.py --session-key 11392 --season 2026 --round 18 --out docs/data/inspection_11392.json` |
| Versions | fastf1 3.9.0, pandas 2.3.3, numpy 2.3.5 (see `uv.lock`) |

Every number below appears in the evidence JSON. Re-running the script against the warm
cache gives a byte-identical file (checked across numpy 2.5.4 and 2.3.5).

Each statement carries one of these tags:
**[MEASURED]** comes from the evidence JSON. **[CODE]** comes from reading the pinned
library source. **[HYPOTHESIS]** fits the evidence but is not established. **[NOT VERIFIED]**
could not be checked this phase.

---

## 0. Source availability (blocking finding)

**[MEASURED]** `livetiming.formula1.com/static/...` returns **HTTP 401** without an F1
account token. This applies to every session we tried (2024 Italian GP Q, 2025 Abu Dhabi
GP Q, 2026 United States GP Q). FastF1 3.9.0 signs in with `F1_USERNAME` / `F1_PASSWORD`
(F1TV subscription). Without them, `Session.load()` only logs warnings and then raises
`DataNotLoadedError` when you touch `.laps`.

Consequences:

| Source | Auth | Role in Apex |
|---|---|---|
| **OpenF1** `api.openf1.org/v1` (historical) | none needed | **Primary** until FastF1 credentials are available. Raw responses cached byte-for-byte (`apex/core/sources/openf1.py`). |
| **FastF1** (livetiming) | F1TV account | Secondary. Adapter `apex/core/sources/fastf1_source.py` refuses to run without credentials rather than return a half-loaded session. |
| **Jolpica** (Ergast successor) via `fastf1.ergast` | none needed | Independent reference for official Q1/Q2/Q3 times (§6). |

Apex never handles F1 account credentials. Set them in your own shell if you have an
account.

---

## 1. Car data stream: OpenF1 `/car_data`

| Field | Unit | dtype | Observed range | Missing as | Notes |
|---|---|---|---|---|---|
| `date` | ISO-8601 UTC, ms precision | str | 18:37:04.754 → 22:03:58.952 | never null | Stream starts ~2 h 23 min before Q1 (see gaps) |
| `speed` | km/h, **integer** | int64 | 0 – 346 | never null | Resolution 1 km/h ⇒ ±0.14 m/s quantisation |
| `rpm` | rev/min, integer | int64 | 0 – 13 314 | never null | |
| `n_gear` | gear index | int64 | {0 … 8} | never null | 0 = neutral/stationary or no data |
| `throttle` | % | int64 | 0 – 100, plus **104** | never null | 104 is a sentinel, see below |
| `brake` | **binary** | int64 | **{0, 100, 104}** | never null | On/off only, not pressure. 104 is a sentinel |
| `drs` | – | object | **all null** (0 non-null of 372 328 rows) | null | Consistent with 2026 rules replacing DRS with active aero [HYPOTHESIS for the cause]. Expect values in earlier seasons [NOT VERIFIED] |

### Sampling [MEASURED]
- **All 22 cars share one timestamp vector** (`all_drivers_share_identical_timestamps: true`,
  16 924 rows each). The feed is one broadcast clock, not per-car sampling. A car that
  isn't running still gets a row at every tick.
- Intervals sit on a **40 ms grid** (`quantum_s: 0.04`). About 2 % of intervals land 1 ms
  off the grid (0.241, 0.279, 0.281 s).
- **Median 0.240 s (4.17 Hz)**, p5 0.16 s, p95 0.44 s, p99 0.48 s, max 1.00 s (gaps above 1 s excluded).
  Distribution on track: 0.20 s 18.9 %, 0.24 s 16.1 %, 0.16 s 16.0 %, 0.28 s 13.7 %, 0.32 s 9.7 %, …
- No duplicate and no backwards timestamps.
- 36 gaps > 1 s per car in the full stream, the largest being **7 866 s** (18:37 → 20:48).
- **On clean flying laps, gaps above 1 s are normal:** the largest in-lap car gap has a median of 0.92 s and p99 **1.92 s** (≈160 m at speed) over 85 laps (Phase 2 measurement; see §10).
  Within the Q window, 8–39 gaps > 1 s per car (on-track rows only).

> ⚠ ADR 0001 says car data arrives at "~10 Hz". **That is wrong for this feed** (4.17 Hz
> median). ADR 0001 needs amending.

### The 104 sentinel [MEASURED]
- 20–68 % of rows per car have `throttle == 104`. In 99.8 % of those rows `brake == 104`
  as well. A handful of rows have only one of the two at 104 (≤ 2 throttle-only, ≤ 22
  brake-only per car).
- 97.4–100 % of sentinel rows have `speed == 0`. **But 104 also appears while moving:**
  up to 144 rows per car inside the session window (max 263 km/h). Example: RUS at
  21:57:31.8, 144 km/h, 12 444 rpm, gear 2, throttle = brake = 104.
- **[HYPOTHESIS]** 104 means "pedal value not available" (car stationary, in the garage,
  or a dropout). Rule: treat 104 as **missing** in both channels. Never clip it to 100.
  Flag laps that contain sentinel rows while moving.

---

## 2. Position stream: OpenF1 `/location`

| Field | Unit | dtype | Observed range | Missing as |
|---|---|---|---|---|
| `x`, `y` | **decimetres** (1/10 m), circuit frame | int64 | x −2 554 – 15 583, y −4 097 – 6 438 | **(0, 0, 0)** |
| `z` | decimetres (elevation, arbitrary datum) | int64 | 0 – 1 569 (0 only in missing rows) | (0, 0, 0) |

### Units [MEASURED]
Across 91 clean flying laps, XY path length divided by speed-integrated distance (both over
the same time span) gives a **median of 9.957 units/m** (p5 9.925, p95 9.994). Units are
decimetres. The 0.4 % shortfall is **[HYPOTHESIS]** chord-cutting: straight segments
between ~4 Hz position samples undershoot the true arc in corners. Could also be
speed-sensor bias. Phase 2 will separate the two.

### Sampling [MEASURED]
- One shared clock across all cars (17 297 rows each), on a **20 ms grid**.
- **Median 0.259 s (3.86 Hz)**, p5 0.121 s, p95 0.44 s, p99 0.50 s, max 1.00 s.
- **Only 0.40 % of car timestamps also appear in the position stream.** The two streams run
  on independent clocks. Any per-sample combination of position and car channels is
  interpolated, never observed.

### Missing positions [MEASURED]
- 74 516 rows across the session are exactly `(0, 0, 0)`. Inside the session window that's
  1 071–2 242 per car.
- 8–44 of those per car fall where the nearest car sample shows `speed > 0`. So position
  dropouts also happen while moving.
- Rule: `(0,0,0)` is **missing**. Never treat it as a coordinate.

---

## 3. Lap-level data: OpenF1 `/laps`

| Field | Unit | Observed | Missing / quirks |
|---|---|---|---|
| `lap_number` | – | 1 … 20 | Numbering differs from race control, see §4 |
| `date_start` | ISO UTC | | Null for 2 laps (car 11 lap 1, car 77 lap 1) |
| `lap_duration` | s, **whole milliseconds** | | Null on 24 % of pit-out laps. On pit-out laps it **includes garage time** (up to 1 303.7 s) |
| `duration_sector_1/2/3` | s, ms | | S1 null on **93 %** of pit-out laps, never null on other laps |
| `i1_speed`, `i2_speed`, `st_speed` | km/h, integer | i1 140–228, i2 49–192, st 129–341 | |
| `is_pit_out_lap` | bool | 90 of 280 laps | |
| `segments_sector_n` | integer codes | 2048 (3 118), 2049 (2 297), 2064 (441), 2051 (225), 0 (1) | **[NOT VERIFIED]** meaning of codes (mini-sector status). Not used for analysis |

**Not provided by OpenF1 laps:** deleted flag, track-status flag, compound, tyre life,
personal-best flag. Compound and tyre age come from `/stints`. Deletions come only from
race-control free text (§4).

### Internal consistency [MEASURED]
- **Timing resolution: 1 ms.** Every `lap_duration` is a whole number of ms.
- **Sectors sum to the lap time** within 1 ms on 192 of 193 laps that have all three
  sectors. The one exception, car 41 lap 15, has `lap_duration` 465.315 s against a sector
  sum of 113.366 s (in-lap into the garage). Rule: if sectors and lap time disagree by more
  than 1 ms, flag the lap and trust neither.
- **Lap chaining** on normal laps (91 pairs, lap < 110 s, next lap not pit-out):
  `next.date_start − (date_start + lap_duration)` has median −0.038 s, σ 0.082 s,
  range −0.233 … +0.151 s.
  ⇒ **`date_start` is a ~±0.1 s estimate of the line crossing, not the official timing
  instant.** At 300 km/h, 0.1 s is ~8 m. Phase 2 must not cut lap telemetry on
  `date_start` and then claim ms-level agreement. Lap boundaries have to be re-derived
  (e.g. from position crossing the line) and their uncertainty carried forward.

---

## 4. Race control & track status: OpenF1 `/race_control`

- 39 messages. Categories: Other 19, Flag 14, SessionStatus 6. Flags: GREEN 3,
  CLEAR 3, CHEQUERED 3, BLACK AND WHITE 3, DOUBLE YELLOW 1, YELLOW 1.
- Q1/Q2/Q3 windows come from `SessionStatus` messages carrying `qualifying_phase`:
  Q1 21:00:00.095–21:18:00.103, Q2 21:25:00.107–21:40:00.085,
  Q3 21:47:00.092–22:00:00.097 UTC.
- Only 15 % of message timestamps have sub-second precision. Most are whole seconds.
- Yellow flags are **per marshalling sector** (`scope: Sector`, `sector` 1–n). These are
  not the three timing sectors.
- **OpenF1 has no `track_status` endpoint equivalent to FastF1's `TrackStatus`.** SC, VSC
  and red flags have to be reconstructed from race-control flags **[NOT VERIFIED]**: no
  SC/VSC/red occurred in this session.

### Deleted laps and the lap-number offset [MEASURED]
Deletions appear only as free text, e.g.
`CAR 1 (NOR) TIME 1:34.379 DELETED - TRACK LIMITS AT TURN 19 LAP 15 17:01:02`.
For all 6 deletions that quote a time, exactly one OpenF1 lap has that duration, and
**`rc_lap − openf1_lap_number = 1` every time.** The cause is **[NOT VERIFIED]**; the +1 offset
itself is **[MEASURED]** and Phase 2 will re-test it on more sessions. Two `LAP DELETED … (PIT)` messages (car 5) carry no
time and can't be matched by duration.

Rule: match deletions **by car + quoted lap time**, never by lap number alone. Fall back
to `lap_number = rc_lap − 1` only when no time is quoted, and record that as an
assumption.

---

## 5. Weather, stints, pit, results

| Endpoint | Observed |
|---|---|
| `/weather` | 77 samples, **every 60.00 s** (σ 10 ms). air 29.3–29.9 °C, track 36.5–40.7 °C, humidity 37–40.8 %, pressure 1001.6–1001.9 mbar, wind 1.6–5.6 m/s from 117–165°, rainfall always 0. One station for the whole circuit; **not** wind at the car. |
| `/stints` | 90 stints. Compound SOFT 86, MEDIUM 4. `tyre_age_at_start` 0–3 laps. |
| `/pit` | 90 rows. `stop_duration` **always null** (quali, no stationary stop). `pit_duration` = `lane_duration` 24.0–1 178.5 s (includes garage time), null on 24 %. |
| `/session_result` | `duration` and `gap_to_leader` are **lists `[Q1, Q2, Q3]`**. |

---

## 6. Cross-check against official classification [MEASURED]

Reference: Jolpica qualifying results (`fastf1.ergast`, 2026 round 18), which carry the
FIA's Q1/Q2/Q3 times at ms resolution.

| Comparison | Result |
|---|---|
| OpenF1 `session_result.duration[phase]` vs Jolpica Q*n* | **47 / 47 exact** (to the ms) |
| OpenF1 best valid lap per phase (lap started inside the phase window, deletions removed using §4) vs Jolpica Q*n* | **47 / 47 exact** |

This only validates lap totals. Sector times can't be checked against an independent
source here: Jolpica has no sector times.

---

## 7. FastF1: what its code does (not inspected live)

Live FastF1 DataFrames could **not** be inspected (§0). The following comes from reading
the pinned `fastf1==3.9.0` source **[CODE]** and still needs empirical confirmation once
credentials are available:

- `Telemetry._CHANNELS` declares interpolation per channel:
  X/Y/Z/Distance → **quadratic** (`interp1d`, `fill_value="extrapolate"`);
  Speed/RPM/Throttle → linear by index (`limit_direction="both"`);
  Brake/DRS/nGear → discrete, filled by **ffill then bfill**.
- `merge_channels(frequency="original")` (the default) keeps the **union** of car and
  position timestamps and fills every channel at every timestamp. Given §2 (≈0.4 %
  shared timestamps), **almost every X/Y/Z value at a car-data timestamp, and almost every
  Speed value at a position timestamp, is interpolated**, and the quadratic interpolant
  extrapolates at the edges.
- `Brake` is cast to `bool`. **[HYPOTHESIS]** If the livetiming feed has the same 104
  sentinel as OpenF1, FastF1 turns it into `Brake=True` while stationary.
- `calculate_differential_distance` = `Speed/3.6 · Δt` with Δt to the *previous* sample
  (right-endpoint rule). `Distance` is its cumulative sum, so it **integrates speed and is
  not measured**.

To do once FastF1 loads: per-channel diff of FastF1 vs OpenF1 for the same session (same
`date` rows?), check whether 104 exists in FastF1 raw car data, and compare
`Laps.Deleted`/`TrackStatus` with §4.

---

## 8. What public data cannot tell us

| Quantity | Status | What public data gives instead |
|---|---|---|
| Tyre surface / carcass temperature, pressures | **UNKNOWN** | Compound and age in laps (`/stints`) |
| Fuel mass | **UNKNOWN** | None. Must be assumed (Phase 5, configurable) |
| Setup (wing levels, ride height, springs, diff) | **UNKNOWN** | Indirect: top speed / corner speed. Confounded |
| ERS state of charge, deployment, harvesting | **UNKNOWN** | Indirect: speed-trace shape on straights. Heavily confounded in 2026 (larger electrical share) |
| 2026 active-aero mode (low/high-drag state) | **UNKNOWN** | Not in either feed. `drs` is null |
| Brake pressure / pedal travel | **UNKNOWN** | Binary on/off only (§1) |
| Throttle *demand* vs torque delivered | **UNKNOWN** | Pedal % only |
| Steering angle, yaw rate, lateral g | **UNKNOWN** | Lateral accel can be *estimated* from v²·κ (derived, Phase 2) |
| Ride height, kerb strikes, damage | **UNKNOWN** | None |
| Wind at the car | **UNKNOWN** | One trackside station, 60 s cadence |
| Track temperature along the lap | **UNKNOWN** | One sensor, 60 s cadence |
| Exact line-crossing instant per lap from telemetry | **Uncertain ±0.1 s** | `date_start` (§3). Official lap totals are exact to 1 ms |
| Driver intent, engine modes, team instructions | **UNKNOWN** | Team-radio clips (not ingested) |
| Car-to-car aerodynamic effect (tow, dirty air) | **UNKNOWN** | Gap to car ahead can be computed. The effect itself can't |

---

## 9. Rules derived from this contract

1. `throttle == 104` or `brake == 104` → **missing** for that channel. Never clip.
2. `(x, y, z) == (0, 0, 0)` → **missing** position.
3. Car and position streams are independent clocks. Any joined value is **interpolated**
   and must carry a provenance flag.
4. `brake` is binary. Never interpolate it. Use previous-value only.
5. Lap times are exact to 1 ms. Lap *boundaries in telemetry* are only good to ~±0.1 s
   via `date_start`.
6. Deleted laps: match by car + quoted time (§4).
7. Pit-out `lap_duration` includes garage time. Never use it as a lap time.
8. If the sector sum and lap time disagree by more than 1 ms, the lap is invalid for
   timing analysis.

---

## 10. Addendum: measured in Phase 2

Measured on the same session while building alignment
([`validation_11392.json`](data/validation_11392.json), [METHODOLOGY.md](METHODOLOGY.md)).

| Finding | Value | Tag |
|---|---|---|
| Largest in-lap car-data gap, clean flying laps | median 0.92 s, p99 1.92 s | MEASURED |
| `(0,0,0)` positions on clean flying laps | **0** (dropouts happen in the pits/garage) | MEASURED |
| Car vs position stream clock offset | residual minimised between −0.05 and 0 s, i.e. ≤ ~±25 ms | MEASURED |
| Along-track noise of one position sample (after affine fit) | 4.95 m RMS (median lap). 3.3 m is systematic (same on every lap), 3.1 m random. Lag-1 autocorrelation 0.55 | MEASURED |
| Speed-integrated distance vs reference line | 0.53% longer (scale b = 0.9947 ± 0.0019) | MEASURED; cause HYPOTHESIS (wheel-speed overread and/or position chord shortening) |
| Lateral scatter of 10 laps (different drivers) around their mean line | median **0.09 m**, p95 0.64 m | MEASURED. That positions are **map-matched** to a track model is a HYPOTHESIS: real racing lines differ by metres. If true, lateral position (racing line) isn't observable |
| Position-derived line crossing vs `date_start` | crossing is on average 78 ms earlier (σ 67 ms) | MEASURED |
| Line crossing from positions alone, as a lap-boundary estimate | end-crossing residual σ 139 ms: **worse** than `date_start` (σ 82 ms) | MEASURED |
| Single-lap sector time reconstructed from telemetry | σ ≈ 63–79 ms vs official | MEASURED ([VALIDATION](VALIDATION.md)) |
