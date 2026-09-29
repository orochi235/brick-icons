"""Which later-painted faces cover a formed sticker's largest print face.

Mirrors test_occt::test_a_sticker_is_not_clipped_by_the_slope_it_is_stuck_to,
then breaks the covered share down by the face that paints over it. With
--png, draws the print face, its covers and the covered region.

    .venv/bin/python scripts/sticker-cover.py 15068dy6 [--root TREE] --png out.png
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(next((sys.argv[i + 1] for i, x in enumerate(sys.argv)
                  if x == "--root"), Path.cwd())).resolve()
sys.path.insert(0, str(ROOT))
from brick_icons import geom2d, hlr, occt  # noqa: E402


def _geo(f):
    return geom2d.to_geom(f["poly"], f.get("holes") or [])


def _draw(path, part, faces, decal, covers, hidden_g, title):
    from PIL import Image, ImageDraw
    xs = [p[0] for f in faces for p in f["poly"]]
    ys = [p[1] for f in faces for p in f["poly"]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = 900 / max(x1 - x0, y1 - y0)
    W, H = int((x1 - x0) * s) + 40, int((y1 - y0) * s) + 70
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    tr = lambda p: (20 + (p[0] - x0) * s, 50 + (p[1] - y0) * s)
    for f in faces:
        d.polygon([tr(p) for p in f["poly"]], outline=(215, 215, 215))
    d.polygon([tr(p) for p in decal["poly"]], fill=(170, 200, 255), outline=(0, 60, 200))
    for g in [hidden_g] if hidden_g is not None else []:
        for poly in getattr(g, "geoms", [g]):
            if poly.is_empty or poly.geom_type != "Polygon":
                continue
            d.polygon([tr(p) for p in poly.exterior.coords], fill=(230, 40, 40))
    for f in covers:
        d.polygon([tr(p) for p in f["poly"]], outline=(120, 0, 0))
    d.text((20, 15), title, fill="black")
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part", nargs="?", default="15068dy6")
    ap.add_argument("--png")
    ap.add_argument("--title", default="")
    ap.add_argument("--root", help="tree to import brick_icons from")
    a = ap.parse_args()
    ldraw = ROOT / "vendor" / "ldraw"
    out = occt.flatten_part(a.part, ldraw)
    out["tri_colors"] = [m["color"] for m in out["tri_meta"]]
    out["printed"] = hlr._is_printed(
        hlr._resolve_input(a.part, hlr.default_roots(ldraw)))
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    faces = occt.ordered_faces(shape, occt.op_projection(right, up, fwd), out)
    deco = [f for f in faces if f.get("color", 16) != 16]
    decal = max(deco, key=lambda f: geom2d.area(_geo(f)))
    at = next(k for k, f in enumerate(faces) if f is decal)
    g = _geo(decal)
    total = geom2d.area(g)
    rows, cover = [], None
    for k, f in enumerate(faces[at + 1:], at + 1):
        gg = _geo(f)
        ov = geom2d.area(geom2d.intersection(g, gg))
        cover = gg if cover is None else geom2d.union(cover, gg)
        if ov > 1e-9:
            rows.append((ov / total, k, f))
    hidden_g = geom2d.intersection(g, cover) if cover is not None else None
    hidden = geom2d.area(hidden_g) / total if hidden_g is not None else 0.0
    print(f"{a.part}: decal at {at}/{len(faces)}, color {decal.get('color')}, "
          f"standoff {decal.get('standoff', 0.0):.3f}, area {total:.3f}, "
          f"hidden {hidden:.4%}")
    for share, k, f in sorted(rows, key=lambda r: -r[0])[:15]:
        keys = {kk: f[kk] for kk in ("color", "standoff", "kind") if kk in f}
        print(f"  {share:7.3%}  face {k:4d}  area {geom2d.area(_geo(f)):9.3f}  {keys}")
    if a.png:
        _draw(a.png, a.part, faces, decal, [f for _, _, f in rows], hidden_g,
              f"{a.title}  hidden {hidden:.2%}")


main()
