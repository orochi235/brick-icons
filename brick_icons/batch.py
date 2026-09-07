"""What a long unattended batch needs to survive itself.

A part that raises is a row and the run continues; a part that segfaults the
interpreter is named in a marker file and buried on the way back in, so a
resume cannot loop on it forever.
"""
from __future__ import annotations

import ctypes
import json
import os
import select
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

_ARMED = None

# Seconds the child keeps after its own cap before the parent kills it, so a
# part the in-process alarm can still stop reports its own TimeoutError rather
# than arriving as a bare signal.
_GRACE = 5.0

# How often the parent prices the child's process group. One `ps` costs ~3ms;
# a render that matters runs for seconds at least.
_MEM_POLL = 3.0

# phys_footprint out of proc_pid_rusage(2), flavour 0. Offsets: 16 bytes of
# uuid then ten uint64s, of which ri_phys_footprint is the eighth.
_RUSAGE_V0_SIZE = 96
_FOOTPRINT_OFFSET = 72
_libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)


def _phys_footprint(pid: int) -> int | None:
    """Bytes the kernel bills a process for, or None if it will not say.

    Not resident size. The compressor moves a runaway's pages out of resident
    without releasing them, so `ps -o rss=` reads a process holding 97 GB as
    1.2 GB and a cap watching it never fires -- which is how msb-uai had to be
    power cycled on 2026-09-07 under this module's own 8 GB cap.

    A syscall rather than a subprocess, so the reading still works on a machine
    too far gone to fork.
    """
    buf = ctypes.create_string_buffer(_RUSAGE_V0_SIZE)
    if _libc.proc_pid_rusage(ctypes.c_int(pid), ctypes.c_int(0),
                             ctypes.byref(buf)) != 0:
        return None
    return int.from_bytes(
        buf.raw[_FOOTPRINT_OFFSET:_FOOTPRINT_OFFSET + 8], "little")


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
                 extra: dict | None = None, isolate: bool = False,
                 mem_gb: float = 0):
        self.log = Path(log)
        self.inflight = Path(f"{self.log}.inflight")
        self.timeout = timeout
        self.key = key
        self.extra = dict(extra or {})
        self.isolate = isolate
        # Kilobytes, because `ps` reports kilobytes. Darwin accepts no memory
        # rlimit -- setrlimit(RLIMIT_AS) and setrlimit(RLIMIT_DATA) both fail
        # with EINVAL at any value, and `ulimit -d` the same -- so the cap has
        # to be enforced from outside the process it applies to.
        self.mem_kb = int(mem_gb * (1 << 20))
        if timeout:
            signal.signal(signal.SIGALRM, _on_alarm)

    def remaining(self, items: list[str], retry_errors: bool = False) -> list[str]:
        """`items` minus what the log already holds, with a crashed item
        recorded and dropped.

        `retry_errors` keeps the ones that timed out or raised -- worth another
        pass at a bigger cap or on a quieter box. It never returns a
        ProcessDied item: retrying what killed the interpreter loops forever.
        """
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
        done = set()
        for line in self.log.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            error = row.get("error")
            if retry_errors and error and error != "ProcessDied":
                continue  # a later row for the same item may still settle it
            done.add(row[self.key])
        return [i for i in items if i not in done]

    def pruned(self) -> bool:
        """True once onto has marked this job pruned.

        Call it BETWEEN items, never inside one: by then the finished item's
        row is written and `.inflight` is gone, so a resume counts it as done
        instead of burying it as ProcessDied."""
        marker = os.environ.get("ONTO_PRUNE")
        return bool(marker) and Path(marker).exists()

    def write(self, row: dict) -> None:
        with self.log.open("a") as fh:
            fh.write(json.dumps({**self.extra, **row}) + "\n")

    def run(self, item: str, work) -> dict:
        """`work(item)` under the cap. Its dict is returned and logged; a
        failure becomes a row naming the exception.

        Without `isolate` this is best effort: the alarm lands between Python
        bytecodes, so an item stuck inside a C call runs past it.
        """
        self.inflight.write_text(item)
        # onto reads this off the item's own stdout pipe and shows it as the
        # worker's label, so a batched item names the part in hand rather than
        # the one it started with. Consumed, not forwarded: it never reaches
        # the job log. Capped at 48 runes by onto.
        print(f"onto: item {item[:48]}", flush=True)
        started = time.time()
        row = self._isolated(item, work) if self.isolate else self._here(item, work)
        row = {**self.extra, **row}
        row["secs"] = round(time.time() - started, 1)
        self.write(row)
        self.inflight.unlink(missing_ok=True)
        return row

    def _here(self, item: str, work) -> dict:
        global _ARMED
        try:
            if self.timeout:
                _ARMED = self.timeout
                signal.setitimer(signal.ITIMER_REAL, self.timeout)
            return work(item)
        except BaseException as exc:  # an item must not end the run
            return {self.key: item, "error": type(exc).__name__,
                    "detail": str(exc)[:300],
                    "traceback": traceback.format_exc()[-1200:]}
        finally:
            if self.timeout:
                signal.setitimer(signal.ITIMER_REAL, 0)
                _ARMED = None

    def _isolated(self, item: str, work) -> dict:
        """`work(item)` in a forked child the parent can actually stop.

        `timeout` alone cannot stop an item that spends its whole life inside
        one C call -- OCCT's HLR runs for tens of minutes inside a single OCP
        call, delivering no bytecode boundary for SIGALRM to land on, and
        allocates gigabytes while it does. Only killing the process works.

        The child gets its own process group, and the kill goes to the group:
        `occt._unify_survives` forks a grandchild that outlives a kill aimed at
        the child alone, and an orphan with no parent left to reap it keeps
        rendering and keeps allocating with nothing watching it.
        """
        sys.stdout.flush()
        sys.stderr.flush()
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read_fd)
            try:
                os.setpgid(0, 0)
                row = self._here(item, work)
                try:
                    blob = json.dumps(row)
                except (TypeError, ValueError) as exc:
                    blob = json.dumps({self.key: item, "error": "UnserializableRow",
                                       "detail": str(exc)[:300]})
                with os.fdopen(write_fd, "w") as fh:
                    fh.write(blob)
            except BaseException:
                os._exit(1)
            os._exit(0)

        os.close(write_fd)
        # Both sides set the group: whichever runs first wins, and neither can
        # then send a kill to a group the child has not joined yet.
        try:
            os.setpgid(pid, pid)
        except OSError:
            pass
        blob, stopped = self._drain(read_fd, pid)
        # WNOHANG, not a blocking wait: _drain returns on a kill that did not
        # take, and blocking here would hang the batch on exactly the runaway
        # the cap exists to end. A child that survives is left to init.
        status = 0
        for _ in range(50):
            try:
                done, status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                break
            if done:
                break
            time.sleep(0.1)
        if blob:
            try:
                return json.loads(blob)
            except ValueError:
                pass
        if stopped == "time":
            return {self.key: item, "error": "TimeoutError",
                    "detail": f"exceeded {self.timeout}s inside a C call; "
                              "process group killed"}
        if stopped == "memory":
            return {self.key: item, "error": "MemoryError",
                    "detail": f"render process group passed {self.mem_kb >> 20}GB "
                              "resident and was killed"}
        signalled = os.WIFSIGNALED(status) and os.WTERMSIG(status)
        return {self.key: item, "error": "ProcessDied",
                "detail": f"render process died on signal {signalled}"
                          if signalled else
                          "render process exited without writing a result"}

    def _drain(self, fd: int, pid: int) -> tuple[bytes, str]:
        """Read the child's row until EOF, killing its group past either cap.

        Returns what it read and why it stopped: "" for the child finishing on
        its own, "time" or "memory" for a kill.

        Read and wait have to be the same loop. A row carries every diff
        component the compare found, which outgrows the pipe buffer, and a
        parent sitting in waitpid while the child blocks writing to a pipe
        nobody is reading deadlocks both, so the cap that was supposed to end
        it never fires.
        """
        deadline = time.monotonic() + self.timeout + _GRACE if self.timeout else None
        priced = 0.0
        chunks: list[bytes] = []
        stopped = ""
        try:
            while True:
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    if stopped:
                        # The kill did not take. Stop waiting on a pipe held by
                        # something we cannot end; the caller reaps what it can.
                        return b"".join(chunks), stopped
                    stopped = "time"
                    self._killpg(pid)
                    deadline = now + _GRACE   # collect a row it already wrote
                    continue
                if self.mem_kb and not stopped and now - priced >= _MEM_POLL:
                    priced = now
                    if self._group_kb(pid) > self.mem_kb:
                        stopped = "memory"
                        self._killpg(pid)
                        deadline = now + _GRACE
                        continue
                left = 1.0 if deadline is None else min(1.0, deadline - now)
                if not select.select([fd], [], [], max(left, 0.0))[0]:
                    continue
                buf = os.read(fd, 1 << 16)
                if not buf:
                    return b"".join(chunks), stopped
                chunks.append(buf)
        finally:
            os.close(fd)

    @staticmethod
    def _group_kb(pgid: int) -> int:
        """Billed kilobytes across the whole process group.

        The group, not the child: the runaway is as often the grandchild
        `occt._unify_survives` forks as the child that is waiting on it.

        The child's own reading comes from the kernel and always arrives. `ps`
        only adds the rest of the group, so a machine that has stopped being
        able to fork still gets a cap that fires -- it used to return 0 there,
        which reads as a render well under its limit.
        """
        own = _phys_footprint(pgid)
        total = 0 if own is None else own
        try:
            out = subprocess.run(["ps", "-o", "pid=,pgid=", "-ax"],
                                 capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return total >> 10
        for line in out.splitlines():
            fields = line.split()
            if len(fields) != 2 or fields[1] != str(pgid):
                continue
            pid = int(fields[0])
            if pid == pgid:
                continue  # already counted, and counted more reliably
            member = _phys_footprint(pid)
            if member is not None:
                total += member
        return total >> 10

    @staticmethod
    def _killpg(pid: int) -> None:
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
