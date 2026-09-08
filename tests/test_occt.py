import collections
import importlib.util
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

occt = pytest.importorskip("brick_icons.occt", reason="needs the [occt] extra")

from brick_icons import arcfit, geom2d, hlr, goldens  # noqa: E402
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


def test_a_skew_axis_is_rejected():
    """`frame` reads the axis as square to the cross-section and says so when
    it is not. Only the caller that can build the oblique sweep asks again --
    see the wall test below. A shear WITHIN that plane is a different case
    entirely."""
    R = np.array([[1.0, 0.3, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert occt.frame(P("cyli", R, np.zeros(3))) is None


def _oblique_wall():
    """49492's hook: a 4-4cyli whose axis leans 8.6 degrees out of the
    circle's plane, one of four that bend the shepherd's crook."""
    return np.array([[4.0, 0.0, 0.0],
                     [0.0, -13.8, 0.0],
                     [0.0, 2.1, 4.0]])


def test_an_oblique_cylinder_builds_a_swept_wall():
    """A circle swept along a skew axis is an exact surface -- the prism
    elliptic_wall already builds for an elliptical one -- so dropping it takes
    a wall the part authored. 49492 lost two of its six shaft segments that
    way and drew as three pieces of a hook with gaps between them.

    Area against the sweep's own integral: lateral area is
    int |C'(t) x A| dt, which is perimeter x |A| only when A is square to the
    section, so measuring it that way would pass on a wall built upright.
    """
    R = _oblique_wall()
    prim = P("cyli", R, np.zeros(3))
    assert occt.frame(prim) is None
    faces = occt.occt_faces(prim)
    assert len(faces) == 1
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    th = np.linspace(0.0, 2.0 * math.pi, 200001)
    dC = (-np.sin(th)[:, None] * U + np.cos(th)[:, None] * V)
    area = float(np.trapezoid(np.linalg.norm(np.cross(dC, A), axis=1), th))
    assert _face_area(faces[0]) == pytest.approx(area, rel=1e-6)


def test_a_rounded_rotation_is_not_read_as_skew():
    """LDraw writes a placement matrix to three decimals, so a rotation in a
    .dat is only orthonormal to about 1e-3 -- 76382 hangs each hand off
    0.985/0.696/0.707, whose Gram off-diagonal is 1.0e-3. Judged as skew, every
    round subpart under a rotated placement loses its exact surface and falls
    back to tessellation, which is what left the minifig hands a mess."""
    hand = np.array([[0.985, -0.12, 0.12],
                     [0.17, 0.696, -0.696],
                     [0.0, 0.707, 0.707]])
    assert abs(hand[:, 0] @ hand[:, 1]) > 1e-4          # above the old tol
    f = occt.frame(P("cyli", hand @ np.diag([4.0, 11.0, 4.0]), np.zeros(3)))
    assert f is not None
    assert occt.is_round(f[4], f[5]), "a rounded rotation is still a circle"


def _sheared_wall():
    """11090's tube wall: 1-4cylo whose u and v columns sit 89.2 degrees
    apart, with the axis exactly square to both."""
    return np.column_stack([np.array([6.33731, 0.0, -6.25]),
                            np.array([0.0, -20.0, 0.0]),
                            np.array([6.33731, 0.0, 6.25])])


def test_a_sheared_cross_section_is_diagonalized_not_dropped():
    """A linear map sends a circle to an ellipse whatever the shear, so the
    singular values of [u v] are exact semi-axes -- there is nothing to
    approximate. Rejected, 11090's wall reached OCCT as neither a face nor
    triangles, because flatten never loads a substituted primitive's mesh, and
    the base drew hollow with the bore showing through it."""
    f = occt.frame(P("cyli", _sheared_wall(), np.zeros(3), sector=90.0))
    assert f is not None
    _o, uh, _ah, vh, ru, rv, _h, _rh, ph = f
    assert uh @ vh == pytest.approx(0.0, abs=1e-12)
    assert (ru, rv) == pytest.approx((8.96231, 8.83883), rel=1e-5)
    # the diagonalized frame retraces the primitive's own points: the sector
    # rides along in `ph`, and dropping it swings the quarter 135 degrees.
    th = np.linspace(0.0, math.radians(90.0), 64)
    U, V = _sheared_wall()[:, 0], _sheared_wall()[:, 2]
    assert np.cos(th)[:, None] * U + np.sin(th)[:, None] * V == pytest.approx(
        np.cos(th + ph)[:, None] * ru * uh
        + np.sin(th + ph)[:, None] * rv * vh, abs=1e-9)


def test_an_unsheared_frame_carries_no_phase():
    """ph is 0 for everything that already worked, so no sector moves."""
    f = occt.frame(P("cyli", np.diag([4.0, 10.0, 5.0]), np.zeros(3)))
    assert f[8] == 0.0


def test_a_sheared_wall_builds_one_face():
    """Area against the arc length of the primitive's OWN parameterization,
    not of the diagonalized frame: a 90-degree span of an ellipse is a quarter
    of its perimeter only when it is centered on an axis, and this one starts
    at 135 degrees. Measuring the wall the other way hides a lost phase."""
    R = _sheared_wall()
    prim = P("cyli", R, np.zeros(3), sector=90.0)
    faces = occt.occt_faces(prim)
    assert len(faces) == 1
    th = np.linspace(0.0, math.radians(90.0), 200001)
    pts = np.cos(th)[:, None] * R[:, 0] + np.sin(th)[:, None] * R[:, 2]
    arc = float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())
    assert _face_area(faces[0]) == pytest.approx(arc * 20.0, rel=1e-6)


@pytest.mark.parametrize("kind", ["ring", "disc", "edge"])
def test_a_planar_primitive_ignores_a_skew_axis_column(kind):
    """A ring/disc/edge is entirely at local y=0, so the matrix's axis column
    is not its geometry. 3820 caps its grip with two 2-4ring2 whose axis
    column is 14 degrees off the plane, and rejecting them for it dropped both
    rim annuli into tessellation."""
    # the ring's own columns are orthonormal; only the unused axis is skew
    R = np.array([[-2.0, 0.0, 0.0],
                  [0.0, -1.0, -0.5008],
                  [0.0, 0.0, 1.93629]])
    f = occt.frame(P(kind, R, np.zeros(3)))
    assert f is not None
    _o, uh, ah, vh, ru, rv, _h, rh, _ph = f
    assert (ru, rv) == pytest.approx((2.0, 2.0), rel=1e-5)
    # the axis comes from the plane the primitive actually occupies
    assert ah == pytest.approx(np.cross(uh, vh))
    assert rh is True


def test_a_planar_primitive_with_sheared_own_axes_is_diagonalized():
    """u . v is the ring's own geometry, and a shear there is an ellipse whose
    axes are not the columns -- exact once you take the singular values, which
    is what the axis column can never be."""
    R = np.array([[1.0, 0.0, 0.3], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    f = occt.frame(P("ring", R, np.zeros(3)))
    assert f is not None
    _o, uh, ah, vh, ru, rv, _h, _rh, _ph = f
    assert uh @ vh == pytest.approx(0.0, abs=1e-12)
    assert (ru, rv) == pytest.approx((1.16119, 0.86119), rel=1e-4)
    # the axis column is square to both here, so it stays the axis; the
    # diagonalized pair may come out left-handed, which is what rh reports
    assert ah == pytest.approx(np.array([0.0, 1.0, 0.0]))
    assert abs(np.cross(uh, vh) @ ah) == pytest.approx(1.0)


def test_the_grip_rims_of_3820_build_exact_faces(ldraw_dir):
    """Both 2-4ring2 that cap the C-grip reach OCCT as annulus faces. With
    them tessellated the cavity filled solid and no inner rim was drawn."""
    out = occt.flatten_part("3820", ldraw_dir)
    rings = [p for p in out["analytic"] if p.kind == "ring"]
    assert len(rings) == 2
    assert all(len(occt.occt_faces(p)) == 1 for p in rings)


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


def _n_edges(comp):
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    ex, n = TopExp_Explorer(comp, TopAbs_ShapeEnum.TopAbs_EDGE), 0
    while ex.More():
        n += 1
        ex.Next()
    return n


def test_only_authored_edges_are_candidates(ldraw_dir):
    """LDraw states its edges; it does not imply them. Feeding the faces to
    HLR for occlusion only, and the authored edges as edge-shapes, makes an
    unauthored facet boundary structurally undrawable -- 4740p03 authors no
    type-2 lines at all and drew 13359 when every sewn edge was a candidate."""
    out = occt.flatten_part("4740p03", ldraw_dir)
    assert not out["2"], "4740p03 must author no type-2 lines for this to mean anything"
    right, up = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    shape = occt.build_shape(out)
    hard, cond = occt.authored_edges(out, right, up)
    every = occt.hlr_edges(shape, right, up)
    only = occt.hlr_edges(shape, right, up, edges=hard, cond=cond)
    assert _n_edges(every["sharp"]) > 1000, "fixture must have a facet explosion to suppress"
    assert _n_edges(only["sharp"]) < 50


def test_condline_is_drawn_only_when_it_reads_as_silhouette(ldraw_dir):
    """A type-5 conditional line is invisible until it IS the silhouette --
    which is what a tessellated dish has instead of one, since HLR's outline
    compound reports the true silhouette of an analytic surface only."""
    out = occt.flatten_part("3960", ldraw_dir)
    assert out["5"], "3960 must author condlines for this test to mean anything"
    right, up = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    _hard, cond = occt.authored_edges(out, right, up)
    assert 0 < _n_edges(cond) < len(out["5"]) // 10, (
        "a condline must be drawn only where its control points agree")


def test_analytic_crease_skips_the_parametric_seam(ldraw_dir):
    """A closed surface's seam has the same face on both sides. Kept, it draws
    a radial line from 4740's stud to its rim that no edge of the part has."""
    out = occt.flatten_part("4740", ldraw_dir)
    shape = occt.build_shape(out)
    creases = occt.analytic_creases(shape, out)
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    ex = TopExp_Explorer(creases, TopAbs_ShapeEnum.TopAbs_EDGE)
    kinds = []
    while ex.More():
        kinds.append(BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current())).GetType())
        ex.Next()
    assert kinds, "4740's dish rim must survive as a crease"
    assert all(k == GeomAbs_CurveType.GeomAbs_Circle for k in kinds), (
        "a straight crease here is the cylinder seam, which is not an edge")


def _ellipse_perimeter(a, b):
    """Ramanujan's approximation; good to ~1e-9 at these axis ratios."""
    h = ((a - b) / (a + b)) ** 2
    return math.pi * (a + b) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))


def test_elliptical_cylinder_builds_a_wall():
    """ru != rv is an ellipse, not shear -- 50950's wall measures 68.28 by
    84.85 at an orthogonality residual of exactly 0, so no shear tolerance can
    reach it. Rejected, it built no face, and the slope rendered with no
    occluder at all: you saw its underside through the top. No BRepPrimAPI
    maker builds an elliptical cylinder, so this extrudes a gp_Elips, and area
    is what tells a real wall from a circular one at either radius.
    """
    prim = P("cyli", np.diag([4.0, 10.0, 5.0]), np.zeros(3))
    faces = occt.occt_faces(prim)
    assert len(faces) == 1
    assert _face_area(faces[0]) == pytest.approx(
        _ellipse_perimeter(5.0, 4.0) * 10.0, rel=1e-6)


def test_elliptical_cone_is_not_guessed_at():
    """occt_faces returning [] is the honest answer where no measured part
    pins what the shape should be -- see CLAUDE.md on silent []."""
    assert occt.occt_faces(P("con", np.diag([4.0, 10.0, 5.0]), np.zeros(3))) == []


def test_elliptical_disc_and_ring_build_planar_faces():
    """Every non-round disc and ring used to return [], and 190085a -- oval
    discs and an oval rim, no triangles at all -- drew literally nothing."""
    disc = occt.occt_faces(P("disc", np.diag([4.0, 10.0, 5.0]), np.zeros(3)))
    assert len(disc) == 1
    assert _face_area(disc[0]) == pytest.approx(math.pi * 4.0 * 5.0, rel=1e-6)
    ring = occt.occt_faces(P("ring", np.diag([4.0, 10.0, 5.0]), np.zeros(3),
                             inner=2))
    assert len(ring) == 1
    assert _face_area(ring[0]) == pytest.approx(
        math.pi * 4.0 * 5.0 * (3.0 ** 2 - 2.0 ** 2), rel=1e-6)


def test_an_elliptical_sector_keeps_its_span():
    """A quarter of an axis-aligned ellipse is a quarter of its area whichever
    semi-axis is longer. ellipse_axes turns the frame when rv wins, so the
    radial ends are read back off the arc instead of derived through that turn
    a second time."""
    for R in (np.diag([4.0, 10.0, 5.0]), np.diag([5.0, 10.0, 4.0])):
        faces = occt.occt_faces(P("ring", R, np.zeros(3), sector=90.0, inner=2))
        assert len(faces) == 1
        assert _face_area(faces[0]) == pytest.approx(
            math.pi * 4.0 * 5.0 * (3.0 ** 2 - 2.0 ** 2) / 4.0, rel=1e-6)


def test_190085a_oval_discs_reach_the_shape(ldraw_dir):
    """The part-level consequence: this sticker is primitives only, so with
    its discs dropped the shape was the 0.25 LDU rim and nothing else."""
    out = occt.flatten_part("190085a", ldraw_dir)
    assert not out["tri"], "190085a is expected to carry no triangles"
    planar = [p for p in out["analytic"] if p.kind in ("disc", "ring")]
    assert planar and not any(occt.is_round(*occt.frame(p)[4:6]) for p in planar)
    assert all(len(occt.occt_faces(p)) == 1 for p in planar)
    assert occt.count_faces(occt.build_shape(out)) > 1


def test_50950_wall_is_elliptical_and_reaches_the_shape(ldraw_dir):
    """The part-level consequence, not just the face builder."""
    from OCP.GeomAbs import GeomAbs_SurfaceType
    out = occt.flatten_part("50950", ldraw_dir)
    cylis = [p for p in out["analytic"] if p.kind == "cyli"]
    assert cylis, "50950 is expected to carry a cyli primitive"
    assert not any(occt.is_round(*occt.frame(p)[4:6]) for p in cylis)
    assert GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion in _surface_types(
        occt.build_shape(out))


def test_11090_tube_wall_reaches_the_shape(ldraw_dir):
    """The part-level consequence: both halves of the bar tube's wall build a
    face, so the wall occludes the bore inside it."""
    from OCP.GeomAbs import GeomAbs_SurfaceType
    out = occt.flatten_part("11090", ldraw_dir)
    walls = [p for p in out["analytic"]
             if p.kind == "cyli" and np.linalg.norm(p.R[:, 0]) > 8.0]
    assert len(walls) == 2, "11090's tube wall is two quarter cylinders"
    assert all(len(occt.occt_faces(p)) == 1 for p in walls)
    assert GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion in _surface_types(
        occt.build_shape(out))


def _occt_render(part, ldraw_dir):
    out = occt.flatten_part(part, ldraw_dir)
    return occt.visible_segments(out, *hlr.view_basis(30.0, 45.0)[:2], 1024)


def test_50950_wall_draws_as_one_arc(ldraw_dir):
    """HLR hands a projected ELLIPSE back as a BSpline approximation -- only a
    projected circle survives as a conic -- so the wall drew as 31 straight
    segments. locus_arc re-reads the fragment against the exact projected
    conic it was matched to. Both rims of the wall are one arc each, and a
    BSpline approximation emits no arc op at all, so the count is the test.
    """
    res = _occt_render("50950", ldraw_dir)
    assert sum(1 for op in res.segs if op[0] == "arc") == 2


def test_silhouette_polys_cover_the_drawn_ink(ldraw_dir):
    """The stroke layer's closed contour comes from these, and it is the only
    thing mitering an outline corner sharp -- without it the per-edge round
    caps barb at an acute vertex. An empty or degenerate silhouette fails
    silently, drawing nothing, so assert it actually contains the drawing.
    """
    from brick_icons import geom2d
    res = _occt_render("50950", ldraw_dir)
    assert res.sil_polys
    g = geom2d.union_all([geom2d.to_geom(np.asarray(q, float))
                          for q in res.sil_polys])
    x0, y0, x1, y1 = res.bbox
    gx0, gy0, gx1, gy1 = g.bounds
    assert (gx0, gy0, gx1, gy1) == pytest.approx((x0, y0, x1, y1), abs=0.5)


def _arcfit_split(part, ldraw_dir):
    """`out` as the engine really receives it: arcfit has already MOVED every
    fitted chain out of out["2"] into out["fit_arcs"]."""
    from brick_icons import arcfit
    out = occt.flatten_part(part, ldraw_dir)
    out["fit_arcs"], out["2"] = arcfit.fit_edge_arcs(out["2"], out["5"])
    return out


def test_arcfit_chains_still_reach_the_authored_loci(ldraw_dir):
    """arcfit claims a hand-faceted chain by REMOVING it from out["2"], so a
    locus set built from out["2"] alone has no entry for it and every fragment
    on it fails select_authored. On 3941 that is the whole axle-hole rim: 40
    of its 120 type-2 edges, drawn by naive and by nothing in occt."""
    out = _arcfit_split("3941", ldraw_dir)
    assert out["fit_arcs"], "3941 must yield fitted chains for this to mean anything"
    right, up = hlr.view_basis(30.0, 45.0)[:2]
    loci = occt.authored_loci(occt.build_shape(out), out, right, up)
    for a in out["fit_arcs"]:
        P = np.asarray(a["P"], float)
        for p, q in zip(P[:-1], P[1:]):
            pts = occt._proj2(np.linspace(p, q, 5), *occt._screen_axes(right, up))
            assert any(occt._on_locus(pts, l) for l in loci), \
                f"chain chord {p} -> {q} lies on no authored locus"


def test_3941_bore_rim_is_drawn_by_the_occt_engine(ldraw_dir):
    """The rim of the axle hole, end to end. Before the chains were added to
    the loci this counted 0 -- occt drew only the four condline bore verticals,
    which is the 'four thin spikes' the corpus review saw."""
    out = _arcfit_split("3941", ldraw_dir)
    res = occt.visible_segments(out, *hlr.view_basis(30.0, 45.0)[:2], 1024)
    from brick_icons import primitives
    near = []
    for op in res.segs:
        if op[-1] == "sil":
            continue        # occt tags an authored line "line", not "edge"
        xs, ys, _ = primitives._samples_for(op, 5)
        if np.all(np.hypot(xs, ys) < 7.0):
            near.append(op)
    assert len(near) >= 10, f"axle-hole rim ops drawn: {len(near)}"
    # ... and re-read against the fitted circle, not left as the chords the
    # BRep fragments actually are: chords draw the rounded corner between two
    # teeth as two segments meeting at a point.
    assert any(op[0] == "arc" for op in near), \
        "chain fragments must emit as arcs, like the naive engine's"


def test_the_frame_holds_a_dish_whose_edges_span_a_third_of_it(ldraw_dir):
    """4740 seen from the front: HLR reports edges over 14 LDU of a part that
    is 40 wide, because the rest of the dish is drawn by the silhouette
    contour and by no edge at all. Framing on the ops alone put 26 LDU outside
    the viewBox, where it was clipped away."""
    out = occt.flatten_part("4740", ldraw_dir)
    right, up = hlr.view_basis(0.0, 0.0)[:2]
    res = occt.visible_segments(out, right, up, 1024)
    P = np.vstack([np.asarray(q, float) for q in res.sil_polys])
    x0, y0, x1, y1 = res.bbox
    assert (x0, y0, x1, y1) == pytest.approx(
        (min(x0, P[:, 0].min()), min(y0, P[:, 1].min()),
         max(x1, P[:, 0].max()), max(y1, P[:, 1].max())), abs=1e-6)
    assert x1 - x0 > 30.0, f"the dish is 40 LDU wide; framed {x1 - x0:.1f}"


def test_op_projection_matches_the_space_the_ops_are_written_in():
    """apply_affine_faces applies the canvas fit later, so the projection
    handed to order_faces carries the identity pixel fit."""
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    ax, ay = occt._screen_axes(right, up)
    P = np.array([[1.0, 2.0, 3.0], [-4.0, 5.0, 6.0], [0.0, 0.0, 0.0]])
    raw = occt._proj2(P, ax, ay)
    raw[:, 1] *= -1.0                      # _negate_y, applied to points
    proj = occt.op_projection(right, up, fwd)
    x, y, _ = proj.to_px(P)
    assert np.allclose(np.stack([x, y], 1), raw)


def test_op_projection_ray_origin_inverts_it():
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    P = np.array([[7.0, -2.0, 4.0]])
    x, y, _ = proj.to_px(P)
    O = proj.ray_origin(x, y)
    # the ray origin differs from P only along the view direction
    assert np.allclose(np.cross(P[0] - O[0], fwd), 0.0, atol=1e-9)


def test_forward_is_the_negated_projector_axis():
    """occt takes fwd from the caller. Anyone recomputing it locally has to
    get this sign, or every depth comparison runs backwards."""
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    z, _ = occt.projector_axes(right, up)
    assert np.allclose(-z / np.linalg.norm(z), fwd)


def test_wire_points_of_a_circle_lie_on_that_circle():
    o = np.array([0.0, 0.0, 0.0])
    face = occt.annulus_face(o, np.array([0.0, 1.0, 0.0]),
                             np.array([1.0, 0.0, 0.0]), 0.0, 6.0,
                             2 * math.pi)
    pts = occt._wire_points(occt.BRepTools.OuterWire_s(face))
    r = np.linalg.norm(pts - o, axis=1)
    assert np.allclose(r, 6.0, atol=1e-9)
    assert len(pts) >= 40           # 9-degree step over a full turn


def test_wire_points_of_a_polygon_are_its_corners():
    p = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 0.0, 4.0]])
    pts = occt._wire_points(occt.BRepTools.OuterWire_s(occt.tri_face(p)))
    assert len(pts) == 3
    for corner in p:
        assert np.min(np.linalg.norm(pts - corner, axis=1)) < 1e-9


def test_wire_points_do_not_repeat_the_shared_vertex():
    """Consecutive edges share an endpoint; emitting it twice puts a
    zero-length segment in the polygon, which shapely reads as invalid."""
    p = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 0.0, 4.0]])
    pts = occt._wire_points(occt.BRepTools.OuterWire_s(occt.tri_face(p)))
    d = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    assert d.min() > 1e-6


def _plane_faces_of(part, ldraw_dir, lat=30.0, long=45.0):
    out = occt.flatten_part(part, ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(lat, long)
    proj = occt.op_projection(right, up, fwd)
    return occt.plane_faces(shape, proj), proj


def test_a_ring_face_carries_its_bore_as_a_hole():
    o = np.zeros(3)
    face = occt.annulus_face(o, np.array([0.0, 1.0, 0.0]),
                             np.array([1.0, 0.0, 0.0]), 2.0, 6.0,
                             2 * math.pi)
    right, up, fwd = hlr.view_basis(90.0, 0.0)     # straight down the axis
    f = occt._plane_face(face, occt.op_projection(right, up, fwd))
    assert len(f["holes"]) == 1
    outer = np.linalg.norm(f["poly"] - f["poly"].mean(0), axis=1)
    inner = np.linalg.norm(f["holes"][0] - f["poly"].mean(0), axis=1)
    assert inner.max() < outer.min()


def test_a_flat_face_carries_the_fields_fill_ops_reads(ldraw_dir):
    faces, _ = _plane_faces_of("32062", ldraw_dir)
    assert faces
    for f in faces:
        assert set(f) >= {"poly", "normal", "depth", "zs", "plane", "color"}
        assert f["poly"].shape[1] == 2
        assert len(f["zs"]) == len(f["poly"])
        assert f["color"] == 16


def test_32062_is_all_flat_faces(ldraw_dir):
    """178 planes and no curved surface at all -- the part that proves the
    flat path without any limb solving."""
    from OCP.GeomAbs import GeomAbs_SurfaceType
    out = occt.flatten_part("32062", ldraw_dir)
    kinds = _surface_types(occt.build_shape(out))
    assert set(kinds) == {GeomAbs_SurfaceType.GeomAbs_Plane}


def test_the_sewn_shape_does_not_orient_its_faces_consistently(ldraw_dir):
    """Why there is no back-face cull. 4070's near right wall comes back
    oriented AWAY from the camera and its far twin oriented toward it, so a
    cull keyed on orientation drops a wall that is plainly visible and the
    brick's hollow interior draws through the hole."""
    out = occt.flatten_part("4070", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    away = []
    for face in occt._faces_of_type(shape, occt.GeomAbs_SurfaceType.GeomAbs_Plane):
        pl = occt.BRepAdaptor_Surface(face).Plane()
        d = pl.Axis().Direction()
        n = np.array([d.X(), d.Y(), d.Z()], float)
        if face.Orientation() == occt.TopAbs_Orientation.TopAbs_REVERSED:
            n = -n
        f = occt._plane_face(face, proj)
        if float(n @ proj.fwd) > 0:
            away.append(float(f["depth"]))
    assert away, "no face is oriented away at all"
    # the nearest surface in the drawing is among them: culling by orientation
    # would have removed it
    every = [f["depth"] for f in occt.plane_faces(shape, proj)]
    assert min(away) < np.median(every)


def test_a_plane_face_tones_toward_the_camera(ldraw_dir):
    """Follows from the above: with orientation untrustworthy, the tone normal
    is flipped to face the camera the way primitives._flat_face does, or a
    visible wall shades as if it were pointing away."""
    faces, _ = _plane_faces_of("4070", ldraw_dir)
    assert faces
    assert all(f["normal"][2] <= 1e-9 for f in faces)


def test_visible_segments_returns_faces_and_a_projection(ldraw_dir):
    out = occt.flatten_part("32062", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    assert res.faces
    assert res.proj is not None


def test_a_flat_part_actually_fills_under_occt(tmp_path, ldraw_dir):
    """The whole point: flat3 emitted strokes and no fills for the life of
    the port, and nothing errored."""
    from brick_icons.cli import build_parser, _config_from_args, process_one
    args = build_parser().parse_args(
        ["32062", "--engine", "occt", "--format", "svg",
         "--shading", "outline", "--shade-style", "flat3",
         "--out", str(tmp_path)])
    process_one(_config_from_args(args), "32062", tmp_path)
    svg = (tmp_path / "32062.svg").read_text()
    assert svg.count("fill=\"#") > 1


def test_the_fit_sidecar_still_composes_under_occt(ldraw_dir):
    """occt's Projection has an identity pixel fit, so canvas_affine must
    still return the canvas fit unchanged -- the sidecar reads it."""
    out = occt.flatten_part("32062", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    assert hlr.canvas_affine(res, 3.0, 5.0, 7.0) == (3.0, 5.0, 7.0)


def test_a_cylinder_across_the_view_has_two_limbs_half_a_turn_apart():
    # a and b span the RADIAL plane, so the axis is a x b -- here (1,0,0),
    # across the view. Spanning the view plane instead is the end-on cylinder
    # below, which has no limb at all.
    fwd = np.array([0.0, 0.0, 1.0])
    a, b, c = np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0]), np.zeros(3)
    us = occt._limb_params(a, b, c, fwd)
    assert len(us) == 2
    assert abs(((us[1] - us[0]) % (2 * math.pi)) - math.pi) < 1e-9


def test_an_end_on_cylinder_has_no_limb():
    """Axis along the view: the wall projects onto its own end circle and
    encloses no area, so there is no generator to cut it at."""
    fwd = np.array([0.0, 0.0, 1.0])
    a, b = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
    assert occt._limb_params(a, b, np.zeros(3), fwd) == []


def test_a_surface_that_never_turns_edge_on_has_no_limb():
    """A cone pointed at the camera: every normal leans toward it."""
    fwd = np.array([0.0, 0.0, 1.0])
    a = np.array([0.05, 0.0, 0.0]); b = np.array([0.0, 0.05, 0.0])
    c = np.array([0.0, 0.0, -1.0])
    assert occt._limb_params(a, b, c, fwd) == []


def test_a_limb_parameter_really_is_edge_on():
    # c=0.4 here makes |ratio| 1.07, so there are no roots and the assertion
    # below never runs -- the test then passes against any implementation.
    # Keep the axial term small enough that the surface does turn edge-on.
    fwd = np.array([0.3, -0.5, 0.81]); fwd = fwd / np.linalg.norm(fwd)
    a = np.array([1.0, 0.2, 0.0]); b = np.array([0.1, 1.0, 0.3])
    c = np.array([0.0, 0.0, 0.2])
    us = occt._limb_params(a, b, c, fwd)
    assert len(us) == 2
    for u in us:
        n = math.cos(u) * a + math.sin(u) * b + c
        assert abs(float(n @ fwd)) < 1e-9


def _curved_of(part, ldraw_dir, lat=30.0, long=45.0):
    out = occt.flatten_part(part, ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(lat, long)
    proj = occt.op_projection(right, up, fwd)
    return occt.curved_faces(shape, proj), proj


def test_a_cylinder_splits_into_spans_at_its_limbs(ldraw_dir):
    """3005 sews exactly one cylinder (its stud), and a stud seen from an
    iso view shows a front half and a back half."""
    faces, _ = _curved_of("3005", ldraw_dir)
    assert len(faces) == 2
    assert sum(1 for f in faces if f.get("interior")) == 1


def test_a_span_carries_the_gradient_fields_fill_ops_reads(ldraw_dir):
    faces, _ = _curved_of("4740", ldraw_dir)
    assert faces
    for f in faces:
        assert set(f) >= {"poly", "zs", "depth", "grad_samples", "span_deg",
                          "color"}
        # a full turn takes the radial gradient, a limb-cut span the linear one
        assert ("grad_axis" in f) != ("grad_radial" in f)
        if "grad_axis" not in f:
            continue
        offs = [o for o, _ in f["grad_samples"]]
        assert offs == sorted(offs)
        assert all(0.0 <= o <= 1.0 for o in offs)


def test_a_span_boundary_lies_on_the_true_projected_ellipse(ldraw_dir):
    """The point of the exact route: boundary points sit ON the conic, so
    arc recovery reads the run back as an arc instead of a chord fan."""
    out = occt.flatten_part("3005", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    ax, ay = occt._screen_axes(right, up)
    cyl = [f for f in occt._faces_of_type(shape, occt.GeomAbs_SurfaceType.GeomAbs_Cylinder)]
    surf = occt.BRepAdaptor_Surface(cyl[0]).Cylinder()
    o = surf.Position().Location()
    o = np.array([o.X(), o.Y(), o.Z()])
    xd, yd = surf.Position().XDirection(), surf.Position().YDirection()
    u = np.array([xd.X(), xd.Y(), xd.Z()]) * surf.Radius()
    v = np.array([yd.X(), yd.Y(), yd.Z()]) * surf.Radius()
    loc = occt._ell_locus(o, u, v, 1.0, 1.0, "sil", ax, ay)
    span = occt.curved_faces(shape, proj)[0]
    on = span["poly"].copy()
    on[:, 1] *= -1.0                     # back out of op space into locus space
    hits = sum(1 for p in on if occt._on_locus(p[None, :], loc))
    assert hits >= len(on) // 3          # the two arc runs, not the two limbs


def test_a_span_does_not_wrap_past_its_own_limb(ldraw_dir):
    faces, _ = _curved_of("3005", ldraw_dir)
    assert all(f["span_deg"] <= 180.0 + 1e-6 for f in faces)


def test_a_cylinder_span_occluder_reports_the_surface_depth(ldraw_dir):
    """The reason this slice pulls migration item 2 in: a flat depth is
    wrong in the middle of the span, which is where it overlaps a neighbour."""
    out = occt.flatten_part("3005", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    face = next(occt._faces_of_type(shape, occt.GeomAbs_SurfaceType.GeomAbs_Cylinder))
    occ = occt._face_occluder(face)
    point, _, _, _, _ = occt._curved_frame(face)
    u0, u1, v0, v1 = occt.BRepTools.UVBounds_s(face)
    # the occluder reports the NEAREST hit, so probe the front-most point:
    # taking mid-u would land on the back half half the time and compare the
    # near surface against the far one
    us = np.linspace(u0, u1, 181)
    P = point(us, (v0 + v1) / 2.0)
    x, y, z = proj.to_px(P)
    i = int(np.argmin(z))
    d = occ.depth(proj.ray_origin(x[i:i + 1], y[i:i + 1]), proj.fwd)
    assert np.isfinite(d).all()
    assert abs(float(d[0]) - float(z[i])) < 1e-6


def test_a_flat_face_gets_no_occluder(ldraw_dir):
    """Its depth is affine, so _plane_depth_fn is already exact and an
    occluder would be a slower way to get the same number."""
    out = occt.flatten_part("32062", ldraw_dir)
    shape = occt.build_shape(out)
    face = next(occt._faces_of_type(shape, occt.GeomAbs_SurfaceType.GeomAbs_Plane))
    assert occt._face_occluder(face) is None


def test_occt_segments_go_through_the_orphan_cull(ldraw_dir):
    """The stylization tail ran only on the naive branch, so occt drew
    dashes naive had already dropped -- 30162's dot on the barrel.

    Spelled out as the composition rather than a count, so a stage added to
    the tail has to be added here too: this is the record of what occt's
    output goes through between the engine and the caller.
    """
    out = occt.flatten_part("30162", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    kept = hlr.visible_segments("30162", ldraw_dir, render_px=512,
                                engine="occt").segs
    assert len(kept) < len(res.segs)
    tail = hlr.dedupe_segments(list(res.segs), eps=0.05 / res.s,
                               keep_order=True)
    tail, _sil = arcfit.fit_silhouette_arcs(tail)
    assert list(kept) == hlr.cull_orphan_runs(tail)


def test_a_zero_height_cylinder_face_gets_no_occluder(ldraw_dir):
    """72632's sensor body carries a cylinder face of zero height. Its local
    frame is singular, and building an occluder from it raised LinAlgError
    out of the render (the 72632 family, four census parts)."""
    out = occt.flatten_part("72632", ldraw_dir)
    shape = occt.build_shape(out)
    flat = [f for f in occt._faces_of_type(
        shape, occt.GeomAbs_SurfaceType.GeomAbs_Cylinder)
        if abs(occt.BRepTools.UVBounds_s(f)[3]
               - occt.BRepTools.UVBounds_s(f)[2]) < 1e-9]
    assert flat, "expected a zero-height cylinder face on 72632"
    assert all(occt._face_occluder(f) is None for f in flat)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    assert occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd).segs


def test_faces_come_back_in_paint_order(ldraw_dir):
    out = occt.flatten_part("3005", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    assert all("order" in f for f in res.faces)
    assert [f["order"] for f in res.faces] == sorted(f["order"] for f in res.faces)


def test_the_stud_paints_over_the_top_face_it_sits_on(ldraw_dir):
    """A near surface ordering behind a far one is the failure this whole
    task exists to prevent, and it is invisible in a field-set check."""
    out = occt.flatten_part("3005", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    walls = [f for f in res.faces if f["kind"] == "occt-wall"]
    flats = [f for f in res.faces if f["kind"] == "occt-plane"]
    assert walls and flats
    nearest_wall = min(walls, key=lambda f: f["depth"])
    nearest_flat = min(flats, key=lambda f: f["depth"])
    if nearest_wall["depth"] < nearest_flat["depth"]:
        assert nearest_wall["order"] > nearest_flat["order"]


def test_compare_engines_can_select_a_combo():
    spec = importlib.util.spec_from_file_location(
        "compare_engines", ROOT / "scripts" / "compare-engines.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    parts, args = mod.load_combo_parts(
        ROOT / "tests" / "goldens" / "manifest.toml", "outline-flat3",
        "unprinted")
    assert "--shade-style" in args and "flat3" in args
    assert "3068bp00" not in parts          # printed parts stay out
    assert len(parts) == 21


def test_a_full_turn_span_is_marked_interior(ldraw_dir):
    """It never turned edge-on, so it has no near half and no far half. The
    interior branch is the one whose depth probe falls back to the unclamped
    surface hit rather than to an affine plane through a curved sheet --
    4740's dish sorts into a dark crescent over its own top without it."""
    faces, _ = _curved_of("4740", ldraw_dir)
    full = [f for f in faces if f["span_deg"] > 359.999]
    assert full
    assert all(f["interior"] for f in full)


def test_an_elliptical_wall_produces_a_fill_span(ldraw_dir):
    """50950's wall is an extruded ellipse -- no BRepPrimAPI maker builds one,
    so it reaches HLR as a surface of extrusion rather than a cylinder. It was
    the one face kind in the corpus that contributed nothing, and contributed
    it silently: the slope's whole curved top drew as unfilled ribs."""
    out = occt.flatten_part("50950", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    face = next(occt._faces_of_type(
        shape, occt.GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion))
    spans = occt._faces_for(face, proj)
    assert len(spans) == 1
    assert spans[0]["span_deg"] == pytest.approx(45.0, abs=0.5)


def test_an_elliptical_wall_occluder_reports_the_surface_depth(ldraw_dir):
    """The occluder's sector is measured from local angle 0, so the face's
    parameter range has to be re-based. Doing that to the ELLIPSE would shear
    it; it is done to the unit circle R^-1 already maps the ellipse onto."""
    out = occt.flatten_part("50950", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    face = next(occt._faces_of_type(
        shape, occt.GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion))
    point, _, _, _, _ = occt._curved_frame(face)
    u0, u1, v0, v1 = occt.BRepTools.UVBounds_s(face)
    occ = occt._face_occluder(face)
    P = point(np.linspace(u0, u1, 25), (v0 + v1) / 2.0)
    x, y, z = proj.to_px(P)
    d = np.asarray(occ.depth(proj.ray_origin(x, y), proj.fwd), float)
    assert np.isfinite(d).all()
    assert np.abs(d - z).max() < 1e-6


def test_every_corpus_surface_kind_is_one_the_face_producer_handles(ldraw_dir):
    """A kind _faces_for does not know contributes no fill and raises nothing.
    That is how 50950's wall stayed empty; this fails when the next one
    appears instead of waiting for someone to look at a render."""
    import tomllib
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    cfg = tomllib.loads((ROOT / "tests" / "goldens" / "manifest.toml").read_text())
    seen = set()
    for part in cfg["parts"]["unprinted"]:
        shape = occt.build_shape(occt.flatten_part(part, ldraw_dir))
        for face in occt._shape_faces(shape):
            seen.add(BRepAdaptor_Surface(face).GetType())
    handled = set(occt.CURVED_SURFACES) | {occt.GeomAbs_SurfaceType.GeomAbs_Plane}
    assert seen <= handled, f"unhandled surface kinds: {seen - handled}"


def test_boundary_conics_cover_rims_no_drawn_arc_reports(ldraw_dir):
    """The drawn arc ops are already arc-recovery candidates, so this function
    earns its place only through the rims HLR reports as HIDDEN -- which still
    bound a fill, and whose boundary would otherwise re-emit as a fan of
    9-degree chords. 4740's fill fell from 156 L commands to 16."""
    out = occt.flatten_part("4740", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    proj = occt.op_projection(right, up, fwd)

    def key(t):
        return tuple(round(v, 4) for v in t[:6])

    drawn = {key(op[1:7]) for op in res.segs if op[0] == "arc"}
    conics = {key(c) for c in occt._boundary_conics(shape, proj)}
    assert conics - drawn, "every boundary conic is already a drawn arc"
    assert conics <= {key(e) for e in res.ellipses}


def test_a_faceted_dome_shades_as_one_surface(ldraw_dir):
    """3960 sews 822 planes. Toned one at a time they read flat and emit one
    fill element each -- 194 same-color fills against naive's 1, and a dome
    that draws as a disc."""
    out = occt.flatten_part("3960", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    faces = occt.ordered_faces(shape, proj, out)
    planes = [f for f in faces if f["kind"] == "occt-plane"]
    assert len(planes) > 100
    groups = {f["group"] for f in planes}
    assert len(groups) * 10 < len(planes), f"{len(groups)} groups of {len(planes)}"
    assert any("grad_axis" in f or "grad_radial" in f for f in planes)


def test_plane_grouping_unions_only_what_the_part_declares(ldraw_dir):
    """Declared type-5 lines and exact coplanarity, never a dihedral angle:
    an angle test over tessellation is the line explosion this engine exists
    to avoid. Passing no conditional lines must leave the dome shattered."""
    out = occt.flatten_part("3960", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    with_seams = occt.ordered_faces(shape, proj, out)
    bare = occt.ordered_faces(shape, proj, dict(out, **{"5": []}))
    n_with = len({f["group"] for f in with_seams if f["kind"] == "occt-plane"})
    n_bare = len({f["group"] for f in bare if f["kind"] == "occt-plane"})
    assert n_bare > n_with * 5, f"seams changed nothing: {n_bare} vs {n_with}"


def test_wire_points_follow_the_wire_when_an_edge_runs_backwards():
    """A sector's inner arc is a REVERSED edge. Walking it in curve order
    instead of wire order jumps the loop across the sector and the polygon
    self-intersects -- which radius and corner assertions cannot see."""
    face = occt.sector_face(np.zeros(3), np.array([0.0, 1.0, 0.0]),
                            np.array([1.0, 0.0, 0.0]), 3.0, 6.0, math.pi / 2)
    pts = occt._wire_points(occt.BRepTools.OuterWire_s(face))
    step = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    assert step.max() < 3.5      # the radial legs; a wrong-order jump is 4.24


def test_a_grazing_surface_yields_one_cut_not_two_coincident_ones():
    """At exact tangency both root formulas land on the same parameter, and a
    duplicated cut would be a zero-width span."""
    fwd = np.array([0.0, 0.0, 1.0])
    a = np.array([0.0, 0.0, 1.0]); b = np.array([0.0, 1.0, 0.0])
    c = np.array([0.0, 0.0, -1.0])
    assert occt._limb_params(a, b, c, fwd) == [0.0]


def _spans_of(part, ldraw_dir, lat=30.0, long=45.0):
    shape = occt.build_shape(occt.flatten_part(part, ldraw_dir))
    right, up, fwd = hlr.view_basis(lat, long)
    return occt.curved_faces(shape, occt.op_projection(right, up, fwd))


def test_a_full_turn_span_gets_a_radial_gradient(ldraw_dir):
    """Its two ends are the same point, so a linear axis is zero-length and
    SVG paints the last stop: 4740's dish came out #aaaaaa against naive's
    #565656, chosen by sample order rather than by tone."""
    full = [f for f in _spans_of("4740", ldraw_dir) if f["span_deg"] > 359.9]
    assert len(full) == 5
    for f in full:
        assert "grad_axis" not in f
        assert f["grad_radial"]["r"] > 1.0
        us = [u for (u, _), _ in f["grad_samples"]]
        assert max(us) - min(us) > 0.5      # samples span the ring, not a point


def test_a_limb_cut_span_keeps_its_linear_gradient(ldraw_dir):
    cut = [f for f in _spans_of("4740", ldraw_dir) if f["span_deg"] < 359.9]
    assert cut
    for f in cut:
        assert "grad_radial" not in f
        p0, p1 = f["grad_axis"]
        assert math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 1e-6


def test_a_coaxial_stack_of_full_turns_shares_one_ramp(ldraw_dir):
    """A dome is authored as a stack of cones, and a band that ramps on its
    own reads as an onion ring: 4740's dish stepped 215->198->212 across one
    boundary where LDView falls smoothly from 175 to 143."""
    out = occt.flatten_part("4740", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    faces = occt.ordered_faces(shape, occt.op_projection(right, up, fwd), out)
    turns = [f for f in faces if f.get("span_deg", 0) > 359.9]
    stacks = collections.Counter(f["group"] for f in turns if f.get("group"))
    assert any(n > 1 for n in stacks.values())
    for group, n in stacks.items():
        if n < 2:
            continue
        members = [f for f in turns if f.get("group") == group]
        # one shared dict, so trace's def-dedup emits one <radialGradient>
        assert len({id(f["grad_radial"]) for f in members}) == 1
        assert all("grad_axis" not in f for f in members)
    assert all("_turn_ring" not in f for f in faces)
@pytest.mark.parametrize("part", ["4589", "4070", "32062"])
def test_a_fill_boundary_carries_no_sampled_boundary(part, tmp_path, ldraw_dir):
    """A fill boundary must not be a buffer's or a lattice's tessellation.

    Two stages hand a region between elements and used to write their own
    sampling into the fragment. `_stroke_band` buffers every drawn op, and
    its round joins tessellate at ~0.05 px. `_refine_order_clips` sampled
    the region on a 1.2 px grid even between two PLANES, where the answer
    is an exact half-plane. Both put vertices on a boundary no arc
    candidate can absorb, so they cost L commands and draw nothing: these
    three ran 498/719/1377 line commands against naive's 90/110/435, and
    1020 of 32062's 1290 fill segments were shorter than a quarter pixel.

    A sampled boundary leaves a RUN of short segments, which is what this
    measures -- a lone short segment is ordinary geometry. Held only for
    these three, and only for occt. Parts whose refine regions genuinely
    involve a CURVED coverer still run the grid and still carry such runs
    (3941 51, 4019 64), and so does the naive path (32062 18).

    The junction-lens layer is exempt and not an oversight. A lens pocket IS
    a difference against the buffered stroke band (`_ink_lens_pockets`), so
    its boundary is a buffer boundary by construction; it is capped in area,
    must vanish under an opening at half a stroke width, and paints black
    beneath the ink that encloses it. Counting it measures how gnarly the
    pockets are, not whether a surface fill inherited a sampling. `flat3`
    derives every surface tone from part_color, so pure black is the lens
    layer and nothing else.
    """
    from brick_icons.cli import build_parser, _config_from_args, process_one

    out = tmp_path / "occt"
    args = build_parser().parse_args(
        [part, "--engine", "occt", "--format", "svg", "--shading", "outline",
         "--shade-style", "flat3", "--out", str(out)])
    process_one(_config_from_args(args), part, out)

    worst = total = short = 0
    for m in re.finditer(r"<path\b([^>]*)>", (out / f"{part}.svg").read_text()):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', m.group(1)))
        if attrs.get("fill") in (None, "none"):        # fills, not strokes
            continue
        if attrs.get("fill") == "#000000":            # lens layer, see above
            continue
        run, cur = 0, None
        for c in re.finditer(r"([MLAZ])([^MLAZ]*)", attrs.get("d", "")):
            nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", c.group(2))]
            if c.group(1) == "Z" or len(nums) < 2:
                run, cur = 0, None
                continue
            pt = (nums[-2], nums[-1])
            if c.group(1) != "L" or cur is None:
                run = 0                    # an arc or a new subpath breaks it
            else:
                total += 1
                if math.dist(cur, pt) < 0.25:
                    short += 1
                    run += 1
                    worst = max(worst, run)
                else:
                    run = 0
            cur = pt

    assert worst <= 4, (
        f"{part}: {worst} sub-quarter-pixel fill segments in a row "
        f"({short} of {total}) -- a buffer boundary reached the path")


def test_a_part_declaring_no_edge_draws_instead_of_raising(ldraw_dir):
    """1,407 stickers and a few ordinary parts carry faces and not one type-2
    or type-5 line -- `box5-12.dat`, which 185 of them are built on, is named
    "Box with 5 Faces without Any Edges". The engine used to report that
    honestly and draw nothing, which is a blank icon rather than an answer.

    A sticker rather than `5241`, which held this until `8e436a5`: 5241's
    shell was being dropped for an unresolvable subfile, so the part only
    declared no edge because the resolver could not reach the edges it has.
    A specimen whose emptiness depends on a lookup failing is not one."""
    out = occt.flatten_part("003238j", ldraw_dir)
    assert not out.get("2") and not out.get("5")
    right, up = hlr.view_basis(30.0, 65.0)[:2]
    assert occt.visible_segments(out, right, up, 900).segs


def test_the_undeclared_fallback_is_never_consulted_by_a_part_with_edges(
        ldraw_dir, monkeypatch):
    """It may only run where the old code raised. A part that declares an edge
    reaches ops of its own, so the fallback cannot touch what it draws -- which
    is what makes the change byte-safe for the rest of the library."""
    calls = []
    real = occt._undeclared_ops
    monkeypatch.setattr(occt, "_undeclared_ops",
                        lambda comps: (calls.append(1), real(comps))[1])
    right, up = hlr.view_basis(30.0, 65.0)[:2]
    for part in ("3001", "3941", "4740"):
        assert occt.visible_segments(
            occt.flatten_part(part, ldraw_dir), right, up, 900).segs
    assert calls == []


def test_a_part_with_no_geometry_to_read_a_sharp_set_from_still_raises():
    """The fallback reads HLR's sharp set, so it has nothing to offer a part
    that carries no faces. Declaring an edge does not conjure one, and drawing
    an empty icon in silence would hide the fault."""
    with pytest.raises(RuntimeError, match="produced no edges"):
        occt.visible_segments({"2": [(np.zeros(3), np.zeros(3))], "5": [],
                               "tri": [], "tri_meta": [], "analytic": []},
                              np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 900)


def test_an_artwork_line_inside_a_face_does_not_count_as_a_declaration(
        ldraw_dir):
    """6342851a is a box5-12 plate with 8,888 artwork triangles coplanar on its
    top face and two type-2 lines drawn along the artwork. UnifySameDomain
    merges all of it into 6 faces, so both lines sit in the INTERIOR of one and
    match none of HLR's 9 visible edges. Guarding the fallback on the mere
    presence of a type-2 left the part blank."""
    out = occt.flatten_part("6342851a", ldraw_dir)
    right, up = hlr.view_basis(30.0, 65.0)[:2]
    shape = occt.build_shape(out)
    comps = occt.hlr_edges(shape, right, up)
    loci = occt.authored_loci(shape, out, right, up)
    assert out["2"] and not occt.select_authored(comps.get("sharp"), loci)
    assert occt.visible_segments(out, right, up, 900).segs


def test_condlines_alone_do_not_count_as_declaring_an_edge(ldraw_dir):
    """A condline is conditional by construction -- it draws only where its two
    faces straddle the view -- so on a flat plate seen from outside none of them
    qualify and the part is left with no boundary at all. 36 formed stickers and
    their composite siblings sit exactly there: type-5 and no type-2, 26 to 204
    sharp edges from HLR, not one locus matched. Treating type-5 as a
    declaration left every one of them blank."""
    right, up = hlr.view_basis(30.0, 65.0)[:2]
    for part in ("003497bc01", "164325d", "4620856b", "162275dc01"):
        out = occt.flatten_part(part, ldraw_dir)
        assert out["5"] and not out["2"], part
        assert occt.visible_segments(out, right, up, 900).segs, part


def test_an_end_face_hides_the_bore_limb_behind_it(ldraw_dir):
    """79306-f1 is a pneumatic tube: two cylinders and an annulus at each end.
    Its bore's limb runs the whole 40 LDU and every point of it is hidden --
    the far 29 by the outer wall, the near 3 by the end annulus. Sewn into a
    shell those 3 came back visible, two ticks drawn across the annulus, and
    it is orientation that decides it: reversing the shell hides them again.
    So the limbs left are the outer wall's, both full length."""
    out = occt.flatten_part("79306-f1", ldraw_dir)
    right, up = hlr.view_basis(30.0, 45.0)[:2]
    res = occt.visible_segments(out, right, up, 512)
    limbs = sorted(round(float(np.hypot(op[3] - op[1], op[4] - op[2])), 2)
                   for op in res.segs if op[0] == "line" and op[-1] == "sil")
    assert limbs == [31.62, 31.62], limbs


def test_hlr_occludes_with_loose_faces_whatever_the_shell_says(ldraw_dir):
    """The mechanism behind the test above, pinned on its own: HLR drops a
    back-facing occluder once the faces are connected, and sewing leaves this
    part inward. Handed the shell it keeps 2.45 of each bore limb; handed the
    same faces loose, or the shell reversed, it hides them."""
    out = occt.flatten_part("79306-f1", ldraw_dir)
    right, up = hlr.view_basis(30.0, 45.0)[:2]
    shell = occt.build_shape(out)

    def visible_limbs(shape):
        algo = occt.HLRBRep_Algo()
        algo.Add(shape)
        algo.Projector(occt.HLRAlgo_Projector(
            occt.ax2((0.0, 0.0, 0.0), *occt.projector_axes(right, up))))
        algo.Update()
        algo.Hide()
        comp = occt.HLRBRep_HLRToShape(algo).OutLineVCompound()
        return sorted(round(float(np.hypot(op[3] - op[1], op[4] - op[2])), 2)
                      for e in occt._edges_of(comp)
                      for op in occt._edge_ops(e, "sil"))

    assert visible_limbs(shell) == [2.45, 2.45, 31.62, 31.62]
    assert visible_limbs(shell.Reversed()) == [31.62, 31.62]
    assert visible_limbs(occt._loose_faces(shell)) == [31.62, 31.62]


def test_a_unify_that_kills_its_probe_is_counted(monkeypatch):
    """The probe child dies on a SIGSEGV, which leaves a crash report naming
    no part and nothing else. Counting the skip is the only record that this
    part drew with its faces unmerged."""
    from brick_icons import timing

    class _Crashes:
        def __init__(self, *a, **k):
            import os
            import signal
            # SIGKILL rather than a real abort: `_unify_survives` reads
            # WIFEXITED, so any death by signal takes the same branch, and
            # aborting would file a crash report per test run.
            os.kill(os.getpid(), signal.SIGKILL)

    monkeypatch.setattr(occt, "ShapeUpgrade_UnifySameDomain", _Crashes)
    timing.reset()
    try:
        assert occt._unify_survives(occt.TopoDS_Shape()) is False
        assert timing.counts() == {"unify_crash": 1}
    finally:
        timing.reset()


def test_a_unify_that_survives_its_probe_is_not_counted():
    from brick_icons import timing

    timing.reset()
    try:
        assert occt._unify_survives(occt.TopoDS_Shape()) is True
        assert timing.counts() == {}
    finally:
        timing.reset()


def test_a_drawn_circle_is_an_arc_candidate_at_the_facet_step(ldraw_dir):
    """A triangle is sewn into a planar face whose boundary is still the
    authored chord polygon, and an LDraw 16-gon rings a hole in 22.5 deg
    chords -- under geom2d.MAX_STEP 15 those runs stay polylines. occt's own
    surface boundaries sample finer and are appended without a step.
    """
    out = occt.flatten_part("3941", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    drawn = {tuple(round(v, 4) for v in op[1:7])
             for op in res.segs if op[0] == "arc"}
    steps = {round(e[6], 4) for e in res.ellipses
             if len(e) > 6 and tuple(round(v, 4) for v in e[:6]) in drawn}
    assert steps == {occt.RIM_STEP_DEG}
    assert drawn <= {tuple(round(v, 4) for v in e[:6]) for e in res.ellipses}


def test_a_decal_is_not_clipped_by_the_wall_it_is_printed_on(ldraw_dir):
    """A decal is re-projected onto its carrier's exact surface, so its depth
    has to come from that surface too. Fitted an affine plane instead, a panel
    wrapped around a cylinder gets a chord plane that sits BEHIND the body
    facets it is printed on, and the boolean clip in fill_ops then cuts the
    decal away wherever one of them overlaps it: 3941p01 kept 17% of its ink.
    """
    out = occt.flatten_part("3941p01", ldraw_dir)
    # what hlr.visible_segments adds on top of the flatten, and _with_decoration
    # reads: the per-triangle colors and the library's own printed/not verdict
    out["tri_colors"] = [m["color"] for m in out["tri_meta"]]
    out["printed"] = hlr._is_printed(
        hlr._resolve_input("3941p01", hlr.default_roots(ldraw_dir)))
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    faces = occt.ordered_faces(shape, occt.op_projection(right, up, fwd), out)
    deco = [f for f in faces if f.get("color", 16) != 16]
    assert deco, "3941p01 must reach the ordering with its print on it"
    area = lambda f: geom2d.area(geom2d.to_geom(f["poly"], f.get("holes") or []))
    decal = max(deco, key=area)
    at = next(k for k, f in enumerate(faces) if f is decal)
    g = geom2d.to_geom(decal["poly"], decal.get("holes") or [])
    cover = None
    for f in faces[at + 1:]:                       # everything painted later
        gg = geom2d.to_geom(f["poly"], f.get("holes") or [])
        cover = gg if cover is None else geom2d.union(cover, gg)
    hidden = geom2d.area(geom2d.intersection(g, cover)) / geom2d.area(g)
    assert hidden < 0.05, f"{hidden:.0%} of the decal is painted over"
