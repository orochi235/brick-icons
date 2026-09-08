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
# LDConfig files its colours under comment headings -- "LDraw Solid Colours",
# "LDraw Obsolete Colours". Nothing else says which family a colour is in.
_HEADING = re.compile(r"^0\s+//\s+LDraw\s+(?P<name>.+?)\s+Colours\s*$",
                      re.IGNORECASE)
# LDConfig writes LEGO's own number for a colour on the line above it. Only
# the colours LEGO numbers carry one, which is the closest thing the file has
# to "this is a colour LEGO moulds".
_LEGOID = re.compile(r"^0\s+//\s+LEGOID\s+(?P<id>\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Color:
    code: int
    name: str
    rgb: tuple
    alpha: int = 255
    #: The LDConfig heading it was listed under -- 'Solid', 'Rubber',
    #: 'Obsolete' -- or '' for a file that carries no headings.
    category: str = ""
    #: LEGO's own number for the colour, where LDConfig declares one.
    lego_id: int | None = None

    @property
    def hex(self) -> str:
        return "0x%02x%02x%02x" % tuple(self.rgb)

    @property
    def opacity(self) -> float:
        return self.alpha / 255.0


def parse_ldconfig(lines) -> list[Color]:
    """Every '0 !COLOUR ... CODE n VALUE #rrggbb [... ALPHA a]' line."""
    out = []
    category = ""
    lego_id = None
    for ln in lines:
        heading = _HEADING.match(ln)
        if heading:
            category = heading.group("name").strip()
            continue
        legoid = _LEGOID.match(ln)
        if legoid:
            lego_id = int(legoid.group("id"))
            continue
        m = _COLOUR.match(ln)
        if not m:
            continue
        v = int(m.group("value"), 16)
        a = _ALPHA.search(ln[m.end():])
        out.append(Color(code=int(m.group("code")), name=m.group("name"),
                         rgb=((v >> 16) & 255, (v >> 8) & 255, v & 255),
                         alpha=int(a.group(1)) if a else 255,
                         category=category, lego_id=lego_id))
        lego_id = None
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
# up to 5 digits: LDConfig defines 118 codes above 999 (u9496p01 prints in
# 20015, Canvas_White). Six stays hex, which is what keeps '000016' hex.
_CODE = re.compile(r"\d{1,5}")


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
