"""Tests de la autorización con Trakt: almacén del token, device flow, renovación y sesión."""

import json
import stat
from pathlib import Path

import httpx
import pytest

from trakt_manager.auth import (
    DeviceCode,
    DeviceFlowAuthorizer,
    TokenManager,
    TokenStore,
    get_username,
)
from trakt_manager.errors import AuthError, DeviceCodeExpiredError, NotAuthenticatedError
from trakt_manager.trakt_client import TraktClient

TOKEN = {"access_token": "access-1", "refresh_token": "refresh-1", "created_at": 1_000, "expires_in": 7_776_000}


class FakeClock:
    """Reloj controlable: avanza cuando se llama a ``sleep``."""

    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_client(handler) -> TraktClient:
    """Cliente de Trakt sin pausas que responde con ``handler``."""
    return TraktClient("client-id", base_url="https://trakt.test", request_delay=0, transport=httpx.MockTransport(handler))


# --- TokenStore -------------------------------------------------------------------------------


def test_token_store_round_trip_with_private_permissions(tmp_path: Path) -> None:
    """El token se guarda, se lee igual y el fichero solo es accesible por su dueño."""
    store = TokenStore(tmp_path / "data" / "token.json")
    store.save(TOKEN)
    assert store.load() == TOKEN
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert store.delete() is True
    assert store.load() is None
    assert store.delete() is False


def test_corrupt_token_file_counts_as_no_session(tmp_path: Path) -> None:
    """Un fichero de token ilegible se trata como si no hubiera sesión."""
    path = tmp_path / "token.json"
    path.write_text("{no es json", encoding="utf-8")
    assert TokenStore(path).load() is None


# --- Device flow ------------------------------------------------------------------------------


def device_code(expires_in: int = 600) -> DeviceCode:
    return DeviceCode("dev-code", "ABCD1234", "https://trakt.tv/activate", expires_in, 5)


def test_device_flow_success_saves_token(tmp_path: Path) -> None:
    """Tras un sondeo pendiente (400) y la confirmación (200) se guarda el token."""
    responses = iter([httpx.Response(400), httpx.Response(200, json=TOKEN)])
    clock = FakeClock()
    store = TokenStore(tmp_path / "token.json")
    authorizer = DeviceFlowAuthorizer(make_client(lambda r: next(responses)), "secret", store, clock.sleep, clock.time)
    assert authorizer.wait_for_authorization(device_code()) == TOKEN
    assert store.load() == TOKEN
    assert clock.sleeps == [5, 5]


def test_device_flow_slows_down_on_429(tmp_path: Path) -> None:
    """Un 429 durante el sondeo aumenta el intervalo y se sigue esperando."""
    responses = iter([httpx.Response(429), httpx.Response(200, json=TOKEN)])
    clock = FakeClock()
    authorizer = DeviceFlowAuthorizer(
        make_client(lambda r: next(responses)), "secret", TokenStore(tmp_path / "t.json"), clock.sleep, clock.time
    )
    authorizer.wait_for_authorization(device_code())
    assert clock.sleeps == [5, 6]


def test_device_flow_expired_code_saves_nothing(tmp_path: Path) -> None:
    """Si el código caduca sin confirmarse se informa y no se guarda token."""
    clock = FakeClock()
    store = TokenStore(tmp_path / "token.json")
    authorizer = DeviceFlowAuthorizer(make_client(lambda r: httpx.Response(400)), "secret", store, clock.sleep, clock.time)
    with pytest.raises(DeviceCodeExpiredError):
        authorizer.wait_for_authorization(device_code(expires_in=12))
    assert store.load() is None


def test_device_flow_denied_by_user(tmp_path: Path) -> None:
    """Si el usuario deniega el acceso (418) se lanza un AuthError explicativo."""
    clock = FakeClock()
    authorizer = DeviceFlowAuthorizer(
        make_client(lambda r: httpx.Response(418)), "secret", TokenStore(tmp_path / "t.json"), clock.sleep, clock.time
    )
    with pytest.raises(AuthError, match="denegado"):
        authorizer.wait_for_authorization(device_code())


def test_device_flow_start_returns_code() -> None:
    """start() traduce la respuesta de Trakt a un DeviceCode."""
    payload = {"device_code": "d", "user_code": "U", "verification_url": "https://trakt.tv/activate", "expires_in": 600, "interval": 5}
    authorizer = DeviceFlowAuthorizer(make_client(lambda r: httpx.Response(200, json=payload)), "s", TokenStore(Path("/nonexistent")))
    assert authorizer.start() == DeviceCode("d", "U", "https://trakt.tv/activate", 600, 5)


# --- Renovación -------------------------------------------------------------------------------


def test_reuses_valid_token_without_calling_trakt(tmp_path: Path) -> None:
    """Un token vigente se usa tal cual."""
    store = TokenStore(tmp_path / "token.json")
    store.save(TOKEN)
    client = make_client(lambda r: pytest.fail("no debería llamar a Trakt"))
    assert TokenManager(store, client, "secret", clock=lambda: 2_000).get_access_token() == "access-1"


def test_no_saved_token_requires_login(tmp_path: Path) -> None:
    """Sin token guardado se pide autenticarse primero."""
    manager = TokenManager(TokenStore(tmp_path / "token.json"), make_client(lambda r: httpx.Response(500)), "secret")
    with pytest.raises(NotAuthenticatedError, match="auth login"):
        manager.get_access_token()


def test_expired_token_is_refreshed_and_saved(tmp_path: Path) -> None:
    """Un token caducado se renueva con el refresh_token y se guarda el nuevo."""
    store = TokenStore(tmp_path / "token.json")
    store.save(TOKEN)
    refreshed = dict(TOKEN, access_token="access-2", refresh_token="refresh-2")
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=refreshed)

    manager = TokenManager(store, make_client(handler), "secret", clock=lambda: 10_000_000_000)
    assert manager.get_access_token() == "access-2"
    assert seen[0]["grant_type"] == "refresh_token"
    assert seen[0]["refresh_token"] == "refresh-1"
    assert store.load() == refreshed


def test_401_triggers_refresh_and_retry(tmp_path: Path) -> None:
    """Si Trakt rechaza el token (401) el cliente lo renueva y repite la petición."""
    store = TokenStore(tmp_path / "token.json")
    store.save(TOKEN)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json=dict(TOKEN, access_token="access-2"))
        if request.headers.get("Authorization") == "Bearer access-1":
            return httpx.Response(401)
        return httpx.Response(200, json={"user": {"username": "pedro"}})

    client = make_client(handler)
    client.set_token_source(TokenManager(store, client, "secret", clock=lambda: 2_000))
    assert get_username(client) == "pedro"
    assert store.load()["access_token"] == "access-2"


def test_rejected_refresh_asks_to_login_again(tmp_path: Path) -> None:
    """Si Trakt rechaza el refresh_token se pide volver a autenticarse."""
    store = TokenStore(tmp_path / "token.json")
    store.save(TOKEN)
    manager = TokenManager(store, make_client(lambda r: httpx.Response(401)), "secret")
    with pytest.raises(AuthError, match="auth login"):
        manager.refresh_access_token()


# --- Estado y cierre de sesión ----------------------------------------------------------------


def test_logout_revokes_and_deletes(tmp_path: Path) -> None:
    """Cerrar sesión revoca el token en Trakt y borra el fichero."""
    store = TokenStore(tmp_path / "token.json")
    store.save(TOKEN)
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200)

    manager = TokenManager(store, make_client(handler), "secret")
    assert manager.logout() is True
    assert paths == ["/oauth/revoke"]
    assert not store.exists()


# --- Client Secret opcional -------------------------------------------------------------------


class RecordingTrakt:
    """Responde con ``responses`` en orden y guarda el cuerpo JSON de cada petición."""

    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.bodies: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content) if request.content else {})
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


@pytest.mark.parametrize(("secret", "sends_secret"), [(None, False), ("", False), ("secret", True)])
def test_device_flow_sends_secret_only_if_configured(tmp_path: Path, secret, sends_secret: bool) -> None:
    """El sondeo del device flow solo envía client_secret si la aplicación lo tiene."""
    trakt = RecordingTrakt(httpx.Response(200, json=TOKEN))
    clock = FakeClock()
    authorizer = DeviceFlowAuthorizer(make_client(trakt), secret, TokenStore(tmp_path / "t.json"), clock.sleep, clock.time)
    authorizer.wait_for_authorization(device_code())
    assert trakt.bodies[0]["client_id"] == "client-id"
    assert ("client_secret" in trakt.bodies[0]) is sends_secret


def test_refresh_and_revoke_without_secret(tmp_path: Path) -> None:
    """Sin secreto, la renovación y la revocación se hacen solo con el Client ID."""
    store = TokenStore(tmp_path / "token.json")
    store.save(TOKEN)
    trakt = RecordingTrakt(httpx.Response(200, json=dict(TOKEN, access_token="access-2")))
    manager = TokenManager(store, make_client(trakt), None)
    assert manager.refresh_access_token() == "access-2"
    assert manager.logout() is True
    assert [("client_secret" in body) for body in trakt.bodies] == [False, False]
    assert trakt.bodies[0]["grant_type"] == "refresh_token"


def test_device_flow_rejected_without_secret_explains_why(tmp_path: Path) -> None:
    """Si Trakt rechaza la aplicación sin secreto (aunque sea con un 400), el error lo explica."""
    trakt = RecordingTrakt(httpx.Response(400, json={"error": "invalid_client"}))
    clock = FakeClock()
    authorizer = DeviceFlowAuthorizer(make_client(trakt), None, TokenStore(tmp_path / "t.json"), clock.sleep, clock.time)
    with pytest.raises(AuthError, match="Client Secret"):
        authorizer.wait_for_authorization(device_code())
    assert len(trakt.bodies) == 1, "no debe seguir sondeando"


def test_pending_400_without_body_keeps_polling_without_secret(tmp_path: Path) -> None:
    """Sin secreto, un 400 sin cuerpo sigue significando "pendiente"."""
    trakt = RecordingTrakt(httpx.Response(400), httpx.Response(200, json=TOKEN))
    clock = FakeClock()
    authorizer = DeviceFlowAuthorizer(make_client(trakt), None, TokenStore(tmp_path / "t.json"), clock.sleep, clock.time)
    assert authorizer.wait_for_authorization(device_code()) == TOKEN


def test_refresh_rejected_without_secret_explains_why(tmp_path: Path) -> None:
    """Si Trakt rechaza la renovación de una aplicación sin secreto, el error lo explica."""
    store = TokenStore(tmp_path / "token.json")
    store.save(TOKEN)
    manager = TokenManager(store, make_client(lambda request: httpx.Response(401)), None)
    with pytest.raises(AuthError, match="Client Secret"):
        manager.refresh_access_token()
