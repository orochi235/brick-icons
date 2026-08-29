"""Proof sheet: printed parts' decals laid flat, each beside LDView's render.

A decal that fails to bind renders as a blank brick, indistinguishable from an
unprinted part, so the icon output cannot be eyeballed for this class.
Flattening the decal into its carrier's surface shows what SHOULD be drawn;
LDView's own colour render beside it shows what the part actually is.
Disagreement is an unwrap bug; agreement leaves only the projection to check.

Emits a paginated PDF laid out as a grid, each cell labelled with the part id,
title, carrier kind, facet count and the LDraw colours used.

    .venv/bin/python scripts/proof-decals.py --limit 200 --jobs 8
    .venv/bin/python scripts/proof-decals.py --list printed.txt --out out/p.pdf
    .venv/bin/python scripts/proof-decals.py 3941p01 3942bp01

Built for long lists: cells are cached under the output's `proof-work/`, so a
re-run only redoes what is missing; `--jobs` renders in parallel (LDView
dominates the wall clock); `--start`/`--limit` page through a large set. About
4,700 printed parts exist, so batch it.

The unwrap is deliberately standalone so this runs against any checkout. When
`brick_icons/unwrap.py` lands, replace `_unwrap` with a call into it rather
than letting the two drift.

Needs: resvg, imagemagick (see scripts/external-deps.lock)
"""
from __future__ import annotations

import argparse
import base64
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import render  # noqa: E402
from brick_icons.colors import parse_ldconfig  # noqa: E402
from brick_icons.config import load_config  # noqa: E402

LDRAW = ROOT / "vendor" / "ldraw"
PARTS = LDRAW / "parts"
PAL = {c.code: c for c in parse_ldconfig(open(LDRAW / "LDConfig.ldr", errors="replace"))}
CELL = 460
LABEL_H = 46


def _resolve(ref: str):
    ref = ref.replace("\\", "/")
    for sub in ("parts", "p", "parts/s", "p/48"):
        c = LDRAW / sub / ref
        if c.exists():
            return c
    return None


def flatten(path, M, t, colour, out, depth=0):
    """Walk a .dat keeping each polygon's LDraw colour (16 inherits)."""
    if depth > 30 or path is None:
        return
    for ln in Path(path).read_text(errors="replace").splitlines():
        tok = ln.split()
        if not tok or tok[0] == "0":
            continue
        own = int(tok[1]) if len(tok) > 1 and tok[1].isdigit() else 16
        c = colour if own == 16 else own
        if tok[0] == "1" and len(tok) >= 15:
            x, y, z = map(float, tok[2:5])
            m = np.array(list(map(float, tok[5:14])), float).reshape(3, 3)
            flatten(_resolve(" ".join(tok[14:])), M @ m,
                    M @ np.array([x, y, z]) + t, c, out, depth + 1)
        elif tok[0] in ("3", "4"):
            n = 3 if tok[0] == "3" else 4
            if len(tok) >= 2 + 3 * n:
                p = np.array(list(map(float, tok[2:2 + 3 * n])), float).reshape(n, 3)
                out.append((c, p @ M.T + t))


def _quad(polys):
    """The carrier as ONE rectangle. Every body facet leaves the backdrop
    ragged with stud and notch silhouettes; a decal sits on a face, so draw
    that face."""
    if not polys:
        return []
    allp = np.vstack(polys)
    x0, y0 = allp.min(axis=0)
    x1, y1 = allp.max(axis=0)
    return [(16, np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]))]


def _cyl(p, rr):
    th = np.arctan2(p[:, 2], p[:, 0])
    if np.ptp(th) > math.pi:
        th = np.where(th < 0, th + 2 * math.pi, th)
    return np.column_stack([rr * th, p[:, 1]])


def _cone(p, k, b):
    """True development of a cone: an ANNULAR SECTOR, not a rectangle.

    A cone is developable, so the decal has a real flat shape — what you would
    cut out to wrap the piece. Slant distance from the apex is the polar
    radius, and the wrap angle compresses by sin(half-angle) because the full
    turn maps to less than a full turn of the flat sector. Treating radius as
    constant instead gives a rectangle: convenient, and what a cylinder
    genuinely is, but wrong for a cone.
    """
    r = np.hypot(p[:, 0], p[:, 2])
    th = np.arctan2(p[:, 2], p[:, 0])
    if np.ptp(th) > math.pi:
        th = np.where(th < 0, th + 2 * math.pi, th)
    sin_a = abs(k) / math.hypot(1.0, k)          # dr/dy -> half-angle
    rho = r / max(sin_a, 1e-9)                   # slant distance from apex
    phi = th * sin_a
    return np.column_stack([rho * np.sin(phi), -rho * np.cos(phi)])


def _unwrap(deco, body):
    """(decal, carrier, kind) laid flat, LDU on both axes."""
    pts = np.vstack([p for _, p in deco])
    # planarity decides, not radius spread: a 45-degree slope face has a tight
    # radius spread about the part axis and would unwrap as a cylinder, which
    # skews its rectangular border into a trapezoid
    ctr = pts.mean(axis=0)
    normal = np.linalg.svd(pts - ctr)[2][2]
    if float(np.abs((pts - ctr) @ normal).max()) <= 0.5:
        big = max(deco, key=lambda cp: np.linalg.norm(
            np.cross(cp[1][1] - cp[1][0], cp[1][2] - cp[1][0])))[1]
        n = np.cross(big[1] - big[0], big[2] - big[0])
        n = n / np.linalg.norm(n)
        d0 = float(n @ big[0])
        seed = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        u = np.cross(n, seed)
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        flat = [(c, np.column_stack([p @ u, p @ v])) for c, p in deco]
        carrier = _quad([np.column_stack([p @ u, p @ v]) for _, p in body
                         if abs(np.cross(p[1] - p[0], p[2] - p[0]) @ n) > 1e-6
                         and np.all(np.abs(p @ n - d0) < 0.6)])
        return flat, carrier, "flat"

    r = np.hypot(pts[:, 0], pts[:, 2])
    rr = max(r.mean(), 1e-6)
    hs = pts[:, 1]
    k, b = (np.polyfit(hs, r, 1) if np.ptp(hs) > 1e-6 else (0.0, rr))
    tapered = abs(k) > 0.05
    fn = (lambda q: _cone(q, k, b)) if tapered else (lambda q: _cyl(q, rr))
    on = [p for _, p in body
          if np.all(np.abs(np.hypot(p[:, 0], p[:, 2]) - (k * p[:, 1] + b)) < 0.8)]
    if tapered:
        # the carrier is an annular band, not a box; keep its real outline
        carrier = [(16, fn(q)) for q in on]
        return [(c, fn(p)) for c, p in deco], carrier, "cone"
    return ([(c, fn(p)) for c, p in deco], _quad([fn(q) for q in on]), "cylinder")


def cell_svg(pid, title, deco, carrier, kind, ref_png, margin=0.12):
    """One grid cell: LDView render, flat decal, label strip.

    The label is drawn in SVG rather than composited by ImageMagick, whose
    montage labeller has no usable font in this environment.
    """
    allp = np.vstack([p for _, p in deco])
    x0, y0 = allp.min(axis=0)
    x1, y1 = allp.max(axis=0)
    m = margin * max(x1 - x0, y1 - y0, 1e-9)
    x0, y0, x1, y1 = x0 - m, y0 - m, x1 + m, y1 + m
    s = min(CELL / max(x1 - x0, 1e-9), CELL / max(y1 - y0, 1e-9))
    ox = (CELL - (x1 - x0) * s) / 2
    oy = (CELL - (y1 - y0) * s) / 2

    def d(p):
        # LDraw's Y points DOWN and so does SVG's, so pass it straight through
        q = np.column_stack([(p[:, 0] - x0) * s + ox + CELL,
                             (p[:, 1] - y0) * s + oy])
        return " ".join(f"{'M' if i == 0 else 'L'}{a:.2f},{b:.2f}"
                        for i, (a, b) in enumerate(q)) + " Z"

    png = base64.b64encode(Path(ref_png).read_bytes()).decode()
    codes = sorted({c for c, _ in deco})
    names = ", ".join(f"{c} {PAL[c].name}" if c in PAL else str(c)
                      for c in codes[:4]) + (" ..." if len(codes) > 4 else "")
    w, h = 2 * CELL, CELL + LABEL_H
    body = [f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
            f'<image x="0" y="0" width="{CELL}" height="{CELL}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'xlink:href="data:image/png;base64,{png}"/>']
    body += [f'<path d="{d(p)}" fill="#f2f2f2" stroke="none"/>' for _, p in carrier]
    body += [f'<path d="{d(p)}" fill="'
             f'{PAL[c].hex.replace("0x", "#") if c in PAL else "#888888"}" '
             f'stroke="none"/>' for c, p in deco]
    body += [f'<path d="{d(p)}" fill="none" stroke="#b8b8b8" '
             f'stroke-width="1.6" stroke-dasharray="7 5"/>' for _, p in carrier]
    body += [f'<line x1="0" y1="{CELL}" x2="{w}" y2="{CELL}" stroke="#dddddd"/>',
             f'<text x="10" y="{CELL + 20}" font-family="Helvetica,Arial" '
             f'font-size="17" font-weight="bold" fill="#111">{escape(pid)}</text>',
             f'<text x="{16 + 10 * len(pid)}" y="{CELL + 20}" '
             f'font-family="Helvetica,Arial" font-size="13" fill="#555">'
             f'{escape(title[:76])}</text>',
             f'<text x="10" y="{CELL + 39}" font-family="Helvetica,Arial" '
             f'font-size="12" fill="#777">{kind} carrier &#183; '
             f'{len(deco)} facets &#183; {escape(names)}</text>']
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" '
            f'height="{h}">' + "".join(body) + "</svg>")


def printed_ids(limit=None, start=0):
    """Parts carrying geometry in a colour other than 16/24."""
    ids = []
    for f in sorted(PARTS.glob("*p*.dat")):
        try:
            txt = f.read_text(errors="replace")
        except OSError:
            continue
        for ln in txt.splitlines():
            tok = ln.split()
            if (len(tok) > 2 and tok[0] in ("1", "3", "4")
                    and tok[1].isdigit() and int(tok[1]) not in (16, 24)):
                ids.append(f.stem)
                break
    ids = ids[start:]
    return ids[:limit] if limit else ids


def build_cell(pid, cfg, work, force=False):
    """-> (path, note). Cached, so a re-run only redoes missing cells."""
    cell = work / f"{pid}.cell.png"
    if cell.exists() and not force:
        return cell, "cached"
    src = PARTS / f"{pid}.dat"
    polys = []
    flatten(src, np.eye(3), np.zeros(3), 16, polys)
    deco = [(c, p) for c, p in polys if c not in (16, 24)]
    if not deco:
        return None, "no decoration"
    body = [(c, p) for c, p in polys if c == 16]
    flat, carrier, kind = _unwrap(deco, body)
    ref = work / f"{pid}.ldview.png"
    if not ref.exists():
        subprocess.run(render.build_argv(cfg, src, ref), check=True,
                       capture_output=True)
    title = src.read_text(errors="replace").splitlines()[0][2:].strip()
    svg = work / f"{pid}.cell.svg"
    svg.write_text(cell_svg(pid, title, flat, carrier, kind, ref))
    subprocess.run(["resvg", "--background", "white", str(svg), str(cell)],
                   check=True, capture_output=True)
    return cell, f"{kind}, {len(deco)} facets"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list", help="file with one part id per line ('#' comments)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--out", default="out/proof-decals.pdf")
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--rows", type=int, default=5)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="ignore cached cells")
    args = ap.parse_args()

    if args.list:
        ids = [s for ln in Path(args.list).read_text().splitlines()
               if (s := ln.split("#")[0].strip())]
        ids = ids[args.start:]
        if args.limit:
            ids = ids[:args.limit]
    else:
        ids = args.parts or printed_ids(args.limit, args.start)
    out = Path(args.out)
    work = out.parent / "proof-work"
    work.mkdir(parents=True, exist_ok=True)
    cfg = load_config()

    done, skipped, n = {}, [], 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(build_cell, p, cfg, work, args.force): p for p in ids}
        for fut in futures:
            pid = futures[fut]
            n += 1
            try:
                cell, note = fut.result()
            except Exception as e:                  # long lists: never abort
                cell, note = None, f"{type(e).__name__}: {e}"
            print(f"[{n}/{len(ids)}] {pid} ... "
                  f"{note if cell else 'SKIP ' + note}", flush=True)
            if cell:
                done[pid] = cell
            else:
                skipped.append((pid, note))

    cells = [done[p] for p in ids if p in done]
    if not cells:
        print("nothing to proof")
        return 1
    per = args.cols * args.rows
    pages = []
    for i in range(0, len(cells), per):
        # composed with +append/-append rather than `magick montage`, which
        # renders a filename label even when not asked and dies here with
        # "unable to read font ''"
        page_cells = cells[i:i + per]
        strips = []
        for j in range(0, len(page_cells), args.cols):
            strip = work / f"strip{i:04d}_{j:02d}.png"
            subprocess.run(["magick", *[str(c) for c in page_cells[j:j + args.cols]],
                            "-background", "white", "-gravity", "north",
                            "+append", str(strip)], check=True)
            strips.append(strip)
        pg = work / f"page{i // per:04d}.png"
        subprocess.run(["magick", *[str(x) for x in strips], "-background",
                        "white", "-gravity", "west", "-append", str(pg)],
                       check=True)
        pages.append(pg)
    subprocess.run(["magick", *[str(p) for p in pages], str(out)], check=True)
    print(f"\n{len(cells)} proofed, {len(skipped)} skipped, "
          f"{len(pages)} pages -> {out}")
    for pid, why in skipped[:20]:
        print(f"  skipped {pid}: {why}")
    if len(skipped) > 20:
        print(f"  ... and {len(skipped) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
