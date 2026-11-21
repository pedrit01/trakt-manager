"""Simulación en memoria de la API de Trakt para los tests.

Implementa solo los endpoints que usa trakt-manager, con un comportamiento lo
bastante fiel para probar la sincronización de extremo a extremo (búsqueda,
temporadas, listas del usuario, añadir, quitar, reordenar y notas) sin llamar
nunca a la API real.

Uso::

    fake = FakeTrakt()
    fake.add_movie(1, "Shang-Chi", 2021)
    client = TraktClient("id", base_url=FAKE_BASE_URL, transport=fake.transport(), request_delay=0)
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

FAKE_BASE_URL = "https://trakt.test"
PLURAL_TO_KIND = {"movies": "movie", "shows": "show", "seasons": "season", "episodes": "episode"}


@dataclass
class FakeList:
    """Una lista del usuario simulada."""

    trakt_id: int
    metadata: dict[str, Any]
    items: list[dict[str, Any]] = field(default_factory=list)


class FakeTrakt:
    """Estado y comportamiento de un Trakt simulado.

    Atributos:
        requests: Todas las peticiones recibidas, en orden, como ``(método, ruta)``.
        notes_supported: Si es ``False`` la cuenta no es VIP: ``/users/settings`` lo indica
            y las notas se descartan al añadir elementos, como hace Trakt.
        username: Usuario de la sesión simulada.
    """

    def __init__(self) -> None:
        self.movies: dict[int, dict[str, Any]] = {}
        self.shows: dict[int, dict[str, Any]] = {}
        self.seasons: dict[int, list[dict[str, Any]]] = {}
        self.episodes: dict[tuple[int, int], list[dict[str, Any]]] = {}
        self.lists: dict[int, FakeList] = {}
        self.requests: list[tuple[str, str]] = []
        self.notes_supported = True
        self.username = "pedro"
        self.device_authorized = False
        self._next_id = 10_000

    # --- Preparación de datos -----------------------------------------------------------------

    def add_movie(self, trakt_id: int, title: str, year: int, tmdb: int | None = None) -> None:
        """Añade una película al catálogo simulado."""
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        self.movies[trakt_id] = {"title": title, "year": year, "ids": {"trakt": trakt_id, "slug": slug, "tmdb": tmdb}}

    def add_show(self, trakt_id: int, title: str, year: int, seasons: dict[int, list[int]]) -> None:
        """Añade una serie con sus temporadas y episodios (``{temporada: [números]}``).

        El id de Trakt de cada episodio es ``trakt_id * 1000 + temporada * 100 + número``.
        """
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        self.shows[trakt_id] = {"title": title, "year": year, "ids": {"trakt": trakt_id, "slug": slug}}
        self.seasons[trakt_id] = [
            {"number": number, "ids": {"trakt": trakt_id * 100 + number}} for number in seasons
        ]
        for season_number, episode_numbers in seasons.items():
            self.episodes[(trakt_id, season_number)] = [
                {
                    "season": season_number,
                    "number": number,
                    "title": f"Episodio {number}",
                    "ids": {"trakt": trakt_id * 1000 + season_number * 100 + number},
                }
                for number in episode_numbers
            ]

    def create_list(self, name: str, **metadata: Any) -> FakeList:
        """Crea directamente una lista del usuario (para preparar escenarios)."""
        trakt_id = self._new_id()
        fake_list = FakeList(trakt_id, {"name": name, "privacy": "private", **metadata})
        self.lists[trakt_id] = fake_list
        return fake_list

    def list_named(self, name: str) -> FakeList:
        """Devuelve la única lista con ese nombre (falla si hay cero o varias)."""
        matches = [fake_list for fake_list in self.lists.values() if fake_list.metadata["name"] == name]
        assert len(matches) == 1, f"se esperaba una lista '{name}', hay {len(matches)}"
        return matches[0]

    def item_keys(self, fake_list: FakeList) -> list[tuple[str, int]]:
        """Elementos de una lista como ``(tipo, id)`` en su orden actual."""
        return [(item["type"], item["trakt_id"]) for item in sorted(fake_list.items, key=lambda i: i["rank"])]

    def write_requests(self) -> list[tuple[str, str]]:
        """Peticiones que modifican datos (todo lo que no es GET)."""
        return [request for request in self.requests if request[0] != "GET"]

    # --- Transporte ---------------------------------------------------------------------------

    def transport(self) -> httpx.MockTransport:
        """Transporte httpx que responde con esta simulación."""
        # Se llama a self.handle en cada petición (no se guarda el método) para que
        # un test pueda sustituirlo y simular, por ejemplo, una respuesta lenta.
        return httpx.MockTransport(lambda request: self.handle(request))

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Atiende una petición HTTP simulada."""
        path = request.url.path
        method = request.method
        self.requests.append((method, path))
        body = json.loads(request.content) if request.content else None

        if path.startswith("/users/") and not request.headers.get("Authorization"):
            return httpx.Response(401)

        routes = [
            ("POST", r"/oauth/device/code", self._device_code),
            ("POST", r"/oauth/device/token", self._device_token),
            ("POST", r"/oauth/revoke", lambda request, body: httpx.Response(200)),
            ("GET", r"/search/(movie|show)", self._search),
            ("GET", r"/search/(trakt|imdb|tmdb)/([^/]+)", self._search_by_id),
            ("GET", r"/(movies|shows)/([^/]+)", self._get_by_slug),
            ("GET", r"/shows/(\d+)/seasons", self._get_seasons),
            ("GET", r"/shows/(\d+)/seasons/(\d+)", self._get_season_episodes),
            ("GET", r"/users/settings", self._user_settings),
            ("GET", r"/users/me/lists", self._get_lists),
            ("POST", r"/users/me/lists", self._create_list),
            ("GET", r"/users/me/lists/(\d+)", self._get_list),
            ("PUT", r"/users/me/lists/(\d+)", self._update_list),
            ("GET", r"/users/me/lists/(\d+)/items", self._get_items),
            ("POST", r"/users/me/lists/(\d+)/items", self._add_items),
            ("POST", r"/users/me/lists/(\d+)/items/remove", self._remove_items),
            ("POST", r"/users/me/lists/(\d+)/items/reorder", self._reorder_items),
            ("PUT", r"/users/me/lists/(\d+)/items/(\d+)", self._update_item),
        ]
        for route_method, pattern, handler in routes:
            match = re.fullmatch(pattern, path)
            if route_method == method and match:
                return handler(request, body, *match.groups())
        return httpx.Response(404, json={"error": "not found"})

    # --- OAuth -------------------------------------------------------------------------------

    def _device_code(self, request: httpx.Request, body: Any) -> httpx.Response:
        return httpx.Response(
            200,
            json={"device_code": "dev", "user_code": "ABCD1234", "verification_url": "https://trakt.tv/activate", "expires_in": 600, "interval": 1},
        )

    def _device_token(self, request: httpx.Request, body: Any) -> httpx.Response:
        """Pendiente (400) hasta que el test marque ``device_authorized``."""
        if not self.device_authorized:
            return httpx.Response(400)
        return httpx.Response(200, json={"access_token": "test-token", "refresh_token": "r", "created_at": 9_999_999_999, "expires_in": 7_776_000})

    # --- Catálogo -----------------------------------------------------------------------------

    def _search(self, request: httpx.Request, body: Any, media_type: str) -> httpx.Response:
        query = request.url.params.get("query", "").lower()
        catalog = self.movies if media_type == "movie" else self.shows
        results = [{"type": media_type, media_type: media} for media in catalog.values() if query in media["title"].lower()]
        return httpx.Response(200, json=results)

    def _search_by_id(self, request: httpx.Request, body: Any, id_type: str, value: str) -> httpx.Response:
        media_type = request.url.params.get("type", "movie")
        catalog = self.movies if media_type == "movie" else self.shows
        results = [
            {"type": media_type, media_type: media}
            for media in catalog.values()
            if str(media["ids"].get(id_type)) == value
        ]
        return httpx.Response(200, json=results)

    def _get_by_slug(self, request: httpx.Request, body: Any, plural: str, slug: str) -> httpx.Response:
        catalog = self.movies if plural == "movies" else self.shows
        for media in catalog.values():
            if media["ids"]["slug"] == slug:
                return httpx.Response(200, json=media)
        return httpx.Response(404)

    def _get_seasons(self, request: httpx.Request, body: Any, show_id: str) -> httpx.Response:
        if int(show_id) not in self.seasons:
            return httpx.Response(404)
        return httpx.Response(200, json=self.seasons[int(show_id)])

    def _get_season_episodes(self, request: httpx.Request, body: Any, show_id: str, season: str) -> httpx.Response:
        key = (int(show_id), int(season))
        if key not in self.episodes:
            return httpx.Response(404)
        return httpx.Response(200, json=self.episodes[key])

    def _user_settings(self, request: httpx.Request, body: Any) -> httpx.Response:
        # Trakt solo guarda notas de lista en cuentas VIP: se simula con notes_supported.
        return httpx.Response(200, json={"user": {"username": self.username, "vip": self.notes_supported, "vip_ep": False}})

    # --- Listas -------------------------------------------------------------------------------

    def _list_json(self, fake_list: FakeList) -> dict[str, Any]:
        return {
            **fake_list.metadata,
            "ids": {"trakt": fake_list.trakt_id, "slug": f"lista-{fake_list.trakt_id}"},
            "item_count": len(fake_list.items),
        }

    def _get_lists(self, request: httpx.Request, body: Any) -> httpx.Response:
        return httpx.Response(200, json=[self._list_json(fake_list) for fake_list in self.lists.values()])

    def _create_list(self, request: httpx.Request, body: Any) -> httpx.Response:
        fake_list = self.create_list(**body)
        return httpx.Response(201, json=self._list_json(fake_list))

    def _get_list(self, request: httpx.Request, body: Any, list_id: str) -> httpx.Response:
        fake_list = self.lists.get(int(list_id))
        return httpx.Response(200, json=self._list_json(fake_list)) if fake_list else httpx.Response(404)

    def _update_list(self, request: httpx.Request, body: Any, list_id: str) -> httpx.Response:
        fake_list = self.lists[int(list_id)]
        fake_list.metadata.update(body)
        return httpx.Response(200, json=self._list_json(fake_list))

    def _get_items(self, request: httpx.Request, body: Any, list_id: str) -> httpx.Response:
        fake_list = self.lists[int(list_id)]
        return httpx.Response(200, json=[self._item_json(item) for item in sorted(fake_list.items, key=lambda i: i["rank"])])

    def _item_json(self, item: dict[str, Any]) -> dict[str, Any]:
        kind = item["type"]
        data: dict[str, Any] = {"id": item["list_item_id"], "rank": item["rank"], "type": kind, "notes": item["notes"]}
        if kind == "episode":
            show_id = item["trakt_id"] // 1000
            data["show"] = self.shows[show_id]
            season, number = divmod(item["trakt_id"] % 1000, 100)
            data["episode"] = {"season": season, "number": number, "ids": {"trakt": item["trakt_id"]}}
        elif kind == "season":
            show_id = item["trakt_id"] // 100
            data["show"] = self.shows[show_id]
            data["season"] = {"number": item["trakt_id"] % 100, "ids": {"trakt": item["trakt_id"]}}
        else:
            catalog = self.movies if kind == "movie" else self.shows
            data[kind] = catalog.get(item["trakt_id"], {"title": "?", "ids": {"trakt": item["trakt_id"]}})
        return data

    def _add_items(self, request: httpx.Request, body: Any, list_id: str) -> httpx.Response:
        fake_list = self.lists[int(list_id)]
        added = {plural: 0 for plural in PLURAL_TO_KIND}
        for plural, kind in PLURAL_TO_KIND.items():
            for entry in body.get(plural, []):
                trakt_id = entry["ids"]["trakt"]
                if any(item["type"] == kind and item["trakt_id"] == trakt_id for item in fake_list.items):
                    continue  # Trakt no duplica un elemento que ya está en la lista
                fake_list.items.append(
                    {
                        "list_item_id": self._new_id(),
                        "rank": len(fake_list.items) + 1,
                        "type": kind,
                        "trakt_id": trakt_id,
                        "notes": entry.get("notes") if self.notes_supported else None,
                    }
                )
                added[plural] += 1
        return httpx.Response(201, json={"added": added, "not_found": {plural: [] for plural in PLURAL_TO_KIND}})

    def _remove_items(self, request: httpx.Request, body: Any, list_id: str) -> httpx.Response:
        fake_list = self.lists[int(list_id)]
        for plural, kind in PLURAL_TO_KIND.items():
            ids = {entry["ids"]["trakt"] for entry in body.get(plural, [])}
            fake_list.items = [item for item in fake_list.items if not (item["type"] == kind and item["trakt_id"] in ids)]
        self._renumber(fake_list)
        return httpx.Response(200, json={"deleted": {}})

    def _reorder_items(self, request: httpx.Request, body: Any, list_id: str) -> httpx.Response:
        fake_list = self.lists[int(list_id)]
        position = {list_item_id: index for index, list_item_id in enumerate(body["rank"])}
        fake_list.items.sort(key=lambda item: position.get(item["list_item_id"], len(position)))
        self._renumber(fake_list)
        return httpx.Response(200, json={"updated": len(position)})

    def _update_item(self, request: httpx.Request, body: Any, list_id: str, list_item_id: str) -> httpx.Response:
        fake_list = self.lists[int(list_id)]
        for item in fake_list.items:
            if item["list_item_id"] == int(list_item_id):
                if not self.notes_supported:
                    return httpx.Response(420)
                item["notes"] = body.get("notes") or None
                return httpx.Response(204)
        return httpx.Response(404)

    @staticmethod
    def _renumber(fake_list: FakeList) -> None:
        for rank, item in enumerate(fake_list.items, start=1):
            item["rank"] = rank

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id
