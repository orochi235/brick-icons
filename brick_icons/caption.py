"""The caption a review render carries: part, file size, render time.

One line, `3001 ·   18.4 KB ·   3.2 s`, in a strip added below the drawing --
the canvas grows, so the caption never lands on the part. Size is the
uncaptioned file's bytes, which is what production would ship; time is the
render's measured seconds, or a dash when nothing measured it.

Production output never passes through here: the census, the render store,
slot batches and goldens write bare files. The CLI's `--part-label` (implied
by `--review`), `scripts/_sheet.py` and the scripts drawing sheets of their
own are the callers.
"""
from __future__ import annotations

import importlib.util
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SEP = " · "
DASH = "—"
#: Output suffixes a caption is stamped into; anything else a render writes
#: (the fit sidecar, a debug stage) is left as it is.
STAMPED = (".svg", ".png", ".webp")
#: Glyph height as a fraction of the drawing's width. An SVG is rasterized at
#: whatever width the sheet wants, so a caption sized in the file's own px
#: would come out huge on a 600px contact-sheet cell drawn from a 256px file.
SVG_EM = 1 / 40
#: The smallest raster glyph, in px, and the strip's padding.
PX = 12
PAD = 3
#: Monospace advance per em, for sizing an SVG strip without a font on hand.
ADVANCE = 0.6
_SYSTEM_MONO = (Path("/System/Library/Fonts/Menlo.ttc"),
                Path("/System/Library/Fonts/SFNSMono.ttf"))


def size_text(nbytes: int | None) -> str:
    """Bytes in fixed width with one decimal: `  18.4 KB`, `   1.2 MB`."""
    if nbytes is None:
        return f"{DASH:>6}   "
    if nbytes < 1024 * 1024:
        return f"{nbytes / 1024:6.1f} KB"
    return f"{nbytes / (1024 * 1024):6.1f} MB"


def secs_text(secs: float | None) -> str:
    """Seconds in fixed width with one decimal: `  3.2 s`; a dash, in the
    same width, when nothing measured them."""
    if secs is None:
        return f"{DASH:>5}  "
    return f"{secs:5.1f} s"


def line(part: str, nbytes: int | None, secs: float | None) -> str:
    return SEP.join((part, size_text(nbytes), secs_text(secs)))


@dataclass(frozen=True)
class Shot:
    """A panel and what its caption says. `_sheet.sheet` takes these where it
    takes a bare image, and stamps the caption under it."""
    image: Image.Image
    part: str
    nbytes: int | None = None
    secs: float | None = None

    @property
    def text(self) -> str:
        return line(self.part, self.nbytes, self.secs)

    @classmethod
    def of(cls, image, part: str, path: Path | None = None,
           secs: float | None = None) -> "Shot":
        """A panel whose size is read off the file it was drawn from."""
        n = Path(path).stat().st_size if path and Path(path).exists() else None
        return cls(image, part, n, secs)


def _font_paths():
    # matplotlib ships DejaVu Sans Mono wherever the census extra is
    # installed; the system monospace faces cover a node without it. Found
    # by spec, not imported: importing matplotlib costs a second.
    spec = importlib.util.find_spec("matplotlib")
    if spec is not None and spec.origin:
        yield (Path(spec.origin).parent / "mpl-data" / "fonts" / "ttf"
               / "DejaVuSansMono.ttf")
    yield from _SYSTEM_MONO


@lru_cache(maxsize=8)
def font(px: int = PX) -> ImageFont.ImageFont:
    """A monospace face, so the digits are tabular."""
    for p in _font_paths():
        if p.exists():
            return ImageFont.truetype(str(p), px)
    return ImageFont.load_default(size=px)


def strip_height(px: int = PX) -> int:
    return px + 2 * PAD + 2


_PAPER = {"1": (1, 0), "L": (255, 0), "RGB": ((255,) * 3, (0,) * 3),
          "RGBA": ((255,) * 4, (0, 0, 0, 255))}


def glyph_px(width: int) -> int:
    """Caption glyph height for a raster `width` px wide: the SVG's share of
    the width, never below PX."""
    return max(PX, round(width * SVG_EM))


def pad(img: Image.Image, text: str = "", px: int | None = None) -> Image.Image:
    """`img` with a strip below it carrying `text`, right-aligned so the
    fixed-width numbers line up down a column of panels. The canvas widens
    rather than clip a caption longer than the drawing is wide. An empty
    `text` still adds the strip, so a row's uncaptioned panel stays level
    with its captioned neighbors."""
    if img.mode not in _PAPER:
        img = img.convert("RGBA")
    px = px or glyph_px(img.width)
    f = font(px)
    tw = int(f.getlength(text)) + 2 * PAD if text else 0
    w, h = max(img.width, tw), img.height + strip_height(px)
    bg, ink = _PAPER[img.mode]
    out = Image.new(img.mode, (w, h), bg)
    out.paste(img, (0, 0))
    if text:
        ImageDraw.Draw(out).text((w - PAD, h - PAD - 1), text, fill=ink,
                                 font=f, anchor="rd")
    return out


_ROOT = re.compile(r"<svg\b[^>]*>")
_VIEWBOX = re.compile(r'viewBox="([^"]+)"')
_HEIGHT = re.compile(r'\bheight="([\d.]+)([a-z%]*)"')
_WIDTH = re.compile(r'\bwidth="([\d.]+)([a-z%]*)"')


def pad_svg(text: str, caption: str) -> str:
    """The SVG with its viewBox grown by a caption strip at the bottom, and
    widened on the right if the caption is longer than the drawing is wide."""
    m = _ROOT.search(text)
    if m is None:
        raise ValueError("not an SVG")
    root = m.group(0)
    vb = _VIEWBOX.search(root)
    wm, hm = _WIDTH.search(root), _HEIGHT.search(root)
    if vb:
        x0, y0, vw, vh = (float(v) for v in vb.group(1).replace(",", " ").split())
    elif wm and hm:
        x0, y0, vw, vh = 0.0, 0.0, float(wm.group(1)), float(hm.group(1))
    else:
        raise ValueError("SVG has neither a viewBox nor a width and height")
    fs = vw * SVG_EM
    unit = fs / PX
    strip = strip_height() * unit
    nw = max(vw, len(caption) * ADVANCE * fs + 2 * PAD * unit)
    new_vb = f'viewBox="{x0:g} {y0:g} {nw:g} {vh + strip:g}"'
    new = _VIEWBOX.sub(new_vb, root) if vb else root.replace(
        "<svg", f"<svg {new_vb}", 1)
    if hm:
        new = _HEIGHT.sub(f'height="{float(hm.group(1)) * (vh + strip) / vh:.2f}'
                          f'{hm.group(2)}"', new, count=1)
    if wm and nw > vw:
        new = _WIDTH.sub(f'width="{float(wm.group(1)) * nw / vw:.2f}'
                         f'{wm.group(2)}"', new, count=1)
    body = (f'<text x="{x0 + nw - PAD * unit:.2f}" '
            f'y="{y0 + vh + strip - (PAD + 1) * unit:.2f}" '
            # preserve: SVG collapses runs of spaces, and the padding
            # that aligns the numbers is runs of spaces
            f'text-anchor="end" xml:space="preserve" '
            f'font-family="DejaVu Sans Mono, Menlo, monospace" '
            f'font-size="{fs:.2f}" fill="black">{_escape(caption)}</text>')
    close = text.rindex("</svg>")
    return text[:m.start()] + new + text[m.end():close] + body + text[close:]


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stamp_file(path: Path, part: str, secs: float | None) -> None:
    """Caption a written render in place, sizing it before the caption lands."""
    path = Path(path)
    text = line(part, path.stat().st_size, secs)
    if path.suffix == ".svg":
        path.write_text(pad_svg(path.read_text(), text))
        return
    with Image.open(path) as im:
        im.load()
        out = pad(im, text)
    out.save(path)


def stored_secs(part: str, source: str, path: Path | str | None = None,
                db_path: Path | str = "corpus.db") -> float | None:
    """The seconds corpus.db recorded for the stored drawing of `part` in
    `source`: the measurement, else the attempt, of the run that made it.
    With `path`, only if that stored drawing is the file at `path`. None
    when the drawing has no run or its run timed nothing -- never another
    run's number standing in for this one."""
    db = Path(db_path)
    if not db.exists():
        return None
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT run_id, path FROM renders WHERE part_id=? "
                           "AND source=?", (part, source)).fetchone()
        if row is None or row[0] is None:
            return None
        if path is not None and not _same_file(row[1], path, db.parent):
            return None
        for table in ("measurements", "attempts"):
            hit = conn.execute(f"SELECT secs FROM {table} WHERE run_id=? AND "
                               "part_id=? AND source=? AND secs IS NOT NULL",
                               (row[0], part, source)).fetchone()
            if hit is not None:
                return float(hit[0])
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return None


def _same_file(stored: str, path: Path | str, root: Path) -> bool:
    a, b = (root / stored).resolve(), Path(path).resolve()
    return a == b or (a.exists() and b.exists() and a.samefile(b))
