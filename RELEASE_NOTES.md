# trakt-manager v0.1.0

Primera versión de **trakt-manager**: crea y mantiene listas de [Trakt](https://trakt.tv) a partir de ficheros YAML o JSON, desde una interfaz web, una API HTTP o la línea de comandos, todo dentro de una sola imagen Docker.

## Lo más destacado

- **Sin terminal.** Busca `ghcr.io/pedrit01/trakt-manager` en Docker Desktop u OrbStack, publica el puerto 8000, añade un volumen en `/data` y abre <http://localhost:8000/>. Un asistente te guía en la configuración.
- **Listas como código.** Cada definición describe la lista tal como debe quedar: películas, series, temporadas o episodios concretos, en orden, con bloques y notas.
- **Sincronización idempotente.** Crea la lista si no existe; si existe, añade lo que falta, quita lo que sobra y reordena. Repetirla sin cambios no toca nada. Puedes previsualizar los cambios antes de aplicarlos.
- **Tres formas de usarlo**, con los mismos resultados: interfaz web, API HTTP con clave (`X-API-Key`) y CLI (`validate`, `sync`, `lists`, `show`, `auth`).
- **Inicio de sesión con código** (device flow): confirmas en trakt.tv desde cualquier dispositivo y el token se renueva solo.
- **Funciona con las aplicaciones nuevas de Trakt**: el Client Secret es opcional.
- **Ejemplo incluido:** `lists/doomsday.yaml`, la ruta cronológica hacia *Vengadores: Doomsday*.

## Imagen

```bash
docker pull ghcr.io/pedrit01/trakt-manager:0.1.0
```

Disponible para `linux/amd64` y `linux/arm64` (incluidos los Mac con Apple Silicon). También se publica como `0.1`.

## Primeros pasos

1. Arranca el contenedor y abre <http://localhost:8000/>.
2. Copia el código de configuración de los registros del contenedor («usa este código de configuración: XXXX-XXXX»).
3. Crea una aplicación en <https://trakt.tv/oauth/applications> y pega su *Client ID* en el asistente (el *Client Secret* solo si tu aplicación lo tiene).
4. Guarda la clave de API que se muestra al terminar: no se vuelve a mostrar.
5. Conecta con Trakt y sincroniza tu primera definición.

Si lo prefieres, puedes configurarlo con variables de entorno (`TRAKT_CLIENT_ID`, `API_KEY` y, opcionalmente, `TRAKT_CLIENT_SECRET`), que tienen prioridad sobre lo guardado desde la interfaz. Consulta el [README](README.md) para el uso con `docker compose`, el CLI y la API.

## A tener en cuenta

- **Acceso desde la red.** Docker Desktop publica los puertos en todas las interfaces. Completa el asistente nada más arrancar y no expongas el puerto a Internet sin un proxy inverso con TLS.
- **Notas y cuentas VIP.** Trakt puede guardar las notas por elemento solo en cuentas VIP. Sin VIP, la lista se crea igualmente sin notas y la sincronización avisa una vez.
- **Paquete público.** Tras la primera publicación hay que marcar el paquete de GHCR como público para poder descargarlo sin iniciar sesión.

El detalle completo de cambios está en el [CHANGELOG](CHANGELOG.md).
