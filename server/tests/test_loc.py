"""The Library of Congress: free photographs only, asked only for Fotografia."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from frame_server.library.importer import Importer
from frame_server.library.loc import (
    COLLECTIONS,
    IIIF,
    SERVICE,
    LibraryOfCongress,
    loc_mirrors,
    person,
)
from frame_server.library.museums import PRIVATE_LICENCE, Access, Discovery
from frame_server.library.repo import Library
from frame_server.library.vocabulary import PHOTOGRAPHY, category_fits, set_aside

PATH = "pnp/fsac/1a33000/1a33800/1a33833"


def _result(**changes: Any) -> dict[str, Any]:
    """A search result as www.loc.gov gives it (half of it under "item")."""
    result: dict[str, Any] = {
        "access_restricted": False,
        "id": "http://www.loc.gov/item/2017877382/",
        "number_lccn": ["2017877382"],
        "dates": ["1939"],
        "title": "Farm auction, Derby, Conn.",
        "mime_type": ["image/gif", "image/jpg", "image/tif"],
        "image_url": [
            f"{SERVICE}{PATH}_150px.jpg#h=105&w=150",
            f"{SERVICE}{PATH}t.gif#h=105&w=150",
            f"{SERVICE}{PATH}r.jpg#h=450&w=640",
            f"{SERVICE}{PATH}v.jpg#h=719&w=1024",
        ],
        "item": {
            "contributors": ["Delano, Jack, 1914-1997, photographer"],
            "creators": [{"role": "photographer", "title": "Delano, Jack, 1914-1997"}],
            "created_published_date": "1940 Sept.",
            "medium": ["1 slide : color."],
            "genre": ["Slides--Color"],
            "rights_advisory": "No known restrictions on publication.",
            "source_collection": "FSA/OWI color slides and transparencies",
            "subject_headings": ["Auctions--Connecticut--Derby", "Farms"],
        },
    }
    item = {**result["item"], **changes.pop("item", {})}
    return {**result, **changes, "item": item}


def test_free_photographs_become_works() -> None:
    loc = LibraryOfCongress(httpx.Client())
    work = loc._map(_result())
    assert work is not None
    assert work.id == "loc:2017877382" and work.museum == "Library of Congress"
    assert work.artist == "Jack Delano" and work.artist_bio == "1914–1997"
    assert work.year == 1940 and work.date_text == "1940 Sept."
    assert work.subjects == ["Auctions", "Farms"]
    master = f"{IIIF}/master:{PATH.replace('/', ':')}u/full/!2560,2560/0/default.jpg"
    assert work.image_url == master and work.thumb_url == f"{SERVICE}{PATH}r.jpg"
    # A photograph: only with Fotografia, never in the catalogue.
    assert category_fits(work, [PHOTOGRAPHY]) and set_aside(work)
    # When the full scan is kept under another name: the service copies.
    assert loc_mirrors(work) == [f"{SERVICE}{PATH}v.jpg", f"{SERVICE}{PATH}r.jpg"]
    assert loc_mirrors(work, thumb=True) == []
    # Without a scan, the 1024 px copy.
    copy = loc._map(_result(mime_type=["image/jpg"]))
    assert copy is not None and copy.image_url == f"{SERVICE}{PATH}v.jpg"


def test_restricted_prints_and_captions_are_left_out() -> None:
    loc = LibraryOfCongress(httpx.Client())
    assert loc._map(_result(access_restricted=True)) is None
    unknown = {"rights_advisory": "Rights status not evaluated."}
    assert loc._map(_result(item=unknown)) is None
    caption = {"medium": ["1 item (photo caption) : typescript."], "genre": ["Captions"]}
    assert loc._map(_result(item=caption)) is None
    engraving = {"medium": ["1 print : engraving."], "genre": ["Portrait prints"]}
    assert loc._map(_result(item=engraving)) is None
    stereo = {"medium": ["1 photographic print on stereo card"], "genre": ["Stereographs"]}
    assert loc._map(_result(item=stereo)) is None
    assert loc._map(_result(number_lccn=[], id="http://www.loc.gov/item/fsa1998/PP/")) is None


def test_photographs_not_cleared_only_for_private_use() -> None:
    unknown = _result(item={"rights_advisory": "Rights status not evaluated."})
    assert LibraryOfCongress(httpx.Client())._map(unknown) is None
    home = LibraryOfCongress(httpx.Client(), access=Access(private_use=True))
    work = home._map(unknown)
    assert work is not None and work.license == PRIVATE_LICENCE
    assert home._map(_result()).license == "No known restrictions"  # type: ignore[union-attr]
    # Only a thumbnail outside the library: not even then.
    assert home._map(_result(access_restricted=True)) is None


def test_names_of_photographers() -> None:
    assert person("Lange, Dorothea, photographer") == ("Dorothea Lange", "")
    assert person("Brady, Mathew B., approximately 1823-1896, photographer") == (
        "Mathew B. Brady",
        "1823–1896",
    )
    assert person("Detroit Publishing Co., publisher") == ("Detroit Publishing Co", "")


def test_draws_take_turns_between_collections_and_only_for_photographs() -> None:
    asked: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        empty = "prokudin-gorskii" in request.url.path
        results = [] if empty else [_result()]
        return httpx.Response(200, json={"pagination": {"total": 5}, "results": results})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        loc = LibraryOfCongress(http)
        assert loc.discover(Discovery()) == (0, [])
        assert loc.discover(Discovery(kind="painting")) == (0, [])
        assert not asked
        total, items = loc.discover(Discovery(kind="photograph", year_from=1930), 8, 2)
        assert len(items) == 1 and total >= len(COLLECTIONS) * 9
        # Prokudin-Gorsky's turn, empty for those years: the photochroms'.
        paths = [r.url.path for r in asked]
        assert paths == ["/collections/prokudin-gorskii/", "/collections/photochrom-prints/"]
        assert asked[0].url.params["dates"] == "1930/2100"
        asked.clear()
        loc.discover(Discovery(kind="photograph"), 8, 4)
        assert asked[0].url.params["q"] == "negative"  # the FSA's negatives
        asked.clear()
        loc.search("Lange")
        assert asked[0].url.path == "/photos/" and asked[0].url.params["q"] == "Lange"


def test_only_a_search_for_photographs_asks_it(tmp_path: Path) -> None:
    importer = Importer(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
    assert "loc" in importer.sources()
    assert "loc" not in importer.asked_sources()
    assert "loc" not in importer.asked_sources("painting")
    assert "loc" in importer.asked_sources("photograph")
