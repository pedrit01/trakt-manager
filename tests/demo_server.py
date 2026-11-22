"""Servidor de demostración de la GUI con un Trakt simulado (para desarrollo, no para producción).

Arranca la API y la GUI conectadas a ``FakeTrakt``, sin credenciales reales, para
probar la interfaz en un navegador:

    docker compose run --rm -p 8080:8080 --entrypoint python tests tests/demo_server.py

Arranca en modo configuración: el código aparece en la salida (``AB12-CD34``).
Cualquier Client ID/Secret vale. En la vista de Trakt, el device flow se confirma
solo a los 6 segundos de pedir el código, como si el usuario lo hubiera aceptado.
"""

import sys
import tempfile
import threading
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).parent))

from fake_trakt import FAKE_BASE_URL, FakeTrakt  # noqa: E402
from trakt_manager.api import create_app  # noqa: E402
from trakt_manager.app_context import AppContext, AppRuntime  # noqa: E402
from trakt_manager.config import Settings  # noqa: E402
from trakt_manager.setup_guard import SetupGuard  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTO_CONFIRM_SECONDS = 6


def build_fake_trakt() -> FakeTrakt:
    """Trakt simulado con algunos títulos de la ruta Doomsday."""
    fake = FakeTrakt()
    fake.add_movie(1, "Shang-Chi and the Legend of the Ten Rings", 2021, tmdb=566525)
    fake.add_movie(2, "Spider-Man: No Way Home", 2021)
    fake.add_movie(3, "Doctor Strange in the Multiverse of Madness", 2022)
    fake.add_movie(4, "X-Men", 2000, tmdb=36657)
    fake.add_show(7, "WandaVision", 2021, {1: list(range(1, 10))})
    fake.add_show(8, "Loki", 2021, {1: list(range(1, 7)), 2: list(range(1, 7))})
    fake.add_show(11, "The Falcon and the Winter Soldier", 2021, {1: list(range(1, 7))})
    return fake


def main() -> None:
    """Arranca el servidor de demostración en el puerto 8080."""
    fake = build_fake_trakt()
    original_device_code = fake._device_code

    def device_code_with_auto_confirm(request, body):
        # Simula que el usuario confirma el código en trakt.tv unos segundos después.
        fake.device_authorized = False
        threading.Timer(AUTO_CONFIRM_SECONDS, lambda: setattr(fake, "device_authorized", True)).start()
        return original_device_code(request, body)

    fake._device_code = device_code_with_auto_confirm

    def factory(settings: Settings) -> AppContext:
        return AppContext(settings, transport=fake.transport(), base_url=FAKE_BASE_URL)

    data_dir = Path(tempfile.mkdtemp(prefix="trakt-manager-demo-"))
    settings = Settings(_env_file=None, data_dir=data_dir, lists_dir=PROJECT_ROOT / "lists", request_delay=0)
    runtime = AppRuntime(settings, context_factory=factory, setup_guard=SetupGuard(lambda: "AB12-CD34"))
    uvicorn.run(create_app(runtime), host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
