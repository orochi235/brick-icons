"""What the lab and the spot worker say to each other."""
import io
import json

import pytest

from brick_icons import spot_protocol as sp


def test_a_request_carries_what_the_worker_needs():
    req = sp.request("3001", "occt", ["3001", "--engine", "occt"],
                     build="7.abc1234")
    assert req == {"part": "3001", "source": "occt",
                   "argv": ["3001", "--engine", "occt"], "build": "7.abc1234"}


def test_a_ping_is_told_apart_from_a_render():
    assert sp.is_ping(sp.ping())
    assert not sp.is_ping(sp.request("3001", "occt", [], "b"))
    assert sp.pong("7.abc1234") == {"pong": True, "build": "7.abc1234"}


def test_a_drawn_reply_passes_the_check():
    got = sp.reply(svg="<svg/>", secs=1.2, build="7.abc1234", state="drawn")
    assert sp.check_reply(got) == {"svg": "<svg/>", "secs": 1.2,
                                   "build": "7.abc1234", "state": "drawn",
                                   "error": None, "detail": None}


def test_a_failed_reply_needs_no_state():
    got = sp.reply(secs=150.0, build="b", error="TimeoutError",
                   detail="exceeded 150s")
    assert sp.check_reply(got)["state"] is None


def test_the_check_ignores_the_id_onto_echoes():
    got = {"id": "onto-7", **sp.reply(build="b", state="none")}
    assert sp.check_reply(got) is got


@pytest.mark.parametrize("bad", [
    None,
    {"svg": "<svg/>"},
    {**sp.reply(build="b", state="drawn"), "svg": None},
    {**sp.reply(build="b", state="sideways")},
])
def test_a_malformed_reply_is_refused(bad):
    with pytest.raises(ValueError):
        sp.check_reply(bad)


def test_a_request_line_is_split_into_onto_s_id_and_the_request():
    line = json.dumps({"id": "onto-7", "commit": "c" * 40,
                       **sp.request("3001", "occt", ["3001"], "b")})
    ((rid, req),) = list(sp.read(io.StringIO(line + "\n")))
    assert rid == "onto-7"
    assert req["part"] == "3001" and "id" not in req


def test_a_line_that_is_not_an_object_is_a_bad_request():
    got = list(sp.read(io.StringIO("{not json\n[1, 2]\n\n")))
    assert got == [(None, None), (None, None)]


def test_a_reply_echoes_its_id_on_one_line():
    out = io.StringIO()
    sp.write(out, "onto-7", sp.pong("b"))
    assert out.getvalue() == '{"id": "onto-7", "pong": true, "build": "b"}\n'
