"""The spot render worker draws what the CLI draws."""
import io
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest

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


def _lines(*requests):
    return io.StringIO("".join(json.dumps(r) + "\n" for r in requests))


def test_two_requests_draw_at_once_and_each_reply_names_its_request():
    together = threading.Barrier(2, timeout=5)

    def answer(req):
        together.wait()
        return spot_protocol.reply(svg=f"<svg id='{req['part']}'/>", secs=0.1,
                                   build="b", state="drawn")

    out = io.StringIO()
    with ThreadPoolExecutor(spot_worker.POOL) as pool:
        spot_worker.serve(_lines({"id": "onto-1", **_req("3001")},
                                 {"id": "onto-2", **_req("3002")}),
                          out, pool, answer)
    replies = {r["id"]: r for r in map(json.loads, out.getvalue().splitlines())}
    assert replies["onto-1"]["svg"] == "<svg id='3001'/>"
    assert replies["onto-2"]["svg"] == "<svg id='3002'/>"


def test_a_ping_is_answered_without_the_pool():
    import brick_icons
    out = io.StringIO()
    with ThreadPoolExecutor(1) as pool:
        spot_worker.serve(_lines({"id": "p", **spot_protocol.ping()}),
                          out, pool, lambda req: 1 / 0)
    (line,) = out.getvalue().splitlines()
    assert json.loads(line) == {"id": "p", **spot_protocol.pong(brick_icons.build())}


def test_a_line_that_is_not_json_is_answered_not_fatal():
    out = io.StringIO()
    with ThreadPoolExecutor(1) as pool:
        spot_worker.serve(io.StringIO("{not json\n"), out, pool, lambda r: None)
    (line,) = out.getvalue().splitlines()
    got = json.loads(line)
    assert (got["id"], got["error"]) == (None, "BadRequest")


def test_a_render_that_raises_in_the_pool_is_a_reply():
    def die(req):
        raise RuntimeError("pool gone")
    out = io.StringIO()
    with ThreadPoolExecutor(1) as pool:
        spot_worker.serve(_lines({"id": "onto-1", **_req()}), out, pool, die)
    reply = json.loads(out.getvalue())
    assert (reply["error"], reply["detail"]) == ("RuntimeError", "pool gone")


def test_a_reply_that_cannot_be_written_still_answers_once_with_an_error():
    def answer(req):
        return spot_protocol.reply(svg="<svg/>", secs=float("nan"), build="b",
                                   state="drawn")
    out = io.StringIO()
    with ThreadPoolExecutor(1) as pool:
        spot_worker.serve(_lines({"id": "onto-1", **_req()}), out, pool, answer)
    lines = out.getvalue().splitlines()
    assert len(lines) == 1
    got = json.loads(lines[0])
    assert got["id"] == "onto-1"
    assert got["error"] is not None


class _DeadPool:
    """A pool whose `submit` fails the way a `ProcessPoolExecutor` does once
    a worker process has died."""

    def submit(self, fn, req):
        raise BrokenProcessPool("a worker process died")


def test_a_broken_pool_answers_the_request_and_signals_serve_stops():
    out = io.StringIO()
    with pytest.raises(BrokenProcessPool):
        spot_worker.serve(_lines({"id": "onto-1", **_req()}), out, _DeadPool(),
                          spot_worker.render)
    reply = json.loads(out.getvalue())
    assert (reply["id"], reply["error"]) == ("onto-1", "BrokenProcessPool")


def test_the_module_answers_a_ping_on_a_clean_stdout():
    repo = Path(__file__).resolve().parent.parent
    got = subprocess.run(
        [sys.executable, "-m", "brick_icons.spot_worker"],
        input=json.dumps({"id": "p", **spot_protocol.ping()}) + "\n",
        capture_output=True, text=True, timeout=60, cwd=repo,
        env={**os.environ, "PYTHONPATH": str(repo)})
    assert got.returncode == 0, got.stderr
    (line,) = got.stdout.splitlines()
    assert json.loads(line)["pong"] is True
