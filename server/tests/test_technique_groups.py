"""Which technique group a work belongs to when a museum's search found it
for one (Mateusz 2026-11-10: Claude Monet + Plakaty showed his oils, "olej
na tkaninie, rodzaj: obraz"). Museums asked for an artist and one kind bring
any of his works, so the work's own type and material decide."""

from __future__ import annotations

import json
from typing import Any

import httpx
from test_library import RIJKS_OBJECT

from frame_server.library import Item, PlaylistRules
from frame_server.library.museums import (
    Access,
    ArtInstituteChicago,
    Europeana,
    Rijksmuseum,
    by_artist,
)
from frame_server.library.repo import matches
from frame_server.library.search import MuseumSearch
from frame_server.library.vocabulary import DECORATIVE, is_poster, object_category, type_tells


def _found(rules: PlaylistRules, n: int, **fields: Any) -> Item:
    return Item(
        id=f"aic:{n}",
        source="aic",
        source_id=str(n),
        artist=rules.artists[0],
        found_for=[rules.search_key()],
        **fields,
    )


def _shown(item: Item, rules: PlaylistRules) -> bool:
    """In Szukaj and in the smart playlist of the same choices."""
    szukaj = MuseumSearch.of(rules).fits(item)
    assert matches(item, rules) == szukaj
    return szukaj


def test_monet_s_oils_are_no_posters() -> None:
    posters = PlaylistRules(artists=["Claude Monet"], terms=["technique:poster"])
    # What AIC, the CMA, the Rijksmuseum, MNW, Yale and Europeana gave for
    # Monet + Plakaty (2026-11-10, the screenshot's "The Red Kerchief").
    for n, (kind, medium) in enumerate(
        [
            ("Painting", "Oil on canvas"),
            ("Painting", "oil on fabric"),
            ("painting", "oil on panel"),
            ("Painting", "olej, płótno"),
            ("Paintings", "Oil on canvas"),
            ("Painting, Målningar (Måleri), Bildkonst", "Oil painting"),
            ("Drawing and Watercolor", "Graphite on tan wove paper"),
            ("Print", "Etching on ivory laid paper"),
            ("", "Oil on canvas"),
        ]
    ):
        assert not _shown(_found(posters, n, classification=kind, medium=medium), posters), kind
    lautrec = PlaylistRules(artists=["Henri de Toulouse-Lautrec"], terms=["technique:poster"])
    for n, (kind, medium, title) in enumerate(
        [
            ("Poster", "litografia barwna, papier", "Jane Avril, Jardin de Paris"),
            ("Works on Paper - Prints - Posters", "Color lithograph", "Reine de Joie"),
            ("posters, cartell (pòster)", "", "May Belfort"),
            ("Print", "Color lithograph poster on tan wove paper", "Aristide Bruant"),
            ("Print", "Lithograph", "Affiche pour la Revue blanche"),
        ]
    ):
        item = _found(lautrec, n, classification=kind, medium=medium, title=title)
        assert _shown(item, lautrec), kind
    # A design for a poster is a drawing.
    design = _found(lautrec, 9, classification="Drawing", title="Design for a poster")
    assert not is_poster(design) and not _shown(design, lautrec)


def test_a_poster_is_a_print_never_a_painting_or_drawing() -> None:
    def rules(technique: str) -> PlaylistRules:
        return PlaylistRules(artists=["Henri de Toulouse-Lautrec"], terms=[technique])

    def confetti(technique: str) -> Item:  # the V&A's, typed "Poster" alone
        return _found(rules(technique), 1, classification="Poster", title="Confetti")

    assert not _shown(confetti("technique:painting"), rules("technique:painting"))
    assert not _shown(confetti("technique:drawing"), rules("technique:drawing"))
    assert _shown(confetti("technique:print"), rules("technique:print"))
    assert _shown(confetti("technique:poster"), rules("technique:poster"))
    # The catalogue's works, judged without a search, alike.
    work = Item(id="vam:1", source="vam", source_id="1", classification="Poster")
    assert matches(work, PlaylistRules(terms=["technique:print"]))
    assert not matches(work, PlaylistRules(terms=["technique:painting"]))
    # A poster's design, as the Rijksmuseum types it: a drawing and a
    # poster, no print.
    design = work.model_copy(update={"classification": "design, poster, drawing"})
    assert matches(design, PlaylistRules(terms=["technique:drawing"]))
    assert matches(design, PlaylistRules(terms=["technique:poster"]))
    assert not matches(design, PlaylistRules(terms=["technique:print"]))


def test_europeana_s_broad_categories_and_languages() -> None:
    def rules(technique: str) -> PlaylistRules:
        return PlaylistRules(artists=["Rembrandt"], terms=[technique])

    def found(technique: str, kind: str, medium: str = "") -> Item:
        return _found(rules(technique), 1, classification=kind, medium=medium)

    # The provider's "Painting [category]" beside the work's own "drawing".
    drawing = "drawing, Painting [category], Drawing"
    assert not _shown(found("technique:painting", drawing), rules("technique:painting"))
    assert _shown(found("technique:drawing", drawing), rules("technique:drawing"))
    study = "figural study [drawing], Painting [category], figuurstudie[tekening]"
    assert not _shown(found("technique:painting", study, "Paper"), rules("technique:painting"))
    # Only categories: they are all it says.
    alone = "Painting [category], Schilderij[categorie]"
    assert _shown(found("technique:painting", alone), rules("technique:painting"))
    # Prints in German and French: no paintings, no drawings.
    for kind in ("Printing graphic, Druckgrafik", "printed image, image imprimée"):
        assert not _shown(found("technique:painting", kind), rules("technique:painting"))
        assert not _shown(found("technique:drawing", kind), rules("technique:drawing"))
        assert _shown(found("technique:print", kind), rules("technique:print"))
    assert _shown(found("technique:painting", "Målningar (Måleri)"), rules("technique:painting"))
    assert _shown(found("technique:drawing", "Zeichnung"), rules("technique:drawing"))


def test_other_arts_take_their_own_works_only() -> None:
    """Rękopisy, Fotografia, Rzeźba, Ceramika: a picture found for them is
    out in the catalogue too, as it is in Szukaj (``category_fits``)."""
    photos = PlaylistRules(artists=["Edgar Degas"], terms=["technique:photography"])
    assert _shown(_found(photos, 1, classification="Photograph"), photos)
    assert not _shown(_found(photos, 2, classification="Painting", medium="Oil"), photos)
    bronze = PlaylistRules(artists=["Edgar Degas"], terms=["technique:sculpture"])
    assert _shown(_found(bronze, 3, classification="Sculpture", medium="Bronze"), bronze)
    assert not _shown(_found(bronze, 4, classification="Drawing"), bronze)


def test_the_art_institute_is_asked_for_posters_by_classification() -> None:
    asked: list[dict[str, Any]] = []
    poster = {
        "id": 82287,
        "title": "Moulin Rouge, La Goulue",
        "artist_title": "Henri de Toulouse-Lautrec",
        "artwork_type_title": "Print",
        "classification_titles": ["poster", "print", "prints and drawing"],
        "medium_display": "Color lithograph on tan wove paper",
        "image_id": "abc",
        "is_public_domain": True,
        "thumbnail": {"width": 800, "height": 1200},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(json.loads(request.content))
        return httpx.Response(200, json={"pagination": {"total": 1}, "data": [poster]})

    aic = ArtInstituteChicago(httpx.Client(transport=httpx.MockTransport(handler)), access=Access())
    total, items = aic.search_kind(by_artist("Henri de Toulouse-Lautrec"), "poster", 24, 1)
    assert total == 1
    must = asked[0]["query"]["bool"]["must"]
    assert must[0]["simple_query_string"]["query"] == "poster"
    assert must[0]["simple_query_string"]["fields"] == ["classification_titles", "term_titles"]
    assert must[1] == {
        "match": {"artist_title": {"query": "Henri de Toulouse-Lautrec", "operator": "and"}}
    }
    assert "classification_titles" in asked[0]["fields"]
    # Its type is "Print"; the word is among its classifications only.
    assert items[0].classification == "Poster" and is_poster(items[0])
    plain = aic._map({**poster, "classification_titles": ["lithograph", "print"]})
    assert plain is not None and plain.classification == "Print" and not is_poster(plain)


def test_europeana_is_asked_for_one_kind_by_its_what() -> None:
    sent: list[httpx.Request] = []
    record = {
        "id": "/1/job",
        "title": ["JOB"],
        "dcCreator": ["Alphonse Mucha"],
        "dcTypeLangAware": {"en": ["Print"]},
        "rights": ["http://creativecommons.org/publicdomain/mark/1.0/"],
        "edmIsShownBy": ["https://images.example/job.jpg"],
        "edmPreview": ["https://api.europeana.eu/thumbnail/v2/url.json?uri=x&type=IMAGE"],
        "year": ["1896"],
        "guid": ["https://www.europeana.eu/item/1/job"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"totalResults": 1, "items": [record]})

    found = Europeana(httpx.Client(transport=httpx.MockTransport(handler)), access=Access())
    total, items = found.search_kind(by_artist("Alphonse Mucha"), "poster", 24, 1)
    assert total == 1
    assert sent[0].url.params["query"] == 'who:"Alphonse Mucha"'
    assert "what:poster" in sent[0].url.params.get_list("qf")
    # Typed "Print" by its provider, found as a poster: one.
    assert items[0].classification == "Print, poster" and is_poster(items[0])
    _, items = found.search_kind(by_artist("Alphonse Mucha"), "painting", 24, 1)
    assert "what:painting" in sent[1].url.params.get_list("qf")
    assert items[0].classification == "Print"


def test_a_rijksmuseum_name_given_alone_is_read() -> None:
    """A maker's notation as one value, not a list, was read as its keys:
    Toulouse-Lautrec's prints were by "@language" (2026-11-10)."""
    assert Rijksmuseum._notation({"notation": {"@language": "nl", "@value": "Manzi"}}) == "Manzi"
    assert Rijksmuseum._notation({"notation": "print"}) == "print"
    both = [{"@language": "nl", "@value": "prent"}, {"@language": "en", "@value": "print"}]
    assert Rijksmuseum._notation({"notation": both}) == "print"
    assert Rijksmuseum._notation({}) == ""


def test_the_rijksmuseum_gives_every_type_of_a_work() -> None:
    """The first type alone was often a narrower word the server does not
    know: "grisaille" before "painting", "design" before "drawing" (48 of
    the owner's 1 588 works of the museum, 2026-11-11)."""
    types = [
        {"notation": {"@language": "nl", "@value": "grisaille"}},
        {"notation": [{"@language": "en", "@value": "painting"}, {"@value": "schilderij"}]},
        {"notation": "painting"},
    ]
    read = Rijksmuseum(httpx.Client())._map({**RIJKS_OBJECT, "classified_as": types})
    assert read is not None and read.classification == "grisaille, painting"
    assert type_tells(read) and not type_tells(
        read.model_copy(update={"classification": "grisaille"})
    )
    kept = {
        "edm": 1,
        "id": "200106575",
        "iiif": "https://iiif.micr.io/abc",
        "rights": "http://creativecommons.org/publicdomain/mark/1.0/",
        "types": ["design", "drawing"],
    }
    at_home = Rijksmuseum(httpx.Client())._map(kept)
    assert at_home is not None and at_home.classification == "design, drawing"
    # Objects it types in Dutch alone are no pictures (a cane knob of
    # porcelain, a furnishing fabric).
    for dutch in ("wandelstokknop", "bekledingsstof", "kraag, godet", "kastanjevaas"):
        assert object_category(read.model_copy(update={"classification": dutch})) == DECORATIVE
