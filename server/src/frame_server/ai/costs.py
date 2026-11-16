"""What each thing the models do costs, as Konfiguracja tells it (Mateusz
2026-11-16: "Całą tabelkę Claude oraz Gemini … czytelnie podaj koszt dla
każdej pozycji za ostatnie dni? Teraz ciężko się połapać co ile kosztuje").

The spending is kept by day and by the job's kind (``client.Spending``);
the kinds are the code's, several of them one thing for the owner (a study
is its page, its composition in three steps, its details checked…). Each
row here is one thing he can tell apart, in his words, and where it has a
switch in Konfiguracja its key is the switch's (``AiView``'s field), so the
app puts the row's money under that switch. A kind no row names is counted
in "Inne", never lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import Spending

#: The days Konfiguracja looks back over.
DAYS = 7


@dataclass(frozen=True)
class Row:
    #: The switch's key where there is one (``AiView``'s field name).
    key: str
    label: str
    kinds: tuple[str, ...]


#: Claude's (Anthropic's) rows, in the order of the page.
CLAUDE = (
    Row("pl_text", "Polskie tytuły i opisy", ("pl_text", "museum_words")),
    Row("keywords", "Słowa kluczowe", ("keywords",)),
    Row("search_words", "Tłumaczenie słów w Szukaj", ("search_words", "look_words")),
    Row("daily", "Studium dnia (wybór i tekst)", ("daily", "study_pick", "study_fit")),
    Row(
        "studies",
        "Studia dzieł: kompozycja, detale, szkic",
        ("study", "composition", "composition_text", "details_check", "study_extras", "pen"),
    ),
    Row("web_facts", "Fakty z sieci", ("web_facts",)),
    Row("stages", "Jak powstawał", ("stages",)),
    Row("journey", "Droga dzieła", ("journey",)),
    Row("curator", "Kurator Odkrywaj", ("curator",)),
    Row("gatekeeper", "Strażnik katalogu", ("gatekeeper",)),
    Row("twins_judge", "Sędzia powtórek", ("twins.judge",)),
    Row("crops", "Kadrowanie zdjęć dzieł", ("crops",)),
    Row("varnish_blue", "Błękit pod werniksem", ("varnish_blue",)),
    Row("audit", "Nocny przegląd", ("audit",)),
    Row("sheet_judge", "Ocena arkuszy Gemini", ("sheet_judge",)),
    Row("own_works", "Własne dzieła", ("own_hints",)),
    Row("study_refresh", "Uzupełnianie starszych studiów", ("study_refresh",)),
    Row("text_review", "Sprawdzanie starszych tłumaczeń", ("text_review",)),
)

#: Google's (Gemini's).
GEMINI = (
    Row("drawn", "Arkusze kompozycji", ("sheet",)),
    Row("looks", "Szukanie wyglądem", ("looks",)),
    Row("restorer", "Restauracja dzieł", ("restorer",)),
)

OTHER = Row("other", "Inne", ())


def rows(
    spending: Spending, table: tuple[Row, ...], now: datetime | None = None
) -> list[dict[str, Any]]:
    """Each row's money over the last :data:`DAYS` days and the period so
    far, in the table's order; a row that cost nothing in either is left
    out, as is "Inne" then."""
    recent = spending.last_days(DAYS, now)
    period = spending.by_kind(now)
    named = {kind for row in table for kind in row.kinds}
    found: list[dict[str, Any]] = []
    for row in (*table, OTHER):
        kinds = row.kinds if row.kinds else None

        def total(spent: dict[str, float], kinds: tuple[str, ...] | None = kinds) -> float:
            if kinds is None:
                return sum(v for k, v in spent.items() if k not in named)
            return sum(spent.get(k, 0.0) for k in kinds)

        days, so_far = total(recent), total(period)
        if days <= 0 and so_far <= 0:
            continue
        found.append(
            {
                "key": row.key,
                "label": row.label,
                "days_usd": round(days, 4),
                "period_usd": round(so_far, 4),
            }
        )
    return found
