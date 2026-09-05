"""What a long unattended batch needs to survive itself.

A part that raises is a row and the run continues; a part that segfaults the
interpreter is named in a marker file and buried on the way back in, so a
resume cannot loop on it forever.
"""
from __future__ import annotations

import json
import signal
import time
import traceback
from pathlib import Path

_ARMED = None


def _on_alarm(signum, frame):
    """Installed once and never removed: SIGALRM's default action is to KILL,
    so a timer that expires in the microseconds before the itimer is disarmed
    takes the whole run down silently. Ignoring a disarmed alarm is the fix."""
    if _ARMED:
        raise TimeoutError(f"exceeded {_ARMED}s")


class Runner:
    """One append-only JSONL log, one item at a time.

    `key` names the field an item is recorded under, so a caller whose rows are
    keyed by something other than `item` can say so. `extra` is merged into
    every row the runner writes itself, including a burial, so a consumer that
    requires a field finds it on the rows no work function produced.
    """

    def __init__(self, log: Path | str, timeout: float = 0, key: str = "item",
                 extra: dict | None = None):
        self.log = Path(log)
        self.inflight = Path(f"{self.log}.inflight")
        self.timeout = timeout
        self.key = key
        self.extra = dict(extra or {})
        if timeout:
            signal.signal(signal.SIGALRM, _on_alarm)

    def remaining(self, items: list[str]) -> list[str]:
        """`items` minus what the log already holds, with a crashed item
        recorded and dropped."""
        if self.inflight.exists():
            crashed = self.inflight.read_text().strip()
            if crashed:
                self.write({self.key: crashed, "error": "ProcessDied",
                            "detail": "killed mid-render; not retried"})
                print(f"recorded {crashed} as ProcessDied and skipping it",
                      flush=True)
            self.inflight.unlink()
        if not self.log.exists():
            return list(items)
        done = {json.loads(line)[self.key]
                for line in self.log.read_text().splitlines() if line.strip()}
        return [i for i in items if i not in done]

    def write(self, row: dict) -> None:
        with self.log.open("a") as fh:
            fh.write(json.dumps({**self.extra, **row}) + "\n")

    def run(self, item: str, work) -> dict:
        """`work(item)` under the cap. Its dict is returned and logged; a
        failure becomes a row naming the exception.

        Best effort: the alarm lands between Python bytecodes, so an item stuck
        inside a C call runs past it.
        """
        global _ARMED
        self.inflight.write_text(item)
        started = time.time()
        try:
            if self.timeout:
                _ARMED = self.timeout
                signal.setitimer(signal.ITIMER_REAL, self.timeout)
            row = work(item)
        except BaseException as exc:  # an item must not end the run
            row = {self.key: item, "error": type(exc).__name__,
                   "detail": str(exc)[:300],
                   "traceback": traceback.format_exc()[-1200:]}
        finally:
            if self.timeout:
                signal.setitimer(signal.ITIMER_REAL, 0)
                _ARMED = None
        row = {**self.extra, **row}
        row["secs"] = round(time.time() - started, 1)
        self.write(row)
        self.inflight.unlink(missing_ok=True)
        return row
