"""Sources added in November 2026: the national museums in Warsaw and
Kraków, the National Gallery of Art, Yale, the Smithsonian and the V&A."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, unquote

import httpx

from frame_server.library.museums import Access, Discovery, available, museum
from frame_server.library.muza import MuzaMuseum, NationalMuseumKrakow, NationalMuseumWarsaw, polish
from frame_server.library.nga import NationalGalleryOfArt, build
from frame_server.library.smithsonian import Smithsonian
from frame_server.library.vam import VictoriaAndAlbert
from frame_server.library.yale import YaleMuseums

MNW_OBJECT = {
    "id": 444620,
    "title": "Portret matki artysty",
    "masterpieces": True,
    "image": {"filePath": "07/e0/07e0a9", "extension": "jpg"},
    "authors": [{"name": "Malczewski, Jacek (1854-1929)", "role": "malarz"}],
    "createDates": [{"name": "ok. 1880"}],
    "createPlaces": [{"name": "Kraków"}],
    "types": [{"id": 116727, "name": "obraz"}],
    "techniques": [{"name": "olej"}],
    "materials": [{"name": "tektura"}],
    "inventoryNumber": "MP 123 MNW",
    "description": None,
}


def test_national_museums_take_public_domain_pictures() -> None:
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if "/object/" in request.url.path:
            closed = request.url.path.endswith("/2")
            rights = [{"id": 503 if closed else 500, "name": "DOMENA PUBLICZNA"}]
            body = {**MNW_OBJECT, "copyrights": rights, "publicDescriptions": []}
            return httpx.Response(200, json={"data": body})
        page = {"totalItemsCount": 1, "currentPage": 1}
        postcard = {**MNW_OBJECT, "id": 5, "image": {"filePath": "x", "extension": "tif"}}
        return httpx.Response(
            200, json={"data": {"paginatorDetails": page, "items": [MNW_OBJECT, postcard]}}
        )

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        mnw = NationalMuseumWarsaw(http)
        total, items = mnw.search("Malczewski", limit=5)
        mnw.discover(Discovery(kind="painting", style="landscape", year_from=1880, year_to=1900))
        assert mnw.discover(Discovery(kind="decorative")) == (0, [])
        found = mnw.fetch("444620")
        assert mnw.fetch("2") is None  # still under copyright
    assert total == 1 and [i.id for i in items] == ["mnw:444620"]
    item = items[0]
    assert item.artist == "Jacek Malczewski" and item.artist_bio == "1854–1929"
    assert item.year == 1880 and item.classification == "Painting" and item.highlight
    assert item.medium == "olej, tektura" and item.museum == "Muzeum Narodowe w Warszawie"
    assert item.image_url == "https://cyfrowe-cdn.mnw.art.pl/upload/multimedia/07/e0/07e0a9.jpg"
    assert "/upload/cache/multimedia_big/" in item.thumb_url
    assert item.url == "https://cyfrowe.mnw.pl/pl/katalog/444620"
    assert found is not None and found.id == item.id
    search = unquote(str(sent[0].url))
    assert "/search/Object/page/1?" in search and "maxPerPage=5" in search
    assert "filter[phrase]=Malczewski" in search and "filter[copyrights][]=500" in search
    assert "filter[types][]=116727" in search and "filter[types][]=117009" in search
    discover = unquote(str(sent[1].url))
    assert "filter[phrase]=pejzaż" in discover  # the app's words in Polish
    assert "filter[createDates][from]=1880" in discover
    assert "filter[types][]=116729" not in discover  # paintings only


def test_polish_dates_and_words() -> None:
    assert MuzaMuseum._year("lata 80. XIX w.") == 1880
    assert MuzaMuseum._year("koniec XIX w.") == 1890
    assert MuzaMuseum._year("około 1893 roku") == 1893
    assert MuzaMuseum._year("bez daty") is None
    assert polish("landscape") == "pejzaż" and polish("Malczewski") == "Malczewski"
    assert NationalMuseumKrakow.public_domain == 74188


def _csv(rows: list[dict[str, object]]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


NGA_FILES = {
    "published_images": [
        {"depictstmsobjectid": oid, "iiifurl": f"https://api.nga.gov/iiif/{iiif}",
         "viewtype": "primary", "openaccess": oa, "width": "3000", "height": "2400"}
        for oid, iiif, oa in (("1158", "abc", "1"), ("7", "def", "0"), ("9", "ghi", "1"))
    ],
    "constituents": [
        {"constituentid": "5", "forwarddisplayname": "Edgar Degas",
         "displaydate": "French, 1834 - 1917", "nationality": "French"},
    ],
    "objects_constituents": [
        {"objectid": "1158", "constituentid": "5", "displayorder": "1", "roletype": "artist"},
    ],
    "objects_terms": [
        {"objectid": "1158", "termtype": "Style", "term": "Impressionist"},
    ],
    "objects": [
        {"objectid": "1158", "title": "Before the Ballet", "displaydate": "1890/1892",
         "beginyear": "1890", "medium": "oil on canvas", "classification": "Painting",
         "creditline": "Widener Collection", "attribution": "Edgar Degas"},
        {"objectid": "7", "title": "Closed", "displaydate": "", "beginyear": "",
         "medium": "", "classification": "Painting", "creditline": "", "attribution": ""},
        {"objectid": "9", "title": "A jug", "displaydate": "", "beginyear": "1937",
         "medium": "watercolor", "classification": "Index of American Design",
         "creditline": "", "attribution": ""},
    ],
}  # fmt: skip


def test_national_gallery_of_art_searches_its_open_data(tmp_path: Path) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1].removesuffix(".csv")
        return httpx.Response(200, text=_csv(NGA_FILES[name]))

    path = tmp_path / "nga" / "collection.sqlite"
    path.parent.mkdir()
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        assert build(path, http) == 1  # not closed works, not the Index of American Design
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT title FROM works").fetchall() == [("Before the Ballet",)]

    access = Access(data_dir=tmp_path)
    assert "nga" in available(access) and "nga" not in available(Access())
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as http:
        nga = NationalGalleryOfArt(http, access=access)
        total, items = nga.search("degas ballet")
        assert nga.search("monet") == (0, [])
        assert nga.discover(Discovery(kind="painting", year_from=1880, year_to=1900))[0] == 1
        assert nga.discover(Discovery(kind="painting", year_from=1900))[0] == 0
        assert nga.discover(Discovery(style="impressionist"))[0] == 1
        found = nga.fetch("1158")
    assert total == 1 and found is not None
    item = items[0]
    assert item.id == "nga:1158" and item.artist == "Edgar Degas"
    assert item.artist_bio == "French, 1834 - 1917" and item.year == 1890
    assert item.styles == ["Impressionist"] and item.license == "CC0 1.0"
    assert item.image_url == "https://api.nga.gov/iiif/abc/full/!2560,2560/0/default.jpg"
    assert item.thumb_url == "https://api.nga.gov/iiif/abc/full/600,/0/default.jpg"


def _manifest(statement: str) -> dict[str, object]:
    def entry(label: str, value: str) -> dict[str, object]:
        return {"label": {"en": [label]}, "value": {"en": [value]}}

    return {
        "label": {"en": ["Claude Monet, Port-Domois, Belle-Isle, 1887"]},
        "metadata": [
            entry("Copyright Statement", statement),
            entry("Title", "Port-Domois, Belle-Isle"),
            entry("Creator(s)", "Artist: Claude Monet (French, 1840–1926)"),
            entry("Date", "1887"),
            entry("Medium", "Oil on canvas"),
            entry("Classification", "Paintings"),
            entry("Institution", "Yale University Art Gallery"),
        ],
        "homepage": [{"id": "https://artgallery.yale.edu/collections/objects/25955"}],
        "items": [
            {
                "width": 5689,
                "height": 4500,
                "items": [
                    {
                        "items": [
                            {
                                "body": {
                                    "service": [
                                        {"@id": "https://images.collections.yale.edu/iiif/2/yuag:x"}
                                    ]
                                }
                            }
                        ]
                    }
                ],
            }
        ],
    }


def test_yale_takes_works_its_manifests_call_public_domain() -> None:
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        url = str(request.url)
        if "/api/search/" in url:
            items = [{"id": "https://lux.collections.yale.edu/data/object/a"},
                     {"id": "https://lux.collections.yale.edu/data/object/b"}]  # fmt: skip
            return httpx.Response(200, json={"partOf": [{"totalItems": 2}], "orderedItems": items})
        if "/data/object/a" in url:
            return httpx.Response(
                200, text='{"x": "https://manifests.collections.yale.edu/yuag/obj/25955"}'
            )
        if "/data/object/b" in url:
            return httpx.Response(
                200, text='{"x": "https://manifests.collections.yale.edu/yuag/obj/52642"}'
            )
        if url.endswith("/yuag/obj/25955"):
            return httpx.Response(200, json=_manifest("Public domain"))
        return httpx.Response(200, json=_manifest("Copyright Artist/Estate/Foundation"))

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        yale = YaleMuseums(http)
        total, items = yale.search("Monet", limit=2)
        yale.discover(Discovery(kind="painting", year_from=1880, year_to=1890), limit=2)
    assert total == 2 and [i.id for i in items] == ["yale:yuag-25955"]
    item = items[0]
    assert item.artist == "Claude Monet" and item.artist_bio == "French, 1840–1926"
    assert item.year == 1887 and item.museum == "Yale University Art Gallery"
    assert item.image_url.endswith("/yuag:x/full/!2560,2560/0/default.jpg")
    search = json.loads(parse_qs(sent[0].url.query.decode())["q"][0])
    assert {"text": "Monet"} in search["AND"] and {"hasDigitalImage": 1} in search["AND"]
    discover = next(
        json.loads(parse_qs(r.url.query.decode())["q"][0])
        for r in sent[1:]
        if "/api/search/" in str(r.url)
    )
    assert {"classification": {"name": "paintings"}} in discover["AND"]
    assert {"producedDate": "1890-12-31T23:59:59.999Z", "_comp": "<="} in discover["AND"]


SI_ROW = {
    "id": "edanmdm-saam_1909.7.35",
    "title": "William T. Evans",
    "unitCode": "SAAM",
    "content": {
        "descriptiveNonRepeating": {
            "title": {"content": "William T. Evans"},
            "record_link": "https://americanart.si.edu/object/saam_1909.7.35",
            "online_media": {
                "media": [
                    {
                        "type": "Images",
                        "idsId": "SAAM-1909.7.35_1",
                        "usage": {"access": "CC0"},
                        "resources": [
                            {"label": "High-resolution JPEG", "width": 2279, "height": 2880}
                        ],
                    }
                ]
            },
        },
        "freetext": {
            "name": [{"label": "Artist", "content": "Wilhelm Funk, born Hanover 1866"}],
            "date": [{"label": "Date", "content": "1909"}],
            "physicalDescription": [{"label": "Medium", "content": "oil on canvas"}],
        },
        "indexedStructured": {"object_type": ["Paintings"], "date": ["1900s"]},
    },
}  # fmt: skip


def test_smithsonian_needs_a_key_and_takes_cc0_pictures() -> None:
    assert "si" not in available(Access()) and "si" in available(Access(smithsonian_key="k"))
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        closed = json.loads(json.dumps(SI_ROW).replace('"CC0"', '"Usage conditions apply"'))
        closed["id"] = "closed"
        return httpx.Response(200, json={"response": {"rowCount": 2, "rows": [SI_ROW, closed]}})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        si = Smithsonian(http, access=Access(smithsonian_key="k"))
        total, items = si.search("Funk")
        si.discover(Discovery(kind="painting", year_from=1880, year_to=1899))
    assert total == 2 and [i.id for i in items] == ["si:edanmdm-saam_1909.7.35"]
    item = items[0]
    assert item.museum == "Smithsonian American Art Museum" and item.year == 1909
    assert item.image_url == "https://ids.si.edu/ids/deliveryService?id=SAAM-1909.7.35_1&max=2560"
    assert sent[0].url.params["api_key"] == "k"
    assert 'date:"1880s" OR date:"1890s"' in sent[1].url.params["q"]


def test_the_va_only_with_private_use() -> None:
    assert "vam" not in available(Access()) and "vam" in available(Access(private_use=True))
    record = {
        "systemNumber": "O82577",
        "accessionNumber": "583-1888",
        "objectType": "Oil painting",
        "_primaryTitle": "Golding Constable's House, East Bergholt",
        "_primaryMaker": {"name": "Constable, John (RA)"},
        "_primaryDate": "ca. 1811",
        "_images": {"_iiif_image_base_url": "https://framemark.vam.ac.uk/collections/2006AG3410/"},
    }
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"info": {"record_count": 1}, "records": [record]})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        vam = museum("vam", http, Access(private_use=True))
        _, items = vam.search("Constable")
        vam.discover(Discovery(kind="print", year_from=1700, year_to=1950))
        assert vam.discover(Discovery(year_from=1920)) == (0, [])
        assert isinstance(vam, VictoriaAndAlbert)
    item = items[0]
    assert item.artist == "John Constable" and item.year == 1811
    assert item.image_url.endswith("/2006AG3410/full/!2560,2560/0/default.jpg")
    assert sent[0].url.params["year_made_to"] == "1899"
    assert (
        sent[1].url.params["year_made_to"] == "1899"
        and sent[1].url.params["q_object_type"] == "print"
    )
