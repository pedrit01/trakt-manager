# Proposal

## Why

Hoy, para usar trakt-manager hay que clonar el repositorio, editar un `.env`, construir la imagen y lanzar comandos (`docker compose run ... auth login`, `sync`...). Queremos que cualquiera pueda usarlo sin terminal: descargar una imagen ya publicada desde Docker Desktop u OrbStack, abrir el navegador y hacer todo desde una interfaz web. Eso incluye introducir las claves.

## What Changes

- **GUI web** servida por el propio contenedor en `/`, sin paso de build de frontend. Cubre todo lo que hace el CLI salvo `serve`:
  - iniciar, consultar y cerrar la sesión de Trakt;
  - validar una definición;
  - previsualizar y sincronizar (con o sin extras);
  - ver las listas del usuario y sus elementos.

  Además permite subir, pegar, guardar y borrar definiciones, para no tener que editar ficheros.
- **Configuración desde la GUI**:
  - En el primer arranque sin configuración, un asistente pide el Client ID y el Client Secret de Trakt y genera la `API_KEY`.
  - Los valores se guardan en el volumen de datos.
  - Las variables de entorno siguen funcionando y tienen prioridad. Lo que viene del entorno se muestra como no editable.
  - Para que nadie más pueda reclamar una instancia recién arrancada, el asistente exige un código de configuración de un solo uso que aparece en los registros del contenedor. Docker Desktop y OrbStack los muestran en su propia interfaz.
- **Imagen publicada**: un flujo de GitHub Actions construye la imagen para `linux/amd64` y `linux/arm64` y la publica en GHCR (`ghcr.io/pedrit01/trakt-manager`). Basta con buscarla y ejecutarla desde Docker Desktop u OrbStack, sin clonar ni construir nada.
- **BREAKING (comportamiento del servicio)**: la API ya no se niega a arrancar sin `API_KEY`. Arranca en *modo configuración*, en el que solo responden `/health`, la GUI y las rutas del asistente.
- Las definiciones guardadas desde la GUI van a un directorio escribible del volumen de datos (`DATA_DIR/lists`). Se muestran junto a las incluidas en la imagen (o montadas en `LISTS_DIR`).

## Capabilities

### New Capabilities
- `web-gui`: interfaz web del navegador que expone las operaciones del CLI y la gestión de definiciones.
- `runtime-settings`: configuración de credenciales y `API_KEY` en tiempo de ejecución (asistente inicial, almacenamiento en el volumen, prioridad del entorno, código de configuración y aplicación de cambios sin reiniciar).
- `image-publishing`: construcción y publicación automática de la imagen multiarquitectura en GHCR.

### Modified Capabilities
- `web-api`: la protección con clave deja de impedir el arranque (modo configuración). Se añaden rutas para gestionar definiciones guardadas.
- `container-runtime`: la configuración puede venir del entorno o de la GUI. Las definiciones guardadas persisten en el volumen. La imagen funciona sin compose ni `.env` (por ejemplo, ejecutada desde Docker Desktop).

## Impact

- **Dependencia previa**: el cambio `dockerize-trakt-manager` debe archivarse antes de aplicar este, para que existan los specs `web-api` y `container-runtime` que aquí se modifican. Tiene 5 tareas pendientes que necesitan credenciales reales.
- **Código**:
  - nuevos `src/trakt_manager/settings_store.py` y `src/trakt_manager/web/` (HTML, CSS y JS estáticos);
  - cambios en `config.py`, `app_context.py`, `api.py` y `definitions.py`;
  - nuevo `.github/workflows/publish-image.yml`;
  - actualización de `Dockerfile`, `docker-compose.yml` y `README.md`.
- **Dependencias**: ninguna nueva en Python. La GUI no usa CDN ni librerías externas.
- **Sistemas externos**: GitHub Actions y GitHub Container Registry. Para que la imagen se pueda descargar sin iniciar sesión, el paquete de GHCR tiene que ser público, y eso se configura una vez a mano en GitHub.
- **Seguridad**:
  - Las credenciales pasan a guardarse en el volumen (`settings.json`, permisos 600) y nunca se devuelven completas por la API.
  - Docker Desktop publica los puertos en todas las interfaces por defecto, así que el código de configuración y la `API_KEY` son la única barrera ante otros equipos de la red.
