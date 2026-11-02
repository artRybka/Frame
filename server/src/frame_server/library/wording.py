"""Words typed in Szukaj, as each museum's catalogue speaks: the Polish
museums get them as typed, the others in English (Paris Musées in French)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Wording:
    """``text`` as typed, with its English and French when it is Polish
    ("gitara": "guitar", "guitare"); empty when not translated."""

    text: str
    en: str = ""
    fr: str = ""

    def in_language(self, language: str) -> str:
        """What a catalogue in ``language`` ("pl", "en", "fr") is asked."""
        if language == "pl":
            return self.text
        if language == "fr":
            return self.fr or self.text
        return self.en or self.text

    @property
    def translated(self) -> bool:
        return bool(self.en or self.fr)
