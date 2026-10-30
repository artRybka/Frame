"""A language model (Claude, through Anthropic's API) working for the library:
keywords for what pictures show, Polish texts for works. Optional: without
an API key nothing is asked."""

from .client import (
    HAIKU,
    OPUS,
    SONNET,
    AiUnavailable,
    Answer,
    Claude,
    KeyRejected,
    image_block,
    request,
)
from .config import AiConfig, AiConfigStore, AiConfigUpdate
from .daily import DailyJob, Essay
from .jobs import AiWorker, NoteJob, Progress, text_hash
from .keywords import KeywordsJob
from .pl_text import PlTextJob, PolishText

__all__ = [
    "HAIKU",
    "OPUS",
    "SONNET",
    "AiConfig",
    "AiConfigStore",
    "AiConfigUpdate",
    "AiUnavailable",
    "AiWorker",
    "Answer",
    "Claude",
    "DailyJob",
    "Essay",
    "KeyRejected",
    "KeywordsJob",
    "NoteJob",
    "PlTextJob",
    "PolishText",
    "Progress",
    "image_block",
    "request",
    "text_hash",
]
