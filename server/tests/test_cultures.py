from __future__ import annotations

import pytest

from frame_server.library import Item
from frame_server.library.cultures import circle


def _item(**kw: object) -> Item:
    return Item(id="t:1", source="t", source_id="1", **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"artist_bio": "Dutch, Zundert 1853–1890 Auvers-sur-Oise"}, "west"),
        ({"artist_bio": "Katsushika Hokusai (Japanese, 1760–1849)"}, "east-asia"),
        ({"artist_bio": "American, born Japan 1889"}, "west"),  # the first word says
        ({"culture": "India (Rajasthan, Mewar)"}, "south-asia"),
        ({"culture": "Iran"}, "islamic"),
        ({"culture": "Japonia"}, "east-asia"),  # the Polish museums
        ({"culture": "Polska"}, "west"),
        ({"artist_bio": "South African, 1890–1960"}, "africa"),
        ({"artist_bio": "Native American, Lakota"}, "native-america"),
        ({"styles": ["Edo period (1615–1868)"]}, "east-asia"),
        ({"styles": ["Qing dynasty"]}, "east-asia"),
        ({"styles": ["Japonisme"]}, None),  # a European fashion, not Japan
        ({"title": "The Japanese Bridge"}, None),  # never by the title
        ({}, None),
    ],
)
def test_circle(kw: dict[str, object], expected: str | None) -> None:
    assert circle(_item(**kw)) == expected
