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


def _string(value: str) -> str:
    return '"' + value.replace("\\", " ").replace('"', " ") + '"'


class ParisMusees(Museum):
    key = "paris"
    name = "Paris Musées"
    api = "https://apicollections.parismusees.paris.fr/graphql"
    #: About 1000 requests a day per token: few, full pages.
    page_size = 100

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
        token = self.access.paris_token
        if not token:
            return 0, []
        base = [
            '{field: "type", value: "oeuvre"}',
            '{field: "status", value: "1"}',
            '{field: "field_visuels.entity.field_image_libre", value: "1"}',
        ]
        query = (
            "{ nodeQuery("
            f"offset: {(page - 1) * limit}, limit: {limit}, "
            f"filter: {{conditions: [{', '.join([*base, *conditions])}]}}"
            f") {{ {FIELDS} }} }}"
        )
        resp = self.http.post(self.api, json={"query": query}, headers={"auth-token": token})
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            log.warning("Paris Musées: %s", body["errors"][0].get("message"))
        found = (body.get("data") or {}).get("nodeQuery") or {}
        items = [i for d in found.get("entities") or [] if (i := self._map(d))]
        return int(found.get("count") or len(items)), items

    @staticmethod
    def _types(names: tuple[str, ...]) -> str:
        values = ", ".join(_string(n) for n in names)
        return f'{{field: "field_oeuvre_types_objet.entity.name", operator: IN, value: [{values}]}}'

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        conditions = [self._types(self.pictures)]
        if query.strip():
            conditions.insert(
                0, f'{{field: "title", operator: LIKE, value: {_string(f"%{query.strip()}%")}}}'
            )
        return self._query(conditions, limit, page)

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
