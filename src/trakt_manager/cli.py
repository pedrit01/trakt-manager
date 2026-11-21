"""Interfaz de línea de comandos ``trakt-manager``.

Comandos:

- ``auth login | status | logout``: sesión de Trakt (device flow).
- ``validate <fichero>``: valida una definición sin contactar con Trakt.
- ``sync <fichero> [--dry-run] [--include-extras]``: crea o actualiza la lista.
- ``lists``: listas del usuario.
- ``show <lista>``: elementos de una lista en orden.
- ``serve``: arranca la API HTTP y la GUI web.

``validate``, ``sync``, ``lists`` y ``show`` aceptan ``--json`` para emitir el
mismo resultado que devuelve la API. El código de salida es 0 si todo fue bien
y 1 ante cualquier error (validación, configuración, autenticación o Trakt).
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, TypeVar

import typer
from pydantic import BaseModel

from trakt_manager.app_context import AppContext, AppRuntime
from trakt_manager.config import Settings
from trakt_manager.definitions import ValidationOutcome, load_definition_file
from trakt_manager.errors import DefinitionError, TraktManagerError
from trakt_manager.sync import SyncResult

app = typer.Typer(
    help="Gestiona listas de Trakt a partir de ficheros de definición.",
    no_args_is_help=True,
    add_completion=False,
)
auth_app = typer.Typer(help="Sesión de Trakt: iniciar, consultar y cerrar.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")

Result = TypeVar("Result")

JsonOption = Annotated[bool, typer.Option("--json", help="Emite el resultado como JSON en la salida estándar.")]
DefinitionArgument = Annotated[Path, typer.Argument(help="Fichero de definición (.yaml, .yml o .json).")]


@app.callback()
def configure(ctx: typer.Context) -> None:
    """Prepara el contexto de la aplicación con la configuración efectiva.

    La configuración efectiva combina el entorno con lo guardado desde la GUI, de
    modo que el CLI dentro del contenedor usa las mismas credenciales que la web.
    """
    # Los tests inyectan su propio contexto (con un Trakt simulado) mediante ``obj``.
    if ctx.obj is None:
        ctx.obj = AppRuntime(Settings()).current()


# --- auth ------------------------------------------------------------------------------------


@auth_app.command("login")
def auth_login(ctx: typer.Context) -> None:
    """Inicia sesión en Trakt: muestra una URL y un código para confirmar en el navegador."""
    context: AppContext = ctx.obj

    def login() -> str:
        authorizer = context.device_authorizer()
        code = authorizer.start()
        typer.echo("=== Autorización en Trakt ===")
        typer.echo(f"1. Abre en tu navegador: {code.verification_url}")
        typer.echo(f"2. Introduce este código: {code.user_code}")
        typer.echo("Esperando confirmación...")
        authorizer.wait_for_authorization(code)
        return context.username()

    username = _run_or_exit(login)
    typer.echo(f"Sesión iniciada como {username}.")


@auth_app.command("status")
def auth_status(ctx: typer.Context) -> None:
    """Muestra si hay sesión de Trakt y con qué usuario."""
    context: AppContext = ctx.obj
    if not context.has_session():
        typer.echo("Sin sesión de Trakt. Ejecuta 'trakt-manager auth login'.")
        return
    username = _run_or_exit(context.username)
    typer.echo(f"Sesión activa como {username}.")


@auth_app.command("logout")
def auth_logout(ctx: typer.Context) -> None:
    """Cierra la sesión: revoca el token en Trakt y lo borra."""
    context: AppContext = ctx.obj
    closed = _run_or_exit(context.logout)
    typer.echo("Sesión cerrada." if closed else "No había ninguna sesión abierta.")


# --- definiciones y sincronización -----------------------------------------------------------


@app.command("validate")
def validate(definition_file: DefinitionArgument, as_json: JsonOption = False) -> None:
    """Valida una definición sin contactar con Trakt."""
    try:
        outcome = ValidationOutcome.from_definition(load_definition_file(definition_file))
    except DefinitionError as error:
        outcome = ValidationOutcome.from_error(error)

    if as_json:
        _echo_json(outcome)
    elif outcome.valid:
        typer.echo(f"Definición válida: '{outcome.name}' con {outcome.entries} entradas ({outcome.extras} extras).")
    else:
        typer.echo(f"La definición {definition_file} tiene {len(outcome.errors)} errores:", err=True)
        for issue in outcome.errors:
            location = f"entrada {issue.entry_position}" if issue.entry_position else "lista"
            typer.echo(f"  - {location}, campo '{issue.field}': {issue.message}", err=True)

    if not outcome.valid:
        raise typer.Exit(code=1)


@app.command("sync")
def sync(
    ctx: typer.Context,
    definition_file: DefinitionArgument,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Muestra los cambios sin modificar la cuenta de Trakt.")] = False,
    include_extras: Annotated[bool, typer.Option("--include-extras", help="Incluye las entradas marcadas como extra.")] = False,
    as_json: JsonOption = False,
) -> None:
    """Crea o actualiza en Trakt la lista descrita en una definición."""
    context: AppContext = ctx.obj

    def run_sync() -> SyncResult:
        definition = load_definition_file(definition_file)
        return context.synchronizer.sync(definition, include_extras=include_extras, dry_run=dry_run)

    result = _run_or_exit(run_sync)
    if as_json:
        _echo_json(result)
    else:
        _print_sync_result(result)


# --- consulta --------------------------------------------------------------------------------


@app.command("lists")
def lists(ctx: typer.Context, as_json: JsonOption = False) -> None:
    """Muestra las listas de tu cuenta de Trakt."""
    context: AppContext = ctx.obj
    summaries = _run_or_exit(lambda: context.lists_api.get_user_lists())
    if as_json:
        _echo_json([summary.model_dump(mode="json") for summary in summaries])
        return
    if not summaries:
        typer.echo("No tienes listas en Trakt.")
        return
    rows = [[str(s.trakt_id), s.name, s.privacy, str(s.item_count)] for s in summaries]
    _print_table(["ID", "Nombre", "Privacidad", "Elementos"], rows)


@app.command("show")
def show(
    ctx: typer.Context,
    list_id: Annotated[str, typer.Argument(help="Id numérico o slug de la lista.")],
    as_json: JsonOption = False,
) -> None:
    """Muestra los elementos de una lista en su orden."""
    context: AppContext = ctx.obj

    def load_list() -> tuple[Any, list[Any]]:
        summary = context.lists_api.get_list(list_id)
        return summary, context.lists_api.get_items(summary.trakt_id)

    summary, items = _run_or_exit(load_list)
    if as_json:
        _echo_json({"list": summary.model_dump(mode="json"), "items": [item.model_dump(mode="json") for item in items]})
        return
    typer.echo(f"{summary.name} ({summary.privacy}, {summary.item_count} elementos)")
    for item in items:
        note = f"  — {item.notes}" if item.notes else ""
        typer.echo(f"  {item.rank:>3}. [{item.kind}] {item.label}{note}")


# --- servidor --------------------------------------------------------------------------------


@app.command("serve")
def serve(
    host: Annotated[str | None, typer.Option(help="Dirección en la que escuchar (por defecto API_HOST).")] = None,
    port: Annotated[int | None, typer.Option(help="Puerto en el que escuchar (por defecto API_PORT).")] = None,
) -> None:
    """Arranca la API y la GUI web (en modo configuración si falta la configuración)."""
    # Importaciones locales: uvicorn y la API solo hacen falta para este comando.
    import logging

    import uvicorn

    from trakt_manager.api import create_app

    # Sin esto los mensajes de la aplicación (como el código de configuración) no
    # aparecerían con formato en los registros del contenedor.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # El runtime se crea desde el entorno (no desde ctx.obj) para distinguir lo que
    # viene del entorno de lo guardado desde la GUI.
    runtime = AppRuntime(Settings())
    settings = runtime.current().settings
    # Un solo worker: los bloqueos de sincronización y el device flow viven en este proceso.
    uvicorn.run(create_app(runtime), host=host or settings.api_host, port=port or settings.api_port, workers=1)


# --- utilidades ------------------------------------------------------------------------------


def _run_or_exit(action: Callable[[], Result]) -> Result:
    """Ejecuta ``action`` y, si lanza un error de la aplicación, lo muestra y sale con código 1.

    ``action`` debe ser una función sin evaluar (por ejemplo una ``lambda``): así
    también se capturan los errores al construir las dependencias, como la falta
    de ``TRAKT_CLIENT_ID``.
    """
    try:
        return action()
    except TraktManagerError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from error


def _echo_json(value: BaseModel | list[Any] | dict[str, Any]) -> None:
    """Escribe ``value`` como un único documento JSON en la salida estándar."""
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Imprime una tabla de texto con columnas alineadas."""
    widths = [max(len(row[column]) for row in [headers, *rows]) for column in range(len(headers))]
    for row in [headers, ["-" * width for width in widths], *rows]:
        typer.echo("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip())


def _print_sync_result(result: SyncResult) -> None:
    """Muestra el informe de resolución y los cambios de una sincronización."""
    report = result.report
    plan = result.plan

    typer.echo(f"Resolución de '{result.list_name}':")
    for entry in report.resolved:
        year = f" ({entry.matched_year})" if entry.matched_year else ""
        typer.echo(
            f"  [OK] #{entry.position:02d} {entry.entry_title} -> {entry.matched_title}{year}"
            f" [trakt:{entry.trakt_id}] · {len(entry.items)} elementos"
        )
    for missing in report.unresolved:
        typer.echo(f"  [NO ENCONTRADO] #{missing.position:02d} {missing.label} ({missing.reason})")

    heading = "Cambios previstos (dry-run, no se ha modificado nada):" if result.dry_run else "Cambios:"
    typer.echo(heading)
    if not plan.compared_with_account:
        typer.echo("  (sin sesión de Trakt: se compara como si la lista no existiera)")
    if not plan.has_changes:
        typer.echo("  La lista ya coincide con la definición.")
    else:
        if plan.create_list:
            typer.echo("  Crear la lista")
        for change in plan.metadata_changes:
            typer.echo(f"  Cambiar {change.field}: {change.current!r} -> {change.desired!r}")
        typer.echo(
            f"  Añadir: {len(plan.to_add)} · Quitar: {len(plan.to_remove)} · "
            f"Notas: {len(plan.note_updates)} · Reordenar: {'sí' if plan.reorder else 'no'}"
        )
        for item in plan.to_remove:
            typer.echo(f"    - {item.label}")
    for duplicate in plan.duplicates_skipped:
        typer.echo(f"  Repetido en la definición (se añade una sola vez): {duplicate}")
    for warning in result.warnings:
        typer.echo(f"Aviso: {warning}", err=True)
    if not result.dry_run and result.list_id is not None:
        typer.echo(f"Lista sincronizada (id {result.list_id}): {len(plan.final_order)} elementos.")


def main() -> None:
    """Punto de entrada del comando ``trakt-manager``."""
    app()
