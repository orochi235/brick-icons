"""The declared-edge oracle: which visible declared edges a drawing leaves out."""
import numpy as np
from PIL import Image, ImageDraw

from brick_icons import edge_truth, hlr

# A 20-LDU cube: six quads and its twelve edges as type-2 lines.
_C = [(x, y, z) for x in (0, 20) for y in (0, 20) for z in (0, 20)]
_FACES = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6),
          (0, 2, 6, 4), (1, 5, 7, 3)]
_EDGES = [(a, b) for a in range(8) for b in range(a + 1, 8)
          if sum(p != q for p, q in zip(_C[a], _C[b])) == 1]


def _cube(tmp_path, extra="", name="cube"):
    # One name per variant: the loader caches a file's lines by path.
    lines = ["0 cube"]
    for f in _FACES:
        lines.append("4 16 " + "  ".join(" ".join(map(str, _C[i])) for i in f))
    for a, b in _EDGES:
        lines.append(f"2 24 {' '.join(map(str, _C[a]))}  {' '.join(map(str, _C[b]))}")
    path = tmp_path / f"{name}.dat"
    path.write_text("\n".join(lines) + "\n" + extra)
    return path


def _fit(points, width=120):
    """The CLI's fit: one uniform scale, the part centered in the canvas."""
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    P = np.asarray(points, float)
    sx, sy = P @ right, -(P @ up)
    k = (width - 20) / max(np.ptp(sx), np.ptp(sy))
    return {"right": list(right), "up": list(up), "fwd": list(fwd), "k": k,
            "kx": width / 2 - k * (sx.min() + sx.max()) / 2,
            "ky": width / 2 - k * (sy.min() + sy.max()) / 2,
            "width": width, "height": width}


def _draw(segs, fit, zoom, width=2.0):
    """Ink for these canvas-px segments, as a dark-on-white raster would give."""
    W, H = fit["width"] * zoom, fit["height"] * zoom
    img = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(img)
    for x1, y1, x2, y2, _ in segs:
        d.line([(x1 * zoom, y1 * zoom), (x2 * zoom, y2 * zoom)], fill=255,
               width=max(1, round(width * zoom)))
    return np.array(img) > 0


def test_a_cube_at_iso_shows_nine_of_its_twelve_edges(tmp_path):
    out = edge_truth.load(_cube(tmp_path), [tmp_path])
    segs = edge_truth.visible_edges(out, _fit(_C), zoom=4)
    long_runs = [s for s in segs if np.hypot(s[2] - s[0], s[3] - s[1]) > 10]
    assert len(long_runs) == 9


def test_a_drawing_with_every_edge_misses_nothing(tmp_path):
    out = edge_truth.load(_cube(tmp_path), [tmp_path])
    fit = _fit(_C)
    segs = edge_truth.visible_edges(out, fit, zoom=4)
    got = edge_truth.score(segs, _draw(segs, fit, 4), zoom=4, stroke_width=2)
    assert got["declared_len"] > 0
    assert got["missing_comps"] == 0 and got["missing_len"] == 0


def test_an_erased_edge_is_one_gap(tmp_path):
    out = edge_truth.load(_cube(tmp_path), [tmp_path])
    fit = _fit(_C)
    segs = edge_truth.visible_edges(out, fit, zoom=4)
    longest = max(segs, key=lambda s: np.hypot(s[2] - s[0], s[3] - s[1]))
    ink = _draw([s for s in segs if s is not longest], fit, 4)
    got = edge_truth.score(segs, ink, zoom=4, stroke_width=2)
    assert got["missing_comps"] == 1
    assert got["missing_len"] > 20
    assert len(got["gaps"]) == 1


def test_a_conditional_line_counts_only_where_its_condition_holds(tmp_path):
    # A world-vertical line projects screen-vertical at iso, and `right` moves
    # a point straight across the screen: both controls on one side, or one
    # on each.
    right, _, _ = hlr.view_basis(30.0, 45.0)
    a, b = np.array([100.0, 0, 0]), np.array([100.0, 20, 0])
    same = f"5 24 100 0 0 100 20 0  {' '.join(map(str, a + 5 * right))}  " \
           f"{' '.join(map(str, b + 5 * right))}\n"
    split = f"5 24 100 0 0 100 20 0  {' '.join(map(str, a + 5 * right))}  " \
            f"{' '.join(map(str, b - 5 * right))}\n"
    fit = _fit(_C + [tuple(a), tuple(b)])
    held = edge_truth.visible_edges(
        edge_truth.load(_cube(tmp_path, same), [tmp_path]), fit, zoom=4)
    failed = edge_truth.visible_edges(
        edge_truth.load(_cube(tmp_path, split, "split"), [tmp_path]), fit, zoom=4)
    assert sum(s[4] == "sil" for s in held) == 1
    assert sum(s[4] == "sil" for s in failed) == 0


def test_a_part_with_nothing_declared_scores_nothing(tmp_path):
    path = tmp_path / "bare.dat"
    path.write_text("0 bare\n3 16 0 0 0 20 0 0 0 20 0\n")
    fit = _fit([(0, 0, 0), (20, 0, 0), (0, 20, 0)])
    segs = edge_truth.visible_edges(edge_truth.load(path, [tmp_path]), fit, 4)
    got = edge_truth.score(segs, np.zeros((120 * 4, 120 * 4), bool), 4, 2)
    assert got == {"declared_len": 0.0, "missing_len": 0.0,
                   "missing_comps": 0, "gaps": []}


def test_scores_are_filed_by_drawing(tmp_path):
    from brick_icons import db

    conn = db.connect(tmp_path / "corpus.db")
    row = {"part": "3001", "source": "white-occt", "declared_len": 40.0,
           "missing_len": 8.0, "missing_comps": 1, "gaps": [{"len": 8.0}]}
    assert db.record_edge_scores(conn, [
        {**row, "sha256": "old"}, {**row, "sha256": "new", "missing_comps": 0},
        {**row, "sha256": None, "error": "ProcessDied"}]) == 2
    got = dict(conn.execute("SELECT sha256, missing_comps FROM edge_scores"
                            ).fetchall())
    assert got == {"old": 1, "new": 0}


def test_a_census_row_files_its_edge_score_under_the_census_slot(tmp_path):
    import json

    from brick_icons import db

    conn = db.connect(tmp_path / "corpus.db")
    run = db.start_run(conn, "census", {}, "abc")
    tree = tmp_path / "census-white-occt"
    tree.mkdir()
    log = tree / "rows.jsonl"
    log.write_text(json.dumps({
        "part": "3001", "engine": "occt", "missing": [], "missing_px": 0,
        "edges": {"sha256": "cafe", "declared_len": 50.0, "missing_len": 0.0,
                  "missing_comps": 0, "gaps": []}}) + "\n")
    db.import_census_jsonl(conn, run, log, census_dir=tree)
    got = conn.execute("SELECT part_id, source, sha256 FROM edge_scores").fetchall()
    assert [tuple(r) for r in got] == [("3001", "white-occt", "cafe")]


def test_a_row_naming_no_part_is_filed_under_every_part_with_that_drawing(tmp_path):
    """The first fleet run wrote rows with no part id. The drawing's sha finds
    it again -- for every part whose stored drawing has those bytes."""
    import importlib.util
    from pathlib import Path

    from brick_icons import db

    spec = importlib.util.spec_from_file_location(
        "sde", Path(__file__).resolve().parent.parent
        / "scripts" / "score-declared-edges.py")
    sde = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sde)

    conn = db.connect(tmp_path / "corpus.db")
    for pid, sha in (("3001", "same"), ("3001old", "same"), ("3002", "other")):
        conn.execute("INSERT INTO parts (id, title, printed, obsolete, status) "
                     "VALUES (?, 'Brick', 0, 0, 'unreviewed')", (pid,))
        conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                     "path, sha256) VALUES (?, 'white-occt', 'k', 't', 'p', ?)",
                     (pid, sha))
    rows = sde.attach_parts(conn, [
        {"source": "white-occt", "sha256": "same", "missing_comps": 1},
        {"source": "white-occt", "sha256": "gone", "missing_comps": 1},
        {"part": "3002", "source": "white-occt", "sha256": "other"}])
    assert sorted(r["part"] for r in rows) == ["3001", "3001old", "3002"]
