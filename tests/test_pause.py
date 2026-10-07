"""A part's cap counts only time onto did not have the job stopped."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from brick_icons import batch, pause


@pytest.fixture
def paused(tmp_path, monkeypatch):
    """onto's $ONTO_PAUSED file, holding 0 stopped seconds so far."""
    path = tmp_path / "paused"
    path.write_text("0\n")
    monkeypatch.setenv("ONTO_PAUSED", str(path))
    return path


def _stopped_for(paused: Path, secs: int, runs: float):
    """Work that reports `secs` of pause partway through and runs `runs`
    seconds of wall time in all, as a part onto stopped would."""
    def work(item):
        end = time.time() + runs
        time.sleep(0.1)
        paused.write_text(f"{secs}\n")
        while time.time() < end:
            time.sleep(0.02)
        return {"item": item}
    return work


def _spin(_):
    while True:
        time.sleep(0.02)


def test_a_stop_onto_reports_moves_the_cap_out(paused, tmp_path):
    runner = batch.Runner(tmp_path / "out.jsonl", timeout=0.6)
    row = runner.run("a", _stopped_for(paused, 1, runs=1.2))
    assert "error" not in row, row
    assert row["secs"] < 0.6        # the stopped second is not run time


def test_an_isolated_part_moves_its_cap_out_too(paused, tmp_path):
    runner = batch.Runner(tmp_path / "out.jsonl", timeout=0.6, isolate=True)
    row = runner.run("a", _stopped_for(paused, 1, runs=1.2))
    assert "error" not in row, row


def test_the_parent_kill_moves_out_for_a_part_the_alarm_cannot_stop(
        paused, tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "_GRACE", 0.2)

    def deaf(item):
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        return _stopped_for(paused, 2, runs=1.5)(item)

    runner = batch.Runner(tmp_path / "out.jsonl", timeout=0.5, isolate=True)
    row = runner.run("a", deaf)
    assert "error" not in row, row


@pytest.mark.parametrize("isolate", [False, True])
def test_a_real_timeout_still_fires_under_onto(paused, tmp_path, isolate):
    runner = batch.Runner(tmp_path / "out.jsonl", timeout=0.4, isolate=isolate)
    started = time.time()
    row = runner.run("a", _spin)
    assert row["error"] == "TimeoutError"
    assert time.time() - started < 3


def test_unset_reads_as_nothing_stopped(monkeypatch):
    monkeypatch.delenv("ONTO_PAUSED", raising=False)
    assert pause.paused_seconds() == 0


_BATCH = """
import sys, time
from brick_icons import batch
ticks = sys.argv[1]
def work(item):
    for _ in range(20):
        with open(ticks, "a") as fh:
            fh.write("x")
        time.sleep(0.1)
    return {"item": item}
row = batch.Runner(None, timeout=3.5, isolate=True).call("a", work)
print(row.get("error", "ok"), row["secs"])
"""


def _tree(root: int) -> list[int]:
    """`root` and every process descended from it, whatever group each is in."""
    out = subprocess.run(["ps", "-ax", "-o", "pid=,ppid="],
                         capture_output=True, text=True).stdout
    kids: dict[int, list[int]] = {}
    for line in out.splitlines():
        pid, ppid = map(int, line.split())
        kids.setdefault(ppid, []).append(pid)
    tree, todo = [], [root]
    while todo:
        pid = todo.pop()
        tree.append(pid)
        todo.extend(kids.get(pid, []))
    return tree


def _signal_tree(pids: list[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def test_an_onto_pause_spends_none_of_an_isolated_parts_cap(tmp_path):
    """onto stops the whole tree, writes the new total, then continues it. The
    render's own alarm and the parent's kill deadline both sit through the
    stop, and each has to give the stopped seconds back."""
    ticks, counter = tmp_path / "ticks", tmp_path / "paused"
    counter.write_text("0\n")
    env = {**os.environ, "ONTO_PAUSED": str(counter),
           "PYTHONPATH": str(Path(batch.__file__).parents[1])}
    proc = subprocess.Popen([sys.executable, "-c", _BATCH, str(ticks)], env=env,
                            stdout=subprocess.PIPE, text=True,
                            start_new_session=True)
    try:
        while not ticks.exists() or ticks.stat().st_size < 3:
            time.sleep(0.05)
        tree = _tree(proc.pid)
        assert len(tree) > 1                # the isolated render is in it
        _signal_tree(tree, signal.SIGSTOP)
        before = ticks.stat().st_size
        time.sleep(2.5)
        during = ticks.stat().st_size - before
        counter.write_text("2\n")
        _signal_tree(tree, signal.SIGCONT)
        out, _ = proc.communicate(timeout=20)
    finally:
        if proc.poll() is None:
            _signal_tree(_tree(proc.pid), signal.SIGKILL)
    assert during == 0
    verdict, secs = out.split()
    assert verdict == "ok"
    assert float(secs) < 3.5
