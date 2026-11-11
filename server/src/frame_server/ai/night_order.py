"""The night's loop for what is ordered of the Batch API.

The judge of copies, the questions checked by a critic (the gatekeeper, the
review) and the curator each had this loop of their own (the audit of
2026-11-11: four copies of it): an order sent unless the model is off or
over its limit, the batch read once it ended, and the night waiting for it
while it is quiet. The fourth, the notes asked at night (``AiJobs``), is the
background's: its batches are put in by its own poll, whenever they end.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from .client import AiUnavailable

if TYPE_CHECKING:
    from ..night import Night
    from .client import Claude

log = logging.getLogger(__name__)

#: How long the night waits for a batch, and how often it asks: a quarter
#: of an hour (a later answer is collected the next night); an hour each
#: left the tasks after them no time (2026-11-11).
WAIT_SECONDS = 900.0
POLL_SECONDS = 60.0


class NightOrder(ABC):
    """Something ordered of the Batch API at night, put in when it is done."""

    #: Its name in the log.
    name: str
    claude: Claude
    wait_seconds: float = WAIT_SECONDS
    poll_seconds: float = POLL_SECONDS

    @abstractmethod
    def collect(self) -> bool | None:
        """The batch's answers put in once it is done: True when they were,
        False while it runs, None without one."""

    def send(self, requests: list[dict[str, Any]]) -> str | None:
        """``requests`` as one batch: its id, None when it could not go."""
        try:
            return self.claude.create_batch(requests)
        except AiUnavailable as err:
            log.info("%s: not asked (%s)", self.name, err)
        except Exception:
            log.exception("%s: the order failed", self.name)
        return None

    def answers(self, batch: str) -> list[tuple[str, Any]] | None:
        """The answers of ``batch`` once it ended (a failed question's is
        None); None while it runs, or when it could not be read."""
        try:
            ended, _ = self.claude.batch_ended(batch)
            if not ended:
                return None
            return list(self.claude.batch_results(batch))
        except Exception:
            log.exception("%s: the batch could not be read", self.name)
            return None

    def waited(self, night: Night) -> bool:
        """Waits for the batch under way while the night is quiet,
        :attr:`wait_seconds` at most; whether its answers were put in."""
        waited = 0.0
        while True:
            if waited >= self.wait_seconds or not night.quiet():
                return False
            if not night.sleep(self.poll_seconds):
                return False
            waited += self.poll_seconds
            if self.collect() is not False:
                return True


class CheckedNight(NightOrder):
    """A judge's answers checked by a critic, round after round: the
    critic's claims first, then the judge's new questions, then their
    claims."""

    #: The answers put in since :meth:`at_night` began, by outcome
    #: ("written", "rejected", …), for the night's summary.
    tally: dict[str, int]
    #: A batch was ordered ahead of this night's work (:meth:`ahead`).
    _ahead: bool = False

    @abstractmethod
    def order(self) -> bool:
        """The next round asked of the Batch API, unless one is under way or
        nothing waits. Whether one was sent."""

    def rounds(self, ahead: bool) -> int:
        """Rounds ordered in one night at most (``ahead``: one was ordered
        before the night's long work)."""
        return 3

    def count(self, counts: dict[str, int]) -> None:
        """``counts`` added to the night's (:attr:`tally`)."""
        for name, n in counts.items():
            self.tally[name] = self.tally.get(name, 0) + n

    def ahead(self) -> None:
        """Before the night's long work (the pictures looked at, 40 minutes):
        last night's batch put in and the next one ordered, to be collected
        by :meth:`at_night` once that work is done, not waited for."""
        self.tally = {}
        self._ahead = True
        if self.collect() is not False:
            self.order()

    def at_night(self, night: Night) -> None:
        """Last night's batch put in, then the rounds asked, each waited for
        while the night is quiet (a batch ordered :meth:`ahead` is waited
        for first)."""
        if not self._ahead:
            self.tally = {}
        rounds = self.rounds(self._ahead)
        self._ahead = False
        if self.collect() is False and not self.waited(night):
            return
        for _ in range(rounds):
            if not self.order():
                return
            if not self.waited(night):
                return
