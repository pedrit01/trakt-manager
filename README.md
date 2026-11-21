# trakt-manager

Crea y mantiene listas de [Trakt](https://trakt.tv) a partir de ficheros de definición en YAML o JSON. Se puede usar desde la línea de comandos o, a distancia, con una API HTTP. Todo se ejecuta en Docker.

Cada definición describe la lista tal como debe quedar: películas, series, temporadas o episodios concretos, en orden. La sincronización es **idempotente**: crea la lista si no existe y, si existe, solo añade lo que falta, quita lo que sobra y reordena. Repetirla sin cambios no toca nada.

Ejemplo incluido: [`lists/doomsday.yaml`](lists/doomsday.yaml), la ruta cronológica hacia *Vengadores: Doomsday* (películas completas y solo los episodios imprescindibles de cada serie).

## Puesta en marcha con Docker

1. **Crea una aplicación en Trakt** en <https://trakt.tv/oauth/applications> → *New Application*. Ponle cualquier nombre y en *Redirect URI* escribe `urn:ietf:wg:oauth:2.0:oob`. Copia el *Client ID* y el *Client Secret*.

2. **Configura el entorno:**

   ```bash
   cp .env.example .env
   # Edita .env: TRAKT_CLIENT_ID, TRAKT_CLIENT_SECRET y API_KEY.
   # Para generar una API_KEY:
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. **Levanta el servicio:**

   ```bash
   docker compose up -d --build
   docker compose ps          # el servicio debe aparecer como "healthy"
   ```

4. **Inicia sesión en Trakt** (solo una vez: el token se guarda en el volumen `trakt-data` y se renueva solo):

   ```bash
   docker compose run --rm trakt-manager auth login
   # Abre la URL que aparece, introduce el código y espera la confirmación.
   ```

5. **Crea la lista:**

   ```bash
   # Primero previsualiza: no modifica tu cuenta.
   docker compose run --rm trakt-manager sync lists/doomsday.yaml --dry-run
   # Después, sincroniza de verdad.
   docker compose run --rm trakt-manager sync lists/doomsday.yaml
   ```

Las definiciones de `lists/` se montan en el contenedor, así que se pueden editar sin reconstruir la imagen.

### Acceso desde otros equipos

Por defecto la API solo se publica en este equipo (`127.0.0.1:8000`), porque escribe en tu cuenta de Trakt. Para acceder desde otros equipos:

- **Red local:** pon `API_BIND=0.0.0.0` en `.env` y ejecuta `docker compose up -d`. Usa una `API_KEY` larga y aleatoria.
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

Todas las rutas, salvo `/health`, necesitan la cabecera `X-API-Key: <API_KEY>`. La documentación interactiva está en <http://127.0.0.1:8000/docs>.

| Método y ruta | Qué hace |
| --- | --- |
| `GET /health` | Estado del servicio y si hay sesión de Trakt (sin clave). |
| `POST /auth/device` | Inicia el login: devuelve `verification_url` y `user_code`. |
| `GET /auth/status` | `authorized` (con usuario), `pending`, `expired`, `error` o `none`. |
| `DELETE /auth` | Cierra la sesión. |
| `GET /definitions` | Definiciones de `lists/` con su validez y número de entradas. |
| `GET /definitions/{nombre}` | Una definición (`doomsday` para `lists/doomsday.yaml`). |
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

```bash
docker compose run --rm --build tests                     # todos los tests (Python 3.12)
docker compose run --rm tests tests/test_sync.py -q       # un fichero
docker compose run --rm tests -k shared_notes             # tests que contengan un nombre
```

Los tests usan un Trakt simulado (`tests/fake_trakt.py`) y nunca llaman a la API real. El código fuente está en `src/trakt_manager/`. Cada módulo explica su función en su docstring.
