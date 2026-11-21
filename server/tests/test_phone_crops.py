"""Museum photographs cut by the phone's own model, with no Claude
(Mateusz 2026-11-20: „Celem jest całkowite uniknięcie Opus”, „Gdy model
brak pewności — po prostu zostawmy do ręcznego kadrowania”, „Musi szukać
prostokątów prawie na wprost”): what the model's answer comes to
(``imaging/crop_model``), what the server does with what the phone found
(``phone_crops``), and the owner's list "Kadrowane"."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from fastapi.testclient import TestClient
from test_ai import FakeAnthropic, fake  # noqa: F401  (fixture)
from test_crops import TRUE, H, W, _work, photo

from frame_server.imaging import crop_model as cm
from frame_server.service import FrameService


def _logits(
    work: list[tuple[float, float]], frame: list[tuple[float, float]] | None, size: tuple[int, int]
) -> np.ndarray:
    """The masks a model sure of ``work`` (and ``frame`` around it) would give."""
    w, h = size
    _, (ox, oy, nw, nh) = cm.letterbox(np.zeros((h, w, 3), np.uint8))
    out = np.full((2, cm.SIDE, cm.SIDE), -8.0, np.float32)
    for c, quad in enumerate((work, frame)):
        if quad is None:
            continue
        m = np.zeros((cm.SIDE, cm.SIDE), np.float32)
        q = np.array(quad) * [nw, nh] + [ox, oy]
        cv2.fillPoly(m, [np.round(q * 16).astype(np.int32)], 1.0, cv2.LINE_AA, 4)
        out[c] = (m - 0.5) * 16
    return out


#: The corners as kept (``cut.valid``: five places).
KEPT = [[round(x, 5), round(y, 5)] for x, y in TRUE]
FRAMED = [(150 / W, 100 / H), (750 / W, 100 / H), (750 / W, 600 / H), (150 / W, 600 / H)]


def test_a_sure_upright_work_is_cut_an_unsure_or_turned_one_left_to_him() -> None:
    rgb = np.asarray(photo())
    logits = _logits(TRUE, FRAMED, (W, H))
    found = cm.find(rgb, logits, 0.97)
    assert found.verdict == "cut" and found.work is not None and found.surround is not None
    assert (
        max(
            abs(a - b)
            for p, q in zip(found.work, TRUE, strict=True)
            for a, b in zip(p, q, strict=True)
        )
        < 0.004
    )
    assert cm.find(rgb, logits, 0.5).verdict == "unsure"  # not sure enough: his
    assert cm.find(rgb, logits, 0.05).verdict == "whole"  # sure it wants none
    # A work photographed at an angle („bardzo pod kątem”): his, however sure.
    turned = [(0.2, 0.2), (0.8, 0.14), (0.8, 0.86), (0.2, 0.8)]
    assert cm.upright_off(turned, (W, H)) > cm.UPRIGHT
    assert cm.decide(0.99, turned, (W, H)) == "unsure"
    assert cm.decide(0.99, TRUE, (W, H)) == "cut"
    # Nothing in the masks: nothing to cut to.
    empty = np.full((2, cm.SIDE, cm.SIDE), -8.0, np.float32)
    assert cm.find(rgb, empty, 0.99) == cm.Found("unsure", None, None, 0.99)


def test_the_kind_comes_from_the_museums_words() -> None:
    assert cm.KINDS[cm.kind_of("Painting", "Oil on canvas")] == "painting"
    assert cm.KINDS[cm.kind_of("Prints", "Etching on paper")] == "print"
    assert cm.KINDS[cm.kind_of("", "Akwarela, papier")] == "drawing"
    assert cm.KINDS[cm.kind_of("Photograph", "Albumen print")] == "print"  # as trained
    assert cm.KINDS[cm.kind_of("Photographs", "Gelatin silver")] == "photo"
    assert cm.KINDS[cm.kind_of(None, None)] == "other"


def _client(service: FrameService) -> TestClient:
    from frame_server.web import create_app

    app = create_app(service.settings)
    app.state.service = service
    return TestClient(app)


def _found(item_id: str, client: TestClient, **given: Any) -> dict[str, Any]:
    ask = client.get(f"/api/crops/phone/{item_id}").json()
    body = {
        "model": ask["model"],
        "picture": ask["picture"],
        "verdict": "cut",
        "sure": 0.96,
        "work": TRUE,
        "surround": FRAMED,
        "width": 1024,
        "height": round(1024 * H / W),
        **given,
    }
    answer = client.post(f"/api/crops/phone/{item_id}", json=body)
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_the_phone_cuts_and_claude_is_asked_nothing(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    for n in range(1, 5):
        _work(service, f"mnw:{n}", pooled=True, medium="olej, płótno")
    _work(service, "upload:9", pooled=True)
    assert service.crops.on_phone()
    with _client(service) as client:
        # The card opened: the server asks nobody, the phone is to look.
        seen = client.post("/api/library/items/mnw:1/cut/check?wait=5").json()
        assert not seen["changed"]
        ask = client.get("/api/crops/phone/mnw:1").json()
        # A painting: its own model since 2026-11-21 („Tak, wymień dla malarstwa”).
        assert ask["look"] and ask["kind"] == 0 and ask["model"] == cm.PAINTING_MODEL
        assert cm.model_of(1) == cm.model_of(2) == cm.MODEL
        waiting = client.get("/api/crops/phone/waiting?limit=2").json()
        assert waiting["left"] == 4 and len(waiting["works"]) == 2

        cut = _found("mnw:1", client)
        assert cut["cut"] and cut["item"]["cut"]["by"] == "auto"
        assert cut["item"]["cut"]["work"] == KEPT
        assert cut["item"]["cut"]["framed_kind"] == "frame"  # "W ramie"
        assert not client.get("/api/crops/phone/mnw:1").json()["look"]  # looked at
        # Not sure: left whole, for him.
        assert _found("mnw:2", client, verdict="unsure", sure=0.6)["verdict"] == "unsure"
        # Sure it wants no cut.
        whole = _found("mnw:3", client, verdict="whole", sure=0.03, work=None, surround=None)
        assert not whole["cut"] and whole["item"]["cut"]["work"] is None
        # Looked at in another photograph (a copy took its place): nothing.
        other = _found("mnw:4", client, width=700, height=1000)
        assert other["verdict"] == "" and client.get("/api/crops/phone/mnw:4").json()["look"]
        assert client.get("/api/crops/phone/waiting").json()["left"] == 1

        review = client.get("/api/crops/review").json()
        assert [i["id"] for i in review["cut"]] == ["mnw:1"]
        assert [i["id"] for i in review["unsure"]] == ["mnw:2"]
        # He cuts the unsure one himself, and says the model's cut is right.
        mine = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
        assert client.put("/api/library/items/mnw:2/cut", json={"corners": mine}).status_code == 200
        after = client.post("/api/crops/review/mnw:1/fine").json()
        # His own cut stays on the list until he approves it.
        assert [i["id"] for i in after["cut"]] == ["mnw:2"] and after["unsure"] == []
        after = client.post("/api/crops/review/mnw:2/fine").json()
        assert after["cut"] == [] and after["unsure"] == []
        assert client.post("/api/crops/review/mnw:3/fine").status_code == 409
        lessons = {lesson["id"]: lesson for lesson in client.get("/api/crops/lessons").json()}
        assert set(lessons) == {"mnw:1", "mnw:2"}
        assert lessons["mnw:1"]["fine"] and lessons["mnw:1"]["work"] == KEPT
        assert not lessons["mnw:2"]["fine"] and lessons["mnw:2"]["work"] == mine
        assert lessons["mnw:2"]["model"]["v"] == "unsure"
        # His own works are not the phone's.
        assert not client.get("/api/crops/phone/upload:9").json()["look"]
    assert not service.crops.order()
    assert service.crops.waiting_claims() == 0 and service.crops.claims_waiting() == []
    assert fake.batches == {} and fake.asked == []


def test_a_frame_not_around_all_of_the_work_is_no_frame(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # Chełmoński (Mateusz 2026-11-20, „dzieło wystaje za ramę”): the dark
    # board behind a sheet found as its frame, the sheet's corner past it.
    short = [(0.13, 0.11), (0.86, 0.11), (0.84, 0.86), (0.13, 0.89)]
    sheet = [(0.2, 0.2), (0.85, 0.2), (0.85, 0.87), (0.2, 0.87)]
    assert cm.holds(FRAMED, TRUE) and not cm.holds(short, sheet)
    rgb = np.asarray(photo())
    board = [(0.1, 0.1), (0.7, 0.1), (0.7, 0.9), (0.1, 0.9)]
    found = cm.find(rgb, _logits(TRUE, board, (W, H)), 0.97)
    assert found.verdict == "cut" and found.surround is None
    _work(service, "mnw:1", pooled=True, medium="ołówek, papier")
    with _client(service) as client:
        cut = _found("mnw:1", client, surround=[[0.1, 0.1], [0.7, 0.1], [0.7, 0.9], [0.1, 0.9]])
        assert cut["cut"] and cut["item"]["cut"]["surround"] is None
        assert cut["item"]["cut"]["framed_kind"] == ""


def test_bez_ramy_throws_what_is_around_the_work_away(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # Mateusz 2026-11-20: „kadrujemy dzieło, ale nie ma ono ramy ani
    # passepartout. Czyli tło jest do wyrzucenia.” (A painting: a drawing
    # gets no frame from the model at all since 2026-11-21.)
    _work(service, "mnw:1", pooled=True, medium="olej, płótno")
    with _client(service) as client:
        cut = _found("mnw:1", client)
        assert cut["item"]["cut"]["framed_kind"] == "frame"
        bare = client.put("/api/library/items/mnw:1/cut", json={"no_frame": True})
        assert bare.status_code == 200, bare.text
        kept = bare.json()["cut"]
        assert kept["surround"] is None and kept["framed_kind"] == "" and kept["work"] == KEPT
        assert kept["surround_by"] == "owner"
        # Still the model's cut on "Kadrowane", said fine without a frame.
        assert [i["id"] for i in client.get("/api/crops/review").json()["cut"]] == ["mnw:1"]
        after = client.post("/api/crops/review/mnw:1/fine").json()
        assert after["cut"] == [] and after["unsure"] == []
        (lesson,) = client.get("/api/crops/lessons").json()
        assert lesson["fine"] and lesson["surround"] is None


def test_a_work_left_whole_is_kept_whole_and_the_list_says_how_sure(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    for n in (1, 2):
        _work(service, f"mnw:{n}", pooled=True, medium="olej, płótno")
    with _client(service) as client:
        _found("mnw:1", client)
        _found("mnw:2", client, verdict="unsure", sure=0.6)
        review = client.get("/api/crops/review").json()
        assert {s["id"]: s["sure"] for s in review["sure"]} == {"mnw:1": 0.96, "mnw:2": 0.6}
        # "Bez kadru": whole is right.
        assert client.post("/api/crops/review/mnw:2/fine").status_code == 200
        (lesson,) = client.get("/api/crops/lessons").json()
        assert lesson["id"] == "mnw:2" and lesson["fine"]
        assert lesson["work"] is None and lesson["surround"] is None


def test_a_print_or_drawing_is_cut_to_its_sheet_with_no_frame(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # Mateusz 2026-11-20 22:13 UTC: „Rysunki jak dziś, grafiki do papieru”;
    # 2026-11-21 17:48: „Dla rysunku i grafiki zostawimy tylko jedno
    # kadrowanie - »do kartki«”.
    _work(service, "mnw:1", pooled=True, medium="akwaforta, papier")
    _work(service, "mnw:2", pooled=True, medium="ołówek, papier")
    _work(service, "mnw:3", pooled=True, medium="olej, płótno")
    with _client(service) as client:
        for sheet in ("mnw:1", "mnw:2"):
            cut = _found(sheet, client)
            assert cut["cut"] and cut["item"]["cut"]["work"] == KEPT
            assert cut["item"]["cut"]["surround"] is None
        assert _found("mnw:3", client)["item"]["cut"]["framed_kind"] == "frame"


def test_he_tells_at_a_glance_whether_a_painting_wants_a_cut_and_a_frame(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    # Mateusz 2026-11-21: „ekran gdzie dam mu dane startowe”, one kind at a time.
    _work(service, "mnw:1", pooled=True, medium="olej, płótno")
    _work(service, "mnw:2", pooled=True, medium="olej, płótno")
    _work(service, "mnw:3", pooled=True, medium="akwaforta, papier")
    with _client(service) as client:
        shown = client.get("/api/crops/teach").json()
        assert sorted(w["id"] for w in shown["works"]) == ["mnw:1", "mnw:2"] and shown["told"] == 0
        told = client.post("/api/crops/teach/mnw:1", json={"answer": "framed"}).json()
        assert told["told"] == 1
        assert [w["id"] for w in client.get("/api/crops/teach").json()["works"]] == ["mnw:2"]
        assert client.post("/api/crops/teach/mnw:2", json={"answer": "nope"}).status_code == 422
        client.post("/api/crops/teach/mnw:2", json={"answer": "whole"})
        assert client.delete("/api/crops/teach/mnw:2").json()["told"] == 1
        (lesson,) = client.get("/api/crops/told").json()
        assert lesson["id"] == "mnw:1" and lesson["told"] == "framed" and lesson["kind"] == 0
        prints = client.get("/api/crops/teach", params={"kind": 2}).json()["works"]
        assert [w["id"] for w in prints] == ["mnw:3"]
        # A drawing or print is cut to its sheet (17:48: „tylko jedno
        # kadrowanie - »do kartki«”): "framed" of one is taught as a cut.
        client.post("/api/crops/teach/mnw:3", json={"answer": "framed"})
        told_of = {t["id"]: t["told"] for t in client.get("/api/crops/told").json()}
        assert told_of == {"mnw:1": "framed", "mnw:3": "cut"}
