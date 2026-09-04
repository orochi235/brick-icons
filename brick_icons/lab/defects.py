"""The defect list, as git-tracked TOML.

Written in a fixed field order so a diff shows a change of meaning rather than
a reshuffle. Part ids live here and in the other corpus data files, never in
the library.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

DEFAULT_PATH = Path("tests/goldens/defects.toml")
STATUSES = ("open", "fixed", "wontfix", "notabug")
_ORDER = ("id", "part", "engines", "status", "title", "mark", "kind", "points",
          "seen", "filed", "notes")

_HEADER = """\
# Defects found in corpus renders, filed from the lab.
#
# Written by brick_icons.lab; hand edits are kept but reformatted on the next
# write. `mark` is in fractions of the pane box it was drawn on. `kind` and
# `points` are absent on a plain rectangle, which is every defect filed before
# 2026-09. `seen` is retained for records that carry it; the lab now asks
# labkit whether a mark is stale.

"""


def _dump_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_dump_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_dump_value(v)}"
                                for k, v in value.items()) + " }"
    text = str(value)
    if "\n" in text:
        return '"""\n' + text.replace("\\", "\\\\") + '"""'
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def load(path: Path | str = DEFAULT_PATH) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return list(tomllib.loads(path.read_text()).get("defect", []))


def save(path: Path | str, records: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = [_HEADER]
    for record in records:
        lines = ["[[defect]]"]
        for field in _ORDER:
            if field in record:
                lines.append(f"{field} = {_dump_value(record[field])}")
        for field in sorted(set(record) - set(_ORDER)):
            lines.append(f"{field} = {_dump_value(record[field])}")
        chunks.append("\n".join(lines) + "\n")
    path.write_text("\n".join(chunks))


def add(path: Path | str, record: dict) -> dict:
    records = load(path)
    if any(r["id"] == record["id"] for r in records):
        raise ValueError(f"defect {record['id']!r} already exists")
    if record.get("status", "open") not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    records.append(record)
    save(path, records)
    return record


def update(path: Path | str, defect_id: str, changes: dict) -> dict:
    if "status" in changes and changes["status"] not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    records = load(path)
    for record in records:
        if record["id"] == defect_id:
            record.update(changes)
            save(path, records)
            return record
    raise KeyError(f"no defect {defect_id!r}")
