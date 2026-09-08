"""A lab render is the CLI's render: same parser, same Config, same
process_one. Anything else and the app drifts from the command line."""
import multiprocessing
import os
import signal
import threading
import time

from brick_icons.lab import runner


def test_runs_and_writes_an_svg(tmp_path, ldraw_dir):
    result = runner.render(["3005", "--format", "svg", "--shading", "outline"],
                           root=tmp_path)
    assert result["ok"]
    assert "3005.svg" in {a["name"] for a in result["artifacts"]}
    assert result["seconds"] > 0


def test_reports_the_argv_it_actually_ran(tmp_path, ldraw_dir):
    argv = ["3005", "--format", "svg", "--shading", "outline"]
    result = runner.render(argv, root=tmp_path)
    assert result["argv"] == argv
    assert result["command"].startswith("brick-icons 3005 ")


def test_second_run_is_served_from_cache(tmp_path, ldraw_dir):
    argv = ["3005", "--format", "svg", "--shading", "outline"]
    first = runner.render(argv, root=tmp_path)
    second = runner.render(argv, root=tmp_path)
    assert first["cached"] is False
    assert second["cached"] is True


def test_force_reruns_a_cached_render(tmp_path, ldraw_dir):
    argv = ["3005", "--format", "svg", "--shading", "outline"]
    runner.render(argv, root=tmp_path)
    again = runner.render(argv, root=tmp_path, force=True)
    assert again["cached"] is False


def test_a_bad_flag_is_an_error_not_a_crash(tmp_path):
    result = runner.render(["3005", "--nonsense"], root=tmp_path)
    assert result["ok"] is False
    assert "nonsense" in result["error"]


def test_a_missing_part_is_an_error(tmp_path, ldraw_dir):
    result = runner.render(["definitely-not-a-part"], root=tmp_path)
    assert result["ok"] is False
    assert result["error"]


def test_the_render_runs_in_a_child_process(tmp_path, ldraw_dir):
    result = runner.render(["3005", "--format", "svg", "--shading", "outline"],
                           root=tmp_path)
    assert result["ok"]
    assert result["pid"] and result["pid"] != os.getpid()


def test_a_render_process_that_dies_is_an_error():
    """A native crash sends nothing back, so the exit code is the only report
    there is. Reaching it needs the child to die without writing the pipe."""
    proc, conn, _send = _child_process(os._exit, (3,))
    outcome = runner._collect(proc, conn, None)
    assert outcome["ok"] is False
    assert "3" in outcome["error"]


def test_a_signal_death_is_named_by_its_signal():
    assert "SIGSEGV" in runner._death(-signal.SIGSEGV)


def test_cancelling_kills_the_render_process():
    proc, conn, _send = _child_process(time.sleep, (120,))
    cancel = threading.Event()
    cancel.set()
    outcome = runner._collect(proc, conn, cancel)
    assert outcome["ok"] is False
    assert outcome["cancelled"] is True
    assert not proc.is_alive()


def _child_process(target, args):
    """A child holding the write end. The caller keeps `send` alive: dropping
    it makes the read end report EOF, which is a death the child has not had."""
    ctx = multiprocessing.get_context("spawn")
    receive, send = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=target, args=args, daemon=True)
    proc.start()
    return proc, receive, send
