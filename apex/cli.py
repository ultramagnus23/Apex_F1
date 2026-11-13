"""Apex command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from apex import __version__

app = typer.Typer(help="Apex: motorsport performance intelligence.", no_args_is_help=True)
console = Console()


@app.command()
def version() -> None:
    """Print the Apex version."""
    console.print(f"apex {__version__}")


@app.command()
def sources() -> None:
    """Report which data sources are usable in this environment."""
    from apex.core.sources.fastf1_source import has_credentials

    console.print("OpenF1    : available (no auth required for historical data)")
    state = (
        "credentials set"
        if has_credentials()
        else "no F1 account credentials (F1_USERNAME/F1_PASSWORD)"
    )
    console.print(f"FastF1    : {state}")


@app.command()
def compare(
    year: int,
    event: Annotated[str, typer.Argument(help="Circuit/location/country, e.g. Austin")],
    session: Annotated[str, typer.Argument(help="Q, R, SQ, S or full session name")],
    driver_a: str,
    driver_b: str,
    lap_a: Annotated[
        int | None, typer.Option(help="Lap number for A (default: fastest valid)")
    ] = None,
    lap_b: Annotated[
        int | None, typer.Option(help="Lap number for B (default: fastest valid)")
    ] = None,
    phase: Annotated[
        int | None, typer.Option(help="Qualifying phase for default laps (1-3)")
    ] = None,
    method: Annotated[str, typer.Option(help="hybrid | speed | xy")] = "hybrid",
    out: Annotated[Path, typer.Option(help="Output directory")] = Path("out"),
    cache: Annotated[Path, typer.Option(help="OpenF1 cache directory")] = Path("cache/openf1"),
    offline: bool = False,
) -> None:
    """Compare two drivers' laps on distance: deltas, sectors, corners, validation gate."""
    from apex.analysis.compare import compare as run_compare
    from apex.core.laps import classify_laps, fastest_valid
    from apex.core.session import find_session_key, load_openf1
    from apex.report.export import write_comparison

    key = find_session_key(year, event, session, cache, offline=offline)
    with console.status(f"Loading session {key}…"):
        data = load_openf1(key, cache, offline=offline)
    classified = classify_laps(data)
    na, nb = data.driver_number(driver_a), data.driver_number(driver_b)
    la = lap_a or int(fastest_valid(classified, na, phase)["lap_number"])
    lb = lap_b or int(fastest_valid(classified, nb, phase)["lap_number"])
    with console.status("Aligning laps…"):
        cmp = run_compare(
            data,
            (na, la),
            (nb, lb),
            method=method,  # type: ignore[arg-type]
            classified=classified,
        )
    name = f"{year}_{event}_{session}_{driver_a}{la}_vs_{driver_b}{lb}".replace(" ", "_")
    title = (
        f"{year} {data.meta.get('location', event)} {data.meta.get('session_name', session)}: "
        f"{driver_a.upper()} lap {la} vs {driver_b.upper()} lap {lb}"
    )
    path = write_comparison(cmp, data.drivers, out / name, title)

    t = Table(title=title)
    for col in ("Sector", "Official Δ [s]", "Telemetry-only Δ [s]"):
        t.add_column(col, justify="right")
    for r in cmp.sectors.itertuples():
        t.add_row(r.sector, f"{r.official_delta:+.3f}", f"{r.unanchored_delta:+.3f}")
    t.add_row("Lap", f"{cmp.a.tel.lap.lap_duration - cmp.b.tel.lap.lap_duration:+.3f}", "")
    console.print(t)
    for g in cmp.gate:
        console.print(
            f"gate {g.lap_key}: lap z={g.lap_time_z:+.2f}  "
            f"{'[green]PASS' if g.passed else '[red]FAIL'}"
        )
    console.print(f"Wrote {path}")


@app.command()
def pace(
    year: int,
    event: Annotated[str, typer.Argument(help="Circuit/location/country, e.g. Monza")],
    session: Annotated[str, typer.Argument(help="Race or sprint: R or S")] = "R",
    out: Annotated[Path, typer.Option(help="Output directory")] = Path("out"),
    cache: Annotated[Path, typer.Option(help="OpenF1 cache directory")] = Path("cache/openf1"),
    offline: bool = False,
) -> None:
    """Race pace per driver (fuel-, tyre- and stint-adjusted) with credible intervals."""
    import json

    from apex.analysis.pace import codes_for, cross_validate, fit_pace, race_lap_table
    from apex.core.session import find_session_key, load_openf1_laps_only

    key = find_session_key(year, event, session, cache, offline=offline)
    with console.status(f"Loading session {key}…"):
        data = load_openf1_laps_only(key, cache, offline=offline)
    table = race_lap_table(data)
    res = fit_pace(table, codes_for(data), session_key=key)
    check = cross_validate(table, scheme="stint")
    title = f"{year} {data.meta.get('location', event)} {data.meta.get('session_name', session)}"
    t = Table(title=f"{title}: pace on {res.ref_compound}, fresh tyre, lap {res.ref_lap}")
    for col in ("Driver", "Pace [s]", f"{res.ci:.0%} interval [s]", "Clean laps", "Mean rank"):
        t.add_column(col, justify="right")
    for r in res.drivers.itertuples():
        t.add_row(
            r.code,
            f"{r.mean_s:.3f}",
            f"{r.lo_s:.2f} to {r.hi_s:.2f}",
            str(r.n_laps),
            f"{r.rank_mean:.1f}",
        )
    console.print(t)
    for r in res.params.itertuples():
        console.print(
            f"{r.name}: {r.mean:+.3f} {r.unit} ({r.lo:+.3f} to {r.hi:+.3f})  [dim]{r.note}[/dim]"
        )
    if res.status != "OK":
        console.print(f"[red]{res.status}[/red]: " + "; ".join(res.status_reasons))
    console.print(
        f"Check: whole-stint holdout covers {check.coverage:.0%} of laps "
        f"(target {check.nominal:.0%}). Not a forecast: forward prediction is less reliable."
    )
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{year}_{event}_{session}_pace.json".replace(" ", "_")
    path.write_text(json.dumps(res.to_dict(), indent=1, default=float) + "\n", encoding="utf-8")
    console.print(f"Wrote {path}")


@app.command()
def ers(
    year: int,
    event: Annotated[str, typer.Argument(help="Circuit/location/country, e.g. Austin")],
    session: Annotated[str, typer.Argument(help="Q, R, SQ, S or full session name")] = "Q",
    driver: Annotated[str | None, typer.Option(help="Driver code (default: all)")] = None,
    laps_per_driver: Annotated[int, typer.Option(help="Best valid laps per driver")] = 3,
    out: Annotated[Path, typer.Option(help="Output directory")] = Path("out"),
    cache: Annotated[Path, typer.Option(help="OpenF1 cache directory")] = Path("cache/openf1"),
    offline: bool = False,
) -> None:
    """Full-throttle deceleration events (possible ERS clipping) on a driver's best laps."""
    import json

    import pandas as pd

    from apex.analysis.ers import CONFOUNDERS, lap_clipping, repeatability_lift
    from apex.core.laps import classify_laps
    from apex.core.session import find_session_key, load_openf1

    key = find_session_key(year, event, session, cache, offline=offline)
    with console.status(f"Loading session {key}…"):
        data = load_openf1(key, cache, offline=offline)
    classified = classify_laps(data)
    valid = classified[classified["valid"]].sort_values("lap_duration")
    if driver:
        valid = valid[valid["driver_number"] == data.driver_number(driver)]
    best = valid.groupby("driver_number", sort=False).head(laps_per_driver)
    laps, rows = [], []
    for r in best.itertuples():
        try:
            lc = lap_clipping(data, int(r.driver_number), int(r.lap_number))
        except (ValueError, LookupError):
            continue
        laps.append(lc)
        for e in lc.events:
            rows.append(
                {
                    "driver": data.driver_code(lc.driver_number),
                    "lap": lc.lap_number,
                    "lap_position": round(e.frac_start, 3),
                    "onset_kmh": e.v_start_kmh,
                    "lost_kmh": e.speed_lost_kmh,
                    "duration_s": round(e.duration_s, 2),
                    "decel_ms2": round(e.decel_ms2, 2),
                    "decel_se": round(e.decel_se_ms2, 2),
                }
            )
    title = f"{year} {data.meta.get('location', event)} {data.meta.get('session_name', session)}"
    t = Table(title=f"{title}: full-throttle deceleration events")
    for col in ("Driver", "Laps", "Laps with event", "Events/lap", "Clip share"):
        t.add_column(col, justify="right")
    by_driver: dict[int, list] = {}
    for lc in laps:
        by_driver.setdefault(lc.driver_number, []).append(lc)
    for drv, group in by_driver.items():
        share = pd.Series([lc.clip_share for lc in group]).mean()
        t.add_row(
            data.driver_code(drv),
            str(len(group)),
            str(sum(1 for lc in group if lc.events)),
            f"{sum(len(lc.events) for lc in group) / len(group):.2f}",
            f"{share:.1%}",
        )
    console.print(t)
    lift = repeatability_lift(laps)
    console.print(
        f"Repeatability: events repeat at the same place {lift['observed_repeat_rate']:.0%} of the "
        f"time against {lift['chance_repeat_rate']:.0%} by chance (lift {lift['lift']:.1f}x)."
    )
    console.print(
        "[dim]OBSERVED: the speed-trace feature. HYPOTHESIS: that it is electrical deployment "
        "ending. Confounders: " + "; ".join(CONFOUNDERS) + "[/dim]"
    )
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{year}_{event}_{session}_ers.json".replace(" ", "_")
    path.write_text(
        json.dumps({"events": rows, "repeatability": lift}, indent=1) + "\n", encoding="utf-8"
    )
    console.print(f"Wrote {path}")
