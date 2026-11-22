"""Tests del código de configuración de un solo uso."""

import logging

import pytest

from trakt_manager.setup_guard import MAX_FAILED_ATTEMPTS, SetupGuard, generate_setup_code


def sequential_codes():
    """Fábrica de códigos predecibles: CODE-0001, CODE-0002..."""
    counter = iter(range(1, 1000))
    return lambda: f"CODE-{next(counter):04d}"


def test_generated_code_format() -> None:
    """Los códigos tienen el formato XXXX-XXXX en hexadecimal."""
    code = generate_setup_code()
    assert len(code) == 9 and code[4] == "-"
    int(code.replace("-", ""), 16)


def test_issued_code_is_written_to_the_log(caplog: pytest.LogCaptureFixture) -> None:
    """Al emitir el código se escribe en los registros con nivel WARNING."""
    with caplog.at_level(logging.WARNING, logger="trakt_manager.setup"):
        code = SetupGuard(sequential_codes()).issue()
    assert code in caplog.text


def test_correct_code_is_accepted_case_insensitively() -> None:
    """El código correcto se acepta aunque se escriba en minúsculas o con espacios."""
    guard = SetupGuard(lambda: "AB12-CD34")
    guard.issue()
    assert guard.verify(" ab12-cd34 ")


def test_wrong_code_is_rejected() -> None:
    """Un código incorrecto se rechaza."""
    guard = SetupGuard(sequential_codes())
    guard.issue()
    assert not guard.verify("XXXX-XXXX")


def test_code_is_replaced_after_too_many_failures() -> None:
    """Tras demasiados fallos se emite un código nuevo y el anterior deja de valer."""
    guard = SetupGuard(sequential_codes())
    guard.issue()  # CODE-0001
    for _ in range(MAX_FAILED_ATTEMPTS):
        guard.verify("MALO")
    assert not guard.verify("CODE-0001")
    assert guard.verify("CODE-0002")


def test_invalidated_code_no_longer_works() -> None:
    """Tras completar la configuración, el código deja de valer."""
    guard = SetupGuard(lambda: "AB12-CD34")
    guard.issue()
    guard.invalidate()
    assert not guard.is_active
    assert not guard.verify("AB12-CD34")
