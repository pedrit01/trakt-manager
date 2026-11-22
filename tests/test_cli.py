"""Tests del CLI ``trakt-manager`` con un Trakt simulado."""

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from conftest import make_context
from trakt_manager.cli import app

DOOMSDAY_FILE = Path(__file__).resolve().parent.parent / "lists" / "doomsday.yaml"
DEFINITION = {
    "name": "Ruta UCM",
    "entries": [
        {"type": "episodes", "query": "WandaVision", "season": 1, "episodes": [8, 9]},
        {"type": "movie", "query": "Shang-Chi", "year": 2021},
        {"type": "episodes", "query": "VisionQuest", "season": 1, "episodes": [1, 7]},
    ],
}

runner = CliRunner()


def write_definition(tmp_path: Path, data: dict = DEFINITION) -> Path:
    path = tmp_path / "ruta.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_validate_valid_definition_exits_zero() -> None:
    """validate sobre la ruta Doomsday informa de que es válida y sale con 0."""
    result = runner.invoke(app, ["validate", str(DOOMSDAY_FILE)])
    assert result.exit_code == 0, result.output
    assert "Definición válida" in result.output and "21 entradas (4 extras)" in result.output


def test_validate_invalid_definition_lists_all_errors(tmp_path: Path) -> None:
    """validate muestra todos los errores con su posición y sale con código distinto de 0."""
    path = write_definition(tmp_path, {"name": "X", "privacy": "secreta", "entries": [{"type": "movie"}]})
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1
    assert "campo 'privacy'" in result.output and "entrada 1, campo 'query'" in result.output


def test_validate_json_output_is_parseable(tmp_path: Path) -> None:
    """Con --json la salida estándar es un único documento JSON."""
    result = runner.invoke(app, ["validate", str(write_definition(tmp_path)), "--json"])
    assert json.loads(result.stdout) == {"valid": True, "name": "Ruta UCM", "entries": 3, "extras": 0, "errors": []}


def test_sync_dry_run_does_not_touch_account(tmp_path: Path, fake_trakt) -> None:
    """sync --dry-run muestra el informe y los cambios sin modificar la cuenta."""
    context = make_context(tmp_path, fake_trakt)
    result = runner.invoke(app, ["sync", str(write_definition(tmp_path)), "--dry-run"], obj=context)
    assert result.exit_code == 0, result.output
    assert "[NO ENCONTRADO] #03 VisionQuest S01E07" in result.output
    assert "Crear la lista" in result.output and "Añadir: 4" in result.output
    assert fake_trakt.write_requests() == []


def test_sync_without_session_asks_to_login(tmp_path: Path, fake_trakt) -> None:
    """sync real sin sesión indica que hay que ejecutar auth login y sale con error."""
    context = make_context(tmp_path, fake_trakt, logged_in=False)
    result = runner.invoke(app, ["sync", str(write_definition(tmp_path))], obj=context)
    assert result.exit_code == 1
    assert "auth login" in result.output


def test_sync_then_lists_and_show(tmp_path: Path, fake_trakt) -> None:
    """Tras sincronizar, lists y show muestran la lista y sus elementos en orden."""
    context = make_context(tmp_path, fake_trakt)
    sync_result = runner.invoke(app, ["sync", str(write_definition(tmp_path)), "--json"], obj=context)
    assert sync_result.exit_code == 0, sync_result.output
    synced = json.loads(sync_result.stdout)
    assert synced["applied"] is True

    lists_result = runner.invoke(app, ["lists", "--json"], obj=context)
    [summary] = json.loads(lists_result.stdout)
    assert (summary["name"], summary["item_count"]) == ("Ruta UCM", 4)

    show_result = runner.invoke(app, ["show", str(summary["trakt_id"])], obj=context)
    assert show_result.exit_code == 0, show_result.output
    assert "1. [episode] WandaVision S01E08" in show_result.output


def test_lists_table_output(tmp_path: Path, fake_trakt) -> None:
    """lists sin --json muestra una tabla con nombre, id, privacidad y elementos."""
    fake_trakt.create_list("Pendientes", privacy="public")
    result = runner.invoke(app, ["lists"], obj=make_context(tmp_path, fake_trakt))
    assert result.exit_code == 0
    assert "Privacidad" in result.output and "Pendientes" in result.output and "public" in result.output


def test_missing_client_id_is_reported(tmp_path: Path, fake_trakt) -> None:
    """Sin TRAKT_CLIENT_ID el comando falla nombrando la variable."""
    context = make_context(tmp_path, fake_trakt, trakt_client_id=None)
    result = runner.invoke(app, ["lists"], obj=context)
    assert result.exit_code == 1
    assert "TRAKT_CLIENT_ID" in result.output


def test_auth_status_and_logout(tmp_path: Path, fake_trakt) -> None:
    """auth status muestra el usuario y auth logout borra la sesión."""
    context = make_context(tmp_path, fake_trakt)
    assert "Sesión activa como pedro" in runner.invoke(app, ["auth", "status"], obj=context).output
    assert "Sesión cerrada" in runner.invoke(app, ["auth", "logout"], obj=context).output
    assert "Sin sesión" in runner.invoke(app, ["auth", "status"], obj=context).output
