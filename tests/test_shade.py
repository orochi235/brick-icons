import math

import numpy as np
from brick_icons import shade, hlr


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
    def ray_origin(xs, ys): return np.zeros((len(xs), 3))
    kept = shade.cull_occluded_faces(
        [face], occluders=[own], ray_origin=ray_origin, fwd=np.array([0, 0, 1.0]),
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
    def ray_origin(xs, ys): return np.zeros((len(xs), 3))
    kept = shade.cull_occluded_faces(
        [face], occluders=[own, wall], ray_origin=ray_origin,
        fwd=np.array([0, 0, 1.0]), eps=1e-3,
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
    def ray_origin(xs, ys): return np.zeros((len(xs), 3))
    kept = shade.cull_occluded_faces([face], occluders=[FakeOcc()],
                                     ray_origin=ray_origin, fwd=np.array([0, 0, 1.0]),
                                     eps=1e-3, kinds=("disc",))   # tri not listed
    assert kept == [face]


def test_faces_from_analytic_cylinder_gradient_and_disc():
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    R = np.eye(3); t = np.zeros(3)
    cyl = {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": t}
    disc = {"kind": "disc", "sector": 360.0, "inner": 0, "R": R, "t": t}
    faces = shade.faces_from_analytic([cyl, disc], right, up, fwd,
                                      s=2.0, cx=0.0, cy=0.0, half=50.0)
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
    ring = {"kind": "ring", "sector": 360.0, "inner": 2, "R": R, "t": np.zeros(3)}
    faces = shade.faces_from_analytic([ring], right, up, fwd,
                                      s=1.0, cx=0.0, cy=0.0, half=0.0)
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
    ring = {"kind": "ring", "sector": 90.0, "inner": 2, "R": R, "t": np.zeros(3)}
    f = shade.faces_from_analytic([ring], right, up, fwd,
                                  s=1.0, cx=0.0, cy=0.0, half=0.0)[0]
    assert not f.get("holes")           # annular sector: simple valid polygon


def _screen_plane_R():
    # ndis/ring local XZ plane mapped into the screen: U=+x, axis=+z, V=+y
    return np.column_stack([np.array([1.0, 0.0, 0.0]),
                            np.array([0.0, 0.0, 1.0]),
                            np.array([0.0, 1.0, 0.0])])


def test_ndis_face_polygon_quarter():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    rec = {"kind": "ndis", "sector": 90.0, "inner": 0,
           "R": _screen_plane_R(), "t": np.zeros(3)}
    faces = shade.faces_from_analytic([rec], right, up, fwd, 1.0, 0.0, 0.0, 0.0)
    assert len(faces) == 1
    f = faces[0]
    p = f["poly"]
    area = 0.5 * abs(np.sum(p[:, 0] * np.roll(p[:, 1], -1)
                            - np.roll(p[:, 0], -1) * p[:, 1]))
    assert abs(area - (1 - math.pi / 4)) < 0.01
    assert not f.get("holes")
    assert abs(np.linalg.norm(f["normal"]) - 1) < 1e-6


def test_ndis_face_full_sector_has_hole():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    rec = {"kind": "ndis", "sector": 360.0, "inner": 0,
           "R": _screen_plane_R(), "t": np.zeros(3)}
    f = shade.faces_from_analytic([rec], right, up, fwd, 1.0, 0.0, 0.0, 0.0)[0]
    assert len(f["poly"]) == 4 and len(f.get("holes", [])) == 1


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


def _cone_rec(N=1, sector=360.0):
    return {"kind": "con", "sector": sector, "inner": N,
            "R": np.eye(3), "t": np.zeros(3)}


def test_cone_wall_faces_outer_and_interior():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    faces = shade.faces_from_analytic([_cone_rec()], right, up, fwd,
                                      1.0, 0.0, 0.0, 0.0)
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
    f = [x for x in shade.faces_from_analytic([_cone_rec(N=1)], right, up, fwd,
                                              1.0, 0.0, 0.0, 0.0)
         if not x.get("interior")][0]
    xs = np.abs(f["poly"][:, 0])
    assert abs(xs.max() - 2.0) < 1e-6           # base radius N+1


def test_cone_axis_on_view_full_annulus_wall():
    # looking straight down the axis from above the apex: the whole outer wall
    # is visible as an annulus-like band (unlike a cylinder, which shows none).
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 0.0, 1.0])
    fwd = np.array([0.0, -1.0, 0.0])
    faces = shade.faces_from_analytic([_cone_rec()], right, up, fwd,
                                      1.0, 0.0, 0.0, 0.0)
    assert len(faces) == 1 and not faces[0].get("interior")


def test_cylinder_wall_faces_unchanged():
    # regression: generalizing helpers must not perturb cylinder output
    rec = {"kind": "cyli", "sector": 360.0, "inner": 0,
           "R": np.eye(3), "t": np.zeros(3)}
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    faces = shade.faces_from_analytic([rec], right, up, fwd, 1.0, 0.0, 0.0, 0.0)
    assert {f.get("interior", False) for f in faces} == {False, True}
    for f in faces:
        assert abs(f["span_deg"] - 180.0) < 1e-6
        for _, nv in f["grad_samples"]:
            assert abs(nv[1]) < 1e-9            # cylinder normals have no up


def test_faces_from_tris_culls_back_and_projects():
    # a single CCW triangle in the z=0 plane (LDraw world)
    tri = np.array([[[0, 0, 0], [10, 0, 0], [0, 10, 0]]], float)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    faces = shade.faces_from_tris(tri, right, up, fwd, s=2.0, cx=0.0, cy=0.0, half=50.0)
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
    faces = shade.faces_from_tris(tri, right, up, fwd, s=2.0, cx=0, cy=0, half=50.0)
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
    faces = shade.faces_from_tris(np.array(tris), right, up, fwd,
                                  1.0, 0.0, 0.0, 0.0,
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


def test_highlight_ops_only_for_upfacing_discs():
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    R = np.eye(3); t = np.zeros(3)
    disc_up = {"kind": "disc", "sector": 360.0, "inner": 0, "R": R, "t": t}
    hi = shade.highlight_ops([disc_up], right, up, fwd, s=2.0, cx=0.0, cy=0.0,
                             half=50.0, strength=0.15)
    assert len(hi) == 1
    assert hi[0]["opacity"] <= 0.15 and hi[0]["cx"] is not None


def test_remap_highlights_applies_affine_and_strength():
    from brick_icons import shade
    out = shade.remap_highlights([{"cx": 10.0, "cy": 20.0, "r": 5.0, "opacity": 1.0}],
                                 f=2.0, ox=1.0, oy=3.0, strength=0.15)
    assert out[0] == {"cx": 21.0, "cy": 43.0, "r": 10.0, "opacity": 0.15}


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
    def ray_origin(xs, ys):
        return np.stack([xs, ys, np.zeros_like(xs)], axis=1)
    kept = shade.cull_occluded_faces(
        [face], occluders=[StudOcc()], ray_origin=ray_origin,
        fwd=np.array([0, 0, 1.0]), eps=1e-3)
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
    def ray_origin(xs, ys):
        return np.stack([xs, ys, np.zeros_like(xs)], axis=1)
    kept = shade.cull_occluded_faces(
        [face], occluders=[WallOcc()], ray_origin=ray_origin,
        fwd=np.array([0, 0, 1.0]), eps=1e-3)
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
    cyl = {"kind": "cyli", "sector": 270.0, "inner": 0, "R": R, "t": np.zeros(3)}
    faces = shade.faces_from_analytic([cyl], right, up, fwd,
                                      s=2.0, cx=0.0, cy=0.0, half=50.0)
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
    cyl = {"kind": "cyli", "sector": 360.0, "inner": 0, "R": np.eye(3),
           "t": np.zeros(3)}
    faces = shade.faces_from_analytic([cyl], right, up, fwd,
                                      s=2.0, cx=0.0, cy=0.0, half=50.0)
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
    faces = shade.faces_from_tris(allt, right, up, fwd, s=2.0, cx=0, cy=0,
                                  half=200.0, cond_edges=seams)
    grads = [f for f in faces if "grad_axis" in f]
    flats = [f for f in faces if "grad_axis" not in f]
    assert len(grads) >= 4                      # the curved strip grouped
    assert len(flats) >= 1                      # unrelated tri untouched
    ax0 = grads[0]["grad_axis"]
    assert all(g["grad_axis"] == ax0 for g in grads)          # shared axis
    assert all(g["grad_samples"] is grads[0]["grad_samples"] for g in grads)
    offs = [o for o, _ in grads[0]["grad_samples"]]
    assert len(set(round(o, 3) for o in offs)) >= 2           # real ramp
