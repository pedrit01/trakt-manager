"""Fixtures compartidas: un Trakt simulado con un pequeño catálogo y clientes conectados a él."""

import pytest

from fake_trakt import FAKE_BASE_URL, FakeTrakt
from trakt_manager.trakt_client import TraktClient


class StaticTokenSource:
    """Proveedor de tokens fijo para los tests que necesitan sesión."""

    def get_access_token(self) -> str:
        return "test-token"

    def refresh_access_token(self) -> str:
        return "test-token"


@pytest.fixture
def fake_trakt() -> FakeTrakt:
    """Trakt simulado con algunas películas y series del UCM."""
    fake = FakeTrakt()
    fake.add_movie(1, "Shang-Chi and the Legend of the Ten Rings", 2021, tmdb=566525)
    fake.add_movie(2, "Spider-Man: No Way Home", 2021)
    fake.add_movie(3, "Doctor Strange in the Multiverse of Madness", 2022)
    fake.add_movie(4, "X-Men", 2000, tmdb=36657)
    fake.add_movie(5, "X-Men: The Last Stand", 2006)
    fake.add_movie(6, "X-Men Origins: Wolverine", 2009)
    fake.add_show(7, "WandaVision", 2021, {1: [1, 2, 3, 4, 5, 6, 7, 8, 9]})
    fake.add_show(8, "Loki", 2021, {1: [1, 2, 3, 4, 5, 6], 2: [1, 2, 3, 4, 5, 6]})
    fake.add_show(9, "VisionQuest", 2026, {1: [1, 2]})
    return fake


@pytest.fixture
def trakt_client(fake_trakt: FakeTrakt) -> TraktClient:
    """Cliente de Trakt conectado al simulado y con sesión."""
    client = TraktClient("client-id", base_url=FAKE_BASE_URL, request_delay=0, transport=fake_trakt.transport())
    client.set_token_source(StaticTokenSource())
    return client


def make_context(tmp_path, fake: FakeTrakt, *, logged_in: bool = True, sleep=lambda seconds: None, **settings):
    """Crea un AppContext conectado al Trakt simulado y con datos en ``tmp_path``."""
    from trakt_manager.app_context import AppContext
    from trakt_manager.config import Settings

    values = {"trakt_client_id": "client-id", "trakt_client_secret": "secret", "data_dir": tmp_path, "request_delay": 0}
    values.update(settings)
    context = AppContext(Settings(_env_file=None, **values), transport=fake.transport(), base_url=FAKE_BASE_URL, sleep=sleep)
    if logged_in:
        context.token_store.save({"access_token": "test-token", "refresh_token": "r", "created_at": 9_999_999_999, "expires_in": 7_776_000})
    return context
