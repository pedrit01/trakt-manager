# Spec Delta

## Purpose

Permite que la herramienta actúe sobre la cuenta de Trakt del usuario obteniendo, guardando y renovando un token OAuth2 mediante el device flow, sin servidor web local.

## ADDED Requirements

### Requirement: Credenciales de aplicación por configuración
El sistema SHALL leer el Client ID y el Client Secret de la aplicación de Trakt desde la configuración (variables de entorno `TRAKT_CLIENT_ID` y `TRAKT_CLIENT_SECRET`). Las operaciones que solo leen datos públicos de Trakt MUST funcionar únicamente con el Client ID.

#### Scenario: Falta el Client ID
- **WHEN** se lanza cualquier operación que llame a Trakt sin `TRAKT_CLIENT_ID` configurado
- **THEN** la operación falla antes de contactar con Trakt con un error que nombra la variable que falta

#### Scenario: Operación de solo lectura sin secreto
- **WHEN** se ejecuta una previsualización (dry-run) con `TRAKT_CLIENT_ID` pero sin `TRAKT_CLIENT_SECRET`
- **THEN** la operación se completa sin pedir autenticación

### Requirement: Autorización mediante device flow
El sistema SHALL autorizar al usuario con el device flow de Trakt: solicitar un código, mostrar la URL de verificación y el código de usuario, y esperar la confirmación respetando el intervalo de sondeo indicado por Trakt.

#### Scenario: Autorización correcta
- **WHEN** el usuario inicia la autorización y confirma el código en trakt.tv antes de que caduque
- **THEN** el sistema obtiene un token de acceso y lo guarda

#### Scenario: Código caducado
- **WHEN** el código de dispositivo caduca sin que el usuario lo confirme
- **THEN** el sistema informa de que el código ha expirado y no guarda ningún token

#### Scenario: Trakt pide ir más despacio
- **WHEN** Trakt responde con limitación de peticiones (429) durante el sondeo
- **THEN** el sistema aumenta el intervalo de sondeo y continúa esperando

### Requirement: Persistencia del token
El sistema SHALL guardar el token (acceso, renovación y caducidad) en un fichero dentro del directorio de datos configurado, de modo que sobreviva a reinicios del contenedor, y MUST reutilizarlo en lugar de pedir una nueva autorización.

#### Scenario: Token reutilizado
- **WHEN** existe un token válido guardado y se lanza una operación que requiere autenticación
- **THEN** el sistema usa ese token sin iniciar el device flow

#### Scenario: Sin token guardado
- **WHEN** se lanza una operación que requiere autenticación y no hay token guardado
- **THEN** la operación falla indicando que primero hay que autenticarse

### Requirement: Renovación automática del token
El sistema SHALL renovar el token con el `refresh_token` cuando el token de acceso esté caducado o Trakt lo rechace como no autorizado, y MUST guardar el token renovado.

#### Scenario: Token caducado con renovación válida
- **WHEN** el token de acceso guardado ha caducado y el de renovación es válido
- **THEN** el sistema obtiene un token nuevo, lo guarda y completa la operación

#### Scenario: Renovación rechazada
- **WHEN** Trakt rechaza el `refresh_token`
- **THEN** la operación falla indicando que hay que volver a autenticarse

### Requirement: Estado y cierre de sesión
El sistema SHALL permitir consultar si hay una sesión activa (y con qué usuario de Trakt) y eliminar el token guardado.

#### Scenario: Consultar estado con sesión
- **WHEN** se consulta el estado de autenticación con un token válido
- **THEN** el sistema muestra el nombre de usuario de Trakt asociado

#### Scenario: Cerrar sesión
- **WHEN** el usuario cierra la sesión
- **THEN** el token se revoca en Trakt cuando sea posible y el fichero del token se elimina
