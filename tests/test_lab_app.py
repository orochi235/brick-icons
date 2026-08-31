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
