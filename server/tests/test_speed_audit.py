"""What the audit of 2026-11-14 made quicker answers as before: what is
worked out of a work once (its reasons, its texts without accents), the
language model's settings and counts kept while unchanged, a kept thumbnail
read in one go."""

from __future__ import annotations

import gc
import io
from pathlib import Path
from typing import Any

from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.ai import AiConfigUpdate
from frame_server.ai.config import STATE_KEY
from frame_server.ai.keywords import KIND
from frame_server.config import Settings
from frame_server.library import Item, ItemKind, Look, PlaylistRules
from frame_server.library.memo import PerItem
from frame_server.library.models import Note
from frame_server.library.search_index import folded_fields, folded_text
from frame_server.library.verdict import Why, whys
from frame_server.service import FrameService
from frame_server.web import create_app


def _work(item_id: str = "met:1", **kw: Any) -> Item:
    kw.setdefault("kind", ItemKind.ARTWORK)
    return Item(id=item_id, source=item_id.split(":")[0], source_id=item_id, **kw)


# -- worked out once of each record ------------------------------------------


def test_a_record_is_worked_on_once_and_its_copy_anew() -> None:
    asked: list[str] = []

    def title(item: Item) -> str:
        asked.append(item.title)
        return item.title.upper()

    memo = PerItem(title)
    work = _work(title="Żółw")
    assert memo(work) == "ŻÓŁW" and memo(work) == "ŻÓŁW"
    assert asked == ["Żółw"]
    # The library never changes a record where it stands: it puts a copy in
    # its place, and that one is asked anew.
    other = work.model_copy(update={"title": "Bocian"})
    assert memo(other) == "BOCIAN" and memo(work) == "ŻÓŁW"
    assert asked == ["Żółw", "Bocian"]


def test_a_record_changed_where_it_stands_is_asked_again() -> None:
    work = _work(title="Żółw", artist="Józef Chełmoński")
    assert whys(work) == () and folded_text(work).startswith("zolw jozef chelmonski")
    assert folded_fields(work)[:2] == ("jozef chelmonski", "zolw")
    work.title = "Postage stamp"
    work.classification = "Stamps"
    assert whys(work) == (Why.POSTAL,)
    assert folded_text(work).startswith("postage stamp") and folded_fields(work)[1] == (
        "postage stamp"
    )


def test_nothing_is_kept_of_a_record_let_go() -> None:
    memo = PerItem(lambda item: item.title)
    work = _work(title="Żółw")
    memo(work)
    assert len(memo) == 1
    del work
    gc.collect()
    assert len(memo) == 0


def test_the_library_answers_by_the_record_it_holds_now(service: FrameService) -> None:
    library = service.library
    library.upsert(_work(title="Bociany", artist="Józef Chełmoński"))
    assert library.query(PlaylistRules(query="bociany"))[0] == 1
    library.update("met:1", title="Żurawie")
    assert library.query(PlaylistRules(query="bociany"))[0] == 0
    assert library.query(PlaylistRules(query="zurawie"))[0] == 1
    library.update("met:1", classification="Sculpture")
    held = library.get("met:1")
    assert held is not None and whys(held) == (Why.SCULPTURE,)


# -- the language model's settings and counts --------------------------------


def test_the_settings_are_read_again_only_when_saved_anew(service: FrameService) -> None:
    store = service.ai_config
    first = store.config
    assert store.config is first
    store.update(AiConfigUpdate(monthly_limit_usd=7))
    assert store.config is not first and store.config.monthly_limit_usd == 7
    # Written past the store (a restored backup): read as it is saved.
    saved = store.config.model_dump() | {"monthly_limit_usd": 9}
    service.library.set_state(STATE_KEY, saved)
    assert store.config.monthly_limit_usd == 9


def test_the_count_is_kept_until_a_work_a_note_or_the_settings_change(
    service: FrameService,
) -> None:
    library, worker = service.library, service.ai
    service.ai_config.set_key("sk-ant-test-0000abcd")
    job = worker.jobs[KIND]
    looked: list[str] = []
    wanted = job.wanted

    def counted(item: Item) -> bool:
        looked.append(item.id)
        return wanted(item)

    job.wanted = counted  # type: ignore[method-assign]
    library.upsert(_work("met:1", title="Bociany"))
    library.upsert(_work("met:2", title="Żurawie", pooled=True))
    assert worker.progress(KIND).waiting == 1 and sorted(looked) == ["met:1", "met:2"]
    assert worker.progress(KIND).waiting == 1 and len(looked) == 2  # kept

    library.update("met:2", show_count=1)  # a pooled work once shown is the owner's
    assert worker.progress(KIND).waiting == 2 and len(looked) == 4

    held = library.get("met:1")
    assert held is not None
    library.save_note(
        Note(
            item_id="met:1",
            kind=KIND,
            model="m",
            prompt_version=job.prompt_version,
            source_hash=job.source_hash(held),
            data={"refused": True},
        )
    )
    progress = worker.progress(KIND)
    assert (progress.done, progress.waiting, progress.refused) == (1, 1, 1)

    service.ai_config.update(AiConfigUpdate(keywords_artworks=False))
    progress = worker.progress(KIND)
    assert (progress.done, progress.waiting) == (1, 0)


def test_a_photo_sent_once_is_counted_each_time(service: FrameService) -> None:
    """Whether it waits follows from "Historia przesłanych", which changes
    none of what the kept count is made of."""
    service.ai_config.set_key("sk-ant-test-0000abcd")
    sent = service.library.upsert(_work("own:1", kind=ItemKind.PHOTO, look=Look()))
    assert service.ai.progress(KIND).waiting == 0
    service.player.remember_sent(sent)
    assert service.ai.progress(KIND).waiting == 1


# -- a kept thumbnail ---------------------------------------------------------


def test_a_kept_thumbnail_is_read_whole_and_a_missing_one_is_none(service: FrameService) -> None:
    images = service.images
    work = _work("met:1")
    assert images.thumb_bytes(work.id) is None and images.thumb_bytes(work.id, tile=True) is None
    path = images.thumb_path(work)
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = jpeg_bytes((90, 120, 200), (640, 480))
    path.write_bytes(kept)
    assert images.thumb_bytes(work.id) == kept
    tile = images.thumb_bytes(work.id, tile=True)
    assert tile is not None and tile == images.tile(path).read_bytes()
    assert images.thumb_bytes("owned:nothing.jpg") is None


def test_the_app_gets_a_kept_thumbnail_and_its_tile(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=tmp_path, seed_library=False, scheduler=False))
    kept = jpeg_bytes((90, 120, 200), (640, 480))
    with TestClient(app) as client:
        thumbs = tmp_path / "library" / "thumbs"
        thumbs.mkdir(parents=True, exist_ok=True)
        (thumbs / "met_1.jpg").write_bytes(kept)
        answer = client.get("/api/library/items/met:1/thumb")
        assert answer.status_code == 200 and answer.content == kept
        assert answer.headers["content-type"] == "image/jpeg"
        assert answer.headers["cache-control"] == "max-age=86400"
        assert answer.headers["content-length"] == str(len(kept))
        tile = client.get("/api/library/items/met:1/thumb", params={"tile": "true"})
        assert tile.status_code == 200 and tile.headers["cache-control"] == "max-age=86400"
        with Image.open(io.BytesIO(tile.content)) as img:
            assert img.size == (640, 480)  # nothing around it to cut
