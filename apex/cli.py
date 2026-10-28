"""Apex command-line interface."""

from __future__ import annotations

import typer
from rich.console import Console

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
