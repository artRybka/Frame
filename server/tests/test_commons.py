from __future__ import annotations

import httpx

from frame_server.library import Item, Library
from frame_server.library.commons import (
    REPAIR_STATE_KEY,
    REPAIR_VERSION,
    commons_html,
    commons_plain,
    commons_year,
    repair_library,
)
from frame_server.library.markup import (
    clean_title,
    commons_rendition,
    strip_language_prefix,
    strip_markup,
)
from frame_server.library.museums import Openverse, WikimediaCommons

TITLE_HTML = (
    '<div class="description mw-content-ltr pl" dir="ltr" lang="pl">'
    '<span class="language pl" title="Polish"><b>Polish: </b></span> Żniwiarka</div>'
    '<span style="display: none;">title QS:P1476,pl:"Żniwiarka"</span>'
    '<span style="display: none;">label QS:Lpl,"Żniwiarka"</span>'
)
DATE_HTML = (
    '<time class="dtstart" datetime="1879">1879</time>'
    '<div style="display: none;">date QS:P571,+1879-00-00T00:00:00Z/9</div>'
)
DESCRIPTION_HTML = (
    '<div class="description mw-content-ltr en" lang="en">'
    '<span class="language en" title="English"><b>English: </b></span>'
    "The Harvester by <a href='/wiki/Malczewski'>Jacek Malczewski</a></div>"
    '<div class="description mw-content-ltr pl" lang="pl">'
    '<span class="language pl" title="Polish"><b>Polski: </b></span>'
    "Żniwiarka, obraz Jacka Malczewskiego<br>olej na płótnie</div>"
)

# Titles from Wikidata carry an edit icon, inside the QS strings too (as Commons
# sends them, shortened).
EDIT_ICON = (
    '\xa0<span class="mw-valign-text-top noprint" typeof="mw:File/Frameless">'
    '<a href="https://www.wikidata.org/wiki/Q25714750#P1476" title="Edytuj to na Wikidanych">'
    '<img alt="Edytuj to na Wikidanych" src="https://thumb.wikimedia.org/x.svg.png?a=1&amp;b=2"'
    ' width="10" height="10" class="mw-file-element"></a></span>'
)
WIKIDATA_TITLE_HTML = (
    '<div class="fn">\n<div style="font-weight:bold;display:inline-block;">'
    '<div style="display:inline-block" dir="ltr" lang="pl">'
    f"<i>Portret Marii Stawarskiej-Golińskiej{EDIT_ICON}</i></div></div>"
    f'<div style="display: none;">title QS:P1476,pl:"Portret Marii Stawarskiej-Golińskiej'
    f'{EDIT_ICON}"</div>'
    f'<div style="display: none;">label QS:Lpl,"Portret Marii Stawarskiej-Golińskiej'
    f'{EDIT_ICON}"</div>'
    '<div style="display: none;">label QS:Len,"Portrait of Maria Stawarska-Golińska"</div></div>'
)
# What 0.17 stored for it: the QS string cut at the icon's first quote.
STORED_WIKIDATA_TITLE = "Portret Marii Stawarskiej-Golińskiej\xa0<span class="

# What older versions stored after plain tag stripping (seen in the app).
STORED_TITLE = 'Polish:  Żniwiarkatitle QS:P1476,pl:"Żniwiarka"label QS:Lpl,"Żniwiarka"'
STORED_DATE = "1879date QS:P571,+1879-00-00T00:00:00Z/9"


def test_html_values() -> None:
    assert commons_html(TITLE_HTML, title=True) == "Żniwiarka"
    # Without the QS span the visible text is used, minus the language label.
    assert commons_html(TITLE_HTML.split("<span style")[0], title=True) == "Żniwiarka"
    assert commons_html(DATE_HTML) == "1879"
    assert commons_html(DESCRIPTION_HTML) == "Żniwiarka, obraz Jacka Malczewskiego\nolej na płótnie"
    assert commons_html(DESCRIPTION_HTML, prefer=("en",)) == "The Harvester by Jacek Malczewski"
    assert commons_html("Babie lato") == "Babie lato"
    assert commons_html("Portrait &amp; study") == "Portrait & study"
    assert commons_html("") == ""


def test_wikidata_titles_lose_the_edit_icon() -> None:
    assert commons_html(WIKIDATA_TITLE_HTML, title=True) == "Portret Marii Stawarskiej-Golińskiej"
    assert commons_html(WIKIDATA_TITLE_HTML, title=True, prefer=("en",)) == (
        "Portrait of Maria Stawarska-Golińska"
    )
    assert commons_html(f"wrzesień 1927{EDIT_ICON}") == "wrzesień 1927"
    assert commons_plain(STORED_WIKIDATA_TITLE, title=True) == (
        "Portret Marii Stawarskiej-Golińskiej"
    )


def test_markup_left_in_short_fields() -> None:
    assert strip_markup("Portret <span class=") == "Portret"
    assert strip_markup("<i>Bitwa</i> pod&nbsp;Grunwaldem") == "Bitwa pod Grunwaldem"
    assert strip_markup("Rock &amp; roll") == "Rock & roll"
    # Not markup: kept.
    assert strip_markup("A < B, 1 <3") == "A < B, 1 <3"
    assert strip_markup("") == ""


def test_titles_lose_language_prefixes() -> None:
    assert strip_language_prefix("en:Night Windows") == "Night Windows"
    assert strip_language_prefix(":fr:Le Pont de l'Europe") == "Le Pont de l'Europe"
    assert strip_language_prefix("w:de:Der Wanderer") == "Der Wanderer"
    assert strip_language_prefix("zh-hant:山水") == "山水"
    assert clean_title('<a href="https://en.wikipedia.org/wiki/X">en:Night Windows</a>') == (
        "Night Windows"
    )
    # Not a language code, a space after the colon, or nothing after it: kept.
    for text in ("Op. 3: Nokturn", "re: list", "XV:Portret", "abcd:Studium", "en:", "Etiuda"):
        assert strip_language_prefix(text) == text


def test_plain_repair() -> None:
    assert commons_plain(STORED_TITLE, title=True) == "Żniwiarka"
    assert commons_plain(STORED_DATE) == "1879"
    assert commons_plain("circa 1880date QS:P571,+1880-00-00T00:00:00Z/9,P1480,Q5727902") == (
        "circa 1880"
    )
    assert commons_plain("Polish: ŻniwiarkaEnglish: The Harvester") == "Żniwiarka"
    assert commons_plain("English: The Harvester") == "The Harvester"
    # English title only in QS: the visible text wins over a non-preferred language.
    assert commons_plain('Die Ernte title QS:P1476,de:"Die Ernte"', title=True) == "Die Ernte"
    # Ordinary text is left alone, including a language name inside a sentence.
    for text in ("Babie lato", "Inscribed in French: Adieu", "1875", "Portret żony"):
        assert commons_plain(text, title=True) == text
    assert commons_year(STORED_DATE) == 1879
    assert commons_year("date QS:P571,+1879-00-00T00:00:00Z/9") == 1879
    assert commons_year("unknown") is None


def test_wikimedia_import_cleans_markup() -> None:
    page = {
        "pageid": 7,
        "title": "File:Jacek Malczewski - Żniwiarka.jpg",
        "imageinfo": [
            {
                "url": "https://upload/full.jpg",
                "extmetadata": {
                    "ObjectName": {"value": TITLE_HTML},
                    "DateTimeOriginal": {"value": DATE_HTML},
                    "ImageDescription": {"value": DESCRIPTION_HTML},
                    "LicenseShortName": {"value": "Public domain"},
                },
            }
        ],
    }
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"query": {"pages": {"7": page}}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        _, items = WikimediaCommons(http).search("Category:Paintings by Jacek Malczewski")
    item = items[0]
    assert item.title == "Żniwiarka" and item.date_text == "1879" and item.year == 1879
    assert item.description.startswith("Żniwiarka, obraz")
    assert sent[0].url.params["iiextmetadatalanguage"] == "pl"


def test_wikimedia_import_drops_language_prefix() -> None:
    # A Commons title written as a bare interwiki link shows its target.
    link = (
        '<a href="https://en.wikipedia.org/wiki/Night_Windows" class="extiw">en:Night Windows</a>'
    )
    page = {
        "pageid": 9,
        "title": "File:Night Windows by Edward Hopper.jpg",
        "imageinfo": [
            {
                "url": "https://upload/full.jpg",
                "extmetadata": {
                    "ObjectName": {"value": link},
                    "LicenseShortName": {"value": "Public domain"},
                },
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"pages": {"9": page}}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        _, items = WikimediaCommons(http).search("Category:Paintings by Edward Hopper")
    assert items[0].title == "Night Windows"


def test_repair_stored_items(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    broken = Item(
        id="wmc:7",
        source="wmc",
        source_id="7",
        title=STORED_TITLE,
        date_text=STORED_DATE,
        favorite=True,
    )
    other = Item(id="met:1", source="met", source_id="1", title="English: kept as is")
    wikidata = Item(id="wmc:8", source="wmc", source_id="8", title=STORED_WIKIDATA_TITLE)
    tagged = Item(id="europeana:1", source="europeana", source_id="1", title="<i>Pejzaż</i>")
    svg = "https://upload.wikimedia.org/wikipedia/commons/f/f1/Mondrian_SVG_kleeblatt.svg"
    drawing = Item(
        id="openverse:1",
        source="openverse",
        source_id="1",
        image_url=svg,
        thumb_url="https://api.openverse.org/v1/images/1/thumb/",
        width=610,
    )
    prefixed = Item(id="wmc:9", source="wmc", source_id="9", title="en:Night Windows")
    linked = Item(id="openverse:2", source="openverse", source_id="2", title=":fr:Le Pont")
    photo = Item(id="upload:1", source="upload", source_id="", title="pl:moja notatka")
    for item in (broken, other, wikidata, tagged, drawing, prefixed, linked, photo):
        lib.upsert(item)

    assert repair_library(lib) == 6
    fixed = lib.get("wmc:7")
    assert fixed is not None
    assert (fixed.title, fixed.date_text, fixed.year) == ("Żniwiarka", "1879", 1879)
    assert fixed.favorite
    assert lib.get("met:1").title == other.title
    assert lib.get("wmc:8").title == "Portret Marii Stawarskiej-Golińskiej"
    assert lib.get("europeana:1").title == "Pejzaż"
    assert lib.get("openverse:1").image_url == commons_rendition(svg, 3840)
    assert lib.get("openverse:1").thumb_url.endswith("/500px-Mondrian_SVG_kleeblatt.svg.png")
    assert lib.get("wmc:9").title == "Night Windows"
    assert lib.get("openverse:2").title == "Le Pont"
    assert lib.get("upload:1").title == photo.title
    assert lib.get_state(REPAIR_STATE_KEY) == REPAIR_VERSION

    # Runs once: later imports are already clean.
    lib.update("wmc:7", title=STORED_TITLE)
    assert repair_library(lib) == 0
    assert Library(tmp_path / "lib.db").get("wmc:7").title == STORED_TITLE


def test_wikimedia_search_leaves_photographs_out() -> None:
    def page(n: int, categories: str) -> dict:
        info = {
            "url": f"https://upload/{n}.jpg",
            "extmetadata": {
                "ObjectName": {"value": f"Work {n}"},
                "LicenseShortName": {"value": "Public domain"},
                "Categories": {"value": categories},
            },
        }
        return {"pageid": n, "title": f"File:{n}.jpg", "imageinfo": [info]}

    pages = {
        "1": page(1, "Paintings by Claude Monet|Seascapes"),
        "2": page(2, "Photographs taken on 2019-07-14|Taken with Canon EOS 5D"),
        "3": page(3, "Self-published work|Beaches of Normandy"),
    }
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"query": {"pages": pages}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        _, items = WikimediaCommons(http).search("sea")
    assert [i.title for i in items] == ["Work 1"]
    assert "hastemplate:Artwork" in sent[0].url.params["gsrsearch"]


def test_wikimedia_leaves_printed_copies_of_paintings_out() -> None:
    def page(n: int, categories: str) -> dict:
        info = {
            "url": f"https://upload/{n}.jpg",
            "extmetadata": {
                "ObjectName": {"value": f"Work {n}"},
                "LicenseShortName": {"value": "Public domain"},
                "Categories": {"value": categories},
            },
        }
        return {"pageid": n, "title": f"File:{n}.jpg", "imageinfo": [info]}

    pages = {
        "1": page(1, "Paintings by Józef Chełmoński|Babie lato by Józef Chełmoński"),
        "2": page(2, "Files from Polona|Paintings by Józef Chełmoński|PD-anon-expired"),
        "3": page(3, "Glass slides in the Leuven University Libraries|PD-anon-70-EU"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"pages": pages}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        _, paintings = WikimediaCommons(http).search("Category:Paintings by Józef Chełmoński")
        _, prints = WikimediaCommons(http).search("Category:Prints by Józef Chełmoński")
    assert [i.title for i in paintings] == ["Work 1"]
    assert paintings[0].artist == "Józef Chełmoński"
    # Prints from a library are originals.
    assert len(prints) == 3 and {i.classification for i in prints} == {"Print"}


def test_small_thumbnails_to_judge_colour_by() -> None:
    from frame_server.library.importer import small_thumb

    base = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b6/Wilki.jpg"
    wmc = Item(id="wmc:1", source="wmc", source_id="1", thumb_url=f"{base}/500px-Wilki.jpg")
    assert small_thumb(wmc) == f"{base}/120px-Wilki.jpg"
    original = wmc.model_copy(update={"thumb_url": "https://upload.wikimedia.org/x/Small.jpg"})
    assert small_thumb(original) == original.thumb_url
    europeana = Item(
        id="europeana:1",
        source="europeana",
        source_id="1",
        thumb_url="https://api.europeana.eu/thumbnail/v2/url.json?uri=x&type=IMAGE&size=w400",
    )
    assert small_thumb(europeana).endswith("&size=w200")


SVG = "https://upload.wikimedia.org/wikipedia/commons/f/f1/Mondrian_SVG_kleeblatt.svg"
TIFF = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Wilki.tif"


def test_commons_renders_what_no_app_reads() -> None:
    thumbs = "https://upload.wikimedia.org/wikipedia/commons/thumb"
    assert commons_rendition(SVG, 3840) == (
        f"{thumbs}/f/f1/Mondrian_SVG_kleeblatt.svg/3840px-Mondrian_SVG_kleeblatt.svg.png"
    )
    # Only the widths Commons renders; drawings at any of them.
    assert "/1920px-" in commons_rendition(SVG, 2560, 610)
    # Bitmaps never past their own width.
    assert commons_rendition(TIFF, 3840, 3000) == (
        f"{thumbs}/a/ab/Wilki.tif/lossy-page1-1920px-Wilki.tif.jpg"
    )
    assert commons_rendition("https://example.org/drawing.svg", 3840) == ""


def test_openverse_drawings_come_rendered_or_not_at_all() -> None:
    def result(n: int, url: str, filetype: str | None) -> dict:
        return {
            "id": f"uuid-{n}",
            "title": f"Work {n}",
            "url": url,
            "filetype": filetype,
            "thumbnail": f"https://api.openverse.org/v1/images/uuid-{n}/thumb/",
            "license": "cc0",
            "license_version": "1.0",
            "width": 610,
            "height": 610,
        }

    results = [
        result(1, SVG, "svg"),
        result(2, "https://example.org/icons/brush.svg", None),
        result(3, "https://images.example.org/painting.jpg", "jpg"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result_count": 3, "results": results})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        _, items = Openverse(http).search("Mondrian")
    assert [i.title for i in items] == ["Work 1", "Work 3"]
    drawing, painting = items
    assert drawing.image_url.endswith("/3840px-Mondrian_SVG_kleeblatt.svg.png")
    assert drawing.thumb_url.endswith("/500px-Mondrian_SVG_kleeblatt.svg.png")
    assert painting.image_url == results[2]["url"]
    assert painting.thumb_url == results[2]["thumbnail"]


def test_wikimedia_files_no_app_reads_come_rendered() -> None:
    def page(n: int, url: str, width: int) -> dict:
        info = {
            "url": url,
            "thumburl": f"https://upload.wikimedia.org/thumb/{n}/500px-x.png",
            "width": width,
            "extmetadata": {
                "ObjectName": {"value": f"Work {n}"},
                "LicenseShortName": {"value": "Public domain"},
            },
        }
        return {"pageid": n, "title": f"File:{n}", "imageinfo": [info]}

    pages = {
        "1": page(1, SVG, 610),
        "2": page(2, TIFF, 6000),
        "3": page(3, "https://upload.wikimedia.org/wikipedia/commons/b/b6/Wilki.jpg", 6000),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"pages": pages}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        _, items = WikimediaCommons(http).search("Category:Paintings by Piet Mondrian")
    urls = {i.title: i.image_url for i in items}
    assert urls["Work 1"].endswith("/3840px-Mondrian_SVG_kleeblatt.svg.png")
    assert urls["Work 2"].endswith("/lossy-page1-3840px-Wilki.tif.jpg")
    assert urls["Work 3"] == pages["3"]["imageinfo"][0]["url"]
