"""What each place of the server says of each kind of work, frozen
(docs/PLAN.md 3.3zzz155).

The rules that decide whether a work is shown are put together anew in many
places (the audit of 2026-11-11: about sixty calls in fifteen files), each
with its own choice of them. Before they become one verdict, this is what
they answer today: one work of every kind the rules tell apart, once as the
server took it in (``pooled``) and once as the owner kept it, asked of every
place that can be asked on its own. A change of the rules that moves a mark
shows here, with the kind and the place it moved in.

The first three places are what the work of the day and the curator's
cards of "Dziś dla Ciebie" choose among (the cards and Propozycje dnia are
filled from the catalogue). Mateusz 2026-11-11: the way to them may change,
their quality may not fall, so a "-" there turns into a "+" only with his
word, and a "+" of a good work never into a "-".

Where the places disagree about a work the owner kept
(:data:`KEPT_COPIES_STUDIED`, :data:`BROWSED_NOT_FOUND`) is the audit's
finding K1: as it is until he decides which of it is meant.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from conftest import jpeg_bytes

from frame_server.ai.gatekeeper import asked_by_rules
from frame_server.library import Item, ItemKind, PlaylistRules
from frame_server.library.models import ART_PHOTO_ARCHIVES
from frame_server.library.twins import candidate
from frame_server.library.vocabulary import category_fits, is_copy, set_aside
from frame_server.service import FrameService

MONET = "Claude Monet"
#: A title for each work: no two alike, none another's with a word added.
WORDS = [
    "Poplars",
    "Haystacks",
    "Cathedral",
    "Bridge",
    "Regatta",
    "Magpie",
    "Luncheon",
    "Terrace",
    "Cliff",
    "Boulevard",
    "Station",
    "Garden",
    "Parliament",
    "Thames",
    "Irises",
    "Wisteria",
    "Willow",
    "Sunrise",
    "Windmill",
    "Tulips",
    "Seine",
    "Beach",
    "Poppies",
    "Lilacs",
    "Meadow",
    "Ice",
    "Fog",
    "Frost",
    "Boats",
    "Harbour",
    "Pines",
    "Rocks",
    "Path",
    "Orchard",
    "Pond",
    "Snow",
    "Storm",
    "Sunset",
    "Morning",
    "Evening",
    "Noon",
    "Dusk",
    "Dawn",
    "Mist",
]
ARCHIVE = sorted(ART_PHOTO_ARCHIVES)[0]

#: One work of every kind the rules tell apart: its source and what it
#: says of itself. All by one painter, large enough, in colour unless said,
#: each under a title of its own (copies of one work are shown once).
SPECIMENS: dict[str, tuple[str, dict[str, Any]]] = {
    "obraz z muzeum": ("met", {}),
    "obraz ze zbioru plików": ("wikiart", {}),
    "detal w tytule": ("wikiart", {"title": "{title}, detail"}),
    "detal po obrazie": ("wikiart", {"detail_of": "met:whole"}),
    "zdjęcie sali z dziełem": ("wmc", {"scene_of": "met:whole"}),
    "reprodukcja": ("europeana", {"title": "{title} (page 41 crop)"}),
    "szara kopia obrazu": ("wmc", {"tint_spread": 0.001}),
    "szara grafika z muzeum": (
        "met",
        {"classification": "Print", "medium": "Etching", "tint_spread": 0.001},
    ),
    "znaczek": ("europeana", {"classification": "Postage stamp", "medium": ""}),
    "dokument": ("rijks", {"classification": "pamphlet", "medium": ""}),
    "archiwum fotografii": ("europeana", {"source_id": "718~water-lilies"}),
    "archiwum sztuki, kolor": ("europeana", {"credit": ARCHIVE}),
    "archiwum sztuki, szare": ("europeana", {"credit": ARCHIVE, "tint_spread": 0.001}),
    "kopia z Openverse": ("openverse", {"url": "https://www.rawpixel.com/image/1"}),
    "fotografia z Openverse": ("openverse", {"classification": "Photograph", "medium": ""}),
    "fotografia z muzeum": ("met", {"classification": "Photograph", "medium": "Gelatin silver"}),
    "rękopis": ("met", {"classification": "Manuscript", "medium": "Ink on parchment"}),
    "rzeźba": ("met", {"classification": "Sculpture", "medium": "Bronze"}),
    "ceramika": ("met", {"classification": "Ceramics", "medium": "Porcelain"}),
    "plakat": ("met", {"classification": "Poster", "medium": "Lithograph"}),
    "odłożone przez Strażnika": ("wikiart", {"seen_as": "not_art"}),
    "mały obraz": ("wikiart", {"width": 800, "height": 600}),
}

#: The places asked, in the order of the marks.
PLACES = (
    "katalog",
    "katalog, szukane słowem",
    "studium dnia",
    "odpowiedź muzeum",
    "Szukaj w muzeach",
    "karta Odkrywaj z muzeów",
    "Strażnik",
    "Nocny przegląd",
    "powtórki",
)

#: What the places answer today: "+" shown (or taken on), "-" left out,
#: for the work as the server took it in, then as the owner kept it.
EXPECTED: dict[str, tuple[str, str]] = {
    "obraz z muzeum": ("++++++-++", "++++++-++"),
    "obraz ze zbioru plików": ("+++++++++", "+++++++++"),
    "detal w tytule": ("---------", "+++------"),
    "detal po obrazie": ("---------", "+++------"),
    "zdjęcie sali z dziełem": ("---------", "+++------"),
    "reprodukcja": ("---------", "+++------"),
    "szara kopia obrazu": ("---------", "++-------"),
    "szara grafika z muzeum": ("++++++-++", "++++++-++"),
    "znaczek": ("---------", "+-+------"),
    "dokument": ("---------", "+-+------"),
    "archiwum fotografii": ("---------", "+++------"),
    "archiwum sztuki, kolor": ("++-++++++", "++-++++++"),
    "archiwum sztuki, szare": ("---------", "+--------"),
    "kopia z Openverse": ("---------", "+++------"),
    "fotografia z Openverse": ("---------", "+--------"),
    "fotografia z muzeum": ("---+----+", "+--+----+"),
    "rękopis": ("---+----+", "+--+----+"),
    "rzeźba": ("---+----+", "+--+----+"),
    "ceramika": ("---+----+", "+--+----+"),
    "plakat": ("++++++-++", "++++++-++"),
    "odłożone przez Strażnika": ("---------", "+++------"),
    "mały obraz": ("++-++++++", "++-++++++"),
}

#: K1, the first oddity: what the rules call a copy (a detail, a
#: reproduction, a stamp…) may be the work of the day once the owner kept
#: it, though a grey copy he kept may not.
KEPT_COPIES_STUDIED = {
    "detal w tytule",
    "detal po obrazie",
    "zdjęcie sali z dziełem",
    "reprodukcja",
    "znaczek",
    "dokument",
    "archiwum fotografii",
    "kopia z Openverse",
    "odłożone przez Strażnika",
}

#: K1, the second: works the owner kept that the catalogue lists while it
#: is browsed and leaves out once a word is typed. ("Sztuki inne" are meant
#: to: found only when their group is asked for.)
BROWSED_NOT_FOUND = {
    "znaczek",
    "dokument",
    "archiwum sztuki, szare",
    "fotografia z Openverse",
    "fotografia z muzeum",
    "rękopis",
    "rzeźba",
    "ceramika",
}


def _work(name: str, pooled: bool) -> Item:
    source, says = SPECIMENS[name]
    slug = name.replace(" ", "-").replace(",", "")
    source_id = says.get("source_id", f"{slug}-{'pooled' if pooled else 'kept'}")
    title = WORDS[2 * list(SPECIMENS).index(name) + pooled]
    fields: dict[str, Any] = {
        "title": title,
        "artist": MONET,
        "year": 1906,
        "classification": "Painting",
        "medium": "Oil on canvas",
        "width": 3000,
        "height": 2000,
        "tint_spread": 0.05,
        # Each its own picture: one address is one work to the grouping.
        "thumb_url": f"https://example.org/{slug}-{pooled}/thumb.jpg",
        "image_url": f"https://example.org/{slug}-{pooled}/image.jpg",
        "url": f"https://example.org/{slug}-{pooled}",
        **says,
    }
    if "source_id" in says:  # one id for both: told apart by a suffix
        source_id = f"{says['source_id']}-{'pooled' if pooled else 'kept'}"
    fields["source_id"] = source_id
    fields["title"] = fields["title"].replace("{title}", title)
    return Item(
        id=f"{source}:{source_id}",
        kind=ItemKind.ARTWORK,
        source=source,
        pooled=pooled,
        **fields,
    )


def _places(service: FrameService) -> dict[str, Callable[[Item], bool]]:
    """Each place as a question about one work: is it shown (taken on)?"""
    library = service.library
    art = PlaylistRules(kinds=[ItemKind.ARTWORK])
    browsed = {i.id for i in library.query(art)[1]}
    searched = {i.id for i in library.query(art.model_copy(update={"query": "Monet"}))[1]}
    studied = {i.id for i in service.daily.pool(date(2026, 11, 11), [])}
    service.audit.per_night = 10_000
    audited = {i.id for i in service.audit.candidates({})}
    importer = service.importer
    return {
        "katalog": lambda i: i.id in browsed,
        "katalog, szukane słowem": lambda i: i.id in searched,
        "studium dnia": lambda i: i.id in studied,
        # As a museum's answer is read: Importer._ask_museum.
        "odpowiedź muzeum": lambda i: not is_copy(i) and bool(importer.without_grey([i])),
        # MuseumSearch.fits, of a search that asks for no category.
        "Szukaj w muzeach": lambda i: category_fits(i, ()),
        # themes.search_page, of a card that asks for no category.
        "karta Odkrywaj z muzeów": lambda i: not set_aside(i),
        "Strażnik": asked_by_rules,
        "Nocny przegląd": lambda i: i.id in audited,
        "powtórki": candidate,
    }


def _works(service: FrameService) -> dict[tuple[str, bool], Item]:
    works = {(name, pooled): _work(name, pooled) for name in SPECIMENS for pooled in (True, False)}
    for item in works.values():
        stored = service.library.upsert(item)
        for path in (service.images.thumb_path(stored), service.images.image_path(stored)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(jpeg_bytes((40, 70, 140), (900, 600)))
    return works


def matrix(service: FrameService) -> dict[str, tuple[str, str]]:
    works = _works(service)
    places = _places(service)

    def marks(item: Item) -> str:
        return "".join("+" if places[place](item) else "-" for place in PLACES)

    return {name: (marks(works[name, True]), marks(works[name, False])) for name in SPECIMENS}


@pytest.fixture
def quiet(service: FrameService) -> FrameService:
    # The spread of a museum's answer is the work's own: nothing downloaded.
    service.importer.spread_of = lambda item: item.tint_spread  # type: ignore[method-assign]
    return service


def test_what_every_place_says_of_every_kind(quiet: FrameService) -> None:
    found = matrix(quiet)
    width = max(map(len, SPECIMENS))
    table = "\n".join(f"{name:<{width}}  {a}  {b}" for name, (a, b) in found.items())
    assert found == EXPECTED, f"\nplaces: {', '.join(PLACES)}\n{table}"


def test_the_server_never_proposes_a_copy_it_took_in_itself(quiet: FrameService) -> None:
    """Nothing the rules call a copy, and no work of "Sztuki inne", that the
    server took in on its own is in the catalogue, found by a word, or among
    the works the work of the day is chosen from."""
    works = _works(quiet)
    places = _places(quiet)
    for (name, pooled), item in works.items():
        if pooled and set_aside(item):
            shown = [p for p in PLACES[:3] if places[p](item)]
            assert not shown, f"{name}: {shown}"


def test_where_the_places_disagree_about_works_the_owner_kept(quiet: FrameService) -> None:
    works = _works(quiet)
    places = _places(quiet)
    kept = {name: item for (name, pooled), item in works.items() if not pooled}
    studied = {n for n, i in kept.items() if is_copy(i) and places["studium dnia"](i)}
    assert studied == KEPT_COPIES_STUDIED
    browsed = {
        n
        for n, i in kept.items()
        if places["katalog"](i) and not places["katalog, szukane słowem"](i)
    }
    assert browsed == BROWSED_NOT_FOUND
