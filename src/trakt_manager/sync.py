"""Sincronización de una definición con su lista de Trakt.

La sincronización es *idempotente*: la definición describe el estado deseado
de la lista, y cada ejecución calcula solo los cambios necesarios para llegar
a él. Repetirla sin cambios en la definición no modifica nada.

Se hace en dos pasos, para poder previsualizar sin tocar la cuenta:

1. :func:`plan_sync` compara lo deseado con lo existente y devuelve un
   :class:`SyncPlan` (función pura, sin llamadas a Trakt).
2. :class:`ListSynchronizer` obtiene los datos, calcula el plan y, si no es una
   previsualización, lo aplica.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel, Field

from trakt_manager.definitions import ListDefinition
from trakt_manager.errors import ListBusyError, NotAuthenticatedError, TraktAPIError
from trakt_manager.items import DesiredItem, ExistingItem, ItemKey
from trakt_manager.resolver import EntryResolver, ResolutionReport
from trakt_manager.trakt_lists import TraktListsAPI, UserListSummary

# Orden manual ascendente: la lista se muestra en el orden de la definición.
SORT_BY = "rank"
SORT_HOW = "asc"


class MetadataChange(BaseModel):
    """Un metadato de la lista que cambiará (por ejemplo, la privacidad)."""

    field: str
    current: Any
    desired: Any


class NoteUpdate(BaseModel):
    """Un elemento ya presente cuya nota cambiará."""

    list_item_id: int
    label: str
    current_notes: str | None
    desired_notes: str | None


class SyncPlan(BaseModel):
    """Cambios necesarios para que la lista de Trakt coincida con la definición.

    Atributos:
        list_name: Nombre de la lista según la definición.
        list_id: Id de la lista existente, o ``None`` si hay que crearla.
        create_list: Si la lista no existe y se va a crear.
        compared_with_account: ``False`` si se previsualizó sin sesión: entonces no
            se pudo consultar la cuenta y el plan supone que la lista no existe.
        metadata_changes: Metadatos que cambiarán.
        to_add: Elementos que se añadirán, en el orden de la definición.
        to_remove: Elementos que se quitarán (ya no están en la definición o están repetidos).
        note_updates: Elementos cuya nota cambiará.
        reorder: Si hará falta reordenar la lista.
        final_order: Orden final de la lista.
        duplicates_skipped: Elementos que aparecían más de una vez en la definición
            (solo se añaden una vez).
    """

    list_name: str
    list_id: int | None
    create_list: bool
    compared_with_account: bool
    metadata_changes: list[MetadataChange] = Field(default_factory=list)
    to_add: list[DesiredItem] = Field(default_factory=list)
    to_remove: list[ExistingItem] = Field(default_factory=list)
    note_updates: list[NoteUpdate] = Field(default_factory=list)
    reorder: bool = False
    final_order: list[DesiredItem] = Field(default_factory=list)
    duplicates_skipped: list[str] = Field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Indica si aplicar el plan modificaría algo en Trakt."""
        return bool(
            self.create_list
            or self.metadata_changes
            or self.to_add
            or self.to_remove
            or self.note_updates
            or self.reorder
        )


class SyncResult(BaseModel):
    """Resultado de una sincronización o de su previsualización.

    Es el mismo modelo que devuelven el CLI (``--json``) y la API.

    Atributos:
        list_name: Nombre de la lista.
        dry_run: Si fue una previsualización.
        applied: Si se aplicaron cambios en Trakt.
        list_id: Id de la lista en Trakt (``None`` en una previsualización de lista nueva).
        report: Informe de la resolución de las entradas.
        plan: Cambios calculados.
        warnings: Avisos no fatales (por ejemplo, notas que Trakt no guardó).
    """

    list_name: str
    dry_run: bool
    applied: bool
    list_id: int | None
    report: ResolutionReport
    plan: SyncPlan
    warnings: list[str] = Field(default_factory=list)


def desired_list_metadata(definition: ListDefinition) -> dict[str, Any]:
    """Metadatos con los que debe quedar la lista en Trakt."""
    return {
        "name": definition.name,
        "description": definition.description or "",
        "privacy": definition.privacy,
        "display_numbers": definition.display_numbers,
        "allow_comments": definition.allow_comments,
        "sort_by": SORT_BY,
        "sort_how": SORT_HOW,
    }


def plan_sync(
    definition: ListDefinition,
    desired_items: list[DesiredItem],
    existing_list: UserListSummary | None,
    existing_items: list[ExistingItem],
    compared_with_account: bool = True,
) -> SyncPlan:
    """Calcula los cambios para que una lista coincida con su definición.

    Es una función pura: no llama a Trakt, solo compara.

    Args:
        definition: Definición de la lista.
        desired_items: Elementos resueltos, en el orden de la definición.
        existing_list: Lista existente en Trakt, o ``None`` si no existe.
        existing_items: Elementos actuales de la lista (vacío si no existe).
        compared_with_account: Ver :attr:`SyncPlan.compared_with_account`.
    """
    unique_items, duplicates = _without_duplicates(desired_items)
    desired_keys = {item.key for item in unique_items}

    kept_by_key: dict[ItemKey, ExistingItem] = {}
    to_remove: list[ExistingItem] = []
    for existing in sorted(existing_items, key=lambda item: item.rank):
        if existing.key not in desired_keys or existing.key in kept_by_key:
            # Sobra: ya no está en la definición, o es una copia repetida en Trakt.
            to_remove.append(existing)
        else:
            kept_by_key[existing.key] = existing

    to_add = [item for item in unique_items if item.key not in kept_by_key]
    note_updates = [
        NoteUpdate(
            list_item_id=kept_by_key[item.key].list_item_id,
            label=item.label,
            current_notes=kept_by_key[item.key].notes,
            desired_notes=item.notes,
        )
        for item in unique_items
        if item.key in kept_by_key and (kept_by_key[item.key].notes or None) != (item.notes or None)
    ]

    # Trakt añade los elementos nuevos al final: si el resultado de "lo que se queda
    # + lo añadido" no sigue el orden deseado, habrá que reordenar.
    order_after_changes = list(kept_by_key) + [item.key for item in to_add]
    reorder = existing_list is not None and order_after_changes != [item.key for item in unique_items]

    return SyncPlan(
        list_name=definition.name,
        list_id=existing_list.trakt_id if existing_list else None,
        create_list=existing_list is None,
        compared_with_account=compared_with_account,
        metadata_changes=_metadata_changes(definition, existing_list),
        to_add=to_add,
        to_remove=to_remove,
        note_updates=note_updates,
        reorder=reorder,
        final_order=unique_items,
        duplicates_skipped=duplicates,
    )


class ListSynchronizer:
    """Sincroniza definiciones con las listas del usuario en Trakt.

    Args:
        resolver: Resuelve las entradas de la definición.
        lists_api: Acceso a las listas del usuario.
        has_session: Función que indica si hay sesión de Trakt.
    """

    def __init__(self, resolver: EntryResolver, lists_api: TraktListsAPI, has_session: Callable[[], bool]) -> None:
        self._resolver = resolver
        self._lists_api = lists_api
        self._has_session = has_session

    def sync(self, definition: ListDefinition, *, include_extras: bool = False, dry_run: bool = False) -> SyncResult:
        """Sincroniza (o previsualiza) una definición.

        En una previsualización sin sesión se resuelven las entradas igualmente,
        pero el plan se calcula como si la lista no existiera.

        Raises:
            NotAuthenticatedError: Si no es una previsualización y no hay sesión.
            ListNotFoundError: Si la definición fija un ``trakt_list_id`` que no existe.
            TraktAPIError: Si Trakt falla.
        """
        session = self._has_session()
        if not dry_run and not session:
            raise NotAuthenticatedError("Para sincronizar hace falta una sesión de Trakt: ejecuta 'trakt-manager auth login'.")

        report = self._resolver.resolve(definition, include_extras)

        existing_list = self._find_existing_list(definition) if session else None
        existing_items = self._lists_api.get_items(existing_list.trakt_id) if existing_list else []
        plan = plan_sync(definition, report.items, existing_list, existing_items, compared_with_account=session)

        if dry_run:
            return SyncResult(list_name=definition.name, dry_run=True, applied=False, list_id=plan.list_id, report=report, plan=plan)

        list_id, warnings = self._apply(definition, plan)
        return SyncResult(
            list_name=definition.name,
            dry_run=False,
            applied=plan.has_changes,
            list_id=list_id,
            report=report,
            plan=plan,
            warnings=warnings,
        )

    def _find_existing_list(self, definition: ListDefinition) -> UserListSummary | None:
        """Encuentra la lista de la definición: por id fijado o, si no, por nombre exacto."""
        if definition.trakt_list_id is not None:
            return self._lists_api.get_list(definition.trakt_list_id)
        return self._lists_api.find_list_by_name(definition.name)

    def _apply(self, definition: ListDefinition, plan: SyncPlan) -> tuple[int, list[str]]:
        """Aplica un plan en Trakt.

        Orden de las operaciones: metadatos, bajas, altas, notas y, por último,
        el orden. Reordenar al final garantiza el orden correcto aunque Trakt
        haya añadido los elementos nuevos al final de la lista.

        Returns:
            El id de la lista y los avisos producidos.
        """
        warnings: list[str] = []
        metadata = desired_list_metadata(definition)

        if plan.create_list:
            list_id = self._lists_api.create_list(metadata).trakt_id
        else:
            assert plan.list_id is not None  # un plan sin crear lista siempre tiene id
            list_id = plan.list_id
            if plan.metadata_changes:
                self._lists_api.update_list(list_id, metadata)

        if plan.to_remove:
            self._lists_api.remove_items(list_id, plan.to_remove)
        if plan.to_add:
            warnings.extend(self._lists_api.add_items(list_id, plan.to_add))
        warnings.extend(self._update_notes(list_id, plan.note_updates))

        if plan.create_list or plan.to_add or plan.to_remove or plan.reorder:
            warnings.extend(self._apply_final_order(list_id, plan.final_order))
        return list_id, warnings

    def _update_notes(self, list_id: int, note_updates: list[NoteUpdate]) -> list[str]:
        """Actualiza notas de elementos existentes.

        Un fallo aquí no detiene la sincronización: las notas por elemento pueden
        ser una función solo para cuentas VIP de Trakt, y la lista sigue siendo útil.
        Tras el primer fallo se deja de intentar, porque el resto fallaría igual.
        """
        for update in note_updates:
            try:
                self._lists_api.update_item_notes(list_id, update.list_item_id, update.desired_notes)
            except TraktAPIError as error:
                return [f"No se pudieron actualizar las notas ({error.status_code}); puede requerir cuenta VIP de Trakt."]
        return []

    def _apply_final_order(self, list_id: int, desired_order: list[DesiredItem]) -> list[str]:
        """Relee la lista, la reordena si hace falta y comprueba el resultado.

        Returns:
            Avisos si faltan elementos o si Trakt no guardó alguna nota.
        """
        warnings: list[str] = []
        current_items = self._lists_api.get_items(list_id)
        current_by_key = {item.key: item for item in current_items}

        desired_ids = [current_by_key[item.key].list_item_id for item in desired_order if item.key in current_by_key]
        current_ids = [item.list_item_id for item in current_items]
        if desired_ids != current_ids:
            self._lists_api.reorder_items(list_id, desired_ids)

        missing = [item.label for item in desired_order if item.key not in current_by_key]
        if missing:
            warnings.append(f"Trakt no muestra en la lista: {', '.join(missing)}.")
        ignored_notes = [
            item.label
            for item in desired_order
            if item.key in current_by_key and item.notes and (current_by_key[item.key].notes or None) != item.notes
        ]
        if ignored_notes:
            warnings.append(
                f"Trakt no guardó la nota de {len(ignored_notes)} elementos; las notas pueden requerir cuenta VIP."
            )
        return warnings


class SyncLocks:
    """Bloqueos por nombre de lista para impedir dos sincronizaciones reales simultáneas.

    Basta con bloqueos en memoria porque la API se ejecuta en un único proceso.
    """

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @contextmanager
    def hold(self, list_name: str) -> Iterator[None]:
        """Reserva la lista durante el bloque ``with``.

        Raises:
            ListBusyError: Si la lista ya está reservada; no se espera a que se libere.
        """
        with self._guard:
            lock = self._locks.setdefault(list_name, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ListBusyError(f"Ya hay una sincronización en curso de la lista '{list_name}'.")
        try:
            yield
        finally:
            lock.release()


def _without_duplicates(items: list[DesiredItem]) -> tuple[list[DesiredItem], list[str]]:
    """Quita los elementos repetidos manteniendo la primera aparición.

    Returns:
        Los elementos sin repetir y las etiquetas de los repetidos que se omitieron.
    """
    seen: set[ItemKey] = set()
    unique: list[DesiredItem] = []
    duplicates: list[str] = []
    for item in items:
        if item.key in seen:
            duplicates.append(item.label)
            continue
        seen.add(item.key)
        unique.append(item)
    return unique, duplicates


def _metadata_changes(definition: ListDefinition, existing_list: UserListSummary | None) -> list[MetadataChange]:
    """Compara los metadatos deseados con los de la lista existente."""
    if existing_list is None:
        return []
    current = {
        "name": existing_list.name,
        "description": existing_list.description or "",
        "privacy": existing_list.privacy,
        "display_numbers": existing_list.display_numbers,
        "allow_comments": existing_list.allow_comments,
        "sort_by": existing_list.sort_by,
        "sort_how": existing_list.sort_how,
    }
    desired = desired_list_metadata(definition)
    return [
        MetadataChange(field=field, current=current[field], desired=value)
        for field, value in desired.items()
        if current[field] != value
    ]
