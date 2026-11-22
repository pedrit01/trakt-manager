"""Autorización OAuth2 con Trakt: device flow, almacenamiento y renovación del token.

Se usa el *device flow* de Trakt porque no necesita un servidor web ni una URL de
redirección: la herramienta muestra un código, el usuario lo introduce en
trakt.tv desde cualquier navegador y la herramienta recibe el token al sondear.

Piezas del módulo:

- :class:`TokenStore`: lee y escribe el token en disco con permisos restringidos.
- :class:`TokenManager`: da tokens válidos y los renueva cuando caducan.
- :class:`DeviceFlowAuthorizer`: ejecuta el device flow en primer plano (CLI).
- :class:`BackgroundDeviceAuthorization`: ejecuta el device flow en un hilo (API).
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

from trakt_manager.errors import (
    AuthError,
    DeviceCodeExpiredError,
    NotAuthenticatedError,
    TraktAPIError,
    TraktManagerError,
)
from trakt_manager.private_files import read_json_object, write_private_json
from trakt_manager.trakt_client import TraktClient

# Margen con el que se considera caducado un token: se renueva un poco antes de
# que expire para que no caduque a mitad de una sincronización larga.
TOKEN_EXPIRY_MARGIN_SECONDS = 300

# Trakt exige este redirect_uri en la renovación aunque el device flow no lo use.
OUT_OF_BAND_REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"

NOT_AUTHENTICATED_MESSAGE = "No hay sesión de Trakt. Ejecuta primero 'trakt-manager auth login'."


@dataclass(frozen=True)
class DeviceCode:
    """Código emitido por Trakt al iniciar el device flow.

    Atributos:
        device_code: Código interno con el que se sondea el token (no se muestra al usuario).
        user_code: Código que el usuario introduce en la web de Trakt.
        verification_url: URL donde el usuario introduce el código.
        expires_in: Segundos de validez del código.
        interval: Segundos que Trakt pide esperar entre sondeos.
    """

    device_code: str
    user_code: str
    verification_url: str
    expires_in: int
    interval: int


class TokenStore:
    """Guarda el token OAuth en un fichero JSON legible solo por su propietario.

    Args:
        path: Ruta del fichero del token (normalmente ``DATA_DIR/token.json``).
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def exists(self) -> bool:
        """Indica si hay un token guardado."""
        return self.path.is_file()

    def load(self) -> dict[str, Any] | None:
        """Lee el token guardado.

        Returns:
            El token como diccionario, o ``None`` si no hay fichero o no tiene
            ``access_token`` (un fichero corrupto se trata como si no hubiera sesión).
        """
        token = read_json_object(self.path)
        return token if token is not None and token.get("access_token") else None

    def save(self, token: dict[str, Any]) -> None:
        """Guarda el token de forma atómica y con permisos ``600``."""
        write_private_json(self.path, token)

    def delete(self) -> bool:
        """Borra el token guardado.

        Returns:
            ``True`` si había un token y se ha borrado.
        """
        if not self.exists():
            return False
        self.path.unlink()
        return True


def is_token_expired(token: dict[str, Any], now: float) -> bool:
    """Indica si un token ha caducado o está a punto de hacerlo.

    Si el token no trae ``created_at`` o ``expires_in`` no se puede saber; se
    considera válido y, si no lo es, el 401 de Trakt provocará la renovación.
    """
    created_at = token.get("created_at")
    expires_in = token.get("expires_in")
    if created_at is None or expires_in is None:
        return False
    return now >= float(created_at) + float(expires_in) - TOKEN_EXPIRY_MARGIN_SECONDS


# Errores OAuth con los que Trakt indica que no acepta el cliente (por ejemplo,
# porque esa aplicación sí necesita Client Secret).
CLIENT_REJECTED_ERRORS = {"invalid_client", "unauthorized_client"}

MISSING_SECRET_HINT = (
    "Trakt ha rechazado la aplicación sin Client Secret. Si tu aplicación de Trakt tiene "
    "Client Secret, configúralo (TRAKT_CLIENT_SECRET o Ajustes en la interfaz web)."
)


def client_credentials(client_id: str, client_secret: str | None) -> dict[str, str]:
    """Credenciales de la aplicación para los endpoints OAuth de Trakt.

    Las aplicaciones nuevas de Trakt no tienen Client Secret: entonces solo se
    envía el Client ID. Las antiguas que sí lo tienen lo siguen enviando.
    """
    credentials = {"client_id": client_id}
    if client_secret:
        credentials["client_secret"] = client_secret
    return credentials


def is_client_rejected(response: httpx.Response) -> bool:
    """Indica si Trakt ha rechazado la aplicación (cliente no válido) en una llamada OAuth."""
    if response.status_code in (401, 403):
        return True
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and body.get("error") in CLIENT_REJECTED_ERRORS


class TokenManager:
    """Proporciona tokens de acceso válidos, renovándolos cuando hace falta.

    Implementa el protocolo ``TokenSource`` que usa :class:`TraktClient`.

    Args:
        store: Almacén del token en disco.
        client: Cliente de Trakt para las llamadas OAuth (no autenticadas).
        client_secret: Client Secret de la aplicación, si la aplicación de Trakt lo tiene
            (las nuevas no): se envía al renovar y revocar solo si existe.
        clock: Reloj de pared (segundos desde epoch); los tests lo sustituyen.
    """

    def __init__(
        self,
        store: TokenStore,
        client: TraktClient,
        client_secret: str | None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._client = client
        self._client_secret = client_secret
        self._clock = clock
        # La API puede pedir tokens desde varios hilos: se evita renovar dos veces a la vez.
        self._refresh_lock = threading.Lock()

    def has_session(self) -> bool:
        """Indica si hay un token guardado (no comprueba que siga siendo válido en Trakt)."""
        return self._store.load() is not None

    def get_access_token(self) -> str:
        """Devuelve el token de acceso, renovándolo antes si ha caducado.

        Raises:
            NotAuthenticatedError: Si no hay token guardado.
            AuthError: Si el token caducado no se puede renovar.
        """
        token = self._store.load()
        if token is None:
            raise NotAuthenticatedError(NOT_AUTHENTICATED_MESSAGE)
        if is_token_expired(token, self._clock()) and token.get("refresh_token"):
            return self.refresh_access_token()
        return str(token["access_token"])

    def refresh_access_token(self) -> str:
        """Renueva el token con el ``refresh_token`` guardado y guarda el resultado.

        Returns:
            El nuevo token de acceso.

        Raises:
            NotAuthenticatedError: Si no hay token o no tiene ``refresh_token``.
            AuthError: Si Trakt rechaza la renovación.
        """
        with self._refresh_lock:
            token = self._store.load()
            if token is None or not token.get("refresh_token"):
                raise NotAuthenticatedError(NOT_AUTHENTICATED_MESSAGE)
            response = self._client.request(
                "POST",
                "/oauth/token",
                json={
                    "refresh_token": token["refresh_token"],
                    **client_credentials(self._client.client_id, self._client_secret),
                    "redirect_uri": OUT_OF_BAND_REDIRECT_URI,
                    "grant_type": "refresh_token",
                },
            )
            if not response.is_success and not self._client_secret and is_client_rejected(response):
                raise AuthError(MISSING_SECRET_HINT)
            if not response.is_success:
                raise AuthError(
                    f"Trakt ha rechazado la renovación del token (HTTP {response.status_code}). "
                    "Vuelve a autenticarte con 'trakt-manager auth login'."
                )
            new_token = response.json()
            self._store.save(new_token)
            return str(new_token["access_token"])

    def logout(self) -> bool:
        """Revoca el token en Trakt (si es posible) y lo borra del disco.

        Un fallo al revocar no impide borrar el token local: el objetivo del
        usuario es cerrar la sesión en esta herramienta.

        Returns:
            ``True`` si había una sesión y se ha cerrado.
        """
        token = self._store.load()
        if token is not None:
            try:
                self._client.request(
                    "POST",
                    "/oauth/revoke",
                    json={
                        "token": token["access_token"],
                        **client_credentials(self._client.client_id, self._client_secret),
                    },
                )
            except TraktAPIError:
                pass
        return self._store.delete()


def get_username(client: TraktClient) -> str:
    """Devuelve el nombre de usuario de Trakt de la sesión activa.

    Raises:
        NotAuthenticatedError: Si no hay sesión.
        TraktAPIError: Si Trakt devuelve un error.
    """
    settings = client.request_json("GET", "/users/settings", authenticated=True)
    return str(settings["user"]["username"])


class DeviceFlowAuthorizer:
    """Ejecuta el device flow de Trakt y guarda el token obtenido.

    Args:
        client: Cliente de Trakt para las llamadas OAuth.
        client_secret: Client Secret de la aplicación, si la tiene (las nuevas de Trakt no).
        store: Almacén donde se guarda el token conseguido.
        sleep: Función de espera entre sondeos; los tests la sustituyen.
        clock: Reloj de pared para controlar la caducidad del código.
    """

    def __init__(
        self,
        client: TraktClient,
        client_secret: str | None,
        store: TokenStore,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client = client
        self._client_secret = client_secret
        self._store = store
        self._sleep = sleep
        self._clock = clock

    def start(self) -> DeviceCode:
        """Pide a Trakt un código de dispositivo para que el usuario lo confirme.

        Raises:
            TraktAPIError: Si Trakt no emite el código.
        """
        data = self._client.request_json("POST", "/oauth/device/code", json={"client_id": self._client.client_id})
        return DeviceCode(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_url=data["verification_url"],
            expires_in=int(data.get("expires_in", 600)),
            interval=int(data.get("interval", 5)),
        )

    def wait_for_authorization(
        self, code: DeviceCode, should_stop: Callable[[], bool] | None = None
    ) -> dict[str, Any]:
        """Sondea a Trakt hasta que el usuario confirma el código, y guarda el token.

        Args:
            code: Código obtenido con :meth:`start`.
            should_stop: Función opcional que, si devuelve ``True``, cancela la espera.

        Returns:
            El token recibido de Trakt.

        Raises:
            DeviceCodeExpiredError: Si el código caduca (o se cancela la espera).
            AuthError: Si el usuario deniega el acceso o el código no es válido.
        """
        interval = code.interval
        expires_at = self._clock() + code.expires_in

        while self._clock() < expires_at:
            if should_stop is not None and should_stop():
                break
            self._sleep(interval)
            response = self._client.request(
                "POST",
                "/oauth/device/token",
                json={
                    "code": code.device_code,
                    **client_credentials(self._client.client_id, self._client_secret),
                },
                retry_rate_limits=False,
            )
            status = response.status_code
            # Se comprueba antes que el 400 "pendiente": si Trakt rechazara la aplicación
            # con un 400, se seguiría sondeando hasta que caducase el código y el usuario
            # solo vería "código caducado" en vez de la causa real.
            if not self._client_secret and is_client_rejected(response):
                raise AuthError(MISSING_SECRET_HINT)
            if status == 200:
                token = response.json()
                self._store.save(token)
                return token
            if status == 400:
                # El usuario todavía no ha introducido el código: se sigue esperando.
                continue
            if status == 429:
                # Trakt pide sondear más despacio.
                interval += 1
                continue
            if status == 410:
                break
            raise AuthError(_device_token_error_message(status))

        raise DeviceCodeExpiredError("El código ha expirado antes de autorizarlo. Vuelve a intentarlo.")


def _device_token_error_message(status: int) -> str:
    """Traduce los códigos de error del device flow de Trakt a un mensaje legible."""
    messages = {
        404: "Trakt no reconoce el código de dispositivo.",
        409: "El código ya se había usado.",
        418: "Has denegado el acceso en Trakt.",
    }
    return messages.get(status, f"Fallo inesperado en la autorización (HTTP {status}).")


AuthorizationStatus = Literal["none", "pending", "authorized", "expired", "error"]


class BackgroundDeviceAuthorization:
    """Gestiona un único device flow en segundo plano, para la API HTTP.

    La API no puede quedarse bloqueada esperando a que el usuario confirme el
    código, así que la espera se hace en un hilo y el estado se consulta aparte.

    Args:
        authorizer: Ejecutor del device flow.
    """

    def __init__(self, authorizer: DeviceFlowAuthorizer) -> None:
        self._authorizer = authorizer
        self._lock = threading.Lock()
        self._status: AuthorizationStatus = "none"
        self._code: DeviceCode | None = None
        self._code_expires_at = 0.0
        self._error: str | None = None
        self._cancelled = threading.Event()

    def start(self) -> DeviceCode:
        """Inicia el device flow, o devuelve el código del que ya está en curso.

        Returns:
            El código que el usuario debe introducir en Trakt.

        Raises:
            TraktAPIError: Si Trakt no emite el código.
        """
        with self._lock:
            if self._status == "pending" and self._code is not None and time.time() < self._code_expires_at:
                return self._code
            code = self._authorizer.start()
            self._code = code
            self._code_expires_at = time.time() + code.expires_in
            self._status = "pending"
            self._error = None
            self._cancelled.clear()
            threading.Thread(target=self._wait, args=(code,), daemon=True, name="trakt-device-flow").start()
            return code

    def cancel(self) -> None:
        """Cancela la espera en curso, si la hay."""
        self._cancelled.set()

    def status(self) -> tuple[AuthorizationStatus, str | None]:
        """Devuelve el estado del último device flow y el mensaje de error, si lo hubo."""
        with self._lock:
            return self._status, self._error

    def _wait(self, code: DeviceCode) -> None:
        """Cuerpo del hilo: espera la confirmación y anota el resultado."""
        try:
            self._authorizer.wait_for_authorization(code, should_stop=self._cancelled.is_set)
            new_status: AuthorizationStatus = "authorized"
            error = None
        except DeviceCodeExpiredError:
            new_status, error = "expired", None
        except TraktManagerError as failure:
            new_status, error = "error", str(failure)
        with self._lock:
            # Solo se actualiza si este hilo sigue siendo el del código vigente.
            if self._code == code:
                self._status = new_status
                self._error = error
