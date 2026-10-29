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
