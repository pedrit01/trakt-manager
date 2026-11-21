"""Configuración de trakt-manager leída de variables de entorno.

Toda la configuración llega por entorno para que el contenedor Docker se pueda
configurar con un fichero ``.env`` sin modificar el proyecto. Fuera de Docker
también se lee un ``.env`` del directorio actual, si existe, por comodidad.

Variables admitidas (todas opcionales a nivel de carga; cada operación exige las
que necesita mediante los métodos ``require_*``):

- ``TRAKT_CLIENT_ID`` / ``TRAKT_CLIENT_SECRET``: credenciales de la aplicación de Trakt
  (el secreto es opcional: las aplicaciones nuevas de Trakt no lo tienen).
- ``API_KEY``: clave que deben enviar los clientes de la API HTTP.
- ``DATA_DIR``: directorio donde se guarda el token (por defecto ``./data``).
- ``LISTS_DIR``: directorio de definiciones de listas (por defecto ``./lists``).
- ``REQUEST_DELAY``: pausa mínima en segundos entre peticiones a Trakt.
- ``API_HOST`` / ``API_PORT``: dirección y puerto en los que escucha la API.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from trakt_manager.errors import ConfigError

TOKEN_FILE_NAME = "token.json"
SAVED_LISTS_DIR_NAME = "lists"


class Settings(BaseSettings):
    """Valores de configuración de la aplicación."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    trakt_client_id: str | None = None
    trakt_client_secret: str | None = None
    api_key: str | None = None
    data_dir: Path = Path("data")
    lists_dir: Path = Path("lists")
    request_delay: float = 0.2
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def token_path(self) -> Path:
        """Ruta del fichero donde se guarda el token OAuth de Trakt."""
        return self.data_dir / TOKEN_FILE_NAME

    @property
    def saved_lists_dir(self) -> Path:
        """Directorio escribible donde la GUI guarda definiciones (``DATA_DIR/lists``)."""
        return self.data_dir / SAVED_LISTS_DIR_NAME

    def require_client_id(self) -> str:
        """Devuelve el Client ID de Trakt.

        Raises:
            ConfigError: Si ``TRAKT_CLIENT_ID`` no está configurado.
        """
        return _require(self.trakt_client_id, "TRAKT_CLIENT_ID")

    def require_api_key(self) -> str:
        """Devuelve la clave de la API HTTP.

        Raises:
            ConfigError: Si ``API_KEY`` no está configurada.
        """
        return _require(self.api_key, "API_KEY")


def _require(value: str | None, variable_name: str) -> str:
    """Devuelve ``value`` si tiene contenido o lanza un error que nombra la variable.

    Una cadena vacía se considera ausente: es lo que queda en un ``.env`` copiado
    de ``.env.example`` sin rellenar.

    Raises:
        ConfigError: Si el valor es ``None`` o solo contiene espacios.
    """
    if value is None or not value.strip():
        raise ConfigError(f"Falta la variable de entorno {variable_name}.")
    return value.strip()
