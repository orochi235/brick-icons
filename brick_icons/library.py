from __future__ import annotations

import json
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ALLOWED_CATEGORIES = {
    "Brick", "Plate", "Tile", "Slope", "Technic", "Wedge", "Panel",
    "Cylinder", "Cone", "Dish", "Bar", "Bracket", "Hinge", "Wing", "Baseplate",
}
EXCLUDE_TITLE_SUBSTR = ("Sticker", "Pattern", "Moved")
_ORG = re.compile(r"!LDRAW_ORG\s+(\w+)")


@dataclass(frozen=True)
class PartInfo:
    title: str
    category: str
    org: str


def parse_header(lines) -> PartInfo:
    title = ""
    org = ""
    for ln in lines:
        s = ln.rstrip("\n")
        if not title and s.startswith("0 ") and "!LDRAW_ORG" not in s and "Name:" not in s:
            title = s[2:].strip()
        m = _ORG.search(s)
        if m and not org:
            org = m.group(1)
        if title and org:
            break
    stripped = title.lstrip("~_ ")
    category = stripped.split()[0] if stripped else ""
    return PartInfo(title=title, category=category, org=org)


def _read_header_lines(path: Path, n=12):
    out = []
    with open(path, "r", errors="replace") as fh:
        for _ in range(n):
            ln = fh.readline()
            if not ln:
                break
            out.append(ln)
    return out


def select_parts(ldraw_dir, limit=None, category=None):
    """Sorted list of part ids (no .dat) that pass the sortable filter."""
    parts_dir = Path(ldraw_dir) / "parts"
    ids = []
    for dat in sorted(parts_dir.glob("*.dat")):
        info = parse_header(_read_header_lines(dat))
        if not is_sortable(info):
            continue
        if category and info.category != category:
            continue
        ids.append(dat.stem)
        if limit and len(ids) >= limit:
            break
    return ids


def is_sortable(info: PartInfo) -> bool:
    if info.org != "Part":
        return False
    if info.title[:1] in ("~", "_"):
        return False
    if any(sub in info.title for sub in EXCLUDE_TITLE_SUBSTR):
        return False
    return info.category in ALLOWED_CATEGORIES


def _render_one(args):
    part, out_dir, ldraw_dir, shade_style, light, force = args
    import re as _re
    info = parse_header(_read_header_lines(Path(ldraw_dir) / "parts" / f"{part}.dat"))
    cat_dir = Path(out_dir) / info.category
    svg = cat_dir / f"{part}.svg"
    rec = {"id": part, "title": info.title, "category": info.category,
           "width_mm": 0.0, "height_mm": 0.0, "status": "ok"}

    def _measure(txt):
        m = _re.search(r'width="([\d.]+)mm" height="([\d.]+)mm"', txt)
        if m:
            rec["width_mm"], rec["height_mm"] = float(m.group(1)), float(m.group(2))

    if svg.exists() and not force:
        _measure(svg.read_text())
        return rec
    try:
        from .config import load_config
        from . import cli as _cli
        cfg = load_config(toml_path=None, root=".", overrides={
            "fmt": "svg", "shading": "outline", "scale_mode": "physical",
            "shade_style": shade_style, "light": light,
            "ldraw_dir": ldraw_dir})
        _cli.process_one(cfg, part, cat_dir)
        if not svg.exists():
            rec["status"] = "skipped-empty"
        else:
            _measure(svg.read_text())
    except Exception as e:                       # noqa: BLE001 — batch must not abort
        rec["status"] = f"error:{type(e).__name__}:{e}"
    return rec


def render_library(out_dir, ldraw_dir="vendor/ldraw", limit=None, category=None,
                   workers=4, shade_style="flat3", light=None, force=False):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ids = select_parts(ldraw_dir, limit=limit, category=category)
    tasks = [(p, out_dir, ldraw_dir, shade_style, light, force) for p in ids]
    if workers <= 1:
        records = [_render_one(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            records = list(ex.map(_render_one, tasks))
    (Path(out_dir) / "manifest.json").write_text(json.dumps(records, indent=2))
    return records


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="brick-icons-library")
    p.add_argument("--out", default="out/library")
    p.add_argument("--ldraw-dir", default="vendor/ldraw")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--category", default=None)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--shade-style", default="flat3",
                   choices=["none", "flat3", "cel", "gradient"])
    p.add_argument("--light", default=None, metavar="LAT,LONG")
    p.add_argument("--force", action="store_true")
    a = p.parse_args(argv)
    recs = render_library(a.out, a.ldraw_dir, a.limit, a.category, a.workers,
                          a.shade_style, a.light, a.force)
    ok = sum(1 for r in recs if r["status"] == "ok")
    print(f"library: {ok}/{len(recs)} ok -> {a.out}/manifest.json")


if __name__ == "__main__":
    main()
