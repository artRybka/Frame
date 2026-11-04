"""Work ids with a slash in them, in the app's addresses.

Some museums number their works with a slash: SMK's "KKS1984-23/366"
(2026-11-04, "Jasne i spokojne" with empty tiles). The app sends it as
``%2F``, but the ASGI server decodes the path before routing, so
``/api/library/items/smk:KKS1984-23/366/thumb`` matched no route at all and
every one of these works answered 404: thumbnail, card, preview, sending
it to the frame.

:class:`EncodedSlashes` routes on the path with an encoded slash kept as
:data:`SLASH`, and the ``item`` convertor (``{item_id:item}``) gives the
handler the id with its slash back.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

from starlette.convertors import Convertor, register_url_convertor

#: An encoded slash while the path is routed; never in a work id.
SLASH = "\x1f"
_ENCODED = re.compile(r"%2f", re.IGNORECASE)


class ItemIdConvertor(Convertor[str]):
    regex = "[^/]+"

    def convert(self, value: str) -> str:
        return value.replace(SLASH, "/")

    def to_string(self, value: str) -> str:
        return value.replace("/", "%2F")


register_url_convertor("item", ItemIdConvertor())


class EncodedSlashes:
    """ASGI middleware: an encoded slash (``%2F``) in the path stays one
    segment of it while the request is routed."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        raw = scope.get("raw_path") if scope["type"] in ("http", "websocket") else None
        if raw and b"%2" in raw and _ENCODED.search(text := raw.decode("latin-1")):
            scope = {**scope, "path": unquote(_ENCODED.sub(SLASH, text))}
        await self.app(scope, receive, send)
