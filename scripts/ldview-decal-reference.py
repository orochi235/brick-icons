#!/usr/bin/env python3
"""LDView's view of a printed part's decoration, resampled onto our decal's
own UV canvas so the two sit side by side at one LDU scale.

    .venv/bin/python scripts/ldview-decal-reference.py 3068bp00 3626bp39

For every decal panel our extraction draws (the groups behind
`unwrap.decal_sheet`), the whole part goes through the vendored LDView with
its body painted the gray our sheets fill the carrier face with (white where
the panel has no face), no lighting and no edge lines, looked at straight
down the carrier normal at the panel's center. LDView cannot unwrap, only
project: a flat carrier's head-on view IS its unwrap, while a curved one is
foreshortened by cos(theta) away from the center. So a curved carrier is
rendered in strips of at most STRIP_DEG of arc, each looked at head-on, and
every pixel of our canvas is filled by pushing its (u, v) through
`unwrap.to_xyz` and the strip's view matrix and reading the LDView pixel
there. The snapshot's pixel scale is measured off a magenta frame written
into the wrapper file at a known place in view space, not taken from
LDView's camera fit.

Output goes under --out (default out/ldview-decal/), one set per part and
overwritten on every run, so the directory never grows past the parts named:
  <part>[.<k>].ours.png     our texture_svg for the panel, rasterized
  <part>[.<k>].ldview.png   LDView, resampled onto the same canvas
  <part>[.<k>].headon.png   the raw head-on snapshot of the center strip
  sheet-<part>.png          ours | LDView | diff
Wrapper files and per-strip snapshots live in a temp dir and are deleted.
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import _sheet  # noqa: E402
from brick_icons import hlr, unwrap  # noqa: E402
from brick_icons.config import load_config  # noqa: E402

STRIP_DEG = 60.0        # widest arc one head-on view is asked to cover
FRAME_T = 1.0           # LDU, the registration frame's thickness
FRAME_LIFT = 8.0        # LDU the frame floats in front of the strip; also
                        # ModelSize is LDView's far clip, so the sphere has to
                        # hold both the frame and the surface behind it
FRAME_COLOR = "0x2FF00FF"
FACE_GRAY = "0x2F2F2F2"   # what `unwrap._panel_paths` fills the carrier face with
WHITE = "0x2FFFFFF"
PX = 900                # our canvas's longer edge, as `brick-icons --decal`
OVERSAMPLE = 2.0        # LDView px per our px, before resampling
MAX_SNAPSHOT = 4096


def panels(part, ldraw_dir):
    """[(carrier, theta0, regions, face, ext)]: `unwrap.decal_panels` with
    the carrier kept, which is what a camera has to be pointed at."""
    tri, cols, ana = hlr.part_geometry(part, ldraw_dir)
    tris = np.asarray(tri, float) if len(tri) else np.empty((0, 3, 3))
    members, inside, flat = unwrap._decoration_members(tris, cols, ana)
    whole = unwrap._pieces_across_carriers(tris, cols, members, inside)
    taken = {int(i) for idx, _g, _k in whole for i in idx}
    groups = unwrap._carrier_groups(
        members, tris, inside, flat, exclude=taken,
        exclude_keys={k for _i, _g, keys in whole for k in keys})
    if not any(c == 16 for c in cols) and not any(
            getattr(p, "color", 16) == 16 for p in ana):
        groups = unwrap._drop_bare_sheet(groups)
    if whole:
        groups = sorted(groups + [g for _i, g, _k in whole],
                        key=lambda g: -unwrap._print_area(g))
        groups = unwrap.significant_groups(groups, cap=None, shatter=False)
    else:
        groups = unwrap.significant_groups(groups)
    if not groups:
        groups = unwrap.significant_groups(unwrap.mesh_groups(tris, cols),
                                           cap=None, shatter=False)
    out = []
    for carrier, theta0, regions, face in groups:
        rings = [r for _c, g in regions for r in unwrap._rings_of(g) if len(r)]
        if not rings:
            continue
        uv = np.vstack([np.asarray(r) for r in rings])
        held = uv if face is None else np.vstack(
            [uv, np.asarray(face.exterior.coords, float)])
        out.append((carrier, theta0, regions, face,
                    unwrap.carrier_extent(carrier, held)))
    return out


def kind_of(carrier):
    if isinstance(carrier, unwrap.Plane):
        return "plane"
    if isinstance(carrier, unwrap.Mesh):
        return "mesh"
    return f"{carrier.kind}{'+skirt' if isinstance(carrier, unwrap.Skirt) else ''}"


def xyz(uv, carrier, theta0):
    return unwrap.to_xyz(np.asarray(uv, float).reshape(-1, 2), carrier, theta0)


def view_matrix(carrier, theta0, uc, vc, d=0.05):
    """(M, pc): world -> LDView view space, camera outside the carrier looking
    down its normal at (uc, vc), screen up along +v. Screen right is then
    forced by handedness, so a mirrored unwrap shows up as a mirror here."""
    pc = xyz([[uc, vc]], carrier, theta0)[0]
    eu = xyz([[uc + d, vc]], carrier, theta0)[0] - xyz([[uc - d, vc]], carrier, theta0)[0]
    ev = xyz([[uc, vc + d]], carrier, theta0)[0] - xyz([[uc, vc - d]], carrier, theta0)[0]
    eu /= np.linalg.norm(eu)
    ev /= np.linalg.norm(ev)
    n = np.cross(eu, ev)
    n /= np.linalg.norm(n)
    if not isinstance(carrier, (unwrap.Plane, unwrap.Mesh)):
        a = np.array(carrier.R[:, 1], float)     # a copy: R is the carrier's
        a /= np.linalg.norm(a)
        rel = pc - np.asarray(carrier.t, float)
        radial = rel - a * float(rel @ a)
        if float(n @ radial) < 0:
            n = -n
    right = np.cross(ev, n)
    # LDView's front view: +x right, +y DOWN, camera on -z looking along +z
    return np.array([right, -ev, -n]), pc


def mid_radius(carrier, ext):
    """World radius of a curved carrier at the panel's mid-height."""
    (_u0, v0), (_u1, v1) = ext.min(axis=0), ext.max(axis=0)
    vm = (v0 + v1) / 2
    r = float(np.linalg.norm(carrier.R[:, 0]))
    h = float(np.linalg.norm(carrier.R[:, 1])) or 1.0
    level = -vm / h if unwrap.axis_reversed(carrier) else vm / h
    return r * float(carrier.radius_at(level))


def strips(carrier, theta0, ext):
    """[(ua, ub)] slices of the panel's u-range no wider than STRIP_DEG of
    arc, at the radius of the panel's mid-height; one slice for a plane."""
    (u0, _v0), (u1, _v1) = ext.min(axis=0), ext.max(axis=0)
    if isinstance(carrier, (unwrap.Plane, unwrap.Mesh)):
        return [(u0, u1)]
    rad = mid_radius(carrier, ext)
    n = max(1, math.ceil((u1 - u0) / (rad * math.radians(STRIP_DEG))))
    edges = np.linspace(u0, u1, n + 1)
    return list(zip(edges[:-1], edges[1:]))


def strip_frame(carrier, theta0, M, pc, ua, ub, v0, v1, k=48):
    """View-space bbox (xa, xb, ya, yb, zmin, zmax) of the strip's boundary."""
    us = np.linspace(ua, ub, k)
    vs = np.linspace(v0, v1, k)
    ring = np.vstack([np.column_stack([us, np.full(k, v0)]),
                      np.column_stack([np.full(k, ub), vs]),
                      np.column_stack([us, np.full(k, v1)]),
                      np.column_stack([np.full(k, ua), vs])])
    V = (xyz(ring, carrier, theta0) - pc) @ M.T
    lo, hi = V.min(axis=0), V.max(axis=0)
    return lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]


def wrapper(path, part_file, M, pc, xa, xb, ya, yb, zf, body):
    """The part in view space, its body in `body`, plus the magenta frame."""
    T = -M @ pc
    m = " ".join(f"{v:.6f}" for v in [*T, *M.ravel()])
    T_ = FRAME_T
    quads = [
        (xa - T_, ya - T_, xb + T_, ya),        # top
        (xa - T_, yb, xb + T_, yb + T_),        # bottom
        (xa - T_, ya, xa, yb),                  # left
        (xb, ya, xb + T_, yb),                  # right
    ]
    lines = [f"0 {part_file.stem} decal reference",
             f"1 {body} {m} {part_file.name}"]
    for x0, y0, x1, y1 in quads:
        lines.append(f"4 {FRAME_COLOR} {x0:.4f} {y0:.4f} {zf:.4f} "
                     f"{x1:.4f} {y0:.4f} {zf:.4f} {x1:.4f} {y1:.4f} {zf:.4f} "
                     f"{x0:.4f} {y1:.4f} {zf:.4f}")
    path.write_text("\n".join(lines) + "\n")
    return path


def snapshot(cfg, ldr, png, px, center, size):
    argv = [
        *cfg.ldview_launcher, str(cfg.ldview), str(ldr),
        f"-LDrawDir={cfg.ldraw_dir.resolve()}",
        f"-SaveSnapshot={png}", f"-SaveWidth={px}", f"-SaveHeight={px}",
        "-AutoCrop=1", "-SaveAlpha=0", "-BackgroundColor3=0xFFFFFF",
        "-Lighting=0", "-EdgeLines=0", "-ConditionalHighlights=0",
        "-ShowHighlightLines=0", "-BFC=0", "-Seams=0", "-Texmaps=1",
        f"-CurveQuality={cfg.curve_quality}", "-HiResPrimitives=1",
        "-AllowPrimitiveSubstitution=1",
        "-DefaultLatLong=0,0", "-FOV=0.1",
        f"-ModelCenter={center[0]:.4f},{center[1]:.4f},{center[2]:.4f}",
        f"-ModelSize={size:.4f}",
    ]
    subprocess.run(argv, check=True, capture_output=True, timeout=120)
    if not png.exists():
        raise RuntimeError(f"LDView did not write {png}")
    return np.asarray(Image.open(png).convert("RGB"))


def frame_box(img):
    """Pixel bbox (r0, r1, c0, c1), inclusive, of the magenta frame."""
    m = (img[:, :, 0] > 200) & (img[:, :, 1] < 80) & (img[:, :, 2] > 200)
    rows, cols = np.where(m)
    if not len(rows):
        raise RuntimeError("no registration frame in the snapshot")
    return rows.min(), rows.max(), cols.min(), cols.max()


def rasterize(svg_text, png):
    svg = png.with_suffix(".svg")
    svg.write_text(svg_text)
    subprocess.run(["resvg", str(svg), str(png)], check=True)
    svg.unlink()
    return Image.open(png).convert("RGB")


def reference(cfg, part_file, carrier, theta0, ext, W, H, td, tag, body):
    """(image WxH, head-on crop): LDView resampled onto our canvas."""
    (x0, v0), (x1, y1) = ext.min(axis=0), ext.max(axis=0)
    sx, sy = W / (x1 - x0), H / (y1 - v0)
    out = np.full((H, W, 3), 255, np.uint8)
    cols = x0 + (np.arange(W) + 0.5) / sx
    rows = y1 - (np.arange(H) + 0.5) / sy
    vc = (v0 + y1) / 2
    bands = strips(carrier, theta0, ext)
    headon = None
    for k, (ua, ub) in enumerate(bands):
        uc = (ua + ub) / 2
        M, pc = view_matrix(carrier, theta0, uc, vc)
        xa, xb, ya, yb, zmin, zmax = strip_frame(carrier, theta0, M, pc, ua, ub, v0, y1)
        zf = zmin - FRAME_LIFT
        ldr = wrapper(td / f"{tag}.{k}.ldr", part_file, M, pc, xa, xb, ya, yb, zf, body)
        fw, fh = xb - xa + 2 * FRAME_T, yb - ya + 2 * FRAME_T
        size = math.sqrt(fw ** 2 + fh ** 2 + (zmax - zf) ** 2) * 1.1
        px = int(min(MAX_SNAPSHOT, max(512, math.ceil(OVERSAMPLE * max(sx, sy) * size))))
        img = snapshot(cfg, ldr, td / f"{tag}.{k}.png", px,
                       ((xa + xb) / 2, (ya + yb) / 2, (zf + zmax) / 2), size)
        r0, r1, c0, c1 = frame_box(img)
        px_x = (c1 + 1 - c0) / fw
        px_y = (r1 + 1 - r0) / fh
        # every canvas pixel in this strip, through the surface and the view
        sel = np.where((cols >= ua) & (cols < ub) | ((k == 0) & (cols < ua))
                       | ((k == len(bands) - 1) & (cols >= ub)))[0]
        if not len(sel):
            continue
        U, Vv = np.meshgrid(cols[sel], rows)
        P = xyz(np.column_stack([U.ravel(), Vv.ravel()]), carrier, theta0)
        V = (P - pc) @ M.T
        ci = np.floor(c0 + (V[:, 0] - (xa - FRAME_T)) * px_x).astype(int)
        ri = np.floor(r0 + (V[:, 1] - (ya - FRAME_T)) * px_y).astype(int)
        ok = (ci >= c0) & (ci <= c1) & (ri >= r0) & (ri <= r1)
        samp = np.full((len(ci), 3), 255, np.uint8)
        samp[ok] = img[ri[ok], ci[ok]]
        out[:, sel] = samp.reshape(H, len(sel), 3)
        if k == len(bands) // 2:
            ti, tj = int(round(FRAME_T * px_y)), int(round(FRAME_T * px_x))
            headon = Image.fromarray(img[r0 + ti:r1 + 1 - ti, c0 + tj:c1 + 1 - tj])
    if headon is not None and headon.width > PX:
        headon = headon.resize((PX, max(1, round(headon.height * PX / headon.width))))
    return Image.fromarray(out), headon


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/ldview-decal")
    ap.add_argument("--px", type=int, default=PX)
    args = ap.parse_args()
    cfg = load_config(toml_path=ROOT / "labels.toml", root=ROOT)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sheets = []
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        for i, part in enumerate(args.parts, 1):
            part_file = hlr._resolve_input(part, hlr.default_roots(cfg.ldraw_dir))
            found = panels(part, cfg.ldraw_dir)
            if not found:
                print(f"[{i}/{len(args.parts)}] {part}: no decal panel", flush=True)
                continue
            rows = []
            for k, (carrier, theta0, regions, face, ext) in enumerate(found):
                tag = part if len(found) == 1 else f"{part}.{k}"
                kind = kind_of(carrier)
                if kind == "mesh":
                    print(f"[{i}/{len(args.parts)}] {tag}: mesh carrier, skipped",
                          flush=True)
                    continue
                ours = rasterize(unwrap.texture_svg(ext, regions, px=args.px,
                                                    ldraw_dir=cfg.ldraw_dir, face=face),
                                 out / f"{tag}.ours.png")
                # the body stands in for the face our sheet fills gray; a
                # panel with no face is drawn on white, so the body is too
                body = WHITE if face is None or face.is_empty else FACE_GRAY
                ldv, headon = reference(cfg, part_file, carrier, theta0, ext,
                                        ours.width, ours.height, td, tag, body)
                ldv.save(out / f"{tag}.ldview.png")
                if headon is not None:
                    headon.save(out / f"{tag}.headon.png")
                span = ""
                if kind != "plane":
                    arc = (ext[:, 0].max() - ext[:, 0].min()) / mid_radius(carrier, ext)
                    span = f" {math.degrees(arc):.0f} deg"
                n = len(strips(carrier, theta0, ext))
                rows.append((f"{tag}\n{kind}{span}\n{n} view{'s' if n > 1 else ''}",
                             ours, ldv))
                print(f"[{i}/{len(args.parts)}] {tag}: {kind}{span}, {n} LDView view(s)",
                      flush=True)
            if rows:
                path = out / f"sheet-{part}.png"
                _sheet.sheet("decal: ours (unwrap) | LDView (head-on views, resampled "
                             "onto our UV canvas; body painted as our face) | diff",
                             rows, columns=("ours", "LDView"), out=path)
                sheets.append(path)
    for p in sheets:
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
