import httpx
import pytest

from frame_server.library import Item
from frame_server.sizes import KIND, RealSize, Sizes, commons_size, fits, parse


def _item(source: str = "met", source_id: str = "437881", w: int = 890, h: int = 1000) -> Item:
    return Item(
        id=f"{source}:{source_id}",
        source=source,
        source_id=source_id,
        title="Young Woman with a Water Pitcher",
        artist="Johannes Vermeer",
        width=w,
        height=h,
    )


def test_a_museums_text_gives_the_work_not_its_frame() -> None:
    size = parse("Framed: 128.3 x 105.7 x 14.6 cm (50 1/2 x 41 5/8 in.); Unframed: 99 x 79.8 cm")
    assert size == RealSize(height=99, width=79.8)
    assert parse("18 x 16 in. (45,7 × 40,6 cm)") == RealSize(height=45.7, width=40.6)
    assert parse("2390 x 3070 mm") == RealSize(height=239, width=307)
    assert parse("about two feet") is None


def test_a_size_is_kept_only_with_the_pictures_proportions() -> None:
    item = _item(w=889, h=1000)
    assert fits(RealSize(height=45.7, width=40.6), item) == RealSize(height=45.7, width=40.6)
    # Width given first: turned.
    assert fits(RealSize(height=40.6, width=45.7), item) == RealSize(height=45.7, width=40.6)
    # A sheet far wider than its picture.
    assert fits(RealSize(height=45.7, width=60), item) is None
    assert fits(RealSize(height=0.2, width=0.2), _item(w=1, h=1)) is None


def _client(routes: dict[str, dict]) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        for part, body in routes.items():
            if part in str(request.url):
                return httpx.Response(200, json=body)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(answer))


@pytest.fixture
def library(service):
    return service.library


def test_the_met_says_the_size_and_it_is_kept(library) -> None:
    met = {
        "measurements": [
            {"elementName": "Framed", "elementMeasurements": {"Height": 67.9, "Width": 62.2}},
            {"elementName": "Overall", "elementMeasurements": {"Height": 45.7, "Width": 40.6}},
        ]
    }
    sizes = Sizes(library, lambda: _client({"collectionapi.metmuseum.org": met}))
    item = _item()
    assert sizes.look(item) == RealSize(height=45.7, width=40.6)
    assert sizes.size(item) == RealSize(height=45.7, width=40.6)
    assert sizes.look_soon(item) is False  # asked already


def test_wikidata_when_the_museum_does_not_say(library) -> None:
    item = _item(source="rijks", source_id="200108", w=534, h=794)
    routes = {
        "list=search": {"query": {"search": [{"title": "Q12418"}]}},
        "wbgetentities": {
            "entities": {
                "Q12418": {
                    "claims": {
                        "P2048": [
                            {
                                "mainsnak": {
                                    "datavalue": {
                                        "value": {
                                            "amount": "+794",
                                            "unit": "http://www.wikidata.org/entity/Q174789",
                                        }
                                    }
                                }
                            }
                        ],
                        "P2049": [
                            {
                                "mainsnak": {
                                    "datavalue": {
                                        "value": {
                                            "amount": "+53.4",
                                            "unit": "http://www.wikidata.org/entity/Q174728",
                                        }
                                    }
                                }
                            }
                        ],
                    }
                }
            }
        },
    }
    sizes = Sizes(library, lambda: _client(routes))
    assert sizes.look(item) == RealSize(height=79.4, width=53.4)


def test_nothing_found_is_kept_and_a_failure_is_not(library) -> None:
    item = _item(source="europeana", source_id="O1")
    sizes = Sizes(library, lambda: _client({"list=search": {"query": {"search": []}}}))
    assert sizes.look(item) is None  # no museum record, nothing on Wikidata
    assert library.note(item.id, KIND) is not None
    met = _item(source_id="1")
    assert Sizes(library, lambda: _client({})).look(met) is None  # the Met's 404
    assert library.note(met.id, KIND) is None


def test_a_commons_page_says_the_size() -> None:
    page = "{{Artwork\n |artist = Leonardo\n |dimensions = {{Size|cm|77|53}}\n}}"
    assert commons_size(page) == RealSize(height=77, width=53)
    named = " |dimensions = {{Size|unit=mm|width=530|height=770}}"
    assert commons_size(named) == RealSize(height=77, width=53)
    assert commons_size(" |dimensions = 77 × 53 cm") == RealSize(height=77, width=53)
    assert commons_size(" |medium = oil") is None


def test_a_commons_work_by_its_page(library) -> None:
    item = _item(source="wmc", source_id="123", w=530, h=770)
    page = {
        "query": {
            "pages": [
                {
                    "title": "File:Mona Lisa.jpg",
                    "revisions": [
                        {"slots": {"main": {"content": " |dimensions = {{Size|cm|77|53}}"}}}
                    ],
                }
            ]
        }
    }
    sizes = Sizes(library, lambda: _client({"commons.wikimedia.org": page}))
    assert sizes.look(item) == RealSize(height=77, width=53)


def test_polish_museums_the_va_and_the_wellcome_say_the_size(library) -> None:
    mnw = {
        "data": {
            "sizes": [
                {
                    "name": "w ramie",
                    "dimensions": [
                        {"name": "wysokość", "value": "90", "unit": "cm"},
                        {"name": "szerokość", "value": "80", "unit": "cm"},
                    ],
                },
                {
                    "name": "",
                    "dimensions": [
                        {"name": "wysokość", "value": "72,5", "unit": "cm"},
                        {"name": "szerokość", "value": "60", "unit": "cm"},
                    ],
                },
            ]
        }
    }
    item = _item(source="mnw", source_id="943746", w=600, h=725)
    assert Sizes(library, lambda: _client({"mnw.art.pl": mnw})).look(item) == RealSize(
        height=72.5, width=60
    )
    text = {"data": {"sizes": [], "dimensionText": "wys. 12,5 cm, szer. 11 cm"}}
    item = _item(source="mnk", source_id="5", w=110, h=125)
    assert Sizes(library, lambda: _client({"mnk.pl": text})).look(item) == RealSize(
        height=12.5, width=11
    )
    vam = {
        "record": {
            "dimensions": [
                {"dimension": "Height", "value": "12.5", "unit": "cm", "part": ""},
                {"dimension": "Width", "value": "13.5", "unit": "cm", "part": ""},
            ]
        }
    }
    item = _item(source="vam", source_id="O18946", w=135, h=125)
    assert Sizes(library, lambda: _client({"api.vam.ac.uk": vam})).look(item) == RealSize(
        height=12.5, width=13.5
    )
    wellcome = {"physicalDescription": "1 print : etching ; image 21 x 32 cm"}
    item = _item(source="wellcome", source_id="ke2zpvqb", w=320, h=210)
    assert Sizes(library, lambda: _client({"wellcomecollection.org": wellcome})).look(
        item
    ) == RealSize(height=21, width=32)


def _painting(about: str, year: str, height: str) -> dict:
    def side(amount: str) -> list[dict]:
        unit = "http://www.wikidata.org/entity/Q174728"
        return [{"mainsnak": {"datavalue": {"value": {"amount": amount, "unit": unit}}}}]

    return {
        "descriptions": {"en": {"value": about}},
        "claims": {
            "P571": [{"mainsnak": {"datavalue": {"value": {"time": f"+{year}-00-00T00:00:00Z"}}}}],
            "P2048": side(height),
            "P2049": side("+40.6"),
        },
    }


def test_wikidata_by_title_when_nothing_links_the_work(library) -> None:
    item = _item(source="europeana", source_id="x", w=889, h=1000).model_copy(update={"year": 1662})
    routes = {
        "list=search": {"query": {"search": [{"title": "Q1"}, {"title": "Q2"}, {"title": "Q3"}]}},
        "wbgetentities": {
            "entities": {
                "Q1": _painting("painting by Jan Steen", "1662", "+45.7"),  # another artist
                "Q2": _painting("painting by Johannes Vermeer", "1640", "+45.7"),  # another year
                "Q3": _painting("painting by Johannes Vermeer", "1662", "+45.7"),
            }
        },
    }
    assert Sizes(library, lambda: _client(routes)).look(item) == RealSize(height=45.7, width=40.6)
