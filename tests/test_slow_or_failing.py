"""The rerun list: newest row per part, slow or failing, within the window."""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from brick_icons import db

sof = importlib.import_module("slow-or-failing")


def _row(conn, run, pid, secs, error=None, source="occt"):
    conn.execute("INSERT INTO measurements (run_id, part_id, engine, source, "
                 "secs, error) VALUES (?, ?, 'occt', ?, ?, ?)",
                 (run, pid, source, secs, error))


def test_select_reads_each_parts_newest_row_in_the_window(tmp_path):
    conn = db.connect(tmp_path / "c.db")
    old = db.start_run(conn, "census", {"dir": "old"}, "a")
    conn.execute("UPDATE runs SET started = '2020-01-01T00:00:00+00:00' "
                 "WHERE id = ?", (old,))
    new = db.start_run(conn, "census", {"dir": "new"}, "b")
    _row(conn, old, "stale-fail", 5, "TimeoutError")   # outside the window
    _row(conn, old, "fixed", 5, "TimeoutError")
    _row(conn, new, "fixed", 10)                        # newest row drew fast
    _row(conn, old, "broke", 10)
    _row(conn, new, "broke", 300, "TimeoutError")
    _row(conn, new, "slow", 150)
    _row(conn, new, "slower", 250)
    _row(conn, new, "fast", 30)
    _row(conn, new, "other-slot", 290, source="white-occt")
    slow, failing = sof.select(conn, "occt", 24, 120)
    assert [p for p, _ in slow] == ["slower", "slow"]
    assert failing == [("broke", "TimeoutError")]
