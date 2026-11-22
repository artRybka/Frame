"""SigLIP 2's numbers made on the server (frame_server.seen, Mateusz
2026-11-20: "Przesiadamy."): the model fetched and checked, every work
numbered in the background from its kept thumbnail, the owner's question."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from frame_server import seen
from frame_server.library.models import Item, ItemKind
from frame_server.seen import FILES, MODEL, SIDE, SIZE, Seen, SeenModel
from frame_server.service import FrameService

COLOURS = {"red": (200, 30, 30), "blue": (30, 40, 200), "green": (30, 170, 40)}


class FakeModel(SeenModel):
    """A picture points the way of its strongest colour; words the way of
    the colour they name."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.seen = 0

    def here(self) -> bool:
        return True

    def fetch(self, client: httpx.Client | None = None) -> None:
        pass

    def phone(self, client: httpx.Client | None = None) -> Path | None:
        return super().phone(client) if client is not None else None

    @staticmethod
    def _way(at: int) -> np.ndarray:
        out = np.zeros(SIZE, dtype=np.float32)
        out[at] = 1.0
        return out

    def pictures(self, imgs: Sequence[Image.Image]) -> np.ndarray:
        self.seen += len(imgs)
        rows = []
        for img in imgs:
            r, g, b = img.convert("RGB").resize((1, 1)).getpixel((0, 0))  # type: ignore[misc]
            rows.append(self._way(int(np.argmax([r, g, b]))))
        return np.stack(rows)

    def words(self, texts: Sequence[str]) -> np.ndarray:
        return np.stack([self._way(["red", "green", "blue"].index(t.split()[0])) for t in texts])


def _work(service: FrameService, item_id: str, colour: str, **fields: object) -> Item:
    source, _, source_id = item_id.partition(":")
    fields.setdefault("kind", ItemKind.ARTWORK)
    item = Item(
        id=item_id,
        source=source,
        source_id=source_id,
        title=item_id,
        thumb_url=f"https://example.org/{source_id}.jpg",
        **fields,  # type: ignore[arg-type]
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), COLOURS[colour]).save(path, "JPEG")
    return service.library.upsert(item)


@pytest.fixture
def found(service: FrameService, tmp_path: Path) -> Seen:
    service.seen.model = FakeModel(tmp_path / "model")
    return service.seen


def test_every_work_is_numbered_once_and_again_when_its_thumbnail_changes(
    service: FrameService, found: Seen
) -> None:
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _work(service, "upload:1", "green", kind=ItemKind.OWN)
    _work(service, "icloud:1", "red", kind=ItemKind.PHOTO)  # his photograph: never
    service.library.upsert(
        Item(id="met:3", source="met", source_id="3", thumb_url="https://example.org/3.jpg")
    )  # no thumbnail here
    assert found.number() == 3
    assert found.counts() == (3, 4)
    assert found.number() == 0
    model = found.model
    assert isinstance(model, FakeModel) and model.seen == 3
    # A sharper copy: its thumbnail changes, the work is numbered again.
    path = service.images.kept_thumb("met:1")
    assert path is not None
    Image.new("RGB", (64, 48), COLOURS["green"]).save(path, "JPEG")
    import os

    os.utime(path, (path.stat().st_mtime + 5, path.stat().st_mtime + 5))
    assert found.number() == 1
    assert [i for i, _ in found.like("met:1", 1) or []] == ["upload:1"]
    # Kept on disk: a new start reads them.
    again = Seen(service.library, service.images, found.root, model=model)
    assert again.counts() == (3, 4)


def test_works_gone_are_forgotten(service: FrameService, found: Seen) -> None:
    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    found.number()
    assert service.library.delete("met:2")
    assert found.tidy() == 1 and found.index.ids() == {"met:1"}


def test_the_owner_asks_by_work_and_by_words(service: FrameService, found: Seen) -> None:
    from frame_server.web import create_app

    _work(service, "met:1", "red")
    _work(service, "met:2", "blue")
    _work(service, "met:3", "red")
    found.number()
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        state = client.get("/api/debug/seen", params={"item": "met:1", "count": 1}).json()
        assert state["done"] == 3 and state["total"] == 3 and state["model"] is True
        assert state["ids"] == ["met:3"] and state["scores"][0] > 0.99
        words = client.get("/api/debug/seen", params={"text": "blue paint", "count": 1}).json()
        assert words["ids"] == ["met:2"]


def test_the_model_is_fetched_and_checked(tmp_path: Path) -> None:
    files = {name: f"{name} bytes".encode() for name in FILES}
    sums = "".join(f"{hashlib.sha256(v).hexdigest()}  {k}\n" for k, v in files.items())
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        asked.append(name)
        assert f"/{MODEL}/" in request.url.path
        if name == seen.SUMS:
            return httpx.Response(200, text=sums)
        return httpx.Response(200, content=files[name])

    model = SeenModel(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(answer)) as client:
        model.fetch(client)
        assert model.here()
        assert (model.folder / "words.onnx").read_bytes() == b"words.onnx bytes"
        asked.clear()
        model.fetch(client)
        assert asked == []  # here already

    broken = SeenModel(tmp_path / "broken")

    def changed(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if name == seen.SUMS:
            return httpx.Response(200, text=sums)
        return httpx.Response(200, content=b"something else")

    with httpx.Client(transport=httpx.MockTransport(changed)) as client, pytest.raises(ValueError):
        broken.fetch(client)
    assert not broken.here() and not list(broken.folder.glob("*.part"))


def test_words_and_pictures_are_read_as_siglip_was_taught() -> None:
    assert SeenModel.clean("Drzeworyt  japoński, &amp; Fuji!") == "drzeworyt japoński fuji"
    seen_as = SeenModel.pixels(Image.new("L", (300, 100), 255))
    assert seen_as.shape == (3, SIDE, SIDE) and np.allclose(seen_as, 1.0)


def test_siglip_answers_in_googles_place_once_most_works_have_numbers(
    service: FrameService, found: Seen, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seen, "LEAST_SUBJECT", 1)
    monkeypatch.setattr(seen, "FLOORS_SET", True)
    looks = service.looks
    assert (
        not service.ai_config.config.gemini_key
        if hasattr(service.ai_config.config, "gemini_key")
        else True
    )
    _work(service, "met:1", "red", medium="oil on canvas", year=1890, terms=["subject:sea"])
    _work(service, "met:2", "red", medium="etching", year=1650, terms=["subject:sea"])
    _work(service, "met:3", "blue", medium="oil on canvas", year=1880, terms=["subject:city"])
    assert not looks.enabled()  # no Google key, SigLIP not answering yet
    found.number()
    assert not found.settle()  # the layers not taught yet
    assert found.teach() and found.heads is not None
    assert found.settle() and looks.local() and looks.enabled()
    # A new start reads that it answers.
    again = Seen(service.library, service.images, found.root, model=found.model)
    assert again.answers()
    # Words, a photograph, a work: no Google asked.
    assert [f.item.id for f in looks.words("blue water")] == ["met:3"]
    assert {f.item.id for f in looks.words("red sky")} == {"met:1", "met:2"}
    photo = Image.new("RGB", (40, 30), COLOURS["blue"])
    assert [f.item.id for f in looks.picture(photo)] == ["met:3"]
    import io

    out = io.BytesIO()
    photo.save(out, "JPEG")
    key = looks.photo(out.getvalue(), photo)
    assert (looks.alike(key) or [""])[0] == "met:3"  # nearest first, no floor
    assert looks.alike("met:1")[:1] == ["met:2"]
    assert looks.alike("met:1", by="style")[:1] == ["met:2"]
    assert looks.alike("met:1", by="subject")[:1] == ["met:2"]
    assert looks.near_ids("met:1") == ["met:2"]


def test_the_form_is_taught_by_technique_and_half_century(service: FrameService) -> None:
    from frame_server.seen import TECHNIQUES, form_marks, technique

    oil = Item(id="a:1", source="a", source_id="1", title="x", medium="Oil on canvas", year=1890)
    print_ = Item(
        id="a:2",
        source="a",
        source_id="2",
        title="x",
        medium="Woodblock print",
        date_text="ca. 1833",
    )
    assert technique(oil) == "oil" and technique(print_) == "woodcut"
    names = [n for n, _ in TECHNIQUES]
    assert form_marks(oil) == [names.index("oil"), len(TECHNIQUES) + (1890 - 1300) // 50]
    assert form_marks(print_)[1] == len(TECHNIQUES) + (1833 - 1300) // 50
    assert form_marks(Item(id="a:3", source="a", source_id="3", title="x")) == []


class _Session:
    def run(self, _out: object, feed: dict[str, np.ndarray]) -> list[np.ndarray]:
        return [np.zeros((len(next(iter(feed.values()))), SIZE), dtype=np.float32)]


def test_the_model_lets_go_only_with_nothing_left_to_number(
    found: Seen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Out of memory once every work has its numbers, never while works
    wait or the app is in use: its first counting is not to be held up
    (Mateusz 2026-11-20)."""
    model = SeenModel(tmp_path / "real")
    made: list[str] = []
    monkeypatch.setattr(model, "fetch", lambda client=None: None)
    monkeypatch.setattr(model, "phone", lambda client=None: None)
    monkeypatch.setattr(model, "_session", lambda name: made.append(name) or _Session())
    found.model = model
    for name in ("tidy", "teach", "settle"):
        monkeypatch.setattr(found, name, lambda: None)
    rounds = iter([True, False, False, False])  # busy, then three rounds
    counts = iter([16, 0])
    states: list[bool] = []

    def busy() -> bool:
        return next(rounds)

    def number() -> int:
        count = next(counts)
        if count:
            model.pictures([Image.new("RGB", (8, 8))])
        states.append(model.loaded())
        return count

    def wait(_pause: float) -> bool:
        states.append(model.loaded())
        if len(states) >= 5:
            found._stop.set()
        return found._stop.is_set()

    found.busy = busy
    monkeypatch.setattr(found, "number", number)
    monkeypatch.setattr(found._stop, "wait", wait)
    found._run()
    # busy: nothing loaded; 16 numbered: kept; none left: kept while it
    # looks, let go before the long pause.
    assert states == [False, True, True, True, False]
    assert made == ["picture.onnx"]
    model.pictures([Image.new("RGB", (8, 8))])
    assert made == ["picture.onnx", "picture.onnx"]  # read again when wanted


def test_the_phone_numbers_a_photograph_itself_and_sends_only_numbers(
    service: FrameService, found: Seen, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import base64

    from frame_server.web import create_app

    monkeypatch.setattr(seen, "LEAST_SUBJECT", 1)
    monkeypatch.setattr(seen, "FLOORS_SET", True)
    monkeypatch.setattr(seen, "PHONE_SUM", hashlib.sha256(b"core ml").hexdigest())
    _work(service, "met:1", "red", medium="oil on canvas", year=1890, terms=["subject:sea"])
    _work(service, "met:3", "blue", medium="oil on canvas", year=1880, terms=["subject:city"])
    found.number()
    blue = np.zeros(SIZE, dtype="<f4")
    blue[2] = 3.0  # any length: kept at length 1
    sent = {"model": seen.PHONE, "look": base64.b64encode(blue.tobytes()).decode()}
    app = create_app(service.settings)
    app.state.service = service
    with TestClient(app) as client:
        state = client.get("/api/looks/phone").json()
        assert state == {
            "model": seen.PHONE,
            "here": False,
            "size": 0,
            "sha256": "",
            "answers": False,
        }
        assert client.get("/api/looks/phone/model").status_code == 404
        assert client.post("/api/looks/photo/numbers", json=sent).status_code == 409

        def answer(request: httpx.Request) -> httpx.Response:
            assert request.url.path.endswith(f"/{seen.PHONE}/{seen.PHONE_FILE}")
            return httpx.Response(200, content=b"core ml")

        with httpx.Client(transport=httpx.MockTransport(answer)) as http:
            assert found.model.phone(http) is not None
        assert found.teach() and found.settle()
        state = client.get("/api/looks/phone").json()
        assert state["here"] and state["answers"] and state["size"] == 7
        assert client.get("/api/looks/phone/model").content == b"core ml"
        key = client.post("/api/looks/photo/numbers", json=sent).json()["key"]
        assert key.startswith("photo:") and (service.looks.alike(key) or [""])[0] == "met:3"
        assert client.post("/api/looks/photo/numbers", json=sent).json()["key"] == key
        other = {**sent, "model": "look-model-other"}
        assert client.post("/api/looks/photo/numbers", json=other).status_code == 409
        short = {**sent, "look": base64.b64encode(blue[:10].tobytes()).decode()}
        assert client.post("/api/looks/photo/numbers", json=short).status_code == 422
        assert (
            client.post("/api/looks/photo/numbers", json={**sent, "look": "!"}).status_code == 422
        )


def test_the_phones_model_is_checked_on_the_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = SeenModel(tmp_path)
    monkeypatch.setattr(seen, "PHONE_SUM", "")
    assert model.phone() is None  # none released yet: never asked
    monkeypatch.setattr(seen, "PHONE_SUM", hashlib.sha256(b"core ml").hexdigest())
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"changed"))
        ) as http,
        pytest.raises(ValueError),
    ):
        model.phone(http)
    assert model.phone_here() is None and not list(tmp_path.rglob("*.part"))


def test_a_photograph_asks_the_museums_by_its_nearest_works_subjects(
    service: FrameService, found: Seen, monkeypatch: pytest.MonkeyPatch
) -> None:
    from frame_server import looks as looks_module

    monkeypatch.setattr(seen, "LEAST_SUBJECT", 1)
    monkeypatch.setattr(seen, "FLOORS_SET", True)
    monkeypatch.setattr(looks_module, "PHOTO_SUBJECT", 2)
    looks = service.looks
    _work(service, "met:1", "blue", terms=["subject:sea", "subject:ships"])
    _work(service, "met:2", "blue", terms=["subject:sea"])
    _work(service, "met:3", "red", terms=["subject:city"])
    found.number()
    assert found.teach() and found.settle()
    blue = np.zeros(SIZE, dtype=np.float32)
    blue[2] = 1.0
    key = looks.photo_numbers(blue)
    words = service._look_searches(key)
    assert [w.en for w in words] == ["sea"] and words[0].in_language("pl") == "morze"
    # What the museums bring is judged by how it looks like the photograph.
    _work(service, "met:4", "blue")
    _work(service, "met:5", "green")
    museum = [service.library.get("met:5"), service.library.get("met:4")]
    # As near as the catalogue's works shown for it, the nearest first.
    judged = service._judge_look(key, [i for i in museum if i])
    assert judged and judged[0].id == "met:4"
    assert service._look_searches("photo:0000") == []  # not searched here


def test_the_subject_alone_is_asked_without_the_form(found: Seen) -> None:
    """Mateusz 2026-11-22 (Wyspiański's self-portrait by Treść alone: "w
    wynikach praktycznie tylko rysunek"; "Bez formy" on the boards): the
    directions the form layer reads are out of both sides, and the works
    are told at the levels of before."""
    from frame_server.seen import Heads

    def way(**at: float) -> list[float]:
        out = np.zeros(SIZE, dtype=np.float32)
        for name, value in at.items():
            out[{"form": 0, "subject": 1, "face": 2}[name]] = value
        return list(out)

    found.index.add(
        [
            ("met:asked", 1, way(form=1, face=1)),  # a drawn face
            ("met:drawn", 1, way(form=1, face=-0.2)),  # another drawing
            ("met:oil", 1, way(form=-1, face=1)),  # the face in oil
        ]
    )
    reads = np.zeros((SIZE, 1), dtype=np.float32)
    form = np.vstack([reads.copy(), [[0.0]], [[1.0]]]).astype(np.float32)
    form[0, 0] = 1.0
    subject = np.vstack([reads, [[0.0]], [[1.0]]]).astype(np.float32)
    found.heads = Heads(form, subject, ["subject:portrait"], 3)
    asked = found.index.vector("met:asked")
    assert asked is not None
    both = found.alike_near(asked, 3)
    alone = found.alike_near(asked, 3, "subject")
    assert [i for i, _ in both] == ["met:asked", "met:drawn", "met:oil"]
    assert [i for i, _ in alone] == ["met:asked", "met:oil", "met:drawn"]
    # The subject layer reads nothing here: the half-and-half levels are
    # half the whole look's.
    assert [s for _, s in alone] == pytest.approx([s / 2 for _, s in both], abs=1e-3)
