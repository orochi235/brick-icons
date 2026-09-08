"""Indexing the census's kept renders, in place."""
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from brick_icons import db

index_census = importlib.import_module("index-census-renders")

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
       '<path d="M0 0h10v10H0z"/></svg>')


@pytest.fixture
def tree(tmp_path):
    kept = tmp_path / "out" / "census-naive" / "renders" / "naive"
    kept.mkdir(parents=True)
    for pid in ("3001", "3004", "nosuchpart"):
        (kept / f"{pid}.svg").write_text(SVG)
    conn = db.connect(tmp_path / "corpus.db")
    for pid in ("3001", "3004"):
        conn.execute("INSERT INTO parts (id, title, printed, obsolete) "
                     "VALUES (?, 'Brick', 0, 0)", (pid,))
    conn.commit()
    yield tmp_path, conn
    conn.close()


def test_it_indexes_under_the_census_source(tree):
    root, conn = tree
    assert index_census.index(conn, root=root, limit=10) == 2
    rows = conn.execute("SELECT part_id, source FROM renders").fetchall()
    assert {(r["part_id"], r["source"]) for r in rows} == {
        ("3001", "silhouette-naive"), ("3004", "silhouette-naive")}


def test_it_leaves_the_svg_where_the_census_put_it(tree):
    root, conn = tree
    index_census.index(conn, root=root, limit=10)
    assert not (root / "renders" / "silhouette-naive").exists()
    assert (root / "out" / "census-naive" / "renders" / "naive" / "3001.svg").is_file()


def test_the_recorded_path_points_at_the_census_file(tree):
    root, conn = tree
    index_census.index(conn, root=root, limit=10)
    path = conn.execute("SELECT path FROM renders WHERE part_id='3001'").fetchone()[0]
    assert path == "out/census-naive/renders/naive/3001.svg"


def test_it_skips_ids_that_are_not_parts(tree):
    root, conn = tree
    index_census.index(conn, root=root, limit=10)
    assert conn.execute(
        "SELECT count(*) FROM renders WHERE part_id='nosuchpart'"
    ).fetchone()[0] == 0


def test_the_limit_caps_the_work(tree):
    root, conn = tree
    assert index_census.index(conn, root=root, limit=1) == 1


def test_it_skips_what_is_already_indexed(tree):
    root, conn = tree
    index_census.index(conn, root=root, limit=10)
    assert index_census.index(conn, root=root, limit=10) == 0


def test_a_missing_kept_directory_is_an_error_not_a_zero(tree):
    # A wrong --root and a finished backfill must not look identical.
    _, conn = tree
    with pytest.raises(FileNotFoundError):
        index_census.index(conn, root=tree[0] / "nowhere", limit=10)


def test_one_unreadable_svg_does_not_abandon_the_rest(tree):
    root, conn = tree
    (root / "out" / "census-naive" / "renders" / "naive" / "3001.svg").write_text("")
    assert index_census.index(conn, root=root, limit=10) == 1
