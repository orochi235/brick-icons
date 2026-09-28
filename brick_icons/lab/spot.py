"""The lab's line to the spot render worker, through `onto call`.

Every assumption about onto's CLI is a constant here (onto's services guide,
"Calling it"), so a change on onto's side changes this file and nothing else.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Callable

from .. import batch, build_of, commit_of, spot_protocol

BAD_REQUEST_EXIT = 65
DOWN_EXIT = 69
#: The process exited before replying; onto restarts it, and one retry is safe.
DIED_EXIT = 75
ROLL_FAILED_EXIT = 78
TIMEOUT_EXIT = 124
TIMEOUT_FLAG = "--timeout"
COMMIT_FLAG = "--commit"
#: How long a redraw may wait on a roll to a new commit (onto measured 1.1 s).
ROLL_WAIT_S = 30
CALL_TIMEOUT_S = batch.RENDER_TIMEOUT_S + ROLL_WAIT_S + 15
PING_TIMEOUT_S = 5
#: Past onto's own timeout, before the lab stops waiting for onto itself.
SLACK_S = 10
#: The revision the worker is told to draw at: pushed work only.
REVISION = "origin/main"
#: Where onto lives when the lab's own PATH does not carry it (launchd, etc).
ONTO_FALLBACK = "~/.local/bin/onto"

_FAILURES = {BAD_REQUEST_EXIT: "BadRequest", ROLL_FAILED_EXIT: "RollFailed",
             TIMEOUT_EXIT: "TimeoutError", DIED_EXIT: "ProcessDied"}


class SpotDown(Exception):
    """The service is not there to ask. Nothing was tried."""


class SpotError(Exception):
    """onto answered, but with no reply from the worker. `error` names why,
    as a reply's `error` would: `RollFailed`, `TimeoutError`, ..."""

    def __init__(self, detail: str, error: str = "SpotError"):
        super().__init__(detail)
        self.error = error


def _origin_main() -> tuple[str | None, str]:
    return commit_of(REVISION), build_of(REVISION)


def _find_onto() -> str | None:
    import os
    return shutil.which("onto") or (
        os.path.expanduser(ONTO_FALLBACK)
        if os.path.exists(os.path.expanduser(ONTO_FALLBACK)) else None)


class OntoSpot:
    def __init__(self, onto: str | None = None,
                 expected: Callable[[], tuple[str | None, str]] = _origin_main):
        self.onto = onto
        self.expected = expected
        self.slack_s = SLACK_S

    def _once(self, request: dict, timeout: float,
              commit: str | None) -> subprocess.CompletedProcess:
        onto = self.onto or _find_onto()
        if onto is None:
            raise SpotDown("onto is not on the lab's PATH")
        argv = [onto, "call", TIMEOUT_FLAG, f"{int(timeout)}s",
                *([COMMIT_FLAG, commit] if commit else []),
                spot_protocol.NAME, "-"]
        try:
            return subprocess.run(argv, input=json.dumps(request),
                                  capture_output=True, text=True,
                                  timeout=timeout + self.slack_s)
        except FileNotFoundError:
            raise SpotDown(f"no onto at {onto}") from None
        except PermissionError:
            raise SpotDown(f"onto at {onto} is not executable") from None
        except subprocess.TimeoutExpired:
            raise SpotError(f"no reply in {int(timeout)}s",
                            "TimeoutError") from None

    def call(self, request: dict, timeout: float, commit: str | None) -> dict:
        got = self._once(request, timeout, commit)
        if got.returncode == DIED_EXIT:
            got = self._once(request, timeout, commit)
        said = got.stderr.strip()
        if got.returncode == DOWN_EXIT:
            raise SpotDown(said or "the spot render service is down")
        if got.returncode != 0:
            raise SpotError(said or f"onto call exited {got.returncode}",
                            _FAILURES.get(got.returncode, "SpotError"))
        try:
            return json.loads(got.stdout)
        except json.JSONDecodeError:
            raise SpotError(f"onto call printed no JSON: {got.stdout[:200]!r}") from None

    def draw(self, request: dict, commit: str | None) -> dict:
        try:
            return spot_protocol.check_reply(
                self.call(request, CALL_TIMEOUT_S, commit))
        except ValueError as e:
            raise SpotError(str(e)) from None

    def status(self) -> dict:
        """Asked without a commit, so asking never rolls the worker."""
        _commit, want = self.expected()
        try:
            got = self.call(spot_protocol.ping(), PING_TIMEOUT_S, commit=None)
        except (SpotDown, SpotError) as e:
            return {"state": "down", "build": None, "want": want, "detail": str(e)}
        built = got.get("build") if isinstance(got, dict) else None
        return {"state": "up" if built == want else "stale", "build": built,
                "want": want, "detail": None}


def status_line(status: dict) -> str:
    if status["state"] == "down":
        return f"down: {status['detail']}"
    if status["state"] == "stale":
        return (f"up at {status['build']}, rolls to {status['want']} "
                f"on the next redraw")
    return f"up at {status['build']}"
