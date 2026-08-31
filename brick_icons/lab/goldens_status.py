"""What the golden harness has frozen for a part.

Reads only; re-freezing stays with `scripts/freeze-goldens.py`, which is where
a deliberate baseline move belongs.
"""
from __future__ import annotations

from pathlib import Path

DEFAULT_PATH = Path("tests/goldens/hashes.txt")


def frozen(path: Path | str = DEFAULT_PATH) -> dict[str, dict[str, str]]:
    """part -> {combo: hash}, from the frozen hash file."""
    path = Path(path)
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    for line in path.read_text().splitlines():
        text = line.split("#")[0].strip()
        if not text or "__" not in text:
            continue
        fields = text.split()
        case = next(f for f in fields if "__" in f)
        digest = next(f for f in fields if f is not case)
        combo, _, part = case.partition("__")
        out.setdefault(part, {})[combo] = digest
    return out


def status(path: Path | str, part: str) -> dict:
    """The frozen cases for one part, and whether it has any."""
    cases = frozen(path).get(part, {})
    return {"part": part, "cases": cases, "known": bool(cases)}
