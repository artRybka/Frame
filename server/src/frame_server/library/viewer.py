"""Who is looking: the person whose request is being answered.

Each person has hearts of their own (``Library.favorites``). ``Item.favorite``
as stored means "someone's favourite" (what keeps a work from being trimmed);
in an answer to the app it means "mine": the viewer set for the request
decides it when the item is serialised (see ``Item._favorite_for_viewer``).
Background work has no viewer and sees the stored flag."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

#: The owner's id: the server's own token, and everything from before there
#: were people on the server.
OWNER_ID = "owner"


@dataclass(frozen=True)
class Viewer:
    user_id: str
    likes: Callable[[str], bool]


VIEWER: ContextVar[Viewer | None] = ContextVar("viewer", default=None)

#: Serialisation context for writing items to the database: the stored flag,
#: whoever's request it is.
STORE = {"store": True}


@contextmanager
def viewing(viewer: Viewer | None) -> Iterator[None]:
    token = VIEWER.set(viewer)
    try:
        yield
    finally:
        VIEWER.reset(token)


def viewer_id() -> str:
    """The person asking, or the owner when nobody is (background work)."""
    viewer = VIEWER.get()
    return viewer.user_id if viewer is not None else OWNER_ID
