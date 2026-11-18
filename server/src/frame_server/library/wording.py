"""Words typed in Szukaj, as each museum's catalogue speaks: the Polish
museums get them as typed (in Polish when typed in another language), the
others in English (Paris Musées in French)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Wording:
    """``text`` as typed, with its English and French when it is Polish
    ("gitara": "guitar", "guitare"), its Polish when it is in another
    language ("The Storks": "Bociany"); empty when not translated."""

    text: str
    en: str = ""
    fr: str = ""
    pl: str = ""

    def in_language(self, language: str) -> str:
        """What a catalogue in ``language`` ("pl", "en", "fr") is asked."""
        if language == "pl":
            # A title the app's hint gave in English ("The Storks") found
            # nothing in Warsaw: its catalogue has "Bociany" (2026-11-18).
            return self.pl or self.text
        if language == "fr":
            return self.fr or self.text
        return self.en or self.text

    @property
    def translated(self) -> bool:
        return bool(self.en or self.fr)
