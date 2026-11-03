import httpx
import pytest

from frame_server.library import Item
from frame_server.sizes import KIND, RealSize, Sizes, fits, parse


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
    item = _item(source="vam", source_id="O1")
    sizes = Sizes(library, lambda: _client({}))
    assert sizes.look(item) is None  # no museum record, no Wikidata link
    assert library.note(item.id, KIND) is not None
    met = _item(source_id="1")
    assert Sizes(library, lambda: _client({})).look(met) is None  # the Met's 404
    assert library.note(met.id, KIND) is None
