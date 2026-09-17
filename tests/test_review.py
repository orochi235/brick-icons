"""The review log: what a displaced render leaves behind, and what a verdict
does to it."""
import json

import pytest

from brick_icons import db, goldens, review

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180">'
       '<path d="M0 0h10"/></svg>')
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
