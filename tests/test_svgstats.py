import hashlib
import json
import os

from brick_icons import db, svgstats

NS = 'xmlns="http://www.w3.org/2000/svg"'


def _count(body: str) -> int:
    return svgstats.painted_count(f"<svg {NS}>{body}</svg>")


def test_a_stroke_or_a_fill_is_an_object():
    assert _count('<line x1="0" y1="0" x2="1" y2="1" stroke="black"/>'
                  '<path d="M0 0L1 1Z" fill="#999"/>') == 2


def test_what_paints_nothing_is_not_an_object():
    assert _count('<line x1="0" y1="0" x2="1" y2="1"/>'          # no stroke, no area
                  '<path d="M0 0L1 1" fill="none" stroke="black" stroke-width="0"/>'
                  '<path d="M0 0L1 1Z" opacity="0"/>'
                  '<path d="M0 0L1 1Z" display="none"/>') == 0


def test_paint_is_inherited_from_a_group_and_defs_do_not_count():
    assert _count('<defs><path id="a" d="M0 0L1 1Z"/></defs>'
                  '<clipPath id="c"><path d="M0 0L1 1Z"/></clipPath>'
                  '<g fill="none" stroke="black">'
                  '<path d="M0 0L1 1"/><path d="M0 0L1 1" stroke-width="0"/></g>'
                  '<g opacity="0"><path d="M0 0L1 1Z"/></g>') == 1


def test_style_attribute_is_read():
    assert _count('<path d="M0 0L1 1" style="fill: none; stroke: none"/>') == 0


SVG = f'<svg {NS}><path d="M0 0L1 1Z" fill="#999"/></svg>'


def _tree(tmp_path, text=SVG):
    svg = tmp_path / "renders" / "occt" / "3001.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text(text)
    return svg


def test_import_records_the_drawings_size_and_objects(tmp_path):
    svg = _tree(tmp_path)
    shard = tmp_path / "occt-s0.jsonl"
    shard.write_text(json.dumps({"engine": "occt", "part": "3001", "secs": 1.0}) + "\n")
    conn = db.connect(tmp_path / "corpus.db")
    run = db.start_run(conn, "census", {}, "abc1234")
    db.import_census_jsonl(conn, run, shard, tmp_path)
    row = conn.execute("SELECT bytes, objects, drawn_at FROM measurements").fetchone()
    assert (row["bytes"], row["objects"]) == (len(SVG), 1)
    assert row["drawn_at"]
    assert svg.stat().st_size == row["bytes"]


def test_a_drawing_redrawn_since_is_not_credited_to_the_row(tmp_path):
    svg = _tree(tmp_path)
    row = {"engine": "occt", "part": "3001"}
    logged = svg.stat().st_mtime
    assert db.drawing_stats(tmp_path, row, logged)[0] == len(SVG)
    os.utime(svg, (logged + 60, logged + 60))
    assert db.drawing_stats(tmp_path, row, logged) == (None, None, None)


def test_a_recorded_sha_decides_which_drawing_is_the_rows(tmp_path):
    _tree(tmp_path)
    mine = {"engine": "occt", "part": "3001",
            "edges": {"sha256": hashlib.sha256(SVG.encode()).hexdigest()}}
    other = {"engine": "occt", "part": "3001", "edges": {"sha256": "0" * 64}}
    assert db.drawing_stats(tmp_path, mine, 0)[1] == 1
    assert db.drawing_stats(tmp_path, other, 1e12) == (None, None, None)
