import pytest

from fastapi.testclient import TestClient

from brick_icons.lab import app as lab_app


@pytest.fixture
def client(tmp_path):
    return TestClient(lab_app.create_app(cache_root=tmp_path))


def test_schema_route_returns_the_fields(client):
    body = client.get("/api/schema").json()
    keys = {f["key"] for f in body["fields"]}
    assert {"engine", "shading", "shade_style", "angle"} <= keys


def test_lists_route_returns_the_corpus_lists(client):
    body = client.get("/api/lists").json()
    assert any(c["name"] == "specimens" for c in body["lists"])


def test_parts_route_searches(client):
    body = client.get("/api/parts", params={"q": "3941"}).json()
    assert body["results"][0]["id"] == "3941"


def test_parts_route_needs_a_query(client):
    assert client.get("/api/parts", params={"q": ""}).json()["results"] == []


def test_goldens_route_reports_a_part(client):
    body = client.get("/api/goldens", params={"part": "3941"}).json()
    assert body["part"] == "3941"


def test_unknown_route_is_404(client):
    assert client.get("/api/nope").status_code == 404


import time


def _finish(client, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "failed", "cancelled"):
            return body
        time.sleep(0.05)
    raise AssertionError("render did not finish")


def test_render_starts_a_job_and_echoes_the_command(client, ldraw_dir):
    body = client.post("/api/render", json={
        "part": "3005",
        "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    assert body["command"] == "brick-icons 3005 --format svg --shading outline"
    assert body["job"]


def test_a_finished_render_lists_its_artifacts(client, ldraw_dir):
    started = client.post("/api/render", json={
        "part": "3005", "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    done = _finish(client, started["job"])
    assert done["state"] == "done"
    assert "3005.svg" in {a["name"] for a in done["results"][0]["artifacts"]}


def test_an_artifact_is_served_back(client, ldraw_dir):
    started = client.post("/api/render", json={
        "part": "3005", "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    done = _finish(client, started["job"])
    key = done["results"][0]["key"]
    r = client.get(f"/api/artifact/{key}/3005.svg")
    assert r.status_code == 200
    assert r.text.startswith("<svg")


def test_an_artifact_outside_the_cache_is_refused(client):
    r = client.get("/api/artifact/abc123/..%2F..%2Fpyproject.toml")
    assert r.status_code in (400, 404)


def test_an_unknown_config_key_is_a_400(client):
    r = client.post("/api/render", json={"part": "3005",
                                         "config": {"not_a_flag": 1}})
    assert r.status_code == 400


def test_a_job_can_be_cancelled(client, ldraw_dir):
    started = client.post("/api/render", json={
        "part": "3649", "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    assert client.post(f"/api/jobs/{started['job']}/cancel").json()["cancelled"]


def test_an_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


def test_diff_route_compares_two_cached_artifacts(client, tmp_path):
    import numpy as np
    from PIL import Image
    for key, box in (("aaaa1111", None), ("bbbb2222", (10, 10, 20, 20))):
        d = tmp_path / key
        d.mkdir(parents=True)
        a = np.full((64, 64), 255, np.uint8)
        if box:
            x0, y0, x1, y1 = box
            a[y0:y1, x0:x1] = 0
        Image.fromarray(a, "L").save(d / "r.png")
    body = client.get("/api/diff", params={
        "a_key": "aaaa1111", "a_name": "r.png",
        "b_key": "bbbb2222", "b_name": "r.png"}).json()
    assert body["components"] == 1
    assert body["sizes"] == [100]


def test_diff_of_a_missing_artifact_is_404(client):
    r = client.get("/api/diff", params={
        "a_key": "aaaa1111", "a_name": "gone.png",
        "b_key": "bbbb2222", "b_name": "gone.png"})
    assert r.status_code == 404


DEFECT = {
    "id": "3941-occt-borehole", "part": "3941", "engines": ["occt"],
    "status": "open", "title": "borehole rim not drawn",
    "mark": {"x": 0.42, "y": 0.55, "w": 0.11, "h": 0.09},
    "seen": {"angle": "30,25", "shading": "outline", "shade_style": "flat3"},
    "filed": "2026-08-31", "notes": "",
}


@pytest.fixture
def defect_client(tmp_path):
    return TestClient(lab_app.create_app(cache_root=tmp_path / "cache",
                                         defects_path=tmp_path / "defects.toml"))


def test_defects_start_empty(defect_client):
    assert defect_client.get("/api/defects").json()["defects"] == []


def test_a_posted_defect_comes_back(defect_client):
    assert defect_client.post("/api/defects", json=DEFECT).status_code == 200
    got = defect_client.get("/api/defects").json()["defects"]
    assert got[0]["id"] == DEFECT["id"]
    assert got[0]["mark"]["x"] == 0.42


def test_a_duplicate_defect_is_a_409(defect_client):
    defect_client.post("/api/defects", json=DEFECT)
    assert defect_client.post("/api/defects", json=DEFECT).status_code == 409


def test_a_defect_status_can_be_patched(defect_client):
    defect_client.post("/api/defects", json=DEFECT)
    r = defect_client.patch(f"/api/defects/{DEFECT['id']}",
                            json={"status": "fixed"})
    assert r.json()["status"] == "fixed"


def test_patching_an_unknown_defect_is_404(defect_client):
    assert defect_client.patch("/api/defects/nope",
                               json={"status": "fixed"}).status_code == 404


def test_a_bad_status_is_a_400(defect_client):
    defect_client.post("/api/defects", json=DEFECT)
    r = defect_client.patch(f"/api/defects/{DEFECT['id']}",
                            json={"status": "maybe"})
    assert r.status_code == 400


def test_batch_starts_one_job_for_the_list(client, ldraw_dir):
    body = client.post("/api/batch", json={
        "parts": ["3005", "3024"],
        "config": {"fmt": "svg", "shading": "outline"},
    }).json()
    done = _finish(client, body["job"], timeout=180)
    assert done["total"] == 2
    assert done["done"] == 2
    assert [e["index"] for e in done["events"]] == [1, 2]


def test_command_route_returns_argv_without_rendering(client):
    body = client.get("/api/command", params={
        "part": "3941",
        "config": '{"engine": "occt", "shading": "outline"}',
    }).json()
    assert body["argv"] == ["3941", "--shading", "outline", "--engine", "occt"]
    assert body["command"] == "brick-icons 3941 --shading outline --engine occt"


def test_command_route_rejects_an_unknown_key(client):
    r = client.get("/api/command", params={"part": "3941",
                                           "config": '{"not_a_flag": 1}'})
    assert r.status_code == 400


def test_command_route_rejects_unparseable_config(client):
    r = client.get("/api/command", params={"part": "3941", "config": "{oops"})
    assert r.status_code == 400


def test_diff_route_compares_two_svg_renders(client, tmp_path):
    """The engines emit SVG; the differ needs rasters. The route bridges it."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
           '<rect x="{x}" y="2" width="4" height="4" fill="black"/></svg>')
    for key, x in (("aaaa1111", 1), ("bbbb2222", 5)):
        d = tmp_path / key
        d.mkdir(parents=True, exist_ok=True)
        (d / "p.svg").write_text(svg.format(x=x))
    body = client.get("/api/diff", params={
        "a_key": "aaaa1111", "a_name": "p.svg",
        "b_key": "bbbb2222", "b_name": "p.svg"}).json()
    assert body["components"] >= 1
    assert body["url"].startswith("/api/artifact/")


def test_diff_route_reports_a_size_mismatch_as_400(client, tmp_path):
    import numpy as np
    from PIL import Image
    for key, size in (("cccc3333", (16, 16)), ("dddd4444", (32, 32))):
        d = tmp_path / key
        d.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.full(size, 255, np.uint8), "L").save(d / "p.png")
    r = client.get("/api/diff", params={
        "a_key": "cccc3333", "a_name": "p.png",
        "b_key": "dddd4444", "b_name": "p.png"})
    assert r.status_code == 400


def test_reference_route_reports_a_bad_angle(client):
    r = client.get("/api/reference", params={"part": "3005", "angle": "nope"})
    assert r.status_code == 400


def test_reference_route_returns_a_url_when_it_can_render(client, ldraw_dir):
    from brick_icons.lab import reference
    if not reference.available("."):
        pytest.skip("LDView not installed")
    body = client.get("/api/reference",
                      params={"part": "3005", "angle": "30,25"}).json()
    assert body["url"].startswith("/api/reference-artifact/")
    assert client.get(body["url"]).status_code == 200


def test_reference_route_says_when_ldview_is_missing(client, monkeypatch):
    from brick_icons.lab import reference
    monkeypatch.setattr(reference, "available", lambda root: False)
    r = client.get("/api/reference", params={"part": "3005", "angle": "30,25"})
    assert r.status_code == 503
    assert "setup-ldview" in r.json()["detail"]


def test_decal_route_returns_urls_for_a_printed_part(client, ldraw_dir):
    body = client.get("/api/decal", params={"part": "3005p01"}).json()
    assert body["urls"], body
    assert body["urls"][0].startswith("/api/decal-artifact/")
    assert client.get(body["urls"][0]).status_code == 200


def test_decal_route_says_an_unprinted_part_has_none(client, ldraw_dir):
    body = client.get("/api/decal", params={"part": "3005"}).json()
    assert body["urls"] == []


def test_decal_route_reports_a_part_it_cannot_read(client, ldraw_dir):
    r = client.get("/api/decal", params={"part": "no-such-part-9999"})
    assert r.status_code == 400


def test_combos_route_lists_them(client):
    body = client.get("/api/combos").json()
    assert any(c["name"] == "outline-flat3" for c in body["combos"])


def test_goldens_check_starts_a_job_over_the_parts_cases(client, ldraw_dir):
    """`3005` is in three combos and its goldens are frozen, so a check that
    reports nothing -- or reports `missing` -- is the route not working. A
    bare `states <= {...}` passes on an empty result and observes neither."""
    body = client.post("/api/goldens/check", json={"part": "3005"}).json()
    assert body["count"] == 3
    done = _finish(client, body["job"], timeout=600)
    assert done["state"] == "done"
    assert [r["state"] for r in done["results"]] == ["match"] * 3


def test_goldens_check_names_each_case(client, ldraw_dir):
    body = client.post("/api/goldens/check", json={"part": "3005"}).json()
    done = _finish(client, body["job"], timeout=600)
    assert all(r["case"].endswith("__3005") for r in done["results"])


def test_goldens_check_on_a_part_with_no_cases_is_an_empty_job(client):
    body = client.post("/api/goldens/check", json={"part": "not-a-part"}).json()
    done = _finish(client, body["job"])
    assert done["total"] == 0
