#!/usr/bin/env python3
"""Swept extent of an SVG's ink, and how far it sits from the reported bbox.

    python scripts/compare-extents.py --out /tmp/extents.json

`goldens.summarize_svg` builds `bbox` from path ENDPOINTS. An arc's extreme
usually falls between its endpoints, so re-splitting one ellipse into a
different number of arcs moves that number without moving any ink — which is
why a naive-vs-occt bbox delta is not by itself evidence of a geometry change.
This renders the `outline` corpus under both engines and prints both measures
per part: `d_reported` is what the goldens would record, `d_swept` is the ink.
"""
import pathlib
import sys
import re, math
import numpy as np
import xml.etree.ElementTree as ET

TOK = re.compile(r'([MLAZmlaz])|(-?\d*\.?\d+(?:[eE]-?\d+)?)')

def _parse(d):
    out = []
    for m in TOK.finditer(d):
        out.append(m.group(1) if m.group(1) else float(m.group(2)))
    return out

def _arc(p0, rx, ry, phi_deg, laf, sf, p1, n=96):
    phi = math.radians(phi_deg)
    if rx == 0 or ry == 0 or np.allclose(p0, p1):
        return np.array([p0, p1])
    cs, sn = math.cos(phi), math.sin(phi)
    dp = (p0 - p1) / 2.0
    x1 = cs*dp[0] + sn*dp[1]; y1 = -sn*dp[0] + cs*dp[1]
    rx, ry = abs(rx), abs(ry)
    lam = x1*x1/(rx*rx) + y1*y1/(ry*ry)
    if lam > 1:
        rx *= math.sqrt(lam); ry *= math.sqrt(lam)
    num = rx*rx*ry*ry - rx*rx*y1*y1 - ry*ry*x1*x1
    den = rx*rx*y1*y1 + ry*ry*x1*x1
    co = math.sqrt(max(num, 0)/den) if den else 0.0
    if laf == sf:
        co = -co
    cxp = co*rx*y1/ry; cyp = -co*ry*x1/rx
    c = np.array([cs*cxp - sn*cyp, sn*cxp + cs*cyp]) + (p0 + p1)/2.0
    v0 = np.array([(x1-cxp)/rx, (y1-cyp)/ry])
    v1 = np.array([(-x1-cxp)/rx, (-y1-cyp)/ry])
    th0 = math.atan2(v0[1], v0[0])
    dth = math.atan2(v1[1], v1[0]) - th0
    if not sf and dth > 0:
        dth -= 2*math.pi
    if sf and dth < 0:
        dth += 2*math.pi
    th = th0 + dth*np.linspace(0, 1, n)
    x = c[0] + rx*np.cos(th)*cs - ry*np.sin(th)*sn
    y = c[1] + rx*np.cos(th)*sn + ry*np.sin(th)*cs
    return np.stack([x, y], axis=1)

def flatten_d(d):
    t = _parse(d); i = 0; cur = np.zeros(2); start = np.zeros(2)
    pts = []; cmd = None
    while i < len(t):
        if isinstance(t[i], str):
            cmd = t[i]
            if cmd in ('Z', 'z') and len(pts):
                pts.append(start.copy()); cur = start.copy()
            i += 1; continue
        if cmd in ('M', 'm'):
            p = np.array([t[i], t[i+1]]); i += 2
            cur = p if cmd == 'M' else cur + p
            start = cur.copy(); pts.append(cur.copy())
            cmd = 'L' if cmd == 'M' else 'l'
        elif cmd in ('L', 'l'):
            p = np.array([t[i], t[i+1]]); i += 2
            cur = p if cmd == 'L' else cur + p
            pts.append(cur.copy())
        elif cmd in ('A', 'a'):
            rx, ry, rot = t[i], t[i+1], t[i+2]
            laf, sf = int(t[i+3]), int(t[i+4])
            p = np.array([t[i+5], t[i+6]]); i += 7
            end = p if cmd == 'A' else cur + p
            pts.extend(list(_arc(cur, rx, ry, rot, laf, sf, end)))
            cur = end
        else:
            i += 1
    return np.array(pts) if pts else np.zeros((0, 2))

def _tag(el):
    return el.tag.split('}')[-1]

def _ink(el):
    """Every painted element, skipping masks: a clipPath is not ink, and
    counting it puts the silhouette's outset boundary in the extent."""
    for child in el:
        if _tag(child) in ('defs', 'clipPath', 'mask'):
            continue
        yield child
        yield from _ink(child)


def extents(text):
    """(true_swept_bbox, endpoint_only_bbox) for one SVG."""
    root = ET.fromstring(text)
    swept = []; ends = []
    for el in _ink(root):
        t = _tag(el)
        if t == 'path' and el.get('d'):
            f = flatten_d(el.get('d'))
            if len(f):
                swept.append(f)
                ends.append(np.array([f[0], f[-1]]))
        elif t == 'line':
            try:
                seg = np.array([[float(el.get('x1')), float(el.get('y1'))],
                                [float(el.get('x2')), float(el.get('y2'))]])
            except (TypeError, ValueError):
                continue
            swept.append(seg); ends.append(seg)
    if not swept:
        return None, None
    S = np.vstack(swept)
    return ([S[:, 0].min(), S[:, 1].min(), S[:, 0].max(), S[:, 1].max()], None)


def _load_corpus(root):
    import tomllib
    cfg = tomllib.loads((root / "tests/goldens/manifest.toml").read_text())
    spec = cfg["combo"]["outline"]
    names = spec["parts"]
    parts = cfg["parts"][names] if isinstance(names, str) else names
    return parts, spec["args"]


def main():
    import argparse, json, subprocess, tempfile
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", help="keep renders here (default: a temp dir)")
    a = ap.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from brick_icons import goldens

    parts, args = _load_corpus(root)
    work = pathlib.Path(a.work) if a.work else pathlib.Path(tempfile.mkdtemp())
    rows = []
    for i, part in enumerate(parts, 1):
        row = {"part": part}
        for eng in ("naive", "occt"):
            d = work / f"{part}-{eng}"
            d.mkdir(parents=True, exist_ok=True)
            p = subprocess.run([sys.executable, "-m", "brick_icons.cli", part,
                                *args, "--engine", eng, "--out", str(d)],
                               capture_output=True, text=True, cwd=root)
            svgs = sorted(d.glob("*.svg"))
            if p.returncode != 0 or not svgs:
                tail_ = (p.stderr or p.stdout).strip().splitlines()
                row[eng] = {"error": tail_[-1] if tail_ else "no svg"}
                continue
            text = svgs[0].read_text()
            swept, _ = extents(text)
            row[eng] = {"reported": goldens.summarize_svg(text).get("bbox"),
                        "swept": [round(float(v), 2) for v in swept] if swept else None}
        n, o = row.get("naive", {}), row.get("occt", {})
        if n.get("reported") and o.get("reported"):
            row["d_reported"] = [round(b - c, 2) for c, b in zip(n["reported"], o["reported"])]
            row["d_swept"] = [round(b - c, 2) for c, b in zip(n["swept"], o["swept"])]
            print(f"{i:2d}/{len(parts)} {part:12s} "
                  f"d_reported={row['d_reported']}  d_swept={row['d_swept']}", flush=True)
        else:
            print(f"{i:2d}/{len(parts)} {part:12s} ERROR "
                  f"{n.get('error') or o.get('error')}", flush=True)
        rows.append(row)
    pathlib.Path(a.out).write_text(json.dumps(rows, indent=1))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
