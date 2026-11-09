# FAQ

## What is Apex?

An open-source Python toolkit that compares Formula 1 laps using public timing and telemetry data and
reports which differences are real, which are noise, and which cannot be known from public data.

## Who is it for?

People who want to check telemetry-based claims: analysts, writers, researchers and curious fans. It is
a research tool, not a team product, and it has no UI yet.

## What makes it different from other F1 telemetry tools?

Most tools plot two laps and let you draw conclusions. Apex adds three things:

1. **Validation:** each lap is reconstructed from telemetry and checked against official timing.
2. **Uncertainty:** a noise model calibrated on 85 laps gives every difference an error bar.
3. **Stability testing:** each conclusion is recomputed under 81 analysis configurations and only
   called OBSERVED if at least 80% agree.

## Does it tell me why a driver was faster?

No. Telemetry shows differences in speed, braking and throttle. It cannot show intent, setup, tyre
temperature, fuel load, ERS deployment or active-aero state. Apex lists plausible explanations as
HYPOTHESIS with the alternatives, and names the missing inputs as UNKNOWN.

## Why are so many results INCONCLUSIVE?

Because single-lap segment timing noise (about 70 ms) is often larger than the real gap. In the 2025
season study only 52% of conclusions met the 80% stability bar. This is the project's main finding,
not a bug. See [Validation §5](VALIDATION.md#5-season-wide-sensitivity-2025).

## Why not use FastF1 directly?

FastF1 needs an F1TV account for its live-timing data. Apex uses OpenF1 as its primary source because
historical data needs no sign-in. A FastF1 adapter exists, but it refuses to run without credentials.
Apex never handles your credentials. See [Data contract §0](DATA_CONTRACT.md#0-source-availability-blocking-finding).

## Does it work for races?

Not validated. All studies so far use qualifying. Extending to races is on the roadmap.

## Does it predict anything?

No. The lap simulator (Phase 4) is not built, and any simulator output would be labelled MODEL OUTPUT.

## What does a sign flip mean?

A segment where some analysis configurations say driver A is faster beyond the noise and others say B is.
It is the strongest form of instability. Conclusions can also fail by dropping into the noise without
flipping, which is more common.

## Can I trust the numbers?

Check [Validation](VALIDATION.md). Reconstructed lap times match official times with mean error +1.6 ms
and σ 39 ms over 85 laps. The sector-line positions and corner event locations have no independent
reference, and that limit is documented.

## How do I reproduce a result?

Case study 01 runs offline from a committed fixture:
`uv run python examples/case_study_01.py`. CI also checks that it reproduces. See
[Getting started](GETTING_STARTED.md).

## Is the data allowed to be redistributed?

Apex caches data locally and does not commit raw feeds. Review OpenF1 and FastF1's own terms before
redistributing any data. This project is unofficial and not affiliated with Formula 1 companies.

## How can I help?

See [CONTRIBUTING.md](../CONTRIBUTING.md). Good first areas: more sessions in the season study, race
sessions, extra tests, and documentation fixes.
