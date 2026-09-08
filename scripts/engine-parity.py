#!/usr/bin/env python3
"""How much of a naive-vs-occt disagreement is presentation, not geometry?

    scripts/engine-parity.py 3070b 3005 --out /tmp/parity.json
    scripts/engine-parity.py --combo outline-flat3

The two engines cannot produce the same bytes -- a BRep kernel reads a circle
where naive refits a polyline -- but a chunk of the raw text diff is not about
the drawing at all: a closed ring rotated to a different start vertex, the
same paths emitted in a different document order. Those are arbitrary, and
laundering them is what makes the REMAINING diff worth reading.

Each path is canonicalized (closed rings rotated to their lexicographically
smallest step-cycle; polylines also direction-normalized) and the two path
multisets are matched. Every path lands in one class:

  equal      identical text
  rotated    same ring, different start vertex or winding
  moved      same geometry, different position in the document
  near D     same command skeleton, coordinates differ by at most D px
  only       no counterpart in the other engine

`near` is the interesting one -- a sub-pixel D is naive's z-buffer bias
against occt's exact answer -- and `only` is where the engines genuinely draw
different things. `equal + rotated + moved` is the share of the diff that a
canonical emitter would delete outright.

Reads the CLI, never a private render path: both engines go through
`brick_icons.cli` exactly as a user runs them.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "goldens" / "manifest.toml"

_CMD = re.compile(r"([MLTCSQAZmltcsqaz])([^MLTCSQAZmltcsqaz]*)")
_NUM = re.compile(r"-?\d*\.?\d+(?:[eE][-+]?\d+)?")
# numbers per command, and where the endpoint sits inside them
_ARITY = {"M": (2, 0), "L": (2, 0), "T": (2, 0), "C": (6, 4),
          "S": (4, 2), "Q": (4, 2), "A": (7, 5), "Z": (0, 0)}


def parse_d(d: str):
    """[(cmd, [numbers...]), ...] with every number kept, absolute only."""
    ops = []
    for letter, body in _CMD.findall(d):
        if letter.islower() and letter != "z":
            raise ValueError(f"relative command {letter!r} unsupported")
        cmd = letter.upper()
        nums = [float(n) for n in _NUM.findall(body)]
        stride = _ARITY[cmd][0]
        if not stride:
            ops.append((cmd, []))
            continue
        for i in range(0, len(nums) - stride + 1, stride):
            ops.append((cmd, nums[i:i + stride]))
    return ops


def endpoint(op):
    cmd, nums = op
    at = _ARITY[cmd][1]
    return (nums[at], nums[at + 1])


def fmt(ops) -> str:
    out = []
    for cmd, nums in ops:
        out.append(cmd if not nums else
                   cmd + " " + " ".join(f"{n:.2f}" for n in nums))
    return " ".join(out)


def _cycle(ops):
    """(start_vertex, [steps]) for a closed path, or None.

    Z is a straight closure, so it becomes an explicit L step -- otherwise a
    rotation would have to invent the segment the ring is standing on.
    """
    if not ops or ops[0][0] != "M" or ops[-1][0] != "Z":
        return None
    start = endpoint(ops[0])
    steps = list(ops[1:-1])
    if not steps:
        return None
    if endpoint(steps[-1]) != start:
        steps.append(("L", [start[0], start[1]]))
    return start, steps


def _rebuild(start_after, steps):
    return [("M", [start_after[0], start_after[1]])] + steps + [("Z", [])]


def _reverse(start, steps):
    """Reverse a pure-polyline cycle. Arcs carry a sweep flag that reversal
    would have to flip, so they are left alone rather than flipped wrong."""
    if any(c != "L" for c, _ in steps):
        return None
    verts = [start] + [endpoint(s) for s in steps]
    verts = verts[:-1][::-1]
    rs = [("L", [v[0], v[1]]) for v in verts[1:]] + [("L", [verts[0][0], verts[0][1]])]
    return verts[0], rs


def canonical(d: str) -> str:
    """Rotation- and direction-independent text for one path."""
    ops = parse_d(d)
    cyc = _cycle(ops)
    if cyc is None:
        return fmt(ops)
    start, steps = cyc
    cands = [(start, steps)]
    rev = _reverse(start, steps)
    if rev:
        cands.append(rev)
    best = None
    for s0, ss in cands:
        for r in range(len(ss)):
            after = s0 if r == 0 else endpoint(ss[r - 1])
            text = fmt(_rebuild(after, ss[r:] + ss[:r]))
            if best is None or text < best:
                best = text
    return best


def paths_of(svg: str):
    """[(role, raw_d)] in document order. Role keeps a clip mask from
    matching a stroke that happens to trace the same ring."""
    root = ET.fromstring(svg)
    found = []

    def walk(el, role):
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("clipPath", "mask"):
            role = "clip"
        if tag == "path" and el.get("d"):
            found.append((role, el.get("d")))
        for ch in el:
            walk(ch, role)

    walk(root, "ink")
    return found


def _skeleton(d: str):
    return tuple(c for c, _ in parse_d(d))


# An `A` command is `rx ry rot large sweep x y`: two lengths, an angle in
# DEGREES, two booleans, a point. Maxing over all seven reports rot 0 vs 360
# -- the same ellipse -- as a 360px disagreement.
_POS = {"M": (0, 1), "L": (0, 1), "T": (0, 1), "C": (0, 1, 2, 3, 4, 5),
        "S": (0, 1, 2, 3), "Q": (0, 1, 2, 3), "A": (0, 1, 5, 6), "Z": ()}
_ANG = {"A": (2,)}
_FLAG = {"A": (3, 4)}


def _delta(a: str, b: str):
    """(px, deg, flags) between two paths with the same command skeleton, or
    None if they are not comparable."""
    if _skeleton(a) != _skeleton(b):
        return None
    oa, ob = parse_d(a), parse_d(b)
    px = deg = 0.0
    flags = 0
    for (ca, na), (cb, nb) in zip(oa, ob):
        if len(na) != len(nb):
            return None
        for i in _POS.get(ca, ()):
            px = max(px, abs(na[i] - nb[i]))
        for i in _ANG.get(ca, ()):
            d = abs(na[i] - nb[i]) % 360.0
            deg = max(deg, min(d, 360.0 - d))
        for i in _FLAG.get(ca, ()):
            flags += na[i] != nb[i]
    return px, deg, flags


def compare(a_paths, b_paths, near_tol=2.0):
    """Classify every path of both renders.

    A candidate further than `near_tol` px is NOT a near match: sharing a
    command skeleton pairs unrelated paths, which reported a 244px `near` on
    a 256px canvas. Past the tolerance both sides stay unmatched.
    """
    a = [(role, d, canonical(d), i) for i, (role, d) in enumerate(a_paths)]
    b = [(role, d, canonical(d), i) for i, (role, d) in enumerate(b_paths)]
    used_b, classes, deltas = set(), Counter(), []

    # exact text in the same slot, then canonical anywhere
    for role, d, canon, i in a:
        hit = None
        for j, (rb, db, cb, _) in enumerate(b):
            if j in used_b or rb != role:
                continue
            if db == d and i == j:
                hit, cls = j, "equal"
                break
        if hit is None:
            for j, (rb, db, cb, _) in enumerate(b):
                if j in used_b or rb != role:
                    continue
                if db == d:
                    hit, cls = j, "moved"
                    break
        if hit is None:
            for j, (rb, db, cb, _) in enumerate(b):
                if j in used_b or rb != role:
                    continue
                if cb == canon:
                    hit, cls = j, "rotated"
                    break
        if hit is None:
            best = None
            for j, (rb, db, cb, _) in enumerate(b):
                if j in used_b or rb != role:
                    continue
                dd = _delta(d, db)
                if dd is not None and (best is None or dd[0] < best[1][0]):
                    best = (j, dd)
            if best is not None and best[1][0] <= near_tol:
                hit, cls = best[0], "near"
                deltas.append(best[1])
        if hit is None:
            classes["naive_only"] += 1
            continue
        used_b.add(hit)
        classes[cls] += 1
    classes["occt_only"] = len(b) - len(used_b)
    return classes, deltas


def render_tessellated(part: str, engine: str, args: list[str], work: Path):
    """Both engines, with primitive substitution disarmed.

    `flatten` records a Cylinder/Disc/Ring analytically only when `from_ref`
    hands it one; returning None makes it recurse into the primitive file and
    tessellate instead -- so occt sews the SAME triangles naive rasterizes,
    and any surviving disagreement is the two occlusion implementations
    rather than the two solids. In-process, because there is no CLI flag for
    it and inventing one would put a parameter in the engine that only this
    probe uses.
    """
    from brick_icons import cli as _cli, primitives as _prims
    out = work / f"{part}-{engine}-tess"
    out.mkdir(parents=True, exist_ok=True)
    ap = _cli.build_parser()
    ns = ap.parse_args([part, *args, "--engine", engine, "--out", str(out)])
    cfg = _cli._config_from_args(ns)
    real = _prims.from_ref
    _prims.from_ref = lambda *a, **k: None
    try:
        _cli.process_one(cfg, part, out)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    finally:
        _prims.from_ref = real
    svgs = sorted(out.glob("*.svg"))
    return (svgs[0].read_text(), None) if svgs else (None, "no svg")


def render(part: str, engine: str, args: list[str], work: Path):
    out = work / f"{part}-{engine}"
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "brick_icons.cli", part, *args,
         "--engine", engine, "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT)
    svgs = sorted(out.glob("*.svg"))
    if not svgs:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        return None, (tail[-1] if tail else f"exit {proc.returncode}")
    return svgs[0].read_text(), None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--combo", help="take the part list and args from a manifest combo")
    ap.add_argument("--angle", default=None)
    ap.add_argument("--tessellate", action="store_true",
                    help="disarm primitive substitution so both engines see "
                         "the same triangles")
    ap.add_argument("--near-tol", type=float, default=2.0,
                    help="px a matched path may move and still count as near (default 2)")
    ap.add_argument("--out", type=Path, help="write the full JSON report here")
    a = ap.parse_args()

    args = ["--format", "svg", "--shading", "outline"]
    parts = list(a.parts)
    if a.combo:
        cfg = tomllib.loads(MANIFEST.read_text())
        spec = cfg["combo"][a.combo]
        args = list(spec["args"])
        parts = parts or cfg["parts"][spec["parts"]]
    if a.angle:
        args += ["--angle", a.angle]
    if not parts:
        ap.error("name at least one part, or pass --combo")

    rows, work = [], Path(tempfile.mkdtemp(prefix="parity-"))
    print(f"{'part':<12} {'equal':>6} {'moved':>6} {'rot':>5} {'near':>5} "
          f"{'maxPx':>7} {'maxDeg':>7} {'flags':>6} {'n-only':>7} {'o-only':>7}"
          f"  laundered")
    for n, part in enumerate(parts, 1):
        fn = render_tessellated if a.tessellate else render
        sa, ea = fn(part, "naive", args, work)
        sb, eb = fn(part, "occt", args, work)
        if ea or eb:
            why = f"naive: {ea}" if ea else f"occt: {eb}"
            print(f"{part:<12} {'ERROR':>6}  {why}")
            rows.append({"part": part, "error": why})
            continue
        cls, deltas = compare(paths_of(sa), paths_of(sb), near_tol=a.near_tol)
        tot = sum(cls[k] for k in
                  ("equal", "moved", "rotated", "near", "naive_only")) + cls["occt_only"]
        laundered = cls["equal"] + cls["moved"] + cls["rotated"]
        maxd = max((d[0] for d in deltas), default=0.0)
        maxdeg = max((d[1] for d in deltas), default=0.0)
        nflag = sum(d[2] for d in deltas)
        pct = 100.0 * laundered / tot if tot else 0.0
        print(f"{part:<12} {cls['equal']:>6} {cls['moved']:>6} {cls['rotated']:>5} "
              f"{cls['near']:>5} {maxd:>7.2f} {maxdeg:>7.2f} {nflag:>6} "
              f"{cls['naive_only']:>7} {cls['occt_only']:>7}"
              f"  {pct:>5.1f}%   [{n}/{len(parts)}]")
        rows.append({"part": part, **cls, "max_px": maxd, "max_deg": maxdeg,
                     "flag_flips": nflag, "laundered_pct": pct, "paths": tot})
    if a.out:
        a.out.write_text(json.dumps({"args": args, "parts": rows}, indent=2))
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
