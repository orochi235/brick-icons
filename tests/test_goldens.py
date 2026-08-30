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
KNOWN_STRAY = {
    # A 83.79 x 51.31 ellipse in 5 stroke-only paths, larger than the ~134-unit
    # part itself, pushing bbox y-min to -11.08 against a "0 0 256 170" box.
    # Analytic rim candidates in hlr._visible_segments_analytic — the same class
    # as 14769px2's stray arc and the NOTE there, not a new one.
    #
    # Both combos carry the same defect from the same code, so they retire
    # together: drop one alone and the other silently stops being watched.
    "outline-flat3__4019",
    "outline__4019",
}


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

