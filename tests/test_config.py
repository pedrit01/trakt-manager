"""Tests de la lectura de configuración desde el entorno."""

from pathlib import Path

import pytest

from trakt_manager.config import Settings
from trakt_manager.errors import ConfigError


def make_settings(**values: object) -> Settings:
    """Crea una configuración sin leer ningún fichero .env del disco."""
    return Settings(_env_file=None, **values)


def test_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Las variables de entorno se cargan en sus campos correspondientes."""
    monkeypatch.setenv("TRAKT_CLIENT_ID", "id-123")
    monkeypatch.setenv("DATA_DIR", "/data")
    settings = make_settings()
    assert settings.require_client_id() == "id-123"
    assert settings.token_path == Path("/data/token.json")


@pytest.mark.parametrize(
    ("method_name", "variable_name"),
    [
        ("require_client_id", "TRAKT_CLIENT_ID"),
        ("require_client_secret", "TRAKT_CLIENT_SECRET"),
        ("require_api_key", "API_KEY"),
    ],
)
def test_missing_value_names_the_variable(
    monkeypatch: pytest.MonkeyPatch, method_name: str, variable_name: str
) -> None:
    """Si falta un valor obligatorio, el error nombra la variable de entorno."""
    monkeypatch.delenv(variable_name, raising=False)
    settings = make_settings()
    with pytest.raises(ConfigError, match=variable_name):
        getattr(settings, method_name)()


def test_empty_value_counts_as_missing() -> None:
    """Una variable vacía (como en un .env sin rellenar) se trata como ausente."""
    settings = make_settings(trakt_client_id="  ")
    with pytest.raises(ConfigError, match="TRAKT_CLIENT_ID"):
        settings.require_client_id()
