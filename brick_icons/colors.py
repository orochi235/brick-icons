from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_COLOUR = re.compile(
    r"^0\s+!COLOUR\s+(?P<name>\S+)\s+CODE\s+(?P<code>\d+)\s+"
    r"VALUE\s+#(?P<value>[0-9A-Fa-f]{6})",
    re.IGNORECASE)
_ALPHA = re.compile(r"\bALPHA\s+(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class Color:
    code: int
    name: str
    rgb: tuple
    alpha: int = 255

    @property
    def hex(self) -> str:
        return "0x%02x%02x%02x" % tuple(self.rgb)

    @property
    def opacity(self) -> float:
        return self.alpha / 255.0


def parse_ldconfig(lines) -> list[Color]:
    """Every '0 !COLOUR ... CODE n VALUE #rrggbb [... ALPHA a]' line."""
    out = []
    for ln in lines:
        m = _COLOUR.match(ln)
        if not m:
            continue
        v = int(m.group("value"), 16)
        a = _ALPHA.search(ln[m.end():])
        out.append(Color(code=int(m.group("code")), name=m.group("name"),
                         rgb=((v >> 16) & 255, (v >> 8) & 255, v & 255),
                         alpha=int(a.group(1)) if a else 255))
    return out
