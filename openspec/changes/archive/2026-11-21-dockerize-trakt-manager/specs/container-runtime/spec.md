# Spec Delta

## Purpose

Permite levantar con Docker todo lo necesario para usar la herramienta (la API como servicio y el CLI bajo demanda), configurado por entorno y con datos que persisten entre reinicios.

## ADDED Requirements

### Requirement: Una imagen para API y CLI
El proyecto SHALL proporcionar una única imagen Docker que, por defecto, arranca la API y que también permite ejecutar cualquier comando del CLI.

#### Scenario: Arranque del servicio
- **WHEN** se ejecuta `docker compose up -d` con un `.env` válido
- **THEN** la API queda escuchando en el puerto configurado y `GET /health` responde 200

#### Scenario: CLI en el contenedor
- **WHEN** se ejecuta `docker compose run --rm trakt-manager sync lists/doomsday.yaml --dry-run`
- **THEN** se ejecuta el comando del CLI y el contenedor termina con el código de salida del comando

### Requirement: Configuración por entorno
Toda la configuración (credenciales de Trakt, `API_KEY`, puerto, directorio de datos, directorio de definiciones) SHALL tomarse de variables de entorno. El proyecto MUST incluir un `.env.example` con todas ellas y sin valores secretos.

#### Scenario: Configuración desde .env
- **WHEN** el usuario copia `.env.example` a `.env`, rellena sus credenciales y levanta el servicio
- **THEN** el servicio usa esos valores sin cambiar ningún fichero del proyecto

### Requirement: Datos persistentes
El token de Trakt SHALL guardarse en un volumen persistente, y las definiciones de listas SHALL montarse desde el directorio `lists/` del proyecto, de forma que editarlas no requiera reconstruir la imagen.

#### Scenario: Token tras reinicio
- **WHEN** el usuario se autentica, y después se recrea el contenedor
- **THEN** la sesión de Trakt sigue activa sin volver a autenticarse

#### Scenario: Editar una definición
- **WHEN** el usuario modifica `lists/doomsday.yaml` en el anfitrión
- **THEN** la siguiente operación dentro del contenedor usa la versión modificada sin reconstruir la imagen

### Requirement: Secretos fuera de la imagen y del repositorio
La imagen SHALL NOT contener credenciales, tokens ni el fichero `.env`, y el repositorio MUST ignorar `.env` y los ficheros de token.

#### Scenario: Imagen limpia
- **WHEN** se construye la imagen con un `.env` presente en el directorio
- **THEN** la imagen no contiene el `.env` ni ningún fichero de token

### Requirement: Ejecución sin privilegios
El proceso dentro del contenedor SHALL ejecutarse con un usuario no root y la imagen MUST declarar una comprobación de salud basada en `GET /health`.

#### Scenario: Usuario del proceso
- **WHEN** se inspecciona el proceso en ejecución dentro del contenedor
- **THEN** no se ejecuta como root

#### Scenario: Estado de salud de Docker
- **WHEN** la API está funcionando
- **THEN** `docker compose ps` muestra el servicio como `healthy`
