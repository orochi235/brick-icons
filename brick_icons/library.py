from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ALLOWED_CATEGORIES = {
    "Brick", "Plate", "Tile", "Slope", "Technic", "Wedge", "Panel",
    "Cylinder", "Cone", "Dish", "Bar", "Bracket", "Hinge", "Wing", "Baseplate",
}
EXCLUDE_TITLE_SUBSTR = ("Sticker", "Pattern", "Moved")
_ORG = re.compile(r"!LDRAW_ORG\s+(\w+)")


@dataclass(frozen=True)
class PartInfo:
    title: str
    category: str
    org: str


def parse_header(lines) -> PartInfo:
    title = ""
    org = ""
    for ln in lines:
        s = ln.rstrip("\n")
        if not title and s.startswith("0 ") and "!LDRAW_ORG" not in s and "Name:" not in s:
            title = s[2:].strip()
        m = _ORG.search(s)
        if m and not org:
            org = m.group(1)
        if title and org:
            break
    stripped = title.lstrip("~_ ")
    category = stripped.split()[0] if stripped else ""
    return PartInfo(title=title, category=category, org=org)


def is_sortable(info: PartInfo) -> bool:
    if info.org != "Part":
        return False
    if info.title[:1] in ("~", "_"):
        return False
    if any(sub in info.title for sub in EXCLUDE_TITLE_SUBSTR):
        return False
    return info.category in ALLOWED_CATEGORIES
