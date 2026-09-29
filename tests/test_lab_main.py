import pytest

from brick_icons.lab import __main__ as lab_main


@pytest.fixture
def ran(monkeypatch):
    """What `main` handed uvicorn, with no server started."""
    seen = {}
    monkeypatch.setattr(lab_main, "_serve", lambda *a, **k: seen.update(k))
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


def test_the_lab_runs_on_its_own_server(monkeypatch):
    served = []

    def run(self, sockets=None):
        served.append(type(self))
        self.started = True

    monkeypatch.setattr(lab_main.Server, "run", run)
    lab_main._serve(object())
    assert served == [lab_main.Server]


def test_exits_3_when_startup_fails_outside_reload(monkeypatch):
    """`uvicorn.run` exits 3 when the server never started and it is not
    reloading; `_serve` must do the same instead of returning 0 to `main`."""
    monkeypatch.setattr(lab_main.Server, "run", lambda self, sockets=None: None)
    with pytest.raises(SystemExit) as exc:
        lab_main._serve(object())
    assert exc.value.code == 3
