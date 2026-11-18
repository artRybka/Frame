"""Szukaj by how a work looks (frame_server.looks, Mateusz 2026-11-13,
"G1"): the museums' works as Google's numbers, kept on the server; words,
a photograph or a work asked about them."""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.ai import AiConfigUpdate, AiUnavailable
from frame_server.ai.gemini import (
    EMBED_MAX,
    EMBED_MODEL,
    EMBED_SIZE,
    Embedded,
    NotDrawn,
    Painter,
    embed_cost,
)
from frame_server.library.models import Item, ItemKind, PlaylistRules
from frame_server.looks import DESCRIBE, KIND, PART, QUERY, TOLD, LookIndex, Looks
from frame_server.service import FrameService

#: Colours the fake model tells apart, each its own direction.
COLOURS = {"red": (200, 30, 30), "blue": (30, 40, 200), "green": (30, 170, 40)}


def _direction(at: int, lean: int | None = None) -> list[float]:
    vector = [0.0] * EMBED_SIZE
    vector[at] = 1.0
    if lean is not None:
        vector[lean] = 0.25
    return vector


def _colour_of(img: Image.Image) -> int:
    r, g, b = img.convert("RGB").resize((1, 1)).getpixel((0, 0))  # type: ignore[misc]
    return int(np.argmax([r, b, g]))  # red 0, blue 1, green 2


class FakePainter:
    """Google's models: a picture's subject points the way of its colour,
    its style the way of its shape (wide or tall), words the way of the
    colour they name; Gemini's sentence on a picture names its colour."""

    def __init__(self) -> None:
        self.asked: list[list[Embedded]] = []
        self.batches: list[list[tuple[str, Embedded]]] = []
        self.tellings: list[list[tuple[str, Image.Image]]] = []
        self.told: list[Image.Image] = []
        #: Batches Google is still at.
        self.waiting: set[str] = set()
        self.key = True

    def enabled(self) -> bool:
        return self.key

    @staticmethod
    def point(one: Embedded) -> list[float]:
        if isinstance(one, str):
            words = one.removeprefix(QUERY).removeprefix(TOLD)
            assert words != one
            at = next((n for n, name in enumerate(COLOURS) if name in words), 5)
            return _direction(at)
        if isinstance(one, tuple):
            ask, img = one
            if ask.startswith("Represent only the artistic style"):
                return _direction(20 + (img.width < img.height))
            return _direction(_colour_of(img), lean=10)
        return _direction(_colour_of(one), lean=10)

    def embed_batch(self, kind: str, pictures: Sequence[tuple[str, Embedded]]) -> str:
        assert kind == KIND and pictures
        self.batches.append(list(pictures))
        return f"batches/{len(self.batches)}"

    def embed_batched(self, kind: str, batch: str) -> dict[str, list[float] | None] | None:
        if batch in self.waiting:
            return None
        pictures = self.batches[int(batch.split("/")[1]) - 1]
        return {name: self.point(one) for name, one in pictures}

    def embed(self, kind: str, inputs: Sequence[Embedded]) -> list[list[float]]:
        assert kind == KIND and 0 < len(inputs) <= EMBED_MAX
        self.asked.append(list(inputs))
        return [self.point(one) for one in inputs]

    def describe(self, kind: str, prompt: str, img: Image.Image, longest: int = 160) -> str:
        assert kind == KIND and prompt == DESCRIBE
        self.told.append(img)
        return f"a {list(COLOURS)[_colour_of(img)]} thing"

    def describe_batch(
        self, kind: str, prompt: str, pictures: Sequence[tuple[str, Image.Image]]
    ) -> str:
        assert kind == KIND and prompt == DESCRIBE and pictures
        assert all(max(img.size) <= 384 for _, img in pictures)
        self.tellings.append(list(pictures))
        return f"tellings/{len(self.tellings)}"

    def described(self, kind: str, batch: str) -> dict[str, str | NotDrawn] | None:
        if batch in self.waiting:
            return None
        pictures = self.tellings[int(batch.split("/")[1]) - 1]
        return {name: f"a {list(COLOURS)[_colour_of(img)]} thing" for name, img in pictures}


def _three(at: int, lean: int | None = None, style: int = 20) -> list[float]:
    """A work's three: its style one way, its subject and its sentence another."""
    subject = _direction(at, lean)[:PART]
    return [*_direction(style)[:PART], *subject, *subject]


def _work(
    service: FrameService, item_id: str, colour: str, tall: bool = False, **fields: Any
) -> Item:
    source, _, source_id = item_id.partition(":")
    fields.setdefault("kind", ItemKind.ARTWORK)
    item = Item(
        id=item_id,
        source=source,
        source_id=source_id,
        title=item_id,
        thumb_url=f"https://example.org/{source_id}.jpg",
        **fields,
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (48, 64) if tall else (64, 48), COLOURS[colour]).save(path, "JPEG")
    return service.library.upsert(item)


def _numbers(found: Looks) -> int:
    """The works sent through the Batch, their sentences and then their
    numbers read back: how many got them."""
    done = 0
    for _ in range(2):
        found.send()
        done += found.collect()
    return done


@pytest.fixture
def looks(service: FrameService) -> tuple[Looks, FakePainter]:
    painter = FakePainter()
    service.looks.painter = painter  # type: ignore[assignment]
    return service.looks, painter


# -- the numbers kept --------------------------------------------------------------------------


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


def test_the_gatekeeper_gets_a_works_close_look_alikes_without_google(
    looks: tuple[Looks, FakePainter],
) -> None:
    found, painter = looks
    found.three.add(
        [
            ("cover", 1, _three(0)),
            ("other cover", 1, _three(0, 1)),
            ("painting", 1, _three(1, style=21)),
        ]
    )
    painter.key = False  # numbers kept are enough
    assert found.near_ids("cover") == ["other cover"]
    assert found.near_ids("cover", 0) == []
    assert found.near_ids("without numbers") == []
    assert painter.asked == []


def test_a_broken_off_write_keeps_the_whole_rows(tmp_path: Path) -> None:
    index = LookIndex(tmp_path)
    index.add([("a", 1, _direction(0)), ("b", 1, _direction(1))])
    with (tmp_path / "vectors.i8").open("ab") as out:
        out.write(b"\x01\x02\x03")
    assert len(LookIndex(tmp_path)) == 2


# -- Google's embedding model --------------------------------------------------------------------


def test_the_embedding_request_and_its_cost(service: FrameService) -> None:
    sent: list[dict[str, Any]] = []

    def google(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/models/{EMBED_MODEL}:batchEmbedContents")
        assert request.headers["x-goog-api-key"] == "k-1"
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(
            200,
            json={
                "embeddings": [{"values": [0.1] * EMBED_SIZE} for _ in body["requests"]],
                "usageMetadata": {
                    "promptTokenCount": 274,
                    "promptTokenDetails": [
                        {"modality": "IMAGE", "tokenCount": 258},
                        {"modality": "TEXT", "tokenCount": 16},
                    ],
                },
            },
        )

    service.ai_config.set_gemini_key("k-1")
    painter = Painter(
        service.ai_config,
        service.claude,
        http=lambda: httpx.Client(transport=httpx.MockTransport(google)),
    )
    found = painter.embed(KIND, [Image.new("RGB", (8, 8)), QUERY + "morze"])
    assert len(found) == 2 and len(found[0]) == EMBED_SIZE
    first, second = sent[0]["requests"]
    assert first["output_dimensionality"] == EMBED_SIZE
    assert first["content"]["parts"][0]["inline_data"]["mime_type"] == "image/jpeg"
    assert second["content"]["parts"] == [{"text": QUERY + "morze"}]
    usd = embed_cost({"promptTokenDetails": [{"modality": "IMAGE", "tokenCount": 258}]})
    assert usd == pytest.approx(0.000116, abs=1e-6)
    assert painter.spending.by_kind()[KIND] == pytest.approx(0.00012, abs=2e-6)
    with pytest.raises(ValueError):
        painter.embed(KIND, [])


# -- the background ------------------------------------------------------------------------------


def test_only_the_museums_and_his_own_works_with_a_thumbnail_are_sent(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    # His own works too (Mateusz 2026-11-15: "Idzie normalnie do Google"),
    # never his photographs.
    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _work(service, "upload:1", "red", kind=ItemKind.OWN)
    _work(service, "icloud:1", "red", kind=ItemKind.PHOTO)
    gone = Item(id="met:3", source="met", source_id="3", thumb_url="https://example.org/3.jpg")
    service.library.upsert(gone)  # no thumbnail here: not downloaded for this
    assert _numbers(found) == 3
    assert found.three.ids() == {"met:1", "met:2", "upload:1"}
    assert found.counts() == (3, 4)
    assert _numbers(found) == 0  # nothing new
    service.ai_config.update(AiConfigUpdate(looks=False))
    assert not found.enabled() and _numbers(found) == 0


def test_a_changed_picture_of_a_cared_work_is_sent_again(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    item = _work(service, "met:1", "red")
    found.cared = lambda: {"met:1": 0}
    assert _numbers(found) == 1
    thumb = service.images.thumb_path(item)
    Image.new("RGB", (64, 48), COLOURS["blue"]).save(thumb, "JPEG")
    stamp = int(thumb.stat().st_mtime) + 5
    import os

    os.utime(thumb, (stamp, stamp))
    assert _numbers(found) == 1
    assert found.three.stamp("met:1") == stamp


# -- the questions -------------------------------------------------------------------------------


def test_words_find_works_that_look_so(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _work(service, "met:3", "red", excluded=True)  # hidden in the app
    _numbers(found)
    asked = len(painter.asked)
    assert [f.item.id for f in found.words("czerwony red zachód")] == ["met:1"]
    assert [f.item.id for f in found.words("  Czerwony   red zachód ")] == ["met:1"]
    assert len(painter.asked) == asked + 1  # the same words are not asked again
    assert found.words("nic") == []  # far from every work


def test_a_photograph_and_a_work_find_works_that_look_alike(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    red = _work(service, "met:1", "red")
    _work(service, "aic:7", "red")
    _work(service, "met:2", "blue")
    _numbers(found)
    photo = Image.new("RGB", (300, 200), COLOURS["blue"])
    assert [f.item.id for f in found.picture(photo)] == ["met:2"]
    assert [f.item.id for f in found.similar(red)] == ["aic:7"]
    assert found.neighbours("met:1") == ["aic:7"]
    assert found.similar(Item(id="met:9", source="met", source_id="9")) == []


def test_nothing_is_asked_without_a_key_or_numbers(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, painter = looks
    painter.key = False
    with pytest.raises(AiUnavailable):
        found.words("czerwony")
    painter.key = True
    service.ai_config.set_gemini_key("k")
    with pytest.raises(AiUnavailable):  # no work has its numbers yet
        found.words("czerwony")


def test_the_api(service: FrameService, looks: tuple[Looks, FakePainter]) -> None:
    from frame_server.web import create_app

    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _numbers(found)
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        status = client.get("/api/looks").json()
        assert status == {"enabled": True, "ready": True, "done": 2, "total": 2}
        words = client.get("/api/looks/search", params={"q": "niebieski blue"}).json()
        assert [i["id"] for i in words["items"]] == ["met:2"] and words["scores"][0] > 0.9
        out = io.BytesIO()
        Image.new("RGB", (40, 30), COLOURS["red"]).save(out, "JPEG")
        files = {"file": ("photo.jpg", out.getvalue(), "image/jpeg")}
        photo = client.post("/api/looks/picture", files=files).json()
        assert [i["id"] for i in photo["items"]] == ["met:1"]
        bad = {"file": ("photo.jpg", b"not a picture", "image/jpeg")}
        assert client.post("/api/looks/picture", files=bad).status_code == 422
        like = client.get("/api/library/items/met:1/looks").json()
        assert like["items"] == []  # nothing else looks red
        service.ai_config.update(AiConfigUpdate(looks=False))
        assert client.get("/api/looks/search", params={"q": "red"}).status_code == 409
        assert client.get("/api/library/items/met:1/looks").json()["items"] == []
        view = client.get("/api/ai").json()
        assert view["looks"] is False and view["looks_done"] == 2
        assert client.post("/api/terms/sentence", json={"text": "morze"}).status_code in (404, 405)


def test_works_that_look_alike_come_first_among_the_studys_candidates(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    red = _work(service, "met:1", "red", artist="Anna A")
    _work(service, "aic:7", "red", artist="Bruno B")
    _work(service, "aic:8", "red", artist="Anna A")  # the artist's own: "Inne prace artysty"
    _numbers(found)
    assert [i.id for i in service.daily.candidates(red)] == ["aic:7"]


def test_the_works_go_through_the_batch_and_wait_for_it(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    found, painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    painter.waiting.update({"tellings/1", "batches/1"})
    assert found.round() == (0, 2)  # their sentences asked
    assert found.send() == 0  # out already: not sent twice
    assert found.collect() == 0 and len(found.three) == 0
    painter.waiting.discard("tellings/1")
    assert found.round() == (0, 2)  # the sentences back, the numbers asked
    assert [n for n, _ in painter.batches[0]] == [
        f"met:{n}#{p}" for n in (1, 2) for p in ("g", "h", "c")
    ]
    painter.waiting.clear()

    def restarted() -> Looks:
        return Looks(
            service.library,
            service.images,
            painter,
            service.ai_config,
            found.root,  # type: ignore[arg-type]
        )

    again = restarted()  # a restart keeps the batches out
    assert again.collect() == 2 and again.three.ids() == {"met:1", "met:2"}
    assert painter.asked == [] and painter.told == []  # nothing asked one by one
    told = (found.three.root / "told.jsonl").read_text().splitlines()
    assert [json.loads(line)["words"] for line in told] == ["a red thing", "a blue thing"]
    assert restarted()._told == {}  # numbered: no sentence waits


def test_the_embedding_batch_request_and_its_answers(service: FrameService) -> None:
    sent: list[dict[str, Any]] = []
    state = {"now": "BATCH_STATE_RUNNING"}

    def google(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path.endswith(f"/models/{EMBED_MODEL}:asyncBatchEmbedContent")
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"name": "batches/b1", "metadata": {}})
        assert request.url.path.endswith("/batches/b1")
        answers = [
            {
                "response": {"embedding": {"values": [0.5] * EMBED_SIZE}},
                "metadata": {"key": "met:1"},
            },
            {"error": {"code": 3, "message": "bad picture"}, "metadata": {"key": "met:2"}},
        ]
        return httpx.Response(
            200,
            json={
                "name": "batches/b1",
                "metadata": {"state": state["now"]},
                "response": {
                    "inlinedResponses": {"inlinedResponses": answers}
                },  # as Google answers
            },
        )

    service.ai_config.set_gemini_key("k-1")
    painter = Painter(
        service.ai_config,
        service.claude,
        http=lambda: httpx.Client(transport=httpx.MockTransport(google)),
    )
    pictures = [("met:1", Image.new("RGB", (8, 8))), ("met:2", Image.new("RGB", (8, 8)))]
    assert painter.embed_batch(KIND, pictures) == "batches/b1"
    request = sent[0]["batch"]["input_config"]["requests"]["requests"][0]
    assert request["metadata"] == {"key": "met:1"}
    assert request["request"]["output_dimensionality"] == EMBED_SIZE
    assert painter.embed_batched(KIND, "batches/b1") is None  # still at it
    state["now"] = "BATCH_STATE_SUCCEEDED"
    found = painter.embed_batched(KIND, "batches/b1")
    assert found is not None and found["met:2"] is None and len(found["met:1"] or []) == EMBED_SIZE
    assert painter.spending.by_kind()[KIND] == pytest.approx(0.000058, abs=1e-6)  # half price


def test_szukaj_narrows_the_look_by_its_other_choices(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    """Mateusz 2026-11-13: the works found by how they look in Szukaj's own
    list, the groups (an artist, a technique, colours) narrowing them."""
    from frame_server.ai.config import AiConfigUpdate
    from frame_server.web import create_app

    found, _painter = looks
    service.ai_config.set_gemini_key("k")
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
        service.ai_config.update(AiConfigUpdate(looks=False))
        assert client.get("/api/library/items", params={"look": "red"}).status_code == 409
        assert len(ids()) == 4  # without words for a look: as it was


def test_szukaj_finds_the_works_like_one_nearest_first(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    """„Szukaj podobnych” on a work's card (Mateusz 2026-11-13): Szukaj
    with the chip "Podobne do", the works that look like it nearest first,
    the groups narrowing them; no museum is asked."""
    from frame_server.web import create_app

    found, _painter = looks
    service.ai_config.set_gemini_key("k")

    def leaning(x: float) -> list[float]:
        vector = [0.0] * EMBED_SIZE
        vector[0], vector[1] = 1.0, x
        return vector

    def three(x: float) -> list[float]:
        return [*leaning(x)[:PART]] * 3

    for n, artist in enumerate(["Anna A", "Bruno B", "Anna A", "Anna A", "Anna A"], start=1):
        _work(service, f"met:{n}", "red", artist=artist)
    found.three.add(
        [
            ("met:1", 1, three(0)),
            ("met:4", 1, three(0.3)),
            ("met:2", 1, three(0.6)),
            ("met:3", 1, three(0.9)),
            ("met:5", 1, [*_direction(7)[:PART]] * 3),  # nothing like it
            # The catalogue's other works, all unlike them.
            *((f"cma:{n}", 1, [*_direction(n)[:PART]] * 3) for n in range(30, 40)),
        ]
    )
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:

        def ids(**params: Any) -> list[str]:
            page = client.get("/api/library/items", params=params).json()
            return [i["id"] for i in page["items"]]

        assert ids(like="met:1") == ["met:4", "met:2", "met:3"]
        assert ids(like="met:1", artist="Anna A") == ["met:4", "met:3"]
        assert ids(like="met:1", sort="artist") == ["met:4", "met:2", "met:3"]
        assert ids(like="met:9") == []
        service.ai_config.update(AiConfigUpdate(looks=False))
        assert client.get("/api/library/items", params={"like": "met:1"}).status_code == 409
    rules = PlaylistRules(like="met:1")
    assert not rules.is_empty() and rules.search_key() == ""  # no museum asked


def test_a_photograph_is_searched_in_szukajs_own_list(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    """„Szukaj zdjęciem” as „Szukaj podobnych” (Mateusz 2026-11-15): the
    photograph's numbers kept under a key Szukaj asks as ``like``, the
    groups narrowing it, a smart playlist keeping it; the same photograph
    again asks Google nothing, and the photograph itself is not kept."""
    from frame_server.web import create_app

    found, painter = looks
    service.ai_config.set_gemini_key("k")
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
        asked = len(painter.asked)
        assert client.post("/api/looks/photo", files=files).json()["key"] == key
        assert len(painter.asked) == asked  # the same photograph: Google not asked again

        def ids(**params: Any) -> list[str]:
            page = client.get("/api/library/items", params=params).json()
            return [i["id"] for i in page["items"]]

        assert sorted(ids(like=key)) == ["aic:7", "met:1"]
        assert ids(like=key, artist="Anna A") == ["met:1"]
        assert ids(like="photo:0000") == []  # a key nobody kept
        bad = {"file": ("photo.jpg", b"not a picture", "image/jpeg")}
        assert client.post("/api/looks/photo", files=bad).status_code == 422
    kept = list((found.root / "photos").iterdir())
    assert len(kept) == 1 and kept[0].stat().st_size == 3 * PART * 4  # numbers only
    rules = PlaylistRules(like=key)
    assert sorted(i.id for i in service.library.query(rules)[1]) == ["aic:7", "met:1"]
    assert rules.search_key() == ""  # no museum asked
    painter.key = False
    with TestClient(app) as client:
        assert client.post("/api/looks/photo", files=files).status_code == 200  # kept already
        other = io.BytesIO()
        Image.new("RGB", (40, 30), COLOURS["blue"]).save(other, "JPEG")
        new = {"file": ("photo.jpg", other.getvalue(), "image/jpeg")}
        assert client.post("/api/looks/photo", files=new).status_code == 409


def test_a_smart_playlist_keeps_the_look_and_waits_for_google(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    from frame_server.library.models import PlaylistRules

    found, painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red", artist="Anna A")
    _work(service, "met:2", "blue", artist="Anna A")
    _numbers(found)
    rules = PlaylistRules(look="niebieski blue", artists=["Anna A"])
    assert not rules.is_empty() and rules.search_key()  # the artist for the museums
    assert PlaylistRules(look="red").search_key() == ""  # no museum asked for a look
    painter.key = False
    assert service.library.query(rules) == (0, [])
    painter.key = True  # the empty answer was not kept: asked again
    assert [i.id for i in service.library.query(rules)[1]] == ["met:2"]


def test_a_look_puts_only_the_works_near_it_through_the_other_rules(
    service: FrameService, looks: tuple[Looks, FakePainter], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole catalogue put through the rules for a look's words stood
    the server still for minutes (115 000 works, 2026-11-13): only those
    the look may choose from are."""
    from frame_server import looks as looks_module
    from frame_server.library import repo
    from frame_server.library.models import PlaylistRules

    found, _painter = looks
    service.ai_config.set_gemini_key("k")
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


def test_a_batch_too_heavy_for_google_goes_in_halves(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    """300 thumbnails weighed 30 MB, Google takes 19: from 16:08 on
    2026-11-13 no work got its numbers."""
    from frame_server.ai.gemini import TooHeavy

    found, painter = looks
    service.ai_config.set_gemini_key("k")
    for n in range(1, 6):
        _work(service, f"met:{n}", "red")
    _work(service, "met:9", "blue")
    taken = painter.describe_batch

    def describe_batch(kind: str, prompt: str, pictures: Sequence[tuple[str, Image.Image]]) -> str:
        if len(pictures) > 2 or any(name == "met:9" for name, _ in pictures):
            raise TooHeavy("too heavy")
        return taken(kind, prompt, pictures)

    painter.describe_batch = describe_batch  # type: ignore[method-assign]
    assert found.send() == 5  # all but the one too heavy alone
    assert all(len(b) <= 2 for b in painter.tellings)
    assert found.collect() == 0 and len(found._told) == 5
    assert found.send() == 5  # their numbers
    assert found.collect() == 5 and "met:9" not in found.three
    assert found.send() == 0  # it waits as one without a thumbnail


def test_a_suggestion_given_up_counts_nothing_more(service: FrameService) -> None:
    from frame_server.web.discover_api import _term_hits

    _work(service, "met:1", "red", artist="Anna Pejzażystka")
    assert _term_hits(service, "pejzaż", 10)  # counted
    assert _term_hits(service, "pejzaż", 10, gone=lambda: True) == []


def test_the_museums_are_asked_a_looks_searches_and_judged_by_it(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    """Mateusz 2026-11-13 (card, "Hasła i ocena wyglądem"): Haiku's searches
    for the look, in each museum's language; what they bring judged by its
    thumbnail, the numbers kept."""
    from frame_server.library.search import MuseumSearch
    from frame_server.library.wording import Wording

    found, painter = looks
    service.ai_config.set_gemini_key("k")
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
    assert {"cma:10", "cma:11", "cma:12"} <= found.three.ids()  # numbers kept
    painter.key = False
    assert found.judge("red", museum) == []  # no Google: nothing judged


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


def test_a_copy_without_numbers_shows_what_its_works_other_copy_looks_like(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    """Van Gogh's Sunflowers found by a look had no "Podobne wyglądem": the
    card showed the work's best copy, the index had another (2026-11-13)."""
    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red", artist="Vincent van Gogh")
    _work(service, "aic:7", "red")
    _numbers(found)
    copy = service.library.upsert(
        Item(id="wmc:5", source="wmc", source_id="5", title="met:1", artist="Vincent van Gogh")
    )
    works = service.library.works()
    assert works.group_index("wmc:5") == works.group_index("met:1") is not None
    assert copy.id not in found.three
    assert [f.item.id for f in found.similar(copy)] == ["aic:7"]


# -- subject and style apart (Mateusz 2026-11-17) ---------------------------------------------


def test_szukaj_finds_the_works_like_one_by_subject_or_by_style(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    """„Podobne do” with „Temat i styl | Temat | Styl” (Mateusz 2026-11-17:
    "chciałbym mieć styl i tematykę osobno"): the subject finds the same
    colour in the other shape, the style the same shape in another colour."""
    from frame_server.web import create_app

    found, _painter = looks
    service.ai_config.set_gemini_key("k")
    _work(service, "met:1", "red")
    _work(service, "met:2", "red", tall=True)  # its subject, not its style
    _work(service, "met:3", "blue")  # its style, not its subject
    _work(service, "met:4", "green", tall=True)  # neither
    assert _numbers(found) == 4
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:

        def ids(**params: Any) -> list[str]:
            page = client.get("/api/library/items", params=params).json()
            return [i["id"] for i in page["items"]]

        assert ids(like="met:1", like_by="subject") == ["met:2"]
        assert ids(like="met:1", like_by="style") == ["met:3"]
        assert set(ids(like="met:1")) <= {"met:2", "met:3"}
        assert (
            client.get("/api/library/items", params={"like": "met:1", "like_by": "x"}).status_code
            == 422
        )
    rules = PlaylistRules(like="met:1", like_by="style")  # a smart playlist keeps it
    assert [i.id for i in service.library.query(rules)[1]] == ["met:3"]
    assert PlaylistRules.model_validate({"like": "met:1"}).like_by == ""  # rules kept before


def test_the_numbers_of_before_answer_until_most_works_have_their_three(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    """The whole thumbnail's numbers answer while the three are made, and
    are dropped once :data:`READY_SHARE` of the works have them."""
    from frame_server.looks import PHOTO

    _, painter = looks
    service.ai_config.set_gemini_key("k")
    red = _work(service, "met:1", "red")
    _work(service, "aic:7", "red")
    _work(service, "met:2", "blue")
    root = service.looks.root
    LookIndex(root).add(
        [
            ("met:1", 1, _direction(0, 10)),
            ("aic:7", 1, _direction(0, 10)),
            ("met:2", 1, _direction(1, 10)),
        ]
    )
    (root / "photos").mkdir(parents=True, exist_ok=True)
    np.asarray(_direction(1), dtype=np.float32).tofile(root / "photos" / "ab.f32")
    found = Looks(
        service.library,
        service.images,
        painter,  # type: ignore[arg-type]
        service.ai_config,
        root,
    )
    assert found.old() and found.ready() and len(found.three) == 0
    assert [f.item.id for f in found.similar(red, by="style")] == ["aic:7"]
    assert found.alike(PHOTO + "ab") == ["met:2"]
    assert [f.item.id for f in found.words("red")] == ["met:1", "aic:7"]
    found.send()
    found.collect()
    assert found.old() and not found.settle()  # sentences only
    found.round()  # their numbers asked
    found.round()  # and back
    assert not found.old() and len(found.three) == 3
    # The numbers of before stay until the owner has seen the three do well.
    assert (root / "vectors.i8").exists() and (root / "photos" / "ab.f32").exists()
    assert len(found.index) == 0  # not read
    assert found.alike(PHOTO + "ab") == []  # a photograph of before: asked again
    assert [f.item.id for f in found.similar(red, by="subject")] == ["aic:7"]
    again = Looks(service.library, service.images, painter, service.ai_config, root)  # type: ignore[arg-type]
    assert not again.old() and len(again.index) == 0
    (root / "three" / "ready").unlink()  # back to the numbers of before
    assert Looks(service.library, service.images, painter, service.ai_config, root).old()  # type: ignore[arg-type]


def test_the_sentence_and_the_numbers_of_a_work_asked_of_google(service: FrameService) -> None:
    """Gemini Flash-Lite's sentence (low resolution, plain words), and the
    embedding model asked a picture with words in one request."""
    from frame_server.ai.gemini import DESCRIBER
    from frame_server.looks import STYLE_ASK

    sent: list[tuple[str, dict[str, Any]]] = []

    def google(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        sent.append((request.url.path, body))
        if request.url.path.endswith(":generateContent"):
            return httpx.Response(
                200,
                json={
                    "candidates": [{"content": {"parts": [{"text": " A saint  kneels. "}]}}],
                    "usageMetadata": {"promptTokenCount": 334, "candidatesTokenCount": 42},
                },
            )
        if request.url.path.endswith(":batchGenerateContent"):
            return httpx.Response(200, json={"name": "batches/t1"})
        if request.url.path.endswith("/batches/t1"):
            answers = [
                {
                    "response": {
                        "candidates": [{"content": {"parts": [{"text": "A ship."}]}}],
                        "usageMetadata": {"promptTokenCount": 334, "candidatesTokenCount": 42},
                    },
                    "metadata": {"key": "met:1"},
                },
                {"error": {"code": 3, "message": "no"}, "metadata": {"key": "met:2"}},
            ]
            return httpx.Response(
                200,
                json={
                    "metadata": {"state": "BATCH_STATE_SUCCEEDED"},
                    "response": {"inlinedResponses": {"inlinedResponses": answers}},
                },
            )
        return httpx.Response(
            200, json={"embeddings": [{"values": [0.1] * EMBED_SIZE} for _ in body["requests"]]}
        )

    service.ai_config.set_gemini_key("k-1")
    painter = Painter(
        service.ai_config,
        service.claude,
        http=lambda: httpx.Client(transport=httpx.MockTransport(google)),
    )
    img = Image.new("RGB", (8, 8))
    assert painter.describe(KIND, DESCRIBE, img) == "A saint kneels."
    path, body = sent[-1]
    assert path.endswith(f"/models/{DESCRIBER}:generateContent")
    assert body["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_LOW"
    assert body["contents"][0]["parts"][1] == {"text": DESCRIBE}
    usd = (334 * 0.25 + 42 * 1.50) / 1e6
    assert painter.spending.by_kind()[KIND] == pytest.approx(usd, abs=1e-6)
    painter.embed(KIND, [(STYLE_ASK, img)])
    parts = sent[-1][1]["requests"][0]["content"]["parts"]
    assert parts[0] == {"text": STYLE_ASK} and "inline_data" in parts[1]
    assert painter.describe_batch(KIND, DESCRIBE, [("met:1", img), ("met:2", img)]) == "batches/t1"
    told = painter.described(KIND, "batches/t1")
    assert told is not None and told["met:1"] == "A ship." and isinstance(told["met:2"], NotDrawn)


def test_google_taking_no_more_batches_leaves_those_out_and_tries_later(
    service: FrameService, looks: tuple[Looks, FakePainter]
) -> None:
    """More batches out at a time (Mateusz 2026-11-18: "Czy można jakoś
    przyspieszyć tworzenie odcisków?"): when Google takes no more, those out
    stay and the round ends without trouble."""
    from frame_server.ai.gemini import Busy

    found, painter = looks
    service.ai_config.set_gemini_key("k")
    for n in range(1, 4):
        _work(service, f"met:{n}", "red")
    taken = painter.describe_batch

    def describe_batch(kind: str, prompt: str, pictures: Sequence[tuple[str, Image.Image]]) -> str:
        if len(painter.tellings) >= 1:
            raise Busy("Google answered 429: too many batches")
        return taken(kind, prompt, pictures[:1])

    painter.describe_batch = describe_batch  # type: ignore[method-assign]
    import frame_server.looks as looks_module

    looks_module.PER_TOLD, before = 1, looks_module.PER_TOLD
    try:
        assert found.round() == (0, 1)  # one out, then Google said no more
    finally:
        looks_module.PER_TOLD = before
    assert len(found._out("telling.json")) == 1 and found.trouble is None
