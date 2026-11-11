"""The library never holds the event loop up: a long read of the disk, a
grouping being made or the language model's notes don't stop a heart being
read (2026-11-09: the whole server stood 20-44 s while Szukaj searched)."""

from __future__ import annotations

import threading
import time

from frame_server.library import Item, Library
from frame_server.library import repo as repo_module
from frame_server.library.models import Note


def _item(n: int, **kw) -> Item:
    kw.setdefault("title", f"Picture {n}")
    return Item(id=f"test:{n}", source="test", source_id=str(n), **kw)


def _hold_disk(lib: Library) -> tuple[threading.Thread, threading.Event]:
    """A thread holding the disk (as a long read of notes does) until the
    event is set."""
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with lib._db():
            held.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    assert held.wait(5)
    return holder, release


def test_hearts_and_items_are_read_while_the_disk_is_busy(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(_item(1))
    lib.set_favorite("owner", "test:1", True)
    holder, release = _hold_disk(lib)
    try:
        started = time.monotonic()
        assert lib.likes("owner", "test:1")
        assert lib.favorites("owner") == frozenset({"test:1"})
        assert "owner" in lib.fans()
        assert lib.get("test:1") is not None
        assert len(lib.works().groups) == 1
        assert time.monotonic() - started < 1
    finally:
        release.set()
        holder.join(5)


def test_hearts_change_by_replacing_their_sets(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    for n in (1, 2):
        lib.upsert(_item(n))
    before = lib.favorites("owner")
    lib.set_favorite("owner", "test:1", True)
    lib.set_favorite("owner", "test:2", True)
    lib.set_favorite("owner", "test:1", False)
    assert before == frozenset()  # a set handed out never changes
    assert lib.favorites("owner") == frozenset({"test:2"})
    assert lib.get("test:2").favorite and not lib.get("test:1").favorite
    lib.delete("test:2")
    assert lib.favorites("owner") == frozenset()
    lib.set_favorite("guest", "test:1", True)
    lib.forget_person("guest")
    assert "guest" not in lib.fans()
    assert not lib.get("test:1").favorite


def test_works_are_grouped_outside_the_lock_with_the_changes_made_meanwhile(
    tmp_path, monkeypatch
) -> None:
    lib = Library(tmp_path / "lib.db")
    for n in range(3):
        lib.upsert(_item(n, artist="A", title=f"Work {n}"))
    lib._works = None
    making, go_on = threading.Event(), threading.Event()
    real = repo_module.Works

    def slow(items):  # type: ignore[no-untyped-def]
        items = list(items)
        making.set()
        go_on.wait(5)
        return real(items)

    monkeypatch.setattr(repo_module, "Works", slow)
    found: list[object] = []
    maker = threading.Thread(target=lambda: found.append(lib.works()))
    maker.start()
    assert making.wait(5)
    # Meanwhile the library goes on: an item added, one taken out, a heart.
    started = time.monotonic()
    lib.upsert(_item(9, artist="B", title="New one"))
    lib.delete("test:0")
    lib.set_favorite("owner", "test:1", True)
    assert time.monotonic() - started < 1
    go_on.set()
    maker.join(5)
    works = found[0]
    grouped = {i.id for group in works.groups for i in group}  # type: ignore[attr-defined]
    assert grouped == {"test:1", "test:2", "test:9"}
    assert lib.works() is works


def test_a_regrouping_change_meanwhile_is_applied_to_the_grouping(tmp_path, monkeypatch) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(_item(1, artist="A", title="One"))
    lib._works = None
    making, go_on = threading.Event(), threading.Event()
    real = repo_module.Works
    calls: list[int] = []

    def slow(items):  # type: ignore[no-untyped-def]
        items = list(items)
        calls.append(len(items))
        if len(calls) == 1:
            making.set()
            go_on.wait(5)
        return real(items)

    monkeypatch.setattr(repo_module, "Works", slow)
    found: list[object] = []
    maker = threading.Thread(target=lambda: found.append(lib.works()))
    maker.start()
    assert making.wait(5)
    lib.upsert(_item(1, artist="A", title="Another title"))  # regroups
    go_on.set()
    maker.join(5)
    assert len(calls) == 1  # not made again: the one work grouped anew
    titles = [i.title for group in found[0].groups for i in group]  # type: ignore[attr-defined]
    assert titles == ["Another title"]


def test_notes_are_kept_in_memory_and_follow_changes(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(_item(1))
    lib.upsert(_item(2))
    note = Note(item_id="test:1", kind="keywords", model="m", prompt_version="1", data={"a": 1})
    lib.save_note(note)
    assert set(lib.notes("keywords")) == {"test:1"}
    lib.save_note(note.model_copy(update={"item_id": "test:2"}))
    first = lib.notes("keywords")
    assert set(first) == {"test:1", "test:2"}
    first.pop("test:1")  # a copy: the kept notes stay
    holder, release = _hold_disk(lib)
    try:
        started = time.monotonic()
        assert set(lib.notes("keywords")) == {"test:1", "test:2"}
        assert time.monotonic() - started < 1  # from memory, not the disk
    finally:
        release.set()
        holder.join(5)
    lib.delete_notes("keywords", "test:2")
    assert set(lib.notes("keywords")) == {"test:1"}
    lib.delete("test:1")
    assert lib.notes("keywords") == {}
    assert Library(tmp_path / "lib.db").notes("keywords") == {}
