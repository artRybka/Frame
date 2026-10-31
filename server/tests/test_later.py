"""What a work led to ("Co z niego wyrosło"): later works looked up in the
museums and on Wikipedia, once, with what was found kept."""

from __future__ import annotations

from typing import Any

import httpx

from frame_server.ai.daily import Legacy
from frame_server.later import LaterWorks, same_work
from frame_server.library import Item, ItemKind
from frame_server.service import FrameService

WAVE = Legacy(
    year="1897",
    who="Camille Claudel",
    title="Fala",
    text="Trzy kąpiące się kobiety pod falą z onyksu.",
    search="Claudel The Wave",
)
LETTER = Legacy(
    year="1888", who="Vincent van Gogh", title="List do Thea", text="Pisze o fali.", search=""
)


def _work(item_id: str, title: str, artist: str) -> Item:
    return Item(
        id=item_id, source="met", source_id=item_id, kind=ItemKind.ARTWORK, title=title,
        artist=artist,
    )  # fmt: skip


def _wikipedia(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/w/api.php":
        query = request.url.params["srsearch"]
        titles = {
            "Camille Claudel Fala": ["Fala (rzeźba Camille Claudel)"],
            "Vincent van Gogh List do Thea": ["Vincent van Gogh"],
        }.get(query, [])
        return httpx.Response(200, json={"query": {"search": [{"title": t} for t in titles]}})
    title = request.url.path.rsplit("/", 1)[-1]
    pages: dict[str, dict[str, Any]] = {
        "Fala_(rzeźba_Camille_Claudel)": {
            "title": "Fala (rzeźba Camille Claudel)",
            "extract": "Rzeźba Camille Claudel z onyksu i brązu.",
            "thumbnail": {"source": "https://upload.wikimedia.org/fala.jpg"},
        },
        "Vincent_van_Gogh": {
            "title": "Vincent van Gogh",
            "extract": "Holenderski malarz.",
            "thumbnail": {"source": "https://upload.wikimedia.org/autoportret.jpg"},
        },
    }
    from urllib.parse import unquote

    page = pages.get(unquote(title))
    if page is None:
        return httpx.Response(404)
    lang = request.url.host.split(".")[0]
    link = f"https://{lang}.m.wikipedia.org/wiki/{title}"
    return httpx.Response(200, json={**page, "content_urls": {"mobile": {"page": link}}})


def test_a_museum_copy_needs_the_author_and_a_title_word() -> None:
    assert same_work(_work("met:9", "The Wave", "Camille Claudel"), WAVE)
    assert not same_work(_work("met:9", "The Waltz", "Camille Claudel"), WAVE)
    assert not same_work(_work("met:9", "The Wave", "Gustave Courbet"), WAVE)


def test_later_works_are_looked_up_once(service: FrameService) -> None:
    asked: list[str] = []
    museum = [
        _work("met:9", "The Waltz", "Camille Claudel"),
        _work("met:8", "The Wave", "Camille Claudel"),
    ]

    def search(query: str, limit: int) -> tuple[int, list[Item], list[str]]:
        asked.append(query)
        return len(museum), museum, []

    later = LaterWorks(service.library, search)
    later._http = httpx.Client(transport=httpx.MockTransport(_wikipedia))
    item = _work("met:1", "Under the Wave off Kanagawa", "Katsushika Hokusai")
    found = later.look(item, [WAVE, LETTER])
    wave, letter = found.values()
    assert wave.item is not None and wave.item.id == "met:8"
    assert wave.wiki_title == "Fala (rzeźba Camille Claudel)"
    assert wave.picture == "https://upload.wikimedia.org/fala.jpg"
    # The painter's own article: linked, without his portrait.
    assert letter.item is None
    assert letter.wiki_url.endswith("/Vincent_van_Gogh") and letter.picture == ""
    assert asked == ["Claudel The Wave"]  # no search words, no museum

    # Kept, not asked again.
    assert later.missing(item.id, [WAVE, LETTER]) == []
    assert later.look_soon(item, [WAVE, LETTER]) is False
    assert later.known(item.id) == found
