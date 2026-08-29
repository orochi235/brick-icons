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


@dataclass(frozen=True)
class Palette:
    by_code: dict = field(default_factory=dict)
    by_name: dict = field(default_factory=dict)


def normalize_name(name: str) -> str:
    """Fold case, separators, and the gray/grey split. LDConfig spells it
    British; both spellings must resolve."""
    s = str(name).strip().lower()
    for ch in "_- ":
        s = s.replace(ch, "")
    return s.replace("gray", "grey")


@lru_cache(maxsize=8)
def _palette_for(path_str: str) -> Palette:
    path = Path(path_str)
    colors = parse_ldconfig(path.read_text(errors="replace").splitlines())
    return Palette(by_code={c.code: c for c in colors},
                   by_name={normalize_name(c.name): c for c in colors})


def load_palette(ldraw_dir) -> Palette:
    """Colors from <ldraw_dir>/LDConfig.ldr, cached per path."""
    return _palette_for(str(Path(ldraw_dir) / "LDConfig.ldr"))


_HEX6 = re.compile(r"[0-9a-f]{6}")
_HEXANY = re.compile(r"[0-9a-f]{1,6}")
_CODE = re.compile(r"\d{1,3}")


class UnknownColorError(ValueError):
    """A --part-color spec that is neither hex, an LDraw code, nor a name."""


def resolve(spec, ldraw_dir) -> tuple:
    """Any color spec -> ('0xrrggbb', alpha or None).

    Precedence matters: a bare '16' is LDraw code 16, but '000016' is hex, so
    configs written before codes existed keep their meaning.
    """
    s = str(spec).strip()
    low = s.lower()
    explicit = low.startswith("0x") or low.startswith("#")
    body = low[2:] if low.startswith("0x") else low[1:] if explicit else low
    if (explicit or _HEX6.fullmatch(body)) and _HEXANY.fullmatch(body):
        return "0x%06x" % int(body, 16), None

    pal = load_palette(ldraw_dir)
    if _CODE.fullmatch(s):
        c = pal.by_code.get(int(s))
        if c is None:
            raise UnknownColorError(f"no LDraw color with code {s}")
    else:
        c = pal.by_name.get(normalize_name(s))
        if c is None:
            raise UnknownColorError(
                f"unknown color {spec!r}: expected 0xRRGGBB, an LDraw code, "
                f"or a color name (see --list-colors)")
    return c.hex, (c.alpha if c.alpha != 255 else None)
