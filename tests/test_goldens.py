"""The structural summary is what survives the engine swap.

A golden SVG hash catches the naive engine drifting, but an OCCT render can
never match one: the kernel emits `Geom_Circle` edges where the naive engine
emits a polyline refitted onto a guessed arc. So the summary counts arcs and
lines separately — a swap that is working shows `A` rising and `L` falling on
the round parts while the fill palette and bbox hold still.
"""
import pytest

from brick_icons import goldens


ONE_PATH = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 170">'
    '<g stroke-linejoin="round">'
    '<path d="M 10 20 L 30 40 L 10 40 Z" fill="#5e5e5e"/>'
    '</g></svg>'
)


def test_counts_paths_and_commands():
    s = goldens.summarize_svg(ONE_PATH)
    assert s["paths"] == 1
    assert s["commands"] == {"M": 1, "L": 2, "Z": 1}


def test_records_viewbox_and_fill_palette():
    s = goldens.summarize_svg(ONE_PATH)
    assert s["viewBox"] == "0 0 256 170"
    assert s["fills"] == {"#5e5e5e": 1}


def test_bbox_spans_the_drawn_coordinates():
    s = goldens.summarize_svg(ONE_PATH)
    assert s["bbox"] == pytest.approx([10.0, 20.0, 30.0, 40.0])


def test_arc_radii_and_flags_are_not_coordinates():
    """`A rx ry rot large sweep x y` — only the trailing pair is a point.

    Treating every number in the run as a coordinate pulls the bbox out to the
    radius and the rotation angle, so a part whose arcs are large reports a
    box bigger than its own viewBox and every engine comparison drifts.
    """
    svg = ('<svg viewBox="0 0 100 100">'
           '<path d="M 50 50 A 900 900 180.0 0 1 60 50 Z" fill="#000000"/>'
           '</svg>')
    s = goldens.summarize_svg(svg)
    assert s["commands"]["A"] == 1
    assert s["bbox"] == pytest.approx([50.0, 50.0, 60.0, 50.0])


def test_gradient_fills_collapse_to_one_token_and_stops_are_counted():
    """`url(#g3)` ids are allocation order, not content.

    Two runs that differ only in how many gradients came first would report
    different palettes for identical drawings. The stop count is kept because
    it is the uncapped-stops bug's only visible symptom.
    """
    svg = ('<svg viewBox="0 0 10 10"><defs>'
           '<linearGradient id="g3">'
           '<stop offset="0.0%" stop-color="#999999"/>'
           '<stop offset="100.0%" stop-color="#565656"/>'
           '</linearGradient></defs>'
           '<path d="M 0 0 L 1 1" fill="url(#g3)"/></svg>')
    s = goldens.summarize_svg(svg)
    assert s["fills"] == {"gradient": 1}
    assert s["gradients"] == 1
    assert s["gradient_stops"] == 2


def test_counts_lines_and_unfilled_paths():
    svg = ('<svg viewBox="0 0 10 10">'
           '<line x1="1" y1="2" x2="3" y2="4" stroke="#333"/>'
           '<path d="M 0 0 L 5 5" fill="none"/></svg>')
    s = goldens.summarize_svg(svg)
    assert s["lines"] == 1
    assert s["fills"] == {"none": 1}
    assert s["bbox"] == pytest.approx([0.0, 0.0, 5.0, 5.0])


def test_clip_paths_are_not_drawn_geometry():
    """The silhouette clip is a mask, not ink.

    Counting it inflates the path total by one on every part and lets a
    clip that outruns the drawing widen the reported bbox.
    """
    svg = ('<svg viewBox="0 0 10 10">'
           '<clipPath id="sclip"><path d="M -99 -99 L 99 99"/></clipPath>'
           '<path d="M 1 1 L 2 2" fill="#000000"/></svg>')
    s = goldens.summarize_svg(svg)
    assert s["paths"] == 1
    assert s["bbox"] == pytest.approx([1.0, 1.0, 2.0, 2.0])


def test_fill_is_inherited_from_the_enclosing_group():
    """This renderer paints fills and strokes in two groups, and the stroke
    group carries `fill="none"` once on the `<g>` rather than on each path.
    Reading fills off path attributes alone attributes nothing to any of
    them, so the palette silently describes only half the drawing."""
    svg = ('<svg viewBox="0 0 10 10">'
           '<g stroke-linejoin="round">'
           '<path d="M 0 0 L 1 1" fill="#cccccc"/></g>'
           '<g stroke="black" fill="none">'
           '<path d="M 2 2 L 3 3"/><path d="M 3 3 L 4 4"/></g></svg>')
    s = goldens.summarize_svg(svg)
    assert s["fills"] == {"#cccccc": 1, "none": 2}


def test_empty_drawing_has_no_bbox():
    s = goldens.summarize_svg('<svg viewBox="0 0 10 10"></svg>')
    assert s["paths"] == 0
    assert s["bbox"] is None


def test_a_transform_suppresses_the_bbox_rather_than_reporting_a_wrong_one():
    """Path coordinates under a `transform` are in the transformed space, so
    reading them raw gives a box unrelated to the drawing — potrace output puts
    them off by an order of magnitude. A summary that cannot state the extent
    must say so, not report a number nobody will re-check."""
    svg = ('<svg viewBox="0 0 10 10">'
           '<g transform="scale(0.001) translate(-4372 -11523)">'
           '<path d="M 0 0 L 20000 20000" fill="#000000"/></g></svg>')
    s = goldens.summarize_svg(svg)
    assert s["transforms"] == 1
    assert s["bbox"] is None


# --- drift gate -------------------------------------------------------------
#
# Opt-in: these shell out to LDView and cost minutes, so they stay out of the
# default suite. `BRICK_GOLDENS=1` runs a fast subset; `BRICK_GOLDENS=full`
# runs every case in the manifest.
#
# This gate holds the NAIVE engine still. A different engine misses every hash
# by construction — compare that one with scripts/compare-goldens.py.

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDENS = ROOT / "tests" / "goldens"
MODE = os.environ.get("BRICK_GOLDENS")

drift = pytest.mark.skipif(
    not MODE, reason="set BRICK_GOLDENS=1 (subset) or =full")


def _frozen_hashes() -> dict[str, str]:
    path = GOLDENS / "hashes.txt"
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        sha, _, cid = line.partition("  ")
        if cid:
            out[cid.strip()] = sha
    return out


@drift
def test_frozen_hashes_still_reproduce(tmp_path):
    frozen = _frozen_hashes()
    assert frozen, "no goldens: run scripts/freeze-goldens.py"
    cmd = [sys.executable, str(ROOT / "scripts" / "freeze-goldens.py"),
           "--out", str(tmp_path)]
    if MODE != "full":
        cmd += ["--only", "3005"]
    subprocess.run(cmd, check=True, cwd=ROOT)

    fresh = {}
    for line in (tmp_path / "hashes.txt").read_text().splitlines():
        sha, _, cid = line.partition("  ")
        fresh[cid.strip()] = sha

    drifted = {cid: (frozen.get(cid), sha) for cid, sha in fresh.items()
               if frozen.get(cid) != sha}
    assert not drifted, (
        "the naive engine moved on: " + ", ".join(sorted(drifted)))


@drift
def test_every_frozen_case_has_a_summary():
    """A hash with no summary is a golden that cannot be compared across
    engines, which is the only job the corpus exists to do."""
    missing = [cid for cid in _frozen_hashes()
               if not (GOLDENS / "render" / f"{cid}.json").exists()]
    assert not missing, missing


# Cases whose frozen output is known to violate a structural invariant. These
# are goldens too: the swap is expected to fix them, and a silent pass needs
# the note updated rather than absorbing quietly.
# 4019's stray ellipse (both combos) retired here: it was NOT an analytic rim
# candidate as recorded, but _snap_rim_crossings' counterbore separator refit
# re-emitting a 7.2-degree arc as its 310.8-degree complement. Guarded by
# hlr.SEP_REFIT_MAX_GROWTH.
KNOWN_STRAY: set[str] = set()


@drift
def test_drawings_stay_inside_their_own_viewbox():
    """A path outside the viewBox is ink the renderer computed and then clipped
    away — invisible in the picture, and a defect either way. This needs no
    baseline to compare against, which is why it catches things the raster diff
    cannot: it found 4019's stray ellipse numerically before anyone looked."""
    strays = []
    for path in sorted((GOLDENS / "render").glob("*.json")):
        summary = json.loads(path.read_text())
        vb, bb = summary.get("viewBox"), summary.get("bbox")
        if not vb or not bb:
            continue
        x, y, w, h = (float(v) for v in vb.split())
        if (bb[0] < x - 0.01 or bb[1] < y - 0.01
                or bb[2] > x + w + 0.01 or bb[3] > y + h + 0.01):
            strays.append((path.stem, vb, [round(v, 2) for v in bb]))

    unexpected = [s for s in strays if s[0] not in KNOWN_STRAY]
    assert not unexpected, f"new stray geometry: {unexpected}"

    fixed = KNOWN_STRAY - {s[0] for s in strays}
    assert not fixed, (
        f"{sorted(fixed)} no longer draws outside its viewBox — drop it from "
        f"KNOWN_STRAY and say what fixed it")


# --- extraction seam --------------------------------------------------------
#
# The render gate above locks `hashes.txt`. This one locks the other half of
# the corpus, `decal-hashes.txt`, which was frozen by `freeze-goldens.py
# --seam extraction` and read by no test at all: the MAX_DECALS cap silenced
# 19 parts and the suite stayed green.


def _frozen_decals() -> dict[str, tuple[str, int]]:
    path = GOLDENS / "decal-hashes.txt"
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) == 3:
            out[fields[1]] = (fields[0], int(fields[2]))
    return out


def _corpus_parts() -> list[str]:
    text = (GOLDENS / "decal-corpus.txt").read_text()
    return [s for ln in text.splitlines() if (s := ln.split("#")[0].strip())]


def _decal_subset(frozen: dict[str, tuple[str, int]], per_class: int = 3):
    """Sample every decal-COUNT class, not the alphabet.

    The count is what the sliver ratio, the shatter share and MAX_DECALS all
    move, and the classes are lopsided — 310 parts yield one decal, 20 yield
    none. A stride sample over 393 sorted ids would miss both edges, which is
    where the cap does its silencing.
    """
    by_count: dict[int, list[str]] = {}
    for part, (_, n) in sorted(frozen.items()):
        by_count.setdefault(n, []).append(part)
    picked = [p for n in sorted(by_count) for p in by_count[n][:per_class]]
    return sorted(picked)


def test_every_corpus_part_has_a_frozen_decal_hash():
    """Cheap enough to run unconditionally: it opens no LDraw file. A part in
    the corpus with no row is one a partial re-freeze dropped, and nothing
    downstream would notice it had stopped being watched."""
    frozen = _frozen_decals()
    assert frozen, "no decal goldens: freeze-goldens.py --seam extraction"
    missing = [p for p in _corpus_parts() if p not in frozen]
    assert not missing, f"corpus parts with no frozen hash: {missing}"


@drift
def test_frozen_decal_hashes_still_reproduce(tmp_path):
    """The extraction seam's drift lock, mirroring the render seam's.

    `BRICK_GOLDENS=1` re-extracts one part per decal-count class; `=full` does
    the whole 393-part corpus, which costs about six minutes.
    """
    frozen = _frozen_decals()
    assert frozen, "no decal goldens: freeze-goldens.py --seam extraction"

    cmd = [sys.executable, str(ROOT / "scripts" / "freeze-goldens.py"),
           "--seam", "extraction", "--out", str(tmp_path)]
    subset = None
    if MODE != "full":
        subset = _decal_subset(frozen)
        cmd += ["--only", ",".join(subset)]
    subprocess.run(cmd, check=True, cwd=ROOT)

    fresh = {}
    for line in (tmp_path / "decal-hashes.txt").read_text().splitlines():
        fields = line.split()
        if len(fields) == 3:
            fresh[fields[1]] = (fields[0], int(fields[2]))

    assert set(fresh) == set(subset or frozen), (
        "the run did not cover the parts asked for")
    drifted = {p: (frozen.get(p), got) for p, got in fresh.items()
               if frozen.get(p) != got}
    assert not drifted, (
        "extraction moved on: " + ", ".join(sorted(drifted)))


def test_outline_combo_is_strokes_only():
    """The HLR gate must not also test the fill path.

    A fill entering these cases would make an engine swap answerable for
    shading too, which is a separate track (Skia PathOps, evaluated
    elsewhere).
    """
    files = list((GOLDENS / "render").glob("outline__*.json"))
    assert files, "No outline golden cases found; corpus missing or mislocated"
    for p in files:
        fills = json.loads(p.read_text())["fills"]
        assert set(fills) <= {"none"}, f"{p.name} has fills: {fills}"

