# Spec Delta

## MODIFIED Requirements

### Requirement: Una imagen para API y CLI
El proyecto SHALL proporcionar una única imagen Docker que, por defecto, arranca la API y la GUI web, y que también permite ejecutar cualquier comando del CLI. La imagen MUST funcionar sin compose ni `.env`, ejecutada solo con la publicación de su puerto (por ejemplo, desde la interfaz de Docker Desktop u OrbStack).

#### Scenario: Arranque del servicio
- **WHEN** se ejecuta `docker compose up -d` con un `.env` válido
- **THEN** la API queda escuchando en el puerto configurado y `GET /health` responde 200

#### Scenario: CLI en el contenedor
- **WHEN** se ejecuta `docker compose run --rm trakt-manager sync lists/doomsday.yaml --dry-run`
- **THEN** se ejecuta el comando del CLI y el contenedor termina con el código de salida del comando

#### Scenario: Arranque sin compose ni .env
- **WHEN** se ejecuta la imagen publicada desde Docker Desktop indicando solo el puerto 8000
- **THEN** el servicio arranca en modo configuración, queda `healthy` y la GUI muestra el asistente en `http://localhost:8000/`

### Requirement: Configuración por entorno
Toda la configuración (credenciales de Trakt, `API_KEY`, puerto, directorio de datos, directorio de definiciones) SHALL poder tomarse de variables de entorno. Las credenciales de Trakt y la `API_KEY` MAY configurarse también desde la GUI. El proyecto MUST incluir un `.env.example` con todas las variables y sin valores secretos.

#### Scenario: Configuración desde .env
- **WHEN** el usuario copia `.env.example` a `.env`, rellena sus credenciales y levanta el servicio
- **THEN** el servicio usa esos valores sin cambiar ningún fichero del proyecto

#### Scenario: Configuración desde la GUI
- **WHEN** el usuario arranca el contenedor sin `.env` y completa el asistente de la GUI
- **THEN** el servicio usa esos valores sin reiniciar y los conserva tras recrear el contenedor

### Requirement: Datos persistentes
El token de Trakt, la configuración guardada desde la GUI y las definiciones guardadas desde la GUI SHALL guardarse en el volumen de datos (`/data`), que la imagen declara para que persista aunque no se configure un volumen. Las definiciones de `lists/` SHALL poderse montar desde el anfitrión para editarlas sin reconstruir la imagen.

#### Scenario: Token tras reinicio
- **WHEN** el usuario se autentica, y después se recrea el contenedor
- **THEN** la sesión de Trakt sigue activa sin volver a autenticarse

#### Scenario: Editar una definición
- **WHEN** el usuario modifica `lists/doomsday.yaml` en el anfitrión
- **THEN** la siguiente operación dentro del contenedor usa la versión modificada sin reconstruir la imagen

#### Scenario: Configuración y definiciones de la GUI tras recrear
- **WHEN** el usuario configura el servicio y guarda una definición desde la GUI, y después se recrea el contenedor conservando el volumen
- **THEN** la configuración y la definición siguen disponibles
