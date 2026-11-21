# Design

## Context

El repositorio solo contiene `create-tracklist.py` (≈500 líneas, solo librería estándar). Ese script ya resuelve los problemas difíciles con la API de Trakt y conviene reaprovecharlos: device flow, búsqueda por año con tolerancia ±1, resolución de episodios con `/shows/{slug}/seasons/{s}/episodes/{e}` y creación de la lista con `sort_by: rank`. También tiene limitaciones que este cambio corrige:

- `ROADMAP` está incrustado como JSON dentro del código.
- El token se guarda en `./.trakt_token.json`, relativo al directorio actual, y nunca se renueva.
- Las películas se indexan por `note` (`movie_map = {m["notes"]: m ...}`). Como varias películas comparten nota, el diccionario se queda solo con la última de cada grupo: se añaden repetidas y se pierden otras.
- Si se ejecuta dos veces, crea una segunda lista.
- No reintenta ante errores ni respeta `Retry-After`.

Ver proposal.md para la motivación y los specs para el comportamiento exigido.

## Goals / Non-Goals

**Goals:**
- Un único núcleo de dominio que usen el CLI y la API, para que no se desincronicen.
- Un `sync` idempotente: una definición equivale al estado deseado de una lista.
- Que funcione con `docker compose up` más un `.env`, sin instalar Python en el anfitrión.

**Non-Goals:**
- Interfaz web gráfica (solo API JSON; la documentación interactiva de OpenAPI en `/docs` basta por ahora).
- Varios usuarios de Trakt o varias cuentas por instancia: una instancia corresponde a un token.
- Otras funciones de Trakt (historial, watchlist, valoraciones). La estructura debe permitirlas más adelante, pero no se implementan.
- TLS dentro del contenedor: para exponerlo fuera de la red local se usará un proxy inverso.

## Decisions

### Estructura del paquete
```
src/trakt_manager/
  config.py       # Settings desde el entorno (pydantic-settings)
  trakt_client.py # Cliente HTTP: cabeceras, reintentos, 429, renovación del token
  auth.py         # Device flow, TokenStore (DATA_DIR/token.json, permisos 600)
  definitions.py  # Modelos pydantic + carga YAML/JSON + validación
  resolver.py     # Entrada -> elementos de Trakt + informe
  sync.py         # Plan (altas/bajas/reorden/metadatos) y aplicación
  cli.py          # Typer
  api.py          # FastAPI
lists/doomsday.yaml
tests/
```
El CLI y la API son capas finas sobre `resolver` y `sync`, y ambos serializan los mismos modelos de resultado (`ResolutionReport` y `SyncPlan`/`SyncResult`). Así se cumple que la API devuelva lo mismo que `--json`.

### Librerías
- **httpx** (síncrono) en lugar de urllib: timeouts, `MockTransport` para los tests y un cliente reutilizable. Para el volumen de peticiones de esta herramienta no hace falta asincronía.
- **pydantic v2** para las definiciones: los errores ya incluyen la ruta (`entries.3.season`), que es lo que piden los specs.
- **Typer** para el CLI. Click puro sería igual de válido, pero Typer se escribe en menos código con anotaciones de tipo.
- **FastAPI + uvicorn** para la API: valida con los mismos modelos pydantic y genera OpenAPI. Se descarta Flask porque duplicaría la validación.
- **PyYAML** (`safe_load`). Un JSON se lee con el mismo cargador, salvo para dar errores más claros.

### Formato de la definición
```yaml
name: Ruta Cronológica hacia Vengadores: Doomsday
description: Orden cronológico UCM sin relleno…
privacy: private           # private | friends | public
display_numbers: true
allow_comments: false
entries:
  - type: episodes          # movie | show | season | episodes
    title: Bruja Escarlata y Visión
    query: WandaVision
    year: 2021
    season: 1
    episodes: [4, 7, 8, 9]
    block: "1. Inicio del Multiverso"
    note: "Ep. 4, 7, 8 y 9 (si vas justo: solo 8 y 9)"
  - type: movie
    query: Shang-Chi and the Legend of the Ten Rings
    year: 2021
    ids: { tmdb: 566525 }   # opcional; si está, se omite la búsqueda
    block: "1. Inicio del Multiverso"
    extra: false
```
La nota que se envía a Trakt es `"{block} | {note}"`, igual que en el script. En los episodios es `"{title} SxxEyy | {block}"`. `order` deja de existir: el orden es la posición en `entries`.

### Algoritmo de sync
1. Validar y filtrar los extras.
2. Resolver cada entrada a una lista ordenada de `DesiredItem(type, trakt_id, notes)`. La clave de identidad es `(type, trakt_id)`, nunca la nota (así se corrige el fallo).
3. Buscar la lista del usuario por nombre exacto en `GET /users/me/lists`. Si no existe, se crea en el plan.
4. Comparar con `GET /users/me/lists/{id}/items` para obtener altas, bajas, cambios de nota y el nuevo orden.
5. Si es dry-run, devolver el plan. Si no:
   - actualizar metadatos con `PUT /users/me/lists/{id}`;
   - quitar sobrantes con `POST …/items/remove`;
   - añadir los que faltan con `POST …/items` en lotes, en orden;
   - releer los elementos para obtener los `list_item_id`;
   - aplicar el orden final con `POST …/items/reorder` (`rank: [ids…]`).

Reordenar al final, en vez de insertar elemento a elemento como hace el script, garantiza el orden también en una lista ya existente y reduce las peticiones.

### Cliente de Trakt
- Cabeceras `trakt-api-version: 2` y `trakt-api-key`, y un `User-Agent` genérico (`trakt-manager/<versión>`).
- Ante un 429, espera `Retry-After` (2 s si no viene) y reintenta hasta 5 veces. Ante errores de red o 5xx, hasta 3 reintentos con espera exponencial.
- Ante un 401 con token, intenta una sola renovación (`POST /oauth/token` con `grant_type=refresh_token`), guarda el token y repite la petición. También renueva de forma preventiva si `created_at + expires_in` ha pasado.
- Una pausa mínima entre peticiones (≈0,2 s, configurable), como hacía el script.

### Device flow en la API
`POST /auth/device` pide el código y lanza un hilo de sondeo con un único flujo activo a la vez. Si ya hay uno, devuelve el mismo código mientras no caduque. `GET /auth/status` informa de `pending` / `authorized` / `expired` / `none`. En el CLI, `auth login` sondea en primer plano.

### Concurrencia en la API
uvicorn arranca con un solo worker. Un `threading.Lock` por nombre de lista protege los sync reales. Si el lock no está libre, la API responde 409 sin esperar. Con un único proceso no se necesita un bloqueo distribuido.

### Contenedor
- Base `python:3.12-slim`, multi-stage (se construye la wheel y se instala sin herramientas de compilación) y usuario `app` (UID 1000).
- `ENTRYPOINT ["trakt-manager"]`, `CMD ["serve"]`. `serve` es un subcomando interno que lanza uvicorn. Así, `docker compose run --rm trakt-manager <comando>` ejecuta el CLI con la misma imagen.
- `HEALTHCHECK` con `python -c` contra `http://127.0.0.1:8000/health` (sin instalar curl).
- Compose:
  - un servicio `trakt-manager` con `env_file: .env`;
  - volumen nombrado `trakt-data:/data` (`DATA_DIR=/data`) y bind mount `./lists:/app/lists:ro` (`LISTS_DIR=/app/lists`);
  - puerto `${API_BIND:-127.0.0.1}:${API_PORT:-8000}:8000`.
- `.dockerignore` excluye `.env`, `*.json` de tokens, `.git` y `openspec/`.

### Puerto publicado solo en localhost por defecto
Por defecto compose publica en `127.0.0.1`. Para el acceso remoto hay que poner `API_BIND=0.0.0.0` (o usar un proxy inverso) de forma consciente. Así no queda expuesto por accidente un servicio que escribe en la cuenta de Trakt. La comparación de `X-API-Key` se hace con `secrets.compare_digest`.

### Tests
pytest con `httpx.MockTransport` para simular Trakt (búsqueda, episodios, listas, 429, 401→refresh) y `fastapi.testclient` para la API. No se llama a Trakt real en los tests. Habrá un test de regresión específico para el fallo de películas con la misma nota.

## Risks / Trade-offs

- [Las notas por elemento de lista pueden ser una función solo VIP en Trakt y no guardarse en cuentas gratuitas] → El sync no falla si Trakt ignora la nota. Si la nota guardada no coincide, no se reintenta en bucle: se avisa una vez en el informe.
- [Si se renombra la lista en Trakt a mano, el siguiente sync crea otra] → Se documenta. Se admite `trakt_list_id` opcional en la definición para fijar la lista.
- [La búsqueda por texto puede elegir un título equivocado (p. ej. "X-Men" o "Loki")] → El informe muestra título, año e id de cada resolución para revisarla en el dry-run, y la definición admite `ids` explícitos. En la migración se fijan ids para los títulos ambiguos.
- [Un token en un volumen accesible] → El fichero tiene permisos 600 y pertenece al usuario `app`. No se expone por la API ni en los registros.
- [Un solo worker limita el rendimiento] → Es aceptable para uso personal. El cuello de botella real es la limitación de peticiones de Trakt.
- [Dejar de usar solo la librería estándar] → Lo asume la imagen Docker. Para ejecutarlo fuera de Docker basta `pip install .`.

## Migration Plan

1. Convertir `ROADMAP` a `lists/doomsday.yaml` y comprobar con un test que coincide con el original (17 + 4 entradas, mismos episodios y notas).
2. Comprobar en dry-run que la resolución coincide con la del script original.
3. Retirar `create-tracklist.py` y documentar su equivalente en el README.
4. Un token antiguo `.trakt_token.json` se puede copiar a `DATA_DIR/token.json`, ya que el formato es el mismo. Si no, basta con volver a ejecutar `auth login`.

Vuelta atrás: el script original queda en el historial de git y no depende de nada nuevo.

## Open Questions

- Si las notas por elemento son VIP en la cuenta del usuario, se decidirá más adelante si se usa la descripción de la lista para documentar los bloques. No cambia los specs ni las tareas.
