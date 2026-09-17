#!/usr/bin/env python3
"""Does an open defect still reproduce? Draw it beside the reference.

    .venv/bin/python scripts/defect-sheet.py --class mirrored --out out/sheets/mirrored.png
    .venv/bin/python scripts/defect-sheet.py --id 6501596f-decal-mirrored --open

A defect filed weeks ago was filed against a drawing that has since moved --
every render in the corpus is behind at least one drawing commit. So before
investigating one, draw its part at HEAD and put that beside the browser
reference, which is the only panel in the sheet that is not this engine's
own opinion.

The sheet labels what varies: one row per defect, the part id and the filed
complaint on the left, `reference` and `at HEAD` over the two panels. It
answers "is this still true", never "is this right" -- a row that looks
fixed still needs a person to say so.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

DEFECTS = ROOT / "tests" / "goldens" / "defects.toml"
REFERENCE = ROOT / "renders" / "reference"
PANEL = 300
PAD = 10
LABEL_W = 260
ROW_H = PANEL + 2 * PAD


def _font(size: int):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def worktree(rev: str, under: Path) -> Path:
    """A read-only checkout of `rev` to draw the `before` panel from.

    The engine is imported from here by path rather than checked out over the
    working tree, which several sessions share. `vendor/` is symlinked in
    because the library is 24,591 files and none of them are what changed."""
    wt = under / f"wt-{rev}"
    if not wt.is_dir():
        subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach",
                        str(wt), rev], check=True, capture_output=True)
    link = wt / "vendor"
    if not link.exists():
        link.symlink_to(ROOT / "vendor")
    return wt


def draw_part(part: str, source: str, into: Path, tree: Path | None = None) -> Path | None:
    """Draw `part` in `source`'s canonical config, and rasterize it.

    Each (part, source) gets its own directory. Sharing one meant the glob
    below took whichever slot had drawn the part first, and a sheet titled
    `occt` came back full of decal panels with nothing saying so."""
    into = into / source / part
    into.mkdir(parents=True, exist_ok=True)
    for old in into.glob("*"):
        old.unlink()
    argv = list(db._CANONICAL[source])
    if "--format" not in argv:
        argv += ["--format", "svg"]
    cwd = tree or ROOT
    env = {**os.environ, "PYTHONPATH": str(cwd)}
    r = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "brick_icons.cli",
                        part, *argv, "--out", str(into)],
                       capture_output=True, text=True, cwd=cwd, env=env)
    if r.returncode != 0:
        return None
    svgs = sorted(into.glob(f"{part}.*svg"))
    if not svgs:
        return None
    png = svgs[0].with_suffix(".sheet.png")
    subprocess.run(["resvg", "-w", str(PANEL * 2), str(svgs[0]), str(png)],
                   capture_output=True)
    return png if png.exists() else None


def _fit(path: Path | None) -> Image.Image:
    box = Image.new("RGB", (PANEL, PANEL), "white")
    if path is None or not path.exists():
        ImageDraw.Draw(box).text((PANEL // 2 - 30, PANEL // 2), "no render",
                                 fill="#b00", font=_font(14))
        return box
    im = Image.open(path).convert("RGBA")
    flat = Image.new("RGBA", im.size, "white")
    flat.alpha_composite(im)
    im = flat.convert("RGB")
    im.thumbnail((PANEL, PANEL), Image.LANCZOS)
    box.paste(im, ((PANEL - im.width) // 2, (PANEL - im.height) // 2))
    return box


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--id", action="append", default=[], help="defect id")
    ap.add_argument("--match", help="substring of the defect title")
    ap.add_argument("--source", default="decal",
                    help="slot to draw the part in (default from the defect)")
    ap.add_argument("--title", default="open defects, drawn at HEAD")
    ap.add_argument("--before", help="also draw a panel from this revision")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tmp", type=Path,
                    default=Path("/tmp/defect-sheet"))
    a = ap.parse_args(argv)

    rows = tomllib.load(DEFECTS.open("rb"))["defect"]
    rows = [r for r in rows if r.get("status") == "open"]
    if a.id:
        rows = [r for r in rows if r["id"] in a.id]
    if a.match:
        rows = [r for r in rows if a.match.lower() in r["title"].lower()]
    if not rows:
        print("no open defect matched", file=sys.stderr)
        return 1

    a.tmp.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()

    f_title, f_lab, f_small = _font(22), _font(15), _font(12)
    head_h = 64
    cols = 3 if a.before else 2
    sheet = Image.new("RGB", (LABEL_W + cols * (PANEL + PAD) + PAD,
                              head_h + ROW_H * len(rows)), "white")
    d = ImageDraw.Draw(sheet)
    d.text((PAD, 12), a.title, fill="black", font=f_title)
    d.text((PAD, 40), f"drawn at {head} — reference is the browser render, "
                      f"not this engine", fill="#555", font=f_small)

    for i, r in enumerate(rows):
        print(f"{i + 1}/{len(rows)} {r['part']} {r['id']}", flush=True)
        y = head_h + i * ROW_H
        source = a.source if a.source in db.SOURCES else "decal"
        d.text((PAD, y + PAD), r["part"], fill="black", font=f_lab)
        for j, line in enumerate(_wrap(r["title"], 34)):
            d.text((PAD, y + PAD + 22 + j * 15), line, fill="#444", font=f_small)
        d.text((PAD, y + ROW_H - 26), f"filed {r.get('filed', '?')}",
               fill="#888", font=f_small)

        ref = next(iter(REFERENCE.glob(f"{r['part']}.webp")), None)
        panels = [("reference", _fit(ref))]
        if a.before:
            wt = worktree(a.before, a.tmp)
            panels.append((f"before — {a.before}",
                           _fit(draw_part(r["part"], source, a.tmp / "old", wt))))
        panels.append((f"after — {source} at {head}",
                       _fit(draw_part(r["part"], source, a.tmp))))
        for k, (name, im) in enumerate(panels):
            x = LABEL_W + k * (PANEL + PAD)
            sheet.paste(im, (x, y + PAD))
            d.rectangle([x, y + PAD, x + PANEL, y + PAD + PANEL], outline="#ccc")
            d.text((x + 4, y + PAD + PANEL - 16), name, fill="#333", font=f_small)
        d.line([(0, y), (sheet.width, y)], fill="#ddd")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(a.out)
    print(f"wrote {a.out}  ({len(rows)} defects)")
    return 0


def _wrap(s: str, n: int) -> list[str]:
    out, line = [], ""
    for w in s.split():
        if len(line) + len(w) + 1 > n:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out[:5]


if __name__ == "__main__":
    raise SystemExit(main())
