"""What the footprint counts, and what it refuses to guess at."""
from __future__ import annotations

import os

from brick_icons import db
from brick_icons.lab import sizes


def _corpus(tmp_path, rows=(("silhouette-occt", "out/census/renders/occt/3001.svg", 4096),)):
    conn = db.connect(tmp_path / "corpus.db")
    conn.execute("INSERT INTO parts (id, title, category, printed, obsolete, "
                 "status) VALUES ('3001', 'Brick 2 x 4', 'Brick', 0, 0, 'good')")
    for i, (source, path, size) in enumerate(rows):
        made = tmp_path / path
        made.parent.mkdir(parents=True, exist_ok=True)
        made.write_bytes(b"x" * size)
        conn.execute(
            "INSERT INTO renders (part_id, source, config_key, made_at, path, "
            "sha256) VALUES ('3001', ?, ?, ?, ?, 'deadbeef')",
            (source, f"c{i}", db.now(), path))
    conn.commit()
    return conn


def test_a_slot_carries_its_renders_and_its_bakes(tmp_path):
    conn = _corpus(tmp_path)
    bake = tmp_path / "out" / "thumbs" / "silhouette-occt" / "128"
    bake.mkdir(parents=True)
    (bake / "3001.png").write_bytes(b"y" * 8192)

    slots = sizes.footprint(conn, tmp_path)["slots"]
    assert [s["source"] for s in slots] == ["silhouette-occt"]
    assert slots[0]["renders"] >= 4096
    assert slots[0]["bakes"] >= 8192
    assert slots[0]["total"] == slots[0]["renders"] + slots[0]["bakes"]


def test_a_slot_with_nothing_on_disk_is_not_a_row(tmp_path):
    """`db.SOURCES` names ten slots and this corpus has filled one. Drawing
    the other nine as zeroes is nine rows of noise."""
    conn = _corpus(tmp_path)
    assert len(sizes.footprint(conn, tmp_path)["slots"]) == 1


def test_slots_come_back_biggest_first(tmp_path):
    conn = _corpus(tmp_path, rows=(
        ("silhouette-naive", "out/census-naive/renders/naive/3001.svg", 4096),
        ("silhouette-occt", "out/census/renders/occt/3001.svg", 65536)))
    assert [s["source"] for s in sizes.footprint(conn, tmp_path)["slots"]] \
        == ["silhouette-occt", "silhouette-naive"]


def test_a_render_row_whose_file_went_away_is_skipped_not_fatal(tmp_path):
    """A census tree can be deleted without its rows being dropped, and a
    footprint that raises there tells you nothing about the rest."""
    conn = _corpus(tmp_path)
    (tmp_path / "out/census/renders/occt/3001.svg").unlink()
    assert sizes.footprint(conn, tmp_path)["slots"] == []


def test_renders_are_summed_from_the_database_not_the_directory(tmp_path):
    """The database names what the wall can reach. A file beside it that no
    row mentions -- a half-fetched tree, an abandoned pass -- is not the
    slot's cost."""
    conn = _corpus(tmp_path)
    stray = tmp_path / "out/census/renders/occt/9999.svg"
    stray.write_bytes(b"z" * 1_000_000)
    slot = sizes.footprint(conn, tmp_path)["slots"][0]
    assert slot["renders"] < 1_000_000


def test_sizes_are_blocks_rather_than_bytes(tmp_path):
    """A 32px thumbnail is mostly block overhead: counting apparent bytes put
    the bakes at half what `du` says, and two cells measured differently
    cannot be compared."""
    conn = _corpus(tmp_path, rows=())
    tiny = tmp_path / "out" / "thumbs" / "silhouette-occt" / "32"
    tiny.mkdir(parents=True)
    (tiny / "3001.png").write_bytes(b"q")
    walked = sizes.dir_size(tmp_path / "out" / "thumbs")
    assert walked == os.stat(tiny / "3001.png").st_blocks * 512
    assert walked > 1


def test_a_missing_directory_is_zero_rather_than_an_error(tmp_path):
    assert sizes.dir_size(tmp_path / "nothing-here") == 0


def test_tiles_name_every_bucket_the_dashboard_draws(tmp_path):
    conn = _corpus(tmp_path)
    tiles = sizes.footprint(conn, tmp_path)["tiles"]
    assert set(tiles) == {"out", "bakes", "lab_cache", "git", "renders",
                          "library", "corpus_db"}
