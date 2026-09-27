#!/usr/bin/env python3
"""Gate 3 of vet-fix: which golden cases a fix moves, and whether it said so.

    .venv/bin/python scripts/vet-goldens.py --base origin/main --expect 6589,3941
    .venv/bin/python scripts/vet-goldens.py --here --only outline__30   # this Mac
    .venv/bin/python scripts/vet-goldens.py --parts batch.txt --source occt

Renders every case in tests/goldens/manifest.toml twice under one engine:
`before` from a throwaway worktree at --base, `after` from this tree as it
stands, uncommitted edits included. Each pair is component-counted with the
lab's own diff panel, so a count here means what it means on /review.

A case whose part is not in --expect and moved is UNEXPECTED; those are what
go to a person. `--parts` draws a part list instead of the goldens (a file of
`part[<TAB>label]` lines, or ids joined by commas) under a render slot's own
flags, for a change expected to move many parts; its sheet comes in pages,
each row labeled with its line's label. Without --here the run goes to the
fleet through `onto do`,
and the report and sheet come back under out/vet/<label>/.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from PIL import Image  # noqa: E402

from _sheet import sheet  # noqa: E402
from brick_icons.lab import diff as _diff  # noqa: E402

VET_DIR = ROOT / "out" / "vet"
KEEP_RUNS = 10
PAGE_ROWS = 20


def _freeze():
    spec = importlib.util.spec_from_file_location(
        "freeze_goldens", ROOT / "scripts" / "freeze-goldens.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def git(*args, cwd=ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_base_tree(rev: str, where: Path) -> Path:
    if where.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(where)],
                       cwd=ROOT, capture_output=True)
        shutil.rmtree(where, ignore_errors=True)
    git("worktree", "add", "--detach", str(where), rev)
    # The parts library is untracked, so a fresh worktree has none.
    (where / "vendor").symlink_to(ROOT / "vendor")
    return where


def render(case, tree: Path, engine: str, dest: Path, width: int,
           timeout: float | None = None):
    """(png or None, error or None, seconds). `-m` puts cwd first on sys.path,
    so running from `tree` is what makes it import that tree's engine."""
    t0 = time.time()
    work = dest / f".work-{case['id']}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    env = {**os.environ, "PYTHONPATH": str(tree)}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "brick_icons.cli", case["part"],
             "--engine", engine, *case["args"], "--out", str(work)],
            cwd=tree, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        shutil.rmtree(work, ignore_errors=True)
        return None, f"timeout {timeout:g}s", time.time() - t0
    svgs = sorted(work.glob("*.svg"))
    if proc.returncode != 0 or not svgs:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        shutil.rmtree(work, ignore_errors=True)
        return None, (tail[-1] if tail else f"exit {proc.returncode}"), time.time() - t0
    svg = dest / f"{case['id']}.svg"
    shutil.move(svgs[0], svg)
    shutil.rmtree(work, ignore_errors=True)
    png = dest / f"{case['id']}.png"
    r = subprocess.run(["resvg", "--width", str(width), str(svg), str(png)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, "resvg: " + (r.stderr.strip() or "failed"), time.time() - t0
    return png, None, time.time() - t0


def flat(png: Path) -> Image.Image:
    im = Image.open(png).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    return bg.convert("RGB")


def prune_runs(keep: int = KEEP_RUNS) -> None:
    runs = sorted((p for p in VET_DIR.iterdir() if p.is_dir()),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for old in runs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


def read_parts(spec: str) -> list[tuple[str, str]]:
    """(part, label) from a file of `part[<TAB>label]` lines, or from ids
    joined by commas."""
    path = Path(spec)
    if "," not in spec and path.is_file():
        rows = [ln.split("\t", 1) for ln in path.read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]
        return [(r[0].strip(), r[1].strip() if len(r) > 1 else "") for r in rows]
    return [(p, "") for p in spec.split(",") if p]


def part_cases(parts: list[tuple[str, str]], source: str):
    """One case per part, drawn with `source`'s own flags minus its engine
    (--engine decides that, as it does for the goldens)."""
    from brick_icons import db
    argv = db.canonical_argv("PART", source)[1:]
    keep = [x for i, x in enumerate(argv)
            if x != "--engine" and (i == 0 or argv[i - 1] != "--engine")]
    return [{"id": p, "part": p, "args": keep, "label": label}
            for p, label in parts]


def run_here(a) -> int:
    # provision-node.sh installs resvg and potrace here, off the agent's PATH.
    os.environ["PATH"] = f"{Path.home() / '.local' / 'bin'}:{os.environ['PATH']}"
    if a.parts:
        labels = json.loads(a.labels) if a.labels else {}
        parts = [(p, labels.get(p, lb)) for p, lb in read_parts(a.parts)]
        cases, width = part_cases(parts, a.source), 512
    else:
        freeze = _freeze()
        cases, width = freeze.load_cases(freeze.MANIFEST)
    if a.only:
        cases = [c for c in cases if a.only in c["id"]]
    if not shutil.which("resvg"):
        print("resvg not on PATH", file=sys.stderr)
        return 2
    expect = {p for p in (a.expect or "").split(",") if p}
    if a.parts and not a.expect:
        expect = {c["part"] for c in cases}   # a person reviews every page
    base_sha = git("rev-parse", "--short", a.base)
    out = VET_DIR / a.label
    shutil.rmtree(out, ignore_errors=True)
    (out / "before").mkdir(parents=True)
    (out / "after").mkdir(parents=True)
    dirty = git("status", "--porcelain", "--", "brick_icons")
    after_name = git("rev-parse", "--short", "HEAD") + ("+dirty" if dirty else "")
    print(f"{len(cases)} cases, engine {a.engine}, "
          f"before {a.base} ({base_sha}), after {after_name}", flush=True)
    if dirty:
        print("after includes uncommitted engine edits:\n" + dirty, flush=True)

    base_tree = make_base_tree(a.base, out / "base-tree")
    rows = []
    try:
        def one(case):
            b = render(case, base_tree, a.engine, out / "before", width,
                       a.timeout)
            f = render(case, ROOT, a.engine, out / "after", width, a.timeout)
            return case, b, f

        with ThreadPoolExecutor(a.workers) as ex:
            for i, (case, b, f) in enumerate(ex.map(one, cases), 1):
                row = {"case": case["id"], "part": case["part"],
                       "expected": case["part"] in expect}
                if b[1] or f[1]:
                    row.update(state="error", before_error=b[1], after_error=f[1])
                    if b[1] and f[1]:
                        row["state"] = "error-both"
                else:
                    _img, comps, px = _diff.panel(flat(b[0]), flat(f[0]))
                    row.update(comps=comps, px=px,
                               state="moved" if comps else "same")
                unexpected = row["state"] != "same" and not row["expected"] \
                    and row["state"] != "error-both"
                row["unexpected"] = unexpected
                rows.append(row)
                note = (f"{row.get('comps', 0):3d} comp {row.get('px', 0):7d} px"
                        if "comps" in row else
                        f"ERROR before={b[1]} after={f[1]}")
                flag = "  UNEXPECTED" if unexpected else ""
                print(f"{i:3d}/{len(cases)} {case['id']:28s} {note}"
                      f"  {b[2]:5.1f}s/{f[2]:5.1f}s{flag}", flush=True)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(base_tree)],
                       cwd=ROOT, capture_output=True)
        shutil.rmtree(base_tree, ignore_errors=True)

    moved = [r for r in rows if r["state"] == "moved"]
    if a.parts:
        label = {c["id"]: c["label"] for c in cases}
        order = {c["id"]: i for i, c in enumerate(cases)}
        moved.sort(key=lambda r: order[r["case"]])
        pages = [moved[i:i + PAGE_ROWS] for i in range(0, len(moved), PAGE_ROWS)]
        for n, page in enumerate(pages, 1):
            sheet(f"{a.source} under {a.engine}: {a.base} ({base_sha}) -> "
                  f"{after_name}   page {n}/{len(pages)}   magenta = changed",
                  [(r["case"] + "\n" + label[r["case"]].replace(", ", "\n"),
                    flat(out / "before" / f"{r['case']}.png"),
                    flat(out / "after" / f"{r['case']}.png")) for r in page],
                  out=out / f"sheet-{n:02d}.png")
    elif moved:
        moved.sort(key=lambda r: (not r["unexpected"], -r["px"]))
        sheet(f"goldens under {a.engine}: {a.base} ({base_sha}) -> {after_name}"
              f"   magenta = changed",
              [(("UNEXPECTED\n" if r["unexpected"] else "expected\n")
                + r["case"].replace("__", "\n"),
                flat(out / "before" / f"{r['case']}.png"),
                flat(out / "after" / f"{r['case']}.png")) for r in moved],
              out=out / "sheet.png")
    unexpected = [r for r in rows if r["unexpected"]]
    report = {"base": a.base, "base_sha": base_sha, "after": after_name,
              "engine": a.engine, "expect": sorted(expect),
              "verdict": "review" if unexpected else "pass", "cases": rows}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    for side in ("before", "after"):
        for svg in (out / side).glob("*.svg"):
            svg.unlink()

    missed = expect - {r["part"] for r in moved}
    print(f"\n{len(moved)} moved, {len(unexpected)} unexpected, "
          f"{sum(r['state'].startswith('error') for r in rows)} errored")
    for r in unexpected:
        print(f"  UNEXPECTED {r['case']}  {r.get('comps', '-')} comp")
    if missed:
        print(f"  expected to move but did not: {', '.join(sorted(missed))}")
    print(f"verdict: {report['verdict']}   {out.relative_to(ROOT)}/")
    prune_runs()
    return 0


def run_fleet(a) -> int:
    """Re-invoke this script with --here on a node; `onto do` syncs this
    checkout (dirty edits and all) and brings out/vet/<label> home."""
    cmd = [".venv/bin/python", "scripts/vet-goldens.py", "--here",
           "--base", a.base, "--engine", a.engine, "--label", a.label,
           "--workers", str(a.workers)]
    if a.parts:
        # the list and its labels travel on the command line: a file here
        # is not a file the node was sent
        parts = read_parts(a.parts)
        cmd += ["--parts", ",".join(p for p, _lb in parts),
                "--labels", json.dumps({p: lb for p, lb in parts if lb}),
                "--source", a.source]
    if a.timeout:
        cmd += ["--timeout", f"{a.timeout:g}"]
    if a.expect:
        cmd += ["--expect", a.expect]
    if a.only:
        cmd += ["--only", a.only]
    rel = f"out/vet/{a.label}"
    onto = ["onto", "do", "--kind", "score", "--icon", "chart.line.text.clipboard",
            "--task", f"vet-{a.label}", "--timeout", "6h" if a.parts else "1h",
            # a branch with no upstream has no merge-base for onto to sync
            # from; `before`'s revision is one the node can fetch
            "--ref", a.base,
            "--env", "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            "--out", rel, "--to", str(ROOT / rel)]
    if a.node:
        onto += ["--node", a.node]
    print(" ".join(onto + ["--", *cmd]), flush=True)
    rc = subprocess.run([*onto, "--", *cmd], cwd=ROOT).returncode
    report = ROOT / rel / "report.json"
    if report.exists():
        r = json.loads(report.read_text())
        print(f"verdict: {r['verdict']}   {rel}/")
        return 0
    # An agent upgrading mid-run drops `onto do` while the job carries on.
    print(f"no report yet; once `onto jobs` shows vet-{a.label} done:\n"
          f"  onto fetch <node>:brick-icons/{rel} {rel}", file=sys.stderr)
    return rc or 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="origin/main",
                    help="revision to draw `before` at (default origin/main)")
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--expect", help="comma-separated parts predicted to move")
    ap.add_argument("--only", help="substring filter on the case id")
    ap.add_argument("--label", help="run name under out/vet/ (default base..HEAD)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--here", action="store_true",
                    help="render in this tree instead of on the fleet")
    ap.add_argument("--node", help="fleet node to use (default: onto chooses)")
    ap.add_argument("--parts", help="draw this part list instead of the goldens")
    ap.add_argument("--labels", help=argparse.SUPPRESS)   # JSON, from run_fleet
    ap.add_argument("--source", default="occt",
                    help="render slot whose flags --parts draws with")
    ap.add_argument("--timeout", type=float,
                    help="give up on one render after this many seconds")
    a = ap.parse_args(argv)
    a.label = a.label or (f"{git('rev-parse', '--short', a.base)}"
                          f"..{git('rev-parse', '--short', 'HEAD')}-{a.engine}")
    return run_here(a) if a.here else run_fleet(a)


if __name__ == "__main__":
    raise SystemExit(main())
