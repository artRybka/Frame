from __future__ import annotations

import httpx

from frame_server.library import Item, Library
from frame_server.library.commons import (
    REPAIR_STATE_KEY,
    commons_html,
    commons_plain,
    commons_year,
    repair_library,
)
from frame_server.library.museums import WikimediaCommons

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
    lib.upsert(broken)
    lib.upsert(other)

    assert repair_library(lib) == 1
    fixed = lib.get("wmc:7")
    assert fixed is not None
    assert (fixed.title, fixed.date_text, fixed.year) == ("Żniwiarka", "1879", 1879)
    assert fixed.favorite
    assert lib.get("met:1").title == other.title
    assert lib.get_state(REPAIR_STATE_KEY) == 1

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
