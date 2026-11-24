"""The phone's crop model on the server, for the night (Mateusz 2026-11-24
10:40 UTC: „czy kadrowanie mogłoby odbywać się także przy okazji zadań
nocnych?”, 10:53 „Na serwerze w nocy”): the app's own weights
(``ios/Models/*.mlpackage``) exported to ONNX (:data:`.crop_model.WEIGHTS`)
and what :mod:`.crop_model` makes of their answer, as on the phone. On 60
catalogue photographs ONNX here and Core ML on the Mac came to the same in
59 (one painting's frame told otherwise); how sure they were at most 0.008
apart, the corners 0.3 px apart in the middle, 3.5 px at most."""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

from .crop_model import KINDS, WEIGHTS, Found, find, letterbox, model_of, sure_of


class Looker:
    """The models, each loaded once, looking at photographs."""

    def __init__(self, threads: int = 2) -> None:
        self.threads = threads
        self._lock = threading.Lock()
        self._sessions: dict[str, Any] = {}

    def _session(self, model: str) -> Any:
        import onnxruntime as ort

        with self._lock:
            if model not in self._sessions:
                options = ort.SessionOptions()
                options.intra_op_num_threads = self.threads
                options.inter_op_num_threads = 1
                session = ort.InferenceSession(
                    str(WEIGHTS / f"{model}.onnx"), options, providers=["CPUExecutionProvider"]
                )
                named = session.get_modelmeta().custom_metadata_map.get("model")
                if named != model:
                    raise ValueError(f"{model}.onnx is {named}")
                self._sessions[model] = session
            return self._sessions[model]

    def ask(self, rgb: np.ndarray, kind: int) -> tuple[np.ndarray, float]:
        """The answer of :func:`.crop_model.model_of` ``kind`` about
        ``rgb`` (the photograph as the phone looks at it): its masks
        before the sigmoid (2 × side × side) and how sure it is a cut is
        wanted."""
        x, _ = letterbox(rgb)
        told = np.zeros((1, len(KINDS)), np.float32)
        told[0, min(max(kind, 0), len(KINDS) - 1)] = 1.0
        masks, cut = self._session(model_of(kind)).run(
            None, {"x": x.transpose(2, 0, 1)[None].copy(), "kind": told}
        )
        return np.asarray(masks[0], np.float32), float(np.ravel(cut)[0])

    def look(self, rgb: np.ndarray, kind: int) -> Found:
        """What the phone would find in ``rgb`` (``MuseumCrop.look``)."""
        logits, sure = self.ask(rgb, kind)
        return find(rgb, logits, sure, sure_of(kind), kind=kind)
