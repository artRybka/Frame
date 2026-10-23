"""Application services: render + publish content, drive the panel."""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import asdict, dataclass

from PIL import Image

from .config import Settings
from .device import MdcClient, MdcConnectionError, wol
from .imaging import Palette, RenderSettings, get_palette, render
from .imaging.pipeline import encode_image
from .store import ContentInfo, ContentStore

log = logging.getLogger(__name__)

PREVIEW_MAX = 1280


@dataclass
class PushOutcome:
    content: ContentInfo
    pushed: bool
    fetched: bool
    content_url: str
    message: str = ""


class Panel:
    """Serialises access to the panel (it accepts one MDC session at a time)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()

    def client(self) -> MdcClient:
        host, pin = self.settings.require_device()
        return MdcClient(host, pin, self.settings.device_port)

    async def wake(self) -> bool:
        if not self.settings.device_mac:
            return False
        await wol.wake(self.settings.device_mac, self.settings.device_host)
        return True

    async def set_content_url(self, url: str) -> None:
        async with self._lock:
            client = self.client()
            try:
                await client.connect(attempts=2, retry_delay=5)
            except MdcConnectionError:
                if not await self.wake():
                    raise
                log.info("panel unreachable, sent Wake-on-LAN")
                await asyncio.sleep(15)
                await client.connect(attempts=4, retry_delay=8)
            try:
                await client.content_download(url)
            finally:
                await client.close()

    async def status(self) -> dict[str, object]:
        async with self._lock, self.client() as mdc:
            battery = await mdc.battery()
            return {
                "serial": await mdc.serial_number(),
                "software": await mdc.software_version(),
                "model": await mdc.model_name(),
                "name": await mdc.device_name(),
                "battery": {
                    "level": battery.level,
                    "raw": battery.raw.hex(" "),
                },
                "network_standby": await mdc.network_standby(),
            }

    async def sleep(self) -> None:
        """Power off but keep network standby, so Wake-on-LAN still works."""
        async with self._lock, self.client() as mdc:
            await mdc.set_network_standby(True)
            await mdc.set_power(False)


class FrameService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = ContentStore(settings.data_dir)
        self.panel = Panel(settings)
        self.palette: Palette = get_palette(settings.palette)

    def content_url(self, file_id: str) -> str:
        # The query only changes the URL per push; the server ignores it.
        return f"{self.settings.base_url()}/panel/content.json?v={file_id}"

    def prepare(
        self,
        image: bytes,
        render_settings: RenderSettings | None,
        *,
        raw: bool = False,
        fmt: str | None = None,
        title: str = "",
        description: str = "",
        source: str = "",
    ) -> ContentInfo:
        """Render (or pass through untouched with ``raw``) and publish."""
        if raw:
            img = Image.open(io.BytesIO(image))
            ext = "png" if img.format == "PNG" else "jpg"
            if img.format not in ("PNG", "JPEG"):
                image, ext = encode_image(img.convert("RGB"), "png"), "png"
            preview = img.convert("RGB")
            preview.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
            return self.store.publish(
                image,
                ext,
                preview_png=encode_image(preview, "png"),
                title=title,
                description=description,
                source=source,
                render={"raw": True},
            )

        settings = render_settings or RenderSettings()
        result = render(image, settings, self.palette)
        data, ext = result.encode(fmt)  # type: ignore[arg-type]
        preview = result.preview_image()
        preview.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
        return self.store.publish(
            data,
            ext,
            preview_png=encode_image(preview, "png"),
            title=title,
            description=description,
            source=source,
            render=settings.model_dump(mode="json") | {"palette": self.palette.name},
        )

    async def push_current(self, wait: float = 90.0) -> PushOutcome:
        content = self.store.current()
        if content is None:
            raise RuntimeError("nothing published yet")
        url = self.content_url(content.file_id)
        if wait:
            self.store.expect_fetch(content.file_id)
        try:
            await self.panel.set_content_url(url)
        except BaseException:
            self.store.cancel_fetch(content.file_id)
            raise
        fetched = await self.store.wait_for_fetch(content.file_id, wait) if wait else False
        message = "" if fetched or not wait else "panel did not download the image in time"
        return PushOutcome(content, pushed=True, fetched=fetched, content_url=url, message=message)

    def ensure_initial_content(self) -> None:
        """Publish a placeholder so the panel's URL never 404s on a fresh install."""
        if self.store.current() is not None:
            return
        from .imaging.testchart import welcome_card

        img = welcome_card()
        self.store.publish(
            encode_image(img, "png"),
            "png",
            preview_png=encode_image(img.resize((1280, 720)), "png"),
            title="Frame",
            description="Placeholder shown until the first image is sent.",
            source="frame",
        )


def outcome_json(outcome: PushOutcome) -> dict[str, object]:
    return {
        "content": asdict(outcome.content),
        "pushed": outcome.pushed,
        "fetched": outcome.fetched,
        "content_url": outcome.content_url,
        "message": outcome.message,
    }
