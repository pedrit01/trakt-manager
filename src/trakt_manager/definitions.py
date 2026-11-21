"""Formato, carga y validación de los ficheros de definición de listas.

Una definición describe una lista de Trakt como datos: sus metadatos (nombre,
privacidad...) y una secuencia ordenada de entradas. El orden de ``entries`` es
el orden que tendrá la lista en Trakt.

Ejemplo mínimo en YAML::

    name: Mi maratón
    entries:
      - type: movie
        query: Shang-Chi and the Legend of the Ten Rings
        year: 2021
      - type: episodes
        query: Loki
        season: 2
        episodes: [1, 4, 5, 6]

Las definiciones se validan por completo antes de contactar con Trakt, y se
informa de todos los problemas a la vez, cada uno con su posición y su campo.
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import ErrorDetails, PydanticCustomError

from trakt_manager.errors import DefinitionError, DefinitionIssue

# Extensiones admitidas y el formato con el que se leen.
SUPPORTED_EXTENSIONS: dict[str, Literal["yaml", "json"]] = {".yaml": "yaml", ".yml": "yaml", ".json": "json"}

# Nombre que usan los errores de pydantic para la regla propia de este módulo.
DEFINITION_RULE_ERROR = "definition_rule"


class EntryType(str, Enum):
    """Tipos de entrada que admite una definición."""

    MOVIE = "movie"
    """Una película completa."""
    SHOW = "show"
    """Una serie completa."""
    SEASON = "season"
    """Una temporada completa de una serie."""
    EPISODES = "episodes"
    """Episodios concretos de una temporada de una serie."""


class ExternalIds(BaseModel):
    """Identificadores explícitos de una película o serie.

    Si se indica alguno, prevalece sobre la búsqueda por texto. Sirven para
    fijar títulos ambiguos (por ejemplo "X-Men", que tiene varias obras).
    """

    model_config = ConfigDict(extra="forbid")

    trakt: int | None = None
    slug: str | None = None
    imdb: str | None = None
    tmdb: int | None = None

    def is_empty(self) -> bool:
        """Indica si no se ha indicado ningún identificador."""
        return all(value is None for value in (self.trakt, self.slug, self.imdb, self.tmdb))


class Entry(BaseModel):
    """Una entrada de la definición: una película, una serie, una temporada o unos episodios.

    Atributos:
        type: Tipo de entrada.
        title: Título visible (para informes y notas); si falta se usa ``query``.
        query: Texto con el que buscar el título en Trakt.
        year: Año del título; ayuda a elegir el resultado correcto en la búsqueda.
        ids: Identificadores explícitos; si se indican no se hace búsqueda.
        season: Número de temporada (obligatorio en ``season`` y ``episodes``).
        episodes: Números de episodio (obligatorio y no vacío en ``episodes``).
        block: Agrupación a la que pertenece la entrada (por ejemplo "1. Inicio del Multiverso").
        note: Nota libre sobre la entrada.
        extra: Si es ``True`` la entrada solo se incluye cuando se piden los extras.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    type: EntryType
    title: str | None = None
    query: str | None = None
    year: int | None = None
    ids: ExternalIds | None = None
    season: int | None = Field(default=None, ge=0)
    episodes: list[int] = Field(default_factory=list)
    block: str | None = None
    note: str | None = None
    extra: bool = False

    @property
    def display_title(self) -> str:
        """Nombre con el que mostrar la entrada al usuario."""
        if self.title:
            return self.title
        if self.query:
            return self.query
        if self.ids is not None and self.ids.slug:
            return self.ids.slug
        return "entrada sin título"

    @model_validator(mode="after")
    def _check_entry_rules(self) -> "Entry":
        """Comprueba las reglas que dependen de varios campos a la vez."""
        has_ids = self.ids is not None and not self.ids.is_empty()
        if not self.query and not has_ids:
            _fail("query", "indica un texto de búsqueda (query) o un identificador en ids")

        if self.type in (EntryType.SEASON, EntryType.EPISODES) and self.season is None:
            _fail("season", f"las entradas de tipo '{self.type.value}' necesitan una temporada")

        if self.type == EntryType.EPISODES:
            if not self.episodes:
                _fail("episodes", "indica al menos un número de episodio")
            if any(number < 1 for number in self.episodes):
                _fail("episodes", "los números de episodio empiezan en 1")
        elif self.episodes:
            _fail("episodes", f"las entradas de tipo '{self.type.value}' no admiten episodios")

        if self.type in (EntryType.MOVIE, EntryType.SHOW) and self.season is not None:
            _fail("season", f"las entradas de tipo '{self.type.value}' no admiten temporada")
        return self


@dataclass(frozen=True)
class PositionedEntry:
    """Una entrada junto con su posición (empezando en 1) dentro de la definición."""

    position: int
    entry: Entry


class ListDefinition(BaseModel):
    """Definición completa de una lista de Trakt.

    Atributos:
        name: Nombre de la lista en Trakt (obligatorio). Si no se indica
            ``trakt_list_id``, se usa para encontrar la lista existente.
        description: Descripción de la lista.
        privacy: ``private``, ``friends`` o ``public``.
        display_numbers: Si Trakt muestra el número de cada elemento.
        allow_comments: Si se permiten comentarios en la lista.
        trakt_list_id: Identificador de una lista ya existente a la que fijarse,
            útil si la lista se renombra en Trakt.
        entries: Entradas en el orden que tendrá la lista.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str | None = None
    privacy: Literal["private", "friends", "public"] = "private"
    display_numbers: bool = True
    allow_comments: bool = False
    trakt_list_id: int | None = None
    entries: list[Entry] = Field(min_length=1)

    def selected_entries(self, include_extras: bool) -> list[PositionedEntry]:
        """Devuelve las entradas a procesar, con su posición original.

        Args:
            include_extras: Si es ``False`` se omiten las entradas marcadas como extra.
        """
        return [
            PositionedEntry(position, entry)
            for position, entry in enumerate(self.entries, start=1)
            if include_extras or not entry.extra
        ]


class ValidationIssueOut(BaseModel):
    """Un problema de validación, en el formato que devuelven el CLI (``--json``) y la API."""

    entry_position: int | None
    field: str
    message: str


class ValidationOutcome(BaseModel):
    """Resultado de validar una definición, compartido por el CLI y la API.

    Atributos:
        valid: Si la definición es válida.
        name: Nombre de la lista (solo si es válida).
        entries: Número total de entradas (solo si es válida).
        extras: Cuántas de ellas son extras.
        errors: Problemas encontrados (vacío si es válida).
    """

    valid: bool
    name: str | None = None
    entries: int = 0
    extras: int = 0
    errors: list[ValidationIssueOut] = Field(default_factory=list)

    @classmethod
    def from_definition(cls, definition: ListDefinition) -> "ValidationOutcome":
        """Resultado para una definición válida."""
        return cls(
            valid=True,
            name=definition.name,
            entries=len(definition.entries),
            extras=sum(entry.extra for entry in definition.entries),
        )

    @classmethod
    def from_error(cls, error: DefinitionError) -> "ValidationOutcome":
        """Resultado para una definición con errores."""
        return cls(
            valid=False,
            errors=[
                ValidationIssueOut(entry_position=issue.entry_position, field=issue.field, message=issue.message)
                for issue in error.issues
            ],
        )


def load_definition_file(path: Path) -> ListDefinition:
    """Carga y valida una definición desde un fichero YAML o JSON.

    Raises:
        DefinitionError: Si la extensión no es admitida, el fichero no se puede
            leer o interpretar, o la definición no es válida.
    """
    file_format = SUPPORTED_EXTENSIONS.get(path.suffix.lower())
    if file_format is None:
        allowed = ", ".join(SUPPORTED_EXTENSIONS)
        raise DefinitionError([DefinitionIssue(None, "fichero", f"formato no admitido '{path.suffix}'; usa {allowed}")])
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise DefinitionError([DefinitionIssue(None, "fichero", f"no se puede leer {path}: {error.strerror}")]) from error
    return parse_definition_text(text, file_format)


def parse_definition_text(text: str, file_format: Literal["yaml", "json"]) -> ListDefinition:
    """Interpreta el texto de una definición y la valida.

    Raises:
        DefinitionError: Si el texto no es YAML/JSON válido o la definición no es válida.
    """
    try:
        data = json.loads(text) if file_format == "json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise DefinitionError([DefinitionIssue(None, "fichero", f"{file_format.upper()} no válido: {error}")]) from error
    return parse_definition_data(data)


def parse_definition_data(data: Any) -> ListDefinition:
    """Valida una definición ya decodificada (diccionario).

    Raises:
        DefinitionError: Con todos los problemas encontrados.
    """
    if not isinstance(data, dict):
        raise DefinitionError([DefinitionIssue(None, "fichero", "la definición debe ser un objeto con 'name' y 'entries'")])
    try:
        return ListDefinition.model_validate(data)
    except ValidationError as error:
        raise DefinitionError([_issue_from_pydantic(detail) for detail in error.errors()]) from error


def find_definition_files(directory: Path) -> dict[str, Path]:
    """Busca las definiciones de un directorio.

    Returns:
        Diccionario ``nombre -> ruta``, donde el nombre es el fichero sin extensión
        (``doomsday.yaml`` -> ``doomsday``), ordenado por nombre.
    """
    if not directory.is_dir():
        return {}
    files = [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS]
    return {path.stem: path for path in sorted(files)}


def _fail(field: str, message: str) -> None:
    """Lanza un error de validación propio indicando el campo afectado.

    Se usa ``PydanticCustomError`` con el campo en el contexto porque los errores
    de un ``model_validator`` no llevan campo en su ubicación, y el usuario
    necesita saber qué campo corregir.
    """
    raise PydanticCustomError(DEFINITION_RULE_ERROR, message, {"field": field})


def _issue_from_pydantic(detail: ErrorDetails) -> DefinitionIssue:
    """Convierte un error de pydantic en un :class:`DefinitionIssue` legible.

    La ubicación de pydantic es una tupla como ``("entries", 3, "season")``; se
    traduce a posición 4 (empezando en 1) y campo ``season``.
    """
    location = list(detail["loc"])
    entry_position: int | None = None
    if len(location) >= 2 and location[0] == "entries" and isinstance(location[1], int):
        entry_position = location[1] + 1
        location = location[2:]

    context = detail.get("ctx") or {}
    if detail["type"] == DEFINITION_RULE_ERROR:
        field = str(context["field"])
    else:
        field = ".".join(str(part) for part in location) or "entries"
    return DefinitionIssue(entry_position, field, _spanish_message(detail))


def _spanish_message(detail: ErrorDetails) -> str:
    """Traduce los errores más habituales de pydantic al español."""
    context = detail.get("ctx") or {}
    # pydantic une los valores permitidos con " or " ("'a', 'b' or 'c'"): se traduce.
    expected = str(context.get("expected", "")).replace(" or ", " o ")
    messages = {
        "missing": "campo obligatorio",
        "extra_forbidden": "campo no reconocido",
        "literal_error": f"valor no válido; valores permitidos: {expected}",
        "enum": f"valor no válido; valores permitidos: {expected}",
        "int_type": "debe ser un número entero",
        "int_parsing": "debe ser un número entero",
        "int_from_float": "debe ser un número entero",
        "string_type": "debe ser texto",
        "bool_type": "debe ser verdadero o falso",
        "bool_parsing": "debe ser verdadero o falso",
        "list_type": "debe ser una lista",
        "model_type": "debe ser un objeto",
        "greater_than_equal": f"debe ser mayor o igual que {context.get('ge', '')}",
        "too_short": "no puede estar vacío",
        "string_too_short": "no puede estar vacío",
    }
    return messages.get(detail["type"], detail["msg"])
