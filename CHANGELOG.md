# Changelog

Todos los cambios relevantes de este proyecto se documentan en este fichero.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [Unreleased]

## [0.1.0] - 2026-11-22

Primera versión publicada. Sustituye al script suelto `create-tracklist.py` por un gestor de listas de Trakt reutilizable, empaquetado en una sola imagen Docker.

### Añadido

- **Definiciones de listas en YAML o JSON**: metadatos de la lista (nombre, descripción, privacidad, numeración, comentarios, `trakt_list_id` opcional) y entradas ordenadas de tipo `movie`, `show`, `season` o `episodes`, con bloques, notas y entradas `extra`.
- **Validación sin contactar con Trakt**, con todos los errores a la vez, localizados por entrada y campo, y mensajes en español.
- **Resolución de títulos** contra Trakt: los `ids` explícitos (`trakt`, `slug`, `imdb`, `tmdb`) tienen prioridad; si no, se busca y se elige el año exacto, luego ±1 y, por último, el primer resultado. Informe de lo encontrado y lo no encontrado.
- **Sincronización idempotente**: crea la lista o, si ya existe, actualiza metadatos, quita lo que sobra, añade lo que falta, actualiza notas y reordena. Repetirla sin cambios no toca nada. Modo `--dry-run` (también sin sesión) y opción `--include-extras`.
- **Autenticación con Trakt por device flow**, con token persistido en `DATA_DIR/token.json` (permisos 600), renovación automática con el `refresh_token` y cierre de sesión con revocación.
- **CLI `trakt-manager`**: `auth login|status|logout`, `validate`, `sync`, `lists`, `show` y `serve`. Salida `--json` y códigos de salida `0`/`1`.
- **API HTTP** (FastAPI) protegida con `X-API-Key`: salud, autenticación remota, definiciones (listar, ver, descargar, guardar, borrar), validación, previsualización, sincronización y consulta de listas. Una sola sincronización a la vez por lista (`409`) y `502` cuando falla Trakt. Documentación interactiva en `/docs`.
- **Interfaz web** servida en `/`, sin dependencias ni paso de compilación: sesión de Trakt, gestión de definiciones (pegar, subir, validar, guardar, descargar, borrar), previsualización con confirmación antes de sincronizar, consulta de listas y ajustes.
- **Configuración en tiempo de ejecución**: asistente inicial protegido con un código de un solo uso que aparece en los registros del contenedor; credenciales guardadas en `DATA_DIR/settings.json`; el entorno (incluido `.env`) siempre tiene prioridad; los cambios se aplican sin reiniciar y la clave de API se puede regenerar.
- **Catálogo de definiciones** que combina las incluidas en la imagen (`LISTS_DIR`) con las guardadas desde la GUI (`DATA_DIR/lists`).
- **Imagen Docker** única para API y CLI, ejecutada sin privilegios, con `docker-compose.yml` (servicio, CLI y tests) y volumen persistente en `/data`.
- **Publicación automática** en `ghcr.io/pedrit01/trakt-manager` para `linux/amd64` y `linux/arm64` mediante GitHub Actions, solo si pasan los tests: `latest` y `sha-<commit>` en `main`, `X.Y.Z` y `X.Y` en etiquetas `vX.Y.Z`.
- **Cliente HTTP de Trakt** con espaciado de peticiones, respeto de `Retry-After` en los `429`, reintentos ante errores `5xx` o de red y una renovación del token ante un `401`.
- Definición de ejemplo `lists/doomsday.yaml` (ruta cronológica hacia *Vengadores: Doomsday*), migrada del script original.
- Batería de tests con un Trakt simulado en memoria y un servidor de demostración (`tests/demo_server.py`) para probar la GUI sin credenciales.

### Cambiado

- El **Client Secret de Trakt es opcional**: las aplicaciones nuevas de Trakt ya no lo reciben. Si está configurado se sigue enviando; si Trakt lo exige, el error lo indica claramente.
- La API **arranca en modo configuración** cuando faltan `TRAKT_CLIENT_ID` o `API_KEY`, en lugar de negarse a arrancar. En ese modo solo responden `/health`, la GUI y el asistente; el resto de rutas devuelven `503`.

### Corregido

- Varias películas con la misma nota ya no se pisan entre sí: la comparación se hace por tipo e id de Trakt, nunca por nota (fallo heredado del script original).
- Con cuentas de Trakt sin VIP, que descartan en silencio las notas por elemento, la sincronización ya no propone actualizar notas en cada ejecución: las omite y muestra un único aviso.

### Eliminado

- El script original `create-tracklist.py`; su funcionalidad la cubre `trakt-manager sync lists/doomsday.yaml`.

### Seguridad

- Las respuestas llevan una CSP estricta (`default-src 'self'`), salvo `/docs`, `/redoc` y `/openapi.json`.
- Las credenciales nunca se devuelven completas por la API y se guardan con permisos 600.
- Los nombres de definición se validan (`^[a-z0-9][a-z0-9-]{0,63}$`) para evitar recorridos de rutas.

[Unreleased]: https://github.com/pedrit01/trakt-manager/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pedrit01/trakt-manager/releases/tag/v0.1.0
