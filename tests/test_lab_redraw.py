"""A redraw, from the button's POST to the events the page hears."""
import json
import logging
import threading

import pytest
from fastapi.testclient import TestClient

from brick_icons import db, goldens, spot_protocol, thumbs
from brick_icons.lab import app as lab_app
from brick_icons.lab import cache

OLD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
       '<rect x="0" y="0" width="256" height="170" fill="black"/></svg>')
NEW = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
       '<circle cx="128" cy="85" r="60" fill="black"/></svg>')


def _drawn(svg=NEW, secs=4.2):
    return spot_protocol.reply(svg=svg, secs=secs, build="9.ccccccc",
                               state="drawn")


@pytest.fixture
def lab(tmp_path):
    """`lab(spot, sheets=False)`: a client over a corpus of 3001 and 3002,
    3001 already drawn in occt, and the events it publishes. The client's
    `settle()` waits for every background sheet patch to finish."""
    conn = db.connect(tmp_path / "corpus.db")
    for pid in ("3001", "3002"):
        conn.execute("INSERT INTO parts (id, title, category, printed, "
                     "obsolete, status) VALUES (?, 'Brick', 'Brick', 0, 0, "
                     "'good')", (pid,))
    held = tmp_path / "renders" / "occt" / "3001.svg"
    held.parent.mkdir(parents=True)
    held.write_text(OLD)
    conn.execute("INSERT INTO renders (part_id, source, config_key, made_at, "
                 "path, sha256) VALUES ('3001', 'occt', ?, "
                 "'2020-01-01T00:00:00+00:00', 'renders/occt/3001.svg', ?)",
                 (cache.key(db.canonical_argv("3001", "occt")),
                  goldens.sha256(OLD.encode())))
    conn.commit()
    conn.close()
    made = []

    def make(spot, sheets=False):
        slot = tmp_path / "thumbs" / "occt"
        if sheets:
            thumbs.bake_part("3001", held, slot, sha="old")
            thumbs.compose(slot, ["3001", "3002"])
        app = lab_app.create_app(
            root=tmp_path, cache_root=tmp_path / "cache",
            corpus_db=tmp_path / "corpus.db", thumbs_root=tmp_path / "thumbs",
            requests_path=tmp_path / "requests.jsonl",
            review_path=tmp_path / "review.jsonl", spot=spot)
        made.append(app)
        heard = []
        app.state.events.subscribe(lambda kind, data: heard.append((kind, data)))
        client = TestClient(app)
        client.settle = app.state.sheet_patches.shutdown
        return client, heard
    yield make
    for app in made:
        app.state.sheet_patches.shutdown()


def _redraw(client, part="3001", source="occt"):
    r = client.post("/api/corpus/redraw", json={"part": part, "source": source})
    assert r.status_code == 200, r.text
    return r.json()


def _one(tmp_path, sql, *args):
    conn = db.connect(tmp_path / "corpus.db")
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def test_a_new_drawing_is_stored_timed_and_announced(lab, stub_spot, tmp_path):
    client, heard = lab(stub_spot(_drawn()), sheets=True)
    body = _redraw(client)
    sha = goldens.sha256(NEW.encode())
    assert (body["state"], body["sha"], body["secs"]) == ("stored", sha, 4.2)
    assert (tmp_path / "renders" / "occt" / "3001.svg").read_text() == NEW
    assert _one(tmp_path, "SELECT sha256 FROM renders WHERE part_id = '3001' "
                          "AND source = 'occt'")[0] == sha
    assert tuple(_one(tmp_path, "SELECT state, secs, error FROM attempts")) == \
        ("stored", 4.2, None)
    client.settle()
    (kind, data), (sheets_kind, sheets) = heard
    assert kind == "changed"
    assert data == {"part": "3001", "source": "occt", "sha": sha,
                    "build": "9.ccccccc"}
    assert sheets_kind == "sheets"
    manifest = json.loads((tmp_path / "thumbs" / "occt" / "sheet-32.json").read_text())
    assert (sheets["part"], sheets["source"]) == ("3001", "occt")
    assert sheets["versions"]["32"] == manifest["version"]
    assert manifest["baked"]["3001"] == sha


def test_a_store_exception_leaves_no_stored_attempt(lab, stub_spot, monkeypatch,
                                                     tmp_path):
    def boom(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(db, "store_render", boom)
    client, heard = lab(stub_spot(_drawn()))
    with pytest.raises(OSError):
        client.post("/api/corpus/redraw", json={"part": "3001", "source": "occt"})
    assert tuple(_one(tmp_path, "SELECT state, error FROM attempts")) == \
        (None, "OSError")
    assert _one(tmp_path, "SELECT sha256 FROM renders WHERE part_id = '3001' "
                          "AND source = 'occt'")[0] == goldens.sha256(OLD.encode())
    assert heard == []


def test_the_change_is_announced_before_the_sheets_are_patched(
        lab, stub_spot, monkeypatch):
    release, patching = threading.Event(), threading.Event()
    real = thumbs.patch_cell

    def held(*args, **kwargs):
        patching.set()
        release.wait(5)
        return real(*args, **kwargs)
    monkeypatch.setattr(thumbs, "patch_cell", held)
    client, heard = lab(stub_spot(_drawn()), sheets=True)
    body = _redraw(client)
    assert body["state"] == "stored"
    assert "sheet_version" not in body
    assert [kind for kind, _ in heard] == ["changed"]
    assert patching.wait(5), "the sheet patch never started"
    assert not release.is_set()
    release.set()
    client.settle()
    assert [kind for kind, _ in heard] == ["changed", "sheets"]


def test_the_sheet_patch_runs_off_the_request_thread(lab, stub_spot, monkeypatch):
    client, _ = lab(stub_spot(_drawn()), sheets=True)
    threads = []
    real = thumbs.bake_part

    def seen(*args, **kwargs):
        threads.append(threading.current_thread())
        return real(*args, **kwargs)
    monkeypatch.setattr(thumbs, "bake_part", seen)
    asked_on = []
    real_redraw = lab_app.redraw_mod.redraw

    def noting(*args, **kwargs):
        asked_on.append(threading.current_thread())
        return real_redraw(*args, **kwargs)
    monkeypatch.setattr(lab_app.redraw_mod, "redraw", noting)
    _redraw(client)
    client.settle()
    (patched_on,), (route_on,) = threads, asked_on
    assert patched_on is not route_on


def test_the_wall_s_delta_carries_the_new_sha(lab, stub_spot):
    client, _ = lab(stub_spot(_drawn()))
    since = client.get("/api/corpus/cells", params={"source": "occt"}).json()["version"]
    body = _redraw(client)
    delta = client.get("/api/corpus/cells",
                       params={"source": "occt", "since": since}).json()
    assert [(c["id"], c["sha"]) for c in delta["cells"]] == [("3001", body["sha"])]


def test_the_worker_is_asked_for_the_slot_s_own_argv_at_origin_main(
        lab, stub_spot, tmp_path):
    spot = stub_spot(_drawn())
    client, _ = lab(spot)
    _redraw(client)
    ((req, commit),) = spot.calls
    assert req == spot_protocol.request("3001", "occt",
                                        db.canonical_argv("3001", "occt"),
                                        build="9.ccccccc")
    assert commit == "c" * 40
    (asked,) = [json.loads(l) for l in
                (tmp_path / "requests.jsonl").read_text().splitlines()]
    assert (asked["part"], asked["source"], asked["build"]) == \
        ("3001", "occt", "9.ccccccc")


def test_the_same_bytes_are_unchanged_and_announce_nothing(lab, stub_spot, tmp_path):
    client, heard = lab(stub_spot(_drawn(OLD)), sheets=True)
    was = (tmp_path / "thumbs" / "occt" / "sheet-32.json").read_text()
    assert _redraw(client)["state"] == "unchanged"
    client.settle()
    assert heard == []
    assert _one(tmp_path, "SELECT made_at FROM renders")[0] > "2020-01-01"
    assert (tmp_path / "thumbs" / "occt" / "sheet-32.json").read_text() == was
    assert _one(tmp_path, "SELECT state FROM attempts")[0] == "stored"


def test_a_timeout_is_an_attempt_and_leaves_the_drawing(lab, stub_spot, tmp_path):
    reply = spot_protocol.reply(secs=150.3, build="9.ccccccc",
                                error="TimeoutError", detail="exceeded 150s")
    client, heard = lab(stub_spot(reply))
    body = _redraw(client)
    assert (body["state"], body["error"]) == ("failed", "TimeoutError")
    assert tuple(_one(tmp_path, "SELECT state, secs, error FROM attempts")) == \
        (None, 150.3, "TimeoutError")
    assert (tmp_path / "renders" / "occt" / "3001.svg").read_text() == OLD
    assert heard == []


def test_a_decal_with_nothing_to_draw_is_recorded_as_none(lab, stub_spot, tmp_path):
    reply = spot_protocol.reply(secs=1.0, build="9.ccccccc", state="none")
    client, heard = lab(stub_spot(reply))
    assert _redraw(client, source="decal")["state"] == "none"
    assert _one(tmp_path, "SELECT state FROM attempts")[0] == "none"
    assert heard == []


def test_a_down_service_is_said_and_tries_nothing(lab, stub_spot, tmp_path):
    client, heard = lab(stub_spot(down="no such service"))
    body = _redraw(client)
    assert (body["state"], body["detail"]) == ("down", "no such service")
    assert _one(tmp_path, "SELECT count(*) FROM attempts")[0] == 0
    assert not (tmp_path / "requests.jsonl").exists()
    assert heard == []


def test_a_failed_roll_is_a_failure_in_onto_s_words(lab, stub_spot, tmp_path):
    client, _ = lab(stub_spot(error="checkout cccc: uv sync failed",
                              error_kind="RollFailed"))
    body = _redraw(client)
    assert (body["state"], body["error"], body["detail"]) == \
        ("failed", "RollFailed", "checkout cccc: uv sync failed")
    assert _one(tmp_path, "SELECT count(*) FROM attempts")[0] == 0
    assert not (tmp_path / "requests.jsonl").exists()


def test_a_sheet_that_cannot_be_patched_still_stores_the_drawing(
        lab, stub_spot, tmp_path, caplog):
    client, heard = lab(stub_spot(_drawn()), sheets=False)
    with caplog.at_level(logging.WARNING):
        body = _redraw(client)
        client.settle()
    assert body["state"] == "stored"
    assert (tmp_path / "renders" / "occt" / "3001.svg").read_text() == NEW
    assert "the next bake repairs them" in caplog.text
    assert [kind for kind, _ in heard] == ["changed"]


def test_a_second_click_joins_the_first(lab, stub_spot, concurrently):
    gate = threading.Event()
    spot = stub_spot(_drawn(), gate=gate)
    client, heard = lab(spot)
    threading.Timer(0.5, gate.set).start()
    got = concurrently(2, lambda: _redraw(client))
    client.settle()
    assert len(spot.calls) == 1
    assert got[0] == got[1]
    assert [kind for kind, _ in heard] == ["changed"]


@pytest.mark.parametrize("source", ["reference", "reference-gray",
                                    "reference-lines"])
def test_a_reference_slot_refuses_a_redraw(lab, stub_spot, source):
    client, _ = lab(stub_spot(_drawn()))
    r = client.post("/api/corpus/redraw", json={"part": "3001", "source": source})
    assert r.status_code == 400


def test_a_redraw_of_an_unknown_part_is_404(lab, stub_spot):
    client, _ = lab(stub_spot(_drawn()))
    r = client.post("/api/corpus/redraw", json={"part": "9999", "source": "occt"})
    assert r.status_code == 404


def test_the_status_route_passes_the_worker_s_state_through(lab, stub_spot):
    status = {"state": "stale", "build": "8.bbbbbbb", "want": "9.ccccccc",
              "detail": None}
    client, _ = lab(stub_spot(status=status))
    assert client.get("/api/spot").json() == status
    assert client.get("/api/spot/status.txt").text == \
        "up at 8.bbbbbbb, rolls to 9.ccccccc on the next redraw"


def test_a_sheet_manifest_is_served_with_its_own_version(lab, stub_spot, tmp_path):
    client, _ = lab(stub_spot(_drawn()), sheets=True)
    manifest = json.loads((tmp_path / "thumbs" / "occt" / "sheet-8.json").read_text())
    assert client.get("/api/thumbs/occt/sheet-8.json").json()["version"] == \
        manifest["version"]


def test_the_part_detail_names_the_spot_build_and_no_queue(lab, stub_spot):
    client, _ = lab(stub_spot(_drawn()))
    _redraw(client)
    slots = {s["source"]: s for s in
             client.get("/api/corpus/part/3001").json()["slots"]}
    assert slots["occt"]["build"] == "9.ccccccc"
    assert all("requested_at" not in s for s in slots.values())


def test_closing_the_app_finishes_its_sheet_patches(lab, stub_spot, tmp_path):
    client, heard = lab(stub_spot(_drawn()), sheets=True)
    with client:
        _redraw(client)
    assert [kind for kind, _ in heard] == ["changed", "sheets"]
