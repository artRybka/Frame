"""The judge of copies at night (frame_server.ai.twins_judge.NightJudge):
what the pictures could not settle, Haiku and Haiku as the critic (Mateusz
2026-11-10 13:48)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from test_ai import FakeAnthropic, _message, fake  # noqa: F401  (fixture)
from test_sharper import _print
from test_twins import _work

from frame_server.ai import AiConfigUpdate
from frame_server.ai.client import HAIKU
from frame_server.ai.twins_judge import STATE_KEY, NightJudge
from frame_server.library.twins import pair_key
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


def _strip(service: FrameService) -> str:
    """A painting and a strip of it, both from Commons: neither surely the
    whole, so the pictures leave the pair to the judge."""
    painting = _print(11, (600, 700))
    _work(service, "wmc:1", painting, title="Kobieta czytająca list")
    _work(service, "wmc:2", painting.crop((150, 0, 400, 700)), title="Czytająca")
    service.twins.look()
    return pair_key("wmc:1", "wmc:2")


def test_what_the_pictures_cannot_settle_is_left_to_the_judge(service: FrameService) -> None:
    key = _strip(service)
    assert key in service.twins.suspects()
    for item_id in ("wmc:1", "wmc:2"):
        item = service.library.get(item_id)
        assert item is not None and not item.detail_of and not item.copy_of
    service.twins.drop_suspects([key])
    assert key not in service.twins.suspects()


def test_the_critic_confirms_before_a_picture_is_hidden(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    key = _strip(service)
    judge: NightJudge = service.twins_judge
    assert judge.collect() is None  # nothing ordered yet

    assert judge.order()
    assert not judge.order()  # one batch at a time
    asked = next(iter(fake.batches.values()))
    assert len(asked) == 1 and asked[0]["params"]["model"] == HAIKU
    assert "Picture A" in str(asked[0]["params"]["messages"])
    assert judge.collect() is False  # still running

    fake.ended = True
    _answer(fake, {"why": "B is a strip of A", "kind": "part", "whole": "A", "confidence": 0.9})
    assert judge.collect() is True
    assert judge.state()["claims"] == {key: "b_detail_of_a"}
    strip = service.library.get("wmc:2")
    assert strip is not None and not strip.detail_of  # not before the critic

    assert judge.order()  # the critic's question
    critic = fake.batches["batch_2"][0]["params"]
    assert critic["model"] == HAIKU
    assert "B lies within A" in str(critic["messages"])
    assert "evidence against the claim" in critic["system"][0]["text"]
    _answer(fake, {"why": "Figures match", "verdict": "confirm", "confidence": 0.9})
    assert judge.collect() is True
    strip = service.library.get("wmc:2")
    assert strip is not None and strip.detail_of == "wmc:1"
    judged = judge.state()["judged"][key]
    assert judged["critic"] == "confirm" and judged["written"] is True
    assert key not in service.twins.suspects()
    assert not judge.order()  # nothing left
    assert service.claude.spending.by_kind()["twins.judge"] > 0


def test_a_claim_the_critic_rejects_changes_nothing(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    key = _strip(service)
    judge: NightJudge = service.twins_judge
    fake.ended = True
    _answer(fake, {"why": "one painting", "kind": "same", "whole": "none", "confidence": 0.8})
    assert judge.order() and judge.collect()
    _answer(fake, {"why": "B is a fragment of its own", "verdict": "reject", "confidence": 0.8})
    assert judge.order() and judge.collect()
    for item_id in ("wmc:1", "wmc:2"):
        item = service.library.get(item_id)
        assert item is not None and not item.detail_of and not item.copy_of
    assert judge.state()["judged"][key]["critic"] == "reject"
    assert key not in service.twins.suspects()


def test_two_works_kept_apart_are_never_asked_again(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    key = _strip(service)
    judge: NightJudge = service.twins_judge
    fake.ended = True
    _answer(fake, {"why": "two works", "kind": "different", "whole": "none", "confidence": 0.9})
    assert judge.order() and judge.collect()
    assert judge.state()["judged"][key]["judge"] == "different"
    assert not judge.state().get("claims")
    assert not judge.order()
    assert len(fake.batches) == 1


def test_the_switch_and_no_key_ask_nothing(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811
) -> None:
    _strip(service)
    service.ai_config.update(AiConfigUpdate(twins_judge=False))
    assert not service.twins_judge.order()
    service.ai_config.update(AiConfigUpdate(twins_judge=True))
    service.ai_config.set_key(None)
    assert not service.twins_judge.order()
    assert fake.batches == {}
    assert service.library.get_state(STATE_KEY) is None


def test_the_judge_never_hides_a_museums_work(service: FrameService) -> None:
    painting = _print(12, (600, 700))
    _work(service, "met:1", painting, title="A")
    _work(service, "rijks:2", painting, title="B", artist="Gerard ter Borch")
    _work(service, "wmc:3", painting.crop((100, 0, 400, 700)), title="C", artist="Unknown")
    twins = service.twins
    assert not twins.apply("met:1", "rijks:2", "same")  # two museums' works
    assert not twins.apply("wmc:3", "met:1", "b_detail_of_a")  # a museum's work set aside
    assert not twins.apply("met:1", "wmc:3", "different")
    assert twins.apply("wmc:3", "met:1", "a_detail_of_b")  # wmc:3 is the part
    part = service.library.get("wmc:3")
    assert part is not None and part.detail_of == "met:1"
    for item_id in ("met:1", "rijks:2"):
        item = service.library.get(item_id)
        assert item is not None and not item.detail_of and not item.copy_of
