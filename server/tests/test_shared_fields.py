"""Works read from the catalogue share pydantic's sets of their fields."""

from __future__ import annotations

from frame_server.library.models import ColorSwatch, Item, shared_fields


def _work(n: int) -> Item:
    return Item.model_validate_json(
        Item(
            id=f"met:{n}",
            source="met",
            source_id=str(n),
            title=f"Work {n}",
            colors=[ColorSwatch(hex="#112233", weight=0.5), ColorSwatch(hex="#445566", weight=0.5)],
        ).model_dump_json()
    )


def test_works_read_alike_share_one_set_of_fields_and_stay_the_same() -> None:
    one, two = _work(1), _work(2)
    before = one.model_dump(), two.model_dump()
    shared_fields(one)
    shared_fields(two)
    assert one.__pydantic_fields_set__ is two.__pydantic_fields_set__
    assert one.colors[0].__pydantic_fields_set__ is two.colors[1].__pydantic_fields_set__
    assert (one.model_dump(), two.model_dump()) == before
    assert one.model_dump(exclude_unset=True) == before[0]
    # A copy with changes has its own set: the shared one stays as it was.
    changed = one.model_copy(update={"title": "Other"})
    assert changed.__pydantic_fields_set__ is not one.__pydantic_fields_set__
    assert two.title == "Work 2"
