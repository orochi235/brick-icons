import pytest

from brick_icons.lab import partindex


_CACHE = {}


@pytest.fixture
def index(ldraw_dir):
    # `ldraw_dir` is function-scoped, so the fixture is too; the index is
    # built once and reused because building it walks 24k files.
    if "index" not in _CACHE:
        _CACHE["index"] = partindex.build(ldraw_dir)
    return _CACHE["index"]


def test_indexes_the_whole_parts_directory(index):
    assert len(index) > 20000


def test_carries_the_description_line(index):
    assert "Brick  2 x  4" in index["3001"]["description"]


def test_flags_printed_parts_from_the_description_not_the_id(index):
    assert index["3040bp08"]["printed"] is True
    assert index["3001"]["printed"] is False


def test_search_matches_an_id_prefix(index):
    hits = [h["id"] for h in partindex.search(index, "3941")]
    assert "3941" in hits


def test_search_matches_words_in_the_description(index):
    hits = [h["id"] for h in partindex.search(index, "brick 2 x 4")]
    assert "3001" in hits


def test_search_ranks_an_exact_id_first(index):
    assert partindex.search(index, "3001")[0]["id"] == "3001"


def test_search_is_capped(index):
    assert len(partindex.search(index, "brick", limit=25)) == 25


def test_empty_query_returns_nothing(index):
    assert partindex.search(index, "  ") == []
