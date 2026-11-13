"""Haiku at the catalogue's door and in its night audit, and the
background's questions asked at night (Mateusz 2026-11-10: "wdrażamy: K1,
A1, O1, K4"; A1, Szukaj by a sentence, gave way to Szukaj by how a work
looks on 2026-11-13, ``test_looks``)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from test_ai import FakeAnthropic, _message, fake  # noqa: F401  (fixture)

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU
from frame_server.ai.keywords import KIND as KEYWORDS
from frame_server.library.models import Item, ItemKind, PhotoInfo
from frame_server.library.verdict import Place, against
from frame_server.service import FrameService


def _answer(client: FakeAnthropic, data: dict[str, Any]) -> None:
    """Every question of every batch answered with ``data``."""

    def results(batch_id: str) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                custom_id=r["custom_id"],
                result=SimpleNamespace(type="succeeded", message=_message(data)),
            )
            for r in client.batches[batch_id]
        ]

    client.messages.batches.results = results


def _work(service: FrameService, item_id: str, **fields: Any) -> Item:
    source, _, source_id = item_id.partition(":")
    fields.setdefault("kind", ItemKind.ARTWORK)
    item = Item(
        id=item_id,
        source=source,
        source_id=source_id,
        thumb_url=f"https://example.org/{source_id}.jpg",
        **fields,
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), (120, 90, 60)).save(path, "JPEG")
    return service.library.upsert(item)


NOTHING = {
    "why": "A landscape painting",
    "postal": False,
    "text": False,
    "room": False,
    "grey_copy": False,
    "not_art": False,
    "confidence": 0.9,
}
STAMP = {**NOTHING, "why": "A postage stamp with a still life", "postal": True}


# -- K1: the gatekeeper ----------------------------------------------------------------


def test_only_gathering_sources_are_asked_the_owners_first(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "met:1", title="Museum's own")
    _work(service, "europeana:2", title="Martwa natura", pooled=True)
    _work(service, "wmc:3", title="Kept", pooled=False)
    _work(service, "europeana:4", title="Znaczek", classification="stamp", pooled=True)
    asked = [i.id for i in service.gatekeeper.candidates({})]
    assert asked == ["wmc:3", "europeana:2"]  # the rules' stamp is out already


def test_the_critic_confirms_before_a_picture_is_set_aside(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "europeana:2", title="Martwa natura", pooled=True)
    keeper = service.gatekeeper
    assert keeper.collect() is None
    assert keeper.order()
    assert not keeper.order()  # one batch at a time
    asked = fake.batches["batch_1"]
    assert len(asked) == 1 and asked[0]["params"]["model"] == HAIKU
    assert '"postal"' in asked[0]["params"]["system"][0]["text"]
    assert keeper.collect() is False

    fake.ended = True
    _answer(fake, STAMP)
    assert keeper.collect() is True
    assert keeper.state()["claims"]["europeana:2"]["seen_as"] == "postal"
    item = service.library.get("europeana:2")
    assert item is not None and not item.seen_as  # not before the critic

    assert keeper.order()
    critic = fake.batches["batch_2"][0]["params"]
    assert "evidence against the claim" in critic["system"][0]["text"]
    assert "postage stamp" in str(critic["messages"])
    _answer(fake, {"why": "Perforated edges", "verdict": "confirm", "confidence": 0.9})
    assert keeper.collect() is True
    item = service.library.get("europeana:2")
    assert item is not None and item.seen_as == "postal" and against(item, Place.SOUGHT)
    (written,) = keeper.written()
    assert written["id"] == "europeana:2" and written["seen_as"] == "postal"
    assert not keeper.order()  # nothing left
    assert service.claude.spending.by_kind()["gatekeeper"] > 0


def test_a_rejected_claim_and_an_artwork_change_nothing(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "wmc:1", pooled=True)
    _work(service, "wmc:2", pooled=True)
    keeper = service.gatekeeper
    fake.ended = True

    def results(batch_id: str) -> list[SimpleNamespace]:
        data = {"w0": STAMP, "w1": NOTHING}
        return [
            SimpleNamespace(
                custom_id=r["custom_id"],
                result=SimpleNamespace(
                    type="succeeded",
                    message=_message(
                        data.get(r["custom_id"], NOTHING)
                        if batch_id == "batch_1"
                        else {"why": "A painting", "verdict": "reject", "confidence": 0.7}
                    ),
                ),
            )
            for r in fake.batches[batch_id]
        ]

    fake.messages.batches.results = results
    assert keeper.order() and keeper.collect()
    assert len(keeper.state()["claims"]) == 1
    assert keeper.order() and keeper.collect()
    for item_id in ("wmc:1", "wmc:2"):
        item = service.library.get(item_id)
        assert item is not None and not item.seen_as and not against(item, Place.SOUGHT)
    assert keeper.written() == []
    assert not keeper.order()  # both asked, neither again


def test_the_owner_brings_a_work_back_for_good(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "wmc:1", pooled=True)
    service.library.update("wmc:1", seen_as="text")
    service.gatekeeper.state()  # nothing else known
    assert service.gatekeeper.bring_back("wmc:1")
    item = service.library.get("wmc:1")
    assert item is not None and not item.seen_as and not against(item, Place.SOUGHT)
    assert service.gatekeeper.candidates({}) == []  # never asked again


def test_a_reimported_work_keeps_what_was_seen(service: FrameService) -> None:
    item = _work(service, "wmc:1", pooled=True, image_url="https://example.org/1.jpg")
    service.library.update("wmc:1", seen_as="room")
    service.library.upsert(item.model_copy(update={"title": "Again"}))
    again = service.library.get("wmc:1")
    assert again is not None and again.seen_as == "room"


def test_the_switch_and_no_key_ask_nothing(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "wmc:1", pooled=True)
    service.ai_config.update(AiConfigUpdate(gatekeeper=False, audit=False))
    assert not service.gatekeeper.order() and not service.audit.order()
    service.ai_config.update(AiConfigUpdate(gatekeeper=True, audit=True))
    service.ai_config.set_key(None)
    assert not service.gatekeeper.order() and not service.audit.order()
    assert fake.batches == {}


# -- K4: the night audit -----------------------------------------------------------------


def test_the_audit_lists_only_what_the_critic_keeps(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "met:1", title="Portrait of a Man", artist="Rembrandt", year=1900)
    audit = service.audit
    fake.ended = True
    _answer(
        fake,
        {
            "why": "A landscape with a river",
            "title_fits": False,
            "date_fits": False,
            "polish_fits": True,
            "picture_fits": True,
            "problems": [
                {"field": "title", "problem": "Tytuł mówi o portrecie, a to pejzaż"},
                {"field": "date", "problem": "Rembrandt nie żył w 1900"},
            ],
            "confidence": 0.8,
        },
    )
    assert audit.order() and audit.collect()
    assert len(audit.state()["claims"]["met:1"]["problems"]) == 2
    assert audit.order()
    critic = fake.batches["batch_2"][0]["params"]
    assert "1. Tytuł" in str(critic["messages"]) and "2. Data" in str(critic["messages"])
    _answer(fake, {"why": "The date is real", "real": [2], "confidence": 0.8})
    assert audit.collect()
    (finding,) = audit.written()
    assert finding["id"] == "met:1"
    assert finding["problems"] == [{"field": "date", "problem": "Rembrandt nie żył w 1900"}]
    item = service.library.get("met:1")
    assert item is not None and item.title == "Portrait of a Man"  # nothing changed


def test_the_review_list_in_the_app(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    app.state.service = service
    _work(service, "wmc:1", title="Bekendmaking", pooled=True)
    service.library.update("wmc:1", seen_as="text")
    state = service.gatekeeper.state()
    state["written"] = [{"id": "wmc:1", "at": "2026-11-10T02:00:00+00:00", "seen_as": "text"}]
    service.gatekeeper._save(state)
    with TestClient(app) as client:
        review = client.get("/api/ai/review").json()
        (entry,) = review["set_aside"]
        assert entry["item"]["id"] == "wmc:1"
        assert entry["seen_as_name"] == "Strona z tekstem albo dokument"
        assert client.get("/api/ai").json()["review_count"] == 1
        after = client.post("/api/ai/review/wmc:1/bring-back").json()
        assert after["set_aside"] == []
    item = service.library.get("wmc:1")
    assert item is not None and not item.seen_as


# -- O1: the background's questions at night ---------------------------------------------------


def test_keywords_nobody_waits_for_go_at_night_for_half_the_price(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _work(service, "met:kept")
    _work(service, "icloud:1", kind=ItemKind.PHOTO, photo=PhotoInfo(caption="Zakopane"))
    assert service.ai.progress(KEYWORDS).waiting == 2
    assert service.ai.sweep() == 0  # not one at a time by day
    assert service.ai.order_night() == 2
    (requests,) = fake.batches.values()
    assert len(requests) == 2
    assert service.ai.order_night() == 0  # already in a batch
    fake.ended = True
    assert service.ai.poll_batches() == 2
    assert service.ai.progress(KEYWORDS).waiting == 0
    assert fake.asked == []  # nothing asked at full price


def test_a_batch_ordered_ahead_is_collected_when_the_turn_comes(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    """The night orders the gatekeeper's batch before the pictures are
    looked at (40 minutes) and puts the answers in afterwards, without
    another wait: then the critic, in the same night."""
    import threading
    import time

    from frame_server.night import Night

    _work(service, "europeana:2", title="Martwa natura", pooled=True)
    keeper = service.gatekeeper
    keeper.ahead()
    assert list(fake.batches) == ["batch_1"]
    keeper.ahead()  # again: one batch at a time
    assert list(fake.batches) == ["batch_1"]

    # Meanwhile the batch ended.
    fake.ended = True
    _answer(fake, STAMP)
    slept: list[float] = []

    class Quick(Night):
        def quiet(self) -> bool:
            return True

        def sleep(self, seconds: float) -> bool:
            slept.append(seconds)
            _answer(fake, {"why": "Perforated edges", "verdict": "confirm", "confidence": 0.9})
            return True

    keeper.at_night(Quick(threading.Event(), time.monotonic() + 600))
    item = service.library.get("europeana:2")
    assert item is not None and item.seen_as == "postal"
    assert len(slept) == 1  # waited for the critic only
    assert keeper.tally["claims"] == 1 and keeper.tally["written"] == 1


def test_the_judge_is_not_asked_about_what_the_gatekeeper_set_aside(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
    monkeypatch: Any,
) -> None:
    _work(service, "openverse:1", title="Symbol", artist="A")
    _work(service, "openverse:2", title="Symbol, bold", artist="A")
    _work(service, "wmc:3", title="Pejzaż", artist="B")
    _work(service, "wikiart:4", title="Landscape", artist="B")
    suspects = {"openverse:1|openverse:2": {"why": "hash"}, "wikiart:4|wmc:3": {"why": "fit"}}
    service.library.set_state("twins_suspects", suspects)
    assert len(service.twins_judge._pairs({})) == 2
    service.library.update("openverse:2", seen_as="not_art")
    assert [key for key, *_ in service.twins_judge._pairs({})] == ["wikiart:4|wmc:3"]
    assert list(service.twins.suspects()) == ["wikiart:4|wmc:3"]  # forgotten for good
