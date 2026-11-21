"""Código de configuración de un solo uso para el asistente inicial.

Cuando el servicio arranca sin configurar, cualquiera que llegue a la GUI podría
completar el asistente y quedarse con la instancia. Docker Desktop publica los
puertos en todas las interfaces por defecto, así que "cualquiera" incluye otros
equipos de la red.

Para evitarlo, el servicio genera un código aleatorio y lo escribe en sus
registros: solo quien controla el contenedor puede verlo (Docker Desktop y
OrbStack muestran los registros en su propia interfaz). El asistente exige ese
código, que deja de valer en cuanto se completa la configuración.
"""

import logging
import secrets
import threading
from collections.abc import Callable

# Fallos permitidos antes de cambiar el código, para frenar los intentos a ciegas.
MAX_FAILED_ATTEMPTS = 10

logger = logging.getLogger("trakt_manager.setup")


def generate_setup_code() -> str:
    """Genera un código legible del tipo ``A1B2-C3D4`` (32 bits aleatorios)."""
    raw = secrets.token_hex(4).upper()
    return f"{raw[:4]}-{raw[4:]}"


class SetupGuard:
    """Emite, comprueba e invalida el código de configuración.

    El código solo vive en memoria: cada arranque sin configurar emite uno nuevo,
    así que nunca queda un código antiguo válido en disco.

    Args:
        code_factory: Función que genera códigos; los tests la sustituyen.
    """

    def __init__(self, code_factory: Callable[[], str] = generate_setup_code) -> None:
        self._code_factory = code_factory
        self._code: str | None = None
        self._failed_attempts = 0
        self._lock = threading.Lock()

    @property
    def is_active(self) -> bool:
        """Indica si hay un código vigente (el servicio está en modo configuración)."""
        return self._code is not None

    def issue(self) -> str:
        """Genera un código nuevo, lo escribe en los registros y lo devuelve."""
        with self._lock:
            return self._issue_locked()

    def verify(self, candidate: str) -> bool:
        """Comprueba un código enviado desde el asistente.

        Tras ``MAX_FAILED_ATTEMPTS`` fallos se emite un código nuevo y el anterior
        deja de valer.

        Returns:
            ``True`` si coincide con el código vigente.
        """
        with self._lock:
            if self._code is None:
                return False
            normalized = candidate.strip().upper()
            if secrets.compare_digest(normalized.encode(), self._code.encode()):
                return True
            self._failed_attempts += 1
            if self._failed_attempts >= MAX_FAILED_ATTEMPTS:
                logger.warning("Demasiados códigos de configuración incorrectos: se genera uno nuevo.")
                self._issue_locked()
            return False

    def invalidate(self) -> None:
        """Anula el código tras completar la configuración."""
        with self._lock:
            self._code = None
            self._failed_attempts = 0

    def _issue_locked(self) -> str:
        """Emite un código nuevo; quien llama ya tiene el lock."""
        self._code = self._code_factory()
        self._failed_attempts = 0
        logger.warning(
            "trakt-manager no está configurado. Abre la interfaz web y usa este código de configuración: %s",
            self._code,
        )
        return self._code
