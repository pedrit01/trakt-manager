"""Tests del formato y la validación de las definiciones de listas."""

import json
from pathlib import Path

import pytest
import yaml

from trakt_manager.definitions import (
    EntryType,
    find_definition_files,
    load_definition_file,
    parse_definition_data,
)
from trakt_manager.errors import DefinitionError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOOMSDAY_FILE = PROJECT_ROOT / "lists" / "doomsday.yaml"
ORIGINAL_ROADMAP_FILE = Path(__file__).parent / "fixtures" / "original_roadmap.json"

MINIMAL = {"name": "Mi lista", "entries": [{"type": "movie", "query": "Dune", "year": 2021}]}


def issues_of(data: dict) -> list[tuple[int | None, str]]:
    """Valida ``data`` y devuelve los problemas como pares (posición, campo)."""
    with pytest.raises(DefinitionError) as error:
        parse_definition_data(data)
    return [(issue.entry_position, issue.field) for issue in error.value.issues]


def with_entries(*entries: dict) -> dict:
    """Construye una definición mínima con las entradas indicadas."""
    return {"name": "Mi lista", "entries": list(entries)}


# --- Formatos ---------------------------------------------------------------------------------


def test_yaml_and_json_produce_the_same_definition(tmp_path: Path) -> None:
    """La misma definición en YAML y en JSON da exactamente el mismo resultado."""
    yaml_file = tmp_path / "lista.yaml"
    json_file = tmp_path / "lista.json"
    yaml_file.write_text(yaml.safe_dump(MINIMAL), encoding="utf-8")
    json_file.write_text(json.dumps(MINIMAL), encoding="utf-8")
    assert load_definition_file(yaml_file) == load_definition_file(json_file)


def test_unsupported_extension_lists_allowed_formats(tmp_path: Path) -> None:
    """Un fichero con otra extensión se rechaza indicando los formatos admitidos."""
    path = tmp_path / "lista.txt"
    path.write_text("name: x", encoding="utf-8")
    with pytest.raises(DefinitionError, match=r"\.yaml, \.yml, \.json"):
        load_definition_file(path)


def test_invalid_yaml_is_reported(tmp_path: Path) -> None:
    """Un YAML mal formado da un error de fichero, no una excepción interna."""
    path = tmp_path / "lista.yaml"
    path.write_text("name: [sin cerrar", encoding="utf-8")
    with pytest.raises(DefinitionError, match="YAML no válido"):
        load_definition_file(path)


# --- Metadatos --------------------------------------------------------------------------------


def test_defaults_when_only_name_is_given() -> None:
    """Sin más metadatos, la lista es privada, con números y sin comentarios."""
    definition = parse_definition_data(MINIMAL)
    assert definition.privacy == "private"
    assert definition.display_numbers is True
    assert definition.allow_comments is False


def test_invalid_privacy_points_to_field_and_allowed_values() -> None:
    """Una privacidad no válida señala el campo y los valores permitidos."""
    with pytest.raises(DefinitionError) as error:
        parse_definition_data(dict(MINIMAL, privacy="secret"))
    issue = error.value.issues[0]
    assert (issue.entry_position, issue.field) == (None, "privacy")
    assert "'private'" in issue.message and "'public'" in issue.message


# --- Entradas ---------------------------------------------------------------------------------


def test_episode_entry_keeps_exact_episodes_in_order() -> None:
    """Una entrada de episodios representa exactamente esos episodios en ese orden."""
    definition = parse_definition_data(
        with_entries({"type": "episodes", "query": "Loki", "season": 2, "episodes": [1, 4, 5, 6]})
    )
    entry = definition.entries[0]
    assert entry.type == EntryType.EPISODES
    assert (entry.season, entry.episodes) == (2, [1, 4, 5, 6])


@pytest.mark.parametrize(
    ("entry", "field"),
    [
        ({"type": "episodes", "query": "Loki", "episodes": [1]}, "season"),
        ({"type": "episodes", "query": "Loki", "season": 1, "episodes": []}, "episodes"),
        ({"type": "movie", "year": 2021}, "query"),
        ({"type": "movie", "query": "Dune", "season": 1}, "season"),
        ({"type": "season", "query": "Loki", "season": 1, "episodes": [2]}, "episodes"),
        ({"type": "documental", "query": "Dune"}, "type"),
    ],
)
def test_invalid_entries_point_to_position_and_field(entry: dict, field: str) -> None:
    """Cada regla de las entradas señala la posición y el campo que fallan."""
    assert issues_of(with_entries(entry)) == [(1, field)]


def test_explicit_ids_are_enough_to_identify_an_entry() -> None:
    """Un identificador explícito basta aunque no haya texto de búsqueda."""
    definition = parse_definition_data(with_entries({"type": "movie", "ids": {"imdb": "tt1160419"}}))
    assert definition.entries[0].ids.imdb == "tt1160419"


def test_reports_all_errors_at_once() -> None:
    """Si hay errores en varias entradas se informa de todos con su posición."""
    good = {"type": "movie", "query": "Dune"}
    entries = [good] * 7
    entries[2] = {"type": "episodes", "query": "Loki", "episodes": [1]}
    entries[6] = {"type": "movie"}
    assert issues_of(with_entries(*entries)) == [(3, "season"), (7, "query")]


# --- Extras -----------------------------------------------------------------------------------


def test_extras_are_excluded_unless_requested() -> None:
    """Las entradas extra se omiten por defecto y aparecen en su posición si se piden."""
    definition = parse_definition_data(
        with_entries(
            {"type": "movie", "query": "A"},
            {"type": "movie", "query": "B", "extra": True},
            {"type": "movie", "query": "C"},
        )
    )
    assert [p.entry.query for p in definition.selected_entries(include_extras=False)] == ["A", "C"]
    assert [(p.position, p.entry.query) for p in definition.selected_entries(include_extras=True)] == [
        (1, "A"),
        (2, "B"),
        (3, "C"),
    ]


# --- Ruta Doomsday ----------------------------------------------------------------------------


def test_doomsday_definition_matches_original_script() -> None:
    """La definición migrada conserva las entradas, episodios, notas, bloques y extras del script."""
    definition = load_definition_file(DOOMSDAY_FILE)
    original = json.loads(ORIGINAL_ROADMAP_FILE.read_text(encoding="utf-8"))

    assert definition.name == "Ruta Cronológica hacia Vengadores: Doomsday"
    assert len(definition.selected_entries(include_extras=False)) == 17
    assert sum(entry.extra for entry in definition.entries) == 4
    assert len(definition.entries) == len(original)

    for entry, item in zip(definition.entries, original, strict=True):
        expected_type = EntryType.MOVIE if item["kind"] == "movie" else EntryType.EPISODES
        assert entry.type == expected_type, item["title"]
        assert (entry.title, entry.query, entry.year) == (item["title"], item["query"], item["year"])
        assert entry.block == item["block"]
        assert entry.extra == item["is_extra"]
        assert f"{entry.block} | {entry.note}" == item["note"]
        if expected_type == EntryType.EPISODES:
            assert (entry.season, entry.episodes) == (item["season"], item["episodes"])


def test_find_definition_files_by_name(tmp_path: Path) -> None:
    """Las definiciones de un directorio se indexan por su nombre sin extensión."""
    (tmp_path / "doomsday.yaml").write_text("x", encoding="utf-8")
    (tmp_path / "otra.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notas.txt").write_text("", encoding="utf-8")
    assert list(find_definition_files(tmp_path)) == ["doomsday", "otra"]
