import math

import numpy as np
import pytest
from brick_icons import shade, hlr
from brick_icons import primitives as P


def _ident_proj():
    # A=x, B=y, Z=z with identity pixel fit: ray_origin(xs, ys) = (xs, ys, 0)
    return P.Projection(np.array([1.0, 0.0, 0.0]), np.array([0.0, -1.0, 0.0]),
                        np.array([0.0, 0.0, 1.0]), 1.0, 0.0, 0.0, 0.0)


def test_cull_self_depth_keeps_own_curved_face():
    """A curved wall face must NOT cull itself: with self-depth taken from its
    OWN occluder at the centroid (not the band mean), and the own-occluder
    excluded from the scan, an isolated wall survives."""
    import numpy as np
    from brick_icons import shade

    class FakeOcc:                       # returns a fixed near depth at any ray
        def __init__(self, d): self.d = d
        def depth(self, O, F): return np.array([self.d], float)

    own = FakeOcc(1.0)                   # wall's near surface at depth 1.0
    face = {"poly": np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float),
            "depth": 5.0, "kind": "cyli"}        # band MEAN is 5.0 (farther)
    kept = shade.cull_occluded_faces(
        [face], occluders=[own], proj=_ident_proj(),
        eps=1e-3, kinds=("tri", "disc", "ring", "cyli"),
        own_occ={id(face): own})
    assert kept == [face]               # not culled by its own near surface


def test_cull_self_depth_removes_occluded_interior_face():
    import numpy as np
    from brick_icons import shade

    class FakeOcc:
        def __init__(self, d): self.d = d
        def depth(self, O, F): return np.array([self.d], float)

    own = FakeOcc(5.0)                   # interior tube near surface at 5.0
    wall = FakeOcc(1.0)                  # outer wall nearer, at 1.0
    face = {"poly": np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float),
            "depth": 5.0, "kind": "cyli"}
    kept = shade.cull_occluded_faces(
        [face], occluders=[own, wall], proj=_ident_proj(), eps=1e-3,
        kinds=("tri", "disc", "ring", "cyli"), own_occ={id(face): own})
    assert kept == []                   # outer wall occludes it -> culled


def test_cull_passthrough_for_untested_kinds():
    """A face whose kind is not in `kinds` passes through untouched."""
    import numpy as np
    from brick_icons import shade
    class FakeOcc:
        def depth(self, O, F): return np.array([0.0], float)   # always nearest
    face = {"poly": np.array([[0, 0], [1, 0], [0, 1]], float),
            "depth": 9.0, "kind": "tri"}
    kept = shade.cull_occluded_faces([face], occluders=[FakeOcc()],
                                     proj=_ident_proj(),
                                     eps=1e-3, kinds=("disc",))   # tri not listed
    assert kept == [face]


def test_faces_from_analytic_cylinder_gradient_and_disc():
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    R = np.eye(3); t = np.zeros(3)
    cyl = P.Cylinder(R=R, t=t, sector=360.0)
    disc = P.Disc(R=R, t=t, sector=360.0)
    faces = shade.faces_from_analytic(
        [cyl, disc], P.Projection(right, up, fwd, 2.0, 0.0, 0.0, 50.0))
    kinds = [f["kind"] for f in faces]
    assert kinds.count("disc") == 1
    # one smooth near wall (not bands) + one interior far wall
    near_walls = [f for f in faces if f["kind"] == "cyli" and not f.get("interior")]
    assert len(near_walls) == 1
    disc_face = next(f for f in faces if f["kind"] == "disc")
    assert disc_face["poly"].shape[1] == 2 and abs(np.linalg.norm(disc_face["normal"]) - 1) < 1e-6
    cyl_face = near_walls[0]
    assert "grad_axis" in cyl_face and len(cyl_face["grad_samples"]) >= 2
    assert cyl_face["poly"].shape[1] == 2


def test_faces_from_analytic_ring_is_annulus_not_solid_disc():
    """A 'ring' primitive (inner radius N, outer N+1) must shade as an annulus
    with the center hole cut out — not a filled disc that covers the bore.
    View is set face-on to the ring so screen radii track world radii."""
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    # ring axis -> camera; U=right, V=up so it projects to a true (annular) circle
    R = np.stack([right, -fwd, up], axis=1)
    ring = P.Ring(R=R, t=np.zeros(3), sector=360.0, inner=2)
    faces = shade.faces_from_analytic(
        [ring], P.Projection(right, up, fwd, 1.0, 0.0, 0.0, 0.0))
    f = next(f for f in faces if f["kind"] == "ring")
    # full sector: outer circle polygon + the bore as a REAL hole ring
    poly, holes = f["poly"], f.get("holes", [])
    assert len(holes) == 1
    assert len(f["zs"]) == len(poly)
    c = poly.mean(axis=0)
    r_out = np.linalg.norm(poly - c, axis=1).mean()
    r_in = np.linalg.norm(holes[0] - c, axis=1).mean()
    assert r_out / r_in > 1.3           # bore clearly separated from rim


def test_ring_partial_sector_keeps_concat_polygon():
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    R = np.stack([right, -fwd, up], axis=1)
    ring = P.Ring(R=R, t=np.zeros(3), sector=90.0, inner=2)
    f = shade.faces_from_analytic(
        [ring], P.Projection(right, up, fwd, 1.0, 0.0, 0.0, 0.0))[0]
    assert not f.get("holes")           # annular sector: simple valid polygon


def test_overlap_witness_respects_holes():
    outer = np.array([(0, 0), (10, 0), (10, 10), (0, 10)], float)
    hole = np.array([(2, 2), (8, 2), (8, 8), (2, 8)], float)
    other = np.array([(4, 4), (6, 4), (6, 6), (4, 6)], float)  # entirely in hole
    assert shade._overlap_witness(outer, other, ha=(hole,)) is None


def test_apply_affine_remaps_holes():
    f = {"poly": np.array([(0, 0), (4, 0), (4, 4)], float),
         "holes": [np.array([(1, 1), (2, 1), (2, 2)], float)],
         "depth": 0.0}
    out = shade.apply_affine_faces([f], 2.0, 1.0, 1.0)[0]
    assert np.allclose(out["holes"][0][0], (3.0, 3.0))


def _cone_prim(N=1, sector=360.0):
    return P.Cone(R=np.eye(3), t=np.zeros(3), sector=sector, top=float(N))


def test_cone_wall_faces_outer_and_interior():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    faces = shade.faces_from_analytic(
        [_cone_prim()], P.Projection(right, up, fwd, 1.0, 0.0, 0.0, 0.0))
    outer = [f for f in faces if not f.get("interior")]
    inner = [f for f in faces if f.get("interior")]
    assert len(outer) == 1 and len(inner) == 1
    assert abs(outer[0]["span_deg"] - 180.0) < 1e-6
    # cone flare: every gradient-sample normal has a positive up-component
    ups = [nv[1] for _, nv in outer[0]["grad_samples"]]
    assert all(u > 0.5 for u in ups)            # (cos,1,sin)/sqrt2 -> up ~ .707


def test_cone_wall_radii_taper():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    f = [x for x in shade.faces_from_analytic(
            [_cone_prim(N=1)], P.Projection(right, up, fwd, 1.0, 0.0, 0.0, 0.0))
         if not x.get("interior")][0]
    xs = np.abs(f["poly"][:, 0])
    assert abs(xs.max() - 2.0) < 1e-6           # base radius N+1


def test_cone_axis_on_view_full_annulus_wall():
    # looking straight down the axis from above the apex: the whole outer wall
    # is visible as an annulus-like band (unlike a cylinder, which shows none).
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 0.0, 1.0])
    fwd = np.array([0.0, -1.0, 0.0])
    faces = shade.faces_from_analytic(
        [_cone_prim()], P.Projection(right, up, fwd, 1.0, 0.0, 0.0, 0.0))
    assert len(faces) == 1 and not faces[0].get("interior")


def test_stacked_cone_walls_merge_into_single_gradient_face():
    """faces_from_analytic on a smooth cone stack must emit ONE outer wall
    face (one path, one gradient) covering the full height — not one strip
    per LDraw primitive with a visible tone step at the joint."""
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    lo = P.Cone(R=np.eye(3), t=np.zeros(3), sector=360.0, top=2.0)
    hi = P.Cone(R=np.eye(3), t=np.array([0.0, 1.0, 0.0]), sector=360.0,
                top=1.0)
    faces = shade.faces_from_analytic(
        [lo, hi], P.Projection(right, up, fwd, 1.0, 0.0, 0.0, 0.0))
    outer = [f for f in faces if not f.get("interior")]
    inner = [f for f in faces if f.get("interior")]
    assert len(outer) == 1 and len(inner) == 1
    f = outer[0]
    assert np.ptp(f["poly"][:, 1]) > 2.0 - 1e-6      # full stack height
    assert abs(np.abs(f["poly"][:, 0]).max() - 3.0) < 1e-6   # base radius
    # one gradient, same 45-degree flare everywhere (equal slope throughout)
    assert "grad_axis" in f
    for _, nv in f["grad_samples"]:
        assert abs(nv[1] - 1 / math.sqrt(2)) < 1e-6


def test_cylinder_wall_faces_unchanged():
    # regression: generalizing helpers must not perturb cylinder output
    prim = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    faces = shade.faces_from_analytic(
        [prim], P.Projection(right, up, fwd, 1.0, 0.0, 0.0, 0.0))
    assert {f.get("interior", False) for f in faces} == {False, True}
    for f in faces:
        assert abs(f["span_deg"] - 180.0) < 1e-6
        for _, nv in f["grad_samples"]:
            assert abs(nv[1]) < 1e-9            # cylinder normals have no up


def test_faces_from_tris_culls_back_and_projects():
    # a single CCW triangle in the z=0 plane (LDraw world)
    tri = np.array([[[0, 0, 0], [10, 0, 0], [0, 10, 0]]], float)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    faces = shade.faces_from_tris(tri, P.Projection(right, up, fwd,
                                                    2.0, 0.0, 0.0, 50.0))
    assert len(faces) in (0, 1)
    for f in faces:
        assert f["poly"].shape == (3, 2)
        assert abs(np.linalg.norm(f["normal"]) - 1.0) < 1e-6
        assert np.isfinite(f["depth"])
        assert f["kind"] == "tri"


def test_faces_from_tris_culls_backface_no_flip():
    """A triangle whose outward normal points AWAY from the camera is dropped,
    not flipped up into a bright top tone. Winding is now trusted."""
    import numpy as np
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    # Build a tri whose geometric normal points along +fwd (away from camera).
    # cross(v1-v0, v2-v0) should be ~ +fwd.
    v0 = np.zeros(3)
    v1 = right * 10.0
    v2 = np.cross(fwd, right) * 10.0        # so cross(v1,v2) proportional to fwd
    tri = np.array([[v0, v1, v2]], float)
    n = np.cross(v1 - v0, v2 - v0); n /= np.linalg.norm(n)
    assert n @ fwd > 0.5                      # confirm it's a back-face
    faces = shade.faces_from_tris(tri, P.Projection(right, up, fwd,
                                                    2.0, 0.0, 0.0, 50.0))
    assert faces == []                        # culled, not flipped


def test_group_ids_stamped_on_all_tri_faces():
    # two coplanar tris sharing an edge + one lone off-plane tri; all three
    # must be camera-facing so all three survive the back-face cull
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    tris = []
    for cand in ([[0, 0, 0], [10, 0, 0], [0, 10, 0]],
                 [[10, 0, 0], [10, 10, 0], [0, 10, 0]],
                 [[50, 0, 10], [60, 0, 20], [50, 10, 30]]):
        v = np.array(cand, float)
        n = np.cross(v[1] - v[0], v[2] - v[0])
        if np.array([n @ right, n @ up, n @ fwd])[2] > 0:
            v = v[::-1]                          # flip to face the camera
        tris.append(v)
    faces = shade.faces_from_tris(np.array(tris),
                                  P.Projection(right, up, fwd,
                                               1.0, 0.0, 0.0, 0.0),
                                  cond_edges=np.zeros((0, 4, 3)))
    assert len(faces) == 3
    assert all("group" in f for f in faces)
    coplanar = [faces[0], faces[1]]
    assert coplanar[0]["group"] == coplanar[1]["group"]
    assert faces[2]["group"] != faces[0]["group"]


def test_flat3_tone_by_orientation():
    from brick_icons import shade
    style = shade.Flat3Style(part_color=(160, 160, 160))
    top = style.tone(np.array([0.0, 1.0, -0.1]))
    left = style.tone(np.array([-1.0, 0.0, -0.1]))
    right = style.tone(np.array([1.0, 0.0, -0.1]))
    assert top != left != right and top != right
    def lum(h): return int(h[1:3], 16)
    assert lum(top) > lum(left) > lum(right)


def test_parse_hex_color():
    from brick_icons import shade
    assert shade.parse_hex_color("0xFF8040") == (255, 128, 64)
    assert shade.parse_hex_color("#00ff00") == (0, 255, 0)
    assert shade.parse_hex_color(None) == (157, 157, 157)
    assert shade.parse_hex_color("nonsense") == (157, 157, 157)


def test_fill_ops_painter_sorted_back_to_front():
    from brick_icons import shade
    style = shade.Flat3Style()
    faces = [
        {"poly": np.array([[0, 0], [10, 0], [10, 10], [0, 10]]),
         "normal": np.array([0, 1, -1.0]), "depth": 5.0, "kind": "tri"},   # far
        {"poly": np.array([[5, 0], [15, 0], [15, 10], [5, 10]]),
         "normal": np.array([0, 1, -1.0]), "depth": 1.0, "kind": "tri"},   # near
    ]
    ops = shade.fill_ops(faces, style)
    assert [o["depth"] for o in ops] == [5.0, 1.0]   # far first
    assert "d" in ops[0] and ops[0]["fill"].startswith("#")


def test_fill_ops_unified_depth_sort_across_kinds():
    """Occlusion is by depth, NOT by flat-vs-curved: emission stays a single
    far->near sequence across all kinds (disjoint polys, so all survive)."""
    from brick_icons import shade
    style = shade.Flat3Style()
    n = np.array([0.0, 1.0, -1.0])

    def poly(ox):
        return np.array([[ox, 0], [ox + 8, 0], [ox, 8]], float)

    faces = [
        {"poly": poly(0), "normal": n, "depth": 2.0, "kind": "tri"},
        {"poly": poly(20), "normal": n, "depth": 5.0, "kind": "disc"},
        {"poly": poly(40), "normal": n, "depth": 1.0, "kind": "disc"},
    ]
    ops = shade.fill_ops(faces, style)
    assert [o["depth"] for o in ops] == [5.0, 2.0, 1.0]   # strictly far->near, kind-agnostic


def _flat_face(x0, y0, x1, y1, order, depth, normal=(0, 1, -0.5), group=None):
    f = {"poly": np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], float),
         "normal": np.array(normal, float), "depth": float(depth),
         "order": order, "kind": "tri"}
    if group is not None:
        f["group"] = group
    return f


def test_fill_ops_drops_fully_hidden_face():
    far = _flat_face(2, 2, 8, 8, order=0, depth=10.0)
    near = _flat_face(0, 0, 10, 10, order=1, depth=1.0)
    ops = shade.fill_ops([far, near], shade.Flat3Style())
    assert len(ops) == 1 and ops[0]["depth"] == 1.0


def test_fill_ops_clips_partial_overlap():
    far = _flat_face(0, 0, 10, 10, order=0, depth=10.0)
    near = _flat_face(5, 0, 15, 10, order=1, depth=1.0)
    ops = shade.fill_ops([far, near], shade.Flat3Style())
    assert len(ops) == 2
    far_op = ops[0]                                # farthest emitted first
    toks = far_op["d"].replace("M", " ").replace("L", " ").replace("Z", " ").split()
    xs = [float(t) for t in toks[0::2]]
    assert max(xs) <= 5.0 + 1e-6                   # clipped at the near face


def test_fill_ops_clip_false_keeps_hidden_faces_far_to_near():
    far = _flat_face(2, 2, 8, 8, order=0, depth=10.0)
    near = _flat_face(0, 0, 10, 10, order=1, depth=1.0)
    ops = shade.fill_ops([far, near], shade.Flat3Style(), clip=False)
    # translucent mode: the fully-covered face survives, whole, painted first
    assert [op["depth"] for op in ops] == [10.0, 1.0]
    toks = ops[0]["d"].replace("M", " ").replace("L", " ").replace("Z", " ").split()
    xs = [float(t) for t in toks[0::2]]
    assert min(xs) == pytest.approx(2.0) and max(xs) == pytest.approx(8.0)


def test_fill_ops_merges_group_into_one_op():
    kw = dict(depth=5.0, group=7)
    fs = [_flat_face(0, 0, 4, 4, order=0, **kw),
          _flat_face(4, 0, 8, 4, order=1, **kw),
          _flat_face(0, 4, 8, 8, order=2, **kw)]   # T-junction against the first two
    ops = shade.fill_ops(fs, shade.Flat3Style())
    assert len(ops) == 1
    assert ops[0]["d"].count("M ") == 1            # a single merged region


def test_fill_ops_group_gradient_kept():
    ga = ((0.0, 0.0), (8.0, 0.0))
    samples = [(0.0, np.array([0, 0, -1.0])), (1.0, np.array([0.6, 0, -0.8]))]
    fs = []
    for i, (x0, x1) in enumerate([(0, 4), (4, 8)]):
        f = _flat_face(x0, 0, x1, 4, order=i, depth=5.0, group=3)
        f["grad_axis"] = ga
        f["grad_samples"] = samples
        fs.append(f)
    ops = shade.fill_ops(fs, shade.Flat3Style())
    assert len(ops) == 1 and "gradient" in ops[0]
    assert len(ops[0]["gradient"]["stops"]) == 2


def test_fill_ops_tiny_slivers_dropped():
    far = _flat_face(0, 0, 10, 10, order=0, depth=10.0)
    near = _flat_face(0.01, 0.01, 10, 10, order=1, depth=1.0)  # covers all but a sliver
    ops = shade.fill_ops([far, near], shade.Flat3Style())
    assert len(ops) == 1


def test_highlights_are_gone():
    """Highlights were removed as a feature: no ops, no CLI/config surface."""
    from brick_icons import shade, config
    assert not hasattr(shade, "highlight_ops")
    assert not hasattr(shade, "remap_highlights")
    assert "highlights" not in config.DEFAULTS
    assert "highlight_strength" not in config.DEFAULTS


def test_light_vector_conventions():
    """--light LAT,LONG in VIEW space: LAT = elevation above the view
    horizon, LONG = azimuth (0 = from the viewer, positive = from the
    viewer's left)."""
    v = shade.light_vector("90,0")
    assert np.allclose(v, [0.0, 1.0, 0.0], atol=1e-9)      # straight overhead
    v = shade.light_vector("0,0")
    assert np.allclose(v, [0.0, 0.0, -1.0], atol=1e-9)     # frontal
    v = shade.light_vector("0,90")
    assert np.allclose(v, [-1.0, 0.0, 0.0], atol=1e-9)     # from viewer's left


def test_flat3_default_light_and_tones_unchanged():
    st = shade.Flat3Style()
    assert st.tone(np.array([0.0, 1.0, 0.0])) == st.top
    assert st.tone(np.array([-0.7, 0.0, -0.7])) == st.left
    assert st.tone(np.array([0.7, 0.0, -0.7])) == st.right
    assert st.top == shade._hex([157 * 1.30] * 3)
    assert st.left == shade._hex([157 * 0.85] * 3)          # left brighter
    assert st.right == shade._hex([157 * 0.60] * 3)
    assert st.light[0] < 0                                  # upper-LEFT default


def test_flat3_light_from_right_swaps_bright_side():
    st = shade.Flat3Style(light=shade.light_vector("37,-39"))
    bright, dark = shade._hex([157 * 0.85] * 3), shade._hex([157 * 0.60] * 3)
    assert st.tone(np.array([0.7, 0.0, -0.7])) == bright    # lit side now right
    assert st.tone(np.array([-0.7, 0.0, -0.7])) == dark
    # curved ramp follows the same light
    assert st.ramp(np.array([0.6, 0.4, -0.6])) != shade.Flat3Style().ramp(
        np.array([0.6, 0.4, -0.6]))


def test_make_style_accepts_light_spec():
    st = shade.make_style("flat3", light="0,-90")
    assert st.light[0] > 0.99                               # from viewer's right


def test_cull_multisample_keeps_face_with_occluded_centroid():
    """A small near feature (stud) covering only the CENTROID of a big face
    must not cull the whole face: 3001's top quad-tris have centroids inside
    stud footprints. Cull requires EVERY sample occluded, not just one."""
    import numpy as np
    from brick_icons import shade

    class StudOcc:                       # occludes only a small spot at (50,50)
        def depth(self, O, F):
            d = np.hypot(O[:, 0] - 50.0, O[:, 1] - 50.0)
            return np.where(d < 10.0, 1.0, np.inf)

    face = {"poly": np.array([[0, 0], [100, 0], [100, 100], [0, 100]], float),
            "depth": 5.0, "zs": np.full(4, 5.0), "kind": "tri"}
    kept = shade.cull_occluded_faces(
        [face], occluders=[StudOcc()], proj=_ident_proj(), eps=1e-3)
    assert kept == [face]                # corners visible -> face survives


def test_cull_multisample_still_removes_fully_hidden_face():
    """All samples behind a big wall -> culled (the sliver case must not
    regress from multi-sampling)."""
    import numpy as np
    from brick_icons import shade

    class WallOcc:                       # nearer everywhere
        def depth(self, O, F):
            return np.full(O.shape[0], 1.0)

    face = {"poly": np.array([[0, 0], [100, 0], [100, 100], [0, 100]], float),
            "depth": 5.0, "zs": np.full(4, 5.0), "kind": "tri"}
    kept = shade.cull_occluded_faces(
        [face], occluders=[WallOcc()], proj=_ident_proj(), eps=1e-3)
    assert kept == []


def test_cyl_wall_partial_sector_wrapping_arc_emits_both_spans():
    """A 270-degree tube oriented so the camera-facing arc wraps past 0 must
    emit BOTH visible wall spans (old naive clamp lost the wrapped piece —
    4019's void pixels traced to exactly this)."""
    import math
    import numpy as np
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(0.0, 0.0)
    g = math.radians(-30.0)          # theta_face = 270 - g = 300 degrees
    U = np.array([math.cos(g), 0.0, math.sin(g)])
    V = np.array([-math.sin(g), 0.0, math.cos(g)])
    A = np.array([0.0, -1.0, 0.0])
    R = np.stack([U, A, V], axis=1)
    cyl = P.Cylinder(R=R, t=np.zeros(3), sector=270.0)
    faces = shade.faces_from_analytic(
        [cyl], P.Projection(right, up, fwd, 2.0, 0.0, 0.0, 50.0))
    near = [f for f in faces if f["kind"] == "cyli" and not f.get("interior")]
    # visible arc [210,390] ∩ sector [0,270] = [210,270] + [0,30]
    assert len(near) == 2
    total = sum(f["span_deg"] for f in near)
    assert abs(total - 90.0) < 1.0


def test_cyl_interior_far_wall_emitted_for_open_tubes():
    """Looking into an open tube you see its far interior wall; that half must
    be emitted (flagged interior, camera-facing normals) instead of leaving
    white voids (4019 hub/pin tubes)."""
    import numpy as np
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    cyl = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    faces = shade.faces_from_analytic(
        [cyl], P.Projection(right, up, fwd, 2.0, 0.0, 0.0, 50.0))
    near = [f for f in faces if f["kind"] == "cyli" and not f.get("interior")]
    inner = [f for f in faces if f["kind"] == "cyli" and f.get("interior")]
    assert len(near) == 1 and len(inner) == 1
    assert abs(inner[0]["span_deg"] - 180.0) < 1.0
    # interior gradient samples face the camera (nv z-component < 0)
    assert all(nv[2] < 1e-6 for _, nv in inner[0]["grad_samples"])


def test_order_faces_witness_depth_beats_mean_depth():
    """The classic painter failure: a big sloped face whose MEAN depth is
    nearer than a small stud's, but which is FARTHER at their actual overlap.
    Witness-depth ordering must paint the big face first (multi-stud plate
    streaks came from exactly this)."""
    import numpy as np
    from brick_icons import shade
    big = {"poly": np.array([[0, 0], [100, 0], [100, 20], [0, 20]], float),
           "zs": np.array([0.0, 10.0, 10.0, 0.0]),     # depth 0 at x=0 -> 10 at x=100
           "depth": 5.0, "kind": "tri", "normal": np.array([0, 1, -1.0])}
    stud = {"poly": np.array([[85, 5], [95, 5], [95, 15], [85, 15]], float),
            "zs": np.full(4, 7.0),                     # locally NEARER than big (~9)
            "depth": 7.0, "kind": "tri", "normal": np.array([0, 1, -1.0])}
    out = shade.order_faces([stud, big], eps=1e-3)
    assert out[0] is big and out[1] is stud            # farther-at-witness first
    assert big["order"] < stud["order"]


def test_order_faces_disjoint_fall_back_to_depth():
    import numpy as np
    from brick_icons import shade
    near = {"poly": np.array([[0, 0], [10, 0], [0, 10]], float),
            "depth": 1.0, "kind": "tri", "normal": np.array([0, 1, -1.0])}
    far = {"poly": np.array([[50, 50], [60, 50], [50, 60]], float),
           "depth": 9.0, "kind": "tri", "normal": np.array([0, 1, -1.0])}
    out = shade.order_faces([near, far], eps=1e-3)
    assert out[0] is far and out[1] is near


def test_order_faces_cycle_break_releases_cycle_member_not_bystander():
    """When the witness graph has a genuine paint cycle, the stall-breaker
    must force-release a member of the blocking cycle — NOT the globally
    deepest remaining face. Releasing a bystander violates its direct
    constraints: 3960's far-rim dome facets were released ahead of the rim's
    interior far wall (their mean depth exceeded the wall's) and got clipped
    behind it, leaving a dark band with a sawtooth boundary."""
    import numpy as np
    from brick_icons import shade
    n = np.array([0.0, 1.0, -1.0])

    def strip(p, q, into, zlo=10.0, zhi=90.0, w=8.0):
        p, q, into = np.asarray(p, float), np.asarray(q, float), np.asarray(into, float)
        poly = np.array([p, q, q + w * into, p + w * into])
        return {"poly": poly, "zs": np.array([zlo, zhi, zhi, zlo]),
                "depth": (zlo + zhi) / 2, "kind": "tri", "normal": n}

    # three strips along a triangle's sides, each near at its start corner and
    # far at its end corner -> pairwise witness depths form a 3-cycle A>B>C>A
    P1, P2, P3 = (0.0, 0.0), (100.0, 0.0), (50.0, 86.0)
    A = strip(P1, P2, (0.0, 1.0))
    B = strip(P2, P3, (-0.865, -0.503))
    C = strip(P3, P1, (0.865, -0.503))
    # innocent bystander: overlaps only A, locally NEARER than A (A must paint
    # first), but with the deepest MEAN depth of all faces
    D = {"poly": np.array([[46, 2], [54, 2], [54, 6], [46, 6]], float),
         "zs": np.full(4, 40.0), "depth": 1000.0, "kind": "tri", "normal": n}
    faces = [A, B, C, D]
    shade.order_faces(faces, eps=1e-3)
    assert A["order"] < D["order"]          # direct constraint survives the cycle


def test_fill_ops_respects_stamped_order():
    """When faces carry an 'order' stamp (witness-ordered upstream), fill_ops
    must NOT re-sort by mean depth."""
    import numpy as np
    from brick_icons import shade
    style = shade.Flat3Style()
    n = np.array([0.0, 1.0, -1.0])
    a = {"poly": np.array([[0, 0], [8, 0], [0, 8]]), "normal": n,
         "depth": 1.0, "kind": "tri", "order": 0}     # near but painted FIRST
    b = {"poly": np.array([[20, 0], [28, 0], [20, 8]]), "normal": n,
         "depth": 5.0, "kind": "tri", "order": 1}
    ops = shade.fill_ops([b, a], style)
    assert [o["depth"] for o in ops] == [1.0, 5.0]


def _curved_strip(right, up, fwd):
    """3 quads (6 tris) bent around the X axis + their 2 interior seam edges,
    wound to face the camera. Mimics 50950's faceted curved top."""
    import math
    import numpy as np
    thetas = [math.radians(a) for a in (0, 30, 60, 90)]
    ring = [np.array([[x, -10 * math.cos(t), 10 * math.sin(t)] for x in (0, 20)])
            for t in thetas]
    tris, seams = [], []
    for a, b in zip(ring, ring[1:]):
        quad = [a[0], a[1], b[1], b[0]]
        for tri in ([quad[0], quad[1], quad[2]], [quad[0], quad[2], quad[3]]):
            v = np.array(tri, float)
            n = np.cross(v[1] - v[0], v[2] - v[0])
            if n @ fwd > 0:
                v = v[[0, 2, 1]]
            tris.append(v)
    for mid in ring[1:-1]:
        seams.append(np.array([mid[0], mid[1], mid[0], mid[1]], float))
    return np.array(tris), seams


def _dome_mesh(fwd):
    """Spherical-cap tessellation (2 rings x 8 sectors + apex fan) whose
    facet normals spread in TWO directions, with every edge seam-marked."""
    R = 30.0
    def ring(polar_deg):
        p = math.radians(polar_deg)
        return [np.array([R * math.sin(p) * math.cos(a),
                          R * math.sin(p) * math.sin(a),
                          R * math.cos(p)])
                for a in np.linspace(0, 2 * math.pi, 9)[:-1]]
    apex = np.array([0.0, 0.0, R])
    r1, r2 = ring(20), ring(45)
    tris, seams = [], []
    for i in range(8):
        j = (i + 1) % 8
        tris.append([apex, r1[i], r1[j]])
        tris.append([r1[i], r2[i], r2[j]])
        tris.append([r1[i], r2[j], r1[j]])
    out = []
    for t in tris:
        v = np.array(t, float)
        n = np.cross(v[1] - v[0], v[2] - v[0])
        if n @ fwd > 0:
            v = v[[0, 2, 1]]
        out.append(v)
        for a, b in ((v[0], v[1]), (v[1], v[2]), (v[2], v[0])):
            seams.append(np.array([a, b, a, b], float))
    return np.array(out), seams


def test_smooth_group_gradient_axis_follows_normal_variation():
    """The linear gradient axis must run along the direction the NORMALS
    change (the curve direction), not the footprint's long axis. A wide,
    short curved strip (cylinder section about the x-axis, 80 wide x 20
    tall) has its footprint long axis ACROSS the rulings; shading along it
    would put different tones at equal offsets."""
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    R = 30.0
    xs = np.linspace(0.0, 80.0, 5)
    phis = np.radians(np.linspace(-20.0, 20.0, 3))
    pt = lambda x, ph: np.array([x, R * math.sin(ph), R * math.cos(ph)])
    tris, seams = [], []
    for i in range(len(xs) - 1):
        for j in range(len(phis) - 1):
            a, b = pt(xs[i], phis[j]), pt(xs[i + 1], phis[j])
            c, d = pt(xs[i + 1], phis[j + 1]), pt(xs[i], phis[j + 1])
            for t in ([a, b, c], [a, c, d]):
                v = np.array(t, float)
                n = np.cross(v[1] - v[0], v[2] - v[0])
                if n @ fwd > 0:
                    v = v[[0, 2, 1]]
                tris.append(v)
                for e0, e1 in ((v[0], v[1]), (v[1], v[2]), (v[2], v[0])):
                    seams.append(np.array([e0, e1, e0, e1], float))
    faces = shade.faces_from_tris(np.array(tris),
                                  P.Projection(right, up, fwd,
                                               1.0, 0.0, 0.0, 0.0),
                                  cond_edges=seams)
    f = next(f for f in faces if "grad_axis" in f)
    (x0, y0), (x1, y1) = f["grad_axis"]
    assert abs(y1 - y0) > abs(x1 - x0)   # along the curve, not the width


def test_dome_group_gets_radial_gradient():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    tris, seams = _dome_mesh(fwd)
    faces = shade.faces_from_tris(tris, P.Projection(right, up, fwd,
                                                     1.0, 0.0, 0.0, 0.0),
                                  cond_edges=seams)
    grads = [f for f in faces if "grad_radial" in f]
    assert len(grads) == len(faces) and len(faces) >= 20
    assert not any("grad_axis" in f for f in faces)
    g = grads[0]["grad_radial"]
    assert g["r"] > 0 and 0.5 < g["ratio"] < 2.0
    # apex facets sample near the center, rim facets near the unit circle
    ts = [math.hypot(*p) for p, _ in grads[0]["grad_samples"]]
    assert min(ts) < 0.35 and max(ts) > 0.7


def _sphere_band(*polars, R=30.0):
    """Rings of quads (as tris) on a sphere around +z between successive
    polar angles, wound OUTWARD, every edge listed as a seam. Facets past
    polar 90deg are back-facing when viewed along -z."""
    def ring(polar_deg):
        p = math.radians(polar_deg)
        return [np.array([R * math.sin(p) * math.cos(a),
                          R * math.sin(p) * math.sin(a),
                          R * math.cos(p)])
                for a in np.linspace(0, 2 * math.pi, 9)[:-1]]
    tris, seams = [], []
    rings = [ring(p) for p in polars]
    for r1, r2 in zip(rings, rings[1:]):
        for i in range(8):
            j = (i + 1) % 8
            for t in ([r1[i], r2[i], r2[j]], [r1[i], r2[j], r1[j]]):
                v = np.array(t, float)
                n = np.cross(v[1] - v[0], v[2] - v[0])
                if n @ v.mean(axis=0) < 0:      # outward winding
                    v = v[[0, 2, 1]]
                tris.append(v)
                for a, b in ((v[0], v[1]), (v[1], v[2]), (v[2], v[0])):
                    seams.append(np.array([a, b, a, b], float))
    return np.array(tris), seams


def test_backfill_extends_smooth_group_past_fold():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    # front band (polar 60..80) + back band (100..120) joined via the fold
    # ring at 90: fold at 90deg
    tris, seams = _sphere_band(60, 80, 100, 120)
    faces = shade.faces_from_tris(tris, P.Projection(right, up, fwd,
                                                     1.0, 0.0, 0.0, 0.0),
                                  cond_edges=seams)
    backs = [f for f in faces if f.get("backfill")]
    fronts = [f for f in faces if not f.get("backfill")]
    assert backs and fronts                     # fold spillover kept
    assert {f["group"] for f in backs} <= {f["group"] for f in fronts}
    assert all("grad_axis" in f or "grad_radial" in f for f in backs)
    # gradient samples come from front members only
    g = fronts[0]
    n_samples = len(g["grad_samples"])
    assert n_samples == len(fronts)


def test_all_back_group_still_dropped():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    tris, seams = _sphere_band(120, 135, 150)   # entirely past the fold
    faces = shade.faces_from_tris(tris, P.Projection(right, up, fwd,
                                                     1.0, 0.0, 0.0, 0.0),
                                  cond_edges=seams)
    assert faces == []


def test_fill_ops_radial_gradient_op():
    spec = {"cx": 50.0, "cy": 50.0, "r": 40.0, "ratio": 0.8}
    # brightest normal (facing the upper-left light) sits at (-0.6, -0.5);
    # a dim, near-edge-on normal at (0.7, 0.6)
    samples = [((-0.6, -0.5), np.array([-0.4, 0.5, -0.77])),
               ((0.0, 0.0), np.array([0, 0.2, -0.98])),
               ((0.7, 0.6), np.array([0.9, -0.3, -0.32]))]
    f = {"poly": np.array([(10, 10), (90, 10), (90, 90), (10, 90)], float),
         "normal": np.array([0, 0, -1.0]), "depth": 5.0, "kind": "tri",
         "order": 0, "grad_radial": spec, "grad_samples": samples}
    ops = shade.fill_ops([f], shade.Flat3Style())
    assert len(ops) == 1
    g = ops[0]["gradient"]
    assert g["type"] == "radial" and g["r"] == 40.0
    offs = [o for o, _ in g["stops"]]
    assert offs[0] == 0.0 and offs[-1] == 1.0 and offs == sorted(offs)
    # focal pulled toward the brightest sample (upper-left), inside r=1
    assert g["fx"] < -0.2 and g["fy"] < -0.15
    assert math.hypot(g["fx"], g["fy"]) <= 0.7 + 1e-9
    # darkest stop at the far end (edge-on normal), lightest near the focal
    def lum(c):
        return int(c[1:3], 16)
    assert lum(g["stops"][0][1]) > lum(g["stops"][-1][1])


def test_apply_affine_remaps_radial_spec():
    f = {"poly": np.array([(0, 0), (4, 0), (4, 4)], float), "depth": 0.0,
         "grad_radial": {"cx": 10.0, "cy": 20.0, "r": 5.0, "ratio": 0.8},
         "grad_samples": []}
    out = shade.apply_affine_faces([f], 2.0, 1.0, 3.0)[0]
    g = out["grad_radial"]
    assert (g["cx"], g["cy"], g["r"], g["ratio"]) == (21.0, 43.0, 10.0, 0.8)


def test_smooth_group_shares_one_gradient_across_facets():
    """Facets joined by conditional-line edges must all carry the SAME
    gradient (axis + stops) so the curve shades seamlessly; an unrelated
    flat tri keeps its flat tone (no gradient)."""
    import numpy as np
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    tris, seams = _curved_strip(right, up, fwd)
    flat = np.array([[100, 0, 100], [110, 0, 100], [100, 0, 110]], float)
    n = np.cross(flat[1] - flat[0], flat[2] - flat[0])
    if n @ fwd > 0:
        flat = flat[[0, 2, 1]]
    allt = np.concatenate([tris, flat[None]], axis=0)
    faces = shade.faces_from_tris(allt, P.Projection(right, up, fwd,
                                                     2.0, 0.0, 0.0, 200.0),
                                  cond_edges=seams)
    grads = [f for f in faces if "grad_axis" in f]
    flats = [f for f in faces if "grad_axis" not in f]
    assert len(grads) >= 4                      # the curved strip grouped
    assert len(flats) >= 1                      # unrelated tri untouched
    ax0 = grads[0]["grad_axis"]
    assert all(g["grad_axis"] == ax0 for g in grads)          # shared axis
    assert all(g["grad_samples"] is grads[0]["grad_samples"] for g in grads)
    offs = [o for o, _ in grads[0]["grad_samples"]]
    assert len(set(round(o, 3) for o in offs)) >= 2           # real ramp


def test_refine_order_clips_restores_pass_through_victim():
    # Two coplanar-screen squares whose scalar paint order contradicts true
    # depth (a pass-through face gets ordered nearer): the scalar clip hands
    # the whole overlap to the impostor; refinement gives it back.
    near = {"poly": np.array([(0., 0.), (10., 0.), (10., 10.), (0., 10.)]),
            "zs": np.array([-5.0] * 4), "depth": -5.0, "kind": "tri",
            "normal": np.array([0.0, 0.0, -1.0]), "order": 0}
    impostor = {"poly": np.array([(0., 0.), (10., 0.), (10., 10.), (0., 10.)]),
                "zs": np.array([5.0] * 4), "depth": 5.0, "kind": "tri",
                "normal": np.array([0.0, 0.0, -1.0]), "order": 1}
    ops = shade.fill_ops([near, impostor], shade.Flat3Style())
    assert len(ops) == 1 and ops[0]["depth"] == -5.0   # true front face wins


def test_silhouette_geom_unions_all_faces():
    from brick_icons import geom2d
    faces = [{"poly": np.array([(0, 0), (10, 0), (10, 10), (0, 10)], float),
              "depth": 0.0, "normal": 0.5},
             {"poly": np.array([(10, 0), (20, 0), (20, 10), (10, 10)], float),
              "depth": 1.0, "normal": 0.5}]
    g = shade.silhouette_geom(faces)
    assert g.geom_type == "Polygon"
    assert abs(geom2d.area(g) - 200.0) < 1e-6


def _ellipse_ring(op, n=360):
    ts = np.radians(np.linspace(0.0, 360.0, n, endpoint=False))
    return np.stack([op[1] + np.cos(ts) * op[3] + np.sin(ts) * op[5],
                     op[2] + np.cos(ts) * op[4] + np.sin(ts) * op[6]], axis=1)


def _refit_scene():
    # canvas-space counterbore trio (same layout as tests/test_hlr.py):
    # F opening, B bore, M old separator; annulus = M - B, wall = F - M
    F = ("arc", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 360.0, "sil")
    B = ("arc", 0.0, 0.15, 0.55, 0.0, 0.0, 0.55, 195.0, 345.0, "sil")
    M = ("arc", 0.0, 0.30, 1.0, 0.0, 0.0, 1.0, 190.0, 350.0, "sil")
    (_, _, new), refits = hlr._snap_rim_crossings([F, B, M])
    from brick_icons import geom2d
    annulus = geom2d.difference(geom2d.to_geom(_ellipse_ring(M)),
                                geom2d.to_geom(_ellipse_ring(B)))
    wall = geom2d.difference(geom2d.to_geom(_ellipse_ring(F)),
                             geom2d.to_geom(_ellipse_ring(M)))
    return annulus, wall, refits


def test_refit_fill_boundaries_swaps_seam_region():
    from shapely import Point
    from brick_icons import geom2d
    annulus, wall, refits = _refit_scene()
    out = shade.refit_fill_boundaries({0: annulus, 1: wall}, refits)

    # tail probe: between the old separator and the refit arc — was annulus,
    # must now shade as wall
    th = math.radians(210.0)
    tail = Point(0.98 * math.cos(th), 0.30 + 0.98 * math.sin(th))
    assert annulus.contains(tail) and not wall.contains(tail)
    assert out[1].contains(tail) and not out[0].contains(tail)

    # apex-side probe inside the refit arc stays annulus
    keep = Point(0.0, -0.645)
    assert out[0].contains(keep) and not out[1].contains(keep)

    # the swap moves area between the two regions; none is lost
    before = geom2d.area(annulus) + geom2d.area(wall)
    after = geom2d.area(out[0]) + geom2d.area(out[1])
    assert after == pytest.approx(before, rel=1e-3)

    # boolean seams must not leave pinhole rings (they bloat the SVG into
    # dozens of degenerate subpaths — the tick-mark class of artifact)
    import shapely
    for g in out.values():
        for p in getattr(g, "geoms", [g]):
            assert all(abs(shapely.Polygon(r).area) > 1e-4
                       for r in p.interiors)


def test_fill_ops_seam_follows_refits():
    if not hlr.Path("vendor/ldraw").exists():
        pytest.skip("LDraw library absent")
    res = hlr.visible_segments("3700", "vendor/ldraw", lat=30, long=45,
                               render_px=900)
    assert res.refits
    style = shade.make_style("flat3")
    base = shade.fill_ops(res.faces, style, clip=True, ellipses=res.ellipses,
                          proj=res.proj, fit=(1.0, 0.0, 0.0))
    moved = shade.fill_ops(res.faces, style, clip=True, ellipses=res.ellipses,
                           proj=res.proj, fit=(1.0, 0.0, 0.0),
                           refits=res.refits)
    assert len(moved) == len(base)
    assert moved != base


def _flat_wall_proj():
    right, up = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
    fwd = np.array([0.0, 0.0, -1.0])
    return P.Projection(right, up, fwd, 1.0, 0.0, 0.0, 0.0)


def _quad(x0, y0, x1, y1, z=0.0):
    a, b = np.array([x0, y0, z]), np.array([x1, y0, z])
    c, d = np.array([x1, y1, z]), np.array([x0, y1, z])
    return [np.array([a, b, c]), np.array([a, c, d])]


def test_coplanar_tjunction_tiles_merge_to_one_fill():
    # HANDOFF: coplanar merge miss. LDraw subparts tile a flat wall with
    # mismatched subdivisions: tiles abut along collinear boundaries with NO
    # shared edge (T-junctions), so edge-adjacency grouping can't union them
    # and the wall emits as several same-tone fills whose antialiased joints
    # read as faint seams at label sizes (3700's side face). Same-plane flat
    # faces must merge into ONE fill element.
    tris = _quad(0, 0, 10, 10) + _quad(10, 0, 20, 5) + _quad(10, 5, 20, 10)
    faces = shade.faces_from_tris(np.array(tris), _flat_wall_proj())
    assert len(faces) == 6
    ops = shade.fill_ops(faces, shade.Flat3Style())
    assert len(ops) == 1


def test_parallel_planes_stay_separate_fills():
    # same normal but different carrier plane = different surface: the
    # plane-identity merge must not fuse offset parallel walls
    tris = _quad(0, 0, 10, 10, z=0.0) + _quad(30, 0, 40, 10, z=5.0)
    faces = shade.faces_from_tris(np.array(tris), _flat_wall_proj())
    ops = shade.fill_ops(faces, shade.Flat3Style())
    assert len(ops) == 2


def test_substroke_residue_absorbed_by_deeper_face():
    # 3941 axle-cross ticks: a face whose visible piece is a sub-stroke
    # sliver (here a 1px strip of the mid face peeking past the near face)
    # is invisible-detail residue. It must not emit as its own fill; the
    # area falls THROUGH to the deeper face, which absorbs it seamlessly
    # (no background slit).
    near = _flat_face(0, 0, 20, 20, order=2, depth=0.0)
    mid = _flat_face(-1, 0, 20, 20, order=1, depth=5.0)
    deep = _flat_face(-8, -8, 28, 28, order=0, depth=10.0)
    ops = shade.fill_ops([deep, mid, near], shade.Flat3Style())
    assert len(ops) == 2                      # no sliver op for mid
    d_deep = ops[0]["d"]
    # deep's hole follows the near face's edge (x=0): the strip is deep's now
    assert "-1.00" not in d_deep


def test_substroke_residue_at_silhouette_drops():
    # same residue strip but nothing behind it: it just drops (the drawn
    # silhouette is the intent; residue past it is authored overhang)
    near = _flat_face(0, 0, 20, 20, order=1, depth=0.0)
    mid = _flat_face(-1, 0, 20, 20, order=0, depth=5.0)
    ops = shade.fill_ops([mid, near], shade.Flat3Style())
    assert len(ops) == 1
    assert "-1.00" not in ops[0]["d"]
