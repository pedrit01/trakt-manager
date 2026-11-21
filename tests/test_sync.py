"""Tests del plan de sincronización y de su aplicación sobre un Trakt simulado."""

import pytest

from fake_trakt import FakeTrakt
from trakt_manager.definitions import parse_definition_data
from trakt_manager.errors import NotAuthenticatedError
from trakt_manager.items import DesiredItem, ExistingItem
from trakt_manager.resolver import EntryResolver
from trakt_manager.sync import ListSynchronizer, plan_sync
from trakt_manager.trakt_lists import TraktListsAPI, UserListSummary

UCM_ENTRIES = [
    {"type": "episodes", "query": "WandaVision", "season": 1, "episodes": [8, 9], "block": "1"},
    {"type": "movie", "query": "Shang-Chi", "year": 2021, "block": "1", "note": "Película completa"},
    {"type": "episodes", "query": "Loki", "season": 2, "episodes": [1, 6], "block": "2"},
    {"type": "movie", "query": "Spider-Man: No Way Home", "year": 2021, "block": "1", "note": "Película completa"},
]
EXPECTED_ORDER = [("episode", 7108), ("episode", 7109), ("movie", 1), ("episode", 8201), ("episode", 8206), ("movie", 2)]


def make_definition(entries: list[dict] | None = None, **metadata):
    """Definición de prueba con las entradas del UCM por defecto."""
    return parse_definition_data({"name": "Ruta UCM", "entries": entries or UCM_ENTRIES, **metadata})


def make_synchronizer(trakt_client, has_session: bool = True) -> ListSynchronizer:
    """Sincronizador conectado al Trakt simulado."""
    return ListSynchronizer(EntryResolver(trakt_client), TraktListsAPI(trakt_client), lambda: has_session)


def desired(kind: str, trakt_id: int, notes: str | None = None) -> DesiredItem:
    return DesiredItem(kind=kind, trakt_id=trakt_id, notes=notes, label=f"{kind}-{trakt_id}")


def existing(list_item_id: int, rank: int, kind: str, trakt_id: int, notes: str | None = None) -> ExistingItem:
    return ExistingItem(list_item_id=list_item_id, rank=rank, kind=kind, trakt_id=trakt_id, notes=notes, label=f"{kind}-{trakt_id}")


SUMMARY = UserListSummary(
    trakt_id=50, slug="ruta-ucm", name="Ruta UCM", privacy="private", item_count=0, description="",
    display_numbers=True, allow_comments=False, sort_by="rank", sort_how="asc",
)


# --- plan_sync (función pura) -----------------------------------------------------------------


def test_plan_for_new_list_adds_everything() -> None:
    """Si la lista no existe, el plan la crea y añade todos los elementos."""
    items = [desired("movie", 1), desired("episode", 2)]
    plan = plan_sync(make_definition(), items, None, [])
    assert plan.create_list and plan.to_add == items and not plan.to_remove


def test_plan_without_changes_is_empty() -> None:
    """Si la lista ya coincide, el plan no tiene cambios."""
    plan = plan_sync(
        make_definition(),
        [desired("movie", 1, "n"), desired("episode", 2)],
        SUMMARY,
        [existing(100, 1, "movie", 1, "n"), existing(101, 2, "episode", 2)],
    )
    assert not plan.has_changes


def test_plan_removes_dropped_items_and_reorders() -> None:
    """Lo que ya no está en la definición se quita y el resto se reordena si hace falta."""
    plan = plan_sync(
        make_definition(),
        [desired("movie", 3), desired("movie", 1)],
        SUMMARY,
        [existing(100, 1, "movie", 1), existing(101, 2, "movie", 2), existing(102, 3, "movie", 3)],
    )
    assert [item.trakt_id for item in plan.to_remove] == [2]
    assert plan.reorder is True
    assert plan.to_add == []


def test_plan_detects_metadata_and_note_changes() -> None:
    """Cambios de privacidad y de nota aparecen en el plan."""
    plan = plan_sync(
        make_definition(privacy="public"),
        [desired("movie", 1, "nueva")],
        SUMMARY,
        [existing(100, 1, "movie", 1, "vieja")],
    )
    assert [change.field for change in plan.metadata_changes] == ["privacy"]
    assert [(update.current_notes, update.desired_notes) for update in plan.note_updates] == [("vieja", "nueva")]


def test_plan_adds_each_item_once_even_with_shared_notes() -> None:
    """Regresión: cinco películas con la misma nota se añaden las cinco, una vez cada una."""
    shared = "1. Inicio del Multiverso | Película completa"
    items = [desired("movie", trakt_id, shared) for trakt_id in (1, 2, 3, 4, 5)]
    plan = plan_sync(make_definition(), items + [desired("movie", 3, shared)], None, [])
    assert [item.trakt_id for item in plan.to_add] == [1, 2, 3, 4, 5]
    assert plan.duplicates_skipped == ["movie-3"]


# --- ListSynchronizer sobre el Trakt simulado -------------------------------------------------


def test_first_sync_creates_list_in_definition_order(trakt_client, fake_trakt: FakeTrakt) -> None:
    """La primera sincronización crea la lista con todo en el orden de la definición."""
    result = make_synchronizer(trakt_client).sync(make_definition())
    fake_list = fake_trakt.list_named("Ruta UCM")
    assert result.applied
    assert fake_trakt.item_keys(fake_list) == EXPECTED_ORDER
    assert fake_list.metadata["sort_by"] == "rank" and fake_list.metadata["sort_how"] == "asc"
    notes = [item["notes"] for item in sorted(fake_list.items, key=lambda i: i["rank"])]
    assert notes[2] == "1 | Película completa" and notes[5] == "1 | Película completa"


def test_shared_notes_regression_end_to_end(trakt_client, fake_trakt: FakeTrakt) -> None:
    """Regresión del script original: películas con la misma nota acaban todas en la lista."""
    entries = [
        {"type": "movie", "query": title, "block": "1. Inicio del Multiverso", "note": "Película completa"}
        for title in ("Shang-Chi", "Spider-Man", "Doctor Strange", "X-Men: The Last", "X-Men Origins")
    ]
    make_synchronizer(trakt_client).sync(make_definition(entries))
    assert fake_trakt.item_keys(fake_trakt.list_named("Ruta UCM")) == [("movie", i) for i in (1, 2, 3, 5, 6)]


def test_second_sync_changes_nothing(trakt_client, fake_trakt: FakeTrakt) -> None:
    """Repetir la sincronización no añade, quita, duplica ni reordena nada."""
    synchronizer = make_synchronizer(trakt_client)
    synchronizer.sync(make_definition())
    fake_trakt.requests.clear()

    result = synchronizer.sync(make_definition())
    assert not result.plan.has_changes and not result.applied
    assert fake_trakt.write_requests() == []
    assert len(fake_trakt.lists) == 1


def test_removed_entry_disappears_and_order_is_kept(trakt_client, fake_trakt: FakeTrakt) -> None:
    """Quitar una entrada de la definición la quita de la lista y el resto mantiene el orden."""
    synchronizer = make_synchronizer(trakt_client)
    synchronizer.sync(make_definition())
    synchronizer.sync(make_definition([UCM_ENTRIES[0], UCM_ENTRIES[3], UCM_ENTRIES[2]]))
    assert fake_trakt.item_keys(fake_trakt.list_named("Ruta UCM")) == [
        ("episode", 7108), ("episode", 7109), ("movie", 2), ("episode", 8201), ("episode", 8206),
    ]


def test_pinned_list_id_updates_renamed_list(trakt_client, fake_trakt: FakeTrakt) -> None:
    """Con trakt_list_id se actualiza esa lista aunque se haya renombrado en Trakt."""
    renamed = fake_trakt.create_list("Nombre cambiado a mano")
    make_synchronizer(trakt_client).sync(make_definition(trakt_list_id=renamed.trakt_id))
    assert len(fake_trakt.lists) == 1
    assert renamed.metadata["name"] == "Ruta UCM"
    assert fake_trakt.item_keys(renamed) == EXPECTED_ORDER


def test_existing_list_is_reordered_to_match(trakt_client, fake_trakt: FakeTrakt) -> None:
    """Una lista existente con el orden cambiado se reordena según la definición."""
    synchronizer = make_synchronizer(trakt_client)
    synchronizer.sync(make_definition())
    fake_list = fake_trakt.list_named("Ruta UCM")
    fake_list.items.reverse()
    FakeTrakt._renumber(fake_list)

    synchronizer.sync(make_definition())
    assert fake_trakt.item_keys(fake_list) == EXPECTED_ORDER


def test_dry_run_sends_no_writes(trakt_client, fake_trakt: FakeTrakt) -> None:
    """La previsualización calcula el plan sin enviar ninguna petición que modifique datos."""
    result = make_synchronizer(trakt_client).sync(make_definition(), dry_run=True)
    assert result.dry_run and not result.applied
    assert len(result.plan.to_add) == 6
    assert fake_trakt.write_requests() == []
    assert fake_trakt.lists == {}


def test_dry_run_without_session_treats_list_as_new(trakt_client, fake_trakt: FakeTrakt) -> None:
    """Sin sesión la previsualización funciona y supone que la lista no existe."""
    result = make_synchronizer(trakt_client, has_session=False).sync(make_definition(), dry_run=True)
    assert result.plan.create_list and not result.plan.compared_with_account
    assert not any(path.startswith("/users") for _, path in fake_trakt.requests)


def test_real_sync_without_session_fails(trakt_client) -> None:
    """Sincronizar de verdad sin sesión pide autenticarse."""
    with pytest.raises(NotAuthenticatedError, match="auth login"):
        make_synchronizer(trakt_client, has_session=False).sync(make_definition())


def test_ignored_notes_produce_a_single_warning(trakt_client, fake_trakt: FakeTrakt) -> None:
    """Si Trakt no guarda las notas (cuenta no VIP) se avisa sin fallar."""
    fake_trakt.notes_supported = False
    result = make_synchronizer(trakt_client).sync(make_definition())
    assert fake_trakt.item_keys(fake_trakt.list_named("Ruta UCM")) == EXPECTED_ORDER
    assert len(result.warnings) == 1 and "VIP" in result.warnings[0]


# --- Consulta de listas -----------------------------------------------------------------------


def test_lists_user_lists_and_items(trakt_client, fake_trakt: FakeTrakt) -> None:
    """Se obtienen las listas del usuario y los elementos de una lista en orden."""
    make_synchronizer(trakt_client).sync(make_definition())
    api = TraktListsAPI(trakt_client)
    [summary] = api.get_user_lists()
    assert (summary.name, summary.privacy, summary.item_count) == ("Ruta UCM", "private", 6)
    labels = [item.label for item in api.get_items(summary.trakt_id)]
    assert labels[:3] == ["WandaVision S01E08", "WandaVision S01E09", "Shang-Chi and the Legend of the Ten Rings (2021)"]
