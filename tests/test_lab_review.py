"""The review queue's routes: what is listed, what is served, what a verdict
does to the defect it speaks to."""
import pytest
from fastapi.testclient import TestClient

from brick_icons import db, goldens, requests as render_requests, review
from brick_icons.lab import app as lab_app
from brick_icons.lab import defects

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180">'
       '<rect x="20" y="20" width="100" height="60" fill="black"/></svg>')
SVG2 = SVG.replace('width="100"', 'width="160"')
SVG3 = SVG.replace('width="100"', 'width="10"')

DEFECT = {"id": "3001-occt-short", "part": "3001", "engines": ["occt"],
          "status": "open", "title": "rect too short",
          "checked": {"occt": "stale"}, "filed": "2026-09-01",
          "notes": "first look"}


def _draw(root, tree, part, text, source="occt"):
    svg = root / tree / "renders" / source / f"{part}.svg"
    svg.parent.mkdir(parents=True, exist_ok=True)
    svg.write_text(text)
    return svg


@pytest.fixture
def lab(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    conn.executemany("INSERT INTO parts (id, title, printed, obsolete) "
                     "VALUES (?, ?, 0, 0)",
                     [("3001", "Brick 2 x 4"), ("3002", "Brick 2 x 3")])
    run1 = db.start_run(conn, "census", {"dir": "out/a"}, "aaa1111")
    run2 = db.start_run(conn, "census", {"dir": "out/b"}, "bbb2222")
    for part in ("3001", "3002"):
        db.record_render(conn, part, "occt", _draw(tmp_path, "out/a", part, SVG),
                         root=tmp_path, run_id=run1)
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "build, secs, extra_d99) VALUES (?, '3001', 'occt', 'occt', "
                 "'100.aaa1111', 1.5, 0.4)", (run1,))
    conn.commit()
    defects.save(tmp_path / "defects.toml", [DEFECT])
    render_requests.add(tmp_path / "requests.jsonl", "3002", "occt",
                        at="2020-01-01T00:00:00+00:00")
    for part in ("3001", "3002"):
        db.record_render(conn, part, "occt", _draw(tmp_path, "out/b", part, SVG2),
                         root=tmp_path, run_id=run2)
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "build, secs, extra_d99) VALUES (?, '3001', 'occt', 'occt', "
                 "'101.bbb2222', 1.2, 0.3)", (run2,))
    conn.commit()
    conn.close()
    client = TestClient(lab_app.create_app(
        root=tmp_path, cache_root=tmp_path / "cache",
        corpus_db=tmp_path / "corpus.db", defects_path=tmp_path / "defects.toml",
        requests_path=tmp_path / "requests.jsonl"))
    return client, tmp_path


def _sha(text):
    return goldens.sha256(text.encode())


def test_the_list_joins_the_defect_the_request_and_the_numbers(lab):
    client, _root = lab
    body = client.get("/api/review").json()
    assert body["verdicts"] == ["fixed", "better", "neutral", "regression"]
    by_part = {e["part"]: e for e in body["entries"]}
    one = by_part["3001"]
    assert one["id"] == review.entry_id("occt", "3001", _sha(SVG2))
    assert one["title"] == "Brick 2 x 4" and one["by"] == "b"
    assert one["before"]["sha256"] == _sha(SVG)
    assert one["before"]["build"] == "100.aaa1111"
    assert one["after"]["build"] == "101.bbb2222"
    assert one["after"]["extra_d99"] == 0.3
    assert one["defects"] == [{"id": DEFECT["id"], "title": "rect too short",
                               "status": "open", "checked": "stale"}]
    assert one["request"] is None and one["superseded_by"] is None
    assert one["diff"] is None and one["judged"] is None
    two = by_part["3002"]
    assert two["defects"] == []
    assert two["request"]["at"] == "2020-01-01T00:00:00+00:00"


def test_the_all_view_gates_on_components_and_keeps_the_unmeasured(lab):
    client, root = lab
    unlinked_defects = root / "defects.toml"
    defects.save(unlinked_defects, [])
    (root / "requests.jsonl").unlink()
    assert client.get("/api/review").json()["entries"] == []
    both = client.get("/api/review", params={"view": "all"}).json()
    assert len(both["entries"]) == 2
    eid = both["entries"][0]["id"]
    assert client.get(f"/api/review/{eid}/diff.png").headers[
        "content-type"] == "image/png"
    measured = client.get("/api/review", params={"view": "all"}).json()
    got = {e["id"]: e["diff"] for e in measured["entries"]}
    assert got[eid]["components"] >= 1 and got[eid]["width"] == 900
    # The measured entry falls under the bar; the unmeasured one is kept,
    # because a gate cannot judge a diff nobody has taken.
    high = client.get("/api/review", params={"view": "all",
                                             "min_components": 10_000}).json()
    assert [e["diff"] for e in high["entries"]] == [None]
    assert high["entries"][0]["id"] != eid


def test_the_images_are_served_by_id_and_not_by_path(lab):
    client, _root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    assert client.get(f"/api/review/{eid}/before").text == SVG
    assert client.get(f"/api/review/{eid}/after").text == SVG2
    assert client.get("/api/review/occt/3001/nope/before").status_code == 404
    assert client.get("/api/review/../../etc/passwd/before").status_code == 404


def test_one_entry_is_read_by_id(lab):
    client, _root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    assert client.get(f"/api/review/{eid}").json()["id"] == eid
    assert client.get("/api/review/occt/3001/nope").status_code == 404


def test_a_verdict_closes_the_defect_and_stamps_what_was_judged(lab):
    client, root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    r = client.post(f"/api/review/{eid}/verdict",
                    json={"verdict": "fixed", "note": "rim is back"})
    assert r.status_code == 200
    item = r.json()
    assert item["judged"]["verdict"] == "fixed"
    assert item["judged"]["defects"] == [DEFECT["id"]]
    assert [(d["id"], d["status"]) for d in item["defects"]] == [
        (DEFECT["id"], "fixed")]
    record = defects.load(root / "defects.toml")[0]
    assert record["status"] == "fixed"
    assert record["checked"] == {"occt": _sha(SVG2)}
    assert record["notes"].startswith("first look\n\n")
    assert record["notes"].endswith("review fixed: rim is back")
    assert [l["kind"] for l in review.load(root / review.DEFAULT_PATH)][-1] == "judged"
    listed = client.get("/api/review").json()["entries"]
    assert eid not in {e["id"] for e in listed}
    shown = client.get("/api/review", params={"judged": 1}).json()["entries"]
    assert eid in {e["id"] for e in shown}


def test_a_regression_keeps_the_defect_open(lab):
    client, root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    client.post(f"/api/review/{eid}/verdict", json={"verdict": "regression"})
    record = defects.load(root / "defects.toml")[0]
    assert record["status"] == "open"
    assert record["checked"]["occt"] == _sha(SVG2)
    assert record["notes"].endswith("review regression")


def test_an_unknown_verdict_is_400(lab):
    client, _root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    assert client.post(f"/api/review/{eid}/verdict",
                       json={"verdict": "meh"}).status_code == 400


def test_a_redrawn_slot_supersedes_the_entry(lab):
    client, root = lab
    conn = db.connect(root / "corpus.db")
    db.record_render(conn, "3001", "occt", _draw(root, "out/c", "3001", SVG3),
                     root=root)
    conn.close()
    entries = {e["id"]: e for e in client.get("/api/review").json()["entries"]}
    first = entries[review.entry_id("occt", "3001", _sha(SVG2))]
    third = review.entry_id("occt", "3001", _sha(SVG3))
    assert first["superseded_by"] == third
    assert entries[third]["superseded_by"] is None


def test_measure_fills_in_every_unmeasured_entry(lab):
    client, _root = lab
    assert client.post("/api/review/measure").json() == {"measured": 2,
                                                          "failed": []}
    assert client.post("/api/review/measure").json()["measured"] == 0
    body = client.get("/api/review", params={"view": "all"}).json()
    assert all(e["diff"]["components"] >= 1 for e in body["entries"])
