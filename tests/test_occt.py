import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

occt = pytest.importorskip("brick_icons.occt", reason="needs the [occt] extra")

from brick_icons import hlr, goldens  # noqa: E402
from brick_icons.cli import process_one  # noqa: E402
from brick_icons.config import load_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _load_compare_goldens():
    """`scripts/compare-goldens.py` has a hyphen, so `import` can't name it."""
    spec = importlib.util.spec_from_file_location(
        "compare_goldens", ROOT / "scripts" / "compare-goldens.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


raster_delta = _load_compare_goldens().raster_delta


def _render_svg(part: str, engine: str, out: Path) -> Path | None:
    """Render `part` with `engine` via the real CLI, rasterize it with resvg,
    and return the PNG path -- or None if either step is unavailable."""
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "brick_icons.cli", part, "--engine", engine,
         "--format", "svg", "--shading", "outline", "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT)
    svgs = sorted(out.glob("*.svg"))
    if proc.returncode != 0 or not svgs:
        return None
    if not shutil.which("resvg"):
        return None
    png = out / "render.png"
    rproc = subprocess.run(
        ["resvg", "--background", "white", "--width", "512", str(svgs[0]), str(png)],
        capture_output=True, text=True)
    return png if rproc.returncode == 0 else None


def _mirrored(png: Path, mode=Image.FLIP_LEFT_RIGHT) -> Path:
    tag = "mirrored" if mode is Image.FLIP_LEFT_RIGHT else "flipped"
    out = png.with_name(f"{png.stem}-{tag}{png.suffix}")
    Image.open(png).transpose(mode).save(out)
    return out


class P:
    """Minimal stand-in for a recognized primitive."""
    def __init__(self, kind, R, t, sector=360.0, top=1, inner=1):
        self.kind, self.R, self.t = kind, R, t
        self.sector, self.top, self.inner = sector, top, inner


def test_sheared_frame_is_rejected():
    """Non-orthogonal frames have no exact OCCT counterpart (5% of parts)."""
    R = np.array([[1.0, 0.3, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert occt.frame(P("cyli", R, np.zeros(3))) is None


def test_cone_radii_are_n_plus_one_and_n_scaled():
    """conN is radius N+1 at the base tapering to N, BOTH in primitive units,
    so the matrix scale multiplies both. Using the scale directly as the outer
    radius builds a plausible-looking part at the wrong size."""
    prim = P("con", np.diag([2.0, 5.0, 2.0]), np.zeros(3), top=3)
    r_base, r_top = occt.cone_radii(prim)
    assert r_base == pytest.approx(8.0)   # (3 + 1) * 2
    assert r_top == pytest.approx(6.0)    # 3 * 2


def test_edge_primitives_contribute_no_surface():
    assert occt.occt_faces(P("edge", np.eye(3), np.zeros(3))) == []


def test_3001_builds_and_sews(ldraw_dir):
    """The spike's step 2: a real brick builds with no exceptions."""
    shape = occt.build_shape(occt.flatten_part("3001", ldraw_dir))
    assert occt.count_faces(shape) > 0


def test_projector_axis_puts_image_y_on_up():
    """OCCT derives image Y as Z x X. Feeding view_basis's `fwd` and `right`
    directly pitches the whole render 90 degrees.

    Asserted against -up, not up: cross(cross(right, up), right) == up holds
    for ANY orthonormal pair by the triple-product identity, regardless of
    which way Z points, so it is a tautology that can't catch a flipped Z.
    -up is hlr.project's actual screen-Y convention and is what pins the
    frame down.
    """
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    z, x = occt.projector_axes(right, up)
    assert np.allclose(np.cross(z, x), -up, atol=1e-9)


def test_orientation_is_verified_against_a_chiral_part(ldraw_dir, tmp_path):
    """A 180-degree 'rotation' that appears to fix orientation is a
    reflection: it measured RMSE 0.003 against the MIRROR of the render and
    0.344 against the render itself. A gear (4019) was tried first and was
    INCONCLUSIVE -- 0.0458 direct vs 0.0504 mirrored, inside the noise,
    because a 16-tooth gear is nearly invariant under the very reflection
    being tested (a part chiral to the eye need not be chiral to the RMSE
    metric). 4070 (the headlight brick) is asymmetric under BOTH a
    left-right flip (recessed stud is off-center) and a top-bottom flip
    (stud on top, notch on the bottom face), so a direct-vs-naive match is
    real evidence and not an artifact of near-symmetry.
    """
    naive = _render_svg("4070", "naive", tmp_path / "n")
    ported = _render_svg("4070", "occt", tmp_path / "o")
    if naive is None or ported is None:
        pytest.skip("CLI render unavailable (missing resvg or render failed)")
    rmse_direct, _, note_direct = raster_delta(ported, naive)
    rmse_lr, _, note_lr = raster_delta(ported, _mirrored(naive, Image.FLIP_LEFT_RIGHT))
    rmse_tb, _, note_tb = raster_delta(ported, _mirrored(naive, Image.FLIP_TOP_BOTTOM))
    if rmse_direct is None or rmse_lr is None or rmse_tb is None:
        pytest.skip(note_direct or note_lr or note_tb or "raster comparison unavailable")
    assert rmse_direct < rmse_lr
    assert rmse_direct < rmse_tb


def test_3001_renders_through_the_occt_engine(tmp_path):
    cfg = load_config(toml_path="labels.toml", root=".",
                      overrides={"fmt": "svg", "shading": "outline",
                                 "engine": "occt"})
    process_one(cfg, "3001", tmp_path)
    s = goldens.summarize_svg((tmp_path / "3001.svg").read_text())
    assert s["paths"] > 0
    assert s["fills"] == {"none": s["paths"]}    # strokes only, no fills


def test_circle_edges_become_arc_ops_not_polylines(ldraw_dir):
    """The whole point of the port: a projected stud rim arrives as a curve,
    so nothing has to guess a circle back out of a chord polygon. A weak
    `any(op[0] == "arc")` check would still pass if U/V collapsed to unit
    vectors, so this also checks the ops are radius-scaled and that the
    parametric ellipse reconstructs the real edge endpoints."""
    import math

    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    shape = occt.build_shape(occt.flatten_part("3941", ldraw_dir))
    edges = occt.hlr_edges(shape, *hlr.view_basis(30.0, 45.0))
    ops = occt.edges_to_ops(edges)
    assert any(op[0] == "arc" for op in ops)

    for comp in edges.values():
        if comp is None:
            continue
        ex = TopExp_Explorer(comp, TopAbs_ShapeEnum.TopAbs_EDGE)
        while ex.More():
            edge = TopoDS.Edge_s(ex.Current())
            c = BRepAdaptor_Curve(edge)
            curve_type = c.GetType()
            if curve_type == GeomAbs_CurveType.GeomAbs_Circle:
                r_maj = r_min = c.Circle().Radius()
            elif curve_type == GeomAbs_CurveType.GeomAbs_Ellipse:
                r_maj, r_min = c.Ellipse().MajorRadius(), c.Ellipse().MinorRadius()
            else:
                ex.Next()
                continue

            op = occt._edge_ops(edge, "line")[0]
            assert op[0] == "arc"
            _, cx, cy, ux, uy, vx, vy, t0, t1, _kind = op

            # Radius-scaled, not unit vectors -- this is the check a bare
            # `op[0] == "arc"` cannot make: unit U/V would still tag "arc".
            assert math.hypot(ux, uy) == pytest.approx(r_maj, rel=1e-6)
            assert math.hypot(vx, vy) == pytest.approx(r_min, rel=1e-6)

            for t in (t0, t1):
                x = cx + ux * math.cos(t) + vx * math.sin(t)
                y = cy + uy * math.cos(t) + vy * math.sin(t)
                p = c.Value(t)
                assert x == pytest.approx(p.X(), abs=1e-6)
                assert y == pytest.approx(p.Y(), abs=1e-6)
            return
    pytest.fail("no circle/ellipse edge found in HLR output for 3941")


def test_outline_compound_edges_are_silhouette_kind(ldraw_dir):
    """`kind == 'sil'` selects --silhouette-width downstream. The kernel
    reports the sharp/smooth/silhouette split directly, so this is kernel
    output rather than the inference the naive engine does."""
    shape = occt.build_shape(occt.flatten_part("3941", ldraw_dir))
    edges = occt.hlr_edges(shape, *hlr.view_basis(30.0, 45.0))
    ops = occt.edges_to_ops({"outline": edges["outline"]})
    assert ops and all(op[-1] == "sil" for op in ops)
