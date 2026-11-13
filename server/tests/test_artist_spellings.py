"""Who made a work, however a museum writes it (Mateusz 2026-11-10, after
the audit of the technique groups: Mucha's posters lost to "Alphonse",
Toulouse-Lautrec's prints "by" their publisher or by nobody)."""

from __future__ import annotations

import json
from typing import Any, ClassVar

import httpx

from frame_server.library import Item, Library, PlaylistRules
from frame_server.library.artists import ArtistNames, learn, made_by, other_spelling
from frame_server.library.museums import (
    Access,
    ArtInstituteChicago,
    Europeana,
    Museum,
    Rijksmuseum,
    by_artist,
)


def test_a_first_name_in_another_language_is_the_same_person() -> None:
    for spelling in ("Alphonse Mucha", "Alphonse-Marie Mucha", "Alfons Maria Mucha"):
        assert made_by(spelling, ["Alfons Mucha"]), spelling
    assert made_by("Henri de Toulouse-Lautrec", ["Henry de Toulouse-Lautrec"])
    assert made_by("Jan Steen", ["Johannes Steen"])
    # A surname is kept as written; a workshop or another generation is
    # someone else in any language.
    assert not made_by("Jan Stern", ["Jan Steen"])
    assert not made_by("Workshop of Peter Paul Rubens", ["Pieter Paulus Rubens"])
    assert not made_by("Pieter Bruegel the Younger", ["Peter Bruegel the Elder"])
    assert not made_by("Alphonse Legros", ["Alfons Mucha"])


def test_the_catalogue_finds_every_spelling_of_a_first_name(tmp_path) -> None:
    library = Library(tmp_path / "lib.db")
    for n, artist in enumerate(["Alphonse Mucha", "Alfons Mucha", "Alphonse Legros"]):
        library.upsert(Item(id=f"vam:{n}", source="vam", source_id=str(n), artist=artist))
    total, items = library.query(PlaylistRules(artists=["Alfons Mucha"]))
    assert total == 2 and {i.artist for i in items} == {"Alphonse Mucha", "Alfons Mucha"}


def test_a_rijksmuseum_print_is_by_its_maker_not_its_publisher() -> None:
    def part(technique: str, name: str | None = None) -> dict[str, Any]:
        found: dict[str, Any] = {"technique": [{"notation": [{"@value": technique}]}]}
        if name:
            found["carried_out_by"] = [{"notation": {"@language": "nl", "@value": name}}]
        return found

    record = {
        "id": "https://id.rijksmuseum.nl/200130875",
        "identified_by": [{"type": "Name", "content": "Portret van uitgever W.H.B. Sands"}],
        "produced_by": {
            "referred_to_by": [{"content": "Henri de Toulouse-Lautrec (mentioned on object)"}],
            # The printmaker is only attributed (an id, no name); the
            # publisher and printer are named.
            "part": [
                part("printmaker"),
                part("publisher", "Manzi, Joyant & Cie."),
                part("printer (person)", "Manzi, Joyant & Cie."),
            ],
        },
    }
    rijks = Rijksmuseum(httpx.Client())
    rijks._image = lambda d: ("https://iiif.micr.io/x", "Public Domain Mark 1.0")  # type: ignore[method-assign]
    item = rijks._map(record)
    assert item is not None and item.artist == "Henri de Toulouse-Lautrec"
    record["produced_by"]["part"][0] = part("printmaker", "Henri de Toulouse-Lautrec")
    item = rijks._map(record)
    assert item is not None and item.artist == "Henri de Toulouse-Lautrec"


def _europeana(**fields: Any) -> dict[str, Any]:
    return {
        "id": "/2064108/poster",
        "title": ["May Milton"],
        "dcTypeLangAware": {"de": ["Plakat"]},
        "rights": ["http://creativecommons.org/publicdomain/mark/1.0/"],
        "edmIsShownBy": ["https://images.example/may.jpg"],
        "edmPreview": ["https://api.europeana.eu/thumbnail/v2/url.json?uri=x&type=IMAGE"],
        "year": ["1895"],
        **fields,
    }


def test_europeana_s_maker_from_its_agents_and_contributors() -> None:
    found = Europeana(httpx.Client(), access=Access())

    def artist(record: dict[str, Any]) -> str:
        item = found._map(record)
        assert item is not None
        return item.artist

    # The Kunstbibliothek's posters: the designer as a contributor only.
    designer = "Henri de Toulouse-Lautrec (23.11.1864 - 9.9.1901, Entwerfer)"
    assert artist(_europeana(dcContributor=[designer])) == "Henri de Toulouse-Lautrec"
    # A printer as creator gives way to him.
    printed = _europeana(dcCreator=["Imprimerie Chaix"], dcContributor=[designer])
    assert artist(printed) == "Henri de Toulouse-Lautrec"
    # A creator named by Europeana's and the GND's addresses only.
    linked = _europeana(
        dcCreator=["http://data.europeana.eu/agent/60678", "https://d-nb.info/gnd/11862346X"],
        edmAgentLabelLangAware={
            "ru": ["Анри де Тулуз-Лотрек"],
            "en": ["Henri de Toulouse-Lautrec"],
        },
    )
    assert artist(linked) == "Henri de Toulouse-Lautrec"
    # SMK's own id for the painter ("250_person", Michael Ancher) is no
    # name: his agent's is (Mateusz 2026-11-13, "A Girl with Sunflowers").
    smk = _europeana(
        dcCreator=["250_person"],
        dcCreatorLangAware={"def": ["250_person"]},
        edmAgentLabelLangAware={"def": ["Ancher, Michael", "Statens Museum for Kunst"]},
    )
    assert artist(smk) == "Michael Ancher"
    # A contributor in another role is no author.
    assert artist(_europeana(dcContributor=["Musée X (Leihgeber)"])) == ""


def _two_spellings() -> None:
    works = {"Alphonse Mucha": {1, 2, 3}, "Alfons Mucha": {4, 5}}
    learn(ArtistNames(works, {"Alphonse Mucha": "Q41406", "Alfons Mucha": "Q41406"}))


def test_a_museum_is_asked_by_another_spelling_when_its_own_finds_none() -> None:
    assert other_spelling("Alfons Mucha") is None
    _two_spellings()
    assert other_spelling("Alfons Mucha") == "Alphonse Mucha"
    assert other_spelling("Alphonse Mucha") == "Alfons Mucha"
    assert other_spelling("Somebody Else") is None

    class ByField(Museum):
        key = "vam"
        name = "By field"
        asked: ClassVar[list[str]] = []

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            ByField.asked.append(f"words: {query}")
            return 0, []

        def search_by(
            self, artist: str, words: str = "", limit: int = 20, page: int = 1
        ) -> tuple[int, list[Item]]:
            ByField.asked.append(f"artist: {artist}")
            if artist != "Alphonse Mucha":
                return 0, []
            return 1, [self._item("job", title="Job", artist=artist)]

        def fetch(self, source_id: str) -> Item | None:
            return None

    total, _ = ByField(httpx.Client()).search_artist("Alfons Mucha")
    assert total == 1
    assert ByField.asked == ["artist: Alfons Mucha", "artist: Alphonse Mucha"]


def test_the_art_institute_is_asked_by_another_spelling_too() -> None:
    _two_spellings()
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        name = body["query"]["bool"]["must"][1]["match"]["artist_title"]["query"]
        asked.append(name)
        total = 1 if name == "Alphonse Mucha" else 0
        data = [
            {
                "id": 1,
                "title": "Zodiaque",
                "artist_title": name,
                "artwork_type_title": "Print",
                "classification_titles": ["poster"],
                "image_id": "abc",
                "is_public_domain": True,
            }
        ]
        return httpx.Response(200, json={"pagination": {"total": total}, "data": data[:total]})

    aic = ArtInstituteChicago(httpx.Client(transport=httpx.MockTransport(handler)), access=Access())
    total, items = aic.search_kind(by_artist("Alfons Mucha"), "poster", 24, 1)
    assert asked == ["Alfons Mucha", "Alphonse Mucha"]
    assert total == 1 and items[0].artist == "Alphonse Mucha"
