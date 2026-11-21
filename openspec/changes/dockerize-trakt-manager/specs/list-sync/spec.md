# Spec Delta

## Purpose

Convierte una definición de lista en una lista real en Trakt: resuelve cada entrada a elementos de Trakt y crea o actualiza la lista del usuario para que coincida con la definición, en el mismo orden.

## ADDED Requirements

### Requirement: Resolución de entradas
El sistema SHALL resolver cada entrada a uno o varios elementos de Trakt. En búsquedas por texto MUST preferir la coincidencia de año exacto, después una diferencia de un año, y en último caso el primer resultado.

#### Scenario: Coincidencia por año
- **WHEN** una búsqueda devuelve varios resultados y uno coincide con el año indicado
- **THEN** se elige el resultado de ese año

#### Scenario: Episodios concretos
- **WHEN** una entrada pide los episodios 8 y 9 de la temporada 1 de una serie
- **THEN** se resuelven exactamente esos dos episodios de esa serie

### Requirement: Informe de resolución
El sistema SHALL generar un informe con lo que resolvió cada entrada (título, año e identificador de Trakt) y con las entradas o episodios no encontrados. Los elementos no encontrados MUST NOT interrumpir la resolución del resto.

#### Scenario: Episodio aún no publicado
- **WHEN** un episodio pedido no existe todavía en Trakt
- **THEN** el informe lo marca como no encontrado y el resto de entradas se procesan

### Requirement: Previsualización sin cambios
El sistema SHALL ofrecer un modo de previsualización que resuelve las entradas y muestra el informe y los cambios que se aplicarían, sin modificar la cuenta de Trakt.

#### Scenario: Previsualización
- **WHEN** se previsualiza una definición
- **THEN** se obtiene el informe y la lista de altas, bajas y reordenaciones previstas, y no se crea ni modifica ninguna lista

### Requirement: Cada elemento se añade una vez
El sistema SHALL añadir a la lista cada elemento resuelto exactamente una vez, con su propia nota, aunque varias entradas compartan la misma nota o bloque.

#### Scenario: Películas con la misma nota
- **WHEN** cinco películas de la definición tienen la nota "1. Inicio del Multiverso | Película completa"
- **THEN** la lista contiene las cinco películas distintas, cada una una sola vez

### Requirement: Orden de la lista
La lista resultante en Trakt SHALL tener sus elementos en el orden de la definición (intercalando películas y episodios) y MUST configurarse para ordenarse por posición manual ascendente.

#### Scenario: Orden intercalado
- **WHEN** la definición tiene episodios de WandaVision, después Shang-Chi y después episodios de Falcon y el Soldado de Invierno
- **THEN** en Trakt aparecen en ese mismo orden

### Requirement: Sincronización idempotente
Si ya existe la lista de la definición (por su identificador de Trakt si lo indica, o si no por nombre exacto), el sistema SHALL actualizarla en lugar de crear otra: añadir lo que falta, quitar lo que sobra, reordenar y actualizar metadatos. Si no existe, MUST crearla.

#### Scenario: Primera sincronización
- **WHEN** se sincroniza una definición cuya lista no existe
- **THEN** se crea la lista con todos los elementos resueltos

#### Scenario: Repetir sin cambios
- **WHEN** se sincroniza dos veces seguidas la misma definición
- **THEN** la segunda vez no se añade, quita ni duplica ningún elemento

#### Scenario: Lista fijada por identificador
- **WHEN** la definición indica el identificador de una lista que se renombró en Trakt
- **THEN** se actualiza esa lista y no se crea otra

#### Scenario: Definición modificada
- **WHEN** se elimina una entrada de la definición y se vuelve a sincronizar
- **THEN** sus elementos desaparecen de la lista y el resto mantiene el orden de la definición

### Requirement: Límites de Trakt
El sistema SHALL respetar la limitación de peticiones de Trakt: ante una respuesta 429 MUST esperar el tiempo indicado y reintentar, y ante errores de red reintentar un número acotado de veces antes de fallar.

#### Scenario: Limitación temporal
- **WHEN** Trakt responde 429 con una cabecera `Retry-After`
- **THEN** el sistema espera ese tiempo y reintenta la petición

### Requirement: Consulta de listas del usuario
El sistema SHALL permitir obtener las listas del usuario autenticado (nombre, identificador, privacidad y número de elementos) y los elementos de una lista concreta.

#### Scenario: Listar listas
- **WHEN** un usuario autenticado consulta sus listas
- **THEN** obtiene todas sus listas con nombre, identificador, privacidad y número de elementos
