"""Sweep printed parts for colored primitives sitting on a connector.

LDraw authors a minifig torso's neck as a 270-degree color-16 cylinder plus a
90-degree one in black — the `// Neck mark` convention. That mark is covered by
the head on an assembled figure, so it does not belong in an extracted decal.

There is no way to tell it from real print by authoring shape: 3942bp01's cone
stripes partition their wall into colored and color-16 sectors summing to 360
exactly as the neck does. What separates them is position — the mark rides
geometry that protrudes past the part's body, and the stripes ride the body
itself. This measures that split across the corpus, so the size and the false
positives of a connector filter are known before it goes into the library.

`share` is the colored fraction of the ring; `outside` is the colored
primitive's extent along the part's up axis measured against the envelope of
its color-16 TRIANGLES — a connector reads positive, body geometry does not.

    .venv/bin/python scripts/sweep-marker-prims.py --out out/markers.tsv
    .venv/bin/python scripts/sweep-marker-prims.py --limit 300 --jobs 8

Flattens references only — no HLR, no view — so the whole corpus is minutes,
not hours.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import hlr  # noqa: E402
from brick_icons.colors import parse_ldconfig  # noqa: E402
from brick_icons.config import load_config  # noqa: E402

LDRAW = ROOT / "vendor" / "ldraw"
PARTS = LDRAW / "parts"
PAL = {c.code: c for c in parse_ldconfig(open(LDRAW / "LDConfig.ldr", errors="replace"))}

COINCIDE_TOL = 0.01     # LDU; survives matrix composition through references


def _surface(prim):
    """The surface a primitive lies on, independent of which sector of it the
    primitive covers or what color it is."""
    q = lambda v: tuple(np.round(np.asarray(v, float) / COINCIDE_TOL).astype(np.int64))
    return (prim.kind, q(prim.t), q(prim.R[:, 1]),
            int(round(float(np.linalg.norm(prim.R[:, 0])) / COINCIDE_TOL)))


def markers_in(part_id: str, ldraw_dir):
    """[(color, kind, share, outside)] per colored primitive that shares a
    surface with a color-16 one. `share` is its color's fraction of the ring;
    `outside` is how far its extent clears the body triangles' envelope."""
    roots = hlr.default_roots(ldraw_dir)
    path = hlr._resolve_input(part_id, roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(path, np.eye(3), np.zeros(3), out, roots)

    tris = np.asarray(out["tri"], float) if out["tri"] else None
    meta = out.get("tri_meta") or []
    body = None
    if tris is not None and len(meta) == len(tris):
        keep = np.array([m.get("color", 16) == 16 for m in meta])
        if keep.any():
            body = tris[keep]

    by_surface = defaultdict(list)
    for p in out["analytic"]:
        by_surface[_surface(p)].append(p)

    found = []
    for key, prims in by_surface.items():
        colors = {getattr(p, "color", 16) for p in prims}
        if 16 not in colors or colors == {16}:
            continue
        total = sum(p.sector for p in prims)
        for c in sorted(colors - {16}):
            members = [p for p in prims if getattr(p, "color", 16) == c]
            share = sum(p.sector for p in members) / max(total, 1e-9)
            found.append((c, key[0], share, _clearance(members, body)))
    return found


def _clearance(prims, body):
    """LDU by which `prims` clear the body triangles along the part's up axis.

    LDraw's up is -y, so a connector standing proud of the body sits at a more
    negative y than anything the body reaches. Positive means it protrudes.
    """
    if body is None or not len(body):
        return float("nan")
    top = float(body[..., 1].min())
    pts = np.vstack([np.asarray(p.fit_pts(), float) for p in prims])
    return top - float(pts[:, 1].max())


def printed_ids(limit=None, start=0):
    """Parts carrying geometry in a color other than 16/24."""
    ids = []
    for f in sorted(PARTS.glob("*.dat")):
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", default="out/markers.tsv")
    args = ap.parse_args()

    cfg = load_config()
    ids = args.parts or printed_ids(args.limit, args.start)
    print(f"sweeping {len(ids)} printed parts", flush=True)

    hits, failed, n = {}, [], 0
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(markers_in, p, str(cfg.ldraw_dir)): p
                   for p in ids}
        for fut in as_completed(futures):
            pid = futures[fut]
            n += 1
            try:
                found = fut.result()
            except Exception as e:
                failed.append((pid, f"{type(e).__name__}: {e}"))
                print(f"[{n}/{len(ids)}] {pid} ... FAIL {type(e).__name__}",
                      flush=True)
                continue
            if found:
                hits[pid] = found
            note = ", ".join(f"{c} {k} share={s:.2f} out={o:+.1f}"
                             for c, k, s, o in found) or "-"
            print(f"[{n}/{len(ids)}] {pid} ... {note}", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        fh.write("part\tcolor\tcolor_name\tkind\tshare\toutside\ttitle\n")
        for pid in sorted(hits):
            src = PARTS / f"{pid}.dat"
            try:
                title = src.read_text(errors="replace").splitlines()[0][2:].strip()
            except (OSError, IndexError):
                title = ""
            for c, kind, share, outside in hits[pid]:
                name = PAL[c].name if c in PAL else str(c)
                fh.write(f"{pid}\t{c}\t{name}\t{kind}\t{share:.3f}\t"
                         f"{outside:.2f}\t{title}\n")

    print(f"\n{len(hits)}/{len(ids)} parts share a surface between body and "
          f"decoration ({len(failed)} failed) -> {out}")

    protruding = [(p, f) for p, fs in hits.items() for f in fs if f[3] > 0.05]
    onbody = [(p, f) for p, fs in hits.items() for f in fs
              if not (f[3] > 0.05) and f[3] == f[3]]
    print(f"\n  protruding past the body (connector): {len(protruding)} "
          f"across {len({p for p, _ in protruding})} parts")
    print(f"  on the body itself (real print):       {len(onbody)} "
          f"across {len({p for p, _ in onbody})} parts")

    print("\nsample protruding:")
    for pid, (c, kind, share, o) in sorted(protruding)[:12]:
        print(f"  {pid:14s} {kind} col {c:3d} share {share:.2f} out {o:+.1f}")
    print("\nsample on-body:")
    for pid, (c, kind, share, o) in sorted(onbody)[:12]:
        print(f"  {pid:14s} {kind} col {c:3d} share {share:.2f} out {o:+.1f}")
    for pid, why in failed[:10]:
        print(f"  failed {pid}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
