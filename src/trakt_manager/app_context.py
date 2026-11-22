"""Construcción y conexión de las piezas de la aplicación.

El CLI y la API usan exactamente los mismos objetos (cliente de Trakt, gestor de
tokens, resolutor, sincronizador...). Este módulo los crea en un único sitio para
que ambas interfaces se comporten igual y para que los tests puedan sustituir el
transporte HTTP por un Trakt simulado.

- :class:`AppContext`: las dependencias para una configuración concreta.
- :class:`AppRuntime`: el contexto *vigente*. Lo reconstruye cuando la
  configuración cambia desde la GUI, sin reiniciar el proceso, y guarda el estado
  que debe sobrevivir a esos cambios (bloqueos de sincronización, device flow y
  código de configuración).
"""

import secrets
import threading
import time
from collections.abc import Callable
from functools import cached_property

import httpx

from trakt_manager.auth import (
    BackgroundDeviceAuthorization,
    DeviceFlowAuthorizer,
    TokenManager,
    TokenStore,
    get_username,
)
from trakt_manager.config import Settings
from trakt_manager.definition_catalog import DefinitionCatalog
from trakt_manager.errors import (
    AlreadyConfiguredError,
    ConfigError,
    InvalidSetupCodeError,
    SettingFromEnvironmentError,
)
from trakt_manager.resolver import EntryResolver
from trakt_manager.settings_store import ResolvedSettings, SettingsStore, resolve_settings, settings_store_for
from trakt_manager.setup_guard import SetupGuard
from trakt_manager.sync import ListSynchronizer, SyncLocks
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
        """Crea el ejecutor del device flow (el Client Secret es opcional).

        Raises:
            ConfigError: Si falta ``TRAKT_CLIENT_ID``.
        """
        return DeviceFlowAuthorizer(self.client, self.settings.trakt_client_secret, self.token_store, sleep=self._sleep)

    def logout(self) -> bool:
        """Cierra la sesión de Trakt aunque falten credenciales.

        Con credenciales se intenta revocar el token en Trakt; sin ellas solo se
        borra el token local.

        Returns:
            ``True`` si había una sesión.
        """
        try:
            return self.token_manager.logout()
        except ConfigError:
            return self.token_store.delete()

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
    def definition_catalog(self) -> DefinitionCatalog:
        """Definiciones incluidas (``LISTS_DIR``) y guardadas desde la GUI (``DATA_DIR/lists``)."""
        return DefinitionCatalog(self.settings.lists_dir, self.settings.saved_lists_dir)

    @cached_property
    def synchronizer(self) -> ListSynchronizer:
        """Sincronizador de definiciones."""
        return ListSynchronizer(EntryResolver(self.client), self.lists_api, self.has_session)


ContextFactory = Callable[[Settings], AppContext]


def generate_api_key() -> str:
    """Genera una ``API_KEY`` aleatoria de 256 bits, apta para una cabecera HTTP."""
    return secrets.token_urlsafe(32)


class AppRuntime:
    """Mantiene el :class:`AppContext` vigente y aplica los cambios de configuración.

    La configuración efectiva sale de combinar el entorno con lo guardado desde la
    GUI (ver :mod:`trakt_manager.settings_store`). Cada vez que cambia, se crea un
    contexto nuevo; las operaciones que ya estaban en marcha terminan con el
    contexto con el que empezaron.

    Args:
        env_settings: Configuración leída del entorno (por defecto, ``Settings()``).
        context_factory: Cómo crear un contexto; los tests lo conectan a un Trakt simulado.
        setup_guard: Guardián del código de configuración (los tests lo sustituyen).
    """

    def __init__(
        self,
        env_settings: Settings | None = None,
        *,
        context_factory: ContextFactory = AppContext,
        setup_guard: SetupGuard | None = None,
    ) -> None:
        self._env_settings = env_settings or Settings()
        self._store = settings_store_for(self._env_settings)
        self._context_factory = context_factory
        self._lock = threading.RLock()
        self._device_authorization: BackgroundDeviceAuthorization | None = None
        self.sync_locks = SyncLocks()
        self.setup_guard = setup_guard or SetupGuard()
        self._resolved = resolve_settings(self._env_settings, self._store)
        self._context = self._context_factory(self._resolved.settings)

    # --- estado ---------------------------------------------------------------------------

    def current(self) -> AppContext:
        """Contexto vigente."""
        with self._lock:
            return self._context

    def resolved(self) -> ResolvedSettings:
        """Configuración efectiva y el origen de cada clave."""
        with self._lock:
            return self._resolved

    def is_configured(self) -> bool:
        """Indica si están las credenciales de Trakt y la ``API_KEY``."""
        return self.resolved().is_complete

    def start_setup_if_needed(self) -> None:
        """Emite el código de configuración si el servicio arranca sin configurar."""
        if not self.is_configured() and not self.setup_guard.is_active:
            self.setup_guard.issue()

    def reload(self) -> AppContext:
        """Vuelve a leer la configuración y crea un contexto nuevo con ella.

        Si cambian las credenciales de Trakt se descarta el device flow en curso,
        porque se inició con la aplicación de Trakt anterior.
        """
        with self._lock:
            previous = self._resolved.settings
            self._resolved = resolve_settings(self._env_settings, self._store)
            self._context = self._context_factory(self._resolved.settings)
            credentials_changed = (previous.trakt_client_id, previous.trakt_client_secret) != (
                self._resolved.settings.trakt_client_id,
                self._resolved.settings.trakt_client_secret,
            )
            if credentials_changed and self._device_authorization is not None:
                self._device_authorization.cancel()
                self._device_authorization = None
            return self._context

    # --- device flow (sobrevive a las recargas que no cambian credenciales) ---------------

    def device_authorization(self) -> BackgroundDeviceAuthorization:
        """Gestor del device flow en segundo plano, creado al usarse por primera vez.

        Raises:
            ConfigError: Si faltan las credenciales de Trakt.
        """
        with self._lock:
            if self._device_authorization is None:
                self._device_authorization = BackgroundDeviceAuthorization(self._context.device_authorizer())
            return self._device_authorization

    def device_authorization_status(self) -> tuple[str, str | None]:
        """Estado del último device flow (``none`` si nunca se inició)."""
        with self._lock:
            authorization = self._device_authorization
        return authorization.status() if authorization is not None else ("none", None)

    def reset_device_authorization(self) -> None:
        """Cancela el device flow en curso, si lo hay, y olvida su estado.

        Se usa al cerrar sesión: así el estado de un login anterior no se confunde
        con una sesión activa.
        """
        with self._lock:
            if self._device_authorization is not None:
                self._device_authorization.cancel()
                self._device_authorization = None

    # --- cambios de configuración ---------------------------------------------------------

    def complete_setup(self, setup_code: str, client_id: str, client_secret: str = "") -> str:
        """Guarda la configuración inicial desde el asistente.

        Args:
            setup_code: Código de configuración escrito en los registros.
            client_id: Client ID de la aplicación de Trakt.
            client_secret: Client Secret de la aplicación de Trakt, si la tiene (opcional:
                las aplicaciones nuevas de Trakt no tienen).

        Returns:
            La ``API_KEY``: la generada, o la del entorno si ya venía definida allí
            (en ese caso no se guarda ni se devuelve, y el resultado es una cadena vacía).

        Raises:
            AlreadyConfiguredError: Si el servicio ya estaba configurado.
            InvalidSetupCodeError: Si el código no es el vigente.
            ConfigError: Si falta el Client ID.
        """
        with self._lock:
            if self.is_configured():
                raise AlreadyConfiguredError("trakt-manager ya está configurado.")
            if not self.setup_guard.verify(setup_code):
                raise InvalidSetupCodeError("El código de configuración no es correcto. Cópialo de los registros del contenedor.")
            sources = self._resolved.sources
            changes: dict[str, str | None] = {}
            if sources["trakt_client_id"] != "env":
                if not client_id.strip():
                    raise ConfigError("Falta TRAKT_CLIENT_ID: indica el Client ID de tu aplicación de Trakt.")
                changes["trakt_client_id"] = client_id
            if sources["trakt_client_secret"] != "env" and client_secret.strip():
                changes["trakt_client_secret"] = client_secret
            api_key = ""
            if sources["api_key"] != "env":
                api_key = generate_api_key()
                changes["api_key"] = api_key
            self._store.update(changes)
            self.reload()
            self.setup_guard.invalidate()
            return api_key

    def update_settings(self, changes: dict[str, str | None]) -> None:
        """Cambia credenciales guardadas desde la GUI y aplica el cambio en caliente.

        Si cambia el Client ID se cierra la sesión de Trakt: el token pertenece a la
        aplicación de Trakt anterior y no valdría con la nueva.

        Raises:
            SettingFromEnvironmentError: Si alguna clave viene del entorno.
            ValueError: Si alguna clave no es configurable.
        """
        with self._lock:
            from_env = [key for key in changes if self._resolved.sources.get(key) == "env"]
            if from_env:
                raise SettingFromEnvironmentError(
                    "Estas claves vienen de variables de entorno y no se pueden cambiar desde la GUI: "
                    + ", ".join(from_env)
                )
            new_client_id = changes.get("trakt_client_id")
            client_id_changes = new_client_id is not None and new_client_id.strip() != (
                self._resolved.settings.trakt_client_id or ""
            )
            if client_id_changes:
                # Se cierra la sesión con el contexto actual, que aún tiene las credenciales viejas.
                self._context.logout()
            self._store.update(changes)
            self.reload()

    def regenerate_api_key(self) -> str:
        """Genera y guarda una ``API_KEY`` nueva; la anterior deja de valer al momento.

        Raises:
            SettingFromEnvironmentError: Si ``API_KEY`` viene del entorno.
        """
        api_key = generate_api_key()
        self.update_settings({"api_key": api_key})
        return api_key

    @property
    def settings_store(self) -> SettingsStore:
        """Almacén de la configuración guardada."""
        return self._store
