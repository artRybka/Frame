"""Szukaj by how a work looks (frame_server.looks, Mateusz 2026-11-13,
"G1"): the works as SigLIP's numbers, kept on the server; words, a
photograph or a work asked about them. Google's numbers answered until
2026-11-23."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_seen import FakeModel as SeenFake

from frame_server import seen as seen_module
from frame_server.ai import AiConfigUpdate, AiUnavailable
from frame_server.library.models import Item, ItemKind, PlaylistRules
from frame_server.library.viewer import OWNER_ID
from frame_server.looks import SIZE, LookIndex, Looks
from frame_server.service import FrameService

#: Colours the fake model tells apart, each its own direction.
COLOURS = {"red": (200, 30, 30), "blue": (30, 40, 200), "green": (30, 170, 40)}


def _direction(at: int, lean: int | None = None) -> list[float]:
    vector = [0.0] * SIZE
    vector[at] = 1.0
    if lean is not None:
        vector[lean] = 0.25
    return vector


class FakeModel(SeenFake):
    """SigLIP: a picture points the way of its colour, words the way of the
    colour they name (nowhere near any picture when they name none)."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.words_asked: list[str] = []

    def words(self, texts: Any) -> np.ndarray:
        self.words_asked += list(texts)
        rows = []
        for text in texts:
            at = next((n for n, name in enumerate(("red", "green", "blue")) if name in text), 7)
            rows.append(self._way(at))
        return np.stack(rows)


def _work(
    service: FrameService, item_id: str, colour: str, tall: bool = False, **fields: Any
) -> Item:
    source, _, source_id = item_id.partition(":")
    fields.setdefault("kind", ItemKind.ARTWORK)
    fields.setdefault("title", item_id)
    excluded = fields.pop("excluded", False)
    item = Item(
        id=item_id,
        source=source,
        source_id=source_id,
        thumb_url=f"https://example.org/{source_id}.jpg",
        **fields,
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (48, 64) if tall else (64, 48), COLOURS[colour]).save(path, "JPEG")
    stored = service.library.upsert(item)
    if excluded:  # hidden by the owner (each person hides their own)
        stored = service.library.set_hidden(OWNER_ID, item_id, True) or stored
    return stored


def _numbers(found: Looks) -> int:
    """The works numbered by SigLIP, its layers taught, and it answering:
    how many got numbers."""
    done = found.seen.number(1000)
    found.seen.teach(force=True)
    found.seen.settle()
    return done


@pytest.fixture
def looks(
    service: FrameService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Looks, FakeModel]:
    monkeypatch.setattr(seen_module, "LEAST_SUBJECT", 1)
    monkeypatch.setattr(seen_module, "FLOORS_SET", True)
    model = FakeModel(tmp_path / "model")
    service.seen.model = model
    return service.looks, model


def test_the_numbers_are_kept_and_the_nearest_found(tmp_path: Path) -> None:
    index = LookIndex(tmp_path)
    index.add([("a", 1, _direction(0)), ("b", 1, _direction(1)), ("c", 1, _direction(0, 1))])
    assert [i for i, _ in index.nearest(_direction(0), 2)] == ["a", "c"]
    again = LookIndex(tmp_path)  # read back from the disk
    assert len(again) == 3 and again.stamp("c") == 1
    assert [i for i, _ in again.nearest(_direction(1), 1)] == ["b"]


def test_a_new_picture_and_a_gone_work_leave_their_old_rows(tmp_path: Path) -> None:
    index = LookIndex(tmp_path)
    index.add([(f"w{n}", 1, _direction(n)) for n in range(10)])
    index.add([("w0", 2, _direction(5))])  # its picture changed
    assert index.stamp("w0") == 2
    assert [i for i, _ in index.nearest(_direction(5), 2)] == ["w5", "w0"]
    index.forget(["w1", "w2"])  # dead rows past the share: written anew
    assert len(index) == 8
    again = LookIndex(tmp_path)
    assert len(again) == 8 and "w1" not in again
    assert (tmp_path / "ids.txt").read_text().count("\n") == 8


def test_a_broken_off_write_keeps_the_whole_rows(tmp_path: Path) -> None:
    index = LookIndex(tmp_path)
    index.add([("a", 1, _direction(0)), ("b", 1, _direction(1))])
    with (tmp_path / "vectors.i8").open("ab") as out:
        out.write(b"\x01\x02\x03")
    assert len(LookIndex(tmp_path)) == 2


def test_haiku_makes_searches_of_a_look_once(service: FrameService, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from types import SimpleNamespace

    from frame_server.ai import look_words

    words = service.look_words
    assert words.searches("mglisty poranek") == []  # no key
    service.ai_config.set_key("sk-ant-test")
    asked: list[dict[str, Any]] = []

    def ask(kind: str, params: dict[str, Any]) -> SimpleNamespace:
        asked.append(params)
        data = {
            "searches": [
                {"polish": "mgła rzeka", "english": "fog river", "french": "brume rivière"},
                {"polish": "", "english": "misty morning", "french": "matin brumeux"},
                {"polish": "mgła", "english": "Fog river", "french": ""},  # the same again
                {"polish": "jezioro", "english": "lake mist", "french": ""},
                {"polish": "x", "english": "one too many", "french": ""},
            ]
        }
        return SimpleNamespace(data=data)

    monkeypatch.setattr(service.claude, "ask", ask)
    found = words.searches("Mglisty  poranek")
    assert [(w.text, w.en) for w in found] == [
        ("mgła rzeka", "fog river"),
        ("misty morning", "misty morning"),
        ("jezioro", "lake mist"),
    ]
    assert len(found) == look_words.MOST
    assert words.searches("mglisty poranek") == found and len(asked) == 1
    assert asked[0]["model"] == look_words.HAIKU
    # With the translation of Szukaj's words switched off, nothing is asked.
    service.ai_config.update(AiConfigUpdate(search_words=False))
    assert words.searches("rwący potok") == [] and len(asked) == 1


def test_words_find_works_that_look_so(
    service: FrameService, looks: tuple[Looks, FakeModel]
) -> None:
    found, model = looks
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _work(service, "met:3", "red", excluded=True)  # hidden in the app
    _numbers(found)
    asked = len(model.words_asked)
    assert [f.item.id for f in found.words("czerwony red zachód")] == ["met:1"]
    assert [f.item.id for f in found.words("  Czerwony   red zachód ")] == ["met:1"]
    assert len(model.words_asked) == asked + 1  # the same words are not made again
    assert found.words("nic") == []  # far from every work


def test_a_photograph_and_a_work_find_works_that_look_alike(
    service: FrameService, looks: tuple[Looks, FakeModel]
) -> None:
    found, _model = looks
    red = _work(service, "met:1", "red")
    _work(service, "aic:7", "red")
    _work(service, "met:2", "blue")
    _numbers(found)
    photo = Image.new("RGB", (300, 200), COLOURS["blue"])
    assert [f.item.id for f in found.picture(photo)] == ["met:2"]
    assert [f.item.id for f in found.similar(red)] == ["aic:7"]
    assert found.neighbours("met:1") == ["aic:7"]
    assert found.similar(Item(id="met:9", source="met", source_id="9")) == []


def test_works_that_look_alike_come_first_among_the_studys_candidates(
    service: FrameService, looks: tuple[Looks, FakeModel]
) -> None:
    found, _model = looks
    red = _work(service, "met:1", "red", artist="Anna A")
    _work(service, "aic:7", "red", artist="Bruno B")
    _work(service, "aic:8", "red", artist="Anna A")  # the artist's own: "Inne prace artysty"
    _numbers(found)
    assert [i.id for i in service.daily.candidates(red)] == ["aic:7"]


def test_szukaj_narrows_the_look_by_its_other_choices(
    service: FrameService, looks: tuple[Looks, FakeModel]
) -> None:
    """Mateusz 2026-11-13: the works found by how they look in Szukaj's own
    list, the groups (an artist, a technique, colours) narrowing them."""
    from frame_server.web import create_app

    found, _model = looks
    _work(service, "met:1", "red", artist="Anna A")
    _work(service, "met:2", "red", artist="Bruno B")
    _work(service, "met:3", "blue", artist="Anna A")
    _work(service, "met:4", "red", artist="Anna A", excluded=True)  # hidden
    _work(service, "met:5", "red", artist="Anna A", kind=ItemKind.PHOTO)  # never sent
    _numbers(found)
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:

        def ids(**params: Any) -> list[str]:
            page = client.get("/api/library/items", params=params).json()
            assert page["total"] >= len(page["items"])
            return [i["id"] for i in page["items"]]

        assert sorted(ids(look="czerwony red")) == ["met:1", "met:2"]
        assert ids(look="czerwony red", artist="Anna A") == ["met:1"]
        assert ids(look="niebieski blue", artist="Anna A") == ["met:3"]
        assert ids(look="niebieski blue", artist="Bruno B") == []
        assert ids(look="nic") == []  # far from every work
        page = client.get("/api/library/items", params={"look": "red", "limit": 1}).json()
        assert page["total"] == 2 and len(page["items"]) == 1
        assert len(ids()) == 4  # without words for a look: as it was
        (found.seen.root / seen_module.ANSWERS).unlink()
        found.seen._answers = False  # SigLIP not answering (yet)
        assert client.get("/api/library/items", params={"look": "red"}).status_code == 409


def test_a_photograph_is_searched_in_szukajs_own_list(
    service: FrameService, looks: tuple[Looks, FakeModel]
) -> None:
    """„Szukaj zdjęciem” as „Szukaj podobnych” (Mateusz 2026-11-15): the
    photograph's numbers kept under a key Szukaj asks as ``like``, the
    groups narrowing it, a smart playlist keeping it; the same photograph
    again asks Google nothing, and the photograph itself is not kept."""
    from frame_server.web import create_app

    found, _model = looks
    _work(service, "met:1", "red", artist="Anna A")
    _work(service, "aic:7", "red", artist="Bruno B")
    _work(service, "met:2", "blue", artist="Anna A")
    _numbers(found)
    app = create_app(service.settings)
    app.state.service = service
    out = io.BytesIO()
    Image.new("RGB", (40, 30), COLOURS["red"]).save(out, "JPEG")
    files = {"file": ("photo.jpg", out.getvalue(), "image/jpeg")}
    with TestClient(app) as client:
        key = client.post("/api/looks/photo", files=files).json()["key"]
        assert key.startswith("photo:")
        assert client.post("/api/looks/photo", files=files).json()["key"] == key

        def ids(**params: Any) -> list[str]:
            page = client.get("/api/library/items", params=params).json()
            return [i["id"] for i in page["items"]]

        # A photograph's nearest, no floor (Mateusz 2026-11-22): the reds first.
        assert sorted(ids(like=key)[:2]) == ["aic:7", "met:1"]
        assert ids(like=key, artist="Anna A")[0] == "met:1"
        assert ids(like="photo:0000") == []  # a key nobody kept
        bad = {"file": ("photo.jpg", b"not a picture", "image/jpeg")}
        assert client.post("/api/looks/photo", files=bad).status_code == 422
    kept = sorted((found.root / "photos").iterdir())
    # Numbers only, and its colours ("Barwy"): never the photograph.
    assert [p.suffixes[-2] for p in kept] == [".palette", ".seen"]
    assert kept[1].stat().st_size == SIZE * 4 and kept[0].stat().st_size <= 4 * 8 * 4
    rules = PlaylistRules(like=key)
    assert sorted(i.id for i in service.library.query(rules)[1][:2]) == ["aic:7", "met:1"]
    assert rules.search_key() == ""  # no museum asked


def test_a_look_puts_only_the_works_near_it_through_the_other_rules(
    service: FrameService, looks: tuple[Looks, FakeModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole catalogue put through the rules for a look's words stood
    the server still for minutes (115 000 works, 2026-11-13): only those
    the look may choose from are."""
    from frame_server import looks as looks_module
    from frame_server.library import repo
    from frame_server.library.models import PlaylistRules

    found, _model = looks
    for n, colour in enumerate(["red", "red", "blue", "green", "blue", "green"], start=1):
        _work(service, f"met:{n}", colour)
    _numbers(found)
    monkeypatch.setattr(looks_module, "AMONG_NEAR", 2)
    seen: set[str] = set()
    plain = repo.matches

    def spy(item: Item, *args: Any, **kwargs: Any) -> bool:
        seen.add(item.id)
        return plain(item, *args, **kwargs)

    monkeypatch.setattr(repo, "matches", spy)
    total, items = service.library.query(PlaylistRules(look="czerwony red"))
    assert sorted(i.id for i in items) == ["met:1", "met:2"] and total == 2
    assert seen == {"met:1", "met:2"}


def test_the_museums_are_asked_a_looks_searches_and_judged_by_it(
    service: FrameService, looks: tuple[Looks, FakeModel]
) -> None:
    """Mateusz 2026-11-13 (card, "Hasła i ocena wyglądem"): Haiku's searches
    for the look, in each museum's language; what they bring judged by its
    thumbnail, the numbers kept."""
    from frame_server.library.search import MuseumSearch
    from frame_server.library.wording import Wording

    found, _model = looks
    _work(service, "met:1", "red")  # the catalogue's best for red
    _numbers(found)
    museum = []
    for n, colour in enumerate(["red", "blue", "red"], start=10):
        item = Item(
            id=f"cma:{n}",
            source="cma",
            source_id=str(n),
            title=f"Work {n}",
            thumb_url=f"https://example.org/{n}.jpg",
            kind=ItemKind.ARTWORK,
        )
        path = service.images.thumb_path(item)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 48), COLOURS[colour]).save(path, "JPEG")
        museum.append(item)

    asked: list[dict[str, str]] = []
    spare: list[str] = []

    class Museums:
        look_searches = staticmethod(
            lambda text: [
                Wording("czerwień", "red sky", "ciel rouge"),
                Wording("zachód", "sunset", ""),
            ]
        )
        judge_look = staticmethod(found.judge)

        def asked_sources(self, kind: str = "any") -> list[str]:
            return ["cma", "mnw"]

        def search_all(self, texts, limit, page, keys, kind="any"):  # type: ignore[no-untyped-def]
            asked.append(dict(texts))
            brought = museum if page == 1 and texts["cma"] == "red sky" else []
            return (len(brought), brought, [])

        def in_colors(self, items, colors):  # type: ignore[no-untyped-def]
            return items

        def measure(self, items) -> None:  # type: ignore[no-untyped-def]
            return None

    search = MuseumSearch.of(PlaylistRules(look="czerwony red zachód"), keys=["cma", "mnw"])
    assert not search.empty
    pages = list(
        search.pages(Museums(), ["cma", "mnw"], 1, lambda items: spare.extend(i.id for i in items))
    )  # type: ignore[arg-type]
    assert asked[0] == {"cma": "red sky", "mnw": "czerwień"}  # Polish museums in Polish
    assert asked[1] == {"cma": "sunset", "mnw": "zachód"}
    shown = [i.id for _, items, _, _ in pages for i in items]
    assert shown == ["cma:10", "cma:12"]  # the blue one does not look red
    assert "cma:11" in spare  # asked for already: into the catalogue
    assert {"cma:10", "cma:11", "cma:12"} <= found.seen.index.ids()  # numbers kept


def test_a_copy_without_numbers_shows_what_its_works_other_copy_looks_like(
    service: FrameService, looks: tuple[Looks, FakeModel]
) -> None:
    """Van Gogh's Sunflowers found by a look had no "Podobne wyglądem": the
    card showed the work's best copy, the index had another (2026-11-13)."""
    found, _model = looks
    _work(service, "met:1", "red", artist="Vincent van Gogh")
    _work(service, "aic:7", "red")
    _numbers(found)
    copy = service.library.upsert(
        Item(id="wmc:5", source="wmc", source_id="5", title="met:1", artist="Vincent van Gogh")
    )
    works = service.library.works()
    assert works.group_index("wmc:5") == works.group_index("met:1") is not None
    assert copy.id not in found.seen.index
    assert [f.item.id for f in found.similar(copy)] == ["aic:7"]


def _slowa(service: FrameService, looks: tuple[Looks, FakeModel]) -> Looks:
    """Works for "red": one with the word and the look, one with the look
    alone, one with the word alone (it is blue)."""
    found, _model = looks
    _work(service, "met:1", "red", title="A red barn")
    _work(service, "met:2", "red", title="Barn at dusk")
    _work(service, "met:3", "blue", title="The red letter")
    _work(service, "met:4", "green", title="Meadow")
    _numbers(found)
    return found


def test_slowa_find_works_by_their_words_and_by_how_they_look(
    service: FrameService, looks: tuple[Looks, FakeModel]
) -> None:
    """Mateusz 2026-11-19: "Słowa, słowa kluczowe, hasła i słowa o tym co
    widać - może połączyć w jedno?": the works with the words, and those
    that look so, nearest first; those with the words only after them."""
    _slowa(service, looks)
    words = PlaylistRules(query="red")
    assert sorted(i.id for i in service.library.query(words)[1]) == ["met:1", "met:3"]
    seen = PlaylistRules(query="red", seen=True)
    total, items = service.library.query(seen)
    assert [i.id for i in items][:2] in (["met:1", "met:2"], ["met:2", "met:1"])
    assert [i.id for i in items][2:] == ["met:3"] and total == 3
    # Another order asked: as the words found them, those by look after.
    by_year = [i.id for i in service.library.query(seen, sort="year")[1]]
    assert sorted(by_year[:2]) == ["met:1", "met:3"] and by_year[2:] == ["met:2"]


def test_slowa_finding_plenty_by_words_only_order_them(
    service: FrameService, looks: tuple[Looks, FakeModel], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Words that find many works alone ("Kraków", "akwaforta") get none
    only by how they look: theirs go nearest first."""
    from frame_server.library import repo

    _slowa(service, looks)
    monkeypatch.setattr(repo, "SEEN_PLENTY", 2)
    items = service.library.query(PlaylistRules(query="red", seen=True))[1]
    assert [i.id for i in items] == ["met:1", "met:3"]


def test_nothing_is_answered_until_siglip_answers(
    service: FrameService, looks: tuple[Looks, FakeModel]
) -> None:
    found, _model = looks
    _work(service, "met:1", "red")
    assert not found.enabled() and not found.ready()
    with pytest.raises(AiUnavailable):
        found.words("czerwony red")
    _numbers(found)
    assert found.enabled() and found.ready()
    assert [f.item.id for f in found.words("red")] == ["met:1"]


def test_the_api(service: FrameService, looks: tuple[Looks, FakeModel]) -> None:
    from frame_server.web import create_app

    found, _model = looks
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _numbers(found)
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        status = client.get("/api/looks").json()
        assert status == {"enabled": True, "ready": True, "done": 2, "total": 2}
        words = client.get("/api/looks/search", params={"q": "niebieski blue"}).json()
        assert [i["id"] for i in words["items"]] == ["met:2"]
        out = io.BytesIO()
        Image.new("RGB", (40, 30), COLOURS["red"]).save(out, "JPEG")
        files = {"file": ("photo.jpg", out.getvalue(), "image/jpeg")}
        photo = client.post("/api/looks/picture", files=files).json()
        assert [i["id"] for i in photo["items"]] == ["met:1"]
        bad = {"file": ("photo.jpg", b"not a picture", "image/jpeg")}
        assert client.post("/api/looks/picture", files=bad).status_code == 422
        view = client.get("/api/ai").json()
        # No switch of its own, nor Google's trouble: the count alone.
        assert "looks" not in view and "looks_error" not in view
        assert view["looks_done"] == 2 and view["looks_total"] == 2
        # An older app's switch changes nothing.
        assert client.put("/api/ai", json={"looks": False}).status_code == 200
        assert client.get("/api/looks/search", params={"q": "red"}).status_code == 200
