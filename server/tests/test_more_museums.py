"""Sources added in November 2026: the national museums in Warsaw and
Kraków, the National Gallery of Art, Yale, the Smithsonian and the V&A."""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote

import httpx
import pytest

from frame_server.library import courtauld
from frame_server.library.museums import Access, Discovery, available, museum
from frame_server.library.muza import MuzaMuseum, NationalMuseumKrakow, NationalMuseumWarsaw, polish
from frame_server.library.nga import INDEX, NationalGalleryOfArt, build, provenance
from frame_server.library.smithsonian import Smithsonian
from frame_server.library.vam import VictoriaAndAlbert
from frame_server.library.wellcome import WellcomeCollection, split_title
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


def test_national_museums_give_protected_works_for_private_use() -> None:
    sent: list[str] = []
    wroblewski = {
        **MNW_OBJECT,
        "id": 448343,
        "title": "Matki",
        "authors": [{"name": "Wróblewski, Andrzej (1927-1957)", "role": "malarz"}],
    }

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(unquote(str(request.url)))
        if "/object/" in request.url.path:
            rights = [{"id": 504, "name": "licencja na użytkowanie, PRAWA AUTORSKIE W MOCY"}]
            return httpx.Response(200, json={"data": {**wroblewski, "copyrights": rights}})
        page = {"totalItemsCount": 2, "currentPage": 1}
        items = [MNW_OBJECT, wroblewski]
        return httpx.Response(200, json={"data": {"paginatorDetails": page, "items": items}})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        NationalMuseumWarsaw(http).search("Wróblewski")
        found = NationalMuseumWarsaw(http).fetch("448343")
        home = NationalMuseumWarsaw(http, private_use=True)
        total, items = home.search("Andrzej Wróblewski")
        mine = home.fetch("448343")
    # Without private use the museum is asked for public domain only.
    assert "filter[copyrights][]=500" in sent[0] and found is None
    assert "filter[copyrights]" not in sent[2]
    assert total == 2 and [i.title for i in items] == ["Portret matki artysty", "Matki"]
    assert items[0].license == "Public Domain Mark 1.0"  # Malczewski died in 1929
    assert items[1].license == NationalMuseumWarsaw.private_licence
    assert mine is not None and mine.license == NationalMuseumWarsaw.private_licence


def test_national_museums_find_nothing_without_failing() -> None:
    # Muza answers a search with no results 404 "NO_RESULTS_FOR_GIVEN_QUERY".
    def answer(request: httpx.Request) -> httpx.Response:
        body = {"data": None, "status": 404, "message": "NO_RESULTS_FOR_GIVEN_QUERY"}
        return httpx.Response(404, json=body)

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        assert NationalMuseumKrakow(http).search("Andrzej Wróblewski") == (0, [])
        assert NationalMuseumWarsaw(http).discover(Discovery(kind="painting")) == (0, [])


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
         "creditline": "Widener Collection", "attribution": "Edgar Degas",
         "provenancetext": "Sold 1893 to Durand-Ruel, Paris; Widener, 1914."},
        {"objectid": "7", "title": "Closed", "displaydate": "", "beginyear": "",
         "medium": "", "classification": "Painting", "creditline": "", "attribution": ""},
        {"objectid": "9", "title": "A jug", "displaydate": "", "beginyear": "1937",
         "medium": "watercolor", "classification": "Index of American Design",
         "creditline": "", "attribution": ""},
    ],
}  # fmt: skip


def test_an_index_of_an_older_make_is_built_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An index from before provenance was kept is searched as it is and
    built again at once, not when it turns a month old."""
    path = tmp_path / "nga" / "collection.sqlite"
    path.parent.mkdir()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE works (id INTEGER PRIMARY KEY, title TEXT)")
    started: list[Path] = []
    monkeypatch.setattr(INDEX, "_start", started.append)
    assert not INDEX.current(path)
    # (The tests' own ``ready`` never builds: the class's is asked.)
    assert type(INDEX).ready(INDEX, path) and started == [path]  # searched meanwhile
    assert provenance(tmp_path, "1158") is None  # cannot say yet


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
    # The gallery's provenance is kept with the work (the study's "Droga dzieła").
    assert provenance(tmp_path, "1158") == "Sold 1893 to Durand-Ruel, Paris; Widener, 1914."
    assert provenance(tmp_path, "404") == "" and provenance(None, "1158") is None
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
    assert sent[0].headers["x-api-key"] == "k" and "api_key" not in sent[0].url.params
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


def _wellcome_work(
    title: str, licence: str = "pdm", genres: tuple[str, ...] = ("Etching",)
) -> dict[str, object]:
    return {
        "id": "ke2zpvqb",
        "title": title,
        "physicalDescription": "1 print : etching, with watercolour ; image 21 x 32 cm",
        "thumbnail": {
            "url": "https://iiif.wellcomecollection.org/image/V0047380EL/full/300,/0/default.jpg",
            "license": {"id": licence},
        },
        "contributors": [
            {"agent": {"label": "H. Humphrey", "type": "Organisation"}, "primary": False},
            {"agent": {"label": "James Gillray", "type": "Person"}, "primary": True},
        ],
        "production": [
            {"dates": [{"label": "[1795?]"}], "places": [{"label": "London (No. 37 New Bond St)"}]}
        ],
        "genres": [{"label": g} for g in genres],
        "subjects": [{"label": "Hats"}],
        "referenceNumber": "12345i",
        "description": "<p>A <i>fine</i> pair</p>",
    }


def test_wellcome_takes_public_domain_pictures_and_cuts_the_title() -> None:
    works = [
        _wellcome_work("A man and a woman, both wearing enormous hats. Etching by J. Gillray."),
        _wellcome_work("Two friends. Coloured etching after J. Gillray, 1800.", licence="cc-by-nc"),
        _wellcome_work("A doctor. Photograph, 1890.", genres=("Photographs",)),
        _wellcome_work(
            "Head of a man with a disease affecting his face. Watercolour by C. D'Alton."
        ),
    ]
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.path.endswith("/works/gone"):
            return httpx.Response(410)
        return httpx.Response(200, json={"totalResults": 3, "results": works})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        wellcome = museum("wellcome", http, Access())
        assert isinstance(wellcome, WellcomeCollection)
        total, items = wellcome.search("Gillray")
        wellcome.discover(Discovery(kind="painting", year_from=1800, year_to=1850))
        assert wellcome.discover(Discovery(kind="sculpture")) == (0, [])
        assert wellcome.discover(Discovery(highlight=True)) == (0, [])
        assert wellcome.fetch("gone") is None
        _, private = museum("wellcome", http, Access(private_use=True)).search("Gillray")
    # The CC BY-NC one only for private use; no photographs, no diseases.
    assert total == 3 and len(items) == 1
    item = items[0]
    assert item.id == "wellcome:ke2zpvqb" and item.museum == "Wellcome Collection"
    assert item.title == "A man and a woman, both wearing enormous hats"
    assert item.artist == "James Gillray" and item.year == 1795 and item.date_text == "1795"
    assert item.medium == "etching, with watercolour" and item.culture == "London"
    assert item.license == "Public Domain Mark 1.0" and item.credit == "Wellcome Collection, 12345i"
    assert item.description == "A fine pair"
    assert item.image_url == (
        "https://iiif.wellcomecollection.org/image/V0047380EL/full/!2560,2560/0/default.jpg"
    )
    assert item.url == "https://wellcomecollection.org/works/ke2zpvqb"
    assert [i.license for i in private] == ["Public Domain Mark 1.0", "CC BY-NC 4.0"]
    assert sent[0].url.params["items.locations.license"] == "pdm,cc-0"
    assert sent[0].url.params["workType"] == "k" and sent[0].url.params["query"] == "Gillray"
    found = sent[1].url.params
    assert found["genres.label"] == "Paintings,Gouaches,Watercolor painting"
    assert found["production.dates.from"] == "1800-01-01"
    assert found["production.dates.to"] == "1850-12-31"
    assert "cc-by-nc" in sent[-1].url.params["items.locations.license"]


def test_wellcome_titles_lose_the_description_of_the_picture() -> None:
    assert split_title("An election banquet. Engraving by W. Hogarth, 1755.") == (
        "An election banquet",
        "Engraving",
    )
    assert split_title("Indian acrobats performing. Gouache painting.") == (
        "Indian acrobats performing",
        "Gouache painting",
    )
    assert split_title("St. Luke painting the Virgin. Oil painting.") == (
        "St. Luke painting the Virgin",
        "Oil painting",
    )
    assert split_title("Pen and ink. Pen and ink drawing by T. Rowlandson.")[1] == (
        "Pen and ink drawing"
    )
    assert split_title("Dr. Ranby's house in Chiswick") == ("Dr. Ranby's house in Chiswick", "")


def _courtauld_manifest(
    title: str, maker: str, date: str, statement: str, width: int = 7506, height: int = 5559
) -> dict[str, object]:
    def pair(label: str, value: str) -> dict[str, object]:
        return {"label": {"none": [label]}, "value": {"none": [value]}}

    body = {
        "id": "https://gallerycollections.courtauld.ac.uk/iiif/3/134471/full/max/0/default.jpg",
        "width": width,
        "height": height,
    }
    return {
        "label": {"none": [title]},
        "metadata": [
            pair("Title", title),
            pair("Maker", f" {maker}"),
            pair("Production date", date),
            pair("Medium", "oil on canvas\n"),
            pair("Accession number", "P.1934.SC.234"),
            pair("Dimensions", "Height: 96 cm (canvas)<br>Width: 130 cm (canvas)"),
            pair("Credit", "Courtauld Gallery, London (Samuel Courtauld Trust)"),
            pair("Copyright statement", statement),
            pair("Label text", f"{maker}\u2019s <b>last</b> major painting."),
        ],
        "items": [{"items": [{"items": [{"body": body}]}]}],
    }


def test_courtauld_lists_its_paintings_and_searches_the_list(tmp_path: Path) -> None:
    site = courtauld.SITE
    sitemap = "".join(
        f"<url><loc>{site}/{slug}</loc></url>"
        for slug in ("object-p-1934-sc-234", "object-p-1984-ah-192", "object-p-1", "object-d-9")
    )
    manifests = {
        "O2271": _courtauld_manifest(
            "A Bar at the Folies-Bergère", "Édouard Manet", "1882", "Work in the public domain"
        ),
        "O5937": _courtauld_manifest(
            "A Sybilline Courtyard", "Ivon Hitchens", "1974", "© The Estate. All rights reserved"
        ),
        "O1": _courtauld_manifest(
            "Saint Jerome", "Circle of Orioli", "(circa) 1480", "", width=373, height=500
        ),
    }
    pages = {"object-p-1934-sc-234": "O2271", "object-p-1984-ah-192": "O5937", "object-p-1": "O1"}
    printed = f"{site}/assets/object_images/1/74/134471/v0_high.jpg?_m=1&amp;x=2"
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        path = request.url.path.strip("/")
        asked.append(path)
        if path == "sitemap.xml":
            return httpx.Response(200, text=f"<urlset>{sitemap}</urlset>")
        if path in pages:
            link = f"api/iiif/{pages[path]}/manifest.json"
            picture = (
                f'<img id="print-image" alt="Printable main image" src="{printed}">'
                if path == "object-p-1934-sc-234"
                else ""
            )
            return httpx.Response(200, text=f'<a href="{link}">{link}</a>{picture}')
        if path.startswith("api/iiif/"):
            return httpx.Response(200, json=manifests[path.split("/")[2]])
        return httpx.Response(404)

    path = courtauld.list_path(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        assert courtauld.build(path, http) == 2  # the small picture is no use
        asked.clear()
        assert courtauld.build(path, http) == 2
    assert asked == ["sitemap.xml"]  # known paintings are not asked again

    assert "courtauld" not in available(Access(data_dir=tmp_path))
    access = Access(private_use=True, data_dir=tmp_path)
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        gallery = museum("courtauld", http, access)
        total, items = gallery.search("manet")
        assert gallery.discover(Discovery(year_from=1900))[0] == 1
        assert gallery.discover(Discovery(kind="print")) == (0, [])
        work = gallery.fetch("p-1984-ah-192")
    assert total == 1
    bar = items[0]
    assert bar.id == "courtauld:p-1934-sc-234" and bar.artist == "Édouard Manet"
    assert bar.year == 1882 and bar.medium == "oil on canvas" and bar.license == "CC BY-NC 4.0"
    assert bar.description == "Édouard Manet’s last major painting."
    assert bar.credit == "Courtauld Gallery, London (Samuel Courtauld Trust), P.1934.SC.234"
    assert bar.image_url == f"{site}/iiif/3/134471/full/!2560,2560/0/default.jpg"
    # The tile is the picture the page prints: the IIIF one of a CMYK scan is white.
    assert bar.thumb_url == f"{site}/assets/object_images/1/74/134471/v0_high.jpg?_m=1&x=2"
    assert bar.url == f"{site}/object-p-1934-sc-234" and bar.width == 7506
    assert work is not None and work.license == "Prawa autorskie w mocy (użytek prywatny)"
    assert work.thumb_url == f"{site}/iiif/3/134471/full/!600,600/0/default.jpg"

    # Listed before the page's picture was kept: the pages are asked again
    # (not the manifests), once.
    listed = json.loads(path.read_text())
    for work_ in listed.values():
        if work_:
            del work_["picture"]
    path.write_text(json.dumps(listed))
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        asked.clear()
        assert courtauld.build(path, http) == 2
        assert sorted(asked) == ["object-p-1934-sc-234", "object-p-1984-ah-192", "sitemap.xml"]
        asked.clear()
        courtauld.build(path, http)
        assert asked == ["sitemap.xml"]
    assert json.loads(path.read_text())["object-p-1934-sc-234"]["picture"].endswith("x=2")
    assert courtauld.dimensions("Height: 96 cm (canvas)<br>Width: 130 cm (canvas)") == (96, 130)


def test_courtauld_originals_smaller_than_the_frame_are_asked_whole() -> None:
    iiif = f"{courtauld.SITE}/iiif/3/134252"
    # IIIF 3 does not enlarge without "^": !2560,2560 of a 1797 px scan is a 400.
    assert courtauld.original_url(iiif, 1797, 1564) == f"{iiif}/full/max/0/default.jpg"
    assert courtauld.original_url(iiif, 7506, 5559) == f"{iiif}/full/!2560,2560/0/default.jpg"
    assert courtauld.original_url(iiif, None, None) == f"{iiif}/full/!2560,2560/0/default.jpg"


def _png(img: object) -> bytes:
    out = io.BytesIO()
    img.save(out, "PNG")  # type: ignore[attr-defined]
    return out.getvalue()


def test_courtauld_white_cmyk_scans_are_asked_again_as_png(tmp_path: Path) -> None:
    """Its IIIF server reads some CMYK scans as RGBA with nothing opaque: the
    JPEG is white, the PNG's channels are cyan, magenta, yellow and black
    (Borghese di Piero's predella, 2026-11-05)."""
    from PIL import Image

    from frame_server.library.images import BYTES, ImageCache

    url = f"{courtauld.SITE}/iiif/3/134252/full/!600,600/0/default.jpg"
    white = Image.new("RGB", (60, 40), (255, 255, 255))
    red = Image.new("RGBA", (60, 40), (0, 230, 220, 0))  # cyan 0, magenta, yellow, black 0
    jpeg = io.BytesIO()
    white.save(jpeg, "JPEG")
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        if request.url.path.endswith(".png"):
            return httpx.Response(200, content=_png(red))
        return httpx.Response(200, content=jpeg.getvalue())

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(answer)))
    cache.repairs[courtauld.HOST] = courtauld.repair
    img = cache.sample(url)
    assert asked == [url, url.removesuffix(".jpg") + ".png"]
    r, g, b = img.getpixel((5, 5))
    assert r > 240 and g < 40 and b < 50 and img.info[BYTES] > 0

    # A picture that is not white is kept as it came, with no second request.
    asked.clear()
    jpeg = io.BytesIO()
    Image.new("RGB", (60, 40), (120, 80, 40)).save(jpeg, "JPEG")
    assert cache.sample(url).getpixel((5, 5))[0] > 100 and len(asked) == 1
    assert not courtauld.blank(Image.new("RGB", (4, 4), (200, 255, 255)))
    # Nor are the page's own pictures asked again as PNG.
    page = f"{courtauld.SITE}/assets/object_images/2/52/43/134252/v0_high.jpg"
    assert courtauld.repair(page, white, lambda u: b"") is white
    with pytest.raises(OSError):
        courtauld.from_cmyk_png(_png(Image.new("RGB", (4, 4), (1, 2, 3))))
    with pytest.raises(OSError):
        courtauld.from_cmyk_png(_png(Image.new("RGBA", (4, 4), (0, 0, 0, 0))))

    # White pictures kept before are removed, so they come again.
    white.save(tmp_path / "courtauld_p-1.jpg")
    Image.new("RGB", (4, 4), (9, 9, 9)).save(tmp_path / "courtauld_p-2.jpg")
    white.save(tmp_path / "met_1.jpg")
    assert courtauld.forget_white([tmp_path]) == 1
    assert sorted(p.name for p in tmp_path.glob("*.jpg")) == ["courtauld_p-2.jpg", "met_1.jpg"]


PARIS_WORK = {
    "entityId": "151109",
    "title": "Les Petites Baigneuses",
    "absolutePath": "/fr/petit-palais/oeuvres/les-petites-baigneuses",
    "fieldOeuvreAuteurs": [{"entity": {"fieldAuteurAuteur": {"entity": {
        "name": "Courbet, Gustave",
        "fieldPipDateNaissance": {"startYear": 1819},
        "fieldPipDateDeces": {"startYear": 1877},
    }}}}],
    "fieldVisuels": [{"entity": {
        "publicUrl": "https://www.parismuseescollections.paris.fr/sites/default/files/a.jpg",
        "vignette": "https://www.parismuseescollections.paris.fr/sites/default/files/styles/t/a.jpg",
        "fieldImageLibre": True,
    }}],
    "fieldDateProduction": {"startYear": 1849, "century": "19e siècle"},
    "fieldOeuvreTypesObjet": [{"entity": {"name": "Peinture"}}],
    "fieldMateriauxTechnique": [{"entity": {"name": "Huile sur toile"}}],
    "fieldOeuvreThemeRepresente": [{"entity": {"name": "baigneuse"}}],
    "fieldMusee": {"entity": {"name": "Petit Palais"}},
}  # fmt: skip


def test_paris_musees_needs_a_token_and_takes_free_pictures() -> None:
    from frame_server.library.paris import ParisMusees

    assert "paris" not in available(Access())
    assert "paris" in available(Access(paris_token="t"))
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        closed = {**PARIS_WORK, "entityId": "2", "fieldVisuels": [{"entity": {
            "publicUrl": "https://x/b.jpg", "fieldImageLibre": False}}]}  # fmt: skip
        found = {"count": 2, "entities": [PARIS_WORK, closed, None]}
        return httpx.Response(200, json={"data": {"nodeQuery": found}})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        assert ParisMusees(http).search("Baigneuses") == (0, [])  # no token, nothing asked
        paris = ParisMusees(http, access=Access(paris_token="t"))
        total, items = paris.search('Baig"neuses')
        paris.discover(Discovery(kind="painting", year_from=1800, year_to=1899))
        assert paris.discover(Discovery(style="Impressionism")) == (0, [])
    assert total == 2 and [i.id for i in items] == ["paris:151109"]
    item = items[0]
    assert item.artist == "Gustave Courbet"
    assert item.artist_bio == "1819–1877" and item.year == 1849
    assert item.museum == "Petit Palais" and item.license == "CC0 1.0"
    assert item.url.startswith("https://www.parismuseescollections.paris.fr/fr/petit-palais/")
    assert item.thumb_url.endswith("/styles/t/a.jpg")
    assert len(sent) == 2 and sent[0].headers["auth-token"] == "t"
    query = json.loads(sent[0].content)["query"]
    assert "field_image_libre" in query
    # Each word in the title or the author's name.
    assert query.count("conjunction: OR") == 2 and '"%Baig%"' in query and '"%neuses%"' in query
    assert "field_auteur_auteur.entity.name" in query
    assert 'operator: GREATER_THAN_OR_EQUAL, value: "1800"' in json.loads(sent[1].content)["query"]


def test_paris_musees_searches_titles_only_when_authors_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from frame_server.library.paris import ParisMusees, _words

    monkeypatch.setattr(ParisMusees, "_by_author", True)
    assert _words("Le Pont de l'Europe Caillebotte") == ["Pont", "l'Europe", "Caillebotte"]
    assert _words("a la de") == []
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)["query"]
        sent.append(query)
        if "groups" in query:
            return httpx.Response(200, json={"errors": [{"message": "field not found"}]})
        return httpx.Response(
            200, json={"data": {"nodeQuery": {"count": 1, "entities": [PARIS_WORK]}}}
        )

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        paris = ParisMusees(http, access=Access(paris_token="t"))
        assert paris.search("Baigneuses Courbet")[0] == 1
        assert paris.search("Baigneuses")[0] == 1
    # Refused once, then the whole query in the title, without asking again.
    assert "groups" in sent[0] and '"%Baigneuses Courbet%"' in sent[1]
    assert len(sent) == 3 and "groups" not in sent[2]


def test_source_keys_are_checked_kept_and_never_sent_back(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from frame_server.config import Settings
    from frame_server.source_keys import KeyRejected
    from frame_server.web.app import create_app

    app = create_app(
        Settings(data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1")
    )
    svc = app.state.service
    good = "si-key-good-1234"

    def check(source: str, key: str, http: object = None) -> None:
        if key != good:
            raise KeyRejected("no")

    svc.source_keys.check = check
    with TestClient(app) as client:
        views = {v["source"]: v for v in client.get("/api/sources/keys").json()}
        assert set(views) == {"si", "paris", "europeana", "wikiart"}
        assert views["si"]["key_set"] is False and views["si"]["signup"].startswith("https://")
        assert "si" not in svc.importer.sources()

        assert client.put("/api/sources/keys/si", json={"key": "wrong"}).status_code == 400
        assert client.put("/api/sources/keys/nope", json={"key": good}).status_code == 404
        resp = client.put("/api/sources/keys/si", json={"key": f" {good} "})
        assert resp.status_code == 200 and good not in resp.text
        si = next(v for v in resp.json() if v["source"] == "si")
        assert si["key_tail"] == "1234" and si["key_from_app"] is True
        assert svc._access().smithsonian_key == good and "si" in svc.importer.sources()

        resp = client.delete("/api/sources/keys/si")
        assert next(v for v in resp.json() if v["source"] == "si")["key_set"] is False
        assert "si" not in svc.importer.sources()


def test_a_source_key_is_asked_of_its_service() -> None:
    from frame_server.source_keys import KeyRejected, KeyUnchecked, SourceKeys

    def answer(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and not request.url.params.get("q"):
            return httpx.Response(400)  # the search asked without its words
        key = request.headers.get("auth-token") or request.headers.get("x-api-key")
        assert "api_key" not in request.url.params  # out of the server's log
        if key == "down":
            return httpx.Response(503)
        return httpx.Response(200 if key == "good" else 403, json={})

    keys = SourceKeys.__new__(SourceKeys)
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        for source in ("si", "paris"):
            keys.check(source, "good", http)
            for bad, error in (("bad", KeyRejected), ("down", KeyUnchecked)):
                try:
                    keys.check(source, bad, http)
                except error:
                    continue
                raise AssertionError((source, bad))


def test_wikiart_keys_are_two_codes_and_open_a_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from frame_server.library.museums import WikiArt
    from frame_server.source_keys import KeyRejected, SourceKeys

    monkeypatch.setattr(WikiArt, "_sessions", {})
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        params = request.url.params
        if request.url.path.endswith("/login"):
            if (params["accessCode"], params["secretCode"]) != ("acc", "sec"):
                return httpx.Response(
                    500, json={"Exception": {"Message": "Invalid Api/Secret combination"}}
                )
            return httpx.Response(200, json={"SessionKey": "s1"})
        if params.get("authSessionKey") != "s1":
            return httpx.Response(500, json={"Exception": {"Message": "Free API limit exceeded"}})
        return httpx.Response(200, json={"data": [], "hasMore": False})

    keys = SourceKeys.__new__(SourceKeys)
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        keys.check("wikiart", "acc:sec", http)
        for bad in ("acc:wrong", "accsec"):
            with pytest.raises(KeyRejected):
                keys.check("wikiart", bad, http)
        wikiart = museum("wikiart", http, Access(private_use=True, wikiart_keys=("acc", "sec")))
        assert wikiart.search("Rothko") == (0, [])
        assert wikiart.search("Klee") == (0, [])
    logins = [r for r in sent if r.url.path.endswith("/login")]
    assert len(logins) == 3  # two checks (no colon: not asked), one session for both


def test_a_refused_wikiart_login_is_not_tried_at_every_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its login answered 500 to 50 tries on 2026-11-08, up to eight in two
    minutes: one for each search."""
    from frame_server.library.museums import WikiArt

    monkeypatch.setattr(WikiArt, "_sessions", {})
    monkeypatch.setattr(WikiArt, "_refused", {})
    clock = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    refuse = [True]
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.path.endswith("/login"):
            if refuse[0]:
                return httpx.Response(500, json={"Exception": {"Message": "Too many sessions"}})
            return httpx.Response(200, json={"SessionKey": "s1"})
        return httpx.Response(200, json={"data": [], "hasMore": False})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        wikiart = museum("wikiart", http, Access(private_use=True, wikiart_keys=("acc", "sec")))
        for term in ("Rothko", "Klee", "Hopper"):
            with pytest.raises(httpx.HTTPError):
                wikiart.search(term)
        assert len(sent) == 1  # one login; nothing asked after it
        clock[0] += WikiArt.LOGIN_AGAIN
        refuse[0] = False
        assert wikiart.search("Rothko") == (0, [])
    assert [r.url.path.rsplit("/", 1)[-1] for r in sent] == ["login", "login", "PaintingSearch"]


FILE_PATH = "http://commons.wikimedia.org/wiki/Special:FilePath/"


def _louvre_row(
    ark: str, qid: str, title: str, creator: str, died: str, file: str = ""
) -> dict[str, str]:
    return {
        "ark": ark,
        "work": f"http://www.wikidata.org/entity/{qid}",
        "workLabel": title,
        "file": FILE_PATH + file.replace(" ", "%20") if file else "",
        "creatorLabel": creator,
        "died": f"{died}-01-01T00:00:00Z" if died else "",
    }


def _louvre_entry(
    title: str,
    credit: str,
    start: int | None,
    creator: tuple[str, str] = ("VALENCIENNES Pierre-Henri de", "Q1386458"),
    period: str = "",
) -> dict[str, object]:
    media = "https://collections.louvre.fr/media/cache"
    return {
        "title": title,
        "creator": [{"label": creator[0], "wikidata": creator[1]}],
        "dateCreated": [
            {"startYear": start, "endYear": start + 4 if start else None, "text": period}
        ],
        "materialsAndTechniques": "huile sur papier marouflé sur carton",
        "objectNumber": [{"value": "RF 2908", "type": "Numéro principal"}],
        "room": "Salle 711, Aile Denon, Niveau 1",
        "dimension": [
            {"type": "Hauteur", "value": "0,25", "unit": "m"},
            {"type": "Hauteur avec accessoire", "value": "0,4", "unit": "m"},
            {"type": "Largeur", "value": "38", "unit": "cm"},
        ],
        "image": [
            {
                "urlImage": f"{media}/large/1/2/detail_OG.JPG",
                "urlThumbnail": f"{media}/small/1/2/detail_OG.JPG",
                "copyright": credit,
                "type": "détail",
                "position": 1,
            },
            {
                "urlImage": f"{media}/large/1/2/whole_OG.JPG",
                "urlThumbnail": f"{media}/small/1/2/whole_OG.JPG",
                "copyright": credit,
                "type": "face, recto, avers, avant ; vue d'ensemble",
                "position": 0,
            },
        ],
    }


def test_louvre_takes_the_paintings_commons_lacks(tmp_path: Path) -> None:
    from frame_server.library import louvre
    from frame_server.library.wikidata import record_id
    from frame_server.sizes import _louvre

    rows = [
        # On Commons in full size: Commons keeps it.
        _louvre_row(
            "010062370", "Q12418", "Mona Lisa", "Leonardo da Vinci", "1519", "Mona_Lisa.jpg"
        ),
        # On Commons, but small; two authors, the later death counts.
        _louvre_row(
            "010061111",
            "Q1",
            "Rome, the Colosseum",
            "Pierre-Henri de Valenciennes",
            "1819",
            "Valenciennes small.jpg",
        ),
        _louvre_row(
            "010061111", "Q1", "Rome, the Colosseum", "Q999", "1830", "Valenciennes small.jpg"
        ),
        # Not on Commons; a modern work still in copyright.
        _louvre_row("010069999", "Q2", "Q2", "anonymous", "1970"),
        # An unknown author: Wikidata's blank node; the date a French period.
        _louvre_row(
            "010068888",
            "Q5",
            "Piero di Lorenzo de' Medici",
            "http://www.wikidata.org/.well-known/genid/46375a1257e7eeb3",
            "",
        ),
        _louvre_row("010068888", "Q5", "Piero di Lorenzo de' Medici", "Q42", ""),
        # Another institution's photograph only.
        _louvre_row("010065555", "Q3", "Portrait of a man", "Jacques-Louis David", "1825"),
        # Gone from the Louvre's site.
        _louvre_row("010060404", "Q4", "Lost", "Somebody", "1700"),
    ]
    entries = {
        "010061111": _louvre_entry(
            "Rome, le Colisée", "© 2009 GrandPalaisRmn (musée du Louvre) / Hervé Lewandowski", 1782
        ),
        "010069999": _louvre_entry(
            "Plafond", "© Musée du Louvre / Antoine Mongodin", 1953, creator=("France", "")
        ),
        "010068888": _louvre_entry(
            "Portrait de Piero di Lorenzo de Médicis",
            "© Musée du Louvre / Angèle Dequier",
            None,
            creator=("Hals, Frans", "Q167654"),
            period="2e moitié du XVe siècle",
        ),
        "010065555": _louvre_entry(
            "Portrait d'homme", "© GrandPalaisRmn (musée d'Orsay) / Martine Beck-Coppola", 1790
        ),
    }
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        asked.append(f"{host}{path}")
        if host == "query.wikidata.org":
            assert "P9394" in request.url.params["query"]
            out = io.StringIO()
            writer = csv.DictWriter(out, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            return httpx.Response(200, text=out.getvalue())
        if host == "commons.wikimedia.org":
            titles = parse_qs(request.content.decode())["titles"][0].split("|")
            assert sorted(titles) == ["File:Mona_Lisa.jpg", "File:Valenciennes small.jpg"]
            return httpx.Response(
                200,
                json={
                    "query": {
                        "normalized": [{"from": "File:Mona_Lisa.jpg", "to": "File:Mona Lisa.jpg"}],
                        "pages": {
                            "1": {
                                "title": "File:Mona Lisa.jpg",
                                "imageinfo": [{"width": 7479, "height": 11146}],
                            },
                            "2": {
                                "title": "File:Valenciennes small.jpg",
                                "imageinfo": [{"width": 800, "height": 540}],
                            },
                        },
                    }
                },
            )
        ark = path.removeprefix("/ark:/53355/cl").removesuffix(".json")
        if ark in entries:
            return httpx.Response(200, json=entries[ark])
        return httpx.Response(404)

    path = louvre.list_path(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        assert louvre.build(path, http) == 3
        louvre_asked = sorted(a for a in asked if a.startswith("collections"))
        assert louvre_asked == [
            f"collections.louvre.fr/ark:/53355/cl{ark}.json"
            for ark in ("010060404", "010061111", "010065555", "010068888", "010069999")
        ]  # never the Mona Lisa: Commons has it in full size
        asked.clear()
        assert louvre.build(path, http) == 3
    assert not any(a.startswith("collections") for a in asked)  # entries are not asked again
    assert json.loads(path.read_text())["complete"] is True

    assert "louvre" not in available(Access(data_dir=tmp_path))
    access = Access(private_use=True, data_dir=tmp_path)
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        gallery = museum("louvre", http, access)
        total, items = gallery.search("colisée")
        assert gallery.search("colosseum")[0] == 1  # English title from Wikidata
        assert gallery.discover(Discovery(year_from=1900))[0] == 1
        assert gallery.discover(Discovery(kind="print")) == (0, [])
        assert gallery.fetch("010062370") is None and gallery.fetch("010065555") is None
        modern = gallery.fetch("010069999")
        piero = gallery.fetch("010068888")
        size = _louvre(http, items[0])
    assert total == 1
    rome = items[0]
    assert rome.id == "louvre:010061111" and rome.museum == "Luwr"
    assert rome.title == "Rome, the Colosseum" and rome.artist == "Pierre-Henri de Valenciennes"
    assert rome.year == 1782 and rome.date_text == "1782–1786"
    assert rome.license == louvre.LICENCE and rome.classification == "Painting"
    assert rome.credit == "© 2009 GrandPalaisRmn (musée du Louvre) / Hervé Lewandowski, RF 2908"
    assert rome.url == "https://collections.louvre.fr/ark:/53355/cl010061111"
    assert rome.image_url.endswith("/large/1/2/whole_OG.JPG")  # the whole work, not the detail
    assert rome.thumb_url.endswith("/small/1/2/whole_OG.JPG")
    assert record_id(rome) == ("P9394", "010061111")
    assert size is not None and (size.height, size.width) == (25.0, 38.0)
    # A school ("France") is no author.
    assert modern is not None and modern.title == "Plafond" and modern.artist == "Anonim"
    assert modern.license == "Prawa autorskie w mocy (użytek prywatny)"
    assert piero is not None and piero.artist == "Frans Hals"  # the Louvre's name
    assert piero.date_text == "1450–1499" and piero.year == 1450
    assert gallery.search("1450")[0] == 1

    # A list of 1.104.0 (Wikidata's blank node for the author, the French
    # period, no "year_end"): shown right at once, its records looked up again.
    listed = json.loads(path.read_text())
    listed.pop("format")
    old = listed["works"]["010068888"]
    old["artist"] = "http://www.wikidata.org/.well-known/genid/46375a1257e7eeb3"
    old["work"].pop("year_end")
    old["work"].update(date="2e moitié du XVe siècle", year=None, artist_fr="France")
    path.write_text(json.dumps(listed))
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        before = museum("louvre", http, access).fetch("010068888")
        assert before is not None and before.artist == "Anonim" and before.date_text == "1450–1499"
        assert before.year == 1450
        asked.clear()
        assert louvre.build(path, http) == 3
    assert sum(a.startswith("collections") for a in asked) == 3  # records, not the gone one
    assert json.loads(path.read_text())["format"] == louvre.FORMAT


def test_louvre_list_cut_short_is_finished(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from frame_server.library import louvre

    started: list[Path] = []
    index = louvre._Index()
    monkeypatch.setattr(index, "_start", started.append)
    path = louvre.list_path(tmp_path)
    assert index.works(path) == {} and started == [path]  # no list yet
    path.parent.mkdir(parents=True)
    work = {"image": "x", "thumb": "y", "title_fr": "A"}
    path.write_text(json.dumps({"complete": False, "works": {"1": {"commons": 0, "work": work}}}))
    started.clear()
    assert list(index.works(path)) == ["1"] and started == [path]  # a restart cut it short
    done = {"complete": True, "works": {"1": {"commons": 0, "work": work}}}
    path.write_text(json.dumps(done))  # finished, but in the format of 1.104.0
    started.clear()
    os.utime(path, (time.time() + 2, time.time() + 2))
    assert list(index.works(path)) == ["1"] and started == [path]
    path.write_text(json.dumps({**done, "format": louvre.FORMAT}))
    started.clear()
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert list(index.works(path)) == ["1"] and started == []


def test_louvre_waits_for_commons_when_asked_to() -> None:
    from frame_server.library import louvre

    answers = [
        httpx.Response(429, headers={"Retry-After": "30"}),
        httpx.Response(
            200,
            json={
                "query": {
                    "pages": {
                        "1": {"title": "File:A.jpg", "imageinfo": [{"width": 900, "height": 2000}]}
                    }
                }
            },
        ),
    ]
    waits: list[float] = []
    with httpx.Client(transport=httpx.MockTransport(lambda r: answers.pop(0))) as http:
        assert louvre.commons_sizes(http, ["A.jpg"], sleep=waits.append) == {"A.jpg": 2000}
    assert waits == [31.0]


def test_louvre_works_kept_before_1_104_1_are_repaired() -> None:
    from frame_server.library.commons import _repairs
    from frame_server.library.models import Item, ItemKind

    item = Item(
        id="louvre:010068888",
        kind=ItemKind.ARTWORK,
        source="louvre",
        source_id="010068888",
        title="Piero di Lorenzo de' Medici",
        artist="http://www.wikidata.org/.well-known/genid/46375a1257e7eeb3",
        date_text="2e moitié du XVe siècle",
        year=None,
    )
    assert _repairs(item) == {"artist": "Anonim", "date_text": "1450–1499", "year": 1450}
    # Antiquity's centuries, "Anonim" for no author, a capital to the title.
    wall = item.model_copy(
        update={"title": "peinture murale", "artist": "", "date_text": "Ie s. ap. J.-C.", "year": 1}
    )
    assert _repairs(wall) == {
        "artist": "Anonim",
        "title": "Peinture murale",
        "date_text": "1–100 n.e.",
    }
    done = wall.model_copy(
        update={"artist": "Anonim", "title": "Peinture murale", "date_text": "1–100 n.e."}
    )
    assert _repairs(done) == {}
    fine = item.model_copy(update={"artist": "Frans Hals", "date_text": "1503–1519", "year": 1503})
    assert _repairs(fine) == {}


def test_louvre_periods_and_authors_read_as_people_write_them() -> None:
    from frame_server.library.louvre import french_years, named, years_text

    def period(text: str) -> str | None:
        span = french_years(text)
        return years_text(*span) if span else None

    assert period("Ie s. ap. J.-C.") == "1–100 n.e."
    assert period("4e quart IIe s. ap. J.-C. (?)") == "175–199 n.e."
    assert period("Ier s. av. J.-C.") == "100–1 p.n.e."
    assert period("2e moitié du Ier siècle avant J.-C.") == "50–1 p.n.e."
    assert period("Milieu du XVe siècle") == "1440–1460"
    assert period("1er tiers du XVIIe siècle") == "1600–1632"
    assert period("vers 1500") == "1500" and period("50 av. J.-C.") == "50 p.n.e."
    assert period("époque romaine") is None
    assert years_text(-50, 20) == "50 p.n.e.–20 n.e."

    assert named({"label": "Hals, Frans", "wikidata": ""})
    assert named({"label": "VALENCIENNES Pierre-Henri de", "wikidata": ""})
    assert not named({"label": "Anonyme", "wikidata": "Q4233718"})
    assert not named({"label": "Allemagne Rhin", "wikidata": "", "linkType": "École de"})
    assert not named({"label": "Italie", "wikidata": ""})
    assert not named({"label": "RAPHAEL", "attributionLevel": "Ancienne attribution"})


def test_wikiart_gives_all_works_of_the_artist_a_search_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its search ends after one page of 60: de Chirico's 60 of 198 (Mateusz,
    2026-11-12). An artist's name brings the artist's whole list, the
    search's works first; other words stay a search."""
    from frame_server.library.museums import WikiArt

    monkeypatch.setattr(WikiArt, "_sessions", {})
    monkeypatch.setattr(WikiArt, "_artists", {})
    monkeypatch.setattr(WikiArt, "_named", {})
    monkeypatch.setattr(WikiArt, "_tokens", {})

    def work(n: int, artist: str = "Giorgio de Chirico", artist_id: str = "a1") -> dict:
        return {
            "id": f"p{n}",
            "title": f"Piazza {n}",
            "artistName": artist,
            "artistId": artist_id,
            "artistUrl": "giorgio-de-chirico",
            "url": f"piazza-{n}",
            "image": f"https://uploads.wikiart.org/p{n}.jpg!Large.jpg",
            "width": 900,
            "height": 1200,
        }

    found = [work(5), work(2), work(999, "Alberto Savinio", "a2")]
    whole = [work(n) for n in range(1, 131)]
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        endpoint = request.url.path.rsplit("/", 1)[-1]
        sent.append(endpoint)
        if endpoint == "PaintingSearch":
            if params["term"] == "metaphysical towers":
                return httpx.Response(200, json={"data": [work(9)], "hasMore": False})
            return httpx.Response(200, json={"data": found, "hasMore": False})
        if endpoint == "PaintingsByArtist":
            assert params["id"] == "a1"
            start = int(params.get("paginationToken") or 0)
            page = whole[start : start + 60]
            more = start + 60 < len(whole)
            return httpx.Response(
                200,
                json={"data": page, "hasMore": more, "paginationToken": str(start + 60)},
            )
        raise AssertionError(request.url)

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        wikiart = museum("wikiart", http, Access(private_use=True))
        total, items = wikiart.search("de Chirico", limit=40)
        assert total == 130
        assert [i.source_id for i in items[:3]] == ["p5", "p2", "p1"]
        assert len({i.id for i in items}) == 40
        total, items = wikiart.search("de Chirico", limit=40, page=4)
        assert len(items) == 10 and items[-1].source_id == "p130"
        assert sent.count("PaintingsByArtist") == 3  # kept, not asked again
        # Words not in the artist's name: the search as it is.
        assert wikiart.search("metaphysical towers") == (1, [wikiart._map(work(9))])


def test_wikiart_search_stays_when_the_artists_list_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from frame_server.library.museums import WikiArt

    monkeypatch.setattr(WikiArt, "_sessions", {})
    monkeypatch.setattr(WikiArt, "_artists", {})
    monkeypatch.setattr(WikiArt, "_named", {})
    monkeypatch.setattr(WikiArt, "_tokens", {})
    row = {"id": "p1", "title": "Ariadne", "artistName": "Giorgio de Chirico", "image": "x.jpg"}
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        sent.append(endpoint)
        if endpoint == "PaintingSearch":
            return httpx.Response(200, json={"data": [row], "hasMore": False})
        if endpoint == "Painting":  # the short record names no artist id
            return httpx.Response(200, json={**row, "artistId": "a1"})
        return httpx.Response(500, json={"Exception": {"Message": "Free API limit exceeded"}})

    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        wikiart = museum("wikiart", http, Access(private_use=True))
        total, items = wikiart.search("Chirico")
        assert (total, [i.source_id for i in items]) == (1, ["p1"])
    assert sent == ["PaintingSearch", "Painting", "PaintingsByArtist"]
