# web-gui Specification

## Purpose
Interfaz web, servida por el propio contenedor, que permite hacer desde el navegador todo lo que hace el CLI y gestionar las definiciones de listas sin usar la terminal ni editar ficheros.

## Requirements

### Requirement: GUI servida por el servicio
El servicio SHALL servir la GUI en la ruta raíz (`/`) del mismo puerto que la API, sin recursos de terceros (CDN, fuentes externas). La GUI MUST funcionar en las versiones actuales de Chrome, Firefox y Safari, también en pantallas de móvil.

#### Scenario: Abrir la GUI
- **WHEN** el usuario abre `http://<equipo>:<puerto>/` en el navegador
- **THEN** se muestra la GUI y el navegador no hace peticiones a dominios externos

### Requirement: Acceso a la GUI con la clave de API
Fuera del modo configuración, la GUI SHALL pedir la `API_KEY` antes de mostrar ningún dato y MUST enviarla en cada llamada a la API. El usuario MAY elegir que el navegador la recuerde; si no lo elige, se olvida al cerrar la pestaña.

#### Scenario: Clave correcta
- **WHEN** el usuario introduce la `API_KEY` correcta
- **THEN** la GUI muestra el panel principal

#### Scenario: Clave incorrecta
- **WHEN** el usuario introduce una clave incorrecta
- **THEN** la GUI indica que la clave no es válida y no muestra datos

#### Scenario: Salir
- **WHEN** el usuario pulsa "Salir"
- **THEN** la GUI olvida la clave guardada y vuelve a pedirla

### Requirement: Sesión de Trakt desde la GUI
La GUI SHALL mostrar el estado de la sesión de Trakt (sin sesión, pendiente, conectada con el usuario, caducada o error). También SHALL permitir iniciarla mostrando la URL y el código que el usuario confirma en trakt.tv, y cerrarla.

#### Scenario: Conectar con Trakt
- **WHEN** el usuario pulsa "Conectar con Trakt"
- **THEN** la GUI muestra la URL de verificación y el código, y al confirmarlo en trakt.tv pasa sola a "Conectado como <usuario>" sin recargar la página

#### Scenario: Código caducado
- **WHEN** el código caduca sin confirmarse
- **THEN** la GUI indica que ha caducado y ofrece volver a intentarlo

#### Scenario: Desconectar
- **WHEN** el usuario pulsa "Desconectar" y lo confirma
- **THEN** la sesión de Trakt se cierra y la GUI muestra "Sin sesión"

### Requirement: Gestión de definiciones
La GUI SHALL listar todas las definiciones disponibles indicando su origen (incluida en la imagen o montada, o bien guardada desde la GUI), si son válidas y su número de entradas. Las definiciones guardadas MUST poderse crear (pegando texto o subiendo un fichero YAML/JSON), descargar y borrar desde la GUI; las incluidas o montadas solo se pueden ver y descargar.

#### Scenario: Subir una definición
- **WHEN** el usuario sube `maraton.yaml` válido
- **THEN** la definición queda guardada, aparece en la lista como "guardada" y sigue disponible tras reiniciar el contenedor

#### Scenario: Definición inválida al guardar
- **WHEN** el usuario intenta guardar una definición con errores
- **THEN** la GUI muestra cada error con su posición y campo y no la guarda

#### Scenario: Borrar una definición guardada
- **WHEN** el usuario borra una definición guardada y lo confirma
- **THEN** desaparece de la lista; las listas ya creadas en Trakt no se modifican

#### Scenario: Definición incluida no borrable
- **WHEN** el usuario ve una definición incluida en la imagen
- **THEN** la GUI no ofrece borrarla

### Requirement: Validar una definición desde la GUI
La GUI SHALL permitir validar una definición pegada, subida o ya disponible, sin contactar con Trakt, y mostrar todos los errores con su posición y campo.

#### Scenario: Validación con errores
- **WHEN** el usuario valida una definición con errores en las entradas 3 y 7
- **THEN** la GUI muestra los dos errores con su posición y campo

### Requirement: Previsualizar y sincronizar desde la GUI
Para cualquier definición disponible, la GUI SHALL permitir previsualizar y sincronizar, con la opción de incluir extras. Antes de una sincronización real MUST mostrar los cambios previstos y pedir confirmación. Con el resultado, la GUI MUST mostrar el informe de resolución (título, año e id de cada entrada, y los no encontrados), los cambios y los avisos.

#### Scenario: Previsualizar
- **WHEN** el usuario pulsa "Previsualizar" en `doomsday`
- **THEN** la GUI muestra qué encontró para cada entrada, lo no encontrado y los cambios previstos, sin modificar la cuenta

#### Scenario: Sincronizar con confirmación
- **WHEN** el usuario pulsa "Sincronizar" y confirma los cambios mostrados
- **THEN** la lista se crea o actualiza en Trakt y la GUI muestra el resultado y los avisos

#### Scenario: Sincronizar sin sesión
- **WHEN** el usuario intenta sincronizar sin sesión de Trakt
- **THEN** la GUI indica que primero hay que conectar con Trakt y ofrece hacerlo

#### Scenario: Sincronización ya en curso
- **WHEN** la API responde que ya hay otra sincronización de esa lista en curso
- **THEN** la GUI lo indica y no reintenta automáticamente

### Requirement: Consultar listas desde la GUI
La GUI SHALL mostrar las listas de la cuenta de Trakt (nombre, privacidad, número de elementos) y, al elegir una, sus elementos en orden con su tipo y nota.

#### Scenario: Ver una lista
- **WHEN** el usuario abre una de sus listas
- **THEN** la GUI muestra sus elementos numerados en el orden de Trakt

### Requirement: Errores comprensibles
La GUI SHALL mostrar los errores de la API (sin sesión, Trakt no disponible, configuración incompleta, etc.) como mensajes legibles en español, sin perder lo que el usuario estaba haciendo.

#### Scenario: Trakt no disponible
- **WHEN** la API responde 502 durante una previsualización
- **THEN** la GUI muestra que Trakt no está disponible y permite reintentar
