"""Cliente HTTP de bajo nivel para la API de Trakt.

Se encarga de todo lo que es común a cualquier petición a Trakt, para que el resto
del código solo tenga que pensar en rutas y datos:

- Cabeceras obligatorias (``trakt-api-version``, ``trakt-api-key``) y ``User-Agent``.
- Una pausa mínima entre peticiones, para no rozar los límites de Trakt.
- Reintentos ante limitación de peticiones (HTTP 429, respetando ``Retry-After``),
  errores de red y errores 5xx, siempre en número acotado.
- Token de acceso para las peticiones autenticadas y una única renovación
  automática si Trakt responde 401.
"""

import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from trakt_manager import __version__
from trakt_manager.errors import NotAuthenticatedError, TraktAPIError

API_BASE_URL = "https://api.trakt.tv"

# User-Agent genérico: identifica la herramienta sin incluir datos del usuario.
USER_AGENT = f"trakt-manager/{__version__}"

# Espera por defecto ante un 429 si Trakt no envía la cabecera Retry-After.
DEFAULT_RETRY_AFTER_SECONDS = 2.0


class TokenSource(Protocol):
    """Proveedor de tokens de acceso para las peticiones autenticadas."""

    def get_access_token(self) -> str:
        """Devuelve un token de acceso válido o lanza ``NotAuthenticatedError``."""
        ...

    def refresh_access_token(self) -> str:
        """Renueva el token, lo guarda y devuelve el nuevo token de acceso."""
        ...


class TraktClient:
    """Cliente síncrono de la API de Trakt con reintentos y autenticación.

    Args:
        client_id: Client ID de la aplicación de Trakt (cabecera ``trakt-api-key``).
        base_url: URL base de la API. Se cambia en los tests.
        request_delay: Pausa mínima en segundos entre dos peticiones consecutivas.
        transport: Transporte HTTP alternativo; en los tests, un ``httpx.MockTransport``.
        sleep: Función para esperar; los tests la sustituyen para no esperar de verdad.
        clock: Reloj monotónico usado para calcular la pausa entre peticiones.
        max_rate_limit_retries: Reintentos máximos ante respuestas 429.
        max_transient_retries: Reintentos máximos ante errores de red o 5xx.
        timeout: Tiempo máximo de cada petición en segundos.
    """

    def __init__(
        self,
        client_id: str,
        *,
        base_url: str = API_BASE_URL,
        request_delay: float = 0.2,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_rate_limit_retries: int = 5,
        max_transient_retries: int = 3,
        timeout: float = 20.0,
    ) -> None:
        self._client_id = client_id
        self._request_delay = request_delay
        self._sleep = sleep
        self._clock = clock
        self._max_rate_limit_retries = max_rate_limit_retries
        self._max_transient_retries = max_transient_retries
        self._last_request_at: float | None = None
        self._token_source: TokenSource | None = None
        self._http = httpx.Client(base_url=base_url, transport=transport, timeout=timeout)

    @property
    def client_id(self) -> str:
        """Client ID con el que se identifican las peticiones."""
        return self._client_id

    def set_token_source(self, token_source: TokenSource) -> None:
        """Configura de dónde se obtiene el token para las peticiones autenticadas.

        Se hace después de construir el cliente porque el propio gestor de tokens
        usa este cliente para hablar con los endpoints OAuth (que no van autenticados).
        """
        self._token_source = token_source

    def close(self) -> None:
        """Cierra las conexiones HTTP abiertas."""
        self._http.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        authenticated: bool = False,
        retry_rate_limits: bool = True,
    ) -> httpx.Response:
        """Envía una petición con reintentos y devuelve la respuesta, sea cual sea su código.

        Args:
            method: Método HTTP (``GET``, ``POST``...).
            path: Ruta de la API, por ejemplo ``/users/me/lists``.
            json: Cuerpo JSON opcional.
            params: Parámetros de la query string.
            authenticated: Si es ``True`` se envía el token de acceso del usuario.
            retry_rate_limits: Si es ``False`` un 429 se devuelve tal cual en lugar de
                reintentarse. El device flow lo necesita porque en ese endpoint el 429
                significa "sondea más despacio" y lo gestiona él mismo.

        Returns:
            La última respuesta recibida (puede ser un error si se agotaron los reintentos).

        Raises:
            NotAuthenticatedError: Si la petición es autenticada y no hay sesión.
            TraktAPIError: Si no se pudo contactar con Trakt tras los reintentos.
        """
        rate_limit_attempts = 0
        transient_attempts = 0
        token_refreshed = False

        while True:
            headers = self._build_headers(authenticated)
            self._wait_for_request_slot()
            try:
                response = self._http.request(method, path, json=json, params=params, headers=headers)
            except httpx.TransportError as error:
                transient_attempts += 1
                if transient_attempts > self._max_transient_retries:
                    raise TraktAPIError(None, method, path, str(error)) from error
                self._sleep(_exponential_backoff(transient_attempts))
                continue

            status = response.status_code
            if status == 429 and retry_rate_limits and rate_limit_attempts < self._max_rate_limit_retries:
                rate_limit_attempts += 1
                self._sleep(_retry_after_seconds(response))
                continue
            if status >= 500 and transient_attempts < self._max_transient_retries:
                transient_attempts += 1
                self._sleep(_exponential_backoff(transient_attempts))
                continue
            if status == 401 and authenticated and not token_refreshed and self._token_source is not None:
                # El token puede haber caducado antes de lo previsto: se renueva una sola vez
                # para no entrar en un bucle si Trakt sigue rechazándolo.
                self._token_source.refresh_access_token()
                token_refreshed = True
                continue
            return response

    def request_json(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> Any:
        """Envía una petición y devuelve el cuerpo JSON decodificado.

        Returns:
            El JSON de la respuesta, o ``None`` si la respuesta no tiene cuerpo.

        Raises:
            TraktAPIError: Si la respuesta final no es un código 2xx.
            NotAuthenticatedError: Si la petición es autenticada y no hay sesión.
        """
        response = self.request(method, path, json=json, params=params, authenticated=authenticated)
        if not response.is_success:
            raise TraktAPIError(response.status_code, method, path, response.text[:500])
        return response.json() if response.content else None

    def get_all_pages(self, path: str, *, params: dict[str, Any] | None = None, authenticated: bool = False) -> list[Any]:
        """Hace un ``GET`` a un endpoint que devuelve una lista y recorre todas sus páginas.

        Trakt indica la paginación con las cabeceras ``X-Pagination-Page-Count`` y
        ``X-Pagination-Limit``. Si no aparecen, la primera respuesta ya es completa.

        Raises:
            TraktAPIError: Si alguna página devuelve un error.
        """
        first_response = self._get_success("GET", path, params, authenticated)
        items: list[Any] = list(first_response.json() or [])

        page_count = int(first_response.headers.get("X-Pagination-Page-Count", "1"))
        page_limit = first_response.headers.get("X-Pagination-Limit")
        for page in range(2, page_count + 1):
            page_params = dict(params or {}, page=page)
            if page_limit:
                page_params["limit"] = page_limit
            response = self._get_success("GET", path, page_params, authenticated)
            items.extend(response.json() or [])
        return items

    def _get_success(
        self, method: str, path: str, params: dict[str, Any] | None, authenticated: bool
    ) -> httpx.Response:
        """Envía la petición y lanza ``TraktAPIError`` si la respuesta no es 2xx."""
        response = self.request(method, path, params=params, authenticated=authenticated)
        if not response.is_success:
            raise TraktAPIError(response.status_code, method, path, response.text[:500])
        return response

    def _build_headers(self, authenticated: bool) -> dict[str, str]:
        """Construye las cabeceras de una petición, incluido el token si se pide.

        Raises:
            NotAuthenticatedError: Si se pide autenticación y no hay proveedor de tokens.
        """
        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self._client_id,
            "User-Agent": USER_AGENT,
        }
        if authenticated:
            if self._token_source is None:
                raise NotAuthenticatedError("Esta operación necesita una sesión de Trakt.")
            headers["Authorization"] = f"Bearer {self._token_source.get_access_token()}"
        return headers

    def _wait_for_request_slot(self) -> None:
        """Espera lo necesario para que entre dos peticiones pase al menos ``request_delay``."""
        now = self._clock()
        if self._last_request_at is not None and self._request_delay > 0:
            remaining = self._request_delay - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last_request_at = now


def _retry_after_seconds(response: httpx.Response) -> float:
    """Devuelve cuántos segundos esperar según la cabecera ``Retry-After`` de un 429."""
    header_value = response.headers.get("Retry-After")
    try:
        return max(float(header_value), 0.0) if header_value is not None else DEFAULT_RETRY_AFTER_SECONDS
    except ValueError:
        return DEFAULT_RETRY_AFTER_SECONDS


def _exponential_backoff(attempt: int) -> float:
    """Espera creciente entre reintentos por errores transitorios: 1 s, 2 s, 4 s..."""
    return float(2 ** (attempt - 1))
