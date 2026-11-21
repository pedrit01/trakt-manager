# Spec Delta

## Purpose

Expone por HTTP las mismas operaciones que el CLI (autenticación con Trakt, validación, previsualización, sincronización y consulta de listas) para administrar listas desde otro equipo.

## ADDED Requirements

### Requirement: Acceso protegido con clave de API
Todas las rutas de la API, salvo la de salud, SHALL exigir la clave configurada en `API_KEY` enviada en la cabecera `X-API-Key`. El servicio MUST negarse a arrancar si `API_KEY` no está configurada.

#### Scenario: Petición sin clave
- **WHEN** se llama a una ruta protegida sin cabecera `X-API-Key` o con una clave incorrecta
- **THEN** la API responde 401 y no realiza ninguna operación

#### Scenario: Arranque sin clave configurada
- **WHEN** se inicia el servicio sin `API_KEY`
- **THEN** el servicio no arranca y registra un error que nombra la variable

### Requirement: Comprobación de salud
La API SHALL ofrecer `GET /health`, sin autenticación, que indica si el servicio funciona y si hay sesión de Trakt, sin revelar tokens ni secretos.

#### Scenario: Salud
- **WHEN** se llama a `GET /health`
- **THEN** responde 200 con el estado del servicio y si hay sesión de Trakt activa

### Requirement: Autenticación con Trakt remota
La API SHALL permitir iniciar el device flow (`POST /auth/device`, que devuelve URL y código de usuario), consultar el estado (`GET /auth/status`) y cerrar la sesión (`DELETE /auth`). La espera de confirmación MUST continuar en segundo plano sin bloquear la petición.

#### Scenario: Iniciar autorización
- **WHEN** se llama a `POST /auth/device`
- **THEN** la respuesta incluye la URL de verificación, el código de usuario y la caducidad, y el servicio queda esperando la confirmación

#### Scenario: Autorización completada
- **WHEN** el usuario confirma el código en trakt.tv y después se llama a `GET /auth/status`
- **THEN** la respuesta indica sesión activa con el usuario de Trakt

### Requirement: Definiciones disponibles
La API SHALL listar las definiciones del directorio de listas configurado (`GET /definitions`) y devolver una por su nombre (`GET /definitions/{nombre}`).

#### Scenario: Listar definiciones
- **WHEN** el directorio contiene `doomsday.yaml` y se llama a `GET /definitions`
- **THEN** la respuesta incluye `doomsday` con su nombre de lista y número de entradas

### Requirement: Validar, previsualizar y sincronizar
La API SHALL ofrecer `POST /validate`, `POST /sync?dry_run=true|false&include_extras=true|false` con una definición en el cuerpo (JSON o YAML) y `POST /definitions/{nombre}/sync` con los mismos parámetros para una definición del directorio. Las respuestas MUST seguir el mismo contenido que la salida `--json` del CLI.

#### Scenario: Definición inválida por la API
- **WHEN** se envía a `POST /validate` una definición con errores
- **THEN** la API responde 422 con la lista de errores, su posición y su campo

#### Scenario: Previsualización remota
- **WHEN** se llama a `POST /definitions/doomsday/sync?dry_run=true`
- **THEN** la respuesta incluye el informe de resolución y los cambios previstos, y la cuenta de Trakt no cambia

#### Scenario: Sincronización sin sesión
- **WHEN** se llama a sincronizar sin dry-run y no hay sesión de Trakt
- **THEN** la API responde 409 indicando que hay que autenticarse

### Requirement: Consulta de listas remota
La API SHALL ofrecer `GET /lists` con las listas del usuario y `GET /lists/{id}` con los elementos de una lista en orden.

#### Scenario: Listas remotas
- **WHEN** con sesión activa se llama a `GET /lists`
- **THEN** la respuesta incluye las listas con nombre, identificador, privacidad y número de elementos

### Requirement: Una sincronización a la vez
La API SHALL impedir dos sincronizaciones reales simultáneas de la misma lista.

#### Scenario: Sincronización concurrente
- **WHEN** llega una sincronización real de una lista mientras otra de la misma lista está en curso
- **THEN** la API responde 409 sin modificar la lista
