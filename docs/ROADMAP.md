# Roadmap

What is left, grouped by who has to act. Last updated 2026-11-13. For what is already built, see [STATUS.md](STATUS.md).

## 1. Needs your decision or action

These are outward-facing or set direction, so they are not done automatically.

| # | Item | Why it matters | State |
|---|---|---|---|
| 1 | **Merge [PR #4](https://github.com/ultramagnus23/Apex_F1/pull/4) into `master`** | Everything built so far lives on `phase-3/uncertainty-claims`. | CI green, mergeable. |
| 2 | **Enable GitHub Pages** (Settings, Pages) | Gives the dashboard a public URL. The page is self-contained (`docs/dashboard/index.html`), so serving the `docs/` folder is enough for it. The mkdocs site has not been built locally (mkdocs is not installed in the dev environment), so treat a full mkdocs deploy as untested. | Not done. |
| 3 | **Pick the next product direction** (section 3) | Decides what gets built next. | Open. |
| 4 | **Tag a release** (for example `v0.2.0`) after the merge | Gives readers a stable point to cite. | Not done. |

## 2. Blocked by things outside this repo

| Item | Blocker |
|---|---|
| Baku 2025 qualifying in the season study | OpenF1 has no lap data for session 9900 (re-checked 2026-11-13). |
| Cross-checking against FastF1 | Needs an F1TV account; Apex never handles credentials. |
| Sessions after the 2026 data cut-off (Las Vegas, Lusail, Abu Dhabi 2026) | They have not happened or are not published yet. Re-run the studies when they appear. |
| Spa 2025 outlier | Narrowed to two rival laps but the cause needs information public data does not hold (traffic, tow). See [VALIDATION §5](VALIDATION.md#5-season-wide-sensitivity-2025). |

## 3. Candidate next builds

Ordered by value for effort. Each one fits the aim: team-grade methods that stay usable by technical analysts.

| Order | Build | What it adds | Effort | Main risk |
|---|---|---|---|---|
| 1 | **Second signal for the ERS hypothesis** | Test whether laps with full-throttle deceleration also show lower speed-trap or intermediate speeds (`i1_speed`, `i2_speed`, `st_speed` are already in the lap data). A consistent second signal would strengthen or weaken the hypothesis with no new downloads. | Small | The signals may be too coarse to separate. |
| 2 | **Traffic-aware race pace** | Ingest OpenF1 gaps to the car ahead and model traffic instead of dropping outlier laps. Fixes the main stated limit of the pace model. | Medium | Gap data may be sparse. |
| 3 | **ERS in races and earlier seasons** | Shows whether the 2026 shift holds in race running and how it compares with 2024 and before. | Medium to large (race car data is big) | Download size; different energy use in races. |
| 4 | **Sprint races and earlier seasons for race pace** | More validation of the calibration claim. | Small | None significant. |
| 5 | **Lap simulator and explicit fuel and stint model** (Phase 5) | Only useful with assumptions public data cannot check. Recommended to defer until items 1 to 3 are done. | Large | Outputs would be mostly assumptions. |
| 6 | **Interactive app** | The static dashboard covers presentation. Revisit only if users need live filtering beyond it. | Large | Maintenance cost. |

## 4. Guards now in CI

Every push checks: lint and format, strict types on `apex/core`, 83 tests, case study 01 reproduction, that every
documentation link and anchor resolves, and that the committed dashboard matches the study outputs.

## Suggested order of work

1. Merge PR #4 and enable Pages (your action).
2. Build item 1 (second ERS signal), because it is cheap and settles how far the ERS claim can go.
3. Build item 2 (traffic-aware pace), because it removes the pace model's main limit.
4. Decide between items 3 and 5 using what items 1 and 2 show.
