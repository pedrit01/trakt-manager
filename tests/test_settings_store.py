"""Tests de la configuración guardada y de su combinación con el entorno."""

import stat
from pathlib import Path

import pytest

from trakt_manager.config import Settings
from trakt_manager.settings_store import SettingsStore, resolve_settings


def env_settings(tmp_path: Path, **values: object) -> Settings:
    """Configuración "del entorno" con los valores indicados y sin leer .env."""
    return Settings(_env_file=None, data_dir=tmp_path, **values)


def test_stored_values_are_used_when_environment_has_none(tmp_path: Path) -> None:
    """Sin variables de entorno se usan los valores guardados."""
    store = SettingsStore(tmp_path / "settings.json")
    store.update({"trakt_client_id": "id", "trakt_client_secret": "secret", "api_key": "key"})
    resolved = resolve_settings(env_settings(tmp_path), store)
    assert resolved.settings.require_api_key() == "key"
    assert resolved.sources == {"trakt_client_id": "stored", "trakt_client_secret": "stored", "api_key": "stored"}
    assert resolved.is_complete


def test_environment_wins_over_stored_value(tmp_path: Path) -> None:
    """Un valor del entorno prevalece sobre el guardado."""
    store = SettingsStore(tmp_path / "settings.json")
    store.update({"api_key": "guardada"})
    resolved = resolve_settings(env_settings(tmp_path, api_key="del-entorno"), store)
    assert resolved.settings.api_key == "del-entorno"
    assert resolved.sources["api_key"] == "env"


def test_empty_environment_value_lets_stored_value_through(tmp_path: Path) -> None:
    """Una variable vacía (como en un .env sin rellenar) no tapa el valor guardado."""
    store = SettingsStore(tmp_path / "settings.json")
    store.update({"api_key": "guardada"})
    resolved = resolve_settings(env_settings(tmp_path, api_key=""), store)
    assert (resolved.settings.api_key, resolved.sources["api_key"]) == ("guardada", "stored")


def test_dotenv_file_counts_as_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Lo que viene de un fichero .env cuenta como entorno."""
    (tmp_path / ".env").write_text("API_KEY=de-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("API_KEY", raising=False)
    resolved = resolve_settings(Settings(data_dir=tmp_path), SettingsStore(tmp_path / "settings.json"))
    assert resolved.sources["api_key"] == "env"


def test_missing_values_are_reported_by_variable_name(tmp_path: Path) -> None:
    """Las claves que faltan se informan con el nombre de su variable."""
    resolved = resolve_settings(env_settings(tmp_path, trakt_client_id="id"), SettingsStore(tmp_path / "settings.json"))
    assert resolved.missing_variables == ["TRAKT_CLIENT_SECRET", "API_KEY"]
    assert not resolved.is_complete


def test_settings_file_is_private_and_keeps_other_keys(tmp_path: Path) -> None:
    """El fichero tiene permisos 600 y un cambio parcial conserva el resto de claves."""
    store = SettingsStore(tmp_path / "settings.json")
    store.update({"trakt_client_id": "id", "api_key": "key"})
    store.update({"api_key": None})
    assert store.load() == {"trakt_client_id": "id"}
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    """Solo se pueden guardar las claves configurables."""
    with pytest.raises(ValueError, match="data_dir"):
        SettingsStore(tmp_path / "settings.json").update({"data_dir": "/tmp"})
