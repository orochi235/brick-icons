"""The redraw log: what was asked for, when, and at which build."""
from brick_icons import requests


def test_a_request_is_read_back_as_written(tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt", at="2026-09-10T00:00:00+00:00")
    assert requests.load(log) == [{"part": "3001", "source": "occt",
                                   "at": "2026-09-10T00:00:00+00:00",
                                   "by": "lab"}]


def test_a_torn_line_does_not_break_the_log(tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt")
    with log.open("a") as fh:
        fh.write('{"part": "3004", "sour')
    assert [r["part"] for r in requests.load(log)] == ["3001"]


def test_no_log_is_no_requests(tmp_path):
    assert requests.load(tmp_path / "absent.jsonl") == []


def test_a_request_records_the_build_it_asked_for(tmp_path):
    log = tmp_path / "requests.jsonl"
    requests.add(log, "3001", "occt", build="9.ccccccc")
    (record,) = requests.load(log)
    assert record["build"] == "9.ccccccc"


def test_every_reference_slot_is_drawn_elsewhere():
    assert set(requests.DRAWN_ELSEWHERE) == {
        "reference", "reference-gray", "reference-lines"}


def test_the_queue_is_gone():
    for name in ("pending", "pending_for", "cost", "draws_here", "front_load",
                 "LOCAL_MAX_SECS"):
        assert not hasattr(requests, name), name
