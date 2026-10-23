"""Command line: run the server, render images, drive the panel for experiments."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated

import typer

from .config import Settings
from .imaging import PRESETS, RenderSettings, Strategy, get_palette, render

app = typer.Typer(help="Frame: art & photo frame for the Samsung EM32DX.", no_args_is_help=True)
device_app = typer.Typer(help="Talk to the panel over MDC.", no_args_is_help=True)
app.add_typer(device_app, name="device")

PresetOpt = Annotated[str, typer.Option("--preset", "-p", help=f"One of {list(PRESETS)}")]
StrategyOpt = Annotated[Strategy | None, typer.Option("--strategy", "-s")]
SetOpt = Annotated[
    list[str] | None,
    typer.Option("--set", help="Override a render setting, e.g. --set tone.gamma=1.2"),
]


def _settings() -> Settings:
    return Settings.load()


def _parse_value(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def build_render_settings(
    preset: str, strategy: Strategy | None, overrides: list[str] | None
) -> RenderSettings:
    if preset not in PRESETS:
        raise typer.BadParameter(f"unknown preset {preset!r}, choose from {list(PRESETS)}")
    data = PRESETS[preset].model_dump(mode="json")
    for item in overrides or []:
        key, _, value = item.partition("=")
        if not _:
            raise typer.BadParameter(f"--set expects key=value, got {item!r}")
        node = data
        *parents, leaf = key.split(".")
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = _parse_value(value)
    settings = RenderSettings.model_validate(data)
    if strategy is not None:
        settings.strategy = strategy
    return settings


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


@app.command("render")
def render_cmd(
    image: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    out: Annotated[Path, typer.Argument(help="Panel image (.png/.jpg)")],
    preset: PresetOpt = "photo",
    strategy: StrategyOpt = None,
    overrides: SetOpt = None,
    preview: Annotated[Path | None, typer.Option(help="Also save the simulated look")] = None,
    palette: Annotated[str | None, typer.Option(help="Palette name or JSON path")] = None,
) -> None:
    """Render an image for the panel without sending it."""
    settings = build_render_settings(preset, strategy, overrides)
    result = render(image, settings, get_palette(palette or _settings().palette))
    fmt = "jpeg" if out.suffix.lower() in (".jpg", ".jpeg") else "png"
    data, _ = result.encode(fmt)  # type: ignore[arg-type]
    out.write_bytes(data)
    typer.echo(f"panel image -> {out} ({len(data) // 1024} KB)")
    if preview:
        result.preview_image().save(preview)
        typer.echo(f"preview     -> {preview}")


@app.command()
def testchart(
    name: Annotated[str, typer.Argument(help="palette | passthrough | ramps")],
    out: Path,
) -> None:
    """Write a calibration/test chart (send it with: frame push --raw)."""
    from .imaging.testchart import CHARTS

    if name not in CHARTS:
        raise typer.BadParameter(f"choose from {list(CHARTS)}")
    CHARTS[name]().save(out)
    typer.echo(f"{name} chart -> {out}")


@app.command()
def push(
    image: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    preset: PresetOpt = "photo",
    strategy: StrategyOpt = None,
    overrides: SetOpt = None,
    raw: Annotated[bool, typer.Option(help="Send the file untouched (test charts)")] = False,
    fmt: Annotated[str | None, typer.Option("--format", help="png | jpeg")] = None,
    title: str = "",
    server: Annotated[
        str | None, typer.Option(help="Use a running `frame serve` at this URL")
    ] = None,
    keep_serving: Annotated[
        bool,
        typer.Option(help="Keep serving after the push (the panel re-fetches its URL later)"),
    ] = True,
    wait: Annotated[float, typer.Option(help="Seconds to wait for the download")] = 90,
) -> None:
    """Render an image and show it on the panel."""
    render_settings = build_render_settings(preset, strategy, overrides)
    if server:
        _push_remote(server, image, render_settings, raw, title, wait)
    else:
        asyncio.run(_push_embedded(image, render_settings, raw, fmt, title, keep_serving, wait))


def _push_remote(
    server: str, image: Path, settings: RenderSettings, raw: bool, title: str, wait: float
) -> None:
    import httpx

    s = _settings()
    headers = {"Authorization": f"Bearer {s.api_token}"} if s.api_token else {}
    with image.open("rb") as fh:
        resp = httpx.post(
            f"{server.rstrip('/')}/api/display",
            files={"file": (image.name, fh)},
            data={
                "settings_json": settings.model_dump_json(),
                "raw": str(raw).lower(),
                "title": title,
                "wait": str(wait),
            },
            headers=headers,
            timeout=wait + 60,
        )
    typer.echo(json.dumps(resp.json(), indent=2))
    resp.raise_for_status()


async def _push_embedded(
    image: Path,
    settings: RenderSettings,
    raw: bool,
    fmt: str | None,
    title: str,
    keep_serving: bool,
    wait: float,
) -> None:
    import uvicorn

    from .web import create_app

    config = _settings()
    config.require_device()
    web = create_app(config)
    service = web.state.service
    content = service.prepare(
        image.read_bytes(), settings, raw=raw, fmt=fmt, title=title or image.name, source="cli"
    )
    typer.echo(f"published {content.file_name} ({content.size // 1024} KB)")

    server = uvicorn.Server(
        uvicorn.Config(web, host=config.bind, port=config.port, log_level="warning")
    )
    serving = asyncio.create_task(server.serve())
    while not server.started:
        if serving.done():
            serving.result()
        await asyncio.sleep(0.05)

    try:
        typer.echo(f"telling panel to fetch {service.content_url(content.file_id)}")
        outcome = await service.push_current(wait=wait)
        typer.echo("panel downloaded the image" if outcome.fetched else outcome.message)
        for req in service.store.recent_requests:
            typer.echo(f"  {req.time} {req.method} {req.path} {req.status} UA={req.user_agent!r}")
        if keep_serving:
            typer.echo("Still serving so the panel can re-fetch; Ctrl+C to stop.")
            await serving
    finally:
        server.should_exit = True
        await serving


# -- device -------------------------------------------------------------------

HostOpt = Annotated[str | None, typer.Option("--host", envvar="FRAME_DEVICE_HOST")]
PinOpt = Annotated[str | None, typer.Option("--pin", envvar="FRAME_DEVICE_PIN")]


def _device_settings(host: str | None, pin: str | None) -> Settings:
    s = _settings()
    if host:
        s.device_host = host
    if pin:
        s.device_pin = pin
    s.require_device()
    return s


@device_app.command("info")
def device_info(host: HostOpt = None, pin: PinOpt = None) -> None:
    """Serial, firmware, battery, network standby."""
    from .service import Panel

    status = asyncio.run(Panel(_device_settings(host, pin)).status())
    typer.echo(json.dumps(status, indent=2))


@device_app.command("wake")
def device_wake(mac: Annotated[str | None, typer.Option(envvar="FRAME_DEVICE_MAC")] = None) -> None:
    """Send Wake-on-LAN (needs network standby on)."""
    from .device import wol

    s = _settings()
    mac = mac or s.device_mac
    if not mac:
        raise typer.BadParameter("MAC address required (--mac or FRAME_DEVICE_MAC)")
    asyncio.run(wol.wake(mac, s.device_host))
    typer.echo("magic packet sent")


@device_app.command("sleep")
def device_sleep(host: HostOpt = None, pin: PinOpt = None) -> None:
    """Power off, keeping network standby so Wake-on-LAN works."""
    from .service import Panel

    asyncio.run(Panel(_device_settings(host, pin)).sleep())
    typer.echo("panel powered off (network standby on)")


@device_app.command("standby")
def device_standby(
    enabled: Annotated[bool, typer.Argument(help="true/false")],
    host: HostOpt = None,
    pin: PinOpt = None,
) -> None:
    """Turn network standby on or off."""
    from .service import Panel

    async def run() -> None:
        async with Panel(_device_settings(host, pin)).client() as mdc:
            await mdc.set_network_standby(enabled)
            typer.echo(f"network standby: {await mdc.network_standby()}")

    asyncio.run(run())


@device_app.command("set-url")
def device_set_url(url: str, host: HostOpt = None, pin: PinOpt = None) -> None:
    """Point the panel at a content.json URL (no local server involved)."""
    from .service import Panel

    asyncio.run(Panel(_device_settings(host, pin)).set_content_url(url))
    typer.echo("content URL sent")


@device_app.command("raw")
def device_raw(
    command: Annotated[str, typer.Argument(help="Command id, e.g. 0x25")],
    data: Annotated[str, typer.Argument(help="Payload as hex, e.g. '73' or '01 00'")] = "",
    host: HostOpt = None,
    pin: PinOpt = None,
) -> None:
    """Send any MDC command and print the reply (for exploring the protocol)."""
    from .service import Panel

    async def run() -> None:
        async with Panel(_device_settings(host, pin)).client() as mdc:
            reply = await mdc.command_raw(int(command, 0), bytes.fromhex(data))
            typer.echo(f"{'ACK' if reply.ack else 'NAK'} 0x{reply.command:02X}")
            typer.echo(f"payload: {reply.payload.hex(' ')}")
            typer.echo(f"ascii:   {reply.payload.decode('ascii', errors='replace')!r}")
            typer.echo(f"frame:   {reply.raw.hex(' ')}")

    asyncio.run(run())


@app.command("palette")
def palette_cmd(
    name: Annotated[str | None, typer.Argument(help="Built-in name or JSON path")] = None,
    export: Annotated[Path | None, typer.Option(help="Write the palette JSON here")] = None,
) -> None:
    """Show (or export as a starting point for calibration) a palette."""
    pal = get_palette(name or _settings().palette)
    if export:
        pal.save(export)
        typer.echo(f"saved {pal.name} -> {export}")
        return
    typer.echo(f"{pal.name}  ({pal.source})")
    for c in pal.colors:
        typer.echo(f"  {c.name:7s} device={c.device!s:16s} perceived={c.perceived}")


if __name__ == "__main__":
    app()
