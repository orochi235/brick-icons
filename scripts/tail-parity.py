"""Does the stylization tail give both engines the same fields, per part?

    .venv/bin/python scripts/tail-parity.py [part ...]

One row per part, naive beside occt: drawn ops, counterbore refits, fold
ellipses (arcfit's fitted rounds, protected from the orphan cull), fold
loops (closed chains of those, cut into the fills), and how many of the
part's fitted arcs the engine drew. The counts need not agree -- the engines
see different occlusion -- but a zero on one side against a count on the
other is a step one engine is not running.
"""
import sys
from brick_icons import hlr
LIB = "vendor/ldraw"

parts = sys.argv[1:] or ["3700", "3941", "32527", "30162", "4032a", "2654a",
                         "6589", "3001"]
cols = ("ops", "refit", "fold", "loop", "drawn")
head = " ".join(f"{c:>6}" for c in cols)
print(f"{'part':8} naive: {head}   occt: {head}")


def row(res):
    keys = set(res.fold_ells or ())
    drawn = sum(1 for op in res.segs if op[0] == "arc"
                and tuple(round(v, 6) for v in op[1:7]) in keys)
    vals = (len(res.segs), len(res.refits), len(keys), len(res.loops), drawn)
    return " ".join(f"{v:6d}" for v in vals)


for i, part in enumerate(parts, 1):
    nv = hlr.visible_segments(part, LIB, engine="naive")
    oc = hlr.visible_segments(part, LIB, engine="occt")
    print(f"{part:8}        {row(nv)}         {row(oc)}   [{i}/{len(parts)}]",
          flush=True)
