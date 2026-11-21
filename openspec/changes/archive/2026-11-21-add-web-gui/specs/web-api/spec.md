# Spec Delta

## MODIFIED Requirements

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

### Requirement: Definiciones disponibles
La API SHALL listar las definiciones disponibles (`GET /definitions`): las del directorio de listas configurado y las guardadas desde la GUI, indicando el origen de cada una. También SHALL devolver una por su nombre (`GET /definitions/{nombre}`). Si una definición guardada y una incluida tienen el mismo nombre, MUST prevalecer la guardada.

#### Scenario: Listar definiciones
- **WHEN** el directorio contiene `doomsday.yaml` y se llama a `GET /definitions`
- **THEN** la respuesta incluye `doomsday` con su nombre de lista, su número de entradas y su origen

#### Scenario: Definición guardada con el mismo nombre
- **WHEN** existe `doomsday` incluida en la imagen y el usuario guarda otra `doomsday` desde la GUI
- **THEN** `GET /definitions/doomsday` devuelve la guardada

## ADDED Requirements

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
