"""What the lab and the spot render worker say to each other, and how it
travels between onto's node agent and the worker process.

The framing is onto's (its services guide): one JSON object per line each
way. A request line is the caller's fields plus onto's `id`, and the reply
must echo that id. Requests may be answered in any order.
"""
from __future__ import annotations

import json
from typing import IO, Iterator

NAME = "brick-spot-render"
REPLY_KEYS = ("svg", "secs", "build", "state", "error", "detail")
#: `drawn` carries an SVG; `none` is a decal with nothing to draw.
STATES = ("drawn", "none")


def request(part: str, source: str, argv: list[str], build: str) -> dict:
    """`build` is the revision the lab expects, in `brick_icons.build()` form.
    The commit itself travels as `onto call --commit`, which rolls the
    service to it before this is delivered."""
    return {"part": part, "source": source, "argv": list(argv), "build": build}


def ping() -> dict:
    return {"ping": True}


def is_ping(req: dict) -> bool:
    return req.get("ping") is True


def pong(build: str) -> dict:
    return {"pong": True, "build": build}


def reply(*, build: str, svg: str | None = None, secs: float | None = None,
          state: str | None = None, error: str | None = None,
          detail: str | None = None) -> dict:
    """`error` is the exception's type name -- the wall reads `TimeoutError`
    as its own state -- and `detail` its message."""
    return {"svg": svg, "secs": secs, "build": build, "state": state,
            "error": error, "detail": detail}


def check_reply(obj) -> dict:
    """The reply, or ValueError saying what is wrong with it."""
    if not isinstance(obj, dict) or any(k not in obj for k in REPLY_KEYS):
        raise ValueError(f"not a spot reply: {obj!r:.200}")
    if obj["error"] is None and obj["state"] not in STATES:
        raise ValueError(f"a reply with no error has state {obj['state']!r}")
    if obj["state"] == "drawn" and not isinstance(obj["svg"], str):
        raise ValueError("a drawn reply carries no SVG")
    if obj["state"] == "none" and obj["svg"] is not None:
        raise ValueError("a none reply carries an SVG")
    return obj


def read(stream: IO[str]) -> Iterator[tuple[str | None, dict | None]]:
    """(onto's id, the request) per line. The request is None for a line
    that is not a JSON object, which the caller answers as a bad request."""
    for line in stream:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            yield None, None
            continue
        if not isinstance(obj, dict):
            yield None, None
            continue
        rid = obj.pop("id", None)
        obj.pop("commit", None)
        yield rid, obj


def write(stream: IO[str], rid: str | None, body: dict) -> None:
    """A NaN or Infinity in `body` is a bug upstream, so it propagates as a
    ValueError rather than reach the wire as invalid JSON."""
    stream.write(json.dumps({"id": rid, **body}, allow_nan=False) + "\n")
    stream.flush()
