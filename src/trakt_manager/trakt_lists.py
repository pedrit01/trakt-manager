"""Operaciones sobre las listas personales del usuario en Trakt.

Encapsula los endpoints ``/users/me/lists/...`` para que la lógica de
sincronización y las interfaces trabajen con modelos (:class:`UserListSummary`,
:class:`ExistingItem`) en lugar de con el JSON de Trakt.

Todas las operaciones necesitan sesión.
"""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from trakt_manager.errors import ListNotFoundError, TraktAPIError
from trakt_manager.items import PAYLOAD_KEY_BY_KIND, DesiredItem, ExistingItem, episode_code
from trakt_manager.trakt_client import TraktClient

# Elementos por petición al añadir o quitar, para no enviar cuerpos enormes.
ITEMS_PER_REQUEST = 100

LISTS_PATH = "/users/me/lists"


class UserListSummary(BaseModel):
    """Resumen de una lista del usuario.

    Atributos:
        trakt_id: Identificador numérico de la lista.
        slug: Identificador textual de la lista (aparece en su URL).
        name: Nombre de la lista.
        privacy: ``private``, ``friends`` o ``public``.
        item_count: Número de elementos.
        description: Descripción de la lista.
        display_numbers: Si Trakt muestra los números de posición.
        allow_comments: Si se permiten comentarios.
        sort_by: Criterio de orden configurado en Trakt.
        sort_how: Sentido del orden (``asc`` o ``desc``).
    """

    trakt_id: int
    slug: str
    name: str
    privacy: str
    item_count: int
    description: str | None = None
    display_numbers: bool | None = None
    allow_comments: bool | None = None
    sort_by: str | None = None
    sort_how: str | None = None


class TraktListsAPI:
    """Acceso a las listas personales del usuario autenticado.

    Args:
        client: Cliente de Trakt con un proveedor de tokens configurado.
    """

    def __init__(self, client: TraktClient) -> None:
        self._client = client

    def get_user_lists(self) -> list[UserListSummary]:
        """Devuelve todas las listas del usuario."""
        lists = self._client.request_json("GET", LISTS_PATH, authenticated=True) or []
        return [_summary_from_json(data) for data in lists]

    def account_supports_list_notes(self) -> bool:
        """Indica si la cuenta puede guardar notas en los elementos de sus listas.

        Trakt solo las guarda en cuentas VIP. Con otras cuentas acepta el lote sin
        error, pero descarta las notas en silencio, así que hay que preguntarlo antes.
        """
        settings = self._client.request_json("GET", "/users/settings", authenticated=True) or {}
        user = settings.get("user", {})
        return bool(user.get("vip") or user.get("vip_ep"))

    def get_list(self, list_id: int | str) -> UserListSummary:
        """Devuelve una lista por su id numérico o su slug.

        Raises:
            ListNotFoundError: Si la lista no existe en la cuenta.
        """
        try:
            data = self._client.request_json("GET", f"{LISTS_PATH}/{list_id}", authenticated=True)
        except TraktAPIError as error:
            if error.status_code == 404:
                raise ListNotFoundError(f"No existe ninguna lista '{list_id}' en tu cuenta de Trakt.") from error
            raise
        return _summary_from_json(data)

    def find_list_by_name(self, name: str) -> UserListSummary | None:
        """Busca una lista del usuario por su nombre exacto."""
        return next((summary for summary in self.get_user_lists() if summary.name == name), None)

    def get_items(self, list_id: int | str) -> list[ExistingItem]:
        """Devuelve los elementos de una lista ordenados por su posición."""
        raw_items = self._client.get_all_pages(f"{LISTS_PATH}/{list_id}/items", authenticated=True)
        items = [item for item in (_existing_item_from_json(raw) for raw in raw_items) if item is not None]
        return sorted(items, key=lambda item: item.rank)

    def create_list(self, metadata: dict[str, Any]) -> UserListSummary:
        """Crea una lista con los metadatos indicados y la devuelve."""
        data = self._client.request_json("POST", LISTS_PATH, json=metadata, authenticated=True)
        return _summary_from_json(data)

    def update_list(self, list_id: int, metadata: dict[str, Any]) -> None:
        """Actualiza los metadatos de una lista."""
        self._client.request_json("PUT", f"{LISTS_PATH}/{list_id}", json=metadata, authenticated=True)

    def add_items(self, list_id: int, items: list[DesiredItem]) -> list[str]:
        """Añade elementos a una lista, en el orden dado y en lotes.

        Los elementos consecutivos del mismo tipo se envían juntos; al cambiar de
        tipo se abre un lote nuevo, para que Trakt los añada en el orden deseado.

        Returns:
            Avisos por elementos que Trakt no reconoció.
        """
        warnings: list[str] = []
        for batch in _batches_by_kind(items):
            payload_key = PAYLOAD_KEY_BY_KIND[batch[0].kind]
            payload = {payload_key: [_item_payload(item, include_notes=True) for item in batch]}
            response = self._client.request_json("POST", f"{LISTS_PATH}/{list_id}/items", json=payload, authenticated=True)
            not_found = (response or {}).get("not_found", {}).get(payload_key, [])
            if not_found:
                warnings.append(f"Trakt no reconoció {len(not_found)} elementos de tipo {batch[0].kind} al añadirlos.")
        return warnings

    def remove_items(self, list_id: int, items: Iterable[ExistingItem]) -> None:
        """Quita elementos de una lista."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            grouped.setdefault(PAYLOAD_KEY_BY_KIND[item.kind], []).append({"ids": {"trakt": item.trakt_id}})
        for payload_key, payload_items in grouped.items():
            for start in range(0, len(payload_items), ITEMS_PER_REQUEST):
                chunk = payload_items[start : start + ITEMS_PER_REQUEST]
                self._client.request_json(
                    "POST", f"{LISTS_PATH}/{list_id}/items/remove", json={payload_key: chunk}, authenticated=True
                )

    def update_item_notes(self, list_id: int, list_item_id: int, notes: str | None) -> None:
        """Cambia la nota de un elemento de la lista."""
        self._client.request_json(
            "PUT", f"{LISTS_PATH}/{list_id}/items/{list_item_id}", json={"notes": notes or ""}, authenticated=True
        )

    def reorder_items(self, list_id: int, list_item_ids: list[int]) -> None:
        """Fija el orden de la lista: ``list_item_ids`` en el orden deseado."""
        self._client.request_json(
            "POST", f"{LISTS_PATH}/{list_id}/items/reorder", json={"rank": list_item_ids}, authenticated=True
        )


def _summary_from_json(data: dict[str, Any]) -> UserListSummary:
    """Convierte una lista tal como la devuelve Trakt en :class:`UserListSummary`."""
    return UserListSummary(
        trakt_id=int(data["ids"]["trakt"]),
        slug=str(data["ids"].get("slug", "")),
        name=str(data["name"]),
        privacy=str(data.get("privacy", "private")),
        item_count=int(data.get("item_count", 0)),
        description=data.get("description"),
        display_numbers=data.get("display_numbers"),
        allow_comments=data.get("allow_comments"),
        sort_by=data.get("sort_by"),
        sort_how=data.get("sort_how"),
    )


def _existing_item_from_json(data: dict[str, Any]) -> ExistingItem | None:
    """Convierte un elemento de lista de Trakt en :class:`ExistingItem`.

    Devuelve ``None`` para tipos que esta herramienta no gestiona (por ejemplo personas).
    """
    kind = data.get("type")
    if kind not in PAYLOAD_KEY_BY_KIND or not data.get(kind):
        return None
    media = data[kind]
    return ExistingItem(
        list_item_id=int(data["id"]),
        rank=int(data.get("rank", 0)),
        kind=kind,
        trakt_id=int(media["ids"]["trakt"]),
        notes=data.get("notes") or None,
        label=_existing_item_label(kind, data),
    )


def _existing_item_label(kind: str, data: dict[str, Any]) -> str:
    """Construye un texto legible para un elemento existente de una lista."""
    if kind == "episode":
        show_title = data.get("show", {}).get("title", "")
        episode = data["episode"]
        return f"{show_title} {episode_code(int(episode.get('season', 0)), int(episode.get('number', 0)))}"
    if kind == "season":
        return f"{data.get('show', {}).get('title', '')} T{data['season'].get('number', '?')}"
    media = data[kind]
    year = media.get("year")
    return f"{media.get('title', '')} ({year})" if year else str(media.get("title", ""))


def _item_payload(item: DesiredItem, include_notes: bool) -> dict[str, Any]:
    """Cuerpo con el que se envía un elemento a Trakt."""
    payload: dict[str, Any] = {"ids": {"trakt": item.trakt_id}}
    if include_notes and item.notes:
        payload["notes"] = item.notes
    return payload


def _batches_by_kind(items: list[DesiredItem]) -> list[list[DesiredItem]]:
    """Agrupa elementos consecutivos del mismo tipo en lotes de como mucho ``ITEMS_PER_REQUEST``."""
    batches: list[list[DesiredItem]] = []
    for item in items:
        if batches and batches[-1][0].kind == item.kind and len(batches[-1]) < ITEMS_PER_REQUEST:
            batches[-1].append(item)
        else:
            batches.append([item])
    return batches
