"""Where works are: one key for each museum, however a source spells it.

Szukaj's "Muzeum" chooses places, not sources (Mateusz, 2026-11-08: "grupa
Muzea w Szukaj musiałaby … przestać wskazywać źródła dzieł, a określać
kolekcje/muzeum, czyli to gdzie fizycznie dzieło jest"). A place's key is
its Wikidata item ("Q190804" for the Rijksmuseum): the Met's own API, a
Commons file's Wikidata collection and Europeana's data provider all name
the same museum differently, and the key joins them. A museum nobody has
found on Wikidata yet is keyed by its folded name (``name:…``) until the
night finds it (:meth:`Places.canon` then answers its item for both).

Museums with an API of their own are known here with their names as the app
shows them and their cities; the rest are learnt (a work's collection on
Wikidata names it) and kept in the library's state.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

#: A key made from a name nobody has found on Wikidata yet.
NAME = "name:"
#: A Wikidata item.
QID = re.compile(r"^Q\d+$")


@dataclass(frozen=True)
class Place:
    """A museum (or a church, a library) where works are."""

    key: str
    name: str
    city: str = ""
    #: The source that is this museum's own collection ("rijks"), if any:
    #: asked when the place is chosen.
    source: str = ""


def _place(qid: str, name: str, city: str, source: str = "") -> tuple[str, Place]:
    return qid, Place(qid, name, city, source)


#: Museums whose collection is a source of ours, as the app names them.
OWN: dict[str, Place] = dict(
    [
        _place("Q239303", "Art Institute of Chicago", "Chicago", "aic"),
        _place("Q657415", "Cleveland Museum of Art", "Cleveland", "cma"),
        _place("Q160236", "Metropolitan Museum of Art", "Nowy Jork", "met"),
        _place("Q190804", "Rijksmuseum", "Amsterdam", "rijks"),
        _place("Q671384", "Statens Museum for Kunst", "Kopenhaga", "smk"),
        _place("Q214867", "National Gallery of Art", "Waszyngton", "nga"),
        _place("Q153306", "Muzeum Narodowe w Warszawie", "Warszawa", "mnw"),
        _place("Q195311", "Muzeum Narodowe w Krakowie", "Kraków", "mnk"),
        _place("Q6352575", "Yale Center for British Art", "New Haven", "yale"),
        _place("Q1568434", "Yale University Art Gallery", "New Haven", "yale"),
        _place("Q1192305", "Smithsonian American Art Museum", "Waszyngton", "si"),
        _place("Q1967614", "National Portrait Gallery", "Waszyngton", "si"),
        _place("Q105749808", "National Museum of Asian Art", "Waszyngton", "si"),
        _place("Q1620553", "Hirshhorn Museum and Sculpture Garden", "Waszyngton", "si"),
        _place("Q1129820", "Cooper Hewitt, Smithsonian Design Museum", "Nowy Jork", "si"),
        _place("Q46812", "National Museum of African Art", "Waszyngton", "si"),
        _place("Q213322", "Victoria and Albert Museum", "Londyn", "vam"),
        _place("Q7981191", "Wellcome Collection", "Londyn", "wellcome"),
        _place("Q12110695", "Courtauld Gallery", "Londyn", "courtauld"),
        _place("Q731126", "J. Paul Getty Museum", "Los Angeles", "getty"),
        _place("Q19675", "Luwr", "Paryż", "louvre"),
        _place("Q131454", "Biblioteka Kongresu", "Waszyngton", "loc"),
        _place("Q640447", "Musée Carnavalet", "Paryż", "paris"),
        _place("Q2599177", "Maison de Victor Hugo", "Paryż", "paris"),
        _place("Q2714932", "Musée de la Vie romantique", "Paryż", "paris"),
    ]
)

#: The places of a source that is one museum's collection, or of several
#: (Yale's two, the Smithsonian's units). Paris Musées' fourteen museums are
#: told apart by their names; those not listed are learnt.
SOURCE_PLACES: dict[str, tuple[str, ...]] = {}
for _place_ in OWN.values():
    SOURCE_PLACES.setdefault(_place_.source, ())
    SOURCE_PLACES[_place_.source] += (_place_.key,)

#: Sources with no museum of their own: pictures gathered from many.
GATHERING = ("wmc", "europeana", "openverse", "wikiart")

#: Other names of the museums above: the sources', Wikidata's Polish and
#: English labels, what Commons and Europeana write.
_ALIASES: dict[str, tuple[str, ...]] = {
    "Q239303": ("The Art Institute of Chicago",),
    "Q657415": ("The Cleveland Museum of Art",),
    "Q160236": ("The Metropolitan Museum of Art", "The Met", "Metropolitan Museum"),
    "Q190804": ("Rijksmuseum Amsterdam", "Rijks Museum"),
    "Q671384": ("SMK", "Państwowe Muzeum Sztuki w Kopenhadze", "National Gallery of Denmark"),
    "Q214867": (
        "Narodowa Galeria Sztuki w Waszyngtonie",
        "National Gallery of Art, Washington",
        "National Gallery of Art Washington",
    ),
    "Q153306": ("National Museum in Warsaw", "Muzeum Narodowe Warszawa"),
    "Q195311": ("National Museum in Kraków", "National Museum in Krakow", "Muzeum Narodowe Kraków"),
    "Q6352575": ("YCBA",),
    "Q1568434": ("YUAG",),
    "Q1192305": (
        "Smithsonian American Art Museum and the Renwick Gallery",
        "Smithsonian American Art Museum and Renwick Gallery",
    ),
    "Q1967614": (
        "National Portrait Gallery w Waszyngtonie",
        "National Portrait Gallery, Washington",
    ),
    "Q105749808": ("Freer Gallery of Art", "Arthur M. Sackler Gallery", "Freer|Sackler"),
    "Q46812": ("Narodowe Muzeum Sztuki Afrykańskiej",),
    "Q213322": (
        "Muzeum Wiktorii i Alberta",
        "Victoria & Albert Museum",
        "V&A",
        "V&A Museum",
    ),
    "Q731126": (
        "The J. Paul Getty Museum",
        "Getty Museum",
        "Getty Center",
        "J. Paul Getty Museum, Los Angeles",
    ),
    "Q12110695": ("The Courtauld", "Courtauld Institute of Art", "Courtauld Institute Galleries"),
    "Q19675": ("Louvre", "Louvre Museum", "Musée du Louvre", "Muzeum Luwru"),
    "Q131454": ("Library of Congress", "Biblioteka Kongresu Stanów Zjednoczonych"),
    "Q640447": (
        "Carnavalet",
        "Musée Carnavalet, Histoire de Paris",
        "Musée Carnavalet - Histoire de Paris",
    ),
    "Q2599177": ("Maisons de Victor Hugo", "Maison de Victor Hugo - Hauteville House"),
}

#: A source's own word for one of its museums, where a name alone would
#: mean another ("National Portrait Gallery" is in London as well).
_SOURCE_NAMES: dict[str, dict[str, str]] = {
    "si": {
        "national portrait gallery": "Q1967614",
        "national museum of asian art": "Q105749808",
    },
}


def fold(text: str) -> str:
    """A name for comparing: lower case, no accents, no leading "the", one
    space between words ("The Metropolitan Museum of Art" and "metropolitan
    museum of art" are one)."""
    decomposed = unicodedata.normalize("NFKD", text.replace("ł", "l").replace("Ł", "L"))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    plain = plain.replace("&", " and ")
    words = re.findall(r"\w+", plain)
    if words and words[0] in ("the", "le", "la", "les", "il", "het", "de"):
        words = words[1:]
    return " ".join(words)


def name_key(name: str) -> str:
    """The key of a museum known only by its name."""
    return NAME + fold(name) if fold(name) else ""


class Places:
    """Who is where: the museums known here and those learnt."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: Places learnt from Wikidata, by their item.
        self._learnt: dict[str, Place] = {}
        #: Folded names of museums, and their items.
        self._aliases: dict[str, str] = {}
        #: Folded names Wikidata was asked about and knew nothing of.
        self._unknown: set[str] = set()
        #: Europeana's names of its data providers, by place.
        self._providers: dict[str, str] = {}
        #: Names of museums met while someone typed, not learnt yet.
        self._heard: dict[str, str] = {}
        #: A Commons file of a work in each place with none in the catalogue
        #: (Szukaj's band behind its name); "" when Wikidata knows none.
        self._pictures: dict[str, str] = {}
        self._fixed: dict[str, str] = {}
        for qid, place in OWN.items():
            self._fixed[fold(place.name)] = qid
            for alias in _ALIASES.get(qid, ()):
                self._fixed[fold(alias)] = qid

    # -- what is known -----------------------------------------------------------

    def place(self, key: str) -> Place | None:
        key = self.canon(key)
        if key in OWN:
            return OWN[key]
        with self._lock:
            return self._learnt.get(key)

    def name(self, key: str) -> str:
        """The place's name, "" when only its key is known."""
        found = self.place(key)
        if found is not None:
            return found.name
        with self._lock:
            return self._heard.get(key, "")

    def qid_of(self, name: str, source: str = "") -> str:
        """The Wikidata item of the museum ``name`` (as ``source`` writes it),
        "" when nobody knows it."""
        folded = fold(name)
        if not folded:
            return ""
        if qid := _SOURCE_NAMES.get(source, {}).get(folded):
            return qid
        if qid := self._fixed.get(folded):
            return qid
        with self._lock:
            return self._aliases.get(folded, "")

    def key_of(self, name: str, source: str = "") -> str:
        """The key of the museum ``name``: its Wikidata item when known, else
        its folded name; "" for no name. A source that is one museum's
        collection answers that museum for a name it alone uses."""
        if qid := self.qid_of(name, source):
            return qid
        places = SOURCE_PLACES.get(source, ())
        if len(places) == 1:
            return places[0]
        return name_key(name)

    def canon(self, key: str) -> str:
        """``key`` as it stands now: a name's key turns into the museum's
        Wikidata item once that is known."""
        if key.startswith(NAME):
            folded = key[len(NAME) :]
            if qid := self._fixed.get(folded):
                return qid
            with self._lock:
                return self._aliases.get(folded, key)
        return key

    def provider(self, key: str) -> str:
        """Europeana's name of the place, when it is one of its providers."""
        with self._lock:
            return self._providers.get(self.canon(key), "")

    def unresolved(self, names: Iterable[str]) -> list[str]:
        """Of ``names``, those no key of a Wikidata item stands for yet and
        Wikidata was not asked about."""
        out: list[str] = []
        with self._lock:
            for name in names:
                folded = fold(name)
                if (
                    folded
                    and folded not in self._fixed
                    and folded not in self._aliases
                    and folded not in self._unknown
                    and name not in out
                ):
                    out.append(name)
        return out

    def unnamed(self, keys: Iterable[str]) -> list[str]:
        """Of ``keys``, the Wikidata items whose name and city are not known."""
        with self._lock:
            return [
                k
                for k in dict.fromkeys(keys)
                if QID.match(k) and k not in OWN and k not in self._learnt
            ]

    # -- learning ------------------------------------------------------------------

    def learn(self, qid: str, name: str, city: str = "", aliases: Iterable[str] = ()) -> None:
        """The place ``qid`` is called ``name`` and is in ``city``; ``aliases``
        are other names it goes by."""
        if not QID.match(qid):
            return
        with self._lock:
            if qid not in OWN and name:
                self._learnt[qid] = Place(qid, name, city)
            for alias in (name, *aliases):
                folded = fold(alias)
                if folded and folded not in self._fixed:
                    self._aliases[folded] = qid
                    self._unknown.discard(folded)

    def alias(self, name: str, qid: str) -> None:
        """``name`` is the museum ``qid`` (Europeana's data provider, a
        holder's name)."""
        self.learn(qid, "", aliases=[name])

    def heard(self, qid: str, name: str) -> None:
        """A museum's name met in a search, until the night learns it."""
        if QID.match(qid) and name:
            with self._lock:
                self._heard[qid] = name

    def not_found(self, name: str) -> None:
        with self._lock:
            if folded := fold(name):
                self._unknown.add(folded)

    def provides(self, key: str, provider: str) -> None:
        """Europeana's works of ``key`` come from its data provider ``provider``."""
        if provider and key:
            with self._lock:
                self._providers.setdefault(key, provider)

    def picture(self, key: str) -> str | None:
        """The Commons file shown for ``key``; "" when it has none, None
        when nobody has looked yet."""
        with self._lock:
            return self._pictures.get(self.canon(key))

    def pictured(self, key: str, file: str) -> None:
        with self._lock:
            self._pictures[self.canon(key)] = file

    # -- keeping -------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "places": {k: [p.name, p.city] for k, p in self._learnt.items()},
                "aliases": dict(self._aliases),
                "unknown": sorted(self._unknown),
                "providers": dict(self._providers),
                "pictures": dict(self._pictures),
                "heard": dict(self._heard),
            }

    @classmethod
    def from_state(cls, data: Mapping[str, Any] | None) -> Places:
        found = cls()
        data = data or {}
        for qid, (name, city) in (data.get("places") or {}).items():
            if QID.match(qid) and qid not in OWN:
                found._learnt[qid] = Place(qid, str(name), str(city))
        found._aliases.update(
            {str(k): str(v) for k, v in (data.get("aliases") or {}).items() if QID.match(str(v))}
        )
        found._unknown.update(str(n) for n in data.get("unknown") or [])
        found._providers.update({str(k): str(v) for k, v in (data.get("providers") or {}).items()})
        found._pictures.update({str(k): str(v) for k, v in (data.get("pictures") or {}).items()})
        # Museums met while typing, chosen maybe (a playlist's chip): named
        # until the night learns them.
        found._heard.update(
            {str(k): str(v) for k, v in (data.get("heard") or {}).items() if QID.match(str(k))}
        )
        return found


_known = Places()


def known_places() -> Places:
    return _known


def learn_places(places: Places) -> None:
    """Who is where from now on (the library's state at start, a test's)."""
    global _known
    _known = places


def source_place(source: str) -> str:
    """The place of a source that is one museum's collection, "" else."""
    places = SOURCE_PLACES.get(source, ())
    return places[0] if len(places) == 1 else ""


def migrate_sources(sources: Iterable[str]) -> tuple[list[str], list[str]]:
    """Old rules' museums as places: (places, sources still kept as sources).
    A museum's own collection becomes its places (Yale's two, the
    Smithsonian's six); a source gathering pictures from many, or the
    owner's own photos, stays a source."""
    places: list[str] = []
    kept: list[str] = []
    for source in sources:
        if source in SOURCE_PLACES and source != "paris":
            places += [p for p in SOURCE_PLACES[source] if p not in places]
        elif source not in kept:
            kept.append(source)
    return places, kept
