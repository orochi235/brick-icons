#!/usr/bin/env python3
"""Count each part's declared-smooth facet regions, and how many of them a
quadric fits -- the number that decides whether freeform smooth shading is
worth building.

    .venv/bin/python scripts/count-smooth-regions.py --out out/smooth-regions 3001 51283
    .venv/bin/python scripts/count-smooth-regions.py --list      # every part id, one per line
    .venv/bin/python scripts/count-smooth-regions.py --report out/smooth-regions

Geometry only: each part is flattened, swept and repaired the way the
engines see it, its regions found by quadric.regions_of (triangles joined
across conditional lines, `quadric.MIN_FACETS` or more) and each classified
by quadric.classify under the same residual gates the renderer uses. One TSV
per invocation, named for its first part, one row per part:

    part  category  printed  n_quadric  n_freeform  tris_quadric  tris_freeform  kinds  secs  error

`--report` reads every TSV under a directory and prints the totals.
"""
from __future__ import annotations

import argparse
import collections
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from brick_icons import quadric  # noqa: E402

LDRAW = ROOT / "vendor" / "ldraw"
COLUMNS = ("part", "category", "printed", "n_quadric", "n_freeform",
           "tris_quadric", "tris_freeform", "kinds", "secs", "error")
PART_TIMEOUT = 120


def header(part):
    """(category, printed): the file's !CATEGORY, else its description's
    first word; printed from Pattern/Sticker in the description."""
    path = LDRAW / "parts" / f"{part}.dat"
    desc, cat = "", ""
    with open(path, errors="replace") as fh:
        for i, ln in enumerate(fh):
            s = ln.strip()
            if i == 0:
                desc = s[2:].strip() if s.startswith("0 ") else s
            if s.startswith("0 !CATEGORY"):
                cat = s[len("0 !CATEGORY"):].strip()
                break
            if s[:1] in ("1", "2", "3", "4", "5"):
                break
    if not cat:
        cat = desc.lstrip("~_=|").split()[0] if desc.lstrip("~_=|").split() else ""
    printed = "pattern" in desc.lower() or "sticker" in desc.lower()
    return cat, printed


def in_scope(path):
    """The parts the corpus draws: not a subfile alias (~), not a moved or
    obsolete stub (_ / Moved), not an alias of another part (=)."""
    with open(path, errors="replace") as fh:
        desc = fh.readline()[2:].strip()
    return not (desc[:1] in "~_=" or desc.startswith("Moved") or not desc)


def count(part):
    out = quadric.load(part, LDRAW)
    tris = np.asarray(out["tri"], float).reshape(-1, 3, 3)
    q = f = tq = tf = 0
    kinds = collections.Counter()
    for ids in quadric.regions_of(tris, out["tri_colors"], out["5"]):
        T = tris[ids]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        fit = quadric.classify(list(T), list(n))
        if fit is None:
            f += 1
            tf += len(ids)
        else:
            q += 1
            tq += len(ids)
            kinds[fit.kind] += 1
    return q, f, tq, tf, ",".join(f"{k}:{v}" for k, v in sorted(kinds.items()))


class _Timeout(Exception):
    pass


def _alarm(*_a):
    raise _Timeout()


def run(parts, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{parts[0]}.tsv"
    done = set()
    if dest.exists():
        done = {ln.split("\t", 1)[0] for ln in dest.read_text().splitlines()[1:]}
    signal.signal(signal.SIGALRM, _alarm)
    with open(dest, "a") as fh:
        if not done:
            fh.write("\t".join(COLUMNS) + "\n")
        todo = [p for p in parts if p not in done]
        print(f"onto: plan 0/{len(todo)}", flush=True)
        for i, part in enumerate(todo, 1):
            t0 = time.monotonic()
            cat, printed = "", False
            row, err = ("", "", "", "", ""), ""
            signal.alarm(PART_TIMEOUT)
            try:
                cat, printed = header(part)
                row = count(part)
            except _Timeout:
                err = "timeout"
            except Exception as e:           # noqa: BLE001 -- a row per part
                err = f"{type(e).__name__}: {e}"[:200].replace("\t", " ").replace("\n", " ")
            finally:
                signal.alarm(0)
            secs = time.monotonic() - t0
            fh.write("\t".join(map(str, (part, cat, int(printed), *row,
                                         f"{secs:.2f}", err))) + "\n")
            fh.flush()
            print(f"{i}/{len(todo)} {part} q={row[0]} f={row[1]} {secs:.2f}s {err}",
                  flush=True)
            print(f"onto: progress {i}/{len(todo)}", flush=True)


def report(out_dir, top=20):
    rows = []
    for p in sorted(Path(out_dir).rglob("*.tsv")):
        lines = p.read_text().splitlines()
        for ln in lines[1:]:
            c = dict(zip(COLUMNS, ln.split("\t")))
            rows.append(c)
    ok = [r for r in rows if not r.get("error") and r.get("n_quadric") != ""]
    err = len(rows) - len(ok)

    def ints(r):
        return {k: int(r[k]) for k in ("n_quadric", "n_freeform",
                                        "tris_quadric", "tris_freeform")}
    for r in ok:
        r.update(ints(r))
    for label, sel in (("all parts", ok),
                       ("unprinted", [r for r in ok if r["printed"] == "0"])):
        fp = [r for r in sel if r["n_freeform"]]
        qp = [r for r in sel if r["n_quadric"]]
        print(f"== {label}: {len(sel)} parts counted")
        print(f"   parts with a freeform region  {len(fp):6d}"
              f"   regions {sum(r['n_freeform'] for r in sel):6d}"
              f"   tris {sum(r['tris_freeform'] for r in sel):8d}")
        print(f"   parts with a quadric region   {len(qp):6d}"
              f"   regions {sum(r['n_quadric'] for r in sel):6d}"
              f"   tris {sum(r['tris_quadric'] for r in sel):8d}")
    kinds = collections.Counter()
    for r in ok:
        for kv in filter(None, r["kinds"].split(",")):
            k, v = kv.split(":")
            kinds[k] += int(v)
    print("   quadric regions by kind:", dict(kinds))
    print(f"   errored/timed out: {err}")
    sel = [r for r in ok if r["printed"] == "0"]
    by = collections.Counter(r["category"] for r in sel if r["n_freeform"])
    tot = collections.Counter(r["category"] for r in sel)
    print("\n== unprinted parts with a freeform region, by category")
    print(f"{'category':32s} {'parts':>6s} {'of':>6s}")
    for c, n in by.most_common():
        print(f"{c[:32]:32s} {n:6d} {tot[c]:6d}")
    print(f"\n== {top} largest freeform parts by freeform triangles (unprinted)")
    for r in sorted(sel, key=lambda r: -r["tris_freeform"])[:top]:
        print(f"{r['part']:14s} {r['category'][:28]:28s} "
              f"{r['tris_freeform']:7d} tris  {r['n_freeform']:4d} regions")
    return by, tot


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--out", default="out/smooth-regions")
    ap.add_argument("--list", action="store_true",
                    help="print every in-scope part id and exit")
    ap.add_argument("--report", help="summarize the TSVs under this directory")
    a = ap.parse_args()
    if a.list:
        for p in sorted((LDRAW / "parts").glob("*.dat")):
            if in_scope(p):
                print(p.stem)
        return 0
    if a.report:
        report(a.report)
        return 0
    if not a.parts:
        ap.error("no parts")
    # onto's --batch hands a batch over as ONE argument, joined by spaces
    parts = [p for arg in a.parts for p in arg.split()]
    run(parts, ROOT / a.out if not Path(a.out).is_absolute() else Path(a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
