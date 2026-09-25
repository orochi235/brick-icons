"""The review log: what a displaced render leaves behind, and what a verdict
does to it."""
import json
import sqlite3

import pytest

from brick_icons import db, goldens, review

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180">'
       '<path d="M0 0h10" stroke="black" stroke-width="4"/></svg>')
SVG2 = SVG.replace("h10", "h20")


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "corpus.db")
    c.execute("INSERT INTO parts (id, title, printed, obsolete) "
              "VALUES ('3001', 'Brick', 0, 0)")
    c.commit()
    yield c
    c.close()


def _draw(root, tree, part, text, source="occt"):
    svg = root / tree / "renders" / source / f"{part}.svg"
    svg.parent.mkdir(parents=True, exist_ok=True)
    svg.write_text(text)
    return svg


def test_the_id_names_the_slot_the_part_and_the_after_sha():
    sha = goldens.sha256(SVG2.encode())
    assert review.entry_id("occt", "3001", sha) == f"occt/3001/{sha[:12]}"


def test_fold_takes_the_latest_diff_and_verdict(tmp_path):
    log = tmp_path / "review.jsonl"
    review.append(log, {"kind": "replaced", "id": "occt/3001/abc", "at": "t1",
                        "part": "3001", "source": "occt", "run_id": 1,
                        "by": "slot-occt", "before": {"path": "a", "sha256": "1"},
                        "after": {"path": "b", "sha256": "abc"}})
    review.append(log, {"kind": "diff", "id": "occt/3001/abc", "at": "t2",
                        "components": 9, "pixels": 100, "width": 900})
    review.append(log, {"kind": "diff", "id": "occt/3001/abc", "at": "t3",
                        "components": 3, "pixels": 40, "width": 900})
    review.append(log, {"kind": "judged", "id": "occt/3001/abc", "at": "t4",
                        "verdict": "better", "note": "closer", "by": "lab",
                        "defects": ["d1"]})
    log.write_text(log.read_text() + '{"torn": ')
    folded = review.fold(review.load(log))
    entry = folded["occt/3001/abc"]
    assert entry["diff"] == {"components": 3, "pixels": 40, "width": 900,
                             "at": "t3"}
    assert entry["judged"]["verdict"] == "better"
    assert entry["judged"]["defects"] == ["d1"]
    assert entry["before"]["sha256"] == "1"


def test_a_diff_or_verdict_for_an_unknown_entry_is_dropped(tmp_path):
    log = tmp_path / "review.jsonl"
    review.append(log, {"kind": "diff", "id": "occt/9/x", "at": "t",
                        "components": 1, "pixels": 1, "width": 900})
    assert review.fold(review.load(log)) == {}


def test_a_displacement_is_logged_and_the_before_kept(conn, tmp_path):
    first = _draw(tmp_path, "out/slot-occt-a", "3001", SVG)
    db.record_render(conn, "3001", "occt", first, root=tmp_path, run_id=1)
    second = _draw(tmp_path, "out/slot-occt-b", "3001", SVG2)
    db.record_render(conn, "3001", "occt", second, root=tmp_path, run_id=2)

    lines = review.load(tmp_path / review.DEFAULT_PATH)
    assert [l["kind"] for l in lines] == ["replaced"]
    line = lines[0]
    sha1, sha2 = goldens.sha256(SVG.encode()), goldens.sha256(SVG2.encode())
    assert line["id"] == f"occt/3001/{sha2[:12]}"
    assert line["by"] == "slot-occt-b"
    assert line["before"]["path"] == "out/slot-occt-a/renders/occt/3001.svg"
    assert line["before"]["sha256"] == sha1
    assert line["before"]["run_id"] == 1
    assert line["after"] == {"path": "out/slot-occt-b/renders/occt/3001.svg",
                             "sha256": sha2}
    kept = tmp_path / line["before"]["kept"]
    assert kept == tmp_path / "store-queue" / "before" / "occt" / f"3001.{sha1[:8]}.svg"
    assert kept.read_text() == SVG

    row = conn.execute("SELECT * FROM review").fetchone()
    assert row["id"] == line["id"]
    assert row["part_id"] == "3001" and row["source"] == "occt"
    assert row["before_sha"] == sha1 and row["after_sha"] == sha2
    assert row["verdict"] is None and row["diff_components"] is None


def test_a_first_render_and_a_retake_of_the_same_sha_log_nothing(conn, tmp_path):
    svg = _draw(tmp_path, "out/slot-occt-a", "3001", SVG)
    db.record_render(conn, "3001", "occt", svg, root=tmp_path)
    db.record_render(conn, "3001", "occt", svg, root=tmp_path)
    same = _draw(tmp_path, "out/slot-occt-b", "3001", SVG)
    db.record_render(conn, "3001", "occt", same, root=tmp_path)
    assert not (tmp_path / review.DEFAULT_PATH).exists()
    assert conn.execute("SELECT count(*) FROM review").fetchone()[0] == 0


def test_review_log_none_is_how_a_rebuild_stays_silent(conn, tmp_path):
    db.record_render(conn, "3001", "occt",
                     _draw(tmp_path, "out/a", "3001", SVG), root=tmp_path,
                     review_log=None)
    db.record_render(conn, "3001", "occt",
                     _draw(tmp_path, "out/b", "3001", SVG2), root=tmp_path,
                     review_log=None)
    assert not (tmp_path / review.DEFAULT_PATH).exists()


def test_an_in_place_overwrite_still_has_its_before(conn, tmp_path):
    """`store_render` writes over renders/<slot>/<part>.svg, which is the one
    path where the displaced drawing would otherwise be gone for good."""
    made = tmp_path / "made.svg"
    made.write_text(SVG)
    db.store_render(conn, "3001", "occt", made, root=tmp_path)
    made.write_text(SVG2)
    db.store_render(conn, "3001", "occt", made, root=tmp_path)
    line = review.load(tmp_path / review.DEFAULT_PATH)[0]
    assert line["by"] == "lab"
    assert line["before"]["path"] == "renders/occt/3001.svg"
    assert (tmp_path / line["before"]["kept"]).read_text() == SVG
    assert (tmp_path / "renders" / "occt" / "3001.svg").read_text() == SVG2


def test_replay_folds_the_log_into_a_fresh_table(conn, tmp_path):
    db.record_render(conn, "3001", "occt",
                     _draw(tmp_path, "out/a", "3001", SVG), root=tmp_path)
    db.record_render(conn, "3001", "occt",
                     _draw(tmp_path, "out/b", "3001", SVG2), root=tmp_path)
    log = tmp_path / review.DEFAULT_PATH
    entry_id = review.load(log)[0]["id"]
    review.record_diff(conn, log, entry_id, components=4, pixels=50, width=900)
    review.record_judged(conn, log, entry_id, "regression", "lost the rim",
                         by="lab", defects=[])

    fresh = db.connect(tmp_path / "fresh.db")
    assert review.replay(fresh, log) == 1
    row = fresh.execute("SELECT * FROM review").fetchone()
    assert row["diff_components"] == 4
    assert row["verdict"] == "regression" and row["note"] == "lost the rim"
    assert json.loads(row["judged_defects"]) == []


def test_a_verdict_must_be_one_of_the_four(conn, tmp_path):
    with pytest.raises(ValueError):
        review.record_judged(conn, tmp_path / "r.jsonl", "occt/3001/x",
                             "meh", "", by="lab", defects=[])


def test_by_is_the_round_or_the_store():
    assert review.by_from_path("out/slot-occt-refresh/renders/occt/1.svg") == "slot-occt-refresh"
    assert review.by_from_path("renders/occt/1.svg") == "store"


def test_fold_clears_a_verdict_an_unjudged_line_takes_back():
    lines = [
        {"kind": "replaced", "id": "s/p/a", "at": "1",
         "part": "p", "source": "s",
         "before": {"path": "b.svg", "sha256": "bb"},
         "after": {"path": "a.svg", "sha256": "aa"}},
        {"kind": "judged", "id": "s/p/a", "at": "2", "verdict": "fixed",
         "note": "", "by": "lab", "defects": ["d1"]},
        {"kind": "unjudged", "id": "s/p/a", "at": "3", "by": "lab"},
    ]
    assert review.fold(lines)["s/p/a"]["judged"] is None


def test_fold_takes_a_verdict_cast_again_after_an_undo():
    lines = [
        {"kind": "replaced", "id": "s/p/a", "at": "1",
         "part": "p", "source": "s",
         "before": {"path": "b.svg", "sha256": "bb"},
         "after": {"path": "a.svg", "sha256": "aa"}},
        {"kind": "judged", "id": "s/p/a", "at": "2", "verdict": "fixed",
         "note": "", "by": "lab", "defects": []},
        {"kind": "unjudged", "id": "s/p/a", "at": "3", "by": "lab"},
        {"kind": "judged", "id": "s/p/a", "at": "4", "verdict": "regression",
         "note": "no", "by": "lab", "defects": []},
    ]
    assert review.fold(lines)["s/p/a"]["judged"]["verdict"] == "regression"


def test_a_judged_line_carries_what_the_verdict_overwrote(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(review.SCHEMA)
    log = tmp_path / "review.jsonl"
    restore = {"d1": {"status": "open", "checked": {"occt": "old"},
                      "notes": "first"}}
    review.record_judged(conn, log, "s/p/a", "fixed", "", by="lab",
                         defects=["d1"], restore=restore)
    line = json.loads(log.read_text().splitlines()[-1])
    assert line["restore"] == restore


def test_record_unjudged_clears_the_row_and_appends_a_line(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(review.SCHEMA)
    conn.execute("INSERT INTO review (id, part_id, source, at, before_path, "
                 "before_sha, after_path, after_sha, verdict, note, "
                 "judged_at, judged_by, judged_defects) VALUES "
                 "('s/p/a', 'p', 's', '1', 'b.svg', 'bb', 'a.svg', 'aa', "
                 "'fixed', 'n', '2', 'lab', '[\"d1\"]')")
    conn.commit()
    review.record_unjudged(conn, log := tmp_path / "review.jsonl", "s/p/a",
                           by="lab")
    row = conn.execute("SELECT * FROM review WHERE id = 's/p/a'").fetchone()
    assert (row["verdict"], row["note"], row["judged_at"], row["judged_by"],
            row["judged_defects"]) == (None, None, None, None, None)
    assert json.loads(log.read_text().splitlines()[-1])["kind"] == "unjudged"


def test_a_panel_measured_under_other_settings_is_measured_again(tmp_path):
    """The threshold moved once and every entry already measured kept its
    old panel and its old count, which is the bug the move was fixing."""
    from brick_icons.lab import diff as lab_diff
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(review.SCHEMA)
    before = tmp_path / "before.svg"
    after = tmp_path / "after.svg"
    before.write_text(SVG)
    after.write_text(SVG2)
    log = tmp_path / "review.jsonl"
    conn.execute(
        "INSERT INTO review (id, part_id, source, at, before_path, before_sha, "
        "after_path, after_sha) VALUES ('s/p/a', 'p', 's', '1', 'before.svg', "
        "'bb', 'after.svg', 'aa')")
    conn.commit()
    row = conn.execute("SELECT * FROM review").fetchone()
    panel = review.measure(conn, tmp_path, log, tmp_path / "cache", row)
    first = panel.read_bytes()
    assert conn.execute("SELECT diff_panel FROM review").fetchone()[0] == \
        review.panel_signature()

    conn.execute("UPDATE review SET diff_panel = 'thr=64 min=12 w=900'")
    conn.commit()
    row = conn.execute("SELECT * FROM review").fetchone()
    review.measure(conn, tmp_path, log, tmp_path / "cache", row)
    assert conn.execute("SELECT diff_panel FROM review").fetchone()[0] == \
        review.panel_signature()
    assert lab_diff.PANEL_THRESHOLD == 8   # the signature tracks the settings
    assert first == panel.read_bytes()


def test_a_panel_measured_under_the_same_settings_is_left_alone(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(review.SCHEMA)
    (tmp_path / "before.svg").write_text(SVG)
    (tmp_path / "after.svg").write_text(SVG2)
    log = tmp_path / "review.jsonl"
    conn.execute(
        "INSERT INTO review (id, part_id, source, at, before_path, before_sha, "
        "after_path, after_sha) VALUES ('s/p/a', 'p', 's', '1', 'before.svg', "
        "'bb', 'after.svg', 'aa')")
    conn.commit()
    row = conn.execute("SELECT * FROM review").fetchone()
    panel = review.measure(conn, tmp_path, log, tmp_path / "cache", row)
    stamped = panel.stat().st_mtime_ns
    row = conn.execute("SELECT * FROM review").fetchone()
    review.measure(conn, tmp_path, log, tmp_path / "cache", row)
    assert panel.stat().st_mtime_ns == stamped


def test_measure_unmeasured_takes_the_panels_painted_under_old_settings(tmp_path):
    """Otherwise a threshold change reaches only the entries someone opens."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(review.SCHEMA)
    (tmp_path / "before.svg").write_text(SVG)
    (tmp_path / "after.svg").write_text(SVG2)
    conn.execute(
        "INSERT INTO review (id, part_id, source, at, before_path, before_sha, "
        "after_path, after_sha, diff_components, diff_pixels, diff_panel) "
        "VALUES ('s/p/a', 'p', 's', '1', 'before.svg', 'bb', 'after.svg', "
        "'aa', 1, 462, 'thr=64 min=12 w=900')")
    conn.commit()
    measured, failed = review.measure_unmeasured(
        conn, tmp_path, tmp_path / "review.jsonl", tmp_path / "cache")
    assert (measured, failed) == (1, [])
    row = conn.execute("SELECT * FROM review").fetchone()
    assert row["diff_panel"] == review.panel_signature()
    assert row["diff_components"] != 1 or row["diff_pixels"] != 462

    # Nothing left to do on a second pass.
    assert review.measure_unmeasured(
        conn, tmp_path, tmp_path / "review.jsonl", tmp_path / "cache") == (0, [])


def test_a_dropped_entry_does_not_come_back_when_the_log_is_folded(conn, tmp_path):
    """The log is append-only and `fold` rebuilds the table from it, so
    deleting a row alone is undone by the next rebuild. A drop is a line."""
    log = tmp_path / "review.jsonl"
    _draw(tmp_path, "out/a", "3001", SVG)
    _draw(tmp_path, ".", "3001", SVG2)
    line = review.record_replaced(
        conn, tmp_path, log, part="3001", source="occt",
        before={"path": "out/a/renders/occt/3001.svg",
                "sha256": goldens.sha256(SVG), "made_at": None, "run_id": 1},
        after={"path": "renders/occt/3001.svg", "sha256": goldens.sha256(SVG2)},
        run_id=2, by="test")
    eid = line["id"]
    assert eid in review.fold(review.load(log))
    review.record_dropped(conn, log, eid, by="test")
    assert eid not in review.fold(review.load(log))
    assert conn.execute("SELECT COUNT(*) n FROM review WHERE id = ?",
                        (eid,)).fetchone()["n"] == 0


def test_a_redraw_with_the_same_pixels_logs_nothing(conn, tmp_path):
    plain = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
             '<path d="M0 0L8 0L8 8Z" fill="#b40000"/></svg>')
    marked = plain.replace('<path d="M0 0L8 0L8 8Z"', '<path d="M0 0L8 0L8 8Z" class="deco"')
    db.record_render(conn, "3001", "occt", _draw(tmp_path, "out/a", "3001", plain),
                     root=tmp_path)
    db.record_render(conn, "3001", "occt", _draw(tmp_path, "out/b", "3001", marked),
                     root=tmp_path)
    assert not (tmp_path / review.DEFAULT_PATH).exists()
    row = conn.execute("SELECT path FROM renders WHERE part_id = '3001'").fetchone()
    assert row["path"] == "out/b/renders/occt/3001.svg"


def test_a_redraw_that_moves_a_pixel_is_logged(conn, tmp_path):
    plain = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
             '<path d="M0 0L8 0L8 8Z" fill="#b40000"/></svg>')
    moved = plain.replace("L8 8Z", "L4 8Z")
    db.record_render(conn, "3001", "occt", _draw(tmp_path, "out/a", "3001", plain),
                     root=tmp_path)
    db.record_render(conn, "3001", "occt", _draw(tmp_path, "out/b", "3001", moved),
                     root=tmp_path)
    assert [l["kind"] for l in review.load(tmp_path / review.DEFAULT_PATH)] == ["replaced"]
