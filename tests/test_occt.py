import collections
import importlib.util
import math
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


def _render_svg(part: str, engine: str, out: Path) -> Path:
    """Render `part` with `engine` via the real CLI and rasterize it with
    resvg. Raises RuntimeError on a genuine CLI failure -- callers should
    let that fail the test, not skip it, since a silent skip would blind
    the suite to the engine breaking outright. Skip only for a missing
    `resvg` binary, which callers check for themselves."""
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "brick_icons.cli", part, "--engine", engine,
         "--format", "svg", "--shading", "outline", "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT)
    svgs = sorted(out.glob("*.svg"))
    if proc.returncode != 0 or not svgs:
        raise RuntimeError(
            f"CLI render of {part!r} with --engine {engine} failed "
            f"(exit {proc.returncode}):\n{proc.stderr}")
    png = out / "render.png"
    rproc = subprocess.run(
        ["resvg", "--background", "white", "--width", "512", str(svgs[0]), str(png)],
        capture_output=True, text=True)
    if rproc.returncode != 0:
        raise RuntimeError(f"resvg failed on {svgs[0]}:\n{rproc.stderr}")
    return png


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
    """OCCT derives image Y as Z x X. Z = +cross(right, up), not -cross(...),
    was settled empirically (task-6 fix round 1: an 8-way sweep against the
    naive engine's render of a chiral part, see occt.projector_axes and
    task-6-report.md) -- the algebraically "obvious" Z = forward put the
    virtual eye on the wrong side of the part and drew its hidden underside.
    edges_to_ops negates the resulting HLR Y to compensate, so the pipeline's
    net screen-Y convention is still -up; this test checks the raw identity
    before that compensation, which comes out as +up for this Z.

    cross(cross(right, up), right) == up holds for ANY orthonormal pair by
    the triple-product identity regardless of which way Z points, so a
    flipped Z alone still fails this (Z's sign changes which side X x Z
    lands on). What it can't catch is Z and X flipping TOGETHER, since that
    combination preserves the identity -- that's the failure mode this test
    and test_orientation_is_verified_against_a_chiral_part are complementary
    on: between them, neither flip escapes both checks, but neither test
    alone catches both.
    """
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    z, x = occt.projector_axes(right, up)
    assert np.allclose(np.cross(z, x), up, atol=1e-9)


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
    if not shutil.which("resvg"):
        pytest.skip("resvg binary not installed")
    naive = _render_svg("4070", "naive", tmp_path / "n")
    ported = _render_svg("4070", "occt", tmp_path / "o")
    rmse_direct, _, note_direct = raster_delta(ported, naive)
    rmse_lr, _, note_lr = raster_delta(ported, _mirrored(naive, Image.FLIP_LEFT_RIGHT))
    rmse_tb, _, note_tb = raster_delta(ported, _mirrored(naive, Image.FLIP_TOP_BOTTOM))
    if rmse_direct is None or rmse_lr is None or rmse_tb is None:
        pytest.fail(note_direct or note_lr or note_tb or "raster comparison unavailable")
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
    edges = occt.hlr_edges(shape, *hlr.view_basis(30.0, 45.0)[:2])
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

            # op's t0/t1 are DEGREES (the SVG/raster consumers' convention);
            # c.Value() wants OCCT's native radians.
            for t_deg in (t0, t1):
                t = math.radians(t_deg)
                x = cx + ux * math.cos(t) + vx * math.sin(t)
                y = cy + uy * math.cos(t) + vy * math.sin(t)
                p = c.Value(t)
                assert x == pytest.approx(p.X(), abs=1e-6)
                assert y == pytest.approx(p.Y(), abs=1e-6)
            return
    pytest.fail("no circle/ellipse edge found in HLR output for 3941")


def test_unoccluded_stud_rims_sweep_a_full_360(ldraw_dir):
    """task-6 fix round 2: OCCT's FirstParameter/LastParameter are radians,
    and every 'arc' op consumer (trace._arc_to_svg, process.draw_segments)
    reads t0/t1 as degrees. Unconverted, a full circle's 0..2*pi span reads
    as a ~6-degree sliver -- rims rendered as tiny disconnected chevrons
    instead of closed circles, while `any(op[0] == "arc")` and even the
    radius/endpoint checks above stayed green throughout, because both
    checks hold regardless of what units t0/t1 are in. A count- or
    existence-based assertion cannot catch this; only the actual angular
    span can. 3001's 8 stud top rims are unoccluded by construction (a
    stud's own top-rim silhouette can't be hidden by anything shorter than
    itself), so each must be swept exactly once end to end.

    Sewing splits a rim circle where the abutting faces' seams land, so the
    sweep arrives as several arcs about one centre; summing per centre is
    what makes this independent of that split. Asserting a single 360-degree
    op instead passed only while cylinders were built as capped solids,
    where the phantom cap's boundary circle laid a duplicate full rim over
    the fragments -- the assertion was reading the artifact, not the rim.
    """
    shape = occt.build_shape(occt.flatten_part("3001", ldraw_dir))
    edges = occt.hlr_edges(shape, *hlr.view_basis(30.0, 45.0)[:2])
    ops = occt.edges_to_ops(edges)
    rim_r = 6.0    # stud rim radius in the part's own primitive units
    sweeps = collections.defaultdict(float)
    for op in ops:
        if op[0] != "arc":
            continue
        if math.hypot(op[3], op[4]) != pytest.approx(rim_r, rel=1e-3):
            continue
        sweeps[(round(op[1], 3), round(op[2], 3))] += abs(op[8] - op[7])
    full = [c for c, deg in sweeps.items() if deg == pytest.approx(360.0, abs=1e-6)]
    assert len(full) == 8, dict(sweeps)
    # the other 8 are the stud BASE rims, half-hidden behind their own stud
    assert sorted(round(d, 6) for d in sweeps.values()) == [180.0] * 8 + [360.0] * 8


def test_outline_compound_edges_are_silhouette_kind(ldraw_dir):
    """`kind == 'sil'` selects --silhouette-width downstream. The kernel
    reports the sharp/smooth/silhouette split directly, so this is kernel
    output rather than the inference the naive engine does."""
    shape = occt.build_shape(occt.flatten_part("3941", ldraw_dir))
    edges = occt.hlr_edges(shape, *hlr.view_basis(30.0, 45.0)[:2])
    ops = occt.edges_to_ops({"outline": edges["outline"]})
    assert ops and all(op[-1] == "sil" for op in ops)


def _face_area(face):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    return g.Mass()


def test_full_ring_face_has_its_hole():
    """ringN at 360 degrees must come out as an annulus, not a disc and not
    nothing. `TopoDS_Wire.Reversed()` returns a TopoDS_SHAPE, which
    `BRepBuilderAPI_MakeFace.Add` rejects outright -- and `occt_faces` catches
    every exception and returns [], so the ring vanished from the sewn solid
    with no error anywhere. Area is what separates the three outcomes: an
    empty list, a disc (pi*r_out^2), and the annulus.
    """
    prim = P("ring", np.diag([3.0, 1.0, 3.0]), np.zeros(3), inner=3)
    faces = occt.occt_faces(prim)
    assert len(faces) == 1
    # inner 3*3 = 9, outer (3+1)*3 = 12
    assert _face_area(faces[0]) == pytest.approx(math.pi * (144 - 81), rel=1e-6)


def test_ring_sector_face_has_its_hole():
    """The bounded-sector path builds the inner boundary from real edges
    rather than a reversed wire, so it never hit the bug above -- pinned so a
    shared refactor of annulus_face can't regress it silently."""
    prim = P("ring", np.diag([3.0, 1.0, 3.0]), np.zeros(3), sector=90.0, inner=3)
    faces = occt.occt_faces(prim)
    assert len(faces) == 1
    assert _face_area(faces[0]) == pytest.approx(math.pi * (144 - 81) / 4, rel=1e-6)


def test_6589_bore_geometry_survives_into_the_shape(ldraw_dir):
    """6589's hub is four ring webs; with them dropped the axle-hole geometry
    behind them lost its surround and the render came back a blank disc.
    Guards the part-level consequence, not just the face builder."""
    out = occt.flatten_part("6589", ldraw_dir)
    rings = [p for p in out["analytic"] if p.kind == "ring"]
    assert rings, "6589 is expected to carry ring primitives"
    assert all(occt.occt_faces(p) for p in rings)


def _surface_types(shape):
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.TopoDS import TopoDS
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_ShapeEnum
    out = []
    ex = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while ex.More():
        out.append(BRepAdaptor_Surface(TopoDS.Face_s(ex.Current())).GetType())
        ex.Next()
    return out


def test_cylinder_is_an_open_tube_not_a_capped_solid():
    """LDraw's `cyli` is the lateral surface alone -- open at both ends.
    `BRepPrimAPI_MakeCylinder(...).Shape()` hands back a SOLID, whose two
    planar end caps are material the part never had. On 6589 the r=9 bore
    cylinder's cap sealed the axle hole and HLR correctly hid the cross
    behind it, which read as "OCCT lost the geometry"."""
    from OCP.GeomAbs import GeomAbs_SurfaceType
    prim = P("cyli", np.diag([9.0, 3.0, 9.0]), np.zeros(3))
    faces = occt.occt_faces(prim)
    assert len(faces) == 1
    kinds = _surface_types(faces[0])
    assert kinds == [GeomAbs_SurfaceType.GeomAbs_Cylinder], f"got {kinds}"
    assert _face_area(faces[0]) == pytest.approx(2 * math.pi * 9.0 * 3.0, rel=1e-6)


def test_cone_is_an_open_skirt_not_a_capped_solid():
    """Same cap trap as the cylinder, via the shared BRepPrimAPI_MakeOneAxis
    base: `.Shape()` is a solid, `.Face()` is the lateral surface."""
    from OCP.GeomAbs import GeomAbs_SurfaceType
    prim = P("con", np.diag([2.0, 2.5, 2.0]), np.zeros(3), top=5)
    faces = occt.occt_faces(prim)
    assert len(faces) == 1
    kinds = _surface_types(faces[0])
    assert kinds == [GeomAbs_SurfaceType.GeomAbs_Cone], f"got {kinds}"
    r_base, r_top = occt.cone_radii(prim)          # 12 and 10
    slant = math.hypot(r_base - r_top, 2.5)
    assert _face_area(faces[0]) == pytest.approx(
        math.pi * (r_base + r_top) * slant, rel=1e-6)


def test_cylinder_sector_keeps_its_sweep_without_caps():
    prim = P("cyli", np.diag([9.0, 3.0, 9.0]), np.zeros(3), sector=90.0)
    faces = occt.occt_faces(prim)
    assert len(faces) == 1
    assert _face_area(faces[0]) == pytest.approx(2 * math.pi * 9.0 * 3.0 / 4, rel=1e-6)


def test_no_analytic_primitive_of_6589_contributes_a_cap(ldraw_dir):
    """Part-level guard: every face 6589's recognized primitives contribute is
    a curved surface or an annulus wire-bounded plane -- never a full disc
    sealing the bore."""
    from OCP.GeomAbs import GeomAbs_SurfaceType
    out = occt.flatten_part("6589", ldraw_dir)
    caps = []
    for p in out["analytic"]:
        if p.kind not in ("cyli", "con"):
            continue
        for f in occt.occt_faces(p):
            caps += [t for t in _surface_types(f)
                     if t == GeomAbs_SurfaceType.GeomAbs_Plane]
    assert caps == [], f"{len(caps)} phantom cap face(s) on 6589"


def test_authored_condlines_are_tagged_smooth(ldraw_dir):
    """A type-5 conditional line declares its edge INTERIOR to one smooth
    surface. Untagged, every tessellation boundary reaches HLR as a hard edge
    and draws — 3941's wall goes 70 lines to 324."""
    out = occt.flatten_part("3941", ldraw_dir)
    assert out["5"], "3941 must author condlines for this test to mean anything"
    shape = occt.build_shape(out)
    edges = occt.hlr_edges(shape, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]))
    smooth = edges.get("smooth")
    assert smooth is not None and not smooth.IsNull(), (
        "condline edges must land in the smooth (Rg1Line) compound")


def test_smooth_edges_are_not_drawn(ldraw_dir):
    """LDraw's rule: a conditional line is invisible until it IS the
    silhouette. The silhouette still arrives via the outline compound, so
    dropping the smooth compound is that rule, not a loss."""
    out = occt.flatten_part("3941", ldraw_dir)
    shape = occt.build_shape(out)
    comps = occt.hlr_edges(shape, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]))
    assert comps.get("smooth") is not None
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    ex, n_smooth = TopExp_Explorer(comps["smooth"],
                                   TopAbs_ShapeEnum.TopAbs_EDGE), 0
    while ex.More():
        n_smooth += 1
        ex.Next()
    assert n_smooth, "fixture must actually have smooth edges"
    drawn = occt.edges_to_ops(comps)
    without = occt.edges_to_ops(
        {k: v for k, v in comps.items() if k != "smooth"})
    assert len(drawn) == len(without), (
        "smooth edges must not contribute drawn ops")
