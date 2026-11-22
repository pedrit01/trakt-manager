"""Comprobaciones básicas de que el paquete se instala e importa correctamente."""

import trakt_manager


def test_package_exposes_version() -> None:
    """El paquete declara una versión en formato semántico."""
    assert trakt_manager.__version__.count(".") == 2
