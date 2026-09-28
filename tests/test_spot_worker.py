"""The spot render worker draws what the CLI draws."""
import time

from brick_icons import cli, db, spot_protocol, spot_worker


def _req(part="3005", source="naive"):
    return spot_protocol.request(part, source, db.canonical_argv(part, source),
                                 build="b")


def test_a_request_draws_the_same_bytes_as_the_cli(tmp_path, ldraw_dir):
    reply = spot_worker.render(_req())
    assert reply["error"] is None, reply["detail"]
    assert reply["state"] == "drawn"
    out = tmp_path / "cli"
    assert cli.main([*db.canonical_argv("3005", "naive"), "--out", str(out)]) == 0
    (svg,) = out.glob("*.svg")
    assert reply["svg"] == svg.read_text()
    assert spot_protocol.check_reply(reply) is reply


def test_a_part_past_the_cap_is_a_timeout_reply(monkeypatch):
    monkeypatch.setattr(spot_worker.lab_runner, "draw",
                        lambda argv, out: time.sleep(30))
    started = time.time()
    reply = spot_worker.render(_req(), timeout=0.5)
    assert time.time() - started < 10
    assert (reply["error"], reply["state"], reply["svg"]) == \
        ("TimeoutError", None, None)


def test_an_engine_error_is_named_in_the_reply(monkeypatch):
    def boom(argv, out):
        raise ValueError("boom")
    monkeypatch.setattr(spot_worker.lab_runner, "draw", boom)
    reply = spot_worker.render(_req())
    assert (reply["error"], reply["detail"]) == ("ValueError", "boom")


def test_a_decal_with_nothing_to_draw_is_a_none_reply(monkeypatch):
    monkeypatch.setattr(spot_worker.lab_runner, "draw", lambda argv, out: None)
    reply = spot_worker.render(_req("3005", "decal"))
    assert (reply["state"], reply["svg"], reply["error"]) == ("none", None, None)


def test_the_reply_names_the_build_that_drew_it(monkeypatch):
    import brick_icons
    monkeypatch.setattr(spot_worker.lab_runner, "draw", lambda argv, out: None)
    assert spot_worker.render(_req("3005", "decal"))["build"] == brick_icons.build()


def test_the_pool_holds_two_workers_by_default():
    assert spot_worker.POOL == 2
