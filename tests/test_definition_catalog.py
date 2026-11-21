"""Tests del catálogo de definiciones (incluidas y guardadas) y de sus rutas en la API."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import make_runtime
from trakt_manager.api import CONTENT_SECURITY_POLICY, create_app
from trakt_manager.definition_catalog import DefinitionCatalog
from trakt_manager.errors import DefinitionError, DefinitionNotDeletableError, InvalidDefinitionNameError

VALID_YAML = "# comentario que debe conservarse\nname: Maratón\nentries:\n  - {type: movie, query: Dune}\n"
HEADERS = {"X-API-Key": "k"}


@pytest.fixture
def catalog(tmp_path: Path) -> DefinitionCatalog:
    """Catálogo con 'doomsday' incluida y un directorio de guardadas vacío."""
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "doomsday.yaml").write_text("name: Doomsday\nentries: [{type: movie, query: X}]\n", encoding="utf-8")
    return DefinitionCatalog(bundled, tmp_path / "data" / "lists")


def test_saved_definition_keeps_original_text(catalog: DefinitionCatalog) -> None:
    """Una definición guardada aparece como 'saved' y conserva su texto (y comentarios)."""
    catalog.save("maraton", VALID_YAML, "yaml")
    assert [(entry.name, entry.origin) for entry in catalog.entries()] == [("doomsday", "bundled"), ("maraton", "saved")]
    assert catalog.read_source("maraton")[0] == VALID_YAML


def test_invalid_definition_is_not_saved(catalog: DefinitionCatalog) -> None:
    """Una definición inválida no se guarda."""
    with pytest.raises(DefinitionError):
        catalog.save("rota", "name: X\nentries: [{type: movie}]\n", "yaml")
    assert [entry.name for entry in catalog.entries()] == ["doomsday"]


@pytest.mark.parametrize("name", ["../secreto", "a/b", "Mayusculas", "", "-empieza-por-guion", "x" * 65])
def test_unsafe_names_are_rejected(catalog: DefinitionCatalog, tmp_path: Path, name: str) -> None:
    """Los nombres que no son minúsculas, números y guiones se rechazan sin escribir nada."""
    with pytest.raises(InvalidDefinitionNameError):
        catalog.save(name, VALID_YAML, "yaml")
    assert not (tmp_path / "data").exists()


def test_saved_definition_wins_over_bundled(catalog: DefinitionCatalog) -> None:
    """Una guardada con el mismo nombre sustituye a la incluida."""
    catalog.save("doomsday", VALID_YAML, "yaml")
    assert catalog.find("doomsday").origin == "saved"
    assert catalog.load("doomsday").name == "Maratón"


def test_bundled_definition_cannot_be_deleted(catalog: DefinitionCatalog) -> None:
    """Las definiciones incluidas no se pueden borrar."""
    with pytest.raises(DefinitionNotDeletableError):
        catalog.delete("doomsday")


def test_saving_in_another_format_replaces_previous_file(catalog: DefinitionCatalog) -> None:
    """Guardar en JSON una definición que estaba en YAML no deja dos versiones."""
    catalog.save("maraton", VALID_YAML, "yaml")
    catalog.save("maraton", '{"name": "JSON", "entries": [{"type": "movie", "query": "Dune"}]}', "json")
    assert catalog.find("maraton").path.suffix == ".json"
    assert len(catalog.entries()) == 2


# --- rutas de la API --------------------------------------------------------------------------


def make_api(tmp_path: Path, fake_trakt) -> TestClient:
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "doomsday.yaml").write_text(yaml.safe_dump({"name": "Doomsday", "entries": [{"type": "movie", "query": "Shang-Chi"}]}), encoding="utf-8")
    runtime = make_runtime(tmp_path / "data", fake_trakt, api_key="k", trakt_client_id="id", trakt_client_secret="s", lists_dir=bundled)
    return TestClient(create_app(runtime))


def test_save_list_download_and_delete_through_api(tmp_path, fake_trakt) -> None:
    """PUT guarda, GET lista y descarga el original, y DELETE borra una definición guardada."""
    api = make_api(tmp_path, fake_trakt)
    yaml_headers = {**HEADERS, "Content-Type": "application/yaml"}
    assert api.put("/definitions/maraton", headers=yaml_headers, content=VALID_YAML).status_code == 200
    origins = {item["name"]: item["origin"] for item in api.get("/definitions", headers=HEADERS).json()}
    assert origins == {"doomsday": "bundled", "maraton": "saved"}

    source = api.get("/definitions/maraton/source", headers=HEADERS)
    assert source.text == VALID_YAML and "maraton.yaml" in source.headers["content-disposition"]

    assert api.post("/definitions/maraton/sync?dry_run=true", headers=HEADERS).status_code == 200
    assert api.delete("/definitions/maraton", headers=HEADERS).json() == {"deleted": True}
    assert api.get("/definitions/maraton", headers=HEADERS).status_code == 404


def test_invalid_definition_through_api_returns_422(tmp_path, fake_trakt) -> None:
    """Guardar una definición inválida responde 422 con los errores."""
    response = make_api(tmp_path, fake_trakt).put("/definitions/rota", headers=HEADERS, json={"name": "X", "entries": [{"type": "movie"}]})
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "query"


def test_path_traversal_name_returns_422_without_writing(tmp_path, fake_trakt) -> None:
    """Un nombre con '..' y '/' codificada responde 422 y no escribe ningún fichero."""
    api = make_api(tmp_path, fake_trakt)
    response = api.put("/definitions/..%2Fsecreto", headers=HEADERS, content=VALID_YAML)
    assert response.status_code == 422
    assert not list(tmp_path.rglob("secreto*"))


def test_deleting_bundled_definition_returns_409(tmp_path, fake_trakt) -> None:
    """Borrar una definición incluida responde 409."""
    assert make_api(tmp_path, fake_trakt).delete("/definitions/doomsday", headers=HEADERS).status_code == 409


def test_saved_definition_overrides_bundled_in_api(tmp_path, fake_trakt) -> None:
    """GET /definitions/{nombre} devuelve la guardada si hay una incluida con el mismo nombre."""
    api = make_api(tmp_path, fake_trakt)
    api.put("/definitions/doomsday", headers={**HEADERS, "Content-Type": "application/yaml"}, content=VALID_YAML)
    definition = api.get("/definitions/doomsday", headers=HEADERS).json()
    assert (definition["origin"], definition["name"]) == ("saved", "Maratón")


# --- GUI estática -----------------------------------------------------------------------------


def test_gui_is_served_with_csp_and_api_still_works(tmp_path, fake_trakt) -> None:
    """La raíz sirve el HTML con la CSP y las rutas de la API siguen respondiendo."""
    api = make_api(tmp_path, fake_trakt)
    page = api.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert page.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert api.get("/health").json()["status"] == "ok"
    assert "content-security-policy" not in api.get("/docs").headers
