"""Works whose museum numbers them with a slash (SMK's "KKS1984-23/366"):
the app sends the slash as %2F, and every address of the work answers."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from frame_server.library.models import Item

SLASHED = "smk:KKS1984-23/366"
SENT = "smk:KKS1984-23%2F366"


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 180, 150)).save(out, "JPEG")
    return out.getvalue()


def test_a_work_with_a_slash_in_its_id_answers_everywhere(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        item = svc.library.upsert(
            Item(
                id=SLASHED,
                source="smk",
                source_id="KKS1984-23/366",
                title="Udklip på papir med kvindetegnet",
                image_url="https://iip.smk.dk/x.jpg",
                thumb_url="https://iip-thumb.smk.dk/x.jpg",
            )
        )
        svc.images.store(item, _jpeg())
        card = client.get(f"/api/library/items/{SENT}")
        assert card.status_code == 200, card.text
        assert card.json()["id"] == SLASHED
        thumb = client.get(f"/api/library/items/{SENT}/thumb")
        assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
        assert client.get(f"/api/library/items/{SENT}/image").status_code == 200
        framing = client.get(f"/api/library/items/{SENT}/framing")
        assert framing.status_code == 200
        liked = client.patch(f"/api/library/items/{SENT}", json={"favorite": True})
        assert liked.status_code == 200 and liked.json()["favorite"]
        # The id goes back with its slash where the app finds it again.
        assert SLASHED in client.get("/api/library/items", params={"source": "smk"}).text
