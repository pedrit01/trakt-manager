# Design

## Context

Lo que existe (cambio `dockerize-trakt-manager`):

- La configuración se lee una sola vez del entorno (`config.Settings`).
- `AppContext` crea en caché el `TraktClient` con el `TRAKT_CLIENT_ID` de ese momento. Cambiar las credenciales hoy obliga a reiniciar.
- `api.create_app` lee `API_KEY` al crear la aplicación y lanza `ConfigError` si falta, así que `serve` no arranca.
- Las definiciones solo se leen de `LISTS_DIR`. En compose se monta `./lists` en solo lectura. Con una imagen publicada sin montajes solo están las que van dentro de la imagen.
- El CLI y la API ya comparten los modelos de resultado (`SyncResult`, `ValidationOutcome`), y eso es lo que pintará la GUI.

Motivación y alcance: ver proposal.md. Comportamiento exigido: ver los specs de este cambio.

## Goals / Non-Goals

**Goals:**
- La GUI no reimplementa lógica: solo llama a la API existente y a las rutas nuevas.
- Configurar y reconfigurar sin reiniciar el contenedor.
- La GUI tiene cero dependencias y cero pasos de build. Es HTML, CSS y JS estándar, legible para quien mantenga el proyecto.

**Non-Goals:**
- Varios usuarios o roles en la GUI: una instancia tiene una `API_KEY` y una cuenta de Trakt.
- Un editor visual de definiciones con formularios por entrada. Se pega o se sube YAML/JSON. Un editor guiado puede venir después.
- Arrancar o actualizar el contenedor desde la propia GUI. Eso es de Docker Desktop u OrbStack.
- HTTPS dentro del contenedor (sigue siendo cosa de un proxy inverso).

## Decisions

### Configuración efectiva por capas
Nuevo módulo `settings_store.py`:
- `SettingsStore` lee y escribe `DATA_DIR/settings.json` con permisos 600 y escritura atómica, igual que `TokenStore`.
- `resolve_settings(env_settings, store)` devuelve un `Settings` efectivo y, para cada clave sensible, su origen (`env`, `stored` o `missing`).

Un valor cuenta como "del entorno" si está en `model_fields_set` del `Settings` leído del entorno. Así un `.env` también cuenta como entorno, que es lo esperado.

Alternativa descartada: escribir el `.env` desde la GUI. Con la imagen publicada no existe ese fichero, y mezclaría un fichero del anfitrión con estado del contenedor.

### Recarga en caliente con `AppRuntime`
Nuevo `AppRuntime` (en `app_context.py`), que guarda el `AppContext` vigente:
- `current()` devuelve el contexto vigente.
- `reload()` vuelve a resolver la configuración y crea un `AppContext` nuevo, bajo un lock.

Las rutas de la API piden el contexto en cada petición (`runtime.current()`) en lugar de capturarlo al crear la aplicación. Una operación en curso termina con el contexto con el que empezó, lo cual es aceptable. Los `SyncLocks` y el device flow en segundo plano viven en `AppRuntime` y no en el contexto, para que sobrevivan a una recarga.

Alternativa descartada: reiniciar el proceso tras guardar. Es más simple de implementar, pero corta las peticiones en curso y depende de la política de reinicio del contenedor.

### Modo configuración y código de un solo uso
- `AppRuntime.is_configured()` es verdadero si los tres valores están presentes.
- La dependencia `require_api_key` responde 503 si no lo están y 401 si la clave no coincide. La comparación se hace con `secrets.compare_digest` contra la clave **vigente**, que se lee en cada petición. Así una clave regenerada deja de valer al instante.
- `SetupGuard` guarda el código en memoria. Es un `secrets.token_hex(4)` con formato `XXXX-XXXX`, que se escribe en el log con nivel WARNING al arrancar sin configurar. Tras 10 fallos se genera otro, con un contador protegido por un lock.
- Cada reinicio sin configurar genera un código nuevo. No se guarda en disco: así nunca hay un código viejo válido.

Motivo: Docker Desktop publica los puertos en `0.0.0.0` por defecto. Sin el código, cualquiera en la red podría reclamar una instancia recién arrancada antes que su dueño. Los registros los ve quien controla el contenedor, y Docker Desktop y OrbStack los muestran en su interfaz, así que no hace falta ningún comando.

Alternativa descartada: permitir el asistente solo desde localhost. Dentro del contenedor todas las peticiones llegan desde la IP del puente de Docker, así que no se puede distinguir.

### Cambio de credenciales
- `PUT /settings` solo acepta las claves que no vienen del entorno.
- Si cambia el Client ID, primero se intenta revocar el token con las credenciales antiguas, después se borra `token.json` y por último se recarga.
- `POST /settings/api-key` genera una clave con `secrets.token_urlsafe(32)` y la devuelve una sola vez.

### Catálogo de definiciones
Nuevo `definition_catalog.py` con `DefinitionCatalog`, que une dos orígenes:
- `bundled`: `LISTS_DIR`, solo lectura (incluida en la imagen o montada).
- `saved`: `DATA_DIR/lists`, escribible.

Si un nombre está en los dos, gana el guardado. El nombre debe cumplir `^[a-z0-9][a-z0-9-]{0,63}$`, que impide salir del directorio (`..`, `/`). Las definiciones se guardan con el texto original (`.yaml` o `.json` según lo enviado) para conservar los comentarios. Antes de guardar se validan. La API usa el catálogo en `GET/PUT/DELETE /definitions` y en `POST /definitions/{nombre}/sync`. El CLI sigue recibiendo rutas de fichero.

### La GUI
- Ficheros en `src/trakt_manager/web/`: `index.html`, `styles.css` y módulos ES:
  - `api.js`: `fetch` con la clave, traducción de errores al español y reintento manual;
  - `router.js`: navegación por `#/ruta`;
  - `views/*.js`: una vista por sección (setup, login, trakt, definiciones, listas, ajustes).
- Se incluyen en el paquete como *package data* y FastAPI los sirve con `StaticFiles(html=True)` montado en `/`. El montaje va el último, para que las rutas de la API tengan prioridad.
- El contenido se pinta con `textContent`/`createElement`, nunca con `innerHTML` sobre datos, para evitar XSS con títulos o notas que vengan de Trakt.
- Las respuestas de la GUI llevan `Content-Security-Policy: default-src 'self'`, que hace cumplir que no se carga nada de terceros.
- La clave se guarda en `sessionStorage`, o en `localStorage` si el usuario marca "recordar en este navegador", y se envía como `X-API-Key`.
- Se descartan las cookies de sesión porque obligarían a añadir protección CSRF a todas las rutas POST/PUT/DELETE. Con una cabecera explícita no hace falta.
- El estado del device flow se consulta cada 3 s (`GET /auth/status`) mientras está `pending`, y se para al salir de la vista.

### Publicación de la imagen
`.github/workflows/publish-image.yml` tiene dos jobs:
1. `test`: construye el target `dev` y ejecuta pytest. Se ejecuta en `push` a `main`, en etiquetas `v*` y en pull requests.
2. `publish`: depende de `test`, solo en `push` a `main` o en etiquetas `v*`. Usa QEMU y Buildx, inicia sesión en GHCR con `GITHUB_TOKEN` (permiso `packages: write`), calcula etiquetas y etiquetas OCI con `docker/metadata-action` (`latest`, `sha-<corto>`, semver `X.Y.Z` y `X.Y`) y hace build-push para `linux/amd64,linux/arm64` con caché de GitHub Actions.

Las acciones se fijan por versión mayor. Como alternativa se pueden fijar por SHA más adelante.

Hacer el paquete público es un paso manual único en GitHub (*Package settings → Change visibility*). Se documenta en el README.

## Risks / Trade-offs

- [Secretos guardados en el volumen] → Permisos 600, propietario `app`. La API nunca los devuelve. Quien tenga acceso al volumen ya tiene acceso al token de Trakt, así que el nivel de riesgo no empeora.
- [Clave guardada en `localStorage` si se marca "recordar"] → Es opcional, va avisado en la GUI y la CSP limita la superficie de XSS. Por defecto se usa `sessionStorage`.
- [Alguien en la red ve los registros del contenedor] → Sería tener acceso al anfitrión, que queda fuera del modelo de amenaza.
- [Recarga en caliente con operaciones en curso] → Terminan con el contexto anterior. Los locks de sync están en `AppRuntime` y siguen evitando dos sincronizaciones de la misma lista.
- [Sin tests automáticos del JS] → Mantenerlo sin build ni dependencias es un objetivo. La API que usa la GUI está cubierta por pytest, la GUI se prueba en un navegador real en las tareas, y un test de humo comprueba que se sirve y que lleva la CSP.
- [La compilación arm64 con QEMU es lenta en Actions] → La caché de GitHub Actions lo reduce. Si fuera un problema, se pueden usar runners arm64 nativos.
- [Cambio de comportamiento: el servicio arranca sin `API_KEY`] → En modo configuración solo se exponen `/health`, la GUI y el asistente protegido por código. Quien ya usa `.env` no nota ningún cambio.

## Migration Plan

1. Archivar `dockerize-trakt-manager`, para que existan los specs `web-api` y `container-runtime` que este cambio modifica.
2. Desplegar: quien use compose con `.env` no tiene que hacer nada. Sus definiciones montadas aparecen como "incluidas".
3. Publicar: hacer merge a `main`, comprobar que el flujo publica y hacer el paquete público.

Vuelta atrás: volver a la imagen anterior. `settings.json` y `DATA_DIR/lists` se ignoran, así que no estorban.
