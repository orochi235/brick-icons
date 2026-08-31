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
