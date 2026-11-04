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
import pytest

from frame_server.library import courtauld
from frame_server.library.museums import Access, Discovery, available, museum
from frame_server.library.muza import MuzaMuseum, NationalMuseumKrakow, NationalMuseumWarsaw, polish
from frame_server.library.nga import NationalGalleryOfArt, build
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
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        path = request.url.path.strip("/")
        asked.append(path)
        if path == "sitemap.xml":
            return httpx.Response(200, text=f"<urlset>{sitemap}</urlset>")
        if path in pages:
            link = f"api/iiif/{pages[path]}/manifest.json"
            return httpx.Response(200, text=f'<a href="{link}">{link}</a>')
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
    assert bar.url == f"{site}/object-p-1934-sc-234" and bar.width == 7506
    assert work is not None and work.license == "Prawa autorskie w mocy (użytek prywatny)"
    assert courtauld.dimensions("Height: 96 cm (canvas)<br>Width: 130 cm (canvas)") == (96, 130)


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
        wikiart = museum("wikiart", http, Access(wikiart=True, wikiart_keys=("acc", "sec")))
        assert wikiart.search("Rothko") == (0, [])
        assert wikiart.search("Klee") == (0, [])
    logins = [r for r in sent if r.url.path.endswith("/login")]
    assert len(logins) == 3  # two checks (no colon: not asked), one session for both
