"""Part id and description, for the title-bar search.

`printed` reads line 1, not the id: `^\\d{3,}p\\d+$` catches only 3254 of
13081 printed parts and 132 bare-numeric ids are patterned, so the id is a
fast path and never the authority.
"""
from __future__ import annotations

from pathlib import Path


def _header(path: Path) -> tuple[str, str | None]:
    """The description line, and the `!PREVIEW` orientation if one is declared.

    Scanned to the first geometry line, not to a fixed line count: `!PREVIEW`
    sits as deep as line 22 in the library, so the 12 lines
    `library._read_header_lines` takes would miss 340 of the 394 parts that
    declare one. All 394 come before any geometry, so the header's end is a
    bound and a cap is not needed.
    """
    preview = None
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            first = fh.readline().strip()
            desc = first[1:].strip() if first.startswith("0") else ""
            for line in fh:
                fields = line.split()
                if not fields:
                    continue
                if fields[0] != "0":
                    break
                if len(fields) > 1 and fields[1] == "!PREVIEW":
                    preview = " ".join(fields[2:])
                    break
    except OSError:
        return "", None
    return desc, preview


def build(ldraw_dir: Path | str) -> dict[str, dict]:
    """Every file in `parts/`, as id -> {description, printed, preview}."""
    out = {}
    for path in sorted(Path(ldraw_dir).joinpath("parts").glob("*.dat")):
        desc, preview = _header(path)
        out[path.stem] = {
            "id": path.stem,
            "description": desc,
            "printed": "pattern" in desc.lower() or "sticker" in desc.lower(),
            "preview": preview,
        }
    return out


def _text_rank(entry: dict, q: str) -> int:
    """Whole-phrase description matches beat scattered word matches.

    Without this the cap alone decides: 'brick 2 x 4' matches thousands of
    parts on its four words and the id-sorted first 25 are all unrelated.
    """
    desc = " ".join(entry["description"].lower().split())
    if desc == q:
        return 0
    if q in desc:
        return 1
    return 2


def search(index: dict[str, dict], query: str, limit: int = 25) -> list[dict]:
    """Id and description matches, exact id first, then id prefix, then text."""
    q = " ".join(query.lower().split())
    if not q:
        return []
    words = q.split()
    exact, prefix, text = [], [], []
    for entry in index.values():
        pid = entry["id"].lower()
        haystack = f"{pid} {' '.join(entry['description'].lower().split())}"
        if pid == q:
            exact.append(entry)
        elif pid.startswith(q):
            prefix.append(entry)
        elif all(w in haystack for w in words):
            text.append(entry)
    text.sort(key=lambda e: _text_rank(e, q))
    return [*exact, *prefix, *text][:limit]
