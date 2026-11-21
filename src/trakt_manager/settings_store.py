"""Configuración guardada desde la GUI y su combinación con el entorno.

Las credenciales de Trakt y la ``API_KEY`` pueden llegar de dos sitios:

1. Variables de entorno (o el ``.env``): mandan siempre y no se pueden cambiar
   desde la GUI. Es lo que usa quien configura el contenedor con compose.
2. El fichero ``DATA_DIR/settings.json``, que escribe la GUI: se usa para cada
   clave que no venga del entorno. Es lo que permite usar la imagen publicada
   sin ``.env`` ni comandos.

:func:`resolve_settings` combina ambas fuentes y anota de dónde sale cada clave,
para que la GUI pueda mostrar qué es editable.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from trakt_manager.config import Settings
from trakt_manager.private_files import read_json_object, write_private_json

SETTINGS_FILE_NAME = "settings.json"

# Claves configurables desde la GUI y la variable de entorno equivalente.
CONFIGURABLE_KEYS: dict[str, str] = {
    "trakt_client_id": "TRAKT_CLIENT_ID",
    "trakt_client_secret": "TRAKT_CLIENT_SECRET",
    "api_key": "API_KEY",
}

SettingSource = Literal["env", "stored", "missing"]


class SettingsStore:
    """Guarda las claves configurables en ``DATA_DIR/settings.json`` (permisos ``600``).

    Args:
        path: Ruta del fichero de configuración guardada.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        """Devuelve las claves guardadas que tienen valor (solo las configurables)."""
        data = read_json_object(self.path) or {}
        return {
            key: str(value).strip()
            for key, value in data.items()
            if key in CONFIGURABLE_KEYS and isinstance(value, str) and value.strip()
        }

    def update(self, changes: dict[str, str | None]) -> None:
        """Cambia algunas claves guardadas y conserva las demás.

        Args:
            changes: Claves a cambiar; un valor ``None`` o vacío borra esa clave.

        Raises:
            ValueError: Si alguna clave no es configurable.
        """
        unknown = set(changes) - set(CONFIGURABLE_KEYS)
        if unknown:
            raise ValueError(f"Claves no configurables: {', '.join(sorted(unknown))}")
        values = self.load()
        for key, value in changes.items():
            if value is None or not value.strip():
                values.pop(key, None)
            else:
                values[key] = value.strip()
        write_private_json(self.path, values)


@dataclass(frozen=True)
class ResolvedSettings:
    """Configuración efectiva y el origen de cada clave configurable.

    Atributos:
        settings: Configuración que debe usar la aplicación.
        sources: Para cada clave de ``CONFIGURABLE_KEYS``: ``env``, ``stored`` o ``missing``.
    """

    settings: Settings
    sources: dict[str, SettingSource]

    @property
    def missing_variables(self) -> list[str]:
        """Nombres de variable de las claves que faltan (por ejemplo ``API_KEY``)."""
        return [CONFIGURABLE_KEYS[key] for key, source in self.sources.items() if source == "missing"]

    @property
    def is_complete(self) -> bool:
        """Indica si están las tres claves y el servicio puede salir del modo configuración."""
        return not self.missing_variables


def settings_store_for(settings: Settings) -> SettingsStore:
    """Almacén de configuración del directorio de datos de ``settings``."""
    return SettingsStore(settings.data_dir / SETTINGS_FILE_NAME)


def resolve_settings(env_settings: Settings, store: SettingsStore) -> ResolvedSettings:
    """Combina la configuración del entorno con la guardada.

    Una clave cuenta como "del entorno" si se indicó al crear ``env_settings``
    (variable de entorno, ``.env`` o argumento) y no está vacía; una cadena vacía,
    como la de un ``.env`` copiado sin rellenar, no cuenta y deja pasar el valor
    guardado.

    Args:
        env_settings: Configuración leída del entorno.
        store: Configuración guardada desde la GUI.
    """
    stored = store.load()
    effective_values: dict[str, str | None] = {}
    sources: dict[str, SettingSource] = {}

    for key in CONFIGURABLE_KEYS:
        env_value = getattr(env_settings, key)
        if key in env_settings.model_fields_set and env_value and env_value.strip():
            effective_values[key], sources[key] = env_value.strip(), "env"
        elif key in stored:
            effective_values[key], sources[key] = stored[key], "stored"
        else:
            effective_values[key], sources[key] = None, "missing"

    # model_copy mantiene el resto de opciones (directorios, puerto...) tal cual.
    return ResolvedSettings(settings=env_settings.model_copy(update=effective_values), sources=sources)
