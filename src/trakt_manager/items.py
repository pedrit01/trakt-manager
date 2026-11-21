"""Modelos de los elementos que forman una lista de Trakt.

Una lista de Trakt contiene elementos de varios tipos (películas, series,
temporadas y episodios). Cada elemento se identifica por su tipo y su id de
Trakt: esa pareja es la *clave* que se usa para comparar la lista deseada con
la que ya existe. Nunca se usa la nota como clave, porque varias entradas
pueden compartir la misma nota (era el fallo del script original).
"""

from typing import Literal

from pydantic import BaseModel

ItemKind = Literal["movie", "show", "season", "episode"]

ItemKey = tuple[str, int]

# Trakt agrupa los elementos por tipo en plural en los cuerpos de añadir y quitar.
PAYLOAD_KEY_BY_KIND: dict[str, str] = {
    "movie": "movies",
    "show": "shows",
    "season": "seasons",
    "episode": "episodes",
}


def episode_code(season: int, episode: int) -> str:
    """Formatea un episodio como ``S01E04``."""
    return f"S{season:02d}E{episode:02d}"


class DesiredItem(BaseModel):
    """Un elemento que debe estar en la lista según la definición.

    Atributos:
        kind: Tipo de elemento en Trakt.
        trakt_id: Identificador de Trakt del elemento.
        notes: Nota que debe tener el elemento en la lista.
        label: Texto legible para informes (por ejemplo ``Loki S02E01``).
    """

    kind: ItemKind
    trakt_id: int
    notes: str | None = None
    label: str

    @property
    def key(self) -> ItemKey:
        """Clave de identidad del elemento: ``(tipo, id de Trakt)``."""
        return (self.kind, self.trakt_id)


class ExistingItem(BaseModel):
    """Un elemento que ya está en una lista de Trakt.

    Atributos:
        list_item_id: Identificador del elemento dentro de la lista (lo usa Trakt
            para reordenar y editar notas; no es el id de la película o episodio).
        rank: Posición actual en la lista, empezando en 1.
        kind: Tipo de elemento.
        trakt_id: Identificador de Trakt de la película, serie, temporada o episodio.
        notes: Nota guardada en Trakt.
        label: Texto legible para informes.
    """

    list_item_id: int
    rank: int
    kind: ItemKind
    trakt_id: int
    notes: str | None = None
    label: str

    @property
    def key(self) -> ItemKey:
        """Clave de identidad del elemento: ``(tipo, id de Trakt)``."""
        return (self.kind, self.trakt_id)
