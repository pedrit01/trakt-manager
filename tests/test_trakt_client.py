"""Tests del cliente HTTP de Trakt: cabeceras, reintentos y renovación del token."""

import httpx
import pytest

from trakt_manager.errors import NotAuthenticatedError, TraktAPIError
from trakt_manager.trakt_client import USER_AGENT, TraktClient


class RecordingSleep:
    """Sustituto de ``time.sleep`` que apunta las esperas en lugar de esperar."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_client(handler, sleep: RecordingSleep | None = None) -> TraktClient:
    """Crea un cliente que responde con ``handler`` y no espera de verdad."""
    return TraktClient(
        "client-id",
        base_url="https://trakt.test",
        request_delay=0,
        transport=httpx.MockTransport(handler),
        sleep=sleep or RecordingSleep(),
    )


def test_sends_required_headers() -> None:
    """Cada petición lleva la versión de la API, el Client ID y un User-Agent genérico."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    assert make_client(handler).request_json("GET", "/ping") == {"ok": True}
    headers = seen[0].headers
    assert headers["trakt-api-version"] == "2"
    assert headers["trakt-api-key"] == "client-id"
    assert headers["User-Agent"] == USER_AGENT
    assert "Authorization" not in headers


def test_retries_after_rate_limit_using_retry_after() -> None:
    """Un 429 espera lo que indica Retry-After y reintenta la petición."""
    responses = iter([httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json=[1])])
    sleep = RecordingSleep()
    client = make_client(lambda request: next(responses), sleep)
    assert client.request_json("GET", "/x") == [1]
    assert sleep.calls == [3.0]


def test_gives_up_after_repeated_server_errors() -> None:
    """Tras agotar los reintentos ante 5xx se lanza un TraktAPIError con el código."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, text="mantenimiento")

    with pytest.raises(TraktAPIError) as error:
        make_client(handler).request_json("GET", "/x")
    assert error.value.status_code == 503
    assert len(calls) == 4  # la petición original más 3 reintentos


def test_network_errors_are_retried_then_reported() -> None:
    """Los errores de red se reintentan y, si persisten, se informa sin código HTTP."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    with pytest.raises(TraktAPIError) as error:
        make_client(handler).request("GET", "/x")
    assert error.value.status_code is None


class FakeTokenSource:
    """Proveedor de tokens que cambia de token al renovar."""

    def __init__(self) -> None:
        self.token = "old"
        self.refreshes = 0

    def get_access_token(self) -> str:
        return self.token

    def refresh_access_token(self) -> str:
        self.refreshes += 1
        self.token = "new"
        return self.token


def test_unauthorized_response_refreshes_token_once() -> None:
    """Un 401 en una petición autenticada renueva el token y repite la petición."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer old":
            return httpx.Response(401)
        return httpx.Response(200, json={"user": "ok"})

    client = make_client(handler)
    tokens = FakeTokenSource()
    client.set_token_source(tokens)
    assert client.request_json("GET", "/users/settings", authenticated=True) == {"user": "ok"}
    assert tokens.refreshes == 1


def test_authenticated_request_without_token_source_fails() -> None:
    """Sin proveedor de tokens una petición autenticada falla antes de enviarse."""
    client = make_client(lambda request: httpx.Response(200))
    with pytest.raises(NotAuthenticatedError):
        client.request("GET", "/users/me/lists", authenticated=True)


def test_follows_pagination_headers() -> None:
    """get_all_pages junta todas las páginas que anuncia Trakt."""

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=[page], headers={"X-Pagination-Page-Count": "3", "X-Pagination-Limit": "1"})

    assert make_client(handler).get_all_pages("/items") == [1, 2, 3]
