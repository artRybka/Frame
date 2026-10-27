"""A language model (Claude, through Anthropic's API) working for the library:
keywords for what pictures show, Polish texts for works. Optional: without
an API key nothing is asked."""

from .client import HAIKU, SONNET, AiUnavailable, Answer, Claude, KeyRejected, image_block, request
from .config import AiConfig, AiConfigStore, AiConfigUpdate
from .jobs import AiWorker, NoteJob, Progress, text_hash
from .keywords import KeywordsJob

__all__ = [
    "HAIKU",
    "SONNET",
    "AiConfig",
    "AiConfigStore",
    "AiConfigUpdate",
    "AiUnavailable",
    "AiWorker",
    "Answer",
    "Claude",
    "KeyRejected",
    "KeywordsJob",
    "NoteJob",
    "Progress",
    "image_block",
    "request",
    "text_hash",
]
