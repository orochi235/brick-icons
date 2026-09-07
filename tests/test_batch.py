import json
import os
import signal
import time
from pathlib import Path

from brick_icons import batch


def _spin(_):
    while True:
        pass


def test_a_timeout_is_a_row_not_the_end_of_the_run(tmp_path):
    log = tmp_path / "out.jsonl"
    runner = batch.Runner(log, timeout=0.2)
    done = [runner.run(item, _spin if item == "b" else (lambda i: {"item": i}))
            for item in ("a", "b", "c")]
    assert [d["item"] for d in done] == ["a", "b", "c"]
    assert ["error" in d for d in done] == [False, True, False]
    assert done[1]["error"] == "TimeoutError"
    assert [json.loads(l)["item"] for l in log.read_text().splitlines()] == \
        ["a", "b", "c"]


def test_resume_skips_what_is_done_and_buries_what_crashed(tmp_path):
    log = tmp_path / "out.jsonl"
    log.write_text(json.dumps({"item": "a"}) + "\n")
    (tmp_path / "out.jsonl.inflight").write_text("b")
    runner = batch.Runner(log, timeout=0)
    assert runner.remaining(["a", "b", "c"]) == ["c"]
    rows = [json.loads(l) for l in log.read_text().splitlines()]
    assert rows[-1] == {"item": "b", "error": "ProcessDied",
                        "detail": "killed mid-render; not retried"}


def test_every_row_carries_the_run_wide_fields(tmp_path):
    """The census keys measurements by engine, so a row it writes without one
    -- a crash burial especially -- cannot be imported."""
    log = tmp_path / "out.jsonl"
    (tmp_path / "out.jsonl.inflight").write_text("b")
    runner = batch.Runner(log, key="part", extra={"engine": "occt"})
    assert runner.remaining(["a", "b"]) == ["a"]
    runner.run("a", lambda p: {"part": p})
    rows = [json.loads(l) for l in log.read_text().splitlines()]
    assert [r["part"] for r in rows] == ["b", "a"]
    assert [r["engine"] for r in rows] == ["occt", "occt"]


def test_a_raising_item_is_a_row_and_the_inflight_marker_is_cleared(tmp_path):
    log = tmp_path / "out.jsonl"
    runner = batch.Runner(log)

    def boom(_):
        raise RuntimeError("no such part")

    row = runner.run("a", boom)
    assert row["error"] == "RuntimeError"
    assert row["detail"] == "no such part"
    assert not (tmp_path / "out.jsonl.inflight").exists()


def test_a_retry_pass_picks_up_what_failed_but_not_what_crashed(tmp_path):
    """A timeout under contention is worth another pass at a bigger cap; a part
    that killed the interpreter is not, and retrying it loops the run forever."""
    log = tmp_path / "out.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"item": "done"},
        {"item": "slow", "error": "TimeoutError"},
        {"item": "broke", "error": "RuntimeError"},
        {"item": "fatal", "error": "ProcessDied"},
    ]) + "\n")
    runner = batch.Runner(log)
    every = ["done", "slow", "broke", "fatal", "fresh"]
    assert runner.remaining(every) == ["fresh"]
    assert runner.remaining(every, retry_errors=True) == \
        ["slow", "broke", "fresh"]


def test_a_retry_that_succeeded_is_not_retried_again(tmp_path):
    """A retry appends a row rather than replacing the failed one, so the log
    holds both. The later success is what counts."""
    log = tmp_path / "out.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        {"item": "slow", "error": "TimeoutError"},
        {"item": "slow"},
    ]) + "\n")
    assert batch.Runner(log).remaining(["slow"], retry_errors=True) == []


def _deaf(_):
    """An item the in-process cap cannot stop, which is what OCCT's HLR is: it
    spends its whole life inside one C call, so SIGALRM -- delivered only
    between bytecodes -- is never seen."""
    signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
    while True:
        time.sleep(0.05)


def test_isolate_stops_an_item_the_alarm_cannot(tmp_path):
    log = tmp_path / "out.jsonl"
    runner = batch.Runner(log, timeout=1, isolate=True)
    row = runner.run("deaf", _deaf)
    assert row["error"] == "TimeoutError"
    assert "process group killed" in row["detail"]
    assert not (tmp_path / "out.jsonl.inflight").exists()


def test_isolate_takes_a_forked_grandchild_with_it(tmp_path):
    """`occt._unify_survives` forks. A kill aimed at the child alone leaves that
    grandchild running, reparented to init, still allocating and unwatched --
    which is how a census node ends up with renders nothing can stop."""
    marker = tmp_path / "grandchild.pid"

    def forks(_):
        pid = os.fork()
        if pid == 0:
            marker.write_text(str(os.getpid()))
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
            while True:
                time.sleep(0.05)
        os.waitpid(pid, 0)      # the parent blocks here, as _unify_survives does
        return {"item": "forks"}

    runner = batch.Runner(tmp_path / "out.jsonl", timeout=1, isolate=True)
    assert runner.run("forks", forks)["error"] == "TimeoutError"
    grandchild = int(marker.read_text())
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(grandchild, 0)
        except OSError:
            return
        time.sleep(0.05)
    raise AssertionError(f"grandchild {grandchild} outlived the kill")


def test_isolate_keeps_the_run_going_when_an_item_kills_its_process(tmp_path):
    """Without isolation this ends the batch and every part after it is absent
    from the census rather than failed in it."""
    log = tmp_path / "out.jsonl"
    runner = batch.Runner(log, timeout=5, isolate=True)
    rows = [runner.run(i, (lambda _: os.kill(os.getpid(), signal.SIGKILL))
                       if i == "b" else (lambda x: {"item": x}))
            for i in ("a", "b", "c")]
    assert [r["item"] for r in rows] == ["a", "b", "c"]
    assert rows[1]["error"] == "ProcessDied"
    assert [json.loads(l)["item"] for l in log.read_text().splitlines()] == \
        ["a", "b", "c"]


def test_isolate_returns_a_row_bigger_than_the_pipe_buffer(tmp_path):
    """A census row carries every diff component the compare found. If the
    parent waits before it reads, the child blocks writing and both hang."""
    big = [{"n": i, "box": [i, i, i, i]} for i in range(20000)]
    runner = batch.Runner(tmp_path / "out.jsonl", timeout=30, isolate=True)
    row = runner.run("big", lambda i: {"item": i, "missing": big})
    assert "error" not in row
    assert row["missing"] == big


def test_isolate_kills_a_group_that_outgrows_the_memory_cap(tmp_path):
    """Darwin honours no memory rlimit -- setrlimit(RLIMIT_AS) fails with
    EINVAL at every value -- so the cap is the parent watching `ps`. Without it
    a single render reaches 4GB in a minute and twelve of them fill the swap."""
    def hog(_):
        signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        held = []
        while True:
            held.append(bytearray(64 << 20))
            for i in range(0, len(held[-1]), 4096):
                held[-1][i] = 1
            time.sleep(0.02)

    runner = batch.Runner(tmp_path / "out.jsonl", timeout=120, isolate=True,
                          mem_gb=1)
    started = time.time()
    row = runner.run("hog", hog)
    assert row["error"] == "MemoryError", row
    assert "1GB" in row["detail"]
    assert time.time() - started < 60      # the cap, not the 120s timeout


def test_the_render_store_isolates_and_caps_memory(monkeypatch, tmp_path):
    """A store run is unattended for hours on a shared node, and its --timeout
    is setitimer, whose handler runs only between bytecodes -- an occt render
    stuck inside one OCP call ignores it while it keeps allocating. Runner
    already carries the fork + external watchdog 18310b7 built for the census;
    the store has to ask for them."""
    import importlib
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    store = importlib.import_module("build-render-store")
    seen = {}

    class FakeRunner:
        def __init__(self, log, **kw):
            seen.update(kw)

        def remaining(self, ids, retry_errors=False):
            return []

    monkeypatch.setattr(store, "Runner", FakeRunner)
    store.main(["3001", "--sources", "occt", "--log", str(tmp_path / "l.jsonl"),
                "--db", str(tmp_path / "c.db")])
    assert seen["isolate"] is True
    assert seen["mem_gb"] > 0
