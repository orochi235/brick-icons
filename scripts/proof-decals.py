"""Proof sheet: every printed part's decal laid flat, beside LDView's render.

Printed parts are the one class we cannot eyeball in the icon output, because a
decal that fails to bind renders as a blank brick — indistinguishable from an
unprinted one. Flattening the decal into its carrier's parameter space shows
what SHOULD be drawn, and putting LDView's own colour render next to it shows
what the part actually is. Disagreement between the two columns is a bug in the
unwrap; agreement means only the projection is left to check.

Emits a paginated PDF, one row per part: LDView on the left, flat decal on the
right.

    .venv/bin/python scripts/proof-decals.py --limit 40 --out out/proof.pdf
    .venv/bin/python scripts/proof-decals.py 3941p01 3942bp01 3068bp00

The unwrap here is deliberately standalone so this runs against any checkout.
Once `brick_icons/unwrap.py` lands, replace `_unwrap` with a call into it
rather than letting the two drift.

Needs: resvg, imagemagick (see scripts/external-deps.lock)
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import render  # noqa: E402
from brick_icons.colors import parse_ldconfig  # noqa: E402
from brick_icons.config import load_config  # noqa: E402

LDRAW = ROOT / "vendor" / "ldraw"
PARTS = LDRAW / "parts"
PAL = {c.code: c for c in parse_ldconfig(open(LDRAW / "LDConfig.ldr", errors="replace"))}


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
    """The carrier as ONE rectangle. Drawing every body facet leaves the
    backdrop ragged with stud and notch silhouettes; the surface a decal sits
    on is a quad, so draw that."""
    if not polys:
        return []
    allp = np.vstack(polys)
    x0, y0 = allp.min(axis=0)
    x1, y1 = allp.max(axis=0)
    return [(16, np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]))]


def _unwrap(deco, body):
    """(polys, kind) in carrier parameter space, LDU on both axes.

    Cylinder and cone both unwrap to (arc length, height) about the part axis,
    which is what keeps a lamp round; a plane unwraps in its own basis. The
    axis is Y in LDraw. Radius spread across the decal picks between them.
    """
    pts = np.vstack([p for _, p in deco])
    # planarity decides, not radius spread: a 45-degree slope face has a tight
    # radius spread about the part axis and was being unwrapped as a cylinder,
    # which skews its rectangular border into a trapezoid
    c = pts.mean(axis=0)
    normal = np.linalg.svd(pts - c)[2][2]
    curved = float(np.abs((pts - c) @ normal).max()) > 0.5
    r = np.hypot(pts[:, 0], pts[:, 2])
    if curved:
        rr = max(r.mean(), 1e-6)
        out = []
        for c, p in deco:
            th = np.arctan2(p[:, 2], p[:, 0])
            if np.ptp(th) > math.pi:
                th = np.where(th < 0, th + 2 * math.pi, th)
            out.append((c, np.column_stack([rr * th, p[:, 1]])))
        # only body facets ON the decal's own surface: studs and underside
        # notches otherwise make the backdrop ragged, and the carrier is a
        # quad by construction
        # a cone's radius varies with height, so a single mean radius catches
        # only a thin band of its wall; fit radius(h) from the decal and test
        # body facets against that
        hs, rs = pts[:, 1], np.hypot(pts[:, 0], pts[:, 2])
        k, b = (np.polyfit(hs, rs, 1) if np.ptp(hs) > 1e-6 else (0.0, rr))
        on = [p for _, p in body
              if np.all(np.abs(np.hypot(p[:, 0], p[:, 2]) - (k * p[:, 1] + b)) < 0.8)]
        carrier = _quad([np.column_stack(
            [rr * np.arctan2(q[:, 2], q[:, 0]), q[:, 1]]) for q in on])
        return out, carrier, "curved"
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


def decal_svg(deco, carrier, px=560, pad=10, margin=0.12):
    """Cropped to the decal, with the carrier's edge dashed.

    A cylinder's carrier spans its whole circumference, so framing on the
    carrier letterboxes the decal into a sliver of mostly blank wall. Frame on
    the decal instead and draw the carrier boundary dashed: where it shows,
    the decal stops short of the edge; where it does not, the carrier runs on
    past the crop. One uniform scale throughout — scaling x and y
    independently warps the decal and turns a round lamp into an ellipse.
    """
    allp = np.vstack([p for _, p in deco])
    x0, y0 = allp.min(axis=0)
    x1, y1 = allp.max(axis=0)
    m = margin * max(x1 - x0, y1 - y0, 1e-9)
    x0, y0, x1, y1 = x0 - m, y0 - m, x1 + m, y1 + m
    s = px / max(x1 - x0, y1 - y0, 1e-9)
    w, h = (x1 - x0) * s + 2 * pad, (y1 - y0) * s + 2 * pad

    def xy(p):
        return np.column_stack([(p[:, 0] - x0) * s + pad, (y1 - p[:, 1]) * s + pad])

    def d(p):
        return " ".join(f"{'M' if i == 0 else 'L'}{a:.2f},{b:.2f}"
                        for i, (a, b) in enumerate(xy(p))) + " Z"

    body = [f'<path d="{d(p)}" fill="#f2f2f2" stroke="none"/>' for _, p in carrier]
    body += [f'<path d="{d(p)}" fill="'
             f'{PAL[c].hex.replace("0x", "#") if c in PAL else "#888"}" '
             f'stroke="none"/>' for c, p in deco]
    body += [f'<path d="{d(p)}" fill="none" stroke="#b0b0b0" '
             f'stroke-width="1.4" stroke-dasharray="6 4"/>' for _, p in carrier]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
            f'height="{h:.0f}"><rect width="{w:.0f}" height="{h:.0f}" '
            f'fill="#ffffff"/>' + "".join(body) + "</svg>")


def printed_ids(limit=None):
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
        if limit and len(ids) >= limit:
            break
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--out", default="out/proof-decals.pdf")
    ap.add_argument("--rows", type=int, default=6, help="rows per PDF page")
    args = ap.parse_args()

    ids = args.parts or printed_ids(args.limit)
    out = Path(args.out)
    work = out.parent / "proof-work"
    work.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    rows, skipped = [], []

    for n, pid in enumerate(ids, 1):
        print(f"[{n}/{len(ids)}] {pid} ... ", end="", flush=True)
        try:
            polys = []
            flatten(PARTS / f"{pid}.dat", np.eye(3), np.zeros(3), 16, polys)
            deco = [(c, p) for c, p in polys if c not in (16, 24)]
            if not deco:
                print("no decoration")
                skipped.append((pid, "no decoration"))
                continue
            body = [(c, p) for c, p in polys if c == 16]
            flat, carrier, kind = _unwrap(deco, body)
            (work / f"{pid}.svg").write_text(decal_svg(flat, carrier))
            subprocess.run(["resvg", "--background", "white",
                            str(work / f"{pid}.svg"), str(work / f"{pid}.png")],
                           check=True, capture_output=True)
            ref = work / f"{pid}.ldview.png"
            subprocess.run(render.build_argv(cfg, PARTS / f"{pid}.dat", ref),
                           check=True, capture_output=True)
            row = work / f"{pid}.row.png"
            subprocess.run(["magick", str(ref), str(work / f"{pid}.png"),
                            "-background", "white", "-gravity", "center",
                            "-resize", "460x460", "-extent", "480x480",
                            "+append", str(row)], check=True)
            rows.append(row)
            print(f"ok ({kind}, {len(deco)} facets)")
        except (subprocess.CalledProcessError, ValueError, IndexError,
                OSError) as e:
            print(f"FAILED ({type(e).__name__})")
            skipped.append((pid, type(e).__name__))

    if not rows:
        print("nothing to proof")
        return 1
    pages = []
    for i in range(0, len(rows), args.rows):
        pg = work / f"page{i // args.rows:03d}.png"
        subprocess.run(["magick", *[str(r) for r in rows[i:i + args.rows]],
                        "-background", "white", "-append", str(pg)], check=True)
        pages.append(pg)
    subprocess.run(["magick", *[str(p) for p in pages], str(out)], check=True)
    print(f"\n{len(rows)} proofed, {len(skipped)} skipped -> {out}")
    for pid, why in skipped:
        print(f"  skipped {pid}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
