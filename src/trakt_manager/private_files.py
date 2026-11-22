"""Lectura y escritura de ficheros JSON privados (token de Trakt, configuración guardada).

Ambos contienen secretos, así que se escriben siempre igual: con permisos ``600``
(solo su propietario puede leerlos) y de forma atómica, para que un corte a mitad
de la escritura nunca deje un fichero corrupto.
"""

import json
import os
from pathlib import Path
from typing import Any


def write_private_json(path: Path, data: dict[str, Any]) -> None:
    """Escribe ``data`` como JSON en ``path`` con permisos ``600`` y de forma atómica.

    Se escribe primero en un fichero temporal del mismo directorio y luego se
    renombra sobre el definitivo; el renombrado es atómico en el mismo sistema
    de ficheros.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    file_descriptor = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as output:
        json.dump(data, output, indent=2)
    # os.open no aplica el modo si el fichero temporal ya existía: se fuerza aquí.
    os.chmod(temporary_path, 0o600)
    os.replace(temporary_path, path)


def read_json_object(path: Path) -> dict[str, Any] | None:
    """Lee un objeto JSON de ``path``.

    Returns:
        El objeto leído, o ``None`` si el fichero no existe, no se puede leer o
        no contiene un objeto JSON (un fichero corrupto se trata como ausente).
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
