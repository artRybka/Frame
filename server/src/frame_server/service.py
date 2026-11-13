"""Application services: render + publish content, drive the panel."""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from pathlib import Path

from PIL import Image

from . import notifications
from .ai import AiConfigStore, AiWorker, Claude, DailyJob, KeywordsJob, PlTextJob
from .ai.audit import Audit
from .ai.composition import ComposeJob
from .ai.curator import Curator
from .ai.daily import View
from .ai.details import MendJob
from .ai.extras import ExtrasJob
from .ai.gatekeeper import Gatekeeper
from .ai.gemini import Painter
from .ai.journey import Journeys
from .ai.look_words import LookWords
from .ai.museum_words import MuseumWords
from .ai.prose import ProseJob
from .ai.redraw import PenJob
from .ai.refresh import StudyRefresh
from .ai.search_words import SearchWords
from .ai.study import StudyJob
from .ai.twins_judge import NightJudge
from .ai.web_facts import WebFacts
from .albums import Albums
from .artist_people import ArtistPeople
from .artist_works import ArtistWorks
from .births import Births
from .cared import Cared
from .config import Settings
from .copies import Copies
from .daily import Daily
from .device import MdcClient, MdcConnectionError, MdcError, wol
from .drawn import DrawnSheets
from .holders import Holders
from .imaging import Palette, RenderSettings, get_palette, render, render_multi
from .imaging.pipeline import encode_image
from .kept import KeptOriginals
from .later import LaterWorks
from .leftover import Leftover
from .library import ImageCache, Importer, Item, Library, courtauld, low_res
from .library.commons import repair_library
from .library.fragments import Fragments
from .library.hosts import guard as host_guard
from .library.loc import loc_mirrors
from .library.museums import PRIVATE_LICENCE, TEST_LICENCE, Access, WikiArt, europeana_mirrors
from .library.museums import client as museum_client
from .library.records import records
from .library.twins import Twins
from .library.wikidata import MIRRORED, CommonsCopies
from .looks import Looks
from .media import Media
from .museum_places import MuseumPlaces
from .night import NightQueue
from .notifications import Notifier
from .panel_app import POLL, PanelApp
from .panel_config import PanelConfigStore
from .places import Places
from .player import Player
from .power import INSTALL_LOOK, WAKE_BURST_SECONDS, PowerManager
from .progress import ProgressTracker, Stage
from .rendered import RenderCache, Rendered, render_key
from .restorer import Restorer
from .sharper import Sharper
from .sheets import Sheets
from .sizes import Sizes
from .source_keys import SourceKeys
from .stages import PaintingStages
from .status import StatusMonitor
from .storage import StorageStore
from .store import ContentInfo, ContentStore
from .study import Study
from .study_gate import StudyGate
from .tailnet import Tailnet
from .users import Users

log = logging.getLogger(__name__)

PREVIEW_MAX = 1280
# The Frame app's alarm rings this close to a push: it will ask by itself.
WAKE_SOON = timedelta(minutes=3)
PROGRESS_KEY = "progress_expected"
#: Set once the Courtauld's white pictures kept before 1.100.7 are removed.
COURTAULD_WHITE_KEY = "courtauld_white_removed"
#: Set once the works of the test switches (WikiArt, "Bez limitu 70 lat")
#: carry the licences of "Użytek prywatny" (1.111.0).
TEST_LICENCES_KEY = "test_licences_relabelled"
NO_CERTIFICATES = (
    "Ramka nie ma aplikacji Frame: wgraj certyfikaty Samsunga w Konfiguracji → Aplikacja ramki."
)


@dataclass
class PushOutcome:
    content: ContentInfo
    pushed: bool
    fetched: bool
    content_url: str
    message: str = ""


def relabel_test_licences(library: Library) -> int:
    """Works let in by the test switches "WikiArt" and "Bez limitu 70 lat",
    folded into "Użytek prywatny" in 1.111.0, carry its licences; returns
    how many changed."""
    _, items = library.query(include_excluded=True)
    moved = 0
    for item in items:
        if item.source == "wikiart" and item.license == WikiArt.test_licence:
            licence = WikiArt.licence
        elif item.source == "europeana" and item.license.startswith(TEST_LICENCE):
            licence = PRIVATE_LICENCE + item.license.removeprefix(TEST_LICENCE)
        else:
            continue
        library.upsert(item.model_copy(update={"license": licence}))
        moved += 1
    return moved


class Panel:
    """Serialises access to the panel (it accepts one MDC session at a time)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self.on_wake: Callable[[], None] | None = None  # e.g. to show "waking" in the app
        self.woke = False  # the last waking session had to wake it

    def client(self) -> MdcClient:
        host, pin = self.settings.require_device()
        return MdcClient(host, pin, self.settings.device_port)

    async def wake(self, seconds: int = 0) -> bool:
        """Wake-on-LAN; with ``seconds`` a packet a second for that long (a
        dozing Wi-Fi client only listens every few beacons)."""
        if not self.settings.device_mac:
            return False
        if seconds:
            await wol.wake(
                self.settings.device_mac, self.settings.device_host, repeats=seconds, interval=1.0
            )
        else:
            await wol.wake(self.settings.device_mac, self.settings.device_host)
        return True

    @asynccontextmanager
    async def waking_session(self) -> AsyncIterator[MdcClient]:
        """A session, waking the panel with Wake-on-LAN if it does not answer."""
        async with self._lock:
            client = self.client()
            self.woke = False
            try:
                await client.connect(attempts=2, retry_delay=5)
            except MdcConnectionError:
                if not self.settings.device_mac:
                    raise
                self.woke = True
                if self.on_wake:
                    self.on_wake()
                # On battery the panel answers one to three minutes into the
                # burst (E13): keep sending until it does.
                log.info("panel unreachable, sending Wake-on-LAN")
                burst = asyncio.create_task(self.wake(seconds=WAKE_BURST_SECONDS))
                try:
                    await self._connect_until(client, WAKE_BURST_SECONDS + 10)
                finally:
                    burst.cancel()
            try:
                yield client
            finally:
                await client.close()

    @staticmethod
    async def _connect_until(client: MdcClient, seconds: float) -> None:
        """Try to connect every few seconds until ``seconds`` have passed."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while True:
            await asyncio.sleep(5)
            try:
                await client.connect()
                return
            except MdcConnectionError:
                if loop.time() >= deadline:
                    raise

    @asynccontextmanager
    async def session(self) -> AsyncIterator[MdcClient]:
        """One short MDC session, never overlapping with another."""
        async with self._lock, self.client() as mdc:
            yield mdc

    async def sleep(self) -> None:
        """Power off but keep network standby, so Wake-on-LAN still works."""
        async with self.session() as mdc:
            await self.power_off(mdc)

    @staticmethod
    async def power_off(mdc: MdcClient) -> None:
        await mdc.set_network_standby(True)
        await mdc.set_power(False)


class FrameService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = ContentStore(settings.data_dir)
        self.panel = Panel(settings)
        self.progress = ProgressTracker()
        self.rendered = RenderCache()
        self.panel.on_wake = lambda: self.progress.advance(Stage.WAKING)
        self.palette: Palette = self._initial_palette()
        self.library = Library(settings.data_dir / "library.db")
        if repaired := repair_library(self.library):
            log.info("repaired stored text and links of %d items", repaired)
        # The owner (the server's token) and household members.
        self.users = Users(self.library, settings.api_token)
        # Before anything reads the panel's address: the app's values win.
        self.panel_config = PanelConfigStore(settings, self.library)
        # Quotas of the sources that have one (library/policy.py) outlive a restart.
        host_guard.keep_budgets(settings.data_dir / "hosts" / "quotas.json")
        # A week of requests by source, for Konfiguracja → Diagnostyka.
        host_guard.keep_tally(settings.data_dir / "hosts" / "tally.json")
        host_guard.keep_rests(settings.data_dir / "hosts" / "rests.json")
        self.images = ImageCache(settings.data_dir / "library", museum_client)
        self.images.mirrors["europeana"] = europeana_mirrors
        self.library.long_side = self.images.long_side  # playlists "by quality"
        # Tiles and cards mark a picture small for the frame by its size.
        low_res.known_sizes(self.images.long_side)
        self.images.mirrors["loc"] = loc_mirrors
        # The Courtauld's CMYK scans come white as JPEG: asked again as PNG.
        self.images.repairs[courtauld.HOST] = courtauld.repair
        if not self.library.get_state(COURTAULD_WHITE_KEY):
            if white := courtauld.forget_white([self.images.thumbs, self.images.images]):
                log.info("removed %d white Courtauld pictures", white)
            self.library.set_state(COURTAULD_WHITE_KEY, True)
        if not self.library.get_state(TEST_LICENCES_KEY):
            if moved := relabel_test_licences(self.library):
                log.info("%d works of the test switches now under private use", moved)
            self.library.set_state(TEST_LICENCES_KEY, True)
        # The museums' pictures as Commons keeps them, when a museum's image
        # server turns us away (the AIC's IIIF behind a Cloudflare challenge)
        # or does not answer (the MNK's, 2026-11-07).
        copies = CommonsCopies(lambda: self.images.http())
        for source in MIRRORED:
            self.images.mirrors[source] = copies
        # Before the player trims or grows the catalogue: the app's limit wins.
        self.storage = StorageStore(settings, self.library, self.images, self.store)
        # Keys of art sources, entered in the app.
        self.source_keys = SourceKeys(settings, self.library)
        # Tailscale built into the app: the key its phones join with.
        self.tailnet = Tailnet(self.library)
        self.importer = Importer(
            self.library,
            self.images,
            self.palette,
            access=self._access,
        )
        self.importer.fragments = Fragments(settings.data_dir / "fragments.json", museum_client)
        self.status = StatusMonitor(self.panel, self.library)
        # The owner's phone hears of the battery, failed sends, new pictures.
        self.notifier = Notifier(settings.data_dir, self.library)
        self.notifier.base_url = settings.base_url  # works' pictures for the phone
        self.status.on_battery_level = self.notifier.battery
        self.status.on_firmware = self.notifier.firmware
        self.status.on_mac = self.panel_config.learn_mac
        self.progress.on_end = lambda stage, title, message: self.notifier.ended(
            stage == Stage.FAILED, title, message, self.progress.item_id
        )
        self.progress.on_change = self.notifier.progress_changed
        self.notifier.progress = self.progress.view
        self.notifier.tz = self._tz
        self.progress.restore(self.library.get_state(PROGRESS_KEY, {}))
        self.progress.on_learn = lambda learned: self.library.set_state(PROGRESS_KEY, learned)
        self.progress.likely_asleep = lambda: self.status.sleeping
        self.app = PanelApp(self)
        self.player = Player(self)
        #: Originals of Favourites and manual/album playlists, always here.
        self.kept = KeptOriginals(self)
        self.power = PowerManager(self)
        self.albums = Albums(self)
        # The language model: keywords and Polish texts; idle without a key.
        self.ai_config = AiConfigStore(settings, self.library)
        self.claude = Claude(self.ai_config, self.library)
        # Polish words typed in Szukaj, in English for the museums abroad.
        self.search_words = SearchWords(self.library, self.claude, self.ai_config)
        self.importer.translate = self.search_words.wording
        self.library.wording = self.search_words.known
        # The museum's labels on a work's card ("Painting", "Italy") in Polish.
        self.museum_words = MuseumWords(self.library, self.claude, self.ai_config)
        self.ai = AiWorker(self.library, self.images, self.claude, self.ai_config)
        self.ai.register(KeywordsJob(self.library, self.images, self.ai_config))
        self.pl_text = PlTextJob(self.library, self.images, self.ai_config)
        self.ai.register(self.pl_text)
        # Discover's work of the day and its page.
        self.daily = Daily(
            self.library,
            self.player,
            self.ai,
            DailyJob(self.library, self.images, self.ai_config),
        )
        self.ai.register(self.daily.job)
        # Which of the day's best works is worth a page (Sonnet, once a day).
        self.daily.claude = self.claude
        # What Wikidata knows of each work, kept on disk across updates.
        self.pl_text.wikidata.kept = self.daily.job.wikidata.kept = records(settings.data_dir)
        # Discover's curator: two cards of "Dziś dla Ciebie", ordered at night.
        self.curator = Curator(self.library, self.claude, self.ai_config, self.player.taste)
        # What the pages say a work led to, looked up in the museums and on Wikipedia.
        self.later = LaterWorks(self.library, lambda q, n: self.importer.search_all(q, n))
        self.daily.later = self.later
        # Other works by a study's artist, from the museums when the catalogue has too few.
        self.artists = ArtistWorks(
            self.library, lambda q, n: self.importer.search_all(q, n), self.images
        )
        self.daily.artists = self.artists
        # How big each study's work really is, from its museum or Wikidata.
        self.sizes = Sizes(self.library)
        # Studies of any work, asked for on its card.
        # Sharper copies of works whose own picture is poor: looked for when
        # a card opens, and for the work of the day before its page.
        self.sharper = Sharper(self.library, self.importer, self.images, copies.file)
        # One work under other titles, and details of works, by their pictures.
        self.twins = Twins(self.library, self.images)
        # Works taken in from the museums are laid over their artist's at once.
        self.importer.taken = self.twins.after_search
        # What the pictures could not settle, judged at night (Haiku, Batch API).
        self.twins_judge = NightJudge(
            self.library, self.images, self.twins, self.claude, self.ai_config
        )
        # What pictures from Commons, Europeana, Openverse and WikiArt really
        # are, and a few works a night looked over (Haiku and its critic).
        self.gatekeeper = Gatekeeper(self.library, self.images, self.claude, self.ai_config)
        self.audit = Audit(self.library, self.images, self.claude, self.ai_config)
        # Favourites, playlists and Discover's works first in the night's
        # tidying (Mateusz 2026-11-11).
        self.cared = Cared(self)
        for tidier in (self.twins, self.twins_judge, self.gatekeeper, self.audit):
            tidier.cared = self.cared.ranks
        self.daily.sharper = self.sharper
        self.copies = Copies(self.sharper)
        # The museums of works from Commons, Openverse, WikiArt: looked up
        # when a card opens and at night.
        self.holders = Holders(self.library, museum_client)
        self.copies.work_qid = self.holders.work_qid
        # How works are made, where their source does not say (the app
        # paints a work's colours in its technique): on the card and at night.
        self.media = Media(self.library, self.importer, self.holders)
        # The study's "Droga dzieła": the museum's provenance retold (Haiku).
        self.journeys = Journeys(
            self.library,
            self.claude,
            self.ai_config,
            work_qid=self.holders.work_qid,
            data_dir=settings.data_dir,
        )
        # Commons' tile sets in place of works' pictures (deeper zoom).
        self.sharper.tiled_copies = self.copies.tiled_copies
        self.sharper.is_tiled = self.copies.tiled
        # Where works are, for Szukaj's "Muzeum": the museums' Wikidata
        # items, names and cities, learnt at night (library/places.py).
        self.museum_places = MuseumPlaces(self.library, museum_client)
        self.artist_people = ArtistPeople(self.library, museum_client)
        # Town names of photos' coordinates: after each album sync and at night.
        self.places = Places(self.library)
        self.study = Study(self.daily, self.ai, StudyJob(self.library, self.images, self.ai_config))
        self.ai.register(self.study.job)
        # Facts about a work from the web, for its page (Sonnet with the web search).
        self.web_facts = WebFacts(self.library, self.claude, self.ai_config)
        self.daily.job.web_facts = self.study.job.web_facts = self.web_facts.for_study
        # The studies written before them filled in with the facts, where
        # they add much, at the owner's tap (Konfiguracja).
        self.study_refresh = StudyRefresh(self.library, self.claude, self.web_facts)
        # Its steps on the Lock Screen, and "Studium gotowe" at the end.
        self.study.on_step = self._study_step
        # Favourite artists' birthdays, for the notifications.
        self.births = Births(self.library)
        # The composition written again for pages written before (as the owner
        # lets it) and for pages left without one.
        self.compose = ComposeJob(self.daily.job)
        self.ai.register(self.compose)
        # The pen sketches of pages drawn by an earlier pen (or by none), drawn
        # again at night.
        pen = PenJob(self.compose)
        self.ai.register(pen)
        # The study sheets the analyses are drawn on, made ahead in the background.
        self.sheets = Sheets(self.library, self.images)
        # Those sheets drawn by the image model, where the owner gave Google's key:
        # not for a take about to be made anew, through Google's Batch for the
        # Studium dnia written a day ahead; a take they cover needs no pen.
        self.painter = Painter(self.ai_config, self.claude)
        self.drawn = DrawnSheets(self.library, self.images, self.painter)
        self.drawn.replacing = lambda item_id: (
            self.compose.enabled() and item_id in self.compose.waiting()
        )
        self.drawn.to_come = self._to_come
        pen.drawn = self._drawn_covers
        # Small pictures of works drawn again larger by the same model
        # ("Kreatywny restaurator"), kept as the owner's pick.
        self.restorer = Restorer(self.library, self.images, self.sharper, self.painter)
        # How a work was painted, when a technical study of it was found.
        self.stages = PaintingStages(
            self.library, self.images, self.painter, self.web_facts, self.ai_config
        )
        # How the museums' works look, as Google's numbers: Szukaj by how a
        # work looks or by a photograph, and the works that look alike
        # (Mateusz 2026-11-13, "G1"); those cared about first.
        self.looks = Looks(
            self.library, self.images, self.painter, self.ai_config, settings.data_dir / "looks"
        )
        self.looks.cared = self.cared.ranks
        # Szukaj's words for how works look, the groups narrowing them, and
        # a smart playlist made of them (Mateusz 2026-11-13).
        self.library.looking = self.looks.looking
        self.library.look_near = self.looks.near
        # The museums asked for a look by Haiku's searches, what they bring
        # judged by how it looks (Mateusz 2026-11-13, card).
        self.look_words = LookWords(self.library, self.claude, self.ai_config)
        self.importer.look_searches = self.look_words.searches
        self.importer.judge_look = self.looks.judge
        self.daily.looks_like = self.looks.neighbours
        # A small picture is drawn larger first, before its study (Mateusz
        # 2026-11-13); which works get none: the rules, the sheet's pixels and
        # Haiku for a pale sheet between them, shared with the study of the day.
        self.study.restorer = self.restorer
        self.study.gate = StudyGate(
            self.library,
            self.images,
            self.claude,
            self.study.job.enabled,
            self.daily.unfit,
        )
        self.daily.study_unfit = self.study.gate.unfit
        # The composition text of pages written before, rewritten once in one
        # voice (their marks stay).
        self.prose = ProseJob(self.daily.job)
        self.ai.register(self.prose)
        # The artist's line of life and the work's paints for pages written
        # before the page's question asked for them.
        self.extras = ExtrasJob(self.daily.job)
        self.ai.register(self.extras)
        # The owner's "Popraw detale": a page's details checked over their cuts.
        self.mend = MendJob(self.library, self.images, self.ai_config)
        self.ai.register(self.mend)
        # What Claude's month leaves at its end goes on more studies.
        self.leftover = Leftover(
            self.library,
            self.ai_config,
            self.claude,
            self.ai,
            self.daily,
            self.study,
            self.player,
            self.cared.ranks,
        )

        #: Heavy work at night, while the server runs its background.
        self.night: NightQueue | None = None

        self._tasks: set[asyncio.Task[object]] = set()

    def _study_step(self, item: Item, status: str, error: str) -> None:
        """A study's step to its Live Activities, "Studium gotowe" at the
        end; one ordered from the month's rest tells nobody (Mateusz
        2026-11-13: "dla tych automatycznych bez powiadomień"), unless
        someone follows it on the Lock Screen."""
        if (
            status in ("ready", "failed")
            and self.leftover.settle(item.id, status)
            and not self.notifier.study_activities(item.id)
        ):
            return
        self.notifier.study_step(
            item.id,
            status,
            error,
            notifications.item_title(self, item) if status == "ready" else "",
            self.study.progress(item.id),
        )

    def _to_come(self, item_id: str) -> bool:
        """The work is the work of a day still to come."""
        day = self.daily.day_of(item_id)
        return day is not None and day > date.today()

    def _drawn_covers(self, item_id: str, view: View) -> bool:
        item = self.library.get(item_id)
        return item is not None and self.drawn.covers(item, view)

    def _access(self) -> Access:
        """What the owner lets art sources return, and their credentials."""
        chosen, config, keys = self.player.settings, self.settings, self.source_keys
        app = None
        if config.openverse_client_id and config.openverse_client_secret:
            app = (config.openverse_client_id, config.openverse_client_secret)
        wikiart = None
        if (codes := keys.get("wikiart")) and ":" in codes:
            access, _, secret = codes.partition(":")
            wikiart = (access, secret)
        return Access(
            private_use=chosen.private_use,
            europeana_key=keys.get("europeana") or config.europeana_key,
            openverse_app=app,
            smithsonian_key=keys.get("si") or "",
            paris_token=keys.get("paris") or "",
            wikiart_keys=wikiart,
            data_dir=config.data_dir,
            sources_off=frozenset(chosen.sources_off),
        )

    @property
    def calibrated_palette_path(self) -> Path:
        return self.settings.data_dir / "palette.json"

    def _initial_palette(self) -> Palette:
        # A palette measured in the app wins over the configured default.
        path = self.calibrated_palette_path
        if path.is_file():
            try:
                return Palette.load(path)
            except (OSError, ValueError, KeyError) as err:
                log.warning("ignoring unreadable %s: %s", path, err)
        return get_palette(self.settings.palette)

    def set_palette(self, palette: Palette | None) -> Palette:
        """Use and keep a calibrated palette; None goes back to the default."""
        if palette is None:
            self.calibrated_palette_path.unlink(missing_ok=True)
            palette = get_palette(self.settings.palette)
        else:
            self.settings.data_dir.mkdir(parents=True, exist_ok=True)
            palette.save(self.calibrated_palette_path)
        self.palette = palette
        self.importer.palette = palette
        return palette

    @property
    def device_configured(self) -> bool:
        return bool(self.settings.device_host and self.settings.device_pin)

    def background(self, coro: Coroutine[object, object, object]) -> asyncio.Task[object]:
        """Run a coroutine after the response; keeps a reference until done."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def prepare(
        self,
        image: bytes | list[bytes],
        render_settings: RenderSettings | None,
        *,
        raw: bool = False,
        fmt: str | None = None,
        title: str = "",
        description: str = "",
        source: str = "",
        extra: dict[str, object] | None = None,
        seed: str = "",
    ) -> ContentInfo:
        """Render (or pass through untouched with ``raw``) and publish.

        Several images are one board of photos (MULTI); ``seed`` keeps its
        automatic grid the same on a redraw."""
        if raw and not isinstance(image, list):
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
        done = self.render_content(image, settings, fmt=fmt, seed=seed)
        return self.store.publish(
            done.data,
            done.ext,
            preview_png=done.preview_png,
            title=title,
            description=description,
            source=source,
            render=settings.model_dump(mode="json") | {"palette": self.palette.name},
            extra=extra,
        )

    def render_content(
        self,
        image: bytes | list[bytes],
        settings: RenderSettings,
        *,
        fmt: str | None = None,
        seed: str = "",
    ) -> Rendered:
        """The panel's image and the app's preview; a render made ahead of
        time (``Player.render_ahead``) with the same inputs is reused."""
        palette = self.palette
        images = image if isinstance(image, list) else [image]
        key = render_key(
            images,
            settings.model_dump_json(),
            repr(palette),
            fmt or "",
            seed if isinstance(image, list) else "",
        )

        def make() -> Rendered:
            if isinstance(image, list):
                result = render_multi(image, settings, palette, seed=seed)
            else:
                result = render(image, settings, palette)
            data, ext = result.encode(fmt)  # type: ignore[arg-type]
            preview = result.original_image()  # the app shows the picture, not the dither
            preview.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
            return Rendered(data, ext, encode_image(preview, "png"))

        return self.rendered.get(key, make)

    async def push_current(self, wait: float = 90.0) -> PushOutcome:
        """The frame's app asks for its pictures (panel_app.py): awake (on the
        charger) it does within seconds; asleep with the Wi-Fi on, Wake-on-LAN
        makes it ask, unless its alarm rings for this very change, and a
        panel up with its app not running gets the app started over MDC; in
        deep sleep the picture waits for the alarm or the button. A panel that does not run the
        app gets it installed and started first."""
        content = self.store.current()
        if content is None:
            raise RuntimeError("Nie ma jeszcze obrazu do wysłania.")
        url = f"{self.settings.base_url()}{self.app.image_path(content)}"
        app, power, progress = self.app, self.power, self.progress
        if not progress.active:
            progress.begin(
                content.title,
                render=False,
                origin=self.player.state.last_change_origin,
                item_id=notifications.shown_item_id(content),
            )
        file_id = content.file_id
        now = datetime.now(UTC)
        wake = app.wakes_at()
        ringing = wake is not None and abs(wake - now) < WAKE_SOON
        if not (app.active and app.deep_asleep() and not ringing):
            # Asleep with the Wi-Fi off nothing is sent: no "Łączę się z ramką".
            progress.advance(Stage.SENDING)
        self.store.expect_fetch(file_id)
        timeout = 0.0
        if not app.active and app.ensure_package() is None:
            # Nothing to install: the Samsung certificates are not here yet.
            self.store.cancel_fetch(file_id)
            power.mark_pending(True)
            message = NO_CERTIFICATES
            progress.finish(Stage.WAITING, message)
            return PushOutcome(
                content, pushed=False, fetched=False, content_url=url, message=message
            )
        try:
            if not app.active:
                await app.install()  # wakes the panel if need be
                timeout = max(wait, INSTALL_LOOK.total_seconds())
            elif app.awake():
                timeout = max(wait, POLL.total_seconds() + 30)
            elif ringing:
                assert wake is not None
                timeout = max(wait, (wake - now).total_seconds() + 120)
            elif not app.deep_asleep():
                # Wake-on-LAN until the app asks; a panel that is up (the
                # button) with its app not running gets the app started over
                # MDC (the launcher seldom does after a cold boot). Without a
                # MAC address only a panel up already.
                mac = bool(self.settings.device_mac)
                if mac or await app.panel_answers():
                    progress.advance(Stage.WAKING)
                    woke, _ = await power.reach(wol=mac)
                    timeout = wait if woke else 0.0
            fetched = await self.store.wait_for_fetch(file_id, timeout) if timeout else False
        except MdcError as err:
            log.info("could not start the frame's app for a picture: %s", err)
            fetched = False
        finally:
            self.store.cancel_fetch(file_id)
        self.status.note_push(fetched)
        if fetched:
            power.mark_pending(False)
            progress.advance(Stage.DOWNLOADING)
            app.follow(file_id)  # refreshing once the app has it all
            return PushOutcome(content, pushed=True, fetched=True, content_url=url)
        power.mark_pending(True)
        wake = app.wakes_at()
        message = self._waiting_reason(wake)
        progress.finish(Stage.WAITING, message, wakes_at=wake)
        return PushOutcome(content, pushed=False, fetched=False, content_url=url, message=message)

    def _tz(self) -> tzinfo:
        return self.player.settings.tz()

    def _waiting_reason(self, wake: datetime | None) -> str:
        """Why a picture waits, under "Pojawi się dziś o 10:00" in the app
        (the bar says when): said in Polish, as the app shows it."""
        app = self.app
        if app.deep_asleep():
            economy = self.player.settings.power_mode == "economy"
            rest = app.state.off or app.state.rest_until is not None
            if economy and not app.state.wifi_lost and not rest:
                return "Ramka jest w trybie oszczędnym."
            return "Ramka śpi bez Wi-Fi."
        if wake is not None:
            return "Ramka nie odpowiada."
        return "Ramka pobierze go, gdy się obudzi."

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
