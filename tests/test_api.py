"""Tests de la API HTTP con un Trakt simulado."""

import json
import threading
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from conftest import make_context
from trakt_manager.api import create_app
from trakt_manager.cli import app as cli_app
from trakt_manager.errors import ConfigError

API_KEY = "clave-de-prueba"
HEADERS = {"X-API-Key": API_KEY}
DEFINITION = {
    "name": "Ruta UCM",
    "entries": [
        {"type": "episodes", "query": "WandaVision", "season": 1, "episodes": [8, 9]},
        {"type": "movie", "query": "Shang-Chi", "year": 2021},
    ],
}


@pytest.fixture
def lists_dir(tmp_path: Path) -> Path:
    """Directorio de definiciones con 'ucm.yaml' válida y 'rota.yaml' inválida."""
    directory = tmp_path / "lists"
    directory.mkdir()
    (directory / "ucm.yaml").write_text(yaml.safe_dump(DEFINITION), encoding="utf-8")
    (directory / "rota.yaml").write_text("name: Rota\nentries: [{type: movie}]\n", encoding="utf-8")
    return directory


def make_api(tmp_path: Path, fake_trakt, lists_dir: Path, **options) -> TestClient:
    """Cliente HTTP de pruebas para la API conectada al Trakt simulado."""
    context = make_context(tmp_path / "data", fake_trakt, api_key=API_KEY, lists_dir=lists_dir, **options)
    return TestClient(create_app(context))


# --- seguridad y salud ------------------------------------------------------------------------


def test_requests_without_valid_key_are_rejected(tmp_path, fake_trakt, lists_dir) -> None:
    """Sin X-API-Key, o con una incorrecta, se responde 401 sin hacer nada."""
    api = make_api(tmp_path, fake_trakt, lists_dir)
    assert api.get("/lists").status_code == 401
    assert api.post("/definitions/ucm/sync", headers={"X-API-Key": "otra"}).status_code == 401
    assert fake_trakt.requests == []


def test_app_refuses_to_start_without_api_key(tmp_path, fake_trakt) -> None:
    """Sin API_KEY no se puede crear la aplicación y el error nombra la variable."""
    with pytest.raises(ConfigError, match="API_KEY"):
        create_app(make_context(tmp_path, fake_trakt, api_key=None))


def test_health_needs_no_key_and_reveals_no_secrets(tmp_path, fake_trakt, lists_dir) -> None:
    """/health responde sin clave e indica si hay sesión, sin incluir tokens."""
    response = make_api(tmp_path, fake_trakt, lists_dir).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "trakt_session": True}


# --- autenticación remota ---------------------------------------------------------------------


def test_device_flow_through_the_api(tmp_path, fake_trakt, lists_dir) -> None:
    """POST /auth/device devuelve el código; tras confirmarlo, /auth/status indica sesión."""
    api = make_api(tmp_path, fake_trakt, lists_dir, logged_in=False, sleep=lambda seconds: time.sleep(0.01))

    started = api.post("/auth/device", headers=HEADERS)
    assert started.status_code == 200
    assert started.json() == {"verification_url": "https://trakt.tv/activate", "user_code": "ABCD1234", "expires_in": 600}
    assert api.get("/auth/status", headers=HEADERS).json()["status"] == "pending"

    fake_trakt.device_authorized = True
    deadline = time.time() + 5
    while api.get("/auth/status", headers=HEADERS).json()["status"] != "authorized" and time.time() < deadline:
        time.sleep(0.02)
    assert api.get("/auth/status", headers=HEADERS).json() == {"status": "authorized", "username": "pedro", "error": None}


def test_logout_through_the_api(tmp_path, fake_trakt, lists_dir) -> None:
    """DELETE /auth cierra la sesión."""
    api = make_api(tmp_path, fake_trakt, lists_dir)
    assert api.delete("/auth", headers=HEADERS).json() == {"logged_out": True}
    assert api.get("/health").json()["trakt_session"] is False


# --- definiciones -----------------------------------------------------------------------------


def test_lists_available_definitions(tmp_path, fake_trakt, lists_dir) -> None:
    """GET /definitions incluye cada definición con su nombre de lista y entradas."""
    definitions = make_api(tmp_path, fake_trakt, lists_dir).get("/definitions", headers=HEADERS).json()
    by_name = {definition["name"]: definition for definition in definitions}
    assert (by_name["ucm"]["valid"], by_name["ucm"]["list_name"], by_name["ucm"]["entries"]) == (True, "Ruta UCM", 2)
    assert by_name["rota"]["valid"] is False


def test_get_definition_by_name(tmp_path, fake_trakt, lists_dir) -> None:
    """GET /definitions/{nombre} devuelve la definición o 404 si no existe."""
    api = make_api(tmp_path, fake_trakt, lists_dir)
    assert api.get("/definitions/ucm", headers=HEADERS).json()["name"] == "Ruta UCM"
    assert api.get("/definitions/no-existe", headers=HEADERS).status_code == 404


def test_validate_invalid_definition_returns_422(tmp_path, fake_trakt, lists_dir) -> None:
    """POST /validate con errores responde 422 con la posición y el campo."""
    api = make_api(tmp_path, fake_trakt, lists_dir)
    response = api.post("/validate", headers=HEADERS, json={"name": "X", "entries": [{"type": "movie"}]})
    assert response.status_code == 422
    assert response.json()["errors"][0]["entry_position"] == 1
    assert response.json()["errors"][0]["field"] == "query"


def test_validate_accepts_yaml_body(tmp_path, fake_trakt, lists_dir) -> None:
    """POST /validate acepta YAML si el Content-Type lo indica."""
    api = make_api(tmp_path, fake_trakt, lists_dir)
    response = api.post("/validate", headers={**HEADERS, "Content-Type": "application/yaml"}, content=yaml.safe_dump(DEFINITION))
    assert response.status_code == 200 and response.json()["valid"] is True


# --- sincronización ---------------------------------------------------------------------------


def test_remote_dry_run_does_not_change_account(tmp_path, fake_trakt, lists_dir) -> None:
    """La previsualización remota devuelve el informe y no modifica la cuenta."""
    response = make_api(tmp_path, fake_trakt, lists_dir).post("/definitions/ucm/sync?dry_run=true", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["dry_run"] is True and len(response.json()["plan"]["to_add"]) == 3
    assert fake_trakt.write_requests() == []


def test_sync_from_body_creates_list(tmp_path, fake_trakt, lists_dir) -> None:
    """POST /sync con la definición en el cuerpo crea la lista."""
    response = make_api(tmp_path, fake_trakt, lists_dir).post("/sync", headers=HEADERS, json=DEFINITION)
    assert response.status_code == 200 and response.json()["applied"] is True
    assert len(fake_trakt.list_named("Ruta UCM").items) == 3


def test_sync_without_session_returns_409(tmp_path, fake_trakt, lists_dir) -> None:
    """Sincronizar sin sesión responde 409 indicando que hay que autenticarse."""
    response = make_api(tmp_path, fake_trakt, lists_dir, logged_in=False).post("/definitions/ucm/sync", headers=HEADERS)
    assert response.status_code == 409
    assert "auth login" in response.json()["detail"]


def test_concurrent_sync_of_same_list_returns_409(tmp_path, fake_trakt, lists_dir) -> None:
    """Una sincronización real mientras otra de la misma lista está en curso responde 409."""
    api = make_api(tmp_path, fake_trakt, lists_dir)
    first_sync_started = threading.Event()
    release_first_sync = threading.Event()
    original_handle = fake_trakt.handle

    def slow_handle(request):
        # Bloquea la primera sincronización al crear la lista, hasta que el test la libere.
        if request.method == "POST" and request.url.path == "/users/me/lists":
            first_sync_started.set()
            release_first_sync.wait(timeout=5)
        return original_handle(request)

    fake_trakt.handle = slow_handle
    results: list[int] = []
    worker = threading.Thread(target=lambda: results.append(api.post("/definitions/ucm/sync", headers=HEADERS).status_code))
    worker.start()
    assert first_sync_started.wait(timeout=5)

    second = api.post("/definitions/ucm/sync", headers=HEADERS)
    release_first_sync.set()
    worker.join(timeout=5)
    assert second.status_code == 409
    assert results == [200]
    assert len(fake_trakt.lists) == 1


# --- consulta ---------------------------------------------------------------------------------


def test_lists_and_list_items(tmp_path, fake_trakt, lists_dir) -> None:
    """GET /lists y GET /lists/{id} devuelven las listas y sus elementos en orden."""
    api = make_api(tmp_path, fake_trakt, lists_dir)
    api.post("/definitions/ucm/sync", headers=HEADERS)
    [summary] = api.get("/lists", headers=HEADERS).json()
    assert (summary["name"], summary["privacy"], summary["item_count"]) == ("Ruta UCM", "private", 3)
    items = api.get(f"/lists/{summary['trakt_id']}", headers=HEADERS).json()["items"]
    assert [item["label"] for item in items][:2] == ["WandaVision S01E08", "WandaVision S01E09"]
    assert api.get("/lists/999", headers=HEADERS).status_code == 404


def test_api_response_matches_cli_json(tmp_path, fake_trakt, lists_dir) -> None:
    """La previsualización por la API devuelve lo mismo que 'sync --dry-run --json' del CLI."""
    context = make_context(tmp_path / "data", fake_trakt, api_key=API_KEY, lists_dir=lists_dir)
    api_result = TestClient(create_app(context)).post("/definitions/ucm/sync?dry_run=true", headers=HEADERS).json()
    cli_result = CliRunner().invoke(cli_app, ["sync", str(lists_dir / "ucm.yaml"), "--dry-run", "--json"], obj=context)
    assert json.loads(cli_result.stdout) == api_result
