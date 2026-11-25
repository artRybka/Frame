"""Command line: run the server, and the updater beside it (Synology)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from .config import Settings

app = typer.Typer(help="Frame: art & photo frame for the Samsung EM32DX.", no_args_is_help=True)


def _settings() -> Settings:
    return Settings.load()


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command()
def serve(
    port: Annotated[int | None, typer.Option(help="Port (default 8099)")] = None,
) -> None:
    """Run the HTTP server (panel content + API)."""
    import uvicorn

    from .web import create_app

    settings = _settings()
    if port:
        settings.port = port
    typer.echo(f"Panel content URL: {settings.base_url()}/panel/content.json")
    uvicorn.run(create_app(settings), host=settings.bind, port=settings.port)


@app.command()
def updater(
    container: Annotated[str, typer.Option(help="The server's container")] = "frame",
    folder: Annotated[Path, typer.Option(help="Shared with the server: its data/update")] = Path(
        "/data/update"
    ),
    replace: Annotated[
        str | None, typer.Option(help="Recreate this container (the updater's own) and exit")
    ] = None,
) -> None:
    """Update the server's container when the app asks (Synology, see
    deploy/synology). Needs the Docker socket."""
    from . import updater as helper

    if replace:
        helper.replace(helper.Docker.connect(), replace)
    else:
        helper.run(folder, container)
