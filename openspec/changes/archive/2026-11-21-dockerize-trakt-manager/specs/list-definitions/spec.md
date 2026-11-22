# Spec Delta

## Purpose

Define el formato de fichero (YAML o JSON) con el que se describe una lista de Trakt y sus entradas en orden, para que las listas sean datos versionables en lugar de código.

## ADDED Requirements

### Requirement: Formatos de fichero admitidos
El sistema SHALL aceptar definiciones de lista en YAML (`.yaml`, `.yml`) y JSON (`.json`) con la misma estructura.

#### Scenario: Misma definición en dos formatos
- **WHEN** se cargan una definición en YAML y su equivalente en JSON
- **THEN** ambas producen exactamente la misma lista y las mismas entradas

#### Scenario: Extensión no admitida
- **WHEN** se intenta cargar un fichero con otra extensión
- **THEN** la carga falla con un error que indica los formatos admitidos

### Requirement: Metadatos de la lista
Una definición SHALL incluir el nombre de la lista (obligatorio) y MAY incluir descripción, privacidad (`private`, `friends`, `public`; por defecto `private`), si se muestran números, si se permiten comentarios y el identificador de una lista de Trakt ya existente a la que fijarse.

#### Scenario: Valores por defecto
- **WHEN** una definición solo indica el nombre
- **THEN** la lista se trata como privada, con números visibles y sin comentarios

#### Scenario: Privacidad no válida
- **WHEN** la privacidad tiene un valor distinto de los admitidos
- **THEN** la validación falla señalando el campo y los valores permitidos

### Requirement: Entradas ordenadas
Una definición SHALL contener una secuencia ordenada de entradas; el orden de la secuencia es el orden de la lista en Trakt. Cada entrada MUST ser de un tipo: película, serie completa, temporada o episodios concretos de una temporada.

#### Scenario: Entrada de episodios concretos
- **WHEN** una entrada es de tipo episodios con temporada 2 y episodios [1, 4, 5, 6]
- **THEN** la entrada representa exactamente esos cuatro episodios en ese orden

#### Scenario: Entrada de episodios sin temporada
- **WHEN** una entrada de tipo episodios no indica temporada o la lista de episodios está vacía
- **THEN** la validación falla señalando la entrada

### Requirement: Identificación del título
Cada entrada SHALL identificar su película o serie mediante un texto de búsqueda con año opcional, o mediante un identificador explícito (Trakt, slug, IMDb o TMDB). Si hay identificador explícito, MUST prevalecer sobre la búsqueda.

#### Scenario: Entrada sin forma de identificarla
- **WHEN** una entrada no tiene ni texto de búsqueda ni identificador
- **THEN** la validación falla señalando la entrada

#### Scenario: Identificador explícito
- **WHEN** una entrada tiene texto de búsqueda e identificador IMDb
- **THEN** se usa el identificador IMDb y no se realiza búsqueda

### Requirement: Notas, bloques y extras
Cada entrada MAY incluir un título visible, una nota para Trakt, un bloque (agrupación) y una marca de extra. Las entradas marcadas como extra MUST excluirse salvo que se pida incluirlas.

#### Scenario: Extras excluidos por defecto
- **WHEN** se procesa una definición con entradas extra sin pedir incluirlas
- **THEN** las entradas extra no forman parte del resultado

#### Scenario: Extras incluidos
- **WHEN** se procesa la misma definición pidiendo incluir extras
- **THEN** las entradas extra aparecen en su posición dentro del orden

### Requirement: Validación con errores localizados
El sistema SHALL validar una definición completa antes de contactar con Trakt y MUST informar de todos los errores encontrados indicando la entrada (posición) y el campo de cada uno.

#### Scenario: Varios errores
- **WHEN** una definición tiene errores en las entradas 3 y 7
- **THEN** la validación informa de ambos errores con su posición y campo, y no se llama a Trakt

### Requirement: Definición de ejemplo incluida
El proyecto SHALL incluir la ruta cronológica hacia *Vengadores: Doomsday* como definición, con las mismas entradas, episodios, notas, bloques y extras que el script original.

#### Scenario: Ruta Doomsday migrada
- **WHEN** se valida la definición incluida de la ruta Doomsday
- **THEN** es válida y contiene 17 entradas principales y 4 extras en el mismo orden que el script original
