"""The corpus lists, read where they already live.

The lab reads these and never writes them: which parts belong in which list is
a curation decision that stays in the files and in review.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

_TEXT_SOURCES = {
    "parts": "parts.txt",
    "specimens": "specimens.txt",
    "decal-corpus": "tests/goldens/decal-corpus.txt",
}
_MANIFEST = "tests/goldens/manifest.toml"


def _ids(path: Path) -> list[str]:
    out = []
    for line in path.read_text().splitlines():
        token = line.split("#")[0].strip()
        if token:
            out.append(token.split()[0])
    return out


def lists(root: Path | str = ".") -> list[dict]:
    """Every corpus list, as name, source path and part ids."""
    root = Path(root)
    out = []
    for name, rel in _TEXT_SOURCES.items():
        path = root / rel
        if path.exists():
            out.append({"name": name, "source": rel, "parts": _ids(path)})
    manifest = root / _MANIFEST
    if manifest.exists():
        data = tomllib.loads(manifest.read_text())
        for name, parts in data.get("parts", {}).items():
            out.append({"name": f"manifest:{name}", "source": _MANIFEST,
                        "parts": list(parts)})
    return out


def combos(root: Path | str = ".") -> list[dict]:
    """The manifest's combos: name, argument list, and the parts they cover.

    A combo names a parts list rather than repeating its ids, so the list is
    resolved here -- the manifest stays the one place a case is declared.
    """
    manifest = Path(root) / _MANIFEST
    if not manifest.exists():
        return []
    data = tomllib.loads(manifest.read_text())
    lists = data.get("parts", {})
    out = []
    for name, spec in data.get("combo", {}).items():
        parts = spec.get("parts")
        resolved = (list(lists.get(parts, [])) if isinstance(parts, str)
                    else list(parts or []))
        out.append({"name": name, "args": list(spec.get("args", [])),
                    "parts": resolved})
    return out


def combos_for(root: Path | str, part: str) -> list[dict]:
    """The combos a part is actually a case in."""
    return [c for c in combos(root) if part in c["parts"]]
