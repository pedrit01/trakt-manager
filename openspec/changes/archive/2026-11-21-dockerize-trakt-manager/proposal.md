# Proposal

## Why

Hoy la única herramienta es `create-tracklist.py`: un script suelto que crea una sola lista (la ruta hacia *Vengadores: Doomsday*), con los datos incrustados en el código, el token guardado en el directorio actual y sin forma de usarlo salvo ejecutándolo a mano en una máquina con Python. Queremos convertirlo en un gestor de listas de Trakt reutilizable, que se levante con Docker con todo lo necesario y se pueda manejar tanto desde la línea de comandos como remotamente desde una API web.

## What Changes

- Nuevo paquete Python `trakt_manager` que extrae del script el cliente de la API de Trakt, la autenticación OAuth (device flow) y la lógica de resolución y creación de listas.
- Las listas pasan a describirse en **ficheros de definición YAML/JSON** (directorio `lists/`). La ruta Doomsday se migra a `lists/doomsday.yaml`.
- **CLI** (`trakt-manager`) con comandos para autenticarse, validar una definición, previsualizar (dry-run), crear/sincronizar una lista y listar las listas del usuario.
- **API HTTP** (servicio siempre encendido) que expone las mismas operaciones, protegida con una clave de API, para administrar listas desde otro equipo.
- **Imagen Docker + `docker-compose.yml`**: un servicio `api` y la posibilidad de ejecutar el CLI con `docker compose run`, con credenciales por variables de entorno (`.env`) y un volumen persistente para el token y las definiciones.
- Corrección de un fallo del script actual: varias películas comparten la misma nota (p. ej. "1. Inicio del Multiverso | Película completa"), y al indexarlas por nota solo sobrevive una, por lo que se añaden películas repetidas y se pierden otras.
- El token OAuth se renueva automáticamente con el `refresh_token` cuando caduca.
- `create-tracklist.py` se elimina una vez migrado (su funcionalidad queda cubierta por `trakt-manager sync lists/doomsday.yaml`).

## Capabilities

### New Capabilities
- `trakt-auth`: autenticación OAuth2 con Trakt mediante device flow, persistencia del token y renovación automática.
- `list-definitions`: formato de los ficheros de definición de listas (metadatos de la lista y entradas ordenadas de películas, series completas o episodios concretos) y su validación.
- `list-sync`: resolución de las entradas de una definición contra Trakt y creación/actualización de la lista respetando el orden, con modo dry-run.
- `cli`: interfaz de línea de comandos que expone autenticación, validación, previsualización, sincronización y consulta de listas.
- `web-api`: API HTTP autenticada que expone las mismas operaciones para uso remoto.
- `container-runtime`: imagen Docker y composición que levantan el servicio y permiten ejecutar el CLI, con configuración por entorno y datos persistentes.

### Modified Capabilities
<!-- Ninguna: no existen specs previas en el proyecto. -->

## Impact

- **Código**: nuevo paquete `src/trakt_manager/`, nuevo directorio `lists/`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `.gitignore`, `README.md`. Se retira `create-tracklist.py`.
- **Dependencias**: se abandona "solo librería estándar". Nuevas: `httpx` (cliente HTTP), `PyYAML`, `pydantic` (validación de definiciones), `typer` (CLI), `fastapi` + `uvicorn` (API), `pytest` para pruebas.
- **Sistemas externos**: API de Trakt (`api.trakt.tv`), con sus límites de peticiones.
- **Seguridad**: la API expuesta en red actúa sobre la cuenta de Trakt del usuario; requiere clave de API y no debe publicarse sin ella. Los secretos (`TRAKT_CLIENT_SECRET`, token) nunca van al repositorio.
