import pytest

from brick_icons.lab import __main__ as lab_main


@pytest.fixture
def ran(monkeypatch):
    """What `main` handed uvicorn, with no server started."""
    seen = {}
    monkeypatch.setattr(lab_main.uvicorn, "run",
                        lambda *a, **k: seen.update(k))
    monkeypatch.setattr(lab_main, "create_app", lambda root: object())
    return seen


def test_requests_are_logged_by_default(ran):
    assert lab_main.main([]) == 0
    assert ran["access_log"] is True


def test_quiet_leaves_requests_out_of_the_log(ran):
    assert lab_main.main(["--quiet"]) == 0
    assert ran["access_log"] is False


def test_quiet_holds_under_reload(ran):
    assert lab_main.main(["--reload", "--quiet"]) == 0
    assert ran["access_log"] is False
