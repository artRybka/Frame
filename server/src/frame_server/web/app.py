"""HTTP API.

/panel/*  – fetched by the panel itself (no auth: it cannot send any).
/api/*    – used by the iOS app and tools; Bearer token when configured.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from .. import build_version, golden, logbuffer, night, notifications
from ..artist_people import START_DELAY
from ..config import Settings
from ..device import MdcError
from ..imaging import PRESETS, RenderSettings, Strategy
from ..imaging.layout import load_image
from ..library import dumps, rijks_index
from ..library.hosts import guard as host_guard
from ..library.images import Gone
from ..library.seed import seed_playlists
from ..library.style import AUTO, preset_for_photo
from ..library.themes import painterly_colour_playlists
from ..loopwatch import LoopWatch
from ..night import NightQueue
from ..night import tasks as night_tasks
from ..panel_app import CODE_VERSION, WIDGET, AppHello, NextAnswer, app_code
from ..player import PANEL_NOT_SET, hold_from
from ..power import WakeResult
from ..progress import DisplayProgress, Stage
from ..service import FrameService, outcome_json
from ..status import DeviceStatus
from ..store import PanelRequest, preview_url
from . import (
    ai_api,
    calibration_api,
    daily_api,
    device_api,
    discover_api,
    library_api,
    looks_api,
    night_api,
    notify_api,
    player_api,
    playlists_api,
    restorer_api,
    sources_api,
    storage_api,
    study_api,
    tailnet_api,
    update_api,
    users_api,
)
from .deps import require_owner, require_token
from .ids import EncodedSlashes
from .purposes import Purposes
from .replays import Replays

log = logging.getLogger(__name__)


def _day_quiet() -> bool:
    """As the night's quiet, by day: waits for the app to be left alone
    (10 minutes at most; else the reading stops until the night)."""
    for _ in range(60):
        if night.idle_for() >= night.QUIET_FOR:
            return True
        time.sleep(night.QUIET_LOOK)
    return False


def _day_pause(seconds: float) -> bool:
    time.sleep(seconds)
    return True


# The panel reports download progress (and failures) here, at the root of the
# content server, whatever path the manifest came from.
PROGRESS_PATH = "/content-transfer-progress"
#: Requests that are not someone using the app (the night's work goes on).
NOT_USE = ("/api/health", "/api/debug/")
SLOW_REQUEST = 2.0  # seconds: an app request this slow goes in the log
#: The app counts as in use this long after its last request (seconds): the
#: background's requests to the museums wait meanwhile.
APP_IN_USE = 120.0
#: Seconds after a start before the looks' numbers (Gemini) are sent and
#: the works searches showed before it are taken in.
LOOKS_DELAY = 180.0
SEARCHED_DELAY = 90.0


def _photo_preset(data: bytes) -> str:
    try:
        return preset_for_photo(load_image(data))
    except OSError:
        return "photo"  # not an image: prepare() says so


async def poll_status(service: FrameService) -> None:
    """Refresh the panel status now and then. On battery only rarely: every
    MDC session may keep the panel awake (to be measured in E8)."""
    await asyncio.sleep(5)
    while True:
        minutes = service.player.settings.status_poll_minutes
        if minutes and service.device_configured:
            last = service.status.status.checked_at
            stale = last is None or datetime.fromisoformat(last) < datetime.now(UTC) - timedelta(
                hours=6
            )
            asleep = service.power.deep_asleep(datetime.now(UTC))
            if not asleep and (not service.status.on_battery or stale):
                await service.status.refresh()
        await asyncio.sleep(max(minutes, 1) * 60)


async def sync_albums_periodically(service: FrameService, minutes: int = 30) -> None:
    await asyncio.sleep(20)
    while True:
        # Reads the playlists from the library: never on the event loop,
        # which would wait for the library's lock.
        await run_in_threadpool(service.albums.sync_all)
        await asyncio.sleep(minutes * 60)


# The Frame app's reports: its probe is a few KB of JSON.
REPORT_BYTES = 16000
# A screenshot of the panel, JPEG.
CAPTURE_BYTES = 15 * 1024 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.load()
    service = FrameService(settings)
    service.ensure_initial_content()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tasks = []
        logbuffer.install()  # again: uvicorn's logging setup dropped it
        if settings.scheduler:  # the server itself, not a test
            logbuffer.keep_on_disk(settings.data_dir / "logs")
        service.notifier.bind(asyncio.get_running_loop())
        if settings.scheduler:
            tasks = [
                asyncio.create_task(service.player.run()),
                asyncio.create_task(service.power.run()),
                asyncio.create_task(poll_status(service)),
                asyncio.create_task(sync_albums_periodically(service)),
                asyncio.create_task(notifications.watch(service)),
                # A loop held up by work that belongs in a thread: in the log.
                asyncio.create_task(LoopWatch().run()),
            ]
            service.ai.start()
        service.app.ensure_package()  # built and signed here (panel_package.py)
        seed_playlists(service.importer)
        painterly_colour_playlists(service.library)  # once: colour playlists keep to paintings
        service.albums.migrate()  # once: the album of older settings becomes a playlist
        service.player.reset_library()  # once: a clean start for the catalogue
        service.player.drop_set_aside()  # once: the catalogue leaves them out now
        service.player.drop_spare_copies()  # a work once, from the most reliable source
        if settings.seed_library:
            service.player.top_up()  # Suggestions come from museums, as needed
        if settings.scheduler:
            # Heavy work at night, one task at a time (night.py): the
            # catalogue turns over and the cache is tidied then, not by day.
            service.night = NightQueue(service, night_tasks(service))
            service.player.at_night = True
            threading.Thread(target=service.night.run, name="night", daemon=True).start()
            # Playlisty open with the counts last worked out while the
            # catalogue changes: each counted afresh when opened, all at
            # night, and once now (the counts are not kept over a restart).
            service.library.counts_may_lag = True
            recount = threading.Timer(60.0, service.library.recount)
            recount.daemon = True
            recount.start()
            # Discover's first visit then finds its themes worked out.
            threading.Thread(target=discover_api.warm_up, args=(service,), daemon=True).start()
            threading.Thread(target=service.daily.run, name="daily", daemon=True).start()
            # The sheets the analyses of composition are drawn on are there
            # before a study is opened (sheets.py).
            service.sheets.start()
            # Google's batches of "Kreatywny restaurator" looked at now and then.
            service.restorer.start()
            service.drawn.start()
            # The museums' works get their looks as numbers ("G1"), and what
            # searches showed before a restart and had not taken in yet:
            # both a while after the start, when the app's first questions
            # are answered (they read and send thousands of thumbnails; the
            # server answered in 30-70 s for minutes after 1.145.99 began).
            for later in (
                threading.Timer(LOOKS_DELAY, service.looks.start),
                threading.Timer(SEARCHED_DELAY, service.player.resume_searched),
            ):
                later.daemon = True
                later.start()
            # The earlier studies' facts and rewrites, ordered from the app.
            service.study_refresh.start_thread()
            # The Polish texts kept, looked over as ordered from the app.
            service.text_review.start_thread()
            # Who the catalogue's artists are, from Wikidata: once some
            # minutes after a start (the search knows them then), new ones at
            # night (artist_people.py).
            people = threading.Timer(START_DELAY, service.artist_people.after_start)
            people.daemon = True
            people.start()
            # What all of that would ask the museums at once waits a while;
            # what the app and the panel ask for goes. The background's own
            # work waits while the app is in use too (library/hosts.py).
            host_guard.calm()
            host_guard.app_in_use = lambda: night.idle_for() < APP_IN_USE
        yield
        for task in tasks:
            task.cancel()
        service.ai.stop()
        service.daily.stop()
        service.sheets.stop()
        service.restorer.stop()
        service.drawn.stop()
        service.looks.stop()
        service.study_refresh.stop()
        service.text_review.stop()
        if service.night is not None:
            service.night.stop()
        service.library.close()

    app = FastAPI(title="Frame", version=build_version(), lifespan=lifespan)
    app.state.service = service
    routers = (
        library_api.router,
        discover_api.router,
        daily_api.router,
        study_api.router,
        playlists_api.router,
        player_api.router,
        calibration_api.router,
        device_api.router,
        storage_api.router,
        ai_api.router,
        update_api.router,
        notify_api.router,
        users_api.router,
        sources_api.router,
        tailnet_api.router,
        night_api.router,
        restorer_api.router,
        looks_api.router,
    )
    for router in routers:
        app.include_router(router)
    app.add_middleware(Purposes)  # what the museums' requests are for
    app.add_middleware(EncodedSlashes)  # work ids with a slash (SMK)

    @app.middleware("http")
    async def log_panel_requests(request: Request, call_next):
        if request.url.path.startswith("/api/") and not request.url.path.startswith(NOT_USE):
            night.used()  # the night's work waits while the app is in use
        started = time.monotonic()
        response = await call_next(request)
        took = time.monotonic() - started
        if took >= SLOW_REQUEST and request.url.path.startswith("/api/"):
            # The app's requests are not logged otherwise: a slow one shows
            # what the owner waited for (2026-11-08, Multi previews).
            log.info(
                "slow %s %s -> %s in %.1f s",
                request.method,
                request.url.path,
                response.status_code,
                took,
            )
        if request.url.path.startswith("/panel/"):
            # The Frame app's page is a file:// origin.
            response.headers["Access-Control-Allow-Origin"] = "*"
        if request.url.path == "/panel/content.json" and response.status_code == 200:
            # Only the panel itself: a browser or script on another computer
            # checking the server is not the panel leaving (2026-10-30).
            client = request.client.host if request.client else None
            panel = service.settings.device_host
            if not panel or client == panel:
                service.app.left()  # another source (Mobile): the app is started again
        if request.url.path.startswith("/panel/") or request.url.path == PROGRESS_PATH:
            entry = PanelRequest(
                time=datetime.now(UTC).isoformat(timespec="milliseconds"),
                client=request.client.host if request.client else "",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                user_agent=request.headers.get("user-agent", ""),
                headers=dict(request.headers),
            )
            service.store.log_request(entry)
            log.info("panel %s %s -> %s", entry.method, request.url, entry.status)
        return response

    # Outermost: a change cut off by the phone going away is finished here
    # and answered again from memory when the app asks once more.
    app.add_middleware(Replays)

    auth = [Depends(require_token)]

    # -- panel ---------------------------------------------------------------

    @app.get("/panel/content.json")
    def panel_manifest(file: str | None = None) -> Response:
        """The Mobile source's manifest. The frame runs our app; this only
        keeps a panel that fell back to Mobile showing the current picture
        until the server has started the app again. ``file``: an earlier
        picture, for a test of Samsung's player (PLAN 2.6t)."""
        if file is not None and not file.isalnum():
            raise HTTPException(404)
        manifest = service.store.manifest(settings.base_url(), file)
        if manifest is None:
            raise HTTPException(404)
        return Response(manifest.encode(), media_type="application/json")

    @app.get("/panel/images/{name}")
    def panel_image(name: str) -> FileResponse:
        path = service.store.image_path(name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path)

    @app.get(notifications.PICTURE_PATH)
    def push_picture(id: str, s: str) -> FileResponse:
        """A work's thumbnail for a notification on the phone: the extension
        that shows it has no token, the address is signed instead."""
        item = service.library.get(id)
        if item is None or not service.notifier.picture_allowed(id, s):
            raise HTTPException(404)
        try:
            path = service.images.ensure_thumb(item)
        except (Gone, httpx.HTTPError, OSError) as err:
            raise HTTPException(502, f"thumbnail unavailable: {err}") from err
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/panel/next")
    async def panel_next(
        reason: str = "start",
        build: str | None = None,
        code: str | None = None,
        screen: str | None = None,
        battery: int | None = None,
        charging: bool | None = None,
        now: int | None = None,
        shown: str | None = None,
    ) -> NextAnswer:
        """The Frame app, at every start and wake: what to show, and when to
        wake next. ``shown``: the picture its page remembers on the screen
        (without it the server never told a freshly started app to draw it
        again: white after a cold start, 2026-11-05)."""
        hello = AppHello(
            reason=reason,
            build=build,
            code=code,
            screen=screen,
            battery=battery,
            charging=charging,
            now=now,
            shown=shown,
        )
        return await service.app.ask(hello)

    @app.post("/panel/report")
    async def panel_report(request: Request) -> dict[str, object]:
        body = (await request.body())[:REPORT_BYTES].decode("utf-8", "replace")
        try:
            data = json.loads(body)
        except ValueError:
            data = {"text": body}
        if not isinstance(data, dict):
            data = {"value": data}
        service.app.report(str(data.pop("event", "")), data)
        return {}

    @app.post("/panel/capture")
    async def panel_capture(request: Request) -> dict[str, object]:
        """The screenshot the Frame app took when the owner asked for one."""
        body = await request.body()
        if len(body) > CAPTURE_BYTES:
            raise HTTPException(413)
        return {"saved": service.app.save_capture(body)}

    @app.get("/panel/app-images/{name}")
    def panel_app_image(name: str) -> FileResponse:
        """The Frame app's JPEG copy of a full-colour picture."""
        path = service.app.picture(name.removesuffix(".jpg"))
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/panel/app/sssp_config.xml")
    async def panel_app_config(request: Request) -> Response:
        xml = service.app.sssp_config()
        if xml is None:
            raise HTTPException(404, "no app package uploaded")
        # The launcher of a panel just booted: it does not start the app
        # itself, the server does (only the panel's own address counts).
        client = request.client.host if request.client else None
        if client and client == service.settings.device_host:
            service.app.launcher_asked()
        return Response(xml, media_type="application/xml")

    @app.get(f"/panel/app/{WIDGET}.wgt")
    def panel_app_package() -> FileResponse:
        if service.app.package() is None:
            raise HTTPException(404, "no app package uploaded")
        return FileResponse(service.app.package_path(), media_type="application/widget")

    @app.get("/panel/app/app.js")
    def panel_app_code() -> Response:
        """The app's logic, loaded by the signed package at every start."""
        body = f'window.FRAME_CODE = "{CODE_VERSION}";\n'.encode() + app_code()
        headers = {"Cache-Control": "no-store"}
        return Response(body, media_type="application/javascript", headers=headers)

    @app.post(PROGRESS_PATH)
    async def panel_progress(request: Request) -> dict[str, object]:
        body = (await request.body())[:2000].decode("utf-8", "replace")
        log.info("panel progress report: %s", body)
        return {}

    # -- API -----------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {"ok": True, "version": build_version(), "palette": service.palette.name}

    @app.get("/api/now", dependencies=auth)
    def now() -> dict[str, object]:
        content = service.store.current()
        if content is None:
            raise HTTPException(404)
        return asdict(content) | {"preview_url": preview_url(content.file_id)}

    @app.get("/api/previews/{file_id}.png", dependencies=auth)
    def preview(file_id: str) -> FileResponse:
        path = service.store.preview_path(file_id)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type="image/png")

    @app.get("/api/previews/{file_id}.jpg", dependencies=auth)
    def preview_jpeg(file_id: str) -> FileResponse:
        path = service.store.preview_jpeg_path(file_id)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/presets", dependencies=auth)
    def presets() -> dict[str, object]:
        return {name: p.model_dump(mode="json") for name, p in PRESETS.items()}

    @app.post("/api/display", dependencies=auth)
    async def display(
        file: Annotated[UploadFile, File()],
        preset: Annotated[str, Form()] = "photo",
        strategy: Annotated[Strategy | None, Form()] = None,
        settings_json: Annotated[str | None, Form()] = None,
        raw: Annotated[bool, Form()] = False,
        title: Annotated[str, Form()] = "",
        description: Annotated[str, Form()] = "",
        push: Annotated[bool, Form()] = True,
        wait: Annotated[float, Form()] = 90.0,
        hold: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        data = await file.read()
        if preset == AUTO and not settings_json:
            preset = await run_in_threadpool(_photo_preset, data)
        if settings_json:
            render_settings = RenderSettings.model_validate_json(settings_json)
        elif preset in PRESETS:
            render_settings = PRESETS[preset].model_copy(deep=True)
        else:
            raise HTTPException(400, f"unknown preset {preset!r}")
        if strategy is not None:
            render_settings.strategy = strategy
        title = title or (file.filename or "")
        if push:
            service.progress.begin(title, origin="app")
        try:
            content = await run_in_threadpool(
                service.prepare,
                data,
                render_settings,
                raw=raw,
                title=title,
                description=description,
                source="upload",
            )
        except Exception as err:
            if push:
                service.progress.finish(Stage.FAILED, str(err))
            raise
        service.player.note_external(hold_from(hold))
        if not push or not service.device_configured:
            message = "" if not push else PANEL_NOT_SET
            if push:
                service.progress.finish(Stage.FAILED, message)
            return {"content": asdict(content), "pushed": False, "message": message}
        try:
            outcome = await service.push_current(wait=wait)
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err
        return outcome_json(outcome)

    @app.post("/api/device/push", dependencies=auth)
    async def push_again(wait: float = 90.0) -> dict[str, object]:
        if not service.device_configured:
            raise HTTPException(409, "panel not configured")
        try:
            return outcome_json(await service.push_current(wait=wait))
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err

    @app.get("/api/progress", dependencies=auth)
    def progress() -> DisplayProgress:
        """The picture on its way to the frame (the app polls this every second)."""
        return service.progress.view()

    @app.get("/api/device/status", dependencies=auth)
    async def device_status() -> DeviceStatus:
        await service.status.refresh()
        service.power.publish_status()
        return service.status.status

    @app.post("/api/device/wake", dependencies=auth)
    async def device_wake(sleep_after: bool = False) -> WakeResult:
        """``sleep_after``: the app's "Sprawdź stan" found the panel asleep
        and wakes it only to look at it."""
        if not service.device_configured:
            raise HTTPException(409, "panel not configured")
        return await service.power.wake_now(sleep_after=sleep_after)

    @app.post("/api/device/restart", dependencies=auth)
    async def device_restart() -> WakeResult:
        """ "Uruchom ponownie": the frame's app reboots the panel (woken for
        it when asleep in the network, started over MDC when hung)."""
        if not service.device_configured:
            raise HTTPException(409, "panel not configured")
        return await service.power.restart_now()

    @app.post("/api/device/sleep", dependencies=auth)
    async def device_sleep(
        hours: Annotated[int | None, Query(ge=1, le=72)] = None, off: bool = False
    ) -> dict[str, object]:
        """ "Uśpij ramkę"; with ``hours`` "Głęboki sen" (the Wi-Fi off, no
        changes) for that long, with ``off`` "Wyłącz ramkę" (no alarm: only
        the button wakes it)."""
        if not service.device_configured:
            raise HTTPException(409, "panel not configured")
        if off or hours is not None:
            rest = await service.power.rest_now(None if off else hours)
            return {"ok": True, **rest.model_dump()}
        try:
            await service.power.sleep_now()
        except MdcError as err:
            raise HTTPException(502, f"panel: {err}") from err
        return {"ok": True}

    @app.post("/api/debug/panel-capture", dependencies=[Depends(require_owner)])
    def ask_panel_capture() -> dict[str, object]:
        """Ask the Frame app for a screenshot at its next question with
        ``stay`` (on the charger every 20 s); fetch it from the GET."""
        return {"asked": True, "on_charger": service.app.ask_capture().on_charger}

    @app.get("/api/debug/panel-capture.jpg", dependencies=[Depends(require_owner)])
    def panel_capture_file() -> FileResponse:
        path = service.app.capture_path
        if not path.exists():
            raise HTTPException(404, "no screenshot yet")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/debug/panel-requests", dependencies=[Depends(require_owner)])
    def panel_requests() -> list[dict[str, object]]:
        return [asdict(r) for r in service.store.recent_requests]

    @app.get("/api/debug/battery", dependencies=[Depends(require_owner)])
    def battery_data() -> dict[str, object]:
        """What the battery estimate is learnt from (battery.py): the
        readings on battery, the panel's activity and the costs fitted."""
        log = service.status.battery
        return {
            "runs": log.runs,
            "activity": log.activity.model_dump(),
            "fit": log.fit().model_dump(),
        }

    log_buffer = logbuffer.install()

    @app.get(
        "/api/debug/log", dependencies=[Depends(require_owner)], response_class=PlainTextResponse
    )
    def recent_log(lines: int = 500, grep: str | None = None, day: str | None = None) -> str:
        """The server's last log records, oldest first (at most
        ``logbuffer.KEEP``), for a look from outside the NAS: from memory,
        or with ``day`` (``YYYY-MM-DD``) that day's as kept on disk."""
        count = min(lines, logbuffer.KEEP)
        if day is None:
            return "\n".join(log_buffer.lines(count, grep)) + "\n"
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise HTTPException(400, "day: YYYY-MM-DD")
        found = logbuffer.day_lines(day, count, grep)
        if found is None:
            raise HTTPException(404, "the log is not kept on disk")
        return "\n".join(found) + "\n"

    @app.get("/api/debug/dumps", dependencies=[Depends(require_owner)])
    def dump_states() -> list[dict[str, object]]:
        """The museums' local indexes (library/dumps.py): built when, how
        many works, building now, or why the last build failed."""
        return [*dumps.states(settings.data_dir), rijks_index.INDEX.state(settings.data_dir)]

    @app.post("/api/debug/dumps/{key}", dependencies=[Depends(require_owner)])
    def build_dump(key: str) -> dict[str, object]:
        """A museum's dump read now, in the background, without waiting for
        the night (the owner's test, 2026-11-08)."""
        if key == rijks_index.KEY:
            # Read while the app is quiet, as at night (library/rijks_index.py).
            return {"started": rijks_index.read_now(settings.data_dir, _day_quiet, _day_pause)}
        if key not in dumps.DUMPS:
            keys = ", ".join([*dumps.DUMPS, rijks_index.KEY])
            raise HTTPException(404, f"no dump {key!r}; one of {keys}")
        return {"started": dumps.build_now(key, settings.data_dir)}

    @app.get("/api/debug/decisions", dependencies=[Depends(require_owner)])
    async def settled_decisions(request: Request) -> dict[str, Any]:
        """What is settled about the works so far (golden.py): which
        pictures are one work, details and photographs, pairs kept apart,
        works set aside. Descriptions only; test data for changes of the
        rules."""
        return await run_in_threadpool(golden.decisions, request.app.state.service)

    @app.get("/api/debug/catalogue", dependencies=[Depends(require_owner)])
    def whole_catalogue(request: Request) -> StreamingResponse:
        """Every work of art as the library has it (golden.py): gzip, a
        work a line. Descriptions only; the catalogue a change of the rules
        is tried on before it is the frame's."""
        return StreamingResponse(
            golden.catalogue(request.app.state.service.library),
            media_type="application/gzip",
            headers={"Content-Disposition": 'attachment; filename="catalogue.jsonl.gz"'},
        )

    @app.get("/api/debug/artists", dependencies=[Depends(require_owner)])
    def catalogue_artists(request: Request) -> dict[str, Any]:
        """Who the catalogue's artists are as Wikidata told (golden.py):
        with the catalogue, what a change of "the same artist" is tried on."""
        return golden.artists(request.app.state.service.library)

    @app.get("/api/debug/hosts", dependencies=[Depends(require_owner)])
    def host_tally() -> dict[str, Any]:
        """The kept days' requests to each host (sent, turned away,
        throttled, failed, refused while resting or over quota, bytes) and
        the quotas spent (library/policy.py)."""
        from ..library.hosts import guard

        return {
            "today": guard.tally(),
            "days": guard.days(),
            "purposes": guard.purposes(),
            "quotas": {
                host: {"spent": guard.spent(host), "of": b.count, "background": b.background}
                for host, b in guard.budgets.items()
            },
        }

    @app.get("/api/diagnostics/sources", dependencies=[Depends(require_owner)])
    def source_requests() -> dict[str, Any]:
        """Konfiguracja → Diagnostyka (Mateusz 2026-11-07): requests to each
        source today and over the last days, the refusals, quotas and rests."""
        from ..library.hosts import TALLY_DAYS, guard

        return {"days": TALLY_DAYS, "sources": guard.by_source()}

    return app
