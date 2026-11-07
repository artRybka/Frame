"""Each source's rules for programs, in one place (Mateusz 2026-11-07:
"spójny model i polityka korzystania ze źródeł").

A :class:`Source` names where its rules are published and when they were
read, and how each of its hosts is asked: the least time between two
requests (``pace``), how many at once (``limit``), how long a block lasts
when it is a fixed one (``long_block``), how many pictures are downloaded at
once (``images``) and a quota over an hour or a day (``budget``).
:mod:`.hosts` (the requests) and :mod:`.images` (the downloads) read the
tables below and nothing else.

A host no source names gets :data:`DEFAULT_LIMIT` requests at once and no
pace: as many as the image downloads already took (four, two more for what
the owner waits for), so nothing gets slower, and no host gets more.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: The Wikimedia wikis' API, counted as one host: Wikimedia limits programs
#: without an account across all wikis together (its robot policy).
WIKIMEDIA = "wikimedia-api"
WIKIMEDIA_HOSTS = frozenset({"commons.wikimedia.org", "www.wikidata.org", "meta.wikimedia.org"})
#: Wikimedia's media files, counted as one host: originals come from
#: upload.wikimedia.org, Special:FilePath's renditions from thumb.wikimedia.org.
WIKIMEDIA_MEDIA = "wikimedia-media"
MEDIA_HOSTS = frozenset({"upload.wikimedia.org", "thumb.wikimedia.org"})

#: Requests at once to a host no source names.
DEFAULT_LIMIT = 6
#: Pictures downloaded at once from a host no source names ...
DEFAULT_IMAGES = 4
#: ... and that many more for what the owner waits for (a card's original).
URGENT_EXTRA = 2

HOUR = 3600.0
DAY = 24 * HOUR


@dataclass(frozen=True)
class Budget:
    """At most ``count`` requests in any ``window`` seconds. What the owner
    waits for (:func:`.hosts.urgently`) may use the whole quota, the
    background only what leaves ``reserve`` of it, so a night's work never
    leaves Szukaj without requests."""

    count: int
    window: float
    reserve: float = 0.4
    #: Only requests without credentials count (Openverse: app credentials
    #: have a quota of their own, far larger).
    anonymous_only: bool = False

    @property
    def background(self) -> int:
        return int(self.count * (1 - self.reserve))


@dataclass(frozen=True)
class Host:
    pace: float = 0.0
    limit: int | None = None
    #: A block of a fixed length (loc.gov: an hour): rested that long at
    #: once, also after a 429 without Retry-After, and not probed meanwhile.
    long_block: float | None = None
    #: Pictures downloaded at once (none of the urgent extra when set).
    images: int | None = None
    budget: Budget | None = None


@dataclass(frozen=True)
class Source:
    name: str
    #: Where its rules for programs are, and when they were read; empty when
    #: it publishes none (then it is asked like any host, gently).
    rules: str
    checked: str
    #: By host, or by :func:`.hosts.lane` for hosts counted together.
    hosts: dict[str, Host] = field(default_factory=dict)
    #: Domains of its other hosts (pictures, IIIF), asked like any host;
    #: only for counting requests by source (Konfiguracja → Diagnostyka).
    domains: tuple[str, ...] = ()


SOURCES: tuple[Source, ...] = (
    Source(
        # "Scraping Images": 60 requests a minute, one picture at a time, a
        # second apart, no scrapers in parallel; widths in library/aic.py.
        "Art Institute of Chicago",
        "https://api.artic.edu/docs/",
        "2026-11-04",
        {
            "api.artic.edu": Host(pace=1.0, limit=1),
            "www.artic.edu": Host(pace=1.0, limit=1, images=1),
        },
        domains=("artic.edu",),
    ),
    Source(
        # 80 requests a second; its bot wall (Imperva) turned bursts of a few
        # hundred a minute away (2026-10-30, 2026-11-07): one at a time.
        "The Metropolitan Museum of Art",
        "https://metmuseum.github.io/",
        "2026-11-07",
        {
            "collectionapi.metmuseum.org": Host(pace=0.25, limit=1),
            "images.metmuseum.org": Host(pace=0.25),
            # The open-access CSV (library/met_index.py), on GitHub's LFS.
            "media.githubusercontent.com": Host(),
        },
        domains=("metmuseum.org",),
    ),
    Source(
        # Robot policy: the Action API one request at a time and below five a
        # second for all wikis together; media at most two at a time.
        "Wikimedia",
        "https://wikitech.wikimedia.org/wiki/Robot_policy",
        "2026-11-04",
        {
            WIKIMEDIA: Host(pace=0.25, limit=1),
            WIKIMEDIA_MEDIA: Host(limit=2),
            "upload.wikimedia.org": Host(images=2),
            "thumb.wikimedia.org": Host(images=2),
            "commons.wikimedia.org": Host(images=2),
            # The query service: five queries at once from one address, a
            # minute of work a minute; Louvre's list and the holders ask it.
            "query.wikidata.org": Host(limit=5),
        },
        domains=("wikimedia.org", "wikipedia.org", "wikidata.org"),
    ),
    Source(
        # "Working within limits": the JSON API 20 requests a minute, image
        # and storage services 150 a minute, else an hour's block.
        "Library of Congress",
        "https://www.loc.gov/apis/json-and-yaml/working-within-limits/",
        "2026-11-07",
        {
            "www.loc.gov": Host(pace=3.5, limit=1, long_block=HOUR),
            "tile.loc.gov": Host(pace=0.5),
        },
        domains=("loc.gov",),
    ),
    Source(
        # The free package: four requests a second, 400 an hour.
        "WikiArt",
        "https://www.wikiart.org/en/App/GetApi",
        "2026-11-04",
        {"www.wikiart.org": Host(pace=1.0, budget=Budget(400, HOUR))},
        domains=("wikiart.org",),
    ),
    Source(
        # api.data.gov: 1000 requests an hour a key; a 429 blocks it for
        # up to an hour.
        "Smithsonian Open Access",
        "https://api.data.gov/docs/developer-manual/",
        "2026-11-04",
        {"api.si.edu": Host(budget=Budget(1000, HOUR))},
        domains=("si.edu",),
    ),
    Source(
        # About 1000 requests a day a token.
        "Paris Musées",
        "https://apicollections.parismusees.paris.fr/",
        "2026-11-04",
        {"apicollections.parismusees.paris.fr": Host(budget=Budget(1000, DAY))},
        domains=("paris.fr",),
    ),
    Source(
        # Anonymous: 20 requests a minute, 200 a day; app credentials more.
        "Openverse",
        "https://api.openverse.org/v1/",
        "2026-11-04",
        {"api.openverse.org": Host(budget=Budget(200, DAY, anonymous_only=True))},
        domains=("openverse.org",),
    ),
    Source(
        # "An absolute maximum of 1 request per second".
        "Nominatim (OpenStreetMap)",
        "https://operations.osmfoundation.org/policies/nominatim/",
        "2026-11-04",
        {"nominatim.openstreetmap.org": Host(pace=1.0, limit=1)},
        domains=("openstreetmap.org",),
    ),
    Source(
        # REST searches up to 10 000 objects, everything else over OAI-PMH;
        # no rates published. A search page is a request a work (cached:
        # library/records.py), asked two at a time.
        "Rijksmuseum",
        "https://data.rijksmuseum.nl/docs/",
        "2026-11-07",
        {"data.rijksmuseum.nl": Host(limit=2), "id.rijksmuseum.nl": Host(limit=2)},
        domains=("rijksmuseum.nl", "micr.io"),
    ),
    Source(
        # No rates published; a result is two requests a work (cached:
        # library/records.py), four at a time as before.
        "Yale (LUX)",
        "",
        "2026-11-07",
        {
            "lux.collections.yale.edu": Host(limit=4),
            "manifests.collections.yale.edu": Host(limit=4),
        },
        domains=("yale.edu",),
    ),
    Source(
        # No API and no rules: its paintings' pages and pictures gently.
        "The Courtauld",
        "",
        "2026-11-04",
        {"gallerycollections.courtauld.ac.uk": Host(pace=0.5, limit=2)},
        domains=("courtauld.ac.uk",),
    ),
    Source(
        # No rules for programs (a bot wall on its search pages): entries
        # (JSON) and photographs gently. Terms: private use with credit.
        "Louvre",
        "https://collections.louvre.fr/en/page/cgu",
        "2026-11-05",
        {"collections.louvre.fr": Host(pace=0.5, limit=2)},
        domains=("louvre.fr",),
    ),
    Source(
        # The site's own search, not documented: gently.
        "J. Paul Getty Museum",
        "",
        "2026-11-06",
        {"www.getty.edu": Host(pace=0.5)},
        domains=("getty.edu",),
    ),
    Source(
        # The key in a header; "reasonable concurrency".
        "Europeana",
        "https://pro.europeana.eu/page/intro",
        "2026-11-04",
        {"api.europeana.eu": Host()},
        domains=("europeana.eu",),
    ),
    Source(
        # The open data on GitHub, read whole (library/nga.py); pictures over
        # IIIF, no rules published.
        "National Gallery of Art",
        "https://github.com/NationalGalleryOfArt/opendata",
        "2026-11-07",
        {"raw.githubusercontent.com": Host()},
        domains=("nga.gov",),
    ),
    Source(
        "Cleveland Museum of Art",
        "https://github.com/ClevelandMuseumArt/openaccess",
        "2026-11-07",
        {"openaccess-api.clevelandart.org": Host()},
        domains=("clevelandart.org",),
    ),
    Source(
        "Wellcome Collection",
        "https://developers.wellcomecollection.org/docs/catalogue",
        "2026-11-07",
        {"api.wellcomecollection.org": Host()},
        domains=("wellcomecollection.org",),
    ),
    # No rules published; asked like any host.
    Source("Statens Museum for Kunst", "", "2026-11-04", {"api.smk.dk": Host()}, ("smk.dk",)),
    Source(
        "Muzeum Narodowe w Warszawie i w Krakowie (Muza)",
        "",
        "2026-11-04",
        {"cyfrowe-api.mnw.art.pl": Host(), "api-zbiory.mnk.pl": Host()},
        domains=("mnw.art.pl", "mnw.pl", "mnk.pl"),
    ),
    Source(
        "Victoria and Albert Museum", "", "2026-11-04", {"api.vam.ac.uk": Host()}, ("vam.ac.uk",)
    ),
)


def _table[T](pick: str) -> dict[str, T]:
    found: dict[str, T] = {}
    for source in SOURCES:
        for host, rules in source.hosts.items():
            value = getattr(rules, pick)
            if value:
                found[host] = value
    return found


#: The least time between two requests to a host (or lane), in seconds.
PACE: dict[str, float] = _table("pace")
#: The most requests under way at once to a host (or lane).
LIMITS: dict[str, int] = _table("limit")
#: Hosts whose block lasts a fixed time, and how long.
LONG_BLOCKS: dict[str, float] = _table("long_block")
#: Pictures downloaded at once from a host, where not :data:`DEFAULT_IMAGES`.
IMAGE_LIMITS: dict[str, int] = _table("images")
#: Quotas, by host.
BUDGETS: dict[str, Budget] = _table("budget")


def source_of(host: str) -> Source | None:
    """The source whose rules ``host`` (or its lane) keeps to."""
    for source in SOURCES:
        if host in source.hosts:
            return source
    return None


def owner_of(host: str) -> Source | None:
    """The source ``host`` belongs to: one of its hosts, or a host of one of
    its domains (a museum's pictures and IIIF); None for the rest
    (Openverse's and Europeana's pictures come from their holders)."""
    found = source_of(host)
    if found is not None:
        return found
    for source in SOURCES:
        if any(host == d or host.endswith("." + d) for d in source.domains):
            return source
    return None
