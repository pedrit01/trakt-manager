"""trakt-manager: crea y sincroniza listas de Trakt a partir de ficheros de definición.

El paquete se organiza en capas:

- ``config``: configuración leída de variables de entorno.
- ``trakt_client``: cliente HTTP de bajo nivel para la API de Trakt (reintentos, límites, token).
- ``auth``: autorización OAuth (device flow), almacenamiento y renovación del token.
- ``definitions``: formato y validación de los ficheros de definición de listas.
- ``resolver``: traduce las entradas de una definición a elementos concretos de Trakt.
- ``trakt_lists``: operaciones sobre las listas del usuario en Trakt.
- ``sync``: calcula y aplica los cambios para que una lista coincida con su definición.
- ``app_context``: construye y conecta las piezas anteriores para el CLI y la API.
- ``cli`` y ``api``: las dos interfaces de usuario, capas finas sobre el núcleo.
"""

__version__ = "0.1.0"
