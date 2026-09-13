"""A/B the decal sheet of every printed part that places a sub-part in a color.

A sub-part placed in a color (76382p0u's arms in 71) is a moulded component,
and hlr._component_body makes its color body rather than print. This draws
each affected part twice in one process -- armed, then with the helper
disarmed so every placed color is print again -- and reports what moved:
panel counts, and whether the sheet came off the mesh fallback.

    .venv/bin/python scripts/component-body-ab.py [--limit N] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import hlr, unwrap  # noqa: E402

LDRAW = ROOT / "vendor" / "ldraw"


def affected() -> list[str]:
    parts = LDRAW / "parts"
    names = {p.name.lower() for p in parts.glob("*.dat")}
    out = []
    for p in sorted(parts.glob("*.dat")):
        lines = p.read_text(errors="replace").splitlines()
        d = lines[0].lower() if lines else ""
        if not ("pattern" in d or "sticker" in d) or "~moved" in d:
            continue
        for ln in lines:
            t = ln.split()
            if (len(t) >= 15 and t[0] == "1" and t[1] not in ("16", "24")
                    and " ".join(t[14:]).replace("\\", "/").lower() in names):
                out.append(p.stem)
                break
    return out


def sheet(part):
    tri, cols, analytic = hlr.part_geometry(part, LDRAW)
    # decal_panels' own two steps, so decal_groups runs once and the sheet
    # still says which path drew it
    groups = unwrap.significant_groups(unwrap.decal_groups(tri, cols, analytic))
    mesh = not groups
    if mesh:
        groups = unwrap.significant_groups(unwrap.mesh_groups(tri, cols),
                                           cap=None, shatter=False)
    panels = [g for g in groups
              if any(len(r) for _c, reg in g[2:3] for _k, gg in reg
                     for r in unwrap._rings_of(gg))]
    return {"panels": len(panels), "mesh": bool(panels) and mesh}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--list", type=Path,
                    help="part ids, one per line, instead of every affected part")
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "component-body-ab")
    args = ap.parse_args()
    parts = ([ln.strip() for ln in args.list.read_text().splitlines() if ln.strip()]
             if args.list else affected())[:args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    armed_fn = hlr._component_body
    rows = []
    for i, part in enumerate(parts, 1):
        row = {"part": part}
        for label, fn in (("before", lambda *_a: None), ("after", armed_fn)):
            hlr._component_body = fn
            hlr._text_cache.clear()
            try:
                s = sheet(part)
            except Exception as e:          # noqa: BLE001 -- report and go on
                s = {"panels": None, "mesh": None, "svg": None,
                     "error": f"{type(e).__name__}: {e}"}
            finally:
                hlr._component_body = armed_fn
            s.pop("svg", None)
            row[label] = s
        row["same"] = row["before"] == row["after"]
        rows.append(row)
        b, a = row["before"], row["after"]
        print(f"[{i}/{len(parts)}] {part}: panels {b['panels']}"
              f"{' mesh' if b['mesh'] else ''} -> {a['panels']}"
              f"{' mesh' if a['mesh'] else ''}", flush=True)
    (args.out / "rows.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    moved = [r for r in rows if not r["same"]]
    print(f"{len(moved)}/{len(rows)} changed; "
          f"off mesh fallback: {sum(1 for r in rows if r['before']['mesh'] and not r['after']['mesh'])}; "
          f"onto mesh fallback: {sum(1 for r in rows if r['after']['mesh'] and not r['before']['mesh'])}; "
          f"lost every panel: {sum(1 for r in rows if (r['before']['panels'] or 0) and not r['after']['panels'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
