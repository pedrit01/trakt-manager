"""Tests de la API en modo configuración, del asistente y de la gestión de la configuración."""

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import make_runtime
from trakt_manager.api import create_app

SETUP_CODE = "AB12-CD34"
SETUP_BODY = {"setup_code": SETUP_CODE, "trakt_client_id": "client-id", "trakt_client_secret": "valor-secreto-123"}


def unconfigured_api(tmp_path: Path, fake_trakt, **env) -> TestClient:
    """API sin configurar (sin variables de entorno ni configuración guardada)."""
    return TestClient(create_app(make_runtime(tmp_path, fake_trakt, logged_in=False, setup_code=SETUP_CODE, **env)))


def configured_api(tmp_path: Path, fake_trakt) -> tuple[TestClient, str]:
    """API configurada mediante el asistente; devuelve el cliente y la API_KEY generada."""
    api = unconfigured_api(tmp_path, fake_trakt)
    api_key = api.post("/setup", json=SETUP_BODY).json()["api_key"]
    return api, api_key


# --- modo configuración -----------------------------------------------------------------------


def test_starts_in_setup_mode_and_logs_the_code(tmp_path, fake_trakt, caplog: pytest.LogCaptureFixture) -> None:
    """Sin configuración el servicio arranca, /health indica modo configuración y el código va al log."""
    with caplog.at_level(logging.WARNING, logger="trakt_manager.setup"):
        api = unconfigured_api(tmp_path, fake_trakt)
    assert SETUP_CODE in caplog.text
    assert api.get("/health").json() == {"status": "ok", "mode": "setup", "trakt_session": False}
    assert api.get("/setup/status").json()["missing"] == ["TRAKT_CLIENT_ID", "API_KEY"]


def test_protected_routes_return_503_in_setup_mode(tmp_path, fake_trakt) -> None:
    """En modo configuración las rutas protegidas responden 503 indicando qué falta."""
    response = unconfigured_api(tmp_path, fake_trakt).get("/lists", headers={"X-API-Key": "lo-que-sea"})
    assert response.status_code == 503
    assert "API_KEY" in response.json()["missing"]


def test_gui_is_served_in_setup_mode(tmp_path, fake_trakt) -> None:
    """La GUI se sirve aunque el servicio no esté configurado."""
    response = unconfigured_api(tmp_path, fake_trakt).get("/")
    assert response.status_code == 200 and "<html" in response.text


# --- asistente --------------------------------------------------------------------------------


def test_setup_with_correct_code_configures_without_restart(tmp_path, fake_trakt) -> None:
    """El asistente con el código correcto configura el servicio y la clave generada funciona."""
    api, api_key = configured_api(tmp_path, fake_trakt)
    assert api.get("/health").json()["mode"] == "ready"
    assert api.get("/definitions", headers={"X-API-Key": api_key}).status_code == 200


def test_setup_with_wrong_code_returns_403(tmp_path, fake_trakt) -> None:
    """Un código incorrecto responde 403 y no configura nada."""
    api = unconfigured_api(tmp_path, fake_trakt)
    assert api.post("/setup", json=dict(SETUP_BODY, setup_code="MALO-0000")).status_code == 403
    assert api.get("/health").json()["mode"] == "setup"


def test_setup_with_empty_client_id_returns_422(tmp_path, fake_trakt) -> None:
    """Si falta el Client ID se responde 422 nombrando el campo."""
    response = unconfigured_api(tmp_path, fake_trakt).post("/setup", json=dict(SETUP_BODY, trakt_client_id=""))
    assert response.status_code == 422 and "TRAKT_CLIENT_ID" in response.json()["detail"]


def test_setup_twice_returns_409(tmp_path, fake_trakt) -> None:
    """Repetir el asistente con el servicio ya configurado responde 409."""
    api, _ = configured_api(tmp_path, fake_trakt)
    assert api.post("/setup", json=SETUP_BODY).status_code == 409


# --- ajustes ----------------------------------------------------------------------------------


def test_settings_never_expose_secrets(tmp_path, fake_trakt) -> None:
    """La configuración muestra el Client ID y el origen de cada clave, pero no los secretos."""
    api, api_key = configured_api(tmp_path, fake_trakt)
    response = api.get("/settings", headers={"X-API-Key": api_key})
    assert response.json()["trakt_client_id"] == {"source": "stored", "set": True, "editable": True, "value": "client-id"}
    assert response.json()["api_key"] == {"source": "stored", "set": True, "editable": True}
    assert "valor-secreto-123" not in response.text and api_key not in response.text


def test_regenerated_key_invalidates_previous(tmp_path, fake_trakt) -> None:
    """Tras regenerar la API_KEY, la anterior responde 401 y la nueva funciona."""
    api, old_key = configured_api(tmp_path, fake_trakt)
    new_key = api.post("/settings/api-key", headers={"X-API-Key": old_key}).json()["api_key"]
    assert api.get("/definitions", headers={"X-API-Key": old_key}).status_code == 401
    assert api.get("/definitions", headers={"X-API-Key": new_key}).status_code == 200


def test_changing_client_id_closes_session(tmp_path, fake_trakt) -> None:
    """Cambiar el Client ID desde la GUI cierra la sesión de Trakt."""
    runtime = make_runtime(tmp_path, fake_trakt, logged_in=False, setup_code=SETUP_CODE)
    api = TestClient(create_app(runtime))
    api_key = api.post("/setup", json=SETUP_BODY).json()["api_key"]
    runtime.current().token_store.save({"access_token": "t"})
    headers = {"X-API-Key": api_key}
    assert api.get("/health").json()["trakt_session"] is True
    response = api.put("/settings", headers=headers, json={"trakt_client_id": "otra-app"})
    assert response.json()["trakt_client_id"]["value"] == "otra-app"
    assert api.get("/health").json()["trakt_session"] is False


def test_environment_values_cannot_be_changed(tmp_path, fake_trakt) -> None:
    """Las claves que vienen del entorno se muestran como no editables y no se pueden cambiar."""
    api = TestClient(create_app(make_runtime(tmp_path, fake_trakt, api_key="k", trakt_client_id="id", trakt_client_secret="s")))
    headers = {"X-API-Key": "k"}
    assert api.get("/settings", headers=headers).json()["api_key"]["editable"] is False
    assert api.post("/settings/api-key", headers=headers).status_code == 409
    assert api.put("/settings", headers=headers, json={"trakt_client_id": "otro"}).status_code == 409


def test_empty_client_id_is_rejected_but_secret_can_be_removed(tmp_path, fake_trakt) -> None:
    """El Client ID no puede quedar vacío; el Client Secret sí se puede borrar (es opcional)."""
    api, api_key = configured_api(tmp_path, fake_trakt)
    headers = {"X-API-Key": api_key}
    assert api.put("/settings", headers=headers, json={"trakt_client_id": " "}).status_code == 422
    response = api.put("/settings", headers=headers, json={"trakt_client_secret": ""})
    assert response.status_code == 200
    assert response.json()["trakt_client_secret"]["set"] is False
    assert api.get("/health").json()["mode"] == "ready"


def test_setup_without_client_secret(tmp_path, fake_trakt) -> None:
    """El asistente se completa solo con el Client ID (las apps nuevas de Trakt no tienen secreto)."""
    api = unconfigured_api(tmp_path, fake_trakt)
    response = api.post("/setup", json={"setup_code": SETUP_CODE, "trakt_client_id": "client-id"})
    assert response.status_code == 200 and response.json()["api_key"]
    assert api.get("/health").json()["mode"] == "ready"
