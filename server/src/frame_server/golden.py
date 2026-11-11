"""The decisions made so far about the works, as data to measure changes
of the rules against (docs/PLAN.md 3.3zzz155).

Before a rule is replaced by a more general one, what the rules, the
pictures, the judge and the owner have settled until now is the best test
there is: which pictures are one work, which are a detail or a photograph of
a work, which pairs were kept apart, which works were set aside as no art.
:func:`decisions` gathers them from the library (``GET /api/debug/decisions``)
and :func:`measure` says how a way of telling works apart does on them.

A change of what is shown is tried on the whole catalogue, away from the
frame's server: :func:`catalogue` writes every work as the library has it
(``GET /api/debug/catalogue``), :func:`works` reads them back and
:func:`library_of` makes a library of them to ask as the server's is asked.

Descriptions only, never a picture, and only works of art from museums and
other sources: the owner's own photographs are not in it.
"""

from __future__ import annotations

import gzip
import json
import zlib
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .library.duplicates import same_work
from .library.images import OWN_SOURCES
from .library.models import Item, ItemKind
from .library.repo import Library
from .library.twins import pair_key
from .library.verdict import COPIES, NAMES, Why, whys

if TYPE_CHECKING:
    from .service import FrameService

#: What a brief says of a work: all :func:`same_work` and the rules of
#: ``library/vocabulary.py`` read, and how the work was settled.
BRIEF_FIELDS = (
    "id",
    "kind",
    "source",
    "source_id",
    "title",
    "artist",
    "date_text",
    "year",
    "medium",
    "classification",
    "museum",
    "url",
    "image_url",
    "width",
    "height",
    "tint_spread",
    "pooled",
    "favorite",
    "copy_of",
    "detail_of",
    "scene_of",
    "seen_as",
    "picture_hash",
    "reproduction",
)

#: Groups by description alone listed at most (each with its works' briefs).
GROUPS_MAX = 5000


def brief(item: Item) -> dict[str, Any]:
    """``item`` as the test data keeps it: its description, no picture."""
    return item.model_dump(mode="json", include=set(BRIEF_FIELDS), exclude_defaults=True) | {
        "id": item.id,
        "source": item.source,
        "source_id": item.source_id,
    }


def work(data: dict[str, Any]) -> Item:
    """A brief as an item again (what it does not say: the defaults)."""
    return Item.model_validate(data)


#: The catalogue is written in pieces of about this many bytes.
PIECE = 1 << 16


def catalogue(library: Library) -> Iterator[bytes]:
    """Every work of art as the library has it, hidden ones too: gzip, a
    work a line (what a work does not say is its default). In pieces, the
    catalogue of a hundred thousand works is never whole in memory."""
    packer = zlib.compressobj(6, zlib.DEFLATED, 31)  # 31: a gzip file
    piece = bytearray()
    for item in library.query(include_excluded=True)[1]:
        if not _art(item):
            continue
        said = item.model_dump(mode="json", exclude_defaults=True) | {
            "id": item.id,
            "source": item.source,
            "source_id": item.source_id,
        }
        piece += packer.compress(json.dumps(said, ensure_ascii=False).encode() + b"\n")
        if len(piece) >= PIECE:
            yield bytes(piece)
            piece.clear()
    yield bytes(piece + packer.flush())


def works(path: Path) -> list[Item]:
    """The works of a catalogue saved by :func:`catalogue`."""
    with gzip.open(path, "rt", encoding="utf-8") as lines:
        return [work(json.loads(line)) for line in lines if line.strip()]


def library_of(path: Path, db: Path) -> Library:
    """A library at ``db`` holding the works of the catalogue saved at
    ``path``: asked as the server's is, with no server."""
    library = Library(db)
    for item in works(path):
        library.upsert(item)
    return library


def _art(item: Item | None) -> bool:
    return (
        item is not None
        and item.kind == ItemKind.ARTWORK
        and item.source not in OWN_SOURCES
        and item.look is None
        and item.photo is None
    )


def decisions(service: FrameService) -> dict[str, Any]:
    """What is settled about the catalogue's works of art.

    - ``same``: pairs that are one work, and ``by`` what: "description"
      (two copies the grouping holds together), "hash", "pictures", "judge"
      (``copy_of``, as the tidy log says it was written; "" when it no
      longer says);
    - ``details``, ``scenes``: a picture and the work it is a part or a
      photograph of;
    - ``apart``: pairs that are not one work, by the "owner" ("To nie to
      samo") or the "judge" (asked and kept apart, or the critic said no);
    - ``set_aside``: works the gatekeeper set aside, and as what;
    - ``kept``: works the owner kept (a heart, a playlist: not ``pooled``)
      that the rules have a reason against (``verdict.whys``: a detail, a
      reproduction, a stamp, a sculpture…), each with its reasons, whether
      it has a heart and whether it is ``studied``: among the works today's
      work of the day is chosen from;
    - ``items``: the brief of every work named above, by id.
    """
    library = service.library
    everything = {i.id: i for i in library.query(include_excluded=True)[1] if _art(i)}
    named: dict[str, Item] = {}

    def keep(*ids: str) -> bool:
        found = [everything.get(i) for i in ids]
        if any(f is None for f in found):
            return False
        named.update({f.id: f for f in found if f is not None})
        return True

    how: dict[str, str] = {}
    for entry in service.twins.log.entries(newest_first=False):
        a, b = str(entry.get("a") or ""), str(entry.get("b") or "")
        if a and b:
            how[pair_key(a, b)] = str(entry.get("by") or "")

    same: list[dict[str, str]] = []
    details: list[dict[str, str]] = []
    scenes: list[dict[str, str]] = []
    set_aside: list[dict[str, str]] = []
    linked: set[str] = set()
    for item in everything.values():
        if item.copy_of and keep(item.id, item.copy_of):
            key = pair_key(item.id, item.copy_of)
            linked.add(key)
            same.append({"a": item.id, "b": item.copy_of, "by": how.get(key, "")})
        if item.detail_of and keep(item.id, item.detail_of):
            details.append({"a": item.id, "b": item.detail_of})
        if item.scene_of and keep(item.id, item.scene_of):
            scenes.append({"a": item.id, "b": item.scene_of})
        if item.seen_as and keep(item.id):
            set_aside.append({"id": item.id, "seen_as": item.seen_as})

    # Copies the descriptions alone hold together: each with the group's
    # best copy, unless a picture or the judge named them already.
    groups = 0
    for group in library.works().groups:
        copies = [i for i in group if i.id in everything]
        if len(copies) < 2:
            continue
        if groups >= GROUPS_MAX:
            break
        first = copies[0]
        pairs = [
            (first, other)
            for other in copies[1:]
            if pair_key(first.id, other.id) not in linked and same_work(first, other)
        ]
        if not pairs:
            continue
        groups += 1
        for best, other in pairs:
            keep(best.id, other.id)
            same.append({"a": best.id, "b": other.id, "by": "description"})

    apart: list[dict[str, str]] = []
    for key in sorted(service.twins.apart()):
        a, _, b = key.partition("|")
        if keep(a, b):
            apart.append({"a": a, "b": b, "by": "owner"})
    judged = service.twins_judge.state().get("judged") or {}
    for key, said in judged.items():
        if not isinstance(said, dict) or said.get("written"):
            continue
        a, _, b = key.partition("|")
        if pair_key(a, b) not in linked and keep(a, b):
            apart.append({"a": a, "b": b, "by": "judge"})

    studied = {i.id for i in service.daily.pool(date.today(), [])}
    kept = [
        {
            "id": item.id,
            "why": [why.value for why in why],
            "liked": item.favorite,
            "studied": item.id in studied,
        }
        for item in everything.values()
        if not item.pooled and (why := whys(item)) and keep(item.id)
    ]

    return {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "works": len(everything),
        "same": same,
        "details": details,
        "scenes": scenes,
        "apart": apart,
        "set_aside": set_aside,
        "kept": kept,
        "items": {i.id: brief(i) for i in named.values()},
    }


def kept_against(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The works the owner kept that the rules have a reason against, by
    the reason as the app would say it (a copy's reasons before "Sztuki
    inne"; a work with several under its first), each as its brief with
    ``liked`` and ``studied``: the list he decides the one verdict by."""
    items = data.get("items") or {}
    found: dict[str, list[dict[str, Any]]] = {}
    for entry in data.get("kept") or []:
        reasons = [Why(value) for value in entry.get("why") or []]
        if not reasons:
            continue
        first = next((why for why in reasons if why in COPIES), reasons[0])
        work = {**(items.get(entry["id"]) or {"id": entry["id"]})}
        work.update(liked=bool(entry.get("liked")), studied=bool(entry.get("studied")))
        found.setdefault(NAMES[first], []).append(work)
    return found


def measure(
    data: dict[str, Any], same: Callable[[Item, Item], bool] = same_work
) -> dict[str, dict[str, int]]:
    """How ``same`` (two works: one work or not) does on the decisions of
    :func:`decisions`: of the pairs settled as one work, by what settled
    them, how many it holds ``together`` and how many it ``misses``; of the
    pairs kept apart, how many it leaves ``apart`` and how many it wrongly
    joins (``joined``). Details and photographs of a work are no copies of
    it: counted with the pairs kept apart."""
    items = {key: work(value) for key, value in (data.get("items") or {}).items()}
    tally: dict[str, dict[str, int]] = {}

    def count(kind: str, outcome: str) -> None:
        tally.setdefault(kind, {})[outcome] = tally.get(kind, {}).get(outcome, 0) + 1

    for pair in data.get("same") or []:
        a, b = items.get(pair["a"]), items.get(pair["b"])
        if a is None or b is None:
            continue
        kind = f"same by {pair.get('by') or 'unknown'}"
        count(kind, "together" if same(a, b) else "misses")
    for name, by in (("apart", ""), ("details", "detail"), ("scenes", "scene")):
        for pair in data.get(name) or []:
            a, b = items.get(pair["a"]), items.get(pair["b"])
            if a is None or b is None:
                continue
            kind = f"apart by {by or pair.get('by') or 'unknown'}"
            count(kind, "joined" if same(a, b) else "apart")
    return tally


def main(argv: list[str] | None = None) -> int:
    """``python -m frame_server.golden decisions.json``: how today's rule
    for "one work" does on the decisions saved from
    ``/api/debug/decisions``, a line for each kind of pair."""
    import sys

    paths = sys.argv[1:] if argv is None else argv
    if len(paths) != 1:
        print("usage: python -m frame_server.golden decisions.json", file=sys.stderr)
        return 2
    data = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    print(f"{data.get('works', '?')} works, saved {data.get('at', '?')}")
    for kind, counts in sorted(measure(data).items()):
        told = ", ".join(f"{n} {what}" for what, n in sorted(counts.items()))
        print(f"{kind}: {told}")
    print(f"set aside by the gatekeeper: {len(data.get('set_aside') or [])}")
    for name, works in sorted(kept_against(data).items()):
        studied = sum(w["studied"] for w in works)
        print(f"kept, {name}: {len(works)} ({studied} may be the work of the day)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
