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

#: Symptom families, in the order they read best: what is drawn that should
#: not be, then what is not drawn that should be, then how it is painted.
CLASSES = ("hidden-leak", "stray-ink", "arc-split", "fill-solid",
           "over-cull", "arc-loss", "fill-hole",
           "banding", "shading", "seam", "stroke-scale", "decal")
_ORDER = ("id", "part", "engines", "status", "title", "classes", "mark",
          "kind", "points", "seen", "checked", "filed", "notes")

_HEADER = """\
# Defects found in corpus renders, filed from the lab.
#
# Written by brick_icons.lab; hand edits are kept but reformatted on the next
# write. `mark` is in fractions of the pane box it was drawn on. `kind` and
# `points` are absent on a plain rectangle, which is every defect filed before
# 2026-09. `seen` is retained for records that carry it; the lab now asks
# labkit whether a mark is stale.
#
# `classes` is the symptom family, from defects.CLASSES: what the drawing
# does wrong, never what causes it. A row nobody can class from its own
# title has none, and there is no `misc`.
#
# `checked` maps a slot to the render sha that was last looked at and judged.
# An open defect whose slot now draws a different sha is looking for review;
# one with no entry for a slot never asks, which is what a record filed
# before this field wants.

"""


def dump_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(dump_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {dump_value(v)}"
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
                lines.append(f"{field} = {dump_value(record[field])}")
        for field in sorted(set(record) - set(_ORDER)):
            lines.append(f"{field} = {dump_value(record[field])}")
        chunks.append("\n".join(lines) + "\n")
    path.write_text("\n".join(chunks))


def wants_review(record: dict, source: str, sha: str | None) -> bool:
    """Whether this defect is asking someone to look at `source` again.

    Only an open defect, only against a slot it was judged on, and only once
    that slot draws something else. Shas and not dates: a bake that redraws
    the same picture has nothing to review, and every open defect flagging at
    once on a routine rebake would be worse than no signal at all.
    """
    if record.get("status", "open") != "open" or sha is None:
        return False
    seen = (record.get("checked") or {}).get(source)
    return seen is not None and seen != sha


def check_classes(classes) -> None:
    unknown = [c for c in classes or () if c not in CLASSES]
    if unknown:
        raise ValueError(f"unknown class(es) {unknown}; expected {CLASSES}")


def add(path: Path | str, record: dict) -> dict:
    records = load(path)
    if any(r["id"] == record["id"] for r in records):
        raise ValueError(f"defect {record['id']!r} already exists")
    if record.get("status", "open") not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    check_classes(record.get("classes"))
    records.append(record)
    save(path, records)
    return record


def update(path: Path | str, defect_id: str, changes: dict) -> dict:
    if "status" in changes and changes["status"] not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if "classes" in changes:
        check_classes(changes["classes"])
    records = load(path)
    for record in records:
        if record["id"] == defect_id:
            record.update(changes)
            save(path, records)
            return record
    raise KeyError(f"no defect {defect_id!r}")
