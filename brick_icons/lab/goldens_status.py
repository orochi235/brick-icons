"""What the golden harness has frozen for a part.

Reads only; re-freezing stays with `scripts/freeze-goldens.py`, which is where
a deliberate baseline move belongs.
"""
from __future__ import annotations

from pathlib import Path

from .. import goldens
from . import corpus

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


def cases_for(root: Path | str, part: str) -> list[dict]:
    """Every golden case this part is in, with the argv that reproduces it."""
    return [{"case": f"{c['name']}__{part}", "combo": c["name"],
             "argv": [part, *c["args"]]}
            for c in corpus.combos_for(root, part)]


def compare_case(svg_path: Path | str, frozen_digest: str | None) -> dict:
    """One case: does a fresh render hash to what was frozen?

    The frozen digest is sha256 of the SVG text, so this is an exact string
    comparison with no tolerance to get wrong.
    """
    path = Path(svg_path)
    if not path.exists():
        return {"state": "missing", "frozen": frozen_digest, "fresh": None}
    fresh = goldens.sha256(path.read_text())
    if frozen_digest is None:
        return {"state": "unfrozen", "frozen": None, "fresh": fresh}
    state = "match" if fresh == frozen_digest else "moved"
    return {"state": state, "frozen": frozen_digest, "fresh": fresh}

