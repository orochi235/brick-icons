#!/usr/bin/env python3
"""Regenerate the handoff's defect list from tests/goldens/defects.toml.

    python scripts/defects-to-handoff.py

The list in HANDOFF.md is generated so that it cannot drift from the store the
lab writes. Everything between the markers is replaced; a hand edit inside them
is lost on the next run, which is why the store is the place to edit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brick_icons.lab import defects  # noqa: E402

BEGIN = "<!-- defects:begin -->"
END = "<!-- defects:end -->"
HEADING = {"open": "Open", "fixed": "Fixed", "wontfix": "Won't fix",
           "notabug": "Not a bug"}


def _bullet(record: dict) -> str:
    engines = ", ".join(record.get("engines", [])) or "both"
    seen = record.get("seen", {})
    at = f" at `{seen['angle']}`" if seen.get("angle") else ""
    line = f"- **`{record['part']}`** ({engines}){at} — {record['title']}"
    notes = (record.get("notes") or "").strip()
    if notes:
        body = "\n".join(f"  {ln}" for ln in notes.splitlines())
        line = f"{line}\n{body}"
    return line


def render(records: list[dict]) -> str:
    if not records:
        return "No defects filed.\n"
    chunks = []
    for status in ("open", "fixed", "wontfix", "notabug"):
        rows = [r for r in records if r.get("status") == status]
        if not rows:
            continue
        rows.sort(key=lambda r: (r["part"], r["id"]))
        chunks.append(f"### {HEADING[status]}\n\n"
                      + "\n".join(_bullet(r) for r in rows) + "\n")
    return "\n".join(chunks)


def write_into(path: Path, records: list[dict]) -> None:
    text = path.read_text()
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < 0:
        raise SystemExit(f"{path}: missing {BEGIN} / {END} markers")
    if end < start:
        raise SystemExit(f"{path}: {END} appears before {BEGIN}")
    body = render(records)
    path.write_text(f"{text[:start + len(BEGIN)]}\n\n{body}\n{text[end:]}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="defects-to-handoff")
    p.add_argument("--defects", type=Path, default=Path("tests/goldens/defects.toml"))
    p.add_argument("--handoff", type=Path, default=Path("HANDOFF.md"))
    args = p.parse_args(argv)
    records = defects.load(args.defects)
    write_into(args.handoff, records)
    print(f"{args.handoff}: wrote {len(records)} defects", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
