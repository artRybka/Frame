import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image

# Lets tests import helper modules (fake_panel) that live next to them.
sys.path.insert(0, str(Path(__file__).parent))

#: Hosts the tests' own servers run on (uvicorn in the end-to-end test).
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}


def jpeg_bytes(color: tuple[int, int, int], size: tuple[int, int] = (320, 240)) -> bytes:
    import io

    img = Image.new("RGB", size, color)
    # A second colour block so palettes have some structure.
    img.paste((20, 20, 20), (0, 0, size[0] // 4, size[1] // 4))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True, scope="session")
def _offline() -> Iterator[None]:
    """No test reaches the internet, nor the background threads a test's
    service leaves behind: those outlive the test (and its ``monkeypatch``),
    and once asked the real museums (Yale answered 403) and logged it in the
    middle of another test, which read the log (2026-11-06). A request to
    anything but this machine fails at once as if offline.

    Nor is a big index built from a museum's site: the National Gallery of
    Art's (~230 MB), the Courtauld's, the Louvre's or the LoC's lists. Tests that want
    one build it from fake files themselves."""
    import httpx

    from frame_server.library import courtauld, dumps, louvre, met_index, nga

    def local(request: httpx.Request) -> None:
        if request.url.host not in LOCAL_HOSTS:
            raise httpx.ConnectError(f"tests are offline: {request.url.host}", request=request)

    sync = httpx.HTTPTransport.handle_request
    async_ = httpx.AsyncHTTPTransport.handle_async_request

    def handle(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        local(request)
        return sync(self, request)

    async def handle_async(
        self: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        local(request)
        return await async_(self, request)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(httpx.HTTPTransport, "handle_request", handle)
        patch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", handle_async)
        patch.setattr(nga.INDEX, "ready", lambda path: path.is_file())
        patch.setattr(courtauld.INDEX, "_start", lambda path: None)
        patch.setattr(louvre.INDEX, "_start", lambda path: None)
        patch.setattr(met_index.INDEX, "_start", lambda path: None)
        patch.setattr(dumps.INDEXES, "build_on_demand", False)
        yield


@pytest.fixture(autouse=True)
def _forget_artist_names() -> Iterator[None]:
    """Who is who among the artists is learnt by any library's term index:
    each test starts with nobody known."""
    from frame_server.library.artists import ArtistNames, learn

    learn(ArtistNames())
    yield
    learn(ArtistNames())


@pytest.fixture(autouse=True)
def _forget_places() -> Iterator[None]:
    """Museums learnt by a library (Szukaj's "Muzeum"): each test starts
    with only those of our own sources."""
    from frame_server.library.places import Places, learn_places

    learn_places(Places())
    yield
    learn_places(Places())


@pytest.fixture(autouse=True)
def _no_real_sizes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A study's page looks up its work's real size in the background: never
    on the internet in tests (each museum answers 404)."""
    import httpx

    from frame_server import sizes

    def offline() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))

    monkeypatch.setattr(sizes, "client", offline)


@pytest.fixture(autouse=True)
def _no_real_places(monkeypatch: pytest.MonkeyPatch) -> None:
    """Photos' towns are looked up after an album sync: never on the
    internet in tests (Nominatim answers 404)."""
    import httpx

    from frame_server import places

    def offline() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))

    monkeypatch.setattr(places, "client", offline)


@pytest.fixture
def service(tmp_path: Path):
    from frame_server.config import Settings
    from frame_server.service import FrameService

    settings = Settings(
        data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1"
    )
    svc = FrameService(settings)
    svc.ensure_initial_content()
    return svc


# Services in the tests start daemon threads (AI workers, the daily job,
# artist-works and study-details lookups) that can still be inside C code when
# the interpreter shuts down, which now and then crashed CI with exit 139 after
# every test had passed. Once pytest has reported, end the process with its
# own exit status instead of tearing those threads down.
_exit_status: int | None = None


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    global _exit_status
    _exit_status = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config: pytest.Config) -> None:
    if _exit_status is None:
        return
    import os

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_status)


@pytest.fixture(autouse=True)
def _no_web_facts(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """The facts from the web would be one more question before every page
    the fakes answer: asked only in ``test_web_facts``."""
    if request.module.__name__.endswith("test_web_facts"):
        return
    from frame_server.ai.web_facts import WebFacts

    monkeypatch.setattr(WebFacts, "enabled", lambda self: False)
