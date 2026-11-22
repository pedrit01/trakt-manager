# trakt-manager

Crea y mantiene listas de [Trakt](https://trakt.tv) a partir de definiciones en YAML o JSON. Se usa desde una **interfaz web**, una API HTTP o la línea de comandos, y todo funciona dentro de Docker.

Cada definición describe la lista tal como debe quedar: películas, series, temporadas o episodios concretos, en orden. La sincronización es **idempotente**: crea la lista si no existe y, si existe, solo añade lo que falta, quita lo que sobra y reordena. Repetirla sin cambios no toca nada.

Ejemplo incluido: [`lists/doomsday.yaml`](lists/doomsday.yaml), la ruta cronológica hacia *Vengadores: Doomsday* (películas completas y solo los episodios imprescindibles de cada serie).

## Instalación

Este repositorio publica una única imagen, `ghcr.io/pedrit01/trakt-manager`, para `linux/amd64` y `linux/arm64`. Las dos formas de instalarlo usan esa misma imagen, así que no hace falta construir nada:

| Etiqueta | Qué contiene |
| --- | --- |
| `latest` | La última versión de `main`. |
| `0.1.0`, `0.1`… | Una versión concreta, publicada con cada [release](https://github.com/pedrit01/trakt-manager/releases). |

### Con Docker Desktop u OrbStack (sin terminal)

No hace falta clonar el repositorio ni abrir una terminal.

1. **Descarga y arranca la imagen.** En Docker Desktop, busca `ghcr.io/pedrit01/trakt-manager` y pulsa *Run*. En las opciones, publica el puerto **8000** del contenedor (*Host port* `8000`) y, para no perder datos al borrar el contenedor, añade un volumen con *Container path* `/data`. En OrbStack, haz lo mismo desde *Containers → New*.
2. **Abre <http://localhost:8000/>.** Como aún no está configurado, aparece el asistente.
3. **Copia el código de configuración.** Está en los registros del contenedor (*Containers → trakt-manager → Logs*), en la línea «usa este código de configuración: XXXX-XXXX». Así solo quien controla el contenedor puede configurarlo.
4. **Crea una aplicación en Trakt** en <https://trakt.tv/oauth/applications> → *New Application* y ponle cualquier nombre. Copia el *Client ID* en el asistente. Si el formulario pide una *Redirect URI*, pon `http://localhost:8000/`: trakt-manager no la usa, porque inicia sesión con un código (device flow). El *Client Secret* es **opcional**. Las aplicaciones nuevas de Trakt no lo tienen, así que déjalo vacío salvo que tu aplicación lo tenga.
5. **Guarda la clave de API** que aparece al terminar (por ejemplo, en tu gestor de contraseñas). No se vuelve a mostrar, y la necesitarás para entrar desde otro navegador o para usar la API.

La configuración, el token de Trakt y las definiciones que guardes desde la interfaz viven en `/data`, así que se conservan al recrear o actualizar el contenedor si mantienes el mismo volumen.

### Con docker compose

Clona el repositorio para tener el `docker-compose.yml` y las definiciones de ejemplo de `lists/`. `docker compose up` descarga la imagen publicada:

```bash
git clone https://github.com/pedrit01/trakt-manager.git
cd trakt-manager
docker compose up -d
docker compose ps          # el servicio debe aparecer como "healthy"
```

Después abre <http://127.0.0.1:8000/> y sigue el asistente (el código sale en `docker compose logs`).

Por defecto se usa `latest`. Para fijar una versión, pon `TRAKT_MANAGER_VERSION=0.1.0` en `.env`. Para actualizar:

```bash
git pull                   # definiciones de ejemplo y docker-compose.yml al día
docker compose pull        # nueva imagen
docker compose up -d
```

También puedes configurarlo por variables de entorno en lugar de con el asistente: `cp .env.example .env` y rellena `TRAKT_CLIENT_ID` y `API_KEY` (y `TRAKT_CLIENT_SECRET` solo si tu aplicación de Trakt lo tiene). Lo que venga del entorno **tiene prioridad** y la interfaz lo muestra como no editable.

Con compose también puedes usar el CLI, que comparte la configuración con la interfaz web:

```bash
docker compose run --rm trakt-manager auth login
docker compose run --rm trakt-manager sync lists/doomsday.yaml --dry-run
docker compose run --rm trakt-manager sync lists/doomsday.yaml
```

Las definiciones de `lists/` se montan en el contenedor, así que puedes editarlas sin descargar ni construir otra imagen.

## La interfaz web

- **Trakt**: pulsa «Conectar con Trakt», abre la URL que aparece (en cualquier dispositivo), introduce el código y confirma en trakt.tv. La página detecta la confirmación sola. «Desconectar» cierra la sesión.
- **Definiciones**: lista las incluidas en la imagen y las tuyas. Puedes pegar o subir un `.yaml`/`.json`, validarlo sin tocar Trakt, guardarlo, descargarlo y borrarlo (solo las tuyas). Si guardas una con el mismo nombre que una incluida, la tuya la sustituye.
- **Previsualizar / sincronizar**: muestra qué ha encontrado Trakt para cada entrada (título, año e id) y qué no. Antes de sincronizar de verdad, enseña los cambios y pide confirmación. Si sincronizas sin «incluir extras», los extras añadidos en una sincronización anterior se quitan, porque la lista refleja la definición con las opciones elegidas.
- **Mis listas**: tus listas de Trakt y sus elementos en orden.
- **Ajustes**: muestra de dónde sale cada clave, permite cambiar las credenciales de Trakt (cambiar el Client ID cierra la sesión, porque el token es de la aplicación anterior) y regenerar la clave de API (la anterior deja de valer al instante).

Al entrar, la clave se guarda solo para esa pestaña, salvo que marques «Recordarla en este navegador». «Salir» la olvida.

## Acceso desde otros equipos

La interfaz y la API escriben en tu cuenta de Trakt, así que conviene saber quién llega a ellas:

- **Con compose**, por defecto solo se publican en este equipo (`127.0.0.1:8000`). Para la red local, pon `API_BIND=0.0.0.0` en `.env` y ejecuta `docker compose up -d`.
- **Con Docker Desktop**, un puerto publicado es accesible **desde toda la red** por defecto. Completa el asistente nada más arrancar: hasta entonces solo te protege el código de configuración, y después la clave de API.
- **Internet:** no publiques el puerto directamente. Ponlo detrás de un proxy inverso con TLS (Caddy, Traefik, nginx…).

## Comandos del CLI

Dentro de Docker, antepón `docker compose run --rm trakt-manager` a cada comando. Fuera de Docker se instala con `pip install .` (Python ≥ 3.11).

| Comando | Qué hace |
| --- | --- |
| `auth login` | Inicia sesión en Trakt con un código que confirmas en el navegador. |
| `auth status` | Indica si hay sesión y con qué usuario. |
| `auth logout` | Revoca el token y lo borra. |
| `validate <fichero>` | Valida una definición sin contactar con Trakt y muestra todos los errores. |
| `sync <fichero> [--dry-run] [--include-extras]` | Crea o actualiza la lista. `--dry-run` solo muestra los cambios. `--include-extras` añade las entradas marcadas como extra. |
| `lists` | Muestra tus listas (id, nombre, privacidad, número de elementos). |
| `show <id o slug>` | Muestra los elementos de una lista en orden. |
| `serve` | Arranca la API HTTP (lo que hace el contenedor por defecto). |

`validate`, `sync`, `lists` y `show` aceptan `--json` para obtener el resultado como JSON. El código de salida es `0` si todo va bien y `1` ante cualquier error.

`sync --dry-run` funciona sin sesión, ya que solo necesita `TRAKT_CLIENT_ID`. En ese caso compara como si la lista no existiera.

## API HTTP

Todas las rutas, salvo `/health`, la interfaz web y el asistente, necesitan la cabecera `X-API-Key: <API_KEY>`. Mientras el servicio no está configurado, el resto de rutas responden `503`. La documentación interactiva está en <http://127.0.0.1:8000/docs>.

| Método y ruta | Qué hace |
| --- | --- |
| `GET /health` | Estado del servicio, modo (`ready` o `setup`) y si hay sesión de Trakt (sin clave). |
| `GET /setup/status`, `POST /setup` | Asistente inicial (sin clave; `POST` exige el código de configuración y devuelve la clave generada una vez). |
| `GET /settings`, `PUT /settings`, `POST /settings/api-key` | Ver el origen de cada clave, cambiar las credenciales de Trakt y regenerar la clave de API. |
| `POST /auth/device` | Inicia el login: devuelve `verification_url` y `user_code`. |
| `GET /auth/status` | `authorized` (con usuario), `pending`, `expired`, `error` o `none`. |
| `DELETE /auth` | Cierra la sesión. |
| `GET /definitions` | Definiciones incluidas y guardadas, con su origen, validez y número de entradas. |
| `GET /definitions/{nombre}` | Una definición (`doomsday` para `lists/doomsday.yaml`). |
| `GET /definitions/{nombre}/source` | El fichero original, para descargarlo con sus comentarios. |
| `PUT /definitions/{nombre}`, `DELETE /definitions/{nombre}` | Guardar (cuerpo YAML o JSON, se valida antes) o borrar una definición guardada. |
| `POST /validate` | Valida una definición enviada en el cuerpo (422 si tiene errores). |
| `POST /definitions/{nombre}/sync?dry_run=true&include_extras=false` | Sincroniza o previsualiza una definición de `lists/`. |
| `POST /sync?dry_run=true` | Igual, con la definición en el cuerpo. |
| `GET /lists`, `GET /lists/{id}` | Tus listas y los elementos de una lista. |

Las respuestas de sincronización y validación son las mismas que la salida `--json` del CLI. Hay dos códigos de error que conviene conocer: `409` cuando falta la sesión o ya hay otra sincronización de la misma lista en curso, y `502` cuando Trakt falla.

```bash
KEY="tu API_KEY"
curl -s http://127.0.0.1:8000/health
curl -s -X POST -H "X-API-Key: $KEY" http://127.0.0.1:8000/auth/device
curl -s -H "X-API-Key: $KEY" http://127.0.0.1:8000/definitions
curl -s -X POST -H "X-API-Key: $KEY" "http://127.0.0.1:8000/definitions/doomsday/sync?dry_run=true"
curl -s -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/yaml" \
     --data-binary @lists/doomsday.yaml http://127.0.0.1:8000/validate
```

## Formato de las definiciones

```yaml
name: "Mi maratón"            # obligatorio; identifica la lista en tu cuenta
description: "Opcional"
privacy: private              # private | friends | public
display_numbers: true
allow_comments: false
# trakt_list_id: 12345        # opcional: fija la lista aunque la renombres en Trakt

entries:                      # el orden de la lista es el orden de este bloque
  - type: movie               # movie | show | season | episodes
    title: "Shang-Chi"        # título visible (opcional)
    query: "Shang-Chi and the Legend of the Ten Rings"   # texto de búsqueda en Trakt
    year: 2021                # ayuda a elegir el resultado (año exacto, si no ±1)
    block: "1. Inicio"        # agrupación; forma parte de la nota en Trakt
    note: "Película completa"
  - type: episodes
    query: "Loki"
    ids: { tmdb: 84958 }      # opcional: trakt, slug, imdb o tmdb; evita la búsqueda
    season: 2
    episodes: [1, 4, 5, 6]
  - type: movie
    query: "X2"
    year: 2003
    extra: true               # solo con --include-extras
```

Las notas que se guardan en Trakt tienen este formato: `"<bloque> | <nota>"` para películas, series y temporadas, y `"<título> S01E04 | <bloque>"` para los episodios. Trakt puede limitar las notas por elemento a las cuentas VIP. Si no las guarda, la sincronización avisa y la lista se crea igualmente.

## Desarrollo

Para probar cambios en el código, añade `--build`. Así compose construye la imagen desde tu copia local en lugar de descargar la publicada:

```bash
docker compose up -d --build                              # GUI y API con tu código
docker compose run --rm --build tests                     # todos los tests (Python 3.12)
docker compose run --rm tests tests/test_sync.py -q       # un fichero
docker compose run --rm tests -k shared_notes             # tests que contengan un nombre
```

Los tests usan un Trakt simulado (`tests/fake_trakt.py`) y nunca llaman a la API real. El código fuente está en `src/trakt_manager/`. Cada módulo explica su función en su docstring.

### Interfaz web

La interfaz está en `src/trakt_manager/web/`: HTML, CSS y módulos JavaScript estándar, sin dependencias ni paso de compilación. La sirve la propia API en `/`. Para probarla sin credenciales de Trakt hay un servidor de demostración conectado al Trakt simulado:

```bash
docker compose run --rm -p 8080:8080 --entrypoint python tests tests/demo_server.py
# http://localhost:8080/ · código de configuración: AB12-CD34 · cualquier Client ID vale
```

En la demostración, el login con Trakt se confirma solo a los 6 segundos.

### Publicar la imagen

El flujo `.github/workflows/publish-image.yml` ejecuta los tests y, si pasan, publica `ghcr.io/pedrit01/trakt-manager` para `linux/amd64` y `linux/arm64`:

- con cada push a `main`: etiquetas `latest` y `sha-<commit>`;
- con cada etiqueta `vX.Y.Z`: etiquetas `X.Y.Z` y `X.Y`.

En las pull requests solo se ejecutan los tests. La primera vez que se publique hay que hacer público el paquete para que se pueda descargar sin iniciar sesión: en GitHub, *Packages → trakt-manager → Package settings → Change visibility → Public*.
