"""Construcción y conexión de las piezas de la aplicación.

El CLI y la API usan exactamente los mismos objetos (cliente de Trakt, gestor de
tokens, resolutor, sincronizador...). Este módulo los crea en un único sitio para
que ambas interfaces se comporten igual y para que los tests puedan sustituir el
transporte HTTP por un Trakt simulado.
"""

import time
from collections.abc import Callable
from functools import cached_property

import httpx

from trakt_manager.auth import DeviceFlowAuthorizer, TokenManager, TokenStore, get_username
from trakt_manager.config import Settings
from trakt_manager.resolver import EntryResolver
from trakt_manager.sync import ListSynchronizer
from trakt_manager.trakt_client import API_BASE_URL, TraktClient
from trakt_manager.trakt_lists import TraktListsAPI


class AppContext:
    """Contenedor de dependencias de la aplicación.

    Los objetos se crean la primera vez que se usan, de modo que un comando que
    no habla con Trakt (como ``validate``) no exige ``TRAKT_CLIENT_ID``.

    Args:
        settings: Configuración de la aplicación.
        transport: Transporte HTTP alternativo (tests).
        base_url: URL base de la API de Trakt (tests).
        sleep: Función de espera (tests).
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        base_url: str = API_BASE_URL,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._transport = transport
        self._base_url = base_url
        self._sleep = sleep
        self.token_store = TokenStore(settings.token_path)

    @cached_property
    def _client_and_token_manager(self) -> tuple[TraktClient, TokenManager]:
        """Crea el cliente de Trakt y su gestor de tokens, conectados entre sí.

        Se crean juntos porque dependen el uno del otro: el gestor usa el cliente
        para las llamadas OAuth, y el cliente pide al gestor el token de acceso.

        Raises:
            ConfigError: Si falta ``TRAKT_CLIENT_ID``.
        """
        client = TraktClient(
            self.settings.require_client_id(),
            base_url=self._base_url,
            request_delay=self.settings.request_delay,
            transport=self._transport,
            sleep=self._sleep,
        )
        token_manager = TokenManager(self.token_store, client, self.settings.trakt_client_secret)
        client.set_token_source(token_manager)
        return client, token_manager

    @property
    def client(self) -> TraktClient:
        """Cliente de Trakt compartido (``ConfigError`` si falta ``TRAKT_CLIENT_ID``)."""
        return self._client_and_token_manager[0]

    @property
    def token_manager(self) -> TokenManager:
        """Gestor de tokens de la sesión (renovación, cierre de sesión)."""
        return self._client_and_token_manager[1]

    def device_authorizer(self) -> DeviceFlowAuthorizer:
        """Crea el ejecutor del device flow.

        Raises:
            ConfigError: Si falta ``TRAKT_CLIENT_ID`` o ``TRAKT_CLIENT_SECRET``.
        """
        return DeviceFlowAuthorizer(self.client, self.settings.require_client_secret(), self.token_store, sleep=self._sleep)

    def has_session(self) -> bool:
        """Indica si hay un token de Trakt guardado."""
        return self.token_store.load() is not None

    def username(self) -> str:
        """Usuario de Trakt de la sesión activa.

        Raises:
            NotAuthenticatedError: Si no hay sesión.
        """
        return get_username(self.client)

    @cached_property
    def lists_api(self) -> TraktListsAPI:
        """Acceso a las listas del usuario."""
        return TraktListsAPI(self.client)

    @cached_property
    def synchronizer(self) -> ListSynchronizer:
        """Sincronizador de definiciones."""
        return ListSynchronizer(EntryResolver(self.client), self.lists_api, self.has_session)
