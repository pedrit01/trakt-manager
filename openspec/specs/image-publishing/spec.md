# image-publishing Specification

## Purpose
Publica automáticamente la imagen de trakt-manager en un registro público para que se pueda ejecutar desde Docker Desktop u OrbStack sin clonar el repositorio ni construir nada.

## Requirements

### Requirement: Publicación automática en GHCR
Un flujo de integración continua SHALL construir la imagen de ejecución y publicarla en `ghcr.io/pedrit01/trakt-manager` cada vez que se actualiza la rama `main` y cada vez que se crea una etiqueta de versión `v*`.

#### Scenario: Cambio en main
- **WHEN** se hace push a `main`
- **THEN** se publica la imagen con la etiqueta `latest` y con la etiqueta del commit (`sha-<corto>`)

#### Scenario: Versión etiquetada
- **WHEN** se crea la etiqueta `v1.2.0`
- **THEN** se publica la imagen con las etiquetas `1.2.0` y `1.2`

### Requirement: Multiarquitectura
La imagen publicada SHALL estar disponible para `linux/amd64` y `linux/arm64`, de modo que funcione en Macs con Apple Silicon y en equipos x86.

#### Scenario: Mac con Apple Silicon
- **WHEN** se descarga `ghcr.io/pedrit01/trakt-manager:latest` en un Mac con Apple Silicon
- **THEN** se obtiene la variante `arm64` sin emulación

### Requirement: Solo se publica lo que pasa los tests
El flujo SHALL ejecutar los tests antes de publicar, y MUST NOT publicar ninguna imagen si fallan. En las pull requests MUST construir la imagen y ejecutar los tests sin publicar.

#### Scenario: Tests fallidos
- **WHEN** un push a `main` rompe un test
- **THEN** el flujo falla y la etiqueta `latest` sigue apuntando a la imagen anterior

#### Scenario: Pull request
- **WHEN** se abre una pull request
- **THEN** se construye la imagen y se ejecutan los tests, pero no se publica nada

### Requirement: Imagen identificable
La imagen publicada SHALL llevar las etiquetas OCI estándar de origen (repositorio), versión y descripción, para que Docker Desktop y GHCR muestren de dónde viene.

#### Scenario: Metadatos visibles
- **WHEN** se inspecciona la imagen publicada
- **THEN** sus etiquetas `org.opencontainers.image.source` y `org.opencontainers.image.version` indican el repositorio y la versión
