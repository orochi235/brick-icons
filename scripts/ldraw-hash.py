#!/usr/bin/env python3
"""Hash what each part is built from, so two library snapshots can be diffed.

    .venv/bin/python scripts/ldraw-hash.py --out out/ldraw/old.jsonl
    .venv/bin/python scripts/ldraw-hash.py --diff out/ldraw/old.jsonl new.jsonl

One line per part: a hash over its own drawing lines and those of every
subfile it resolves to, how many files that closure holds, and any reference
that resolves nowhere.

A part is not its `.dat`. The 2026-06 update moved 50950 by subfiling it with
corrected curvature, and a hash of the named file alone calls that unchanged.
Nor is a part its bytes: an LDraw update rewrites headers across thousands of
files, so only what `hlr.flatten` reads is hashed -- type 1-5 lines and the
type-0 `BFC` declarations -- and a header sweep costs nothing.

The alternative to this is re-rendering 24,591 parts to find out which moved,
which is `render-hash.py` and a fleet job. Take the manifest BEFORE the swap:
`complete.zip` only ever serves the latest snapshot, so a tree overwritten in
place cannot be hashed afterwards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons.hlr import default_roots, resolve  # noqa: E402

#: `hlr.flatten`'s own cap.
MAX_DEPTH = 30


def drawing_lines(text: str) -> list[str]:
    """The lines the renderer acts on, whitespace-collapsed.

    Type-0 is comment and metadata except for `BFC`, which sets the winding
    the repair pass reads; everything else on that line is a header an update
    is free to rewrite.
    """
    out = []
    for raw in text.splitlines():
        tok = raw.split()
        if not tok:
            continue
        if tok[0] == "0":
            if len(tok) > 1 and tok[1] == "BFC":
                out.append(" ".join(tok))
        elif tok[0] in ("1", "2", "3", "4", "5"):
            out.append(" ".join(tok))
    return out


def closure(path: Path, roots: list[Path], ldraw_dir: Path,
            cache: dict[Path, tuple[str, list[str]]]):
    """(files, unresolved) for one part: every `.dat` its references reach.

    Files are keyed by their path under the library, so a subfile promoted out
    of `Unofficial/` moves the parts that reach it even with identical bytes.
    """
    files: dict[str, str] = {}
    unresolved: set[str] = set()
    stack = [(path, 0)]
    while stack:
        cur, depth = stack.pop()
        key = str(cur.resolve().relative_to(ldraw_dir.resolve()))
        if key in files or depth > MAX_DEPTH:
            continue
        if cur not in cache:
            text = cur.read_text(errors="replace")
            lines = drawing_lines(text)
            body = "\n".join(lines)
            cache[cur] = (hashlib.sha256(body.encode()).hexdigest(), lines)
        sha, lines = cache[cur]
        files[key] = sha
        for ln in lines:
            tok = ln.split()
            if tok[0] != "1" or len(tok) < 15:
                continue
            ref = " ".join(tok[14:])
            sub = resolve(ref, roots)
            if sub is None:
                unresolved.add(ref)
            else:
                stack.append((sub, depth + 1))
    return files, sorted(unresolved)


def build(ldraw_dir: Path | str, ids: list[str] | None = None,
          progress=lambda msg: None) -> dict[str, dict]:
    """`{part_id: {sha, files, unresolved}}` for every part in the library."""
    ldraw_dir = Path(ldraw_dir)
    roots = default_roots(ldraw_dir)
    paths = sorted((ldraw_dir / "parts").glob("*.dat"))
    if ids is not None:
        want = set(ids)
        paths = [p for p in paths if p.stem in want]
    cache: dict[Path, tuple[str, list[str]]] = {}
    out = {}
    total = len(paths)
    for n, path in enumerate(paths, 1):
        files, unresolved = closure(path, roots, ldraw_dir, cache)
        digest = hashlib.sha256()
        for key in sorted(files):
            digest.update(f"{key}\0{files[key]}\0".encode())
        out[path.stem] = {"sha": digest.hexdigest(), "files": len(files),
                          "unresolved": unresolved}
        progress(f"{n}/{total} {path.stem}: {len(files)} files"
                 + (f", UNRESOLVED {' '.join(unresolved)}" if unresolved else ""))
    return out


def diff(old: dict[str, dict], new: dict[str, dict]) -> dict[str, list[str]]:
    """What a swap did: parts gained, parts lost, parts whose geometry moved."""
    return {
        "added": sorted(set(new) - set(old)),
        "dropped": sorted(set(old) - set(new)),
        "moved": sorted(p for p in set(old) & set(new)
                        if old[p]["sha"] != new[p]["sha"]),
    }


def read_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["part"]] = row
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ldraw-dir", default="vendor/ldraw", type=Path)
    ap.add_argument("--out", type=Path, help="write the manifest here")
    ap.add_argument("--diff", nargs=2, metavar=("OLD", "NEW"), type=Path)
    ap.add_argument("--only", nargs="*", help="hash these part ids only")
    a = ap.parse_args(argv)

    if a.diff:
        d = diff(read_jsonl(a.diff[0]), read_jsonl(a.diff[1]))
        for kind in ("added", "dropped", "moved"):
            print(f"{kind}: {len(d[kind])}")
            for pid in d[kind]:
                print(f"  {pid}")
        return 0

    rows = build(a.ldraw_dir, a.only, progress=lambda m: print(m, flush=True))
    stray = {p: r["unresolved"] for p, r in rows.items() if r["unresolved"]}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with a.out.open("w") as fh:
            for pid in sorted(rows):
                fh.write(json.dumps({"part": pid, **rows[pid]}) + "\n")
        print(f"\n{len(rows)} parts -> {a.out}")
    print(f"{len(stray)} parts reference a file the library cannot resolve")
    for pid, refs in sorted(stray.items()):
        print(f"  {pid}: {' '.join(refs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
