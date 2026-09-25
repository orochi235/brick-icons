"""The review queue's routes: what is listed, what is served, what a verdict
does to the defect it speaks to."""
import json
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from brick_icons import db, goldens, requests as render_requests, review
from brick_icons.lab import app as lab_app
from brick_icons.lab import defects

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180">'
       '<rect x="20" y="20" width="100" height="60" fill="black"/></svg>')
SVG2 = SVG.replace('width="100"', 'width="160"')
SVG3 = SVG.replace('width="100"', 'width="10"')
# A speck under `diff.PANEL_MIN_PX`: measurable, and not a change anyone
# would look at.
SPECK = '<rect x="200" y="150" width="0.5" height="0.5" fill="black"/>'
SVG2_SPECK = SVG2.replace('</svg>', SPECK + '</svg>')

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


def test_a_regression_reopens_a_defect_an_earlier_verdict_closed(lab):
    """A fix recorded once and undone by a later redraw left the defect
    `fixed` with a regression noted underneath it, so nothing listed it as
    live again and only a reader of the notes would ever know."""
    client, root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    client.post(f"/api/review/{eid}/verdict", json={"verdict": "fixed"})
    assert defects.load(root / "defects.toml")[0]["status"] == "fixed"
    item = client.post(f"/api/review/{eid}/verdict",
                       json={"verdict": "regression"}).json()
    record = defects.load(root / "defects.toml")[0]
    assert record["status"] == "open"
    assert [d["status"] for d in item["defects"]] == ["open"]


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
    body = client.get("/api/review").json()
    entries = {e["id"]: e for e in body["entries"]}
    first = review.entry_id("occt", "3001", _sha(SVG2))
    third = review.entry_id("occt", "3001", _sha(SVG3))
    # Only the newest hop is a queue item; the one it displaced is reachable
    # by id and says what displaced it.
    assert first not in entries and entries[third]["superseded_by"] is None
    assert body["superseded"] == 1
    assert client.get(f"/api/review/{first}").json()["superseded_by"] == third


def test_a_judged_entry_stays_listed_once_the_slot_moves_on(lab):
    client, root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    client.post(f"/api/review/{eid}/verdict", json={"verdict": "neutral"})
    conn = db.connect(root / "corpus.db")
    db.record_render(conn, "3001", "occt", _draw(root, "out/c", "3001", SVG3),
                     root=root)
    conn.close()
    body = client.get("/api/review?judged=1").json()
    assert eid in {e["id"] for e in body["entries"]}
    assert body["superseded"] == 0


def test_measure_fills_in_every_unmeasured_entry(lab):
    client, _root = lab
    assert client.post("/api/review/measure").json() == {"measured": 2,
                                                          "failed": []}
    assert client.post("/api/review/measure").json()["measured"] == 0
    body = client.get("/api/review", params={"view": "all"}).json()
    assert all(e["diff"]["components"] >= 1 for e in body["entries"])


def _displace(root, part, text, source="occt"):
    """Draw `text` over the slot's render, recording the displacement."""
    conn = db.connect(root / "corpus.db")
    run = db.start_run(conn, "census", {"dir": "out/c"}, "ccc3333")
    db.record_render(conn, part, source, _draw(root, "out/c", part, text),
                     root=root, run_id=run)
    conn.commit()
    conn.close()


def test_the_linked_view_screens_out_a_redraw_that_changed_nothing(lab):
    client, root = lab
    _displace(root, "3002", SVG2_SPECK)
    assert client.post("/api/review/measure").json()["measured"] == 3
    speck = review.entry_id("occt", "3002", _sha(SVG2_SPECK))
    body = client.get("/api/review").json()
    assert {e["id"] for e in body["entries"]}.isdisjoint({speck})
    assert body["hidden"] == 1
    shown = client.get("/api/review", params={"min_components": 0}).json()
    assert speck in {e["id"] for e in shown["entries"]}
    assert shown["hidden"] == 0


def test_an_unmeasured_linked_entry_is_kept_because_no_diff_screens_it(lab):
    client, _root = lab
    body = client.get("/api/review").json()
    assert [e["diff"] for e in body["entries"]] == [None, None]
    assert body["hidden"] == 0


def test_measure_can_be_pointed_at_one_view(lab):
    client, root = lab
    defects.save(root / "defects.toml", [])
    (root / "requests.jsonl").unlink()
    assert client.post("/api/review/measure",
                       params={"view": "linked"}).json()["measured"] == 0
    defects.save(root / "defects.toml", [DEFECT])
    assert client.post("/api/review/measure",
                       params={"view": "linked"}).json()["measured"] == 1
    body = client.get("/api/review", params={"view": "all"}).json()
    measured = {e["part"]: e["diff"] for e in body["entries"]}
    assert measured["3001"]["components"] >= 1 and measured["3002"] is None


def test_undo_puts_the_defect_back_exactly_as_the_verdict_found_it(lab):
    client, root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    before = defects.load(root / "defects.toml")
    assert client.post(f"/api/review/{eid}/verdict",
                       json={"verdict": "fixed", "note": "rim is back"}
                       ).status_code == 200
    judged = defects.load(root / "defects.toml")[0]
    assert judged["status"] == "fixed" and judged["checked"]["occt"] != "stale"

    item = client.post(f"/api/review/{eid}/undo").json()
    assert item["judged"] is None
    assert defects.load(root / "defects.toml") == before


def test_undo_returns_the_entry_to_the_unjudged_queue(lab):
    client, _root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    client.post(f"/api/review/{eid}/verdict", json={"verdict": "fixed"})
    assert eid not in [e["id"] for e in
                       client.get("/api/review").json()["entries"]]
    client.post(f"/api/review/{eid}/undo")
    assert eid in [e["id"] for e in client.get("/api/review").json()["entries"]]


def test_a_verdict_can_be_cast_again_after_an_undo(lab):
    client, root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    client.post(f"/api/review/{eid}/verdict", json={"verdict": "fixed"})
    client.post(f"/api/review/{eid}/undo")
    item = client.post(f"/api/review/{eid}/verdict",
                       json={"verdict": "regression"}).json()
    assert item["judged"]["verdict"] == "regression"
    assert defects.load(root / "defects.toml")[0]["status"] == "open"


def test_undoing_an_unjudged_entry_is_400(lab):
    client, _root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    assert client.post(f"/api/review/{eid}/undo").status_code == 400


def test_undo_of_a_legacy_verdict_says_it_could_not_restore(lab):
    """A judged line written before `restore` existed cannot give back the
    previous `checked` sha, so the undo reopens the defect and says so."""
    client, root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    client.post(f"/api/review/{eid}/verdict", json={"verdict": "fixed"})
    log = root / "store-queue" / "review.jsonl"
    kept = [line for line in log.read_text().splitlines()]
    stripped = []
    for line in kept:
        row = json.loads(line)
        row.pop("restore", None)
        stripped.append(json.dumps(row))
    log.write_text("\n".join(stripped) + "\n")

    item = client.post(f"/api/review/{eid}/undo").json()
    assert item["restored"] is False
    record = defects.load(root / "defects.toml")[0]
    assert record["status"] == "open"
    assert "occt" not in record["checked"]


def test_the_reference_panel_serves_the_corpus_reference_slot(lab):
    """The baked slot every reference script and the wall use, not a live
    LDView call: a subprocess per card draws a different picture, in the
    wrong colors."""
    client, root = lab
    conn = db.connect(root / "corpus.db")
    ref = root / "renders" / "reference" / "3001.webp"
    ref.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), (200, 190, 90)).save(ref)
    db.record_render(conn, "3001", "reference", ref, root=root)
    conn.close()

    eid = review.entry_id("occt", "3001", _sha(SVG2))
    r = client.get(f"/api/review/{eid}/reference")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.content == ref.read_bytes()


def test_a_part_with_no_reference_render_is_404_not_a_broken_card(lab):
    client, _root = lab
    eid = review.entry_id("occt", "3001", _sha(SVG2))
    assert client.get(f"/api/review/{eid}/reference").status_code == 404


def test_the_entry_points_at_its_reference(lab):
    client, _root = lab
    entry = client.get("/api/review").json()["entries"][0]
    assert entry["urls"]["reference"] == f"/api/review/{entry['id']}/reference"


def test_each_side_reports_its_file_size(lab):
    """Two drawings that look alike can differ enormously in what they are
    made of, and the diff panel cannot show that."""
    client, _root = lab
    item = client.get("/api/review?view=all").json()["entries"][0]
    for side in ("before", "after"):
        content = item[side]["content"]
        assert content["bytes"] > 0
        assert content["shapes"] is not None


def test_content_counts_the_elements_the_engine_draws(tmp_path):
    """`<path>` and `<line>` are the whole vocabulary of a render; a clipPath
    is a mask, not ink, and must not be counted as a shape."""
    from brick_icons.lab import review_api
    svg = tmp_path / "renders" / "occt" / "3001.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<defs><linearGradient id="g0"><stop offset="0%" stop-color="#000"/>'
        '</linearGradient>'
        '<clipPath id="c"><path d="M 0 0 L 9 9"/></clipPath></defs>'
        '<path d="M 1 1 L 2 2" fill="url(#g0)"/><path d="M 3 3 L 4 4"/>'
        '<line x1="0" y1="0" x2="5" y2="5"/><line x1="1" y1="0" x2="5" y2="4"/>'
        '</svg>')
    got = review_api._content(tmp_path, "renders/occt/3001.svg")
    assert got["shapes"] == 2 and got["lines"] == 2 and got["gradients"] == 1
    assert got["bytes"] == svg.stat().st_size


def test_content_of_a_missing_or_unreadable_side_is_empty(tmp_path):
    """A kept `.svg` can hold a raster -- `keep_before` names the copy after
    the row's slot, not after what the bytes are -- and a side can be gone."""
    from brick_icons.lab import review_api
    png = tmp_path / "renders" / "occt" / "3001.svg"
    png.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(png, format="PNG")
    got = review_api._content(tmp_path, "renders/occt/3001.svg")
    assert got["bytes"] > 0 and got["shapes"] is None
    assert review_api._content(tmp_path, "renders/occt/nope.svg") == {
        "bytes": None, "shapes": None, "lines": None, "gradients": None}


def test_the_list_does_not_parse_an_svg_for_a_row_it_will_not_show(lab, monkeypatch):
    """`list_entries` builds an entry for EVERY row, because `total` and
    `hidden` are counts over all of them -- 16,828 rows the day this was
    found. Parsing both sides of each one to count its elements took the
    board from instant to unusable. Content is for the rows that survive.
    """
    from brick_icons.lab import review_api
    client, root = lab
    # 3002 is linked only by a pending request; drop it so the linked view
    # really does filter a row out
    (root / "requests.jsonl").unlink()
    calls = []
    real = review_api._content
    monkeypatch.setattr(review_api, "_content",
                        lambda *a, **k: (calls.append(a), real(*a, **k))[1])
    body = client.get("/api/review", params={"view": "linked"}).json()
    shown = len(body["entries"])
    assert shown == 1
    assert body["entries"][0]["after"]["content"]["bytes"] > 0
    assert len(calls) <= 2 * shown, f"{len(calls)} parses for {shown} shown"
