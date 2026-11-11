"""A question about works asked at night, and a critic before anything is
written (Mateusz 2026-11-10: "wdrażamy K1 … K4").

What the judge of copies (``ai.twins_judge``) taught: Haiku answers well
when it says why first and then answers simple questions, and a second
Haiku with the opposite question (look for evidence against the claim)
stops the wrong decisions. So a :class:`CriticNight` asks the judge about
the works it picks, through the Batch API at half the price; every answer
that would change something is a claim, asked of the critic the next round;
only what the critic confirms is written. A claim the critic rejects
changes nothing. Each work is asked once per :attr:`version`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .client import HAIKU, AiUnavailable

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from ..night import Night
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

#: How long the night waits for a batch, and how often it asks: a quarter
#: of an hour, as the judge of copies (a later answer is collected the next
#: night); an hour each left the tasks after them no time (2026-11-11).
WAIT_SECONDS = 900.0
POLL_SECONDS = 60.0
#: The rank of a work nobody cares about (``cared``).
REST = 2
#: Works remembered as asked, the newest.
JUDGED_MAX = 60_000
#: What was written (or found), the newest, for the app's list.
WRITTEN_MAX = 500


class CriticNight(ABC):
    """The judge's question about works, its claims checked by a critic."""

    #: The spending's kind and the state's key.
    kind: str
    #: The owner's switch (:meth:`AiConfigStore.enabled`).
    switch: str
    #: Changes when the question changes: works asked before are asked again.
    version: int = 1
    #: Works asked about in one night at most.
    per_night: int = 200
    judge_model = HAIKU
    critic_model = HAIKU

    def __init__(
        self,
        library: Library,
        images: ImageCache,
        claude: Claude,
        config: AiConfigStore,
    ) -> None:
        self.library = library
        self.images = images
        self.claude = claude
        self.config = config
        #: The works cared about, by id: 0 kept, 1 shown (``cared.Cared``);
        #: their candidates go first.
        self.cared: Callable[[], Mapping[str, int]] = dict
        #: The answers put in since :meth:`at_night` began, by outcome
        #: ("written", "rejected", …), for the night's summary.
        self.tally: dict[str, int] = {}
        #: A batch was ordered ahead of this night's work (:meth:`ahead`).
        self._ahead = False

    # -- what a job says ----------------------------------------------------------

    @abstractmethod
    def candidates(self, asked: dict[str, Any]) -> list[Item]:
        """Works to ask the judge about tonight, best first (``asked``: what
        was asked before, by work)."""

    @abstractmethod
    def question(self, item: Item) -> dict[str, Any]:
        """The judge's question (``client.request``); may download the thumbnail."""

    @abstractmethod
    def claim(self, item: Item, data: dict[str, Any]) -> dict[str, Any] | None:
        """What the judge's answer would change, for the critic; None for nothing."""

    @abstractmethod
    def critic_question(self, item: Item, claim: dict[str, Any]) -> dict[str, Any]:
        """The critic's question about ``claim``."""

    @abstractmethod
    def confirmed(self, item: Item, claim: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        """The part of ``claim`` the critic's answer confirms ({} for none)."""

    @abstractmethod
    def write(self, item: Item, claim: dict[str, Any]) -> bool:
        """Writes what the critic confirmed; whether something changed."""

    # -- state ---------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        return dict(self.library.get_state(self.kind, {}) or {})

    def _save(self, state: dict[str, Any]) -> None:
        asked = state.get("asked") or {}
        if len(asked) > JUDGED_MAX:
            state["asked"] = dict(list(asked.items())[-JUDGED_MAX:])
        written = state.get("written") or []
        state["written"] = written[:WRITTEN_MAX]
        self.library.set_state(self.kind, state)

    def asked(self) -> dict[str, Any]:
        """Works asked about with this version of the question."""
        return {
            k: v
            for k, v in (self.state().get("asked") or {}).items()
            if isinstance(v, dict) and v.get("v") == self.version
        }

    def written(self) -> list[dict[str, Any]]:
        """What the critic confirmed and was written, newest first."""
        return list(self.state().get("written") or [])

    def forget_written(self, item_id: str) -> dict[str, Any] | None:
        """Takes ``item_id`` off the written list; what it said, or None."""
        state = self.state()
        written = state.get("written") or []
        found = next((w for w in written if w.get("id") == item_id), None)
        state["written"] = [w for w in written if w.get("id") != item_id]
        self._save(state)
        return found

    # -- the night -------------------------------------------------------------------

    def _round(self, state: dict[str, Any]) -> tuple[bool, list[tuple[Item, dict[str, Any]]]]:
        """The critic's claims when there are any, else the judge's works."""
        claims: dict[str, Any] = state.get("claims") or {}
        if claims:
            found = []
            for item_id, claim in list(claims.items())[: self.per_night]:
                item = self.library.get(item_id)
                if item is not None:
                    found.append((item, claim))
                else:
                    claims.pop(item_id, None)
            return True, found
        return False, [(i, {}) for i in self.candidates(self.asked())[: self.per_night]]

    def order(self) -> bool:
        """The next round (the critic's claims first) asked of the Batch API,
        unless one is under way or nothing waits. Whether one was sent."""
        if not self.config.enabled(self.switch):
            return False
        state = self.state()
        if state.get("order"):
            return False
        critic, round_ = self._round(state)
        if not round_:
            return False
        requests: list[dict[str, Any]] = []
        ids: dict[str, str] = {}
        broken: list[str] = []
        for n, (item, claim) in enumerate(round_):
            try:
                params = self.critic_question(item, claim) if critic else self.question(item)
            except Exception as err:  # a thumbnail gone: no opinion, not asked again
                log.info("%s: %s not asked (%s)", self.kind, item.id, err)
                broken.append(item.id)
                continue
            custom = f"w{n}"
            requests.append({"custom_id": custom, "params": params})
            ids[custom] = item.id
        if broken:
            state = self.state()
            asked = state.get("asked") or {}
            claims = state.get("claims") or {}
            for item_id in broken:
                asked[item_id] = {"v": self.version, "broken": True}
                claims.pop(item_id, None)
            state["asked"], state["claims"] = asked, claims
            self._save(state)
        if not requests:
            return False
        try:
            batch = self.claude.create_batch(requests)
        except AiUnavailable as err:
            log.info("%s: not asked (%s)", self.kind, err)
            return False
        except Exception:
            log.exception("%s: the order failed", self.kind)
            return False
        state = self.state()
        state["order"] = {"batch": batch, "critic": critic, "ids": ids}
        self._save(state)
        log.info(
            "%s: %d works ordered for the %s (batch %s)",
            self.kind,
            len(ids),
            "critic" if critic else "judge",
            batch,
        )
        return True

    def collect(self) -> bool | None:
        """The batch's answers put in once it is done: True when they were,
        False while it runs, None without one."""
        state = self.state()
        order = state.get("order")
        if not order:
            return None
        try:
            ended, _ = self.claude.batch_ended(order["batch"])
            if not ended:
                return False
            results = list(self.claude.batch_results(order["batch"]))
        except Exception:
            log.exception("%s: the batch could not be read", self.kind)
            return False
        critic = bool(order.get("critic"))
        model = self.critic_model if critic else self.judge_model
        state = self.state()
        claims: dict[str, Any] = dict(state.get("claims") or {})
        asked: dict[str, Any] = dict(state.get("asked") or {})
        written: list[dict[str, Any]] = list(state.get("written") or [])
        at = datetime.now(UTC).isoformat(timespec="seconds")
        counts = {"nothing": 0, "claims": 0, "written": 0, "rejected": 0}
        for custom, message in results:
            item_id = order["ids"].get(custom)
            if item_id is None or message is None:
                continue  # failed: asked again another night
            answer = self.claude.answer(self.kind, model, message, batch=True)
            item = self.library.get(item_id)
            if item is None:
                claims.pop(item_id, None)
                continue
            data = answer.data or {}
            if not critic:
                found = None if answer.refused else self.claim(item, data)
                asked[item_id] = {"v": self.version, "at": at[:10]}
                if found:
                    claims[item_id] = found
                    counts["claims"] += 1
                else:
                    counts["nothing"] += 1
                continue
            claim = claims.pop(item_id, None) or {}
            kept = {} if answer.refused else self.confirmed(item, claim, data)
            asked[item_id] = {"v": self.version, "at": at[:10], "critic": bool(kept)}
            if kept and self.write(item, kept):
                written.insert(0, {"id": item_id, "at": at, **kept})
                counts["written"] += 1
            else:
                counts["rejected"] += 1
                log.info("%s: %s rejected by the critic: %s", self.kind, item_id, data.get("why"))
        for name, n in counts.items():  # since the night began (``tally``)
            self.tally[name] = self.tally.get(name, 0) + n
        state = self.state()
        state.pop("order", None)
        state["claims"], state["asked"], state["written"] = claims, asked, written
        self._save(state)
        log.info(
            "%s (%s): %d nothing to change, %d claims for the critic, %d written, %d rejected",
            self.kind,
            "critic" if critic else "judge",
            counts["nothing"],
            counts["claims"],
            counts["written"],
            counts["rejected"],
        )
        return True

    def ahead(self) -> None:
        """Before the night's long work (the pictures looked at, 40 minutes):
        last night's batch put in and the next one ordered, to be collected
        by :meth:`at_night` once that work is done, not waited for."""
        self.tally = {}
        self._ahead = True
        if self.collect() is not False:
            self.order()

    def at_night(self, night: Night) -> None:
        """Last night's batch put in, then the critic's claims and the judge's
        works asked, each waited for while the night is quiet
        (a batch ordered :meth:`ahead` is waited for first)."""
        if not self._ahead:
            self.tally = {}
        self._ahead = False
        if self.collect() is False and not self._waited(night):
            return
        for _ in range(3):  # claims left over, the judge's works, then their claims
            if not self.order():
                return
            if not self._waited(night):
                return

    def _waited(self, night: Night) -> bool:
        """Waits for the batch under way while the night is quiet, a quarter
        of an hour at most; whether its answers were put in."""
        waited = 0.0
        while True:
            if waited >= WAIT_SECONDS or not night.quiet():
                return False
            if not night.sleep(POLL_SECONDS):
                return False
            waited += POLL_SECONDS
            if self.collect() is not False:
                return True
