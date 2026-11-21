# cli Specification

## Purpose
Ofrece un comando `trakt-manager` para autenticarse, validar definiciones y crear, sincronizar y consultar listas de Trakt desde la terminal o dentro del contenedor.

## Requirements

### Requirement: Comandos de autenticación
El CLI SHALL ofrecer `auth login` (inicia el device flow y muestra URL y código), `auth status` y `auth logout`.

#### Scenario: Login interactivo
- **WHEN** el usuario ejecuta `trakt-manager auth login`
- **THEN** se muestran la URL de verificación y el código, y el comando termina con éxito al confirmarse en trakt.tv

### Requirement: Validar una definición
El CLI SHALL ofrecer `validate <fichero>`, que valida la definición sin contactar con Trakt.

#### Scenario: Definición válida
- **WHEN** se ejecuta `trakt-manager validate lists/doomsday.yaml` sobre una definición válida
- **THEN** el comando informa de que es válida y termina con código 0

#### Scenario: Definición inválida
- **WHEN** se ejecuta `validate` sobre una definición con errores
- **THEN** se muestran todos los errores con su posición y campo, y el comando termina con código distinto de 0

### Requirement: Sincronizar una lista
El CLI SHALL ofrecer `sync <fichero>` con las opciones `--dry-run` (previsualizar sin cambios) e `--include-extras`, y mostrar el informe de resolución y el resultado.

#### Scenario: Dry-run
- **WHEN** se ejecuta `trakt-manager sync lists/doomsday.yaml --dry-run`
- **THEN** se muestran el informe y los cambios previstos y la cuenta de Trakt no se modifica

#### Scenario: Sincronización real sin sesión
- **WHEN** se ejecuta `sync` sin `--dry-run` y no hay sesión
- **THEN** el comando indica que hay que ejecutar `auth login` y termina con código distinto de 0

### Requirement: Consultar listas
El CLI SHALL ofrecer `lists` para mostrar las listas del usuario y `show <lista>` para mostrar los elementos de una lista en orden.

#### Scenario: Mostrar listas
- **WHEN** un usuario autenticado ejecuta `trakt-manager lists`
- **THEN** se muestra una tabla con nombre, identificador, privacidad y número de elementos

### Requirement: Salida legible por máquina
Los comandos `validate`, `sync`, `lists` y `show` SHALL aceptar `--json` para emitir su resultado como JSON en la salida estándar.

#### Scenario: Salida JSON
- **WHEN** se ejecuta `trakt-manager lists --json`
- **THEN** la salida estándar contiene solo un documento JSON válido

### Requirement: Códigos de salida
El CLI SHALL terminar con código 0 si la operación tuvo éxito y con código distinto de 0 ante errores de validación, de configuración, de autenticación o de Trakt.

#### Scenario: Falta configuración
- **WHEN** se ejecuta un comando que llama a Trakt sin `TRAKT_CLIENT_ID`
- **THEN** el comando muestra el error y termina con código distinto de 0
