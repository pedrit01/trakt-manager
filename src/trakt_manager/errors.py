"""Jerarquía de errores de trakt-manager.

Todas las excepciones propias heredan de :class:`TraktManagerError`, de modo que
el CLI y la API pueden capturarlas en un único punto y traducirlas a un código de
salida o a una respuesta HTTP sin conocer cada caso concreto.
"""

from dataclasses import dataclass


class TraktManagerError(Exception):
    """Error base de la aplicación. Su mensaje está pensado para mostrarse al usuario."""


class ConfigError(TraktManagerError):
    """Falta o es incorrecta una opción de configuración (normalmente una variable de entorno)."""


class NotAuthenticatedError(TraktManagerError):
    """La operación necesita una sesión de Trakt y no hay ningún token guardado."""


class AuthError(TraktManagerError):
    """La autorización con Trakt ha fallado (código rechazado, renovación denegada, etc.)."""


class DeviceCodeExpiredError(AuthError):
    """El código del device flow ha caducado sin que el usuario lo confirmase."""


class ListNotFoundError(TraktManagerError):
    """La lista de Trakt indicada (por identificador o nombre) no existe en la cuenta."""


class TraktAPIError(TraktManagerError):
    """Trakt ha respondido con un error o no se ha podido contactar con él.

    Atributos:
        status_code: Código HTTP devuelto por Trakt, o ``None`` si falló la conexión.
        method: Método HTTP de la petición que falló.
        path: Ruta de la API de Trakt que falló.
        detail: Cuerpo de la respuesta o descripción del error de red.
    """

    def __init__(self, status_code: int | None, method: str, path: str, detail: str) -> None:
        self.status_code = status_code
        self.method = method
        self.path = path
        self.detail = detail
        status_text = f"HTTP {status_code}" if status_code is not None else "sin conexión"
        super().__init__(f"Error de Trakt en {method} {path} ({status_text}): {detail}")


@dataclass(frozen=True)
class DefinitionIssue:
    """Un problema concreto encontrado al validar una definición de lista.

    Atributos:
        entry_position: Posición de la entrada afectada empezando en 1, o ``None``
            si el problema está en los metadatos de la lista.
        field: Campo afectado (por ejemplo ``season`` o ``privacy``).
        message: Explicación legible del problema.
    """

    entry_position: int | None
    field: str
    message: str

    def describe(self) -> str:
        """Devuelve el problema como una línea de texto para mostrar al usuario."""
        location = f"entrada {self.entry_position}" if self.entry_position else "lista"
        return f"{location}, campo '{self.field}': {self.message}"


class DefinitionError(TraktManagerError):
    """Una definición de lista no se puede cargar o no es válida.

    Atributos:
        issues: Todos los problemas encontrados, no solo el primero.
    """

    def __init__(self, issues: list[DefinitionIssue]) -> None:
        self.issues = issues
        summary = "; ".join(issue.describe() for issue in issues)
        super().__init__(f"La definición no es válida: {summary}")
