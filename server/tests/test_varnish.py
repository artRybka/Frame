"""A blue under yellowed varnish: found by the colours, named by Haiku
(frame_server.library.colors.varnished_blue, frame_server.ai.varnish)."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image
from test_ai import FakeAnthropic, fake  # noqa: F401 - the fixture

from frame_server.ai import AiConfigUpdate
from frame_server.ai.varnish import KIND, pictures
from frame_server.library import Item, ItemKind
from frame_server.library.colors import SCORE_VERSION, analyse, with_blue
from frame_server.player import SCORE_KEY
from frame_server.service import FrameService

SKY = (110, 140, 130)  # a sky under yellowed varnish: teal, blue without the cast
LEAVES = (90, 130, 90)  # real green


def _painting(top: tuple[int, int, int]) -> Image.Image:
    """An ochre landscape with brown earth, a red robe and ``top`` above."""
    pixels = np.zeros((200, 160, 3), np.uint8)
    pixels[:] = (150, 110, 60)
    pixels[120:] = (95, 70, 40)
    pixels[140:170, 30:60] = (170, 40, 35)
    pixels[:50] = top
    return Image.fromarray(pixels)


def test_a_green_that_may_be_a_sky_under_varnish_is_a_question_only() -> None:
    sky = analyse(_painting(SKY))
    assert sky.varnish >= 0.2
    # Not found by any blue until Haiku has seen it.
    assert not {"blue", "accent:blue"} & set(sky.tags)
    assert analyse(_painting(LEAVES)).varnish == 0
    # The marked picture keeps the area's colour and dims the rest.
    whole, marked = pictures(_painting(SKY))
    assert marked.size == whole.size
    assert marked.getpixel((10, 5)) == whole.getpixel((10, 5))
    assert sum(marked.getpixel((10, whole.size[1] - 5))) < sum(whole.getpixel((10, 5)))


def test_the_blue_goes_after_the_other_colours() -> None:
    tags = ["green", "accent:red", "warm", "tone:warm"]
    assert with_blue(tags) == ["green", "accent:red", "accent:blue", "warm", "tone:warm"]
    assert with_blue(["teal", "blue"]) == ["teal", "blue"]


def _add(service: FrameService, item_id: str, top: tuple[int, int, int]) -> Item:
    item = service.library.upsert(
        Item(id=item_id, source="met", source_id=item_id, kind=ItemKind.ARTWORK, title="Landscape")
    )
    path = service.images.thumb_path(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = io.BytesIO()
    _painting(top).save(out, "PNG")
    path.write_bytes(out.getvalue())
    return service.importer.measure_again(item)


def test_the_blue_haiku_names_is_the_works_accent_and_stays(
    service: FrameService,
    fake: FakeAnthropic,  # noqa: F811 - the fixture
) -> None:
    sky = _add(service, "met:1", SKY)
    leaves = _add(service, "met:2", LEAVES)
    job = service.ai.jobs[KIND]
    assert job.wanted(sky) and not job.wanted(leaves)

    fake.answer = {"area": "sky above the hills", "painted": "blue"}
    assert service.ai.run_one(KIND, "met:1") is not None
    content = fake.asked[-1]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image", "image", "text"]
    assert "accent:blue" in service.library.get("met:1").color_tags  # type: ignore[union-attr]

    # Kept when the colours are measured again, and through the rescore.
    again = service.importer.measure_again(service.library.get("met:1"))  # type: ignore[arg-type]
    assert "accent:blue" in again.color_tags
    service.library.set_state(SCORE_KEY, SCORE_VERSION - 1)
    service.player.rescore()
    assert "accent:blue" in service.library.get("met:1").color_tags  # type: ignore[union-attr]


def test_a_green_haiku_sees_stays_green(service: FrameService, fake: FakeAnthropic) -> None:  # noqa: F811
    _add(service, "met:1", SKY)
    fake.answer = {"area": "robe of the saint", "painted": "green"}
    assert service.ai.run_one(KIND, "met:1") is not None
    assert "accent:blue" not in service.library.get("met:1").color_tags  # type: ignore[union-attr]
    # Asked once: the note holds until the picture changes.
    assert not service.ai._stale(service.ai.jobs[KIND], service.ai.jobs[KIND].wanted)


def test_the_owner_can_switch_it_off(service: FrameService, fake: FakeAnthropic) -> None:  # noqa: F811
    _add(service, "met:1", SKY)
    service.ai_config.update(AiConfigUpdate(varnish_blue=False))
    assert service.ai.run_one(KIND, "met:1") is None
    assert not fake.asked
