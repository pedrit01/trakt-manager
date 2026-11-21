# Spec Delta

## Purpose

Permite configurar las credenciales de Trakt y la clave de la API desde la GUI mientras el servicio está en marcha, guardándolas en el volumen de datos, sin `.env` ni comandos y sin que el entorno pierda prioridad.

## ADDED Requirements

### Requirement: Origen y prioridad de la configuración
El sistema SHALL tomar `TRAKT_CLIENT_ID`, `TRAKT_CLIENT_SECRET` y `API_KEY` de las variables de entorno y, si no están definidas, de la configuración guardada en el volumen de datos. Un valor del entorno MUST prevalecer siempre y no se puede cambiar desde la GUI.

#### Scenario: Valor del entorno
- **WHEN** `API_KEY` está definida en el entorno y también guardada en el volumen
- **THEN** se usa la del entorno y la GUI la muestra como "definida por el entorno", sin permitir editarla

#### Scenario: Solo configuración guardada
- **WHEN** ninguna de las tres variables está en el entorno y están guardadas en el volumen
- **THEN** el sistema funciona con los valores guardados

### Requirement: Modo configuración
Si falta cualquiera de los tres valores, el servicio SHALL arrancar en modo configuración. En ese modo solo responden `/health`, la GUI y las rutas del asistente; el resto de rutas MUST responder 503 indicando que falta la configuración.

#### Scenario: Primer arranque sin configuración
- **WHEN** se arranca la imagen sin `.env` ni configuración guardada
- **THEN** el servicio arranca, `GET /health` responde 200 indicando modo configuración y la GUI muestra el asistente

#### Scenario: Ruta normal en modo configuración
- **WHEN** se llama a `GET /lists` en modo configuración
- **THEN** la API responde 503 indicando qué falta por configurar

### Requirement: Código de configuración de un solo uso
En modo configuración, el servicio SHALL generar un código aleatorio y escribirlo en sus registros al arrancar. El asistente MUST exigir ese código para guardar la configuración, y el código MUST dejar de valer en cuanto la configuración se completa.

#### Scenario: Código correcto
- **WHEN** el usuario copia el código de los registros del contenedor en el asistente y envía la configuración
- **THEN** la configuración se guarda

#### Scenario: Código incorrecto
- **WHEN** se envía la configuración con un código incorrecto
- **THEN** se responde 403 y no se guarda nada

#### Scenario: Intentos repetidos
- **WHEN** se envían 10 códigos incorrectos
- **THEN** el servicio genera un código nuevo, lo escribe en los registros y rechaza el anterior

### Requirement: Asistente inicial
El asistente SHALL pedir el Client ID y el Client Secret de Trakt, con un enlace a la página de aplicaciones de Trakt y la Redirect URI que hay que usar, y SHALL generar una `API_KEY` aleatoria. La `API_KEY` MUST mostrarse una sola vez, al terminar, con la opción de copiarla.

#### Scenario: Configuración completada
- **WHEN** el usuario completa el asistente con un código válido
- **THEN** la configuración se guarda, la `API_KEY` generada se muestra una vez y el servicio sale del modo configuración sin reiniciar

#### Scenario: Credencial de Trakt vacía
- **WHEN** el usuario deja vacío el Client ID
- **THEN** el asistente indica el campo que falta y no guarda nada

### Requirement: Cambiar la configuración después
Con la `API_KEY`, la GUI SHALL permitir sustituir las credenciales de Trakt guardadas y regenerar la `API_KEY`. Los cambios MUST aplicarse sin reiniciar el contenedor. Si cambia el Client ID, el sistema MUST cerrar la sesión de Trakt, porque el token pertenece a la aplicación anterior.

#### Scenario: Regenerar la API_KEY
- **WHEN** el usuario regenera la `API_KEY` desde la GUI
- **THEN** se muestra la nueva una vez y la anterior deja de ser aceptada de inmediato

#### Scenario: Cambiar el Client ID
- **WHEN** el usuario guarda un Client ID distinto
- **THEN** la sesión de Trakt se cierra y la GUI pide volver a conectar

### Requirement: Secretos protegidos
La configuración guardada SHALL almacenarse en un fichero del directorio de datos con permisos de solo lectura y escritura para su propietario. La API MUST NOT devolver nunca el Client Secret ni la `API_KEY` completos, salvo la `API_KEY` recién generada en la misma respuesta que la crea.

#### Scenario: Consultar la configuración
- **WHEN** se consulta la configuración desde la GUI
- **THEN** se ve el Client ID, si el secreto y la clave están definidos y su origen (entorno o guardado), pero no sus valores
