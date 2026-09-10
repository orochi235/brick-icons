"""The live ingest watch: what it takes, and when it lets go."""
import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from brick_icons import db

watch_mod = importlib.import_module("ingest-watch")

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
       '<path d="M0 0h10v10H0z"/></svg>')
WIDER = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
         '<path d="M0 0h20v20H0z"/><path d="M4 4h2v2H4z"/></svg>')


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A slot fill's tree, with 3001 already in the slot from an older one."""
    monkeypatch.setattr(watch_mod, "ROOT", tmp_path)
    old = tmp_path / "out" / "slot-occt" / "renders" / "occt"
    old.mkdir(parents=True)
    (old / "3001.svg").write_text(SVG)
    new = tmp_path / "out" / "store-restale-occt" / "renders" / "occt"
    new.mkdir(parents=True)
    (new / "3001.svg").write_text(WIDER)
    (new / "3004.svg").write_text(SVG)

    conn = db.connect(tmp_path / "corpus.db")
    for pid in ("3001", "3004"):
        conn.execute("INSERT INTO parts (id, title, printed, obsolete) "
                     "VALUES (?, 'Brick', 0, 0)", (pid,))
    db.record_render(conn, "3001", "occt", old / "3001.svg", root=tmp_path)
    conn.commit()
    yield tmp_path, conn
    conn.close()


def _row(conn, pid):
    return conn.execute(
        "SELECT path, sha256 FROM renders WHERE part_id = ? AND source = 'occt'",
        (pid,)).fetchone()


def test_the_default_pass_leaves_a_part_already_in_the_slot(tree):
    root, conn = tree
    took, redrew = watch_mod._take_renders(
        conn, root / "out" / "store-restale-occt", "occt", "occt", 1)
    assert (took, redrew) == (1, 0)
    assert _row(conn, "3001")["path"].endswith("out/slot-occt/renders/occt/3001.svg")


def test_overwrite_replaces_the_row_with_the_refresh(tree):
    root, conn = tree
    before = _row(conn, "3001")["sha256"]
    took, redrew = watch_mod._take_renders(
        conn, root / "out" / "store-restale-occt", "occt", "occt", 1,
        overwrite=True)
    assert (took, redrew) == (1, 1)
    after = _row(conn, "3001")
    assert after["path"].endswith("out/store-restale-occt/renders/occt/3001.svg")
    assert after["sha256"] != before


def test_overwrite_keeps_one_row_per_part(tree):
    root, conn = tree
    watch_mod._take_renders(conn, root / "out" / "store-restale-occt",
                            "occt", "occt", 1, overwrite=True)
    assert conn.execute("SELECT count(*) FROM renders WHERE part_id = '3001'"
                        ).fetchone()[0] == 1


def test_an_unchanged_drawing_is_not_rewritten_next_pass(tree):
    # Without this the watch rewrites every row and re-bakes every sheet on
    # every pass, which for a whole-slot refresh is the entire slot.
    root, conn = tree
    seen = {}
    first = watch_mod._take_renders(conn, root / "out" / "store-restale-occt",
                                    "occt", "occt", 1, True, seen)
    second = watch_mod._take_renders(conn, root / "out" / "store-restale-occt",
                                     "occt", "occt", 1, True, seen)
    assert first == (1, 1)
    assert second == (0, 0)


def test_a_redrawn_drawing_is_taken_again(tree):
    root, conn = tree
    new = root / "out" / "store-restale-occt" / "renders" / "occt"
    seen = {}
    watch_mod._take_renders(conn, root / "out" / "store-restale-occt",
                            "occt", "occt", 1, True, seen)
    (new / "3004.svg").write_text(WIDER)
    assert watch_mod._take_renders(conn, root / "out" / "store-restale-occt",
                                   "occt", "occt", 1, True, seen) == (0, 1)


def _jobs(monkeypatch, payload, code=0):
    class R:
        returncode = code
        stdout = payload
    monkeypatch.setattr(watch_mod.subprocess, "run",
                        lambda *a, **k: R())


def test_a_listed_task_is_running(monkeypatch):
    _jobs(monkeypatch, json.dumps(
        {"jobs": [{"task": "store-restale-occt", "state": "running"}],
         "unreachable": []}))
    assert watch_mod._tasks_running(["store-restale-occt"]) is True


def test_a_task_onto_does_not_list_has_stopped(monkeypatch):
    _jobs(monkeypatch, json.dumps(
        {"jobs": [{"task": "something-else"}], "unreachable": []}))
    assert watch_mod._tasks_running(["store-restale-occt"]) is False


def test_an_unreachable_node_is_not_an_answer(monkeypatch):
    # A dead agent hides its own running job, and taking that for "finished"
    # closes the round mid-render.
    _jobs(monkeypatch, json.dumps({"jobs": [], "unreachable": ["msb-uai"]}))
    assert watch_mod._tasks_running(["store-restale-occt"]) is None


def test_onto_failing_is_not_an_answer(monkeypatch):
    _jobs(monkeypatch, "", code=1)
    assert watch_mod._tasks_running(["store-restale-occt"]) is None
    _jobs(monkeypatch, "not json at all")
    assert watch_mod._tasks_running(["store-restale-occt"]) is None


@pytest.fixture
def quiet_tree(tmp_path, monkeypatch):
    """A tree with a SOURCE marker and nothing else to take."""
    monkeypatch.setattr(watch_mod, "ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    tree = tmp_path / "out" / "store-restale-occt"
    (tree / "renders").mkdir(parents=True)
    (tree / db.SOURCE_MARKER).write_text("occt\n")
    monkeypatch.setattr(watch_mod.time, "sleep", lambda s: None)
    return tree


def test_the_watch_closes_on_the_pass_after_the_task_stops(quiet_tree,
                                                           monkeypatch):
    passes = []
    monkeypatch.setattr(watch_mod, "_take_scores",
                        lambda *a, **k: passes.append(1) or 0)
    monkeypatch.setattr(watch_mod, "_tasks_running", lambda tasks: False)
    fetched = []
    monkeypatch.setattr(watch_mod, "_fetch", lambda t: fetched.append(t) or True)
    assert watch_mod.watch([quiet_tree], every=0, once=False, bake=False,
                           until=["store-restale-occt"]) == 0
    assert len(passes) == 2
    assert fetched == ["store-restale-occt"]


def test_the_watch_stays_up_while_the_task_runs(quiet_tree, monkeypatch):
    seen = {"n": 0}

    def running(tasks):
        seen["n"] += 1
        return seen["n"] < 3

    monkeypatch.setattr(watch_mod, "_tasks_running", running)
    monkeypatch.setattr(watch_mod, "_fetch", lambda t: True)
    assert watch_mod.watch([quiet_tree], every=0, once=False, bake=False,
                           until=["store-restale-occt"]) == 0
    assert seen["n"] == 3


def test_no_fetch_closes_without_calling_onto(quiet_tree, monkeypatch):
    monkeypatch.setattr(watch_mod, "_tasks_running", lambda tasks: False)
    called = []
    monkeypatch.setattr(watch_mod, "_fetch", lambda t: called.append(t) or True)
    watch_mod.watch([quiet_tree], every=0, once=False, bake=False,
                    until=["store-restale-occt"], fetch=False)
    assert called == []


def test_an_unknown_fleet_does_not_close_the_watch(quiet_tree, monkeypatch):
    answers = iter([None, None, False])
    monkeypatch.setattr(watch_mod, "_tasks_running", lambda t: next(answers))
    monkeypatch.setattr(watch_mod, "_fetch", lambda t: True)
    assert watch_mod.watch([quiet_tree], every=0, once=False, bake=False,
                           until=["store-restale-occt"]) == 0
