"""Museums' published dumps searched at home (library/dumps.py, Mateusz
2026-11-07): the same works as the museums' APIs, without asking them."""

from __future__ import annotations

import gzip
import io
import json
import random
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from frame_server.library import dumps
from frame_server.library.hosts import Resting
from frame_server.library.museums import Access, Discovery, museum


def _aic(work_id: int, title: str, kind: str = "Painting", **extra: Any) -> dict[str, Any]:
    return {
        "id": work_id,
        "title": title,
        "artist_title": "Claude Monet",
        "artist_display": "Claude Monet\nFrench, 1840-1926",
        "date_display": "1906",
        "date_start": 1906,
        "medium_display": "Oil on canvas",
        "artwork_type_title": kind,
        "style_titles": ["Impressionism"],
        "subject_titles": [],
        "classification_titles": ["painting"],
        "term_titles": [],
        "place_of_origin": "France",
        "image_id": f"img-{work_id}",
        "thumbnail": {"width": 3000, "height": 2000, "lqip": "data:image/gif;base64,AAAA"},
        "is_public_domain": True,
        "provenance_text": "x" * 1000,  # left out of the index
        **extra,
    }


def _tarball(records: list[dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as archive:
        for record in records:
            data = json.dumps(record).encode()
            info = tarfile.TarInfo(f"artic-api-data/json/artworks/{record['id']}.json")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        agent = json.dumps({"id": 1, "title": "Claude Monet"}).encode()
        info = tarfile.TarInfo("artic-api-data/json/agents/1.json")
        info.size = len(agent)
        archive.addfile(info, io.BytesIO(agent))
    return buffer.getvalue()


class Web:
    """Answers by URL start, with ETags; counts what was asked."""

    def __init__(self, files: dict[str, tuple[bytes, str]]) -> None:
        self.files = files
        self.asked: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.asked.append(url)
        for start, (body, etag) in self.files.items():
            if url.startswith(start):
                if request.headers.get("If-None-Match") == etag:
                    return httpx.Response(304)
                return httpx.Response(200, content=body, headers={"ETag": etag})
        return httpx.Response(404)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))


def _no_museum(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"the museum was asked: {request.url}")


def _museum(
    key: str,
    tmp_path: Path,
    answer: Callable[[httpx.Request], httpx.Response] = _no_museum,
    **access: Any,
) -> Any:
    http = httpx.Client(transport=httpx.MockTransport(answer))
    return museum(key, http, Access(data_dir=tmp_path, **access))


@pytest.fixture
def aic(tmp_path: Path) -> Web:
    records = [
        _aic(1, "Water Lilies", subject_titles=["water lilies"]),
        _aic(2, "Water Lily Pond", kind="Print", date_start=1890),
        _aic(3, "Not Free", is_public_domain=False),
        _aic(4, "No Picture", image_id=None),
        *(_aic(100 + n, f"Haystacks {n}") for n in range(30)),
    ]
    web = Web({dumps.AicDump.url: (_tarball(records), '"v1"')})
    assert dumps.INDEXES.refresh(dumps.DUMPS["aic"], tmp_path, older=0, http=web.client())
    return web


def test_the_aic_is_searched_at_home(tmp_path: Path, aic: Web) -> None:
    source = _museum("aic", tmp_path)  # any request to the museum fails the test
    total, items = source.search("haystacks", 10, 2)
    assert total == 30 and len(items) == 10
    assert items[0].image_url.startswith("https://www.artic.edu/iiif/2/img-")
    # Works not free to show, or without a picture, are not in it.
    assert source.fetch("1") is not None and source.fetch("1").title == "Water Lilies"


def test_the_index_keeps_only_what_the_mapping_reads(tmp_path: Path, aic: Web) -> None:
    index = dumps.local_index("aic", tmp_path)
    assert index is not None
    record = index.get("1")
    assert record is not None
    assert "provenance_text" not in record and "lqip" not in record["thumbnail"]
    assert index.get("3") is None and index.get("4") is None


def test_draws_and_kinds_come_from_home(tmp_path: Path, aic: Web) -> None:
    source = _museum("aic", tmp_path)
    total, items = source.discover(Discovery(kind="print"), 24, 1)
    assert total == 1 and items[0].id == "aic:2"
    total, _ = source.discover(Discovery(kind="painting", year_from=1900, year_to=1910), 24, 1)
    assert total == 31
    total, _ = source.discover(Discovery(kind="painting", year_from=1800, year_to=1899), 24, 1)
    assert total == 0
    total, _ = source.discover(Discovery(style="Impressionism"), 24, 1)
    assert total == 32
    drawn = list(source.random_draw(Discovery(kind="painting"), random.Random(1)))
    assert len(drawn) == 31 and len({i.id for i in drawn}) == 31


def test_too_few_at_home_asks_the_museum_and_keeps_home_when_it_rests(
    tmp_path: Path, aic: Web
) -> None:
    asked: list[str] = []

    def api(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        body = {"data": [_aic(9, "Water Lilies (Agapanthus)")], "pagination": {"total": 3}}
        return httpx.Response(200, json=body)

    total, items = _museum("aic", tmp_path, api).search("water lily", 24, 1)
    assert asked and total == 3 and [i.id for i in items] == ["aic:9"]

    def walled(request: httpx.Request) -> httpx.Response:
        raise Resting("api.artic.edu turned us away", request=request)

    total, items = _museum("aic", tmp_path, walled).search("water lily", 24, 1)
    assert total == 2 and {i.id for i in items} == {"aic:1", "aic:2"}


def test_an_unchanged_dump_is_not_read_again(tmp_path: Path, aic: Web) -> None:
    path = dumps.index_path(tmp_path, "aic")
    built = path.stat().st_mtime
    aic.asked.clear()
    path.touch()
    import os

    os.utime(path, (built - 10, built - 10))
    assert dumps.INDEXES.refresh(dumps.DUMPS["aic"], tmp_path, older=0, http=aic.client())
    assert aic.asked == [dumps.AicDump.url]  # answered 304
    assert path.stat().st_mtime > built - 10  # fresh for another two months
    assert dumps.local_index("aic", tmp_path) is not None


def test_without_an_index_the_museum_is_asked_as_before(tmp_path: Path) -> None:
    asked: list[str] = []

    def api(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(200, json={"data": [_aic(9, "Iris")], "pagination": {"total": 1}})

    total, items = _museum("aic", tmp_path, api).discover(Discovery(kind="painting"), 24, 1)
    assert asked and total == 1 and items[0].id == "aic:9"


def _cma(work_id: int, title: str, kind: str = "Painting") -> dict[str, Any]:
    return {
        "id": work_id,
        "share_license_status": "CC0",
        "title": title,
        "creators": [{"description": "Claude Monet (French, 1840-1926)", "role": "artist"}],
        "creation_date": "1906",
        "creation_date_earliest": 1906,
        "technique": "oil on canvas",
        "type": kind,
        "culture": ["France, 20th century"],
        "url": f"https://clevelandart.org/art/{work_id}",
        "images": {
            "web": {"url": f"https://cdn.example/{work_id}_web.jpg", "width": "900", "height": 600},
            "print": {"url": f"https://cdn.example/{work_id}_print.jpg", "width": "3400"},
        },
        "exhibitions": {"current": [{"title": "left out"}]},
    }


def test_cleveland_s_file_and_its_highlights(tmp_path: Path) -> None:
    records = [_cma(1, "Water Lilies"), _cma(2, "The Red Kerchief"), _cma(3, "Vase", "Ceramic")]
    text = "[\n" + ",\n".join(json.dumps(r, indent=2) for r in records).replace("\n", "\n  ")
    text = "[\n  " + text[2:] + "\n]\n"
    web = Web(
        {
            dumps.ClevelandDump.url: (text.encode(), '"c1"'),
            "https://openaccess-api.clevelandart.org/api/artworks/": (
                json.dumps({"data": [{"id": 2}]}).encode(),
                '"h"',
            ),
        }
    )
    assert dumps.INDEXES.refresh(dumps.DUMPS["cma"], tmp_path, older=0, http=web.client())
    source = _museum("cma", tmp_path)
    total, items = source.discover(Discovery(kind="painting"), 24, 1)
    assert total == 2
    total, items = source.discover(Discovery(kind="painting", highlight=True), 24, 1)
    assert total == 1 and items[0].title == "The Red Kerchief" and items[0].highlight
    assert source.fetch("3") is not None
    assert "exhibitions" not in (dumps.local_index("cma", tmp_path).get("1") or {"x": 1})


def _wellcome(work_id: str, title: str, licence: str = "pdm", kind: str = "k") -> str:
    return json.dumps(
        {
            "id": work_id,
            "title": title,
            "workType": {"id": kind},
            "availabilities": [{"id": "online"}],
            "thumbnail": {
                "url": f"https://iiif.wellcomecollection.org/thumbs/{work_id}/full/!200,200/0/default.jpg",
                "license": {"id": licence},
            },
            "genres": [{"label": "Paintings", "concepts": [{"label": "Paintings"}]}],
            "physicalDescription": "1 painting : oil on canvas",
            "production": [{"dates": [{"label": "1820"}], "places": [{"label": "London"}]}],
            "contributors": [{"agent": {"label": "John Smith", "type": "Person"}, "primary": True}],
            "subjects": [{"label": "Horses"}],
            "items": [{"big": "left out"}],
        },
        separators=(",", ":"),
    )


def test_wellcome_s_pictures_from_its_catalogue(tmp_path: Path) -> None:
    lines = [
        _wellcome("a1", "A horse in a field."),
        _wellcome("a2", "A horse at rest.", licence="cc-by"),
        _wellcome("b1", "A book about horses.", kind="a"),
    ]
    packed = gzip.compress(("\n".join(lines) + "\n").encode())
    web = Web({dumps.WellcomeDump.url: (packed, '"w1"')})
    assert dumps.INDEXES.refresh(dumps.DUMPS["wellcome"], tmp_path, older=0, http=web.client())
    total, items = _museum("wellcome", tmp_path).discover(Discovery(kind="painting"), 24, 1)
    assert total == 1 and items[0].id == "wellcome:a1" and items[0].year == 1820
    # A licence for private use only: with "Użytek prywatny" only.
    private = _museum("wellcome", tmp_path, private_use=True)
    total, items = private.discover(Discovery(kind="painting", year_from=1800), 24, 1)
    assert total == 2 and {i.id for i in items} == {"wellcome:a1", "wellcome:a2"}


def _si(work_id: str, unit: str, title: str) -> str:
    return json.dumps(
        {
            "id": work_id,
            "unitCode": unit,
            "title": title,
            "content": {
                "descriptiveNonRepeating": {
                    "title": {"content": title},
                    "unit_code": unit,
                    "record_link": f"https://collections.si.edu/{work_id}",
                    "online_media": {
                        "media": [
                            {
                                "type": "Images",
                                "idsId": f"ids-{work_id}",
                                "usage": {"access": "CC0"},
                            }
                        ]
                    },
                },
                "freetext": {
                    "name": [{"label": "Artist", "content": "Winslow Homer, 1836 - 1910"}],
                    "date": [{"label": "Date", "content": "1880"}],
                },
                "indexedStructured": {"object_type": ["Paintings"], "date": ["1880s"]},
            },
        }
    )


def test_the_smithsonian_s_art_museums_from_its_bucket(tmp_path: Path) -> None:
    from frame_server.library.smithsonian import UNITS

    bucket = dumps.SmithsonianDump.bucket
    listing = (
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<Contents><Key>metadata/edan/{u}/00.txt</Key><ETag>e-{u}</ETag></Contents>"
        "<Contents><Key>metadata/edan/{u}/index.txt</Key><ETag>i</ETag></Contents>"
        "</ListBucketResult>"
    )
    asked: list[str] = []

    def s3(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        path = request.url.path
        if path == "/":
            unit = request.url.params["prefix"].split("/")[2]
            return httpx.Response(200, text=listing.format(u=unit))
        if path == "/metadata/edan/saam/00.txt":
            lines = [_si("s1", "SAAM", "Breezing Up"), _si("s2", "SAAM", "The Gulf Stream")]
            return httpx.Response(200, text="\n".join(lines) + "\n")
        return httpx.Response(200, text="")

    http = httpx.Client(transport=httpx.MockTransport(s3))
    assert dumps.INDEXES.refresh(dumps.DUMPS["si"], tmp_path, older=0, http=http)
    assert len([a for a in asked if a.endswith(".txt")]) == len(UNITS)  # not the index files
    source = _museum("si", tmp_path, smithsonian_key="key")
    total, items = source.discover(Discovery(kind="painting", year_from=1870, year_to=1890), 24, 1)
    assert total == 2 and items[0].museum == "Smithsonian American Art Museum"
    # Nothing changed in the bucket's lists: the files are not read again.
    asked.clear()
    path = dumps.index_path(tmp_path, "si")
    import os

    os.utime(path, (1, 1))
    http = httpx.Client(transport=httpx.MockTransport(s3))
    assert dumps.INDEXES.refresh(dumps.DUMPS["si"], tmp_path, older=0, http=http)
    assert not [a for a in asked if a.endswith(".txt")]
    assert bucket in asked[0]


def test_a_failed_build_keeps_the_index_there_was(tmp_path: Path, aic: Web) -> None:
    broken = Web({dumps.AicDump.url: (b"not a tarball", '"v2"')})
    path = dumps.index_path(tmp_path, "aic")
    import os

    os.utime(path, (1, 1))
    assert dumps.INDEXES.refresh(dumps.DUMPS["aic"], tmp_path, older=0, http=broken.client())
    total, _ = _museum("aic", tmp_path).search("haystacks", 24, 1)
    assert total == 30
    dumps.INDEXES.failed_at.clear()
