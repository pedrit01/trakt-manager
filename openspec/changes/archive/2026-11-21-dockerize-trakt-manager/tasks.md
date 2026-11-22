# Tasks

> Criterio común a todas las tareas de implementación: una tarea solo está terminada si su código es legible y está documentado (docstrings en español en módulos, clases y funciones públicas, type hints en todas las firmas y comentarios que explican el porqué de lo no obvio). Ninguna tarea hace commit ni push.

## 1. Estructura del proyecto

- [x] 1.1 Crear `pyproject.toml` (paquete `trakt_manager` en `src/`, Python ≥3.11, dependencias: httpx, pydantic, pydantic-settings, PyYAML, typer, fastapi, uvicorn; extra `dev`: pytest) con el script `trakt-manager = trakt_manager.cli:app`; verificar que `pip install -e '.[dev]'` funciona y `trakt-manager --help` responde
- [x] 1.2 Crear `src/trakt_manager/__init__.py` y `tests/` con un test trivial; verificar que `pytest` pasa
- [x] 1.3 Crear `.gitignore` (`.env`, `token.json`, `.trakt_token.json`, `__pycache__/`, `.venv/`, `data/`) y verificar con `git check-ignore .env token.json`

## 2. Configuración y cliente de Trakt

- [x] 2.1 Implementar `config.py` (`TRAKT_CLIENT_ID`, `TRAKT_CLIENT_SECRET`, `API_KEY`, `DATA_DIR`, `LISTS_DIR`, `REQUEST_DELAY`) con errores que nombren la variable que falta; verificar con tests de configuración ausente y presente
- [x] 2.2 Implementar `trakt_client.py` con cabeceras de Trakt, `User-Agent` genérico, pausa entre peticiones, reintento ante 429 respetando `Retry-After` y reintentos acotados ante errores de red/5xx; verificar con tests sobre `httpx.MockTransport` (429→éxito, 503×3→fallo, cabeceras correctas)

## 3. Autenticación (trakt-auth)

- [x] 3.1 Implementar `TokenStore` en `DATA_DIR/token.json` (permisos 600, lectura y escritura, borrado) y verificar con tests en un directorio temporal, incluido el permiso del fichero
- [x] 3.2 Implementar el device flow (código, sondeo con intervalo, 400 pendiente, 429 más lento, caducidad) y verificar con tests simulados de éxito, caducidad y 429
- [x] 3.3 Implementar la renovación (preventiva por caducidad y ante un 401, un solo intento, guardado del token nuevo, error claro si se rechaza) y verificar con tests de 401→refresh→reintento y de refresh rechazado
- [x] 3.4 Implementar estado (usuario vía `GET /users/settings`) y cierre de sesión (`POST /oauth/revoke` + borrado) y verificar con tests

## 4. Definiciones de listas (list-definitions)

- [x] 4.1 Implementar en `definitions.py` los modelos pydantic (metadatos con valores por defecto, `trakt_list_id` opcional, entradas `movie|show|season|episodes`, `query`/`year`/`ids`, `title`, `note`, `block`, `extra`) con la validación de episodios y de identificación; verificar con tests de cada escenario del spec
- [x] 4.2 Implementar la carga desde YAML/JSON (rechazo de otras extensiones) y un informe de errores con la posición y el campo de cada uno, todos a la vez; verificar con un test YAML≡JSON y un test con dos errores
- [x] 4.3 Migrar `ROADMAP` a `lists/doomsday.yaml`, fijando `ids` para los títulos ambiguos (X-Men, X2, Loki, Black Widow, The Marvels); verificar con un test que compara contra los datos del script original (17 principales + 4 extras, mismos episodios, bloques y orden)

## 5. Resolución y sincronización (list-sync)

- [x] 5.1 Implementar `resolver.py` (ids explícitos primero, búsqueda con preferencia por año exacto, después ±1 y después el primer resultado, episodios concretos, temporada y serie completa) con un `ResolutionReport` de resueltos y no encontrados; verificar con tests simulados de cada regla y de un episodio inexistente
- [x] 5.2 Implementar el plan de sync en `sync.py` (búsqueda de la lista por id o nombre, comparación por `(type, trakt_id)`, altas, bajas, cambios de nota, orden final y metadatos) como función pura; verificar con tests de lista nueva, repetición sin cambios, entrada eliminada y cinco películas con la misma nota (regresión)
- [x] 5.3 Implementar la aplicación del plan (crear o `PUT` de la lista con `sort_by: rank`, `items/remove`, `items` en lotes, relectura y `items/reorder`) con dry-run que no hace ninguna escritura; verificar con tests simulados que comprueban las peticiones enviadas y que el dry-run no envía ninguna petición POST, PUT o DELETE
- [x] 5.4 Implementar la consulta de listas del usuario y de los elementos de una lista; verificar con tests simulados

- [x] 5.5 Omitir las notas en cuentas sin VIP (detectado en la prueba real: Trakt las descarta y el plan proponía 36 cambios de nota en cada sincronización); verificar con tests de cuenta sin VIP (un aviso, sin notas, segunda sincronización sin cambios ni escrituras) y de cuenta VIP

## 6. CLI (cli)

- [x] 6.1 Implementar `auth login|status|logout`, `validate`, `sync [--dry-run] [--include-extras]`, `lists`, `show` y `serve` con Typer, `--json` en los comandos de resultado y códigos de salida según el spec; verificar con tests de `typer.testing.CliRunner` (validación OK y KO, dry-run, sync sin sesión, salida `--json` parseable)
- [x] 6.2 Documentar los comandos del CLI en `README.md` con ejemplos y verificar que `trakt-manager sync lists/doomsday.yaml --dry-run` funciona como está escrito (con un `TRAKT_CLIENT_ID` real)

## 7. API HTTP (web-api)

- [x] 7.1 Implementar `api.py` con FastAPI: dependencia `X-API-Key` (`compare_digest`), arranque bloqueado si falta `API_KEY` y `GET /health` sin secretos; verificar con tests de 401, arranque sin clave y salud
- [x] 7.2 Implementar `POST /auth/device` (hilo de sondeo, un solo flujo activo), `GET /auth/status` y `DELETE /auth`; verificar con tests simulados de inicio, estado pendiente y autorizado
- [x] 7.3 Implementar `GET /definitions`, `GET /definitions/{nombre}`, `POST /validate` (422 con errores), `POST /sync` (cuerpo JSON/YAML) y `POST /definitions/{nombre}/sync` con `dry_run`/`include_extras`, 409 sin sesión y lock por lista (409 si hay otra sync en curso); verificar con tests de `TestClient` de cada escenario del spec y comprobar que la respuesta coincide con la salida `--json` del CLI
- [x] 7.4 Implementar `GET /lists` y `GET /lists/{id}` y verificar con tests
- [x] 7.5 Documentar la API (autenticación, rutas, `/docs`) en `README.md` y verificar los ejemplos `curl` contra el servicio en local

## 8. Contenedor (container-runtime)

- [x] 8.1 Crear un `Dockerfile` multi-stage (`python:3.12-slim`, usuario `app` no root, `DATA_DIR=/data` propiedad de `app`, `ENTRYPOINT ["trakt-manager"]`, `CMD ["serve"]`, `HEALTHCHECK` contra `/health`) y un `.dockerignore`; verificar que `docker build` funciona y que la imagen no contiene `.env` (`docker run --rm --entrypoint ls <img> -a /app`) y que `whoami` devuelve `app`
- [x] 8.2 Crear `docker-compose.yml` (servicio `trakt-manager`, `env_file`, volumen `trakt-data:/data`, `./lists:/app/lists:ro`, puerto `${API_BIND:-127.0.0.1}:${API_PORT:-8000}:8000`) y `.env.example`; verificar que `docker compose up -d` deja el servicio `healthy` y que `docker compose run --rm trakt-manager validate lists/doomsday.yaml` devuelve 0
- [x] 8.3 Documentar en `README.md` la puesta en marcha con Docker (crear la app en Trakt, `.env`, `auth login` dentro del contenedor, acceso remoto con `API_BIND`/proxy inverso) y verificar los pasos desde cero

## 9. Integración y retirada del script

- [x] 9.1 Prueba de extremo a extremo en Docker con una cuenta real: `auth login`, `sync lists/doomsday.yaml --dry-run`, `sync` real, repetir `sync` (0 cambios) y recrear el contenedor (la sesión sigue activa); verificar en trakt.tv el orden y que no hay duplicados
- [x] 9.2 Eliminar `create-tracklist.py` y verificar que `pytest` y `docker compose run --rm trakt-manager validate lists/doomsday.yaml` siguen pasando

## Workflow follow-up

- Archivar el cambio (`/openspec-archive-change`) una vez revisado e implementado.
