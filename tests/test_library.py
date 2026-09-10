import json
import pathlib

import numpy as np

from brick_icons import library


def test_parse_header_and_accept():
    hdr = "0 Brick  2 x  4\n0 !LDRAW_ORG Part UPDATE 2004-03\n"
    info = library.parse_header(hdr.splitlines())
    assert info.title == "Brick  2 x  4"
    assert info.category == "Brick"
    assert info.org == "Part"
    assert library.is_sortable(info) is True


def test_reject_sticker_shortcut_moved_pattern():
    def info(t, org="Part"):
        return library.parse_header([f"0 {t}", f"0 !LDRAW_ORG {org} UPDATE x"])
    assert library.is_sortable(info("Sticker 1 x 1")) is False
    assert library.is_sortable(info("Brick 2 x 4", org="Shortcut")) is False
    assert library.is_sortable(info("Moved to 3001")) is False
    assert library.is_sortable(info("Tile 2 x 2 with Pattern")) is False
    assert library.is_sortable(info("~Brick 2 x 4")) is False
    assert library.is_sortable(info("Minifig Head")) is False


def test_select_parts_finds_known_ids():
    from brick_icons import library
    ids = set(library.select_parts("vendor/ldraw", limit=None))
    assert "3001" in ids and "3020" in ids and "3040b" in ids
    assert all(not i.endswith(".dat") for i in ids)
    assert len(ids) > 200


def test_render_library_small(tmp_path):
    from brick_icons import library
    manifest = library.render_library(
        out_dir=str(tmp_path), ldraw_dir="vendor/ldraw",
        limit=3, workers=1, shade_style="flat3")
    assert (tmp_path / "manifest.json").exists()
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert len(data) == 3
    ok = [r for r in data if r["status"] == "ok"]
    assert ok, "expected at least one successful render"
    r = ok[0]
    assert r["width_mm"] > 0 and r["height_mm"] > 0 and r["category"]
    svg = tmp_path / r["category"] / f'{r["id"]}.svg'
    assert svg.exists() and svg.read_text().startswith("<svg")


def test_declared_pose_reads_the_preview_meta(ldraw_dir):
    m = library.declared_pose(ldraw_dir / "parts" / "87544dq0.dat")
    assert m is not None
    assert np.allclose(m, [[-1, 0, 0], [0, 1, 0], [0, 0, -1]])


def test_declared_pose_is_none_when_nothing_is_declared(ldraw_dir):
    assert library.declared_pose(ldraw_dir / "parts" / "3001.dat") is None
    # The part that motivated the camera work declares nothing, so honoring
    # the library leaves it exactly as it was.
    assert library.declared_pose(ldraw_dir / "parts" / "14769ptk.dat") is None


def test_declared_pose_survives_a_missing_file(tmp_path):
    assert library.declared_pose(tmp_path / "nope.dat") is None


def test_pose_matrix_refuses_a_reflection():
    # A mirror would flip the winding of every face in the part and render
    # inside-out with no error anywhere, so it is refused rather than folded in.
    assert library.pose_matrix("16 0 0 0 -1 0 0 0 1 0 0 0 1") is None
    assert library.pose_matrix("16 0 0 0 1 0 0 0 1") is None
    assert library.pose_matrix("16 0 0 0 x y z 0 1 0 0 0 1") is None


def test_every_declared_pose_in_the_library_is_a_proper_rotation(ldraw_dir):
    """The library's own declarations, read the way the renderer reads them.

    `lab.partindex` scans the same meta while indexing and stores the argument
    verbatim in corpus.db, so the two are cross-checked here: if they ever
    disagree, the db's copy would pose a part differently from a fresh read of
    its own file.
    """
    import subprocess

    from brick_icons.lab import partindex

    # grep rather than partindex.build: the index walks all 24,591 files and
    # takes minutes, and every declaring file is found here in under a second.
    hit = subprocess.run(["grep", "-rl", "!PREVIEW", str(ldraw_dir / "parts")],
                         capture_output=True, text=True)
    files = [pathlib.Path(f) for f in hit.stdout.split() if f.endswith(".dat")]
    assert len(files) > 300

    for path in files:
        from_file = library.declared_pose(path)
        assert from_file is not None, path.name
        from_index = library.pose_matrix(partindex._header(path)[1])
        assert np.allclose(from_index, from_file), path.name
        assert np.isclose(np.linalg.det(from_file), 1.0), path.name
        # Quarter turns only: every entry is a signed permutation matrix.
        assert np.allclose(np.sort(np.abs(from_file).ravel()),
                           [0, 0, 0, 0, 0, 0, 1, 1, 1]), path.name
