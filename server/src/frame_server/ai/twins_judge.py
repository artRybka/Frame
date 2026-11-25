"""Two pictures shown to a model: one work, a part of it, a photograph of it
on its wall, a copy by another hand, or two works.

At night (:class:`NightJudge`) the pairs the pictures could not settle
(``library.twins`` suspects) go to Haiku through the Batch API; what would
hide a picture (one work, a part, a photograph) is then put to a critic,
Haiku again with the opposite question: look for what says it is not so.
Only what the critic confirms is written (Mateusz 2026-11-10 13:48: „A
gdyby tylko haiku, a przy próbie schowania ponownie haiku jako krytyk?”);
the rest stays as it was.

The pictures tell most copies apart on their own (``library.twins``), but
not all: one scan in two colours, a print after a painting, two landscapes
of one dune. Before a model judges the pairs the pictures were unsure of
every night, Haiku, Sonnet, Opus and Fable are tried on pairs Mateusz's Vermeer
search showed (labelled by hand): the cheapest one that never calls two
works one is the judge (Mateusz 2026-11-10, card "Reguły teraz, potem test
i sędzia"). This is the question each of them is asked.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..library.picture_hash import NONE as NO_HASH
from ..library.picture_hash import distance as hash_distance
from ..library.twins import HASH_NEAR
from ..library.verdict import Place, against
from .client import HAIKU, SONNET, image_block, request
from .daily import _object, _str
from .night_order import CheckedNight

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from ..library.twins import Twins
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

KIND = "twins.judge"
#: The pictures go out as the server keeps its thumbnails (640 px).
SIDE = 640
#: How the second picture relates to the first, as the test script counts.
RELATIONS = (
    "same",
    "a_detail_of_b",
    "b_detail_of_a",
    "a_photo_of_b",
    "b_photo_of_a",
    "copy_by_other_hand",
    "different",
    "unsure",
)
#: What the model is asked: what kind of pair, and for a part or a
#: photograph, which picture is the whole work. One label naming both
#: ("a_detail_of_b") was read backwards by Haiku 6 times in 73 pairs while
#: its own reason said it right (test of 2026-11-10).
KINDS = ("same", "part", "photo", "copy_by_other_hand", "different", "unsure")
WHOLE = ("A", "B", "none")

SYSTEM = """You compare two catalogue pictures of artworks, A and B, for a home art frame \
that must show each artwork once. Decide what kind of pair they are.

"kind":
- "same": both show the same physical artwork whole. Different photographs, colour, \
lighting, sharpness, a trimmed or kept frame, a few percent cropped off an edge, a \
restoration state: still "same". A cast over the whole picture (white balance, a faded \
photograph or print, yellowed varnish: flowers cream in one and yellow in the other) is \
photography, not another artwork: compare shapes and their places.
- "part": one picture shows only a part of the artwork the other shows whole (a head, a \
corner, a window), so much is missing that it is no longer the whole work.
- "photo": one picture is a photograph of the artwork the other shows, together with \
what is around it: a wide frame, the museum wall, a room, a label, visitors.
- "copy_by_other_hand": a different object repeating the composition: a print or \
engraving after a painting, a painted copy, a replica or version by the artist or the \
workshop, a pastiche, a photograph of such a print. Look for different brushwork or line, \
changed details, hatching, a plate margin or lettering.
- "different": two artworks, even by the same artist or of the same subject.
- "unsure": the pictures do not allow a decision.

"whole": for "part" and "photo", the letter of the picture that shows the artwork whole \
and alone ("A" or "B"); the other one is the part or the photograph. For every other \
kind, "none".

Titles, makers and dates come from different museums and languages and are often wrong: \
judge by the pictures, using the texts only as hints. Calling two different artworks \
"same", or taking the whole work for the part, hides an artwork from the owner, so say \
"same" only when the picture content matches figure for figure. Answer with "why" in at \
most 20 words first, then "kind", "whole" and "confidence" from 0 to 1."""

SCHEMA = _object(
    why=_str(),
    kind={"type": "string", "enum": list(KINDS)},
    whole={"type": "string", "enum": list(WHOLE)},
    confidence={"type": "number"},
)


#: What hides a picture once written: a claim the critic is asked about.
CLAIMS = ("same", "a_detail_of_b", "b_detail_of_a", "a_photo_of_b", "b_photo_of_a")
VERDICTS = ("confirm", "reject")

CRITIC = """You check a claim about two catalogue pictures of artworks, A and B, \
before a home art frame acts on it. If the claim is accepted, one picture is hidden \
from the owner for good: merged with the other as one artwork, or set aside as a part \
or a photograph of it. A wrong claim hides an artwork the owner wanted to see.

Look for evidence against the claim: figures, objects, a signature or edges in one \
picture that the other lacks where they should overlap; different shapes or \
proportions; colours that differ beyond lighting and photography (a cast over the whole \
picture, cream for yellow, is photography); a part that shows \
more around its edges than the whole has there; a fragment or cut-down painting that \
is a canvas of its own; a print, an engraving, a copy or another version instead of the \
same object. Titles, makers and dates are often wrong: judge by the pictures.

"confirm" only when the pictures agree figure for figure wherever they should; otherwise \
"reject". Answer with "why" in at most 20 words first, then "verdict" and "confidence" \
from 0 to 1."""

CRITIC_SCHEMA = _object(
    why=_str(),
    verdict={"type": "string", "enum": list(VERDICTS)},
    confidence={"type": "number"},
)

_CLAIM_TEXT = {
    "same": "A and B show the same physical artwork, each of them whole.",
    "b_detail_of_a": "B shows only a part of the artwork that A shows whole: B lies within A.",
    "a_detail_of_b": "A shows only a part of the artwork that B shows whole: A lies within B.",
    "b_photo_of_a": (
        "B is a photograph of the artwork that A shows, with its frame, wall or room "
        "around it: A lies within B."
    ),
    "a_photo_of_b": (
        "A is a photograph of the artwork that B shows, with its frame, wall or room "
        "around it: B lies within A."
    ),
}


def relation(kind: str, whole: str) -> str:
    """The answer as one of :data:`RELATIONS` ("" when it makes no sense:
    a part without its whole)."""
    if kind in ("part", "photo"):
        if whole not in ("A", "B"):
            return ""
        what = "detail" if kind == "part" else "photo"
        return f"b_{what}_of_a" if whole == "A" else f"a_{what}_of_b"
    return kind if kind in RELATIONS else ""


def _label(name: str, item: Item) -> str:
    parts = [
        f"{name}: {item.title or '(no title)'}",
        f"maker: {item.artist or '?'}",
        f"date: {item.date_text or item.year or '?'}",
        f"source: {item.source}",
    ]
    if item.medium:
        parts.append(f"medium: {item.medium}")
    if item.width and item.height:
        parts.append(f"picture: {item.width}×{item.height} px")
    return "; ".join(parts)


def _pictures(images: ImageCache, a: Item, b: Item) -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": "Picture A:"},
        image_block(images, a, SIDE),
        {"type": "text", "text": "Picture B:"},
        image_block(images, b, SIDE),
        {"type": "text", "text": f"{_label('A', a)}\n{_label('B', b)}"},
    ]


def params(
    images: ImageCache, a: Item, b: Item, model: str, effort: str = "low", claim: str = ""
) -> dict[str, Any]:
    """The question about ``a`` and ``b`` for ``model``; with ``claim`` (one
    of :data:`CLAIMS`), the critic's question about it."""
    content = _pictures(images, a, b)
    if claim:
        content.append({"type": "text", "text": f"The claim: {_CLAIM_TEXT[claim]}"})
        return request(
            model=model,
            system=CRITIC,
            content=content,
            schema=CRITIC_SCHEMA,
            max_tokens=4000,
            effort=effort,
        )
    return request(
        model=model, system=SYSTEM, content=content, schema=SCHEMA, max_tokens=4000, effort=effort
    )


def read(data: dict[str, Any] | None, claim: str = "") -> tuple[str, float, str]:
    """An answer as (relation or verdict, confidence, why)."""
    data = data or {}
    if claim:
        verdict = str(data.get("verdict") or "")
        found = verdict if verdict in VERDICTS else ""
    else:
        found = relation(str(data.get("kind") or ""), str(data.get("whole") or ""))
    return found, float(data.get("confidence") or 0.0), str(data.get("why") or "")


# -- at night ------------------------------------------------------------------

#: The judge's state (library): the batch under way, the claims waiting for
#: the critic and what was judged (not asked again).
STATE_KEY = "twins_judge"
#: The judge and the critic (Haiku both: Fable 50 times dearer judged the
#: test pairs as well, and the monthly limit is 5 USD).
JUDGE = HAIKU
CRITIC_MODEL = HAIKU
#: Pairs asked about in one night at most (Haiku through the Batch API: about
#: 0.01 cent a pair).
PAIRS_A_NIGHT = 400
#: Pairs remembered as judged, the newest.
JUDGED_MAX = 20_000
#: The second opinion: a pair whose thumbnails' hashes are this close
#: (``library.twins.HASH_NEAR``) that Haiku kept apart is asked of Sonnet,
#: and a claim of Sonnet's goes to Sonnet as the critic. Haiku called the
#: faded and the clean photograph of van Gogh's "Poppy Flowers" (35 bits
#: apart) "yellow chrysanthemums against white flowers", Sonnet one picture
#: (Mateusz 2026-11-23). About 0.4 cent a pair, few pairs.
SECOND = SONNET
SECOND_A_NIGHT = 100
#: What Haiku said that is asked again.
SECOND_FOR = ("different", "unsure")
#: Raised to ask again of the pairs judged before: what Haiku kept apart
#: before the second opinion was (1: 2026-11-23).
SECOND_AGAIN = 1


class NightJudge(CheckedNight):
    """The pairs the pictures could not settle, judged at night: Haiku asks
    what they are; what would hide a picture goes to the critic; only what
    it confirms is written (:meth:`Twins.apply`)."""

    name = "twins judge"

    def __init__(
        self,
        library: Library,
        images: ImageCache,
        twins: Twins,
        claude: Claude,
        config: AiConfigStore,
    ) -> None:
        self.library = library
        self.images = images
        self.twins = twins
        self.claude = claude
        self.config = config
        #: The works cared about, by id (``cared.Cared``): their pairs first.
        self.cared: Callable[[], Mapping[str, int]] = dict
        self.tally = {}

    def rounds(self, ahead: bool) -> int:
        # Ordered ahead: its answer, the critic's claims, tonight's pairs;
        # else the critic's claims, or the judge's pairs and then theirs;
        # and the second opinions with their claims.
        return 5 if ahead else 4

    # -- state -----------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        return dict(self.library.get_state(STATE_KEY, {}) or {})

    def _save(self, state: dict[str, Any]) -> None:
        judged = state.get("judged") or {}
        if len(judged) > JUDGED_MAX:
            state["judged"] = dict(list(judged.items())[-JUDGED_MAX:])
        self.library.set_state(STATE_KEY, state)

    # -- ordering ----------------------------------------------------------------

    def _pairs(self, state: dict[str, Any]) -> list[tuple[str, Item, Item, str]]:
        """What to ask next: the claims waiting for the critic, else the
        pairs waiting for the second opinion (claim "", in ``second``),
        else the suspects not judged yet (``(key, a, b, claim)``)."""
        claims: dict[str, str] = state.get("claims") or {}
        second: dict[str, Any] = state.get("second") or {}
        limit = PAIRS_A_NIGHT
        if claims:
            wanted = list(claims.items())
        elif second:
            wanted = [(k, "") for k in second]
            limit = SECOND_A_NIGHT
        else:
            judged = state.get("judged") or {}
            wanted = [(k, "") for k in self.twins.suspects() if k not in judged]
            # Pairs of Favourites, playlists and Discover first (2026-11-11).
            cared = self.cared()
            wanted.sort(key=lambda kc: min(cared.get(i, 2) for i in kc[0].split("|")))
        grouped = self.library.works()
        found: list[tuple[str, Item, Item, str]] = []
        gone: list[str] = []
        for key, claim in wanted:
            if len(found) >= limit:
                break
            a_id, _, b_id = key.partition("|")
            a, b = self.library.get(a_id), self.library.get(b_id)
            if (
                a is None
                or b is None
                or _settled(a, b, grouped)
                or against(a, Place.COMPARED)
                or against(b, Place.COMPARED)
            ):
                # Gone, told apart meanwhile, or one of them set aside since
                # (the gatekeeper's "no artwork"): nothing to ask about.
                gone.append(key)
                continue
            found.append((key, a, b, claim))
        if gone:
            self._forget(gone)
        return found

    def _forget(self, keys: list[str]) -> None:
        """Pairs gone or settled meanwhile: neither suspects nor claims."""
        self.twins.drop_suspects(keys)
        state = self.state()
        claims = state.get("claims") or {}
        second = state.get("second") or {}
        by = state.get("claim_models") or {}
        for key in keys:
            claims.pop(key, None)
            second.pop(key, None)
            by.pop(key, None)
        state["claims"] = claims
        state["second"] = second
        state["claim_models"] = by
        self._save(state)

    def _again(self, state: dict[str, Any]) -> dict[str, Any]:
        """Once (:data:`SECOND_AGAIN`): the pairs Haiku kept apart before
        there was a second opinion, hashed near, waiting for it."""
        if int(state.get("second_again") or 0) >= SECOND_AGAIN:
            return state
        second = dict(state.get("second") or {})
        for key, said in (state.get("judged") or {}).items():
            if (
                isinstance(said, dict)
                and said.get("judge") in SECOND_FOR
                and "second" not in said
                and self._near(key)
            ):
                second[key] = said.get("judge")
        state["second"] = second
        state["second_again"] = SECOND_AGAIN
        self._save(state)
        if second:
            log.info("twins judge: %d pairs kept apart before asked again", len(second))
        return state

    def _near(self, key: str) -> bool:
        """Whether the pair's thumbnails are hashed near (one picture, by
        their hashes: :data:`library.twins.HASH_NEAR`)."""
        a_id, _, b_id = key.partition("|")
        a, b = self.library.get(a_id), self.library.get(b_id)
        if a is None or b is None:
            return False
        hashes = (a.picture_hash, b.picture_hash)
        if not all(hashes) or NO_HASH in hashes:
            return False
        return hash_distance(*hashes) <= HASH_NEAR

    def order(self) -> bool:
        """The next pairs (the critic's first) asked of the Batch API, unless
        a batch is under way or nothing is waiting. Whether one was sent."""
        if not self.config.enabled("twins_judge") or self.asked_only("tidy"):
            return False
        state = self.state()
        if state.get("order"):
            return False
        state = self._again(state)
        pairs = self._pairs(state)
        if not pairs:
            return False
        critic = bool(pairs[0][3])
        second = not critic and pairs[0][0] in (state.get("second") or {})
        by: dict[str, str] = state.get("claim_models") or {}
        requests: list[dict[str, Any]] = []
        keys: dict[str, str] = {}
        models: dict[str, str] = {}
        broken: list[str] = []
        for n, (key, a, b, claim) in enumerate(pairs):
            if critic:
                model = SECOND if by.get(key) == SECOND else CRITIC_MODEL
            else:
                model = SECOND if second else JUDGE
            try:
                question = params(self.images, a, b, model, "low", claim)
            except Exception as err:  # a thumbnail gone, refused: no opinion
                log.info("twins judge: %s not asked (%s)", key, err)
                broken.append(key)
                continue
            custom = f"p{n}"
            requests.append({"custom_id": custom, "params": question})
            keys[custom] = key
            models[custom] = model
        if broken:
            self._forget(broken)
        if not requests:
            return False
        batch = self.send(requests)
        if batch is None:
            return False
        state = self.state()
        state["order"] = {
            "batch": batch,
            "critic": critic,
            "second": second,
            "pairs": keys,
            "models": models,
        }
        self._save(state)
        log.info(
            "twins judge: %d pairs ordered for the %s (batch %s)",
            len(keys),
            "critic" if critic else "second opinion" if second else "judge",
            batch,
        )
        return True

    # -- answers -----------------------------------------------------------------

    def collect(self) -> bool | None:
        """The batch's answers put in once it is done: True when they were,
        False while it runs, None without one."""
        state = self.state()
        order = state.get("order")
        if not order:
            return None
        results = self.answers(order["batch"])
        if results is None:
            return False
        critic = bool(order.get("critic"))
        second_round = bool(order.get("second"))
        models: dict[str, str] = order.get("models") or {}
        claims: dict[str, str] = dict(state.get("claims") or {})
        #: Waiting for the second opinion; the model of each claim.
        second: dict[str, Any] = dict(state.get("second") or {})
        by: dict[str, str] = dict(state.get("claim_models") or {})
        #: What the judge said of each claim, for the owner's list.
        reasons: dict[str, str] = dict(state.get("reasons") or {})
        judged: dict[str, Any] = dict(state.get("judged") or {})
        done: list[str] = []
        counts = {"kept": 0, "claims": 0, "second": 0, "written": 0, "rejected": 0}
        at = datetime.now(UTC).date().isoformat()
        for custom, message in results:
            key = order["pairs"].get(custom)
            if key is None or message is None:
                continue  # failed: asked again another night
            model = models.get(custom) or (CRITIC_MODEL if critic else JUDGE)
            answer = self.claude.answer(KIND, model, message, batch=True)
            claim = claims.get(key, "") if critic else ""
            found, _, why = read(answer.data, claim)
            if not found:
                continue
            a_id, _, b_id = key.partition("|")
            if not critic:
                first = second.pop(key, None) if second_round else None
                if found in CLAIMS:
                    claims[key] = found
                    reasons[key] = str(why or "")[:400]
                    if second_round:
                        by[key] = SECOND
                    counts["claims"] += 1
                elif not second_round and found in SECOND_FOR and self._near(key):
                    second[key] = found  # one picture by their hashes: Sonnet asked
                    done.append(key)  # no suspect any more: waits in ``second``
                    counts["second"] += 1
                else:
                    judged[key] = {"judge": first or found, "at": at}
                    if second_round:
                        judged[key]["second"] = found
                    done.append(key)
                    counts["kept"] += 1
                continue
            by.pop(key, None)
            claims.pop(key, None)
            said = {"why": reasons.pop(key, ""), "critic": str(why or "")[:400]}
            written = found == "confirm" and self.twins.apply(a_id, b_id, claim, said)
            judged[key] = {"judge": claim, "critic": found, "written": written, "at": at}
            if found == "reject":
                log.info("twins judge: %s %s rejected: %s", key, claim, why)
            done.append(key)
            counts["written" if written else "rejected"] += 1
        self.count(counts)
        state = self.state()
        state.pop("order", None)
        state["claims"] = claims
        state["second"] = second
        state["claim_models"] = {k: v for k, v in by.items() if k in claims}
        state["reasons"] = {k: v for k, v in reasons.items() if k in claims}
        state["judged"] = judged
        self._save(state)
        self.twins.drop_suspects(done)
        log.info(
            "twins judge (%s): %d kept apart, %d claims for the critic, %d for a second "
            "opinion, %d written, %d rejected",
            "critic" if critic else "second opinion" if second_round else "judge",
            counts["kept"],
            counts["claims"],
            counts["second"],
            counts["written"],
            counts["rejected"],
        )
        return True


def _settled(a: Item, b: Item, grouped: Any) -> bool:
    """Whether the pictures were told apart meanwhile: one work, or one a
    part or a photograph of the other."""
    at = grouped.group_index(a.id)
    if at is not None and at == grouped.group_index(b.id):
        return True
    roots = {a.id, b.id, a.copy_of, b.copy_of} - {"", None}
    return bool((a.detail_of or a.scene_of) in roots or (b.detail_of or b.scene_of) in roots)
