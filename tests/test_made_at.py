"""`renders.made_at` is when the drawing was made, and a rebuild keeps it."""
import json
import os
from datetime import datetime

from brick_icons import db, requests

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180">'
       '<path d="M 10 10 L 20 20" stroke="black"/></svg>')

#: When the census drew 3001, as its row says; the file itself was fetched
#: later and carries the fetch time.
DRAWN = "2026-01-02T03:04:05+00:00"
#: When the store's 3004 was drawn, as the file's own mtime says.
STORED = "2026-01-03T00:00:00+00:00"
#: A redraw of 3001 asked for after the drawing the census holds.
ASKED = "2026-01-05T00:00:00+00:00"


def _epoch(stamp: str) -> float:
    return datetime.fromisoformat(stamp).timestamp()


def _corpus(tmp_path):
    parts = tmp_path / "ldraw" / "parts"
    parts.mkdir(parents=True)
    (parts / "3001.dat").write_text("0 Brick  2 x  4\n")
    (parts / "3004.dat").write_text("0 Brick  1 x  2\n")

    tree = tmp_path / "out" / "census-store-occt"
    (tree / "renders" / "occt").mkdir(parents=True)
    (tree / db.SOURCE_MARKER).write_text("occt\n")
    (tree / "renders" / "occt" / "3001.svg").write_text(SVG)
    (tree / "occt-r0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
        {"part": "3001", "engine": "occt", "secs": 2.0,
         "at": "2026-01-01T00:00:00+00:00"},
        {"part": "3001", "engine": "occt", "secs": 2.0, "at": DRAWN},
        # A later attempt that failed drew nothing: the file is DRAWN's.
        {"part": "3001", "engine": "occt", "error": "TimeoutError",
         "at": "2026-01-09T00:00:00+00:00"},
    ]))

    store = tmp_path / "renders" / "naive"
    store.mkdir(parents=True)
    (store / "3004.svg").write_text(SVG)
    os.utime(store / "3004.svg", (_epoch(STORED), _epoch(STORED)))
    return tmp_path / "ldraw", tree


def _made(path):
    conn = db.connect(path)
    try:
        return {(r["part_id"], r["source"]): r["made_at"] for r in
                conn.execute("SELECT part_id, source, made_at FROM renders")}
    finally:
        conn.close()


def test_a_rebuild_keeps_each_render_s_original_time(tmp_path):
    lib, tree = _corpus(tmp_path)
    out = tmp_path / "corpus.db"
    want = {("3001", "occt"): DRAWN, ("3004", "naive"): STORED}
    db.rebuild(out, lib, root=tmp_path, census_dirs=[tree])
    assert _made(out) == want
    db.rebuild(out, lib, root=tmp_path, census_dirs=[tree])
    assert _made(out) == want


def test_a_request_stays_pending_across_a_rebuild(tmp_path):
    lib, tree = _corpus(tmp_path)
    out = tmp_path / "corpus.db"
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt", at=ASKED)
    for _ in range(2):
        db.rebuild(out, lib, root=tmp_path, census_dirs=[tree])
        conn = db.connect(out)
        try:
            assert requests.pending(conn, "occt", log) == ["3001"]
        finally:
            conn.close()


def test_storing_a_drawing_keeps_its_time_for_the_next_rebuild(tmp_path):
    # A landed tree's file was written at fetch time; its row says when it
    # was drawn, and the store copy has to carry that into every rebuild.
    lib, tree = _corpus(tmp_path)
    out = tmp_path / "corpus.db"
    db.rebuild(out, lib, root=tmp_path, census_dirs=[])
    conn = db.connect(out)
    stated = db.stated_times(tree)
    db.store_render(conn, "3001", "occt", tree / "renders" / "occt" / "3001.svg",
                    root=tmp_path, made_at=stated[("occt", "3001")])
    conn.close()
    assert _made(out)[("3001", "occt")] == DRAWN
    db.rebuild(out, lib, root=tmp_path, census_dirs=[])
    assert _made(out)[("3001", "occt")] == DRAWN


def test_stated_times_skip_rows_that_drew_nothing(tmp_path):
    tree = tmp_path / "store-tree"
    tree.mkdir()
    (tree / "store.jsonl.occt").write_text("".join(json.dumps(r) + "\n" for r in [
        {"source": "occt", "part": "3001", "state": "stored", "at": DRAWN},
        {"source": "occt", "part": "3001", "state": "present",
         "at": "2026-02-01T00:00:00+00:00"},
        {"source": "occt", "part": "3004", "state": "stored"},
    ]) + '{"torn')
    assert db.stated_times(tree) == {("occt", "3001"): DRAWN}
