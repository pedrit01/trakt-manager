"""API HTTP de trakt-manager.

Expone las mismas operaciones que el CLI, con las mismas respuestas que su
salida ``--json``, para administrar listas desde otro equipo.

Seguridad: todas las rutas salvo ``/health`` exigen la cabecera ``X-API-Key``
con el valor de ``API_KEY``. Sin ``API_KEY`` la aplicación no arranca, porque
la API escribe en la cuenta de Trakt del usuario.

Rutas:

- ``GET /health``: estado del servicio (sin autenticación).
- ``POST /auth/device``, ``GET /auth/status``, ``DELETE /auth``: sesión de Trakt.
- ``GET /definitions``, ``GET /definitions/{nombre}``: definiciones de ``LISTS_DIR``.
- ``POST /validate``: valida una definición enviada en el cuerpo (JSON o YAML).
- ``POST /sync``: sincroniza una definición enviada en el cuerpo.
- ``POST /definitions/{nombre}/sync``: sincroniza una definición de ``LISTS_DIR``.
- ``GET /lists``, ``GET /lists/{id}``: listas del usuario y sus elementos.

La documentación interactiva (OpenAPI) está en ``/docs``.
"""

import secrets
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any, TypeVar

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from trakt_manager import __version__
from trakt_manager.app_context import AppContext
from trakt_manager.auth import BackgroundDeviceAuthorization
from trakt_manager.config import Settings
from trakt_manager.definitions import (
    ListDefinition,
    ValidationOutcome,
    find_definition_files,
    load_definition_file,
    parse_definition_text,
)
from trakt_manager.errors import (
    AuthError,
    ConfigError,
    DefinitionError,
    ListNotFoundError,
    NotAuthenticatedError,
    TraktAPIError,
    TraktManagerError,
)
from trakt_manager.sync import SyncResult

Result = TypeVar("Result")


class ListBusyError(TraktManagerError):
    """Ya hay una sincronización real en curso para la misma lista."""


class SyncLocks:
    """Bloqueos por nombre de lista para impedir dos sincronizaciones simultáneas.

    Basta con bloqueos en memoria porque la API se ejecuta en un único proceso.
    """

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @contextmanager
    def hold(self, list_name: str) -> Iterator[None]:
        """Reserva la lista durante el bloque ``with``.

        Raises:
            ListBusyError: Si la lista ya está reservada; no se espera a que se libere.
        """
        with self._guard:
            lock = self._locks.setdefault(list_name, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ListBusyError(f"Ya hay una sincronización en curso de la lista '{list_name}'.")
        try:
            yield
        finally:
            lock.release()


def create_app(context: AppContext | None = None) -> FastAPI:
    """Crea la aplicación FastAPI.

    Args:
        context: Contexto de la aplicación; si no se indica, se crea con la
            configuración del entorno. Los tests pasan uno con un Trakt simulado.

    Raises:
        ConfigError: Si falta ``API_KEY``.
    """
    context = context or AppContext(Settings())
    api_key = context.settings.require_api_key()
    sync_locks = SyncLocks()
    device_authorization = _LazyDeviceAuthorization(context)

    def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        """Rechaza con 401 las peticiones sin la clave correcta."""
        # compare_digest evita filtrar la clave por diferencias en el tiempo de comparación.
        if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), api_key.encode()):
            raise HTTPException(status_code=401, detail="Falta la cabecera X-API-Key o no es correcta.")

    app = FastAPI(
        title="trakt-manager",
        version=__version__,
        description="Crea y sincroniza listas de Trakt a partir de ficheros de definición.",
    )
    _register_error_handlers(app)
    protected = [Depends(require_api_key)]

    # --- salud ----------------------------------------------------------------------------

    @app.get("/health", tags=["servicio"])
    def health() -> dict[str, Any]:
        """Indica si el servicio funciona y si hay sesión de Trakt (sin revelar secretos)."""
        return {"status": "ok", "trakt_session": context.has_session()}

    # --- autenticación con Trakt ----------------------------------------------------------

    @app.post("/auth/device", tags=["auth"], dependencies=protected)
    def start_device_authorization() -> dict[str, Any]:
        """Inicia el device flow: devuelve la URL y el código a introducir en Trakt."""
        code = device_authorization.get().start()
        return {"verification_url": code.verification_url, "user_code": code.user_code, "expires_in": code.expires_in}

    @app.get("/auth/status", tags=["auth"], dependencies=protected)
    def authorization_status() -> dict[str, Any]:
        """Estado de la sesión: ``authorized`` (con usuario), ``pending``, ``expired``, ``error`` o ``none``."""
        if context.has_session():
            return {"status": "authorized", "username": context.username(), "error": None}
        status, error = device_authorization.status()
        return {"status": status, "username": None, "error": error}

    @app.delete("/auth", tags=["auth"], dependencies=protected)
    def logout() -> dict[str, bool]:
        """Cierra la sesión de Trakt."""
        device_authorization.cancel()
        return {"logged_out": context.token_manager.logout()}

    # --- definiciones ---------------------------------------------------------------------

    @app.get("/definitions", tags=["definiciones"], dependencies=protected)
    def list_definitions() -> list[dict[str, Any]]:
        """Definiciones disponibles en ``LISTS_DIR``.

        ``name`` es el nombre de la definición (fichero sin extensión) y ``list_name``
        el nombre de la lista en Trakt.
        """
        summaries = []
        for name, path in find_definition_files(context.settings.lists_dir).items():
            try:
                outcome = ValidationOutcome.from_definition(load_definition_file(path))
            except DefinitionError as error:
                outcome = ValidationOutcome.from_error(error)
            summaries.append(
                {
                    "name": name,
                    "file": path.name,
                    "valid": outcome.valid,
                    "list_name": outcome.name,
                    "entries": outcome.entries,
                    "extras": outcome.extras,
                    "errors": [issue.model_dump(mode="json") for issue in outcome.errors],
                }
            )
        return summaries

    @app.get("/definitions/{name}", tags=["definiciones"], dependencies=protected)
    def get_definition(name: str) -> dict[str, Any]:
        """Devuelve una definición de ``LISTS_DIR`` ya validada."""
        return _load_named_definition(context, name).model_dump(mode="json")

    @app.post("/validate", tags=["definiciones"], dependencies=protected)
    async def validate(request: Request) -> ValidationOutcome:
        """Valida una definición enviada en el cuerpo (JSON, o YAML con ``Content-Type`` YAML).

        Responde 422 con los errores si no es válida.
        """
        definition = _parse_body_definition(await request.body(), request.headers.get("content-type"))
        return ValidationOutcome.from_definition(definition)

    # --- sincronización -------------------------------------------------------------------

    @app.post("/sync", tags=["sincronización"], dependencies=protected)
    async def sync_from_body(
        request: Request,
        dry_run: Annotated[bool, Query()] = False,
        include_extras: Annotated[bool, Query()] = False,
    ) -> SyncResult:
        """Sincroniza (o previsualiza con ``dry_run=true``) una definición enviada en el cuerpo."""
        definition = _parse_body_definition(await request.body(), request.headers.get("content-type"))
        return await run_in_threadpool(_run_sync, context, sync_locks, definition, dry_run, include_extras)

    @app.post("/definitions/{name}/sync", tags=["sincronización"], dependencies=protected)
    def sync_named_definition(
        name: str,
        dry_run: Annotated[bool, Query()] = False,
        include_extras: Annotated[bool, Query()] = False,
    ) -> SyncResult:
        """Sincroniza (o previsualiza con ``dry_run=true``) una definición de ``LISTS_DIR``."""
        definition = _load_named_definition(context, name)
        return _run_sync(context, sync_locks, definition, dry_run, include_extras)

    # --- consulta -------------------------------------------------------------------------

    @app.get("/lists", tags=["listas"], dependencies=protected)
    def get_lists() -> list[dict[str, Any]]:
        """Listas de la cuenta de Trakt."""
        return [summary.model_dump(mode="json") for summary in context.lists_api.get_user_lists()]

    @app.get("/lists/{list_id}", tags=["listas"], dependencies=protected)
    def get_list(list_id: str) -> dict[str, Any]:
        """Una lista (por id numérico o slug) y sus elementos en orden."""
        summary = context.lists_api.get_list(list_id)
        items = context.lists_api.get_items(summary.trakt_id)
        return {"list": summary.model_dump(mode="json"), "items": [item.model_dump(mode="json") for item in items]}

    return app


class _LazyDeviceAuthorization:
    """Crea el device flow en segundo plano solo cuando se usa por primera vez.

    Así la API arranca aunque falte ``TRAKT_CLIENT_SECRET``, que solo se necesita
    para autenticarse; el error aparece al llamar a ``POST /auth/device``.
    """

    def __init__(self, context: AppContext) -> None:
        self._context = context
        self._instance: BackgroundDeviceAuthorization | None = None
        self._lock = threading.Lock()

    def get(self) -> BackgroundDeviceAuthorization:
        """Devuelve el gestor del device flow, creándolo si hace falta."""
        with self._lock:
            if self._instance is None:
                self._instance = BackgroundDeviceAuthorization(self._context.device_authorizer())
            return self._instance

    def status(self) -> tuple[str, str | None]:
        """Estado del último device flow (``none`` si nunca se inició)."""
        return self._instance.status() if self._instance is not None else ("none", None)

    def cancel(self) -> None:
        """Cancela el device flow en curso, si lo hay."""
        if self._instance is not None:
            self._instance.cancel()


def _run_sync(
    context: AppContext, sync_locks: SyncLocks, definition: ListDefinition, dry_run: bool, include_extras: bool
) -> SyncResult:
    """Ejecuta la sincronización, reservando la lista si no es una previsualización."""
    if dry_run:
        return context.synchronizer.sync(definition, include_extras=include_extras, dry_run=True)
    with sync_locks.hold(definition.name):
        return context.synchronizer.sync(definition, include_extras=include_extras, dry_run=False)


def _load_named_definition(context: AppContext, name: str) -> ListDefinition:
    """Carga una definición de ``LISTS_DIR`` por su nombre (sin extensión).

    Raises:
        HTTPException: 404 si no existe.
        DefinitionError: Si no es válida.
    """
    path: Path | None = find_definition_files(context.settings.lists_dir).get(name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No existe la definición '{name}'.")
    return load_definition_file(path)


def _parse_body_definition(body: bytes, content_type: str | None) -> ListDefinition:
    """Interpreta el cuerpo de la petición como una definición.

    Se lee como YAML si el ``Content-Type`` lo indica (``application/yaml``,
    ``text/yaml``...) y como JSON en cualquier otro caso.

    Raises:
        DefinitionError: Si el cuerpo no es válido.
    """
    file_format = "yaml" if content_type and "yaml" in content_type.lower() else "json"
    return parse_definition_text(body.decode("utf-8", errors="replace"), file_format)


def _register_error_handlers(app: FastAPI) -> None:
    """Traduce los errores de la aplicación a respuestas HTTP con un mensaje claro."""

    def handler(status_code: int) -> Callable[[Request, Exception], JSONResponse]:
        def respond(request: Request, error: Exception) -> JSONResponse:
            return JSONResponse(status_code=status_code, content={"detail": str(error)})

        return respond

    @app.exception_handler(DefinitionError)
    def definition_error(request: Request, error: DefinitionError) -> JSONResponse:
        """Una definición no válida: 422 con todos los errores."""
        return JSONResponse(status_code=422, content=ValidationOutcome.from_error(error).model_dump(mode="json"))

    # Sin sesión o con la sesión caducada sin remedio: el cliente debe autenticarse (409).
    app.add_exception_handler(NotAuthenticatedError, handler(409))
    app.add_exception_handler(AuthError, handler(409))
    app.add_exception_handler(ListBusyError, handler(409))
    app.add_exception_handler(ListNotFoundError, handler(404))
    app.add_exception_handler(ConfigError, handler(500))
    # Trakt ha fallado: es un error de un servicio externo (502 Bad Gateway).
    app.add_exception_handler(TraktAPIError, handler(502))
    app.add_exception_handler(TraktManagerError, handler(400))
