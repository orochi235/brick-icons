"""The lab's adapter for `onto call`, against a fake onto."""
import json

import pytest

from brick_icons import spot_protocol as sp
from brick_icons.lab import spot

EXPECTED = ("c" * 40, "9.ccccccc")
REQ = sp.request("3001", "occt", ["3001"], "9.ccccccc")


def _onto(tmp_path, stdout="", code=0, stderr="", sleep=0, codes=None):
    """A fake onto: records its argv and stdin, then answers. `codes` is a
    sequence of exit statuses, one per call, for a retry test."""
    (tmp_path / "stdout").write_text(stdout)
    (tmp_path / "stderr").write_text(stderr)
    (tmp_path / "codes").write_text(" ".join(map(str, codes or [code])))
    script = tmp_path / "onto"
    script.write_text(
        "#!/bin/sh\n"
        f"for a in \"$@\"; do printf '%s\\n' \"$a\"; done > {tmp_path}/argv\n"
        f"cat > {tmp_path}/stdin\n"
        f"echo x >> {tmp_path}/calls\n"
        + (f"sleep {sleep}\n" if sleep else "")
        + f"n=$(wc -l < {tmp_path}/calls)\n"
        f"code=$(cut -d' ' -f$n {tmp_path}/codes)\n"
        f"[ -n \"$code\" ] || code=$(awk '{{print $NF}}' {tmp_path}/codes)\n"
        f"cat {tmp_path}/stdout\ncat {tmp_path}/stderr >&2\nexit $code\n")
    script.chmod(0o755)
    return spot.OntoSpot(onto=str(script), expected=lambda: EXPECTED)


def _drawn():
    return json.dumps({"id": "onto-1", **sp.reply(
        svg="<svg/>", secs=1.0, build="9.ccccccc", state="drawn")})


def test_a_call_sends_the_request_on_stdin_with_its_commit(tmp_path):
    client = _onto(tmp_path, stdout=_drawn())
    assert client.draw(REQ, commit="c" * 40)["svg"] == "<svg/>"
    argv = (tmp_path / "argv").read_text().splitlines()
    assert argv == ["call", spot.TIMEOUT_FLAG, f"{int(spot.CALL_TIMEOUT_S)}s",
                    spot.COMMIT_FLAG, "c" * 40, sp.NAME, "-"]
    assert json.loads((tmp_path / "stdin").read_text()) == REQ


def test_no_commit_means_no_roll(tmp_path):
    client = _onto(tmp_path, stdout=_drawn())
    client.draw(REQ, commit=None)
    assert spot.COMMIT_FLAG not in (tmp_path / "argv").read_text().splitlines()


def test_a_down_service_is_spot_down(tmp_path):
    client = _onto(tmp_path, code=spot.DOWN_EXIT, stderr="no such service")
    with pytest.raises(spot.SpotDown, match="no such service"):
        client.draw(REQ, commit=None)


def test_no_onto_at_all_is_spot_down(tmp_path):
    client = spot.OntoSpot(onto=str(tmp_path / "absent"), expected=lambda: EXPECTED)
    with pytest.raises(spot.SpotDown):
        client.draw(REQ, commit=None)


@pytest.mark.parametrize("code, error", [
    (spot.ROLL_FAILED_EXIT, "RollFailed"),
    (spot.TIMEOUT_EXIT, "TimeoutError"),
    (spot.BAD_REQUEST_EXIT, "BadRequest"),
    (1, "SpotError"),
])
def test_each_failure_names_itself_with_onto_s_words(tmp_path, code, error):
    client = _onto(tmp_path, code=code, stderr="roll to cccc failed: uv sync")
    with pytest.raises(spot.SpotError, match="uv sync") as got:
        client.draw(REQ, commit=None)
    assert got.value.error == error


def test_a_process_that_died_mid_request_is_asked_once_more(tmp_path):
    client = _onto(tmp_path, stdout=_drawn(), codes=[spot.DIED_EXIT, 0])
    assert client.draw(REQ, commit=None)["svg"] == "<svg/>"
    assert len((tmp_path / "calls").read_text().splitlines()) == 2


def test_a_process_that_dies_twice_is_a_failure(tmp_path):
    client = _onto(tmp_path, code=spot.DIED_EXIT, stderr="exited 139")
    with pytest.raises(spot.SpotError) as got:
        client.draw(REQ, commit=None)
    assert got.value.error == "ProcessDied"


def test_a_reply_that_is_not_json_is_a_spot_error(tmp_path):
    client = _onto(tmp_path, stdout="panic: nil map")
    with pytest.raises(spot.SpotError, match="no JSON"):
        client.draw(REQ, commit=None)


def test_a_malformed_reply_is_a_spot_error(tmp_path):
    client = _onto(tmp_path, stdout='{"svg": "<svg/>"}')
    with pytest.raises(spot.SpotError, match="not a spot reply"):
        client.draw(REQ, commit=None)


def test_onto_that_never_answers_is_a_timeout(tmp_path):
    client = _onto(tmp_path, sleep=5)
    client.slack_s = 0
    with pytest.raises(spot.SpotError) as got:
        client.call(sp.ping(), timeout=1, commit=None)
    assert got.value.error == "TimeoutError"


def test_status_is_up_when_the_worker_is_at_origin_main(tmp_path):
    client = _onto(tmp_path, stdout=json.dumps({"id": "p", **sp.pong("9.ccccccc")}))
    assert client.status() == {"state": "up", "build": "9.ccccccc",
                               "want": "9.ccccccc", "detail": None}
    assert spot.COMMIT_FLAG not in (tmp_path / "argv").read_text().splitlines()


def test_status_is_stale_when_a_redraw_would_roll_it(tmp_path):
    client = _onto(tmp_path, stdout=json.dumps(sp.pong("8.bbbbbbb")))
    assert client.status()["state"] == "stale"


def test_status_is_down_when_onto_cannot_reach_it(tmp_path):
    client = _onto(tmp_path, code=spot.DOWN_EXIT, stderr="studio offline")
    got = client.status()
    assert (got["state"], got["detail"]) == ("down", "studio offline")


@pytest.mark.parametrize("status, line", [
    ({"state": "up", "build": "9.c", "want": "9.c", "detail": None}, "up at 9.c"),
    ({"state": "stale", "build": "8.b", "want": "9.c", "detail": None},
     "up at 8.b, rolls to 9.c on the next redraw"),
    ({"state": "down", "build": None, "want": "9.c", "detail": "offline"},
     "down: offline"),
])
def test_status_reads_as_one_line(status, line):
    assert spot.status_line(status) == line
