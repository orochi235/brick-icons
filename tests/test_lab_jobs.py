import threading
import time

from brick_icons.lab import jobs


def _wait(registry, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if registry.get(job_id)["state"] in ("done", "failed", "cancelled"):
            return registry.get(job_id)
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_a_job_runs_and_reports_done():
    r = jobs.Registry()
    job_id = r.start("test", ["a", "b"], lambda item, emit, cancel: emit(f"did {item}"))
    assert _wait(r, job_id)["state"] == "done"


def test_progress_carries_position_out_of_total():
    r = jobs.Registry()
    job_id = r.start("test", ["a", "b"], lambda item, emit, cancel: emit(item))
    _wait(r, job_id)
    events = r.get(job_id)["events"]
    assert [(e["index"], e["total"]) for e in events] == [(1, 2), (2, 2)]


def test_an_item_failure_is_an_event_not_a_stopped_job():
    def work(item, emit, cancel):
        if item == "a":
            raise RuntimeError("boom")
        emit(item)
    r = jobs.Registry()
    job_id = r.start("test", ["a", "b"], work)
    result = _wait(r, job_id)
    assert result["state"] == "done"
    assert result["failed"] == 1
    assert "boom" in result["events"][0]["message"]


def test_cancelling_stops_before_the_next_item():
    started = []

    def work(item, emit, cancel):
        started.append(item)
        time.sleep(0.05)
        emit(item)

    r = jobs.Registry()
    job_id = r.start("test", list("abcdefgh"), work)
    time.sleep(0.06)
    r.cancel(job_id)
    result = _wait(r, job_id)
    assert result["state"] == "cancelled"
    assert len(started) < 8


def test_what_work_returns_is_collected():
    r = jobs.Registry()
    job_id = r.start("test", ["a", "b"],
                     lambda item, emit, cancel: {"item": item})
    assert _wait(r, job_id)["results"] == [{"item": "a"}, {"item": "b"}]


def test_an_unknown_job_id_reads_as_none():
    assert jobs.Registry().get("nope") is None


def test_work_can_watch_the_cancellation():
    """A render long enough to be worth cancelling is one item, so a job that
    only checked between items would run it to the end and throw it away."""
    saw_it = threading.Event()

    def work(item, emit, cancel):
        while not cancel.is_set():
            time.sleep(0.01)
        saw_it.set()

    r = jobs.Registry()
    job_id = r.start("test", ["only"], work)
    time.sleep(0.05)
    r.cancel(job_id)
    assert _wait(r, job_id)["state"] == "cancelled"
    assert saw_it.is_set()
