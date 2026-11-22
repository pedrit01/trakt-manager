"""Tests de la resolución de entradas contra Trakt."""

from trakt_manager.definitions import parse_definition_data
from trakt_manager.resolver import EntryResolver, build_item_note, choose_search_result


def definition_with(*entries: dict):
    """Definición mínima con las entradas indicadas."""
    return parse_definition_data({"name": "Prueba", "entries": list(entries)})


def test_search_prefers_exact_year_then_one_year_off_then_first() -> None:
    """La búsqueda elige año exacto, si no ±1 año, y si no el primer resultado."""
    results = [{"movie": {"title": "A", "year": 2009}}, {"movie": {"title": "B", "year": 2000}}, {"movie": {"title": "C", "year": 2001}}]
    assert choose_search_result(results, "movie", 2000)["title"] == "B"
    assert choose_search_result(results, "movie", 2002)["title"] == "C"
    assert choose_search_result(results, "movie", 1980)["title"] == "A"
    assert choose_search_result([], "movie", 2000) is None


def test_resolves_movie_by_year_among_several_results(trakt_client) -> None:
    """Entre varias películas "X-Men" se elige la del año indicado."""
    report = EntryResolver(trakt_client).resolve(definition_with({"type": "movie", "query": "X-Men", "year": 2000}))
    assert [item.trakt_id for item in report.items] == [4]


def test_explicit_ids_skip_the_search(trakt_client, fake_trakt) -> None:
    """Con un id de TMDB no se hace búsqueda por texto."""
    report = EntryResolver(trakt_client).resolve(definition_with({"type": "movie", "query": "X", "ids": {"tmdb": 36657}}))
    assert [item.trakt_id for item in report.items] == [4]
    assert not any(path == "/search/movie" for _, path in fake_trakt.requests)


def test_resolves_exact_episodes_in_order(trakt_client) -> None:
    """Una entrada de episodios se resuelve exactamente a esos episodios, en orden."""
    report = EntryResolver(trakt_client).resolve(
        definition_with({"type": "episodes", "query": "WandaVision", "season": 1, "episodes": [8, 9], "block": "1. Inicio"})
    )
    assert [(item.kind, item.trakt_id) for item in report.items] == [("episode", 7108), ("episode", 7109)]
    assert report.items[0].notes == "WandaVision S01E08 | 1. Inicio"


def test_missing_episode_is_reported_without_stopping(trakt_client) -> None:
    """Un episodio que Trakt aún no tiene se anota y el resto se procesa."""
    report = EntryResolver(trakt_client).resolve(
        definition_with(
            {"type": "episodes", "query": "VisionQuest", "season": 1, "episodes": [1, 7]},
            {"type": "movie", "query": "Spider-Man: No Way Home", "year": 2021},
        )
    )
    assert [unresolved.label for unresolved in report.unresolved] == ["VisionQuest S01E07"]
    assert [item.trakt_id for item in report.items] == [9101, 2]


def test_unknown_title_is_reported(trakt_client) -> None:
    """Un título inexistente aparece como no encontrado con su posición."""
    report = EntryResolver(trakt_client).resolve(definition_with({"type": "movie", "query": "Película inventada"}))
    assert report.items == []
    assert (report.unresolved[0].position, report.unresolved[0].label) == (1, "Película inventada")


def test_resolves_whole_season_and_show(trakt_client) -> None:
    """Las temporadas y series completas se resuelven a un solo elemento."""
    report = EntryResolver(trakt_client).resolve(
        definition_with({"type": "season", "query": "Loki", "season": 2}, {"type": "show", "query": "WandaVision"})
    )
    assert [(item.kind, item.trakt_id) for item in report.items] == [("season", 802), ("show", 7)]


def test_movie_note_keeps_original_format() -> None:
    """La nota de una película es "<bloque> | <nota>", como en el script original."""
    entry = definition_with({"type": "movie", "query": "Dune", "block": "1. Inicio", "note": "Película completa"}).entries[0]
    assert build_item_note(entry) == "1. Inicio | Película completa"
