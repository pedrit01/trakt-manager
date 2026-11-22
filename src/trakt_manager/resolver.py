"""Resolución de las entradas de una definición a elementos concretos de Trakt.

Cada entrada (una película, una serie, una temporada o unos episodios) se busca
en Trakt y se convierte en uno o varios :class:`DesiredItem`. El resultado es un
:class:`ResolutionReport` que dice qué se encontró y qué no, para poder revisarlo
en una previsualización antes de tocar la cuenta.

Solo usa endpoints públicos de Trakt, así que funciona sin sesión.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from trakt_manager.definitions import Entry, EntryType, ListDefinition, PositionedEntry
from trakt_manager.errors import TraktAPIError
from trakt_manager.items import DesiredItem, episode_code
from trakt_manager.trakt_client import TraktClient

MediaType = Literal["movie", "show"]

# Resultados que se piden a la búsqueda de Trakt para elegir el del año correcto.
SEARCH_RESULT_LIMIT = 10


class ResolvedEntry(BaseModel):
    """Lo que se encontró en Trakt para una entrada de la definición.

    Atributos:
        position: Posición de la entrada en la definición (empezando en 1).
        entry_title: Título de la entrada tal como aparece en la definición.
        matched_title: Título de la película o serie encontrada en Trakt.
        matched_year: Año del título encontrado.
        trakt_id: Id de Trakt de la película o serie encontrada.
        items: Elementos de la lista que aporta esta entrada (varios en el caso de episodios).
    """

    position: int
    entry_title: str
    matched_title: str
    matched_year: int | None
    trakt_id: int
    items: list[DesiredItem]


class UnresolvedItem(BaseModel):
    """Una entrada, o un episodio de una entrada, que no se encontró en Trakt.

    Atributos:
        position: Posición de la entrada en la definición.
        label: Qué no se encontró (por ejemplo ``VisionQuest S01E07``).
        reason: Por qué no se encontró.
    """

    position: int
    label: str
    reason: str


class ResolutionReport(BaseModel):
    """Informe de la resolución de una definición."""

    resolved: list[ResolvedEntry] = Field(default_factory=list)
    unresolved: list[UnresolvedItem] = Field(default_factory=list)

    @property
    def items(self) -> list[DesiredItem]:
        """Todos los elementos encontrados, en el orden de la definición."""
        return [item for entry in self.resolved for item in entry.items]


def build_item_note(entry: Entry, episode_label: str | None = None) -> str | None:
    """Construye la nota que llevará un elemento en la lista de Trakt.

    Mantiene el formato del script original:

    - Episodios (``episode_label`` como ``S01E04``): ``"<título> S01E04 | <bloque>"``.
    - Resto: ``"<bloque> | <nota>"``.

    Las partes vacías se omiten; si no queda nada se devuelve ``None``.
    """
    if episode_label is not None:
        parts = [f"{entry.display_title} {episode_label}", entry.block]
    else:
        parts = [entry.block, entry.note]
    note = " | ".join(part for part in parts if part)
    return note or None


def choose_search_result(results: list[dict[str, Any]], media_type: MediaType, year: int | None) -> dict[str, Any] | None:
    """Elige el mejor resultado de una búsqueda de Trakt.

    Reglas, en orden: el primero con el año exacto; si no hay, el primero con un
    año de diferencia (los estrenos a caballo entre años cambian según la fuente);
    y si tampoco, el primer resultado.

    Args:
        results: Resultados de ``/search/{tipo}`` tal como los devuelve Trakt.
        media_type: ``movie`` o ``show``; es la clave del objeto dentro de cada resultado.
        year: Año esperado, o ``None`` si no se conoce.

    Returns:
        El objeto película/serie elegido, o ``None`` si no hay resultados.
    """
    candidates = [result[media_type] for result in results if result.get(media_type)]
    if not candidates:
        return None
    if year is not None:
        for candidate in candidates:
            if candidate.get("year") == year:
                return candidate
        for candidate in candidates:
            if candidate.get("year") is not None and abs(candidate["year"] - year) <= 1:
                return candidate
    return candidates[0]


class EntryResolver:
    """Resuelve las entradas de una definición contra la API de Trakt.

    Args:
        client: Cliente de Trakt (basta con el Client ID; no necesita sesión).
    """

    def __init__(self, client: TraktClient) -> None:
        self._client = client

    def resolve(self, definition: ListDefinition, include_extras: bool = False) -> ResolutionReport:
        """Resuelve todas las entradas seleccionadas de una definición.

        Lo que no se encuentra se anota en el informe y no interrumpe el resto.

        Raises:
            TraktAPIError: Si Trakt falla por algo distinto de "no encontrado".
        """
        report = ResolutionReport()
        for positioned in definition.selected_entries(include_extras):
            self._resolve_entry(positioned, report)
        return report

    def _resolve_entry(self, positioned: PositionedEntry, report: ResolutionReport) -> None:
        """Resuelve una entrada y añade el resultado al informe."""
        entry = positioned.entry
        media_type: MediaType = "movie" if entry.type == EntryType.MOVIE else "show"
        media = self._find_media(entry, media_type)
        if media is None:
            report.unresolved.append(
                UnresolvedItem(position=positioned.position, label=entry.display_title, reason="no encontrado en Trakt")
            )
            return

        trakt_id = int(media["ids"]["trakt"])
        if entry.type == EntryType.MOVIE:
            items = [DesiredItem(kind="movie", trakt_id=trakt_id, notes=build_item_note(entry), label=_media_label(media))]
        elif entry.type == EntryType.SHOW:
            items = [DesiredItem(kind="show", trakt_id=trakt_id, notes=build_item_note(entry), label=_media_label(media))]
        elif entry.type == EntryType.SEASON:
            items = self._resolve_season(positioned, trakt_id, report)
        else:
            items = self._resolve_episodes(positioned, trakt_id, report)

        report.resolved.append(
            ResolvedEntry(
                position=positioned.position,
                entry_title=entry.display_title,
                matched_title=str(media.get("title", "")),
                matched_year=media.get("year"),
                trakt_id=trakt_id,
                items=items,
            )
        )

    def _find_media(self, entry: Entry, media_type: MediaType) -> dict[str, Any] | None:
        """Encuentra la película o serie de una entrada: por id explícito o por búsqueda."""
        ids = entry.ids
        if ids is not None and not ids.is_empty():
            if ids.trakt is not None:
                return self._lookup_by_id("trakt", str(ids.trakt), media_type)
            if ids.slug is not None:
                return self._get_or_none(f"/{media_type}s/{ids.slug}")
            if ids.imdb is not None:
                return self._lookup_by_id("imdb", ids.imdb, media_type)
            return self._lookup_by_id("tmdb", str(ids.tmdb), media_type)

        results = self._get_or_none(
            f"/search/{media_type}", params={"query": entry.query, "limit": SEARCH_RESULT_LIMIT}
        )
        return choose_search_result(results or [], media_type, entry.year)

    def _lookup_by_id(self, id_type: str, value: str, media_type: MediaType) -> dict[str, Any] | None:
        """Busca un título por un identificador externo (``/search/{tipo_id}/{id}``)."""
        results = self._get_or_none(f"/search/{id_type}/{value}", params={"type": media_type})
        candidates = [result[media_type] for result in results or [] if result.get(media_type)]
        return candidates[0] if candidates else None

    def _resolve_season(self, positioned: PositionedEntry, show_id: int, report: ResolutionReport) -> list[DesiredItem]:
        """Resuelve una temporada completa a su elemento de tipo ``season``."""
        entry = positioned.entry
        label = f"{entry.display_title} T{entry.season}"
        seasons = self._get_or_none(f"/shows/{show_id}/seasons") or []
        for season in seasons:
            if season.get("number") == entry.season:
                return [DesiredItem(kind="season", trakt_id=int(season["ids"]["trakt"]), notes=build_item_note(entry), label=label)]
        report.unresolved.append(UnresolvedItem(position=positioned.position, label=label, reason="temporada no encontrada"))
        return []

    def _resolve_episodes(self, positioned: PositionedEntry, show_id: int, report: ResolutionReport) -> list[DesiredItem]:
        """Resuelve los episodios concretos de una temporada.

        Se pide la temporada entera de una vez (en vez de un episodio por petición)
        para ahorrar llamadas; los episodios que Trakt aún no tiene se anotan como
        no encontrados.
        """
        entry = positioned.entry
        season_number = entry.season if entry.season is not None else 0
        episodes = self._get_or_none(f"/shows/{show_id}/seasons/{season_number}") or []
        episodes_by_number = {episode.get("number"): episode for episode in episodes}

        items: list[DesiredItem] = []
        for number in entry.episodes:
            code = episode_code(season_number, number)
            label = f"{entry.display_title} {code}"
            episode = episodes_by_number.get(number)
            if episode is None or not episode.get("ids", {}).get("trakt"):
                report.unresolved.append(UnresolvedItem(position=positioned.position, label=label, reason="episodio no encontrado"))
                continue
            items.append(
                DesiredItem(kind="episode", trakt_id=int(episode["ids"]["trakt"]), notes=build_item_note(entry, code), label=label)
            )
        return items

    def _get_or_none(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Hace un ``GET`` público y devuelve ``None`` si Trakt responde 404.

        Raises:
            TraktAPIError: Ante cualquier otro error.
        """
        try:
            return self._client.request_json("GET", path, params=params)
        except TraktAPIError as error:
            if error.status_code == 404:
                return None
            raise


def _media_label(media: dict[str, Any]) -> str:
    """Formatea una película o serie como ``Título (año)``."""
    year = media.get("year")
    return f"{media.get('title', '')} ({year})" if year else str(media.get("title", ""))
