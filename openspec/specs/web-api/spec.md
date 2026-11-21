# web-api Specification

## Purpose
Expone por HTTP las mismas operaciones que el CLI (autenticación con Trakt, validación, previsualización, sincronización y consulta de listas) para administrar listas desde otro equipo.

## Requirements

### Requirement: Acceso protegido con clave de API
Todas las rutas de la API, salvo la de salud, la GUI y las del asistente de configuración, SHALL exigir la `API_KEY` vigente (del entorno o guardada) en la cabecera `X-API-Key`. Si falta configuración, el servicio MUST arrancar en modo configuración en lugar de negarse a arrancar.

#### Scenario: Petición sin clave
- **WHEN** se llama a una ruta protegida sin cabecera `X-API-Key` o con una clave incorrecta
- **THEN** la API responde 401 y no realiza ninguna operación

#### Scenario: Arranque sin clave configurada
- **WHEN** se inicia el servicio sin `API_KEY` en el entorno ni guardada
- **THEN** el servicio arranca en modo configuración, registra que falta configuración junto con el código de configuración, y las rutas protegidas responden 503

#### Scenario: Clave regenerada
- **WHEN** se regenera la `API_KEY` y se llama a una ruta protegida con la anterior
- **THEN** la API responde 401

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
La API SHALL listar las definiciones disponibles (`GET /definitions`): las del directorio de listas configurado y las guardadas desde la GUI, indicando el origen de cada una. También SHALL devolver una por su nombre (`GET /definitions/{nombre}`). Si una definición guardada y una incluida tienen el mismo nombre, MUST prevalecer la guardada.

#### Scenario: Listar definiciones
- **WHEN** el directorio contiene `doomsday.yaml` y se llama a `GET /definitions`
- **THEN** la respuesta incluye `doomsday` con su nombre de lista, su número de entradas y su origen

#### Scenario: Definición guardada con el mismo nombre
- **WHEN** existe `doomsday` incluida en la imagen y el usuario guarda otra `doomsday` desde la GUI
- **THEN** `GET /definitions/doomsday` devuelve la guardada

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

### Requirement: Guardar y borrar definiciones
La API SHALL permitir guardar una definición (`PUT /definitions/{nombre}`, cuerpo YAML o JSON) y borrar una guardada (`DELETE /definitions/{nombre}`). El nombre MUST contener solo letras minúsculas, números y guiones, y la definición MUST ser válida para guardarse.

#### Scenario: Guardar una definición válida
- **WHEN** se llama a `PUT /definitions/maraton` con una definición válida
- **THEN** se guarda en el directorio de datos, la respuesta es 200 y aparece en `GET /definitions` como guardada

#### Scenario: Definición inválida
- **WHEN** se llama a `PUT /definitions/maraton` con una definición inválida
- **THEN** la API responde 422 con los errores y no guarda nada

#### Scenario: Nombre no permitido
- **WHEN** se llama a `PUT /definitions/..%2Fsecreto`
- **THEN** la API responde 422 y no escribe ningún fichero

#### Scenario: Borrar una definición incluida
- **WHEN** se llama a `DELETE /definitions/doomsday` y `doomsday` solo existe incluida en la imagen
- **THEN** la API responde 409 indicando que solo se pueden borrar las definiciones guardadas

### Requirement: Rutas de configuración
La API SHALL ofrecer:
- `GET /setup/status`, sin clave: indica si está en modo configuración y qué falta.
- `POST /setup`, sin clave pero con el código de configuración: guarda la configuración inicial y devuelve la `API_KEY` generada.
- `GET /settings` y `PUT /settings`, con clave: consultan y cambian la configuración guardada.
- `POST /settings/api-key`, con clave: regenera la `API_KEY`.

#### Scenario: Setup ya completado
- **WHEN** se llama a `POST /setup` estando ya configurado el servicio
- **THEN** la API responde 409 y no cambia nada
