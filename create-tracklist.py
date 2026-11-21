#!/usr/bin/env python3
"""
Crea automáticamente tu lista numerada y cronológica hacia Vengadores: Doomsday en Trakt.
Añade tanto las películas completas como los CAPÍTULOS EXACTOS de cada serie (sin relleno).

Sin dependencias externas (solo librería estándar de Python 3.8+).

Requisitos previos (2 minutos):
1. Entra en https://trakt.tv/oauth/applications -> "New Application"
2. Pon un nombre cualquiera (ej. "Doomsday Tracker") y en Redirect URI: urn:ietf:wg:oauth:2.0:oob
3. Copia tu Client ID y Client Secret.

Uso:
  export TRAKT_CLIENT_ID="tu_client_id"
  export TRAKT_CLIENT_SECRET="tu_client_secret"

  # 1) Probar búsqueda sin tocar tu cuenta (recomendado primero):
  python3 crear_lista_trakt_doomsday.py --dry-run

  # 2) Crear la lista en Trakt (solo núcleo principal):
  python3 crear_lista_trakt_doomsday.py

  # 3) Crear la lista incluyendo también Endgame Encore, X-Men, X2 y Viuda Negra:
  python3 crear_lista_trakt_doomsday.py --include-extras
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

API_BASE = "https://api.trakt.tv"
TOKEN_FILE = Path(".trakt_token.json")

ROADMAP = json.loads(r"""
[
    {
        "order": 1,
        "title": "Bruja Escarlata y Visión",
        "query": "WandaVision",
        "year": 2021,
        "kind": "episode_list",
        "season": 1,
        "episodes": [
            4,
            7,
            8,
            9
        ],
        "block": "1. Inicio del Multiverso",
        "is_extra": false,
        "note": "1. Inicio del Multiverso | Ep. 4, 7, 8 y 9 (si vas justo: solo 8 y 9)"
    },
    {
        "order": 2,
        "title": "Shang-Chi y la leyenda de los Diez Anillos",
        "query": "Shang-Chi and the Legend of the Ten Rings",
        "year": 2021,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "1. Inicio del Multiverso",
        "is_extra": false,
        "note": "1. Inicio del Multiverso | Película completa"
    },
    {
        "order": 3,
        "title": "Falcon y el Soldado de Invierno",
        "query": "The Falcon and the Winter Soldier",
        "year": 2021,
        "kind": "episode_list",
        "season": 1,
        "episodes": [
            1,
            4,
            5,
            6
        ],
        "block": "1. Inicio del Multiverso",
        "is_extra": false,
        "note": "1. Inicio del Multiverso | Ep. 1, 4, 5 y 6"
    },
    {
        "order": 4,
        "title": "Spider-Man: No Way Home",
        "query": "Spider-Man: No Way Home",
        "year": 2021,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "1. Inicio del Multiverso",
        "is_extra": false,
        "note": "1. Inicio del Multiverso | Película completa"
    },
    {
        "order": 5,
        "title": "Doctor Strange en el Multiverso de la Locura",
        "query": "Doctor Strange in the Multiverse of Madness",
        "year": 2022,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "1. Inicio del Multiverso",
        "is_extra": false,
        "note": "1. Inicio del Multiverso | Película completa"
    },
    {
        "order": 6,
        "title": "Black Panther: Wakanda Forever",
        "query": "Black Panther: Wakanda Forever",
        "year": 2022,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "1. Inicio del Multiverso",
        "is_extra": false,
        "note": "1. Inicio del Multiverso | Película completa"
    },
    {
        "order": 7,
        "title": "Ms. Marvel",
        "query": "Ms. Marvel",
        "year": 2022,
        "kind": "episode_list",
        "season": 1,
        "episodes": [
            1,
            6
        ],
        "block": "1. Inicio del Multiverso",
        "is_extra": false,
        "note": "1. Inicio del Multiverso | Ep. 1 y 6 (si ves The Marvels)"
    },
    {
        "order": 8,
        "title": "Ant-Man y la Avispa: Quantumania",
        "query": "Ant-Man and the Wasp: Quantumania",
        "year": 2023,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "2. La grieta y la AVT",
        "is_extra": false,
        "note": "2. La grieta y la AVT | Película completa"
    },
    {
        "order": 9,
        "title": "The Marvels",
        "query": "The Marvels",
        "year": 2023,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "2. La grieta y la AVT",
        "is_extra": false,
        "note": "2. La grieta y la AVT | Película completa (o acto final + postcréditos)"
    },
    {
        "order": 10,
        "title": "Loki – Temporada 2",
        "query": "Loki",
        "year": 2021,
        "kind": "episode_list",
        "season": 2,
        "episodes": [
            1,
            4,
            5,
            6
        ],
        "block": "2. La grieta y la AVT",
        "is_extra": false,
        "note": "2. La grieta y la AVT | T2: Ep. 1, 4, 5 y 6"
    },
    {
        "order": 11,
        "title": "Deadpool y Lobezno",
        "query": "Deadpool & Wolverine",
        "year": 2024,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "2. La grieta y la AVT",
        "is_extra": false,
        "note": "2. La grieta y la AVT | Película completa"
    },
    {
        "order": 12,
        "title": "Agatha, ¿quién si no?",
        "query": "Agatha All Along",
        "year": 2024,
        "kind": "episode_list",
        "season": 1,
        "episodes": [
            6,
            8,
            9
        ],
        "block": "2. La grieta y la AVT",
        "is_extra": false,
        "note": "2. La grieta y la AVT | Ep. 6, 8 y 9"
    },
    {
        "order": 13,
        "title": "Capitán América: Brave New World",
        "query": "Captain America: Brave New World",
        "year": 2025,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "3. Recta final hacia Doomsday",
        "is_extra": false,
        "note": "3. Recta final hacia Doomsday | Película completa"
    },
    {
        "order": 14,
        "title": "Thunderbolts*",
        "query": "Thunderbolts*",
        "year": 2025,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "3. Recta final hacia Doomsday",
        "is_extra": false,
        "note": "3. Recta final hacia Doomsday | Película completa"
    },
    {
        "order": 15,
        "title": "Los 4 Fantásticos: Primeros pasos",
        "query": "The Fantastic Four: First Steps",
        "year": 2025,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "3. Recta final hacia Doomsday",
        "is_extra": false,
        "note": "3. Recta final hacia Doomsday | Película completa"
    },
    {
        "order": 16,
        "title": "Spider-Man: Brand New Day",
        "query": "Spider-Man: Brand New Day",
        "year": 2026,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "3. Recta final hacia Doomsday",
        "is_extra": false,
        "note": "3. Recta final hacia Doomsday | Película completa"
    },
    {
        "order": 17,
        "title": "VisionQuest",
        "query": "VisionQuest",
        "year": 2026,
        "kind": "episode_list",
        "season": 1,
        "episodes": [
            1,
            2,
            7,
            8
        ],
        "block": "3. Recta final hacia Doomsday",
        "is_extra": false,
        "note": "3. Recta final hacia Doomsday | Ep. 1, 2, 7 y 8"
    },
    {
        "order": 18,
        "title": "Vengadores: Endgame Encore (escenas nuevas)",
        "query": "Avengers: Endgame",
        "year": 2019,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "4. Extras antes del cine",
        "is_extra": true,
        "note": "4. Extras antes del cine | Solo final extendido + créditos (5-6 min). Ver al final."
    },
    {
        "order": 19,
        "title": "X-Men (2000)",
        "query": "X-Men",
        "year": 2000,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "4. Extras antes del cine",
        "is_extra": true,
        "note": "4. Extras antes del cine | Película completa (repaso clásico)"
    },
    {
        "order": 20,
        "title": "X2 (2003)",
        "query": "X2",
        "year": 2003,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "4. Extras antes del cine",
        "is_extra": true,
        "note": "4. Extras antes del cine | Película completa (repaso clásico)"
    },
    {
        "order": 21,
        "title": "Viuda Negra",
        "query": "Black Widow",
        "year": 2021,
        "kind": "movie",
        "season": null,
        "episodes": [],
        "block": "4. Extras antes del cine",
        "is_extra": true,
        "note": "4. Extras antes del cine | Solo si no la viste en su día"
    }
]
""")


def trakt_request(
    method: str,
    path: str,
    client_id: str,
    token: Optional[str] = None,
    payload: Optional[dict] = None,
):
    url = f"{API_BASE}{path}"
    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": client_id,
        "User-Agent": "DoomsdayRoadmapScript/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return e.code, err_body


def authenticate_device(client_id: str, client_secret: str) -> str:
    """Autenticación OAuth2 Device Flow de Trakt (sin servidor web local)."""
    if TOKEN_FILE.exists():
        saved = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        if saved.get("access_token"):
            print("[OK] Usando token guardado en .trakt_token.json")
            return saved["access_token"]

    status, data = trakt_request("POST", "/oauth/device/code", client_id, payload={"client_id": client_id})
    if status != 200:
        sys.exit(f"[ERROR] No se pudo iniciar OAuth en Trakt ({status}): {data}")

    print("\n=== AUTORIZACIÓN EN TRAKT ===")
    print(f"1. Abre en tu navegador: {data['verification_url']}")
    print(f"2. Introduce este código: {data['user_code']}")
    print("Esperando confirmación...\n")

    device_code = data["device_code"]
    interval = int(data.get("interval", 5))
    expires_at = time.time() + int(data.get("expires_in", 600))

    while time.time() < expires_at:
        time.sleep(interval)
        st, token_data = trakt_request(
            "POST",
            "/oauth/device/token",
            client_id,
            payload={
                "code": device_code,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        if st == 200:
            TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
            print("[OK] Autorizado y token guardado en .trakt_token.json\n")
            return token_data["access_token"]
        elif st == 400:
            continue
        elif st == 429:
            interval += 2
            continue
        else:
            sys.exit(f"[ERROR] Fallo en autorización ({st}): {token_data}")

    sys.exit("[ERROR] El código expiró antes de autorizarlo.")


def search_trakt(kind: str, query: str, year: int, client_id: str):
    """Busca película o serie en Trakt priorizando coincidencia exacta por año."""
    encoded = urllib.parse.quote(query)
    status, results = trakt_request("GET", f"/search/{kind}?query={encoded}&limit=8", client_id)
    if status != 200 or not results:
        return None

    for r in results:
        obj = r.get(kind, {})
        if obj.get("year") == year:
            return obj

    for r in results:
        obj = r.get(kind, {})
        if obj.get("year") and abs(obj["year"] - year) <= 1:
            return obj

    return results[0].get(kind)


def resolve_items(client_id: str, include_extras: bool):
    """Resuelve los IDs de Trakt de cada película y episodio exacto."""
    movies_payload = []
    episodes_payload = []
    unresolved = []

    selected = [it for it in ROADMAP if include_extras or not it["is_extra"]]

    print(f"Buscando {len(selected)} entradas en la base de datos de Trakt...\n")

    for it in selected:
        if it["kind"] == "movie":
            match = search_trakt("movie", it["query"], it["year"], client_id)
            if not match:
                unresolved.append(f"#{it['order']} {it['title']} ({it['year']})")
                print(f"  [NO ENCONTRADA] #{it['order']:02d} {it['title']}")
                continue

            trakt_id = match["ids"]["trakt"]
            movies_payload.append({
                "ids": {"trakt": trakt_id},
                "notes": it["note"]
            })
            print(f"  [PELI]  #{it['order']:02d} {match['title']} ({match.get('year')}) -> trakt:{trakt_id}")

        else:
            show = search_trakt("show", it["query"], it["year"], client_id)
            if not show:
                unresolved.append(f"#{it['order']} {it['title']} (Serie)")
                print(f"  [NO ENCONTRADA] #{it['order']:02d} {it['title']}")
                continue

            slug = show["ids"]["slug"]
            season = it["season"]
            found_eps = []

            for ep_num in it["episodes"]:
                st, ep_data = trakt_request("GET", f"/shows/{slug}/seasons/{season}/episodes/{ep_num}", client_id)
                if st == 200 and ep_data and ep_data.get("ids", {}).get("trakt"):
                    episodes_payload.append({
                        "ids": {"trakt": ep_data["ids"]["trakt"]},
                        "notes": f"{it['title']} S{season:02d}E{ep_num:02d} | {it['block']}"
                    })
                    found_eps.append(ep_num)
                else:
                    unresolved.append(f"#{it['order']} {it['title']} S{season:02d}E{ep_num:02d}")
                time.sleep(0.15)

            print(f"  [SERIE] #{it['order']:02d} {show['title']} (S{season:02d}) -> Episodios añadidos: {found_eps}")

        time.sleep(0.15)

    return movies_payload, episodes_payload, unresolved


def main():
    parser = argparse.ArgumentParser(description="Crea la lista cronológica hacia Avengers: Doomsday en Trakt.")
    parser.add_argument("--client-id", default=os.getenv("TRAKT_CLIENT_ID"), help="Trakt Client ID")
    parser.add_argument("--client-secret", default=os.getenv("TRAKT_CLIENT_SECRET"), help="Trakt Client Secret")
    parser.add_argument("--list-name", default="Ruta Cronológica hacia Vengadores: Doomsday", help="Nombre de la lista")
    parser.add_argument("--privacy", choices=["private", "friends", "public"], default="private", help="Privacidad")
    parser.add_argument("--include-extras", action="store_true", help="Incluir Endgame Encore, X-Men, X2 y Viuda Negra")
    parser.add_argument("--dry-run", action="store_true", help="Solo comprueba qué encuentra en Trakt sin crear nada")
    args = parser.parse_args()

    if not args.client_id:
        sys.exit("[ERROR] Falta TRAKT_CLIENT_ID (pásalo por variable de entorno o --client-id).")

    movies, episodes, unresolved = resolve_items(args.client_id, args.include_extras)

    print("\n--- RESUMEN DE RESOLUCIÓN ---")
    print(f"Películas listas: {len(movies)}")
    print(f"Episodios exactos listos: {len(episodes)}")
    if unresolved:
        print("Pendientes / no encontrados en Trakt aún:")
        for u in unresolved:
            print(f"  - {u}")

    if args.dry_run:
        print("\n[DRY-RUN] Fin de la prueba. No se ha modificado tu cuenta de Trakt.")
        return

    if not args.client_secret:
        sys.exit("[ERROR] Falta TRAKT_CLIENT_SECRET para autenticar y crear la lista.")

    token = authenticate_device(args.client_id, args.client_secret)

    # 1. Crear lista numerada en orden manual (rank asc)
    st, created_list = trakt_request(
        "POST",
        "/users/me/lists",
        args.client_id,
        token=token,
        payload={
            "name": args.list_name,
            "description": "Orden cronológico UCM sin relleno (películas + episodios exactos) rumbo a Avengers: Doomsday.",
            "privacy": args.privacy,
            "display_numbers": True,
            "allow_comments": False,
            "sort_by": "rank",
            "sort_how": "asc",
        },
    )
    if st not in (200, 201):
        sys.exit(f"[ERROR] No se pudo crear la lista ({st}): {created_list}")

    list_id = created_list["ids"]["trakt"]
    print(f"[OK] Lista creada: {created_list['name']} (id: {list_id})")

    # 2. Insertar en orden cronológico intercalado (peli -> episodios -> peli)
    print("Insertando elementos en orden cronológico exacto...")
    movie_map = {m["notes"]: m for m in movies}
    ep_groups = {}
    for ep in episodes:
        prefix = ep["notes"].split(" | ")[0]
        ep_groups.setdefault(prefix, []).append(ep)

    selected = [it for it in ROADMAP if args.include_extras or not it["is_extra"]]
    added_movies = 0
    added_episodes = 0

    for it in selected:
        if it["kind"] == "movie":
            m = movie_map.get(it["note"])
            if not m:
                continue
            st, res = trakt_request("POST", f"/users/me/lists/{list_id}/items", args.client_id, token=token, payload={"movies": [m]})
            if st in (200, 201):
                added_movies += res.get("added", {}).get("movies", 0)
        else:
            batch = []
            for ep_num in it["episodes"]:
                key = f"{it['title']} S{it['season']:02d}E{ep_num:02d}"
                batch.extend(ep_groups.get(key, []))
            if not batch:
                continue
            st, res = trakt_request("POST", f"/users/me/lists/{list_id}/items", args.client_id, token=token, payload={"episodes": batch})
            if st in (200, 201):
                added_episodes += res.get("added", {}).get("episodes", 0)
        time.sleep(0.25)

    print(f"\n[COMPLETADO] Lista poblada en Trakt: {added_movies} películas + {added_episodes} episodios exactos.")
    print("Abre la app de Trakt en el móvil -> Lists -> ¡a tachar!")


if __name__ == "__main__":
    main()
