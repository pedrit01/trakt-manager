"""Catálogo de definiciones disponibles: las incluidas o montadas y las guardadas desde la GUI.

Hay dos orígenes:

- ``bundled``: ``LISTS_DIR``. Las definiciones que van dentro de la imagen o que se
  montan desde el anfitrión. Son de solo lectura para la aplicación.
- ``saved``: ``DATA_DIR/lists``. Las que el usuario sube o pega en la GUI. Viven en
  el volumen de datos, así que sobreviven a recrear el contenedor.

Si un nombre existe en los dos, gana el guardado: así el usuario puede adaptar
una definición incluida sin tocar la imagen.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from trakt_manager.definitions import (
    SUPPORTED_EXTENSIONS,
    ListDefinition,
    find_definition_files,
    load_definition_file,
    parse_definition_text,
)
from trakt_manager.errors import DefinitionNotDeletableError, DefinitionNotFoundError, InvalidDefinitionNameError

DefinitionOrigin = Literal["bundled", "saved"]

# Solo minúsculas, números y guiones: impide rutas como "../secreto" o nombres con "/".
DEFINITION_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# Extensión con la que se guarda cada formato.
EXTENSION_BY_FORMAT: dict[str, str] = {"yaml": ".yaml", "json": ".json"}


@dataclass(frozen=True)
class CatalogEntry:
    """Una definición del catálogo.

    Atributos:
        name: Nombre de la definición (fichero sin extensión).
        origin: ``bundled`` (incluida o montada) o ``saved`` (guardada desde la GUI).
        path: Fichero de la definición.
    """

    name: str
    origin: DefinitionOrigin
    path: Path

    @property
    def file_format(self) -> Literal["yaml", "json"]:
        """Formato del fichero según su extensión."""
        return SUPPORTED_EXTENSIONS[self.path.suffix.lower()]


class DefinitionCatalog:
    """Une las definiciones incluidas y las guardadas, y gestiona las guardadas.

    Args:
        bundled_dir: Directorio de solo lectura (``LISTS_DIR``).
        saved_dir: Directorio escribible (``DATA_DIR/lists``); se crea al guardar.
    """

    def __init__(self, bundled_dir: Path, saved_dir: Path) -> None:
        self._bundled_dir = bundled_dir
        self._saved_dir = saved_dir

    def entries(self) -> list[CatalogEntry]:
        """Todas las definiciones disponibles, ordenadas por nombre."""
        merged: dict[str, CatalogEntry] = {
            name: CatalogEntry(name, "bundled", path) for name, path in find_definition_files(self._bundled_dir).items()
        }
        # Las guardadas se aplican después para que sustituyan a las incluidas del mismo nombre.
        merged.update(
            {name: CatalogEntry(name, "saved", path) for name, path in find_definition_files(self._saved_dir).items()}
        )
        return [merged[name] for name in sorted(merged)]

    def find(self, name: str) -> CatalogEntry:
        """Devuelve una definición por su nombre.

        Raises:
            DefinitionNotFoundError: Si no existe.
        """
        for entry in self.entries():
            if entry.name == name:
                return entry
        raise DefinitionNotFoundError(f"No existe la definición '{name}'.")

    def load(self, name: str) -> ListDefinition:
        """Carga y valida una definición por su nombre.

        Raises:
            DefinitionNotFoundError: Si no existe.
            DefinitionError: Si no es válida.
        """
        return load_definition_file(self.find(name).path)

    def read_source(self, name: str) -> tuple[str, CatalogEntry]:
        """Devuelve el texto original de una definición (con sus comentarios) y su entrada.

        Raises:
            DefinitionNotFoundError: Si no existe.
        """
        entry = self.find(name)
        return entry.path.read_text(encoding="utf-8"), entry

    def save(self, name: str, text: str, file_format: Literal["yaml", "json"]) -> CatalogEntry:
        """Valida y guarda una definición con el texto tal cual se envió.

        Se guarda el texto original, no una versión regenerada, para conservar
        los comentarios y el formato que escribió el usuario.

        Raises:
            InvalidDefinitionNameError: Si el nombre no es válido.
            DefinitionError: Si la definición no es válida (no se guarda nada).
        """
        validate_definition_name(name)
        parse_definition_text(text, file_format)

        self._saved_dir.mkdir(parents=True, exist_ok=True)
        target = self._saved_dir / f"{name}{EXTENSION_BY_FORMAT[file_format]}"
        # Si antes estaba guardada en otro formato, se borra para no tener dos versiones.
        for existing in self._saved_files(name):
            if existing != target:
                existing.unlink()
        target.write_text(text, encoding="utf-8")
        return CatalogEntry(name, "saved", target)

    def delete(self, name: str) -> None:
        """Borra una definición guardada.

        Raises:
            InvalidDefinitionNameError: Si el nombre no es válido.
            DefinitionNotDeletableError: Si solo existe como incluida o montada.
            DefinitionNotFoundError: Si no existe.
        """
        validate_definition_name(name)
        saved_files = self._saved_files(name)
        if saved_files:
            for path in saved_files:
                path.unlink()
            return
        if name in find_definition_files(self._bundled_dir):
            raise DefinitionNotDeletableError(
                f"'{name}' está incluida en la imagen o montada: solo se pueden borrar las definiciones guardadas."
            )
        raise DefinitionNotFoundError(f"No existe la definición '{name}'.")

    def _saved_files(self, name: str) -> list[Path]:
        """Ficheros guardados con ese nombre (en cualquier formato admitido)."""
        if not self._saved_dir.is_dir():
            return []
        return [path for path in self._saved_dir.iterdir() if path.is_file() and path.stem == name and path.suffix.lower() in SUPPORTED_EXTENSIONS]


def validate_definition_name(name: str) -> None:
    """Comprueba que un nombre de definición es seguro para usarlo como nombre de fichero.

    Raises:
        InvalidDefinitionNameError: Si no cumple ``DEFINITION_NAME_PATTERN``.
    """
    if not DEFINITION_NAME_PATTERN.fullmatch(name):
        raise InvalidDefinitionNameError(
            f"Nombre de definición no válido: '{name}'. Usa solo minúsculas, números y guiones (máximo 64)."
        )
