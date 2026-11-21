# Tasks

> Criterio común a todas las tareas de implementación: una tarea solo está terminada si su código es legible y está documentado (docstrings en español en módulos, clases y funciones públicas, type hints en todas las firmas, y comentarios que explican el porqué de lo no obvio). Ninguna tarea hace commit ni push.

## 1. Requisito previo

- [ ] 1.1 Archivar `dockerize-trakt-manager` cuando estén cerradas sus tareas pendientes (o con la decisión explícita del usuario de archivarlo con ellas abiertas); verificar que existen `openspec/specs/web-api/spec.md` y `openspec/specs/container-runtime/spec.md` y que `openspec validate add-web-gui --strict` ya no muestra el aviso "Archive would refuse this delta"

## 2. Configuración en tiempo de ejecución (runtime-settings)

- [ ] 2.1 Crear `settings_store.py` con `SettingsStore` (`DATA_DIR/settings.json`, permisos 600, escritura atómica) y `resolve_settings()` que combina entorno y valores guardados, con el origen de cada clave (`env`/`stored`/`missing`); verificar con tests de prioridad del entorno, valores guardados, permisos del fichero y `.env` contado como entorno
- [ ] 2.2 Añadir `AppRuntime` en `app_context.py` (contexto vigente, `reload()` bajo lock, `is_configured()`, `SyncLocks` y device flow en segundo plano que sobreviven a las recargas), y hacer que el CLI construya su contexto con la configuración efectiva; verificar con tests de que tras `reload()` se usan las credenciales nuevas y de que `docker compose run ... lists` funciona con credenciales guardadas desde la GUI
- [ ] 2.3 Implementar `SetupGuard` (código `XXXX-XXXX` escrito en el log con nivel WARNING al arrancar sin configurar, invalidado al completar la configuración y regenerado tras 10 fallos); verificar con tests del código correcto, del incorrecto (403), de la regeneración y de que el código se escribe en el log

## 3. API: modo configuración, ajustes y definiciones (web-api)

- [ ] 3.1 Refactorizar `api.py` para obtener el contexto en cada petición desde `AppRuntime`, arrancar en modo configuración sin `API_KEY` (503 en las rutas protegidas, `/health` con `mode`) y validar `X-API-Key` contra la clave vigente; adaptar los tests existentes de la API y añadir tests de arranque sin clave, 503 y clave regenerada (401 con la anterior)
- [ ] 3.2 Implementar `GET /setup/status`, `POST /setup` (con código, genera y devuelve la `API_KEY` una vez y responde 409 si ya está configurado), `GET/PUT /settings` (sin devolver secretos; rechaza claves del entorno; el cambio de Client ID cierra la sesión de Trakt) y `POST /settings/api-key`; verificar con tests de cada escenario de `runtime-settings` y `web-api`
- [ ] 3.3 Crear `definition_catalog.py` con `DefinitionCatalog` (orígenes `bundled` y `saved`, prioridad de las guardadas, validación del nombre, guardado del texto original) y usarlo en `GET/PUT/DELETE /definitions` y en `POST /definitions/{nombre}/sync`; verificar con tests de guardado, de definición inválida (422), de nombre con `..` (422 sin escribir), de borrado de una incluida (409) y de prioridad ante el mismo nombre
- [ ] 3.4 Servir la GUI: `src/trakt_manager/web/` como package data en `pyproject.toml`, `StaticFiles` montado en `/` después de las rutas de la API y cabecera `Content-Security-Policy: default-src 'self'`; verificar con un test de humo de que `/` devuelve el HTML con la CSP y de que las rutas de la API siguen respondiendo

## 4. GUI web (web-gui)

- [ ] 4.1 Crear la estructura de la GUI (`index.html`, `styles.css` adaptable a móvil, `api.js` con la clave, la traducción de errores al español y la gestión de 401/409/503/502, y `router.js`) y verificar en un navegador real que carga sin peticiones externas y que el diseño se ve bien con 375 px de ancho
- [ ] 4.2 Vista del asistente inicial (código de configuración, Client ID y Secret con el enlace a trakt.tv/oauth/applications y la Redirect URI, y la `API_KEY` generada mostrada una vez con botón de copiar) y vista de acceso con la clave (recordar opcional y salir); verificar en el navegador el flujo completo desde un contenedor sin configurar
- [ ] 4.3 Vista de sesión de Trakt (estado, conectar con la URL y el código, consulta cada 3 s mientras está pendiente, código caducado y desconectar con confirmación); verificar en el navegador contra el Trakt simulado y documentar los pasos con Trakt real en el README
- [ ] 4.4 Vista de definiciones (lista con origen, validez y entradas; pegar, subir, descargar, validar y borrar con confirmación; errores con posición y campo) y verificar en el navegador todos los escenarios de "Gestión de definiciones" y "Validar una definición"
- [ ] 4.5 Vista de sincronización (previsualizar, incluir extras, confirmación con los cambios antes de sincronizar, informe de resolución, cambios y avisos; manejo de sin sesión y de sincronización en curso) y verificar en el navegador con el Trakt simulado los escenarios de "Previsualizar y sincronizar"
- [ ] 4.6 Vistas de listas (tabla y detalle de una lista en orden) y de ajustes (origen de cada clave, cambiar credenciales, regenerar la `API_KEY`); verificar en el navegador, comprobando que la clave anterior deja de funcionar tras regenerarla

## 5. Contenedor e imagen publicada (container-runtime, image-publishing)

- [ ] 5.1 Ajustar `Dockerfile` (crear `DATA_DIR/lists`; añadir etiquetas OCI de descripción) y `docker-compose.yml` (`env_file` opcional ya lo es; documentar que `.env` es opcional) y verificar con `docker run -p 8000:8000 trakt-manager:latest` sin `.env` que el servicio queda `healthy` en modo configuración y que tras configurarlo desde la GUI y recrear el contenedor con el mismo volumen se conservan la configuración y las definiciones guardadas
- [ ] 5.2 Crear `.github/workflows/publish-image.yml` (job `test` con el target `dev` en push y PR; job `publish` dependiente, solo en `main` y `v*`, con QEMU, Buildx, login en GHCR con `GITHUB_TOKEN`, `docker/metadata-action` y build-push `linux/amd64,linux/arm64` con caché) y verificarlo con `actionlint` (ejecutado en Docker) y construyendo localmente las dos plataformas con `docker buildx build --platform linux/amd64,linux/arm64 --target runtime .`
- [ ] 5.3 Documentar en `README.md` el uso sin comandos (buscar `ghcr.io/pedrit01/trakt-manager` en Docker Desktop u OrbStack, publicar el puerto 8000, copiar el código de configuración de los registros, completar el asistente), el paso manual de hacer público el paquete en GHCR y la advertencia sobre la exposición en red; actualizar `CLAUDE.md` con la nueva arquitectura (AppRuntime, catálogo, GUI); verificar siguiendo los pasos del README desde cero con la imagen construida en local

## 6. Integración

- [ ] 6.1 Recorrido completo en el navegador con el contenedor local y el Trakt simulado o real: asistente → clave → conectar Trakt → subir una definición → previsualizar → sincronizar → ver la lista → regenerar la clave → recrear el contenedor; verificar que `pytest` pasa entero y que `openspec validate add-web-gui --strict` es válido

## Workflow follow-up

- Hacer merge a `main` y comprobar en GitHub Actions que se publica `ghcr.io/pedrit01/trakt-manager:latest` para las dos arquitecturas.
- Hacer público el paquete en GHCR (paso único en la configuración del paquete en GitHub).
- Archivar el cambio (`/openspec-archive-change`) una vez revisado e implementado.
