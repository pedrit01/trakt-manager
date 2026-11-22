"""Tests de AppRuntime: configuración efectiva, recarga en caliente y asistente inicial."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from fake_trakt import FAKE_BASE_URL, FakeTrakt
from trakt_manager.app_context import AppContext, AppRuntime
from trakt_manager.cli import app as cli_app
from trakt_manager.config import Settings
from trakt_manager.errors import AlreadyConfiguredError, ConfigError, InvalidSetupCodeError, SettingFromEnvironmentError
from trakt_manager.settings_store import SettingsStore
from trakt_manager.setup_guard import SetupGuard

SETUP_CODE = "AB12-CD34"
TOKEN = {"access_token": "test-token", "refresh_token": "r", "created_at": 9_999_999_999, "expires_in": 7_776_000}


def make_runtime(tmp_path: Path, fake: FakeTrakt, **env: object) -> AppRuntime:
    """Runtime conectado al Trakt simulado, con los valores de entorno indicados."""

    def factory(settings: Settings) -> AppContext:
        return AppContext(settings, transport=fake.transport(), base_url=FAKE_BASE_URL, sleep=lambda seconds: None)

    settings = Settings(_env_file=None, data_dir=tmp_path, request_delay=0, **env)
    return AppRuntime(settings, context_factory=factory, setup_guard=SetupGuard(lambda: SETUP_CODE))


def test_unconfigured_runtime_issues_setup_code(tmp_path: Path, fake_trakt) -> None:
    """Sin configuración el runtime no está configurado y emite el código."""
    runtime = make_runtime(tmp_path, fake_trakt)
    runtime.start_setup_if_needed()
    assert not runtime.is_configured()
    assert runtime.setup_guard.is_active


def test_complete_setup_saves_and_reloads(tmp_path: Path, fake_trakt) -> None:
    """El asistente guarda las credenciales, genera la API_KEY y aplica todo sin reiniciar."""
    runtime = make_runtime(tmp_path, fake_trakt)
    runtime.start_setup_if_needed()
    api_key = runtime.complete_setup(SETUP_CODE, "client-id", "secret")
    assert len(api_key) >= 40
    assert runtime.is_configured()
    assert runtime.current().settings.api_key == api_key
    assert not runtime.setup_guard.is_active
    with pytest.raises(AlreadyConfiguredError):
        runtime.complete_setup(SETUP_CODE, "otro", "otro")


def test_setup_with_wrong_code_saves_nothing(tmp_path: Path, fake_trakt) -> None:
    """Un código incorrecto no guarda nada."""
    runtime = make_runtime(tmp_path, fake_trakt)
    runtime.start_setup_if_needed()
    with pytest.raises(InvalidSetupCodeError):
        runtime.complete_setup("MALO", "client-id", "secret")
    assert runtime.settings_store.load() == {}


def test_setup_with_empty_client_id_names_the_field(tmp_path: Path, fake_trakt) -> None:
    """Si falta el Client ID se indica el campo y no se guarda nada."""
    runtime = make_runtime(tmp_path, fake_trakt)
    runtime.start_setup_if_needed()
    with pytest.raises(ConfigError, match="TRAKT_CLIENT_ID"):
        runtime.complete_setup(SETUP_CODE, " ", "secret")
    assert runtime.settings_store.load() == {}


def test_setup_keeps_environment_api_key(tmp_path: Path, fake_trakt) -> None:
    """Si la API_KEY viene del entorno, el asistente no genera otra."""
    runtime = make_runtime(tmp_path, fake_trakt, api_key="del-entorno")
    runtime.start_setup_if_needed()
    assert runtime.complete_setup(SETUP_CODE, "client-id", "secret") == ""
    assert runtime.current().settings.api_key == "del-entorno"


def test_reload_uses_new_credentials(tmp_path: Path, fake_trakt) -> None:
    """Tras cambiar las credenciales guardadas, el contexto nuevo las usa."""
    runtime = make_runtime(tmp_path, fake_trakt, api_key="k", trakt_client_secret="s")
    runtime.update_settings({"trakt_client_id": "primera"})
    assert runtime.current().client.client_id == "primera"
    runtime.update_settings({"trakt_client_id": "segunda"})
    assert runtime.current().client.client_id == "segunda"


def test_changing_client_id_closes_trakt_session(tmp_path: Path, fake_trakt) -> None:
    """Cambiar el Client ID cierra la sesión de Trakt (el token era de la otra aplicación)."""
    runtime = make_runtime(tmp_path, fake_trakt, api_key="k")
    runtime.update_settings({"trakt_client_id": "primera", "trakt_client_secret": "s"})
    runtime.current().token_store.save(TOKEN)
    runtime.update_settings({"trakt_client_secret": "otro"})
    assert runtime.current().has_session(), "cambiar solo el secreto no cierra la sesión"
    runtime.update_settings({"trakt_client_id": "segunda"})
    assert not runtime.current().has_session()


def test_environment_keys_cannot_be_changed(tmp_path: Path, fake_trakt) -> None:
    """Las claves que vienen del entorno no se pueden cambiar desde la GUI."""
    runtime = make_runtime(tmp_path, fake_trakt, api_key="del-entorno")
    with pytest.raises(SettingFromEnvironmentError, match="api_key"):
        runtime.regenerate_api_key()


def test_regenerated_api_key_replaces_previous(tmp_path: Path, fake_trakt) -> None:
    """Regenerar la API_KEY la cambia al instante en el contexto vigente."""
    runtime = make_runtime(tmp_path, fake_trakt)
    runtime.start_setup_if_needed()
    first = runtime.complete_setup(SETUP_CODE, "client-id", "secret")
    second = runtime.regenerate_api_key()
    assert second != first
    assert runtime.current().settings.api_key == second


def test_cli_uses_credentials_saved_from_the_gui(tmp_path: Path, fake_trakt, monkeypatch: pytest.MonkeyPatch) -> None:
    """El CLI, sin variables de entorno, usa las credenciales guardadas desde la GUI."""
    SettingsStore(tmp_path / "settings.json").update({"trakt_client_id": "id", "trakt_client_secret": "s", "api_key": "k"})
    for variable in ("TRAKT_CLIENT_ID", "TRAKT_CLIENT_SECRET", "API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)  # sin .env en el directorio actual

    context = AppRuntime(Settings()).current()
    assert context.settings.require_client_id() == "id"
    # El mismo contexto, conectado al simulado, sirve al CLI.
    fake_context = AppContext(context.settings, transport=fake_trakt.transport(), base_url=FAKE_BASE_URL)
    fake_context.token_store.save(TOKEN)
    result = CliRunner().invoke(cli_app, ["auth", "status"], obj=fake_context)
    assert "Sesión activa como pedro" in result.output
