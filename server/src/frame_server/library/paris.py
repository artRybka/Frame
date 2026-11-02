"""Paris Musées: the fourteen museums of the City of Paris (Petit Palais,
Carnavalet, Musée de la Vie romantique, Maison de Victor Hugo, Cernuschi…).

A GraphQL API (Drupal) that answers only with a token of one's own,
entered in the app (Konfiguracja → Źródła dzieł); without it the source is
not offered. A token allows about 1000 requests a day. Only works whose
pictures the museums give freely (``field_image_libre``, CC0) are taken;
they come in high definition from the portal's file server.
"""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

from .models import Item
from .museums import Access, Discovery, Museum, _person

log = logging.getLogger(__name__)

PORTAL = "https://www.parismuseescollections.paris.fr"

FIELDS = """
  count
  entities {
    ... on NodeOeuvre {
      entityId
      title
      absolutePath
      fieldOeuvreAuteurs { entity { fieldAuteurAuteur { entity {
        name
        fieldPipDateNaissance { startYear }
        fieldPipDateDeces { startYear }
      } } } }
      fieldVisuels { entity { publicUrl vignette fieldImageLibre } }
      fieldDateProduction { startYear century }
      fieldOeuvreTypesObjet { entity { name } }
      fieldMateriauxTechnique { entity { name } }
      fieldOeuvreThemeRepresente { entity { name } }
      fieldMusee { entity { name } }
    }
  }
"""


def _names(values: Any) -> list[str]:
    out = []
    for value in values or []:
        name = str(((value or {}).get("entity") or {}).get("name") or "").strip()
        if name:
            out.append(name)
    return out


#: The author's name, from a work (a ``nodeQuery`` filter's path).
AUTHOR = "field_oeuvre_auteurs.entity.field_auteur_auteur.entity.name"
#: Words of a search asked for at most: each is one more join on their side.
WORDS = 4


def _words(text: str) -> list[str]:
    """The longest words of a search (at least three letters; "de", "la"
    would match everything), in their order, at most WORDS."""
    words = list(dict.fromkeys(w for w in re.findall(r"[\w'’-]+", text) if len(w) >= 3))
    kept = set(sorted(words, key=len, reverse=True)[:WORDS])
    return [w for w in words if w in kept]


def _string(value: str) -> str:
    return '"' + value.replace("\\", " ").replace('"', " ") + '"'


class ParisMusees(Museum):
    #: Whether the API lets a search look at authors' names (it said no
    #: once: titles only until the server restarts).
    _by_author: ClassVar[bool] = True

    key = "paris"
    name = "Paris Musées"
    api = "https://apicollections.parismusees.paris.fr/graphql"
    #: About 1000 requests a day per token: few, full pages.
    page_size = 100
    language: ClassVar[str] = "fr"

    @classmethod
    def offered(cls, access: Access) -> bool:
        return bool(access.paris_token)

    #: The collections' object types (``field_oeuvre_types_objet``).
    kinds: ClassVar[dict[str, tuple[str, ...]]] = {
        "painting": ("Peinture",),
        "drawing": ("Arts graphiques", "Dessin"),
        "print": ("Estampe", "Arts graphiques"),
        "poster": ("Affiche",),
        "photograph": ("Photographie",),
        "sculpture": ("Sculpture",),
    }
    pictures = ("Peinture", "Arts graphiques", "Dessin", "Estampe")

    def _map(self, d: dict[str, Any]) -> Item | None:
        if not d or not d.get("entityId"):
            return None
        visuals = [(v or {}).get("entity") or {} for v in d.get("fieldVisuels") or [] if v]
        free = [v for v in visuals if v.get("fieldImageLibre") and v.get("publicUrl")]
        if not free:
            return None
        picture = free[0]
        image = str(picture["publicUrl"])
        thumb = str(picture.get("vignette") or "")
        authors = [
            ((a or {}).get("entity") or {}).get("fieldAuteurAuteur") or {}
            for a in d.get("fieldOeuvreAuteurs") or []
        ]
        author = (authors[0].get("entity") or {}) if authors else {}
        artist = _person(str(author.get("name") or "").strip())
        born = (author.get("fieldPipDateNaissance") or {}).get("startYear")
        died = (author.get("fieldPipDateDeces") or {}).get("startYear")
        bio = f"{born}–{died}" if born and died else ""
        made = d.get("fieldDateProduction") or {}
        year = made.get("startYear")
        date = str(year or made.get("century") or "")
        if not year:
            found = re.search(r"\d{4}", date)
            year = int(found.group(0)) if found else None
        museum = (_names([d.get("fieldMusee")]) or [self.name])[0]
        path = str(d.get("absolutePath") or "")
        return self._item(
            str(d["entityId"]),
            title=str(d.get("title") or ""),
            artist=artist,
            artist_bio=bio,
            date_text=date,
            year=int(year) if year else None,
            medium=", ".join(_names(d.get("fieldMateriauxTechnique"))),
            classification=", ".join(_names(d.get("fieldOeuvreTypesObjet"))),
            subjects=_names(d.get("fieldOeuvreThemeRepresente"))[:12],
            credit=f"CC0 Paris Musées / {museum}",
            license="CC0 1.0",
            url=f"{PORTAL}{path}" if path.startswith("/") else path,
            museum=museum,
            image_url=image,
            thumb_url=thumb if thumb.startswith("http") else image,
        )

    def _item(self, source_id: str, **fields: Any) -> Item:
        museum = fields.pop("museum", self.name)
        return super()._item(source_id, **fields).model_copy(update={"museum": museum})

    def _query(self, conditions: list[str], limit: int, page: int) -> tuple[int, list[Item]]:
        return self._found(self._ask(conditions, limit, page) or {})

    def _found(self, found: dict[str, Any]) -> tuple[int, list[Item]]:
        items = [i for d in found.get("entities") or [] if (i := self._map(d))]
        return int(found.get("count") or len(items)), items

    def _ask(
        self, conditions: list[str], limit: int, page: int, groups: list[str] | None = None
    ) -> dict[str, Any] | None:
        """The ``nodeQuery`` answer; None when the API refused the query."""
        token = self.access.paris_token
        if not token:
            return {}
        base = [
            '{field: "type", value: "oeuvre"}',
            '{field: "status", value: "1"}',
            '{field: "field_visuels.entity.field_image_libre", value: "1"}',
        ]
        nested = f", groups: [{', '.join(groups)}]" if groups else ""
        query = (
            "{ nodeQuery("
            f"offset: {(page - 1) * limit}, limit: {limit}, "
            f"filter: {{conjunction: AND, conditions: [{', '.join([*base, *conditions])}]{nested}}}"
            f") {{ {FIELDS} }} }}"
        )
        resp = self.http.post(self.api, json={"query": query}, headers={"auth-token": token})
        resp.raise_for_status()
        body = resp.json()
        found = (body.get("data") or {}).get("nodeQuery")
        if body.get("errors"):
            log.warning("Paris Musées: %s", body["errors"][0].get("message"))
            if found is None:
                return None
        return found or {}

    @staticmethod
    def _types(names: tuple[str, ...]) -> str:
        values = ", ".join(_string(n) for n in names)
        return f'{{field: "field_oeuvre_types_objet.entity.name", operator: IN, value: [{values}]}}'

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        """Works whose title or author holds each word of ``query`` ("Monet",
        "nymphéas monet"); while the API refuses to look at authors, the
        whole query in the title, as before."""
        conditions = [self._types(self.pictures)]
        text = query.strip()
        if not text:
            return self._query(conditions, limit, page)
        words = _words(text)
        if words and ParisMusees._by_author:
            groups = [
                "{conjunction: OR, conditions: ["
                f'{{field: "title", operator: LIKE, value: {_string(f"%{w}%")}}}, '
                f'{{field: "{AUTHOR}", operator: LIKE, value: {_string(f"%{w}%")}}}'
                "]}"
                for w in words
            ]
            found = self._ask(conditions, limit, page, groups)
            if found is not None:
                return self._found(found)
            # Not a field it lets us filter by: titles only from now on.
            log.warning("Paris Musées: no search by author; titles only")
            ParisMusees._by_author = False
        title = f'{{field: "title", operator: LIKE, value: {_string(f"%{text}%")}}}'
        return self._query([title, *conditions], limit, page)

    def discover(self, spec: Discovery, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        # Styles are not named in the records; nor are highlights.
        if spec.highlight or spec.style.strip() or spec.kind == "decorative":
            return 0, []
        conditions = [self._types(self.kinds.get(spec.kind, self.pictures))]
        if spec.year_from is not None:
            conditions.append(
                '{field: "field_date_production.start_year", '
                f'operator: GREATER_THAN_OR_EQUAL, value: "{spec.year_from}"}}'
            )
        if spec.year_to is not None:
            conditions.append(
                '{field: "field_date_production.start_year", '
                f'operator: SMALLER_THAN_OR_EQUAL, value: "{spec.year_to}"}}'
            )
        return self._query(conditions, limit, page)

    def fetch(self, source_id: str) -> Item | None:
        if not source_id.isdigit():
            return None
        _, items = self._query([f'{{field: "nid", value: "{source_id}"}}'], 1, 1)
        return items[0] if items else None
