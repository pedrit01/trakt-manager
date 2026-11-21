"""API HTTP y GUI web de trakt-manager.

Expone las mismas operaciones que el CLI, con las mismas respuestas que su
salida ``--json``, y sirve la interfaz web en ``/``.

Seguridad:

- Las rutas de datos exigen la cabecera ``X-API-Key`` con la ``API_KEY`` vigente,
  que se lee en cada petición para que regenerarla surta efecto al instante.
- Si falta configuración, el servicio arranca en *modo configuración*: solo
  responden ``/health``, la GUI y el asistente (``/setup``), y el resto de rutas
  devuelven 503. El asistente exige el código de un solo uso de los registros.

Rutas:

- ``GET /health``: estado del servicio (sin autenticación).
- ``GET /setup/status``, ``POST /setup``: asistente inicial (sin clave; con código).
- ``GET /settings``, ``PUT /settings``, ``POST /settings/api-key``: configuración.
- ``POST /auth/device``, ``GET /auth/status``, ``DELETE /auth``: sesión de Trakt.
- ``GET /definitions``, ``GET|PUT|DELETE /definitions/{nombre}``,
  ``GET /definitions/{nombre}/source``: catálogo de definiciones.
- ``POST /validate``: valida una definición enviada en el cuerpo (JSON o YAML).
- ``POST /sync``, ``POST /definitions/{nombre}/sync``: sincronización.
- ``GET /lists``, ``GET /lists/{id}``: listas del usuario y sus elementos.

La documentación interactiva (OpenAPI) está en ``/docs``.
"""

import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from trakt_manager import __version__
from trakt_manager.app_context import AppContext, AppRuntime
from trakt_manager.definitions import ListDefinition, ValidationOutcome, parse_definition_text
from trakt_manager.errors import (
    AlreadyConfiguredError,
    AuthError,
    ConfigError,
    DefinitionError,
    DefinitionNotDeletableError,
    DefinitionNotFoundError,
    InvalidDefinitionNameError,
    InvalidSetupCodeError,
    ListBusyError,
    ListNotFoundError,
    NotAuthenticatedError,
    NotConfiguredError,
    SettingFromEnvironmentError,
    TraktAPIError,
    TraktManagerError,
)
from trakt_manager.settings_store import CONFIGURABLE_KEYS
from trakt_manager.sync import SyncResult

WEB_DIRECTORY = Path(__file__).parent / "web"

# La GUI no carga nada de fuera del propio servicio; la CSP lo hace cumplir en el navegador.
CONTENT_SECURITY_POLICY = "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"

# Swagger UI (/docs) y ReDoc cargan sus recursos de un CDN, así que quedan fuera de la CSP.
PATHS_WITHOUT_CSP = ("/docs", "/redoc", "/openapi.json")


class SetupRequest(BaseModel):
    """Datos del asistente inicial."""

    setup_code: str
    trakt_client_id: str = ""
    trakt_client_secret: str = ""


class SettingsUpdate(BaseModel):
    """Cambios de credenciales de Trakt desde la GUI (la API_KEY se regenera aparte).

    Un Client Secret vacío lo borra (las aplicaciones nuevas de Trakt no tienen);
    el Client ID no puede quedar vacío.
    """

    trakt_client_id: str | None = None
    trakt_client_secret: str | None = None


def create_app(runtime: AppRuntime | None = None) -> FastAPI:
    """Crea la aplicación FastAPI con la API y la GUI.

    Si el servicio no está configurado se emite el código de configuración (que
    se escribe en los registros) y la aplicación arranca en modo configuración.

    Args:
        runtime: Runtime de la aplicación; si no se indica, se crea con la
            configuración efectiva. Los tests pasan uno con un Trakt simulado.
    """
    runtime = runtime or AppRuntime()
    runtime.start_setup_if_needed()

    def current_context() -> AppContext:
        """Contexto vigente: se pide en cada petición para recoger los cambios de configuración."""
        return runtime.current()

    def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        """Exige configuración completa (503) y la ``API_KEY`` vigente (401)."""
        resolved = runtime.resolved()
        if not resolved.is_complete:
            raise NotConfiguredError(resolved.missing_variables)
        expected = resolved.settings.require_api_key()
        # compare_digest evita filtrar la clave por diferencias en el tiempo de comparación.
        if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="Falta la cabecera X-API-Key o no es correcta.")

    Context = Annotated[AppContext, Depends(current_context)]
    protected = [Depends(require_api_key)]

    app = FastAPI(
        title="trakt-manager",
        version=__version__,
        description="Crea y sincroniza listas de Trakt a partir de ficheros de definición.",
    )
    _register_error_handlers(app)
    _add_security_headers(app)

    # --- salud ----------------------------------------------------------------------------

    @app.get("/health", tags=["servicio"])
    def health(context: Context) -> dict[str, Any]:
        """Estado del servicio, modo (``ready`` o ``setup``) y si hay sesión de Trakt, sin secretos."""
        return {
            "status": "ok",
            "mode": "ready" if runtime.is_configured() else "setup",
            "trakt_session": context.has_session(),
        }

    # --- asistente y configuración --------------------------------------------------------

    @app.get("/setup/status", tags=["configuración"])
    def setup_status() -> dict[str, Any]:
        """Si el servicio está configurado, qué falta y de dónde sale cada clave."""
        resolved = runtime.resolved()
        return {"configured": resolved.is_complete, "missing": resolved.missing_variables, "sources": resolved.sources}

    @app.post("/setup", tags=["configuración"])
    def complete_setup(request: SetupRequest) -> dict[str, str]:
        """Guarda la configuración inicial y devuelve la ``API_KEY`` generada (solo esta vez)."""
        try:
            api_key = runtime.complete_setup(request.setup_code, request.trakt_client_id, request.trakt_client_secret)
        except ConfigError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"api_key": api_key}

    @app.get("/settings", tags=["configuración"], dependencies=protected)
    def get_settings() -> dict[str, Any]:
        """Configuración actual: origen de cada clave y Client ID, sin secretos."""
        return _settings_view(runtime)

    @app.put("/settings", tags=["configuración"], dependencies=protected)
    def update_settings(update: SettingsUpdate) -> dict[str, Any]:
        """Cambia las credenciales de Trakt guardadas; si cambia el Client ID se cierra la sesión."""
        changes = update.model_dump(exclude_none=True)
        if "trakt_client_id" in changes and not changes["trakt_client_id"].strip():
            raise HTTPException(status_code=422, detail="El Client ID de Trakt no puede quedar vacío.")
        runtime.update_settings(changes)
        return _settings_view(runtime)

    @app.post("/settings/api-key", tags=["configuración"], dependencies=protected)
    def regenerate_api_key() -> dict[str, str]:
        """Genera una ``API_KEY`` nueva y la devuelve (solo esta vez); la anterior deja de valer."""
        return {"api_key": runtime.regenerate_api_key()}

    # --- autenticación con Trakt ----------------------------------------------------------

    @app.post("/auth/device", tags=["auth"], dependencies=protected)
    def start_device_authorization() -> dict[str, Any]:
        """Inicia el device flow: devuelve la URL y el código a introducir en Trakt."""
        code = runtime.device_authorization().start()
        return {"verification_url": code.verification_url, "user_code": code.user_code, "expires_in": code.expires_in}

    @app.get("/auth/status", tags=["auth"], dependencies=protected)
    def authorization_status(context: Context) -> dict[str, Any]:
        """Estado de la sesión: ``authorized`` (con usuario), ``pending``, ``expired``, ``error`` o ``none``."""
        if context.has_session():
            return {"status": "authorized", "username": context.username(), "error": None}
        status, error = runtime.device_authorization_status()
        if status == "authorized":
            # El último device flow terminó bien, pero el token ya no está (se cerró la
            # sesión, quizá desde el CLI): hoy no hay sesión.
            status = "none"
        return {"status": status, "username": None, "error": error}

    @app.delete("/auth", tags=["auth"], dependencies=protected)
    def logout(context: Context) -> dict[str, bool]:
        """Cierra la sesión de Trakt."""
        runtime.reset_device_authorization()
        return {"logged_out": context.logout()}

    # --- definiciones ---------------------------------------------------------------------

    @app.get("/definitions", tags=["definiciones"], dependencies=protected)
    def list_definitions(context: Context) -> list[dict[str, Any]]:
        """Definiciones disponibles, con su origen y su validez.

        ``name`` es el nombre de la definición (fichero sin extensión) y ``list_name``
        el nombre de la lista en Trakt. ``origin`` es ``bundled`` (incluida en la
        imagen o montada) o ``saved`` (guardada desde la GUI).
        """
        summaries = []
        for entry in context.definition_catalog.entries():
            try:
                outcome = ValidationOutcome.from_definition(context.definition_catalog.load(entry.name))
            except DefinitionError as error:
                outcome = ValidationOutcome.from_error(error)
            summaries.append(
                {
                    "name": entry.name,
                    "file": entry.path.name,
                    "origin": entry.origin,
                    "valid": outcome.valid,
                    "list_name": outcome.name,
                    "entries": outcome.entries,
                    "extras": outcome.extras,
                    "errors": [issue.model_dump(mode="json") for issue in outcome.errors],
                }
            )
        return summaries

    @app.get("/definitions/{name}", tags=["definiciones"], dependencies=protected)
    def get_definition(name: str, context: Context) -> dict[str, Any]:
        """Una definición ya validada, con su origen."""
        entry = context.definition_catalog.find(name)
        return {"origin": entry.origin, **context.definition_catalog.load(name).model_dump(mode="json")}

    @app.get("/definitions/{name}/source", tags=["definiciones"], dependencies=protected)
    def get_definition_source(name: str, context: Context) -> PlainTextResponse:
        """El texto original de una definición, para descargarlo con sus comentarios."""
        text, entry = context.definition_catalog.read_source(name)
        media_type = "application/json" if entry.file_format == "json" else "application/yaml"
        disposition = f'attachment; filename="{entry.path.name}"'
        return PlainTextResponse(text, media_type=media_type, headers={"Content-Disposition": disposition})

    # {name:path} acepta también "/" para que nombres como "../secreto" lleguen al
    # catálogo y se rechacen con 422, en vez de caer en la GUI con un 405 confuso.
    @app.put("/definitions/{name:path}", tags=["definiciones"], dependencies=protected)
    async def save_definition(name: str, request: Request) -> dict[str, Any]:
        """Valida y guarda una definición (cuerpo JSON, o YAML con ``Content-Type`` YAML)."""
        body, file_format = await _read_body(request)
        context = runtime.current()
        entry = await run_in_threadpool(context.definition_catalog.save, name, body, file_format)
        return {"name": entry.name, "origin": entry.origin, "file": entry.path.name}

    @app.delete("/definitions/{name:path}", tags=["definiciones"], dependencies=protected)
    def delete_definition(name: str, context: Context) -> dict[str, bool]:
        """Borra una definición guardada (las incluidas o montadas no se pueden borrar)."""
        context.definition_catalog.delete(name)
        return {"deleted": True}

    @app.post("/validate", tags=["definiciones"], dependencies=protected)
    async def validate(request: Request) -> ValidationOutcome:
        """Valida una definición enviada en el cuerpo; responde 422 con los errores si no es válida."""
        body, file_format = await _read_body(request)
        return ValidationOutcome.from_definition(parse_definition_text(body, file_format))

    # --- sincronización -------------------------------------------------------------------

    @app.post("/sync", tags=["sincronización"], dependencies=protected)
    async def sync_from_body(
        request: Request,
        dry_run: Annotated[bool, Query()] = False,
        include_extras: Annotated[bool, Query()] = False,
    ) -> SyncResult:
        """Sincroniza (o previsualiza con ``dry_run=true``) una definición enviada en el cuerpo."""
        body, file_format = await _read_body(request)
        definition = parse_definition_text(body, file_format)
        return await run_in_threadpool(_run_sync, runtime, definition, dry_run, include_extras)

    @app.post("/definitions/{name}/sync", tags=["sincronización"], dependencies=protected)
    def sync_named_definition(
        name: str,
        context: Context,
        dry_run: Annotated[bool, Query()] = False,
        include_extras: Annotated[bool, Query()] = False,
    ) -> SyncResult:
        """Sincroniza (o previsualiza con ``dry_run=true``) una definición del catálogo."""
        return _run_sync(runtime, context.definition_catalog.load(name), dry_run, include_extras)

    # --- consulta -------------------------------------------------------------------------

    @app.get("/lists", tags=["listas"], dependencies=protected)
    def get_lists(context: Context) -> list[dict[str, Any]]:
        """Listas de la cuenta de Trakt."""
        return [summary.model_dump(mode="json") for summary in context.lists_api.get_user_lists()]

    @app.get("/lists/{list_id}", tags=["listas"], dependencies=protected)
    def get_list(list_id: str, context: Context) -> dict[str, Any]:
        """Una lista (por id numérico o slug) y sus elementos en orden."""
        summary = context.lists_api.get_list(list_id)
        items = context.lists_api.get_items(summary.trakt_id)
        return {"list": summary.model_dump(mode="json"), "items": [item.model_dump(mode="json") for item in items]}

    # --- GUI ------------------------------------------------------------------------------

    # Se monta la última para que las rutas de la API tengan prioridad sobre los ficheros.
    app.mount("/", StaticFiles(directory=WEB_DIRECTORY, html=True), name="gui")
    return app


def _run_sync(runtime: AppRuntime, definition: ListDefinition, dry_run: bool, include_extras: bool) -> SyncResult:
    """Ejecuta la sincronización, reservando la lista si no es una previsualización."""
    context = runtime.current()
    if dry_run:
        return context.synchronizer.sync(definition, include_extras=include_extras, dry_run=True)
    with runtime.sync_locks.hold(definition.name):
        return context.synchronizer.sync(definition, include_extras=include_extras, dry_run=False)


async def _read_body(request: Request) -> tuple[str, Literal["yaml", "json"]]:
    """Lee el cuerpo de la petición y decide su formato.

    Se interpreta como YAML si el ``Content-Type`` lo indica (``application/yaml``,
    ``text/yaml``...) y como JSON en cualquier otro caso.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    file_format: Literal["yaml", "json"] = "yaml" if "yaml" in content_type else "json"
    return (await request.body()).decode("utf-8", errors="replace"), file_format


def _settings_view(runtime: AppRuntime) -> dict[str, Any]:
    """Configuración para mostrar en la GUI, sin devolver nunca secretos.

    Para cada clave se indica su origen (``env``, ``stored`` o ``missing``) y si
    tiene valor. Solo se muestra el valor del Client ID, que no es secreto.
    """
    resolved = runtime.resolved()
    view: dict[str, Any] = {}
    for key in CONFIGURABLE_KEYS:
        source = resolved.sources[key]
        view[key] = {"source": source, "set": source != "missing", "editable": source != "env"}
    view["trakt_client_id"]["value"] = resolved.settings.trakt_client_id
    return view


def _add_security_headers(app: FastAPI) -> None:
    """Añade cabeceras de seguridad a todas las respuestas (CSP salvo en la documentación)."""

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith(PATHS_WITHOUT_CSP):
            response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


def _register_error_handlers(app: FastAPI) -> None:
    """Traduce los errores de la aplicación a respuestas HTTP con un mensaje claro en español."""

    def handler(status_code: int) -> Callable[[Request, Exception], JSONResponse]:
        def respond(request: Request, error: Exception) -> JSONResponse:
            return JSONResponse(status_code=status_code, content={"detail": str(error)})

        return respond

    @app.exception_handler(DefinitionError)
    def definition_error(request: Request, error: DefinitionError) -> JSONResponse:
        """Una definición no válida: 422 con todos los errores."""
        return JSONResponse(status_code=422, content=ValidationOutcome.from_error(error).model_dump(mode="json"))

    @app.exception_handler(NotConfiguredError)
    def not_configured(request: Request, error: NotConfiguredError) -> JSONResponse:
        """Modo configuración: 503 indicando qué falta."""
        return JSONResponse(status_code=503, content={"detail": str(error), "missing": error.missing_variables})

    # Sin sesión o con la sesión caducada sin remedio: el cliente debe autenticarse (409).
    app.add_exception_handler(NotAuthenticatedError, handler(409))
    app.add_exception_handler(AuthError, handler(409))
    app.add_exception_handler(ListBusyError, handler(409))
    app.add_exception_handler(AlreadyConfiguredError, handler(409))
    app.add_exception_handler(SettingFromEnvironmentError, handler(409))
    app.add_exception_handler(DefinitionNotDeletableError, handler(409))
    app.add_exception_handler(InvalidSetupCodeError, handler(403))
    app.add_exception_handler(ListNotFoundError, handler(404))
    app.add_exception_handler(DefinitionNotFoundError, handler(404))
    app.add_exception_handler(InvalidDefinitionNameError, handler(422))
    app.add_exception_handler(ConfigError, handler(500))
    # Trakt ha fallado: es un error de un servicio externo (502 Bad Gateway).
    app.add_exception_handler(TraktAPIError, handler(502))
    app.add_exception_handler(TraktManagerError, handler(400))
