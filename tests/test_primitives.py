import math

import numpy as np

from brick_icons import primitives as P


def test_parse_edge_fractions():
    assert P.parse_primitive("4-4edge.dat") == ("edge", 360.0, 0)
    assert P.parse_primitive("1-4edge.dat") == ("edge", 90.0, 0)
    assert P.parse_primitive("3-4edge") == ("edge", 270.0, 0)
    assert P.parse_primitive("1-8edge.dat") == ("edge", 45.0, 0)


def test_parse_cyli_and_alias_cylo():
    assert P.parse_primitive("1-4cyli.dat") == ("cyli", 90.0, 0)
    assert P.parse_primitive("4-4cylo.dat") == ("cyli", 360.0, 0)


def test_parse_disc():
    assert P.parse_primitive("3-4disc.dat") == ("disc", 270.0, 0)


def test_parse_ring_inner_radius():
    assert P.parse_primitive("4-4ring3.dat") == ("ring", 360.0, 3)
    assert P.parse_primitive("4-4ring1.dat") == ("ring", 360.0, 1)


def test_unrecognized_returns_none():
    assert P.parse_primitive("1-4cyls.dat") is None       # sloped cut: fallback
    assert P.parse_primitive("1-8chrd.dat") is None       # chord: straight, fallback
    assert P.parse_primitive("box.dat") is None
    assert P.parse_primitive("stud4.dat") is None


def test_parse_cone_names():
    assert P.parse_primitive("4-4con4.dat") == ("con", 360.0, 4)
    assert P.parse_primitive("1-4con0.dat") == ("con", 90.0, 0)
    assert P.parse_primitive("1-16con13.dat") == ("con", 22.5, 13)
    assert P.parse_primitive("48\\4-4con3.dat") == ("con", 360.0, 3)


def test_parse_ndis_stays_faceted():
    # deliberate: faceted ndis tris join adjacent facet groups and inherit the
    # group gradient (analytic ndis produced a tone-mismatched square, 3960);
    # fill_ops' union merges the tris into one region anyway.
    assert P.parse_primitive("4-4ndis.dat") is None
    assert P.parse_primitive("1-4ndis.dat") is None


def test_parse_still_rejects_unhandled():
    for name in ("1-16tndis.dat", "1-4cyls.dat", "1-8chrd.dat", "4-4con.dat"):
        assert P.parse_primitive(name) is None


def test_project_circle_to_ellipse_basis():
    def proj(Pw):   # simple projector: A=x, B=z, Z=y
        Pw = np.atleast_2d(Pw)
        return Pw[:, 0], Pw[:, 2], Pw[:, 1]
    R, t = np.eye(3), np.zeros(3)
    ell = P.project_circle(R, t, 2.0, proj, s=1.0, cx=0.0, cy=0.0, half=0.0)
    assert np.allclose(ell.center, [0.0, 0.0])
    assert np.allclose(np.hypot(*ell.u), 2.0) and np.allclose(np.hypot(*ell.v), 2.0)


def test_ellipse_svd_axes_circle():
    e = P.Ellipse(center=np.array([5.0, 7.0]), u=np.array([3.0, 0.0]), v=np.array([0.0, 3.0]))
    rx, ry, phi = e.svg_axes()
    assert np.isclose(rx, 3.0) and np.isclose(ry, 3.0)


def test_ellipse_point_param():
    e = P.Ellipse(center=np.array([0.0, 0.0]), u=np.array([2.0, 0.0]), v=np.array([0.0, 1.0]))
    p0 = e.point(0.0)
    p90 = e.point(math.pi / 2)
    assert np.allclose(p0, [2.0, 0.0]) and np.allclose(p90, [0.0, 1.0])


def test_cylinder_depth_hit_and_miss():
    R, t = np.eye(3), np.zeros(3)
    cyl = P.CylinderOccluder(R, t, sector=360.0)
    F = np.array([0.0, 0.0, 1.0])               # look along +z
    O = np.array([[0.0, 0.5, -5.0],              # through axis mid-height -> front wall z=-1
                  [5.0, 0.5, -5.0]])              # misses (x=5 outside r=1)
    d = cyl.depth(O, F)
    assert np.isclose(d[0], 4.0, atol=1e-6)       # lam to reach z=-1 from z=-5
    assert np.isinf(d[1])


def test_cylinder_depth_clamps_height():
    R, t = np.eye(3), np.zeros(3)
    cyl = P.CylinderOccluder(R, t, sector=360.0)
    F = np.array([0.0, 0.0, 1.0])
    O = np.array([[0.0, 5.0, -5.0]])              # above the top (y=5 > 1) -> miss
    assert np.isinf(cyl.depth(O, F)[0])


def test_disc_depth():
    R, t = np.eye(3), np.zeros(3)                 # disc in XZ plane at y=0, radius 1
    disc = P.DiscOccluder(R, t, sector=360.0, inner=0.0, outer=1.0)
    F = np.array([0.0, 1.0, 0.0])                 # look along +y onto the disc
    O = np.array([[0.3, -5.0, 0.2],                # inside radius -> lam=5
                  [2.0, -5.0, 0.0]])                # outside radius -> miss
    d = disc.depth(O, F)
    assert np.isclose(d[0], 5.0) and np.isinf(d[1])


def _proj_xz():
    # A=x, B=z, Z=y (look along +y); identity pixel fit
    return P.Projection(np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, -1.0]),
                        np.array([0.0, 1.0, 0.0]), 1.0, 0.0, 0.0, 0.0)


def test_drawn_edge_is_full_arc():
    prim = P.Edge(R=np.eye(3), t=np.zeros(3), sector=360.0)
    ops = [op for op, *_ in prim.drawn_with_depth(_proj_xz())]
    assert len(ops) == 1 and ops[0][0] == "arc"
    assert ops[0][-1] == "edge"


def test_drawn_cylinder_has_two_silhouette_lines():
    # cylinder axis +y; view along +z so the side silhouette is well-defined
    proj_z = P.Projection(np.array([1.0, 0.0, 0.0]), np.array([0.0, -1.0, 0.0]),
                          np.array([0.0, 0.0, 1.0]), 1.0, 0.0, 0.0, 0.0)
    prim = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    ops = [op for op, *_ in prim.drawn_with_depth(proj_z)]
    sil_lines = [o for o in ops if o[0] == "line" and o[-1] == "sil"]
    assert len(sil_lines) == 2


def test_visibility_splits_op_by_occluder():
    # horizontal edge line across x in [0,10] at depth 0; an occluder slab
    # covers x in [4,6] nearer (depth -1) -> the middle is hidden.
    class Slab:
        def depth(self, O, F):
            x = O[:, 0]
            return np.where((x >= 4) & (x <= 6), -1.0, np.inf)

    op = ("line", 0.0, 0.0, 10.0, 0.0, "edge")
    depth_fn = lambda ts: np.zeros_like(np.asarray(ts, float))   # line lies at depth 0

    def ray_origin(xs, ys):
        return np.stack([xs, ys, np.zeros_like(xs)], 1)

    vis = P.visible_subops([(op, depth_fn)], [Slab()], ray_origin,
                           fwd=np.array([0, 0, 1.0]), eps=1e-6, n=101)
    lines = [o for o in vis if o[0] == "line"]
    assert len(lines) == 2                        # left of 4 and right of 6
    assert lines[0][1] < 4.0 and lines[1][3] > 6.0


def test_visibility_keeps_unoccluded_arc_whole():
    class Empty:
        def depth(self, O, F):
            return np.full(O.shape[0], np.inf)

    # parametric arc: center (50,50), u=(40,0), v=(0,40), params 0..360 deg
    op = ("arc", 50.0, 50.0, 40.0, 0.0, 0.0, 40.0, 0.0, 360.0, "edge")
    depth_fn = lambda degs: np.zeros_like(np.asarray(degs, float))

    def ray_origin(xs, ys):
        return np.stack([xs, ys, np.zeros_like(xs)], 1)

    vis = P.visible_subops([(op, depth_fn)], [Empty()], ray_origin,
                           fwd=np.array([0, 0, 1.0]), eps=1e-6, n=60)
    arcs = [o for o in vis if o[0] == "arc"]
    assert len(arcs) == 1 and np.isclose(arcs[0][7], 0.0) and arcs[0][8] >= 350.0


def test_cone_occluder_axis_aligned_hit():
    # con0: radius 1 at y=0 -> 0 at y=1. Ray along +Z at (x=.25, y=.5):
    # the section there has radius .5, so x^2+z^2=.25 -> z = +-sqrt(.5^2-.25^2)
    occ = P.ConeOccluder(np.eye(3), np.zeros(3), 360.0, 0)
    O = np.array([[0.25, 0.5, -5.0]])
    F = np.array([0.0, 0.0, 1.0])
    z = math.sqrt(0.5 ** 2 - 0.25 ** 2)
    assert abs(occ.depth(O, F)[0] - (5.0 - z)) < 1e-9
    assert abs(occ.depth_far(O, F)[0] - (5.0 + z)) < 1e-9


def test_cone_occluder_height_and_sector_clamp():
    occ = P.ConeOccluder(np.eye(3), np.zeros(3), 360.0, 0)
    assert not np.isfinite(occ.depth(np.array([[0.1, 1.5, -5.0]]),
                                     np.array([0.0, 0.0, 1.0]))[0])
    quarter = P.ConeOccluder(np.eye(3), np.zeros(3), 90.0, 0)
    # ray at x=+.25: near hit (z<0) is outside the [0,90] sector, far hit
    # (z>0, theta~60deg) is inside -> nearest valid hit is the FAR wall
    O = np.array([[0.25, 0.5, -5.0]])
    d = quarter.depth(O, np.array([0.0, 0.0, 1.0]))[0]
    z = math.sqrt(0.5 ** 2 - 0.25 ** 2)
    assert abs(d - (5.0 + z)) < 1e-9


def test_cone_occluder_scaled_transform():
    # radius x2, height x3, translated: lambda is invariant under the linear
    # map, so depths come back in world units.
    R = np.diag([2.0, 3.0, 2.0])
    t = np.array([10.0, 0.0, 0.0])
    occ = P.ConeOccluder(R, t, 360.0, 0)
    O = np.array([[10.5, 1.5, -9.0]])          # local (.25, .5, ...)
    F = np.array([0.0, 0.0, 1.0])
    z = 2.0 * math.sqrt(0.5 ** 2 - 0.25 ** 2)
    assert abs(occ.depth(O, F)[0] - (9.0 - z)) < 1e-9


def _stub_proj():
    # camera looks along -Z: A=x, B=y, depth=-z; identity pixel fit
    return P.Projection(np.array([1.0, 0.0, 0.0]), np.array([0.0, -1.0, 0.0]),
                        np.array([0.0, 0.0, -1.0]), 1.0, 0.0, 0.0, 0.0)


def test_cone_drawn_ops_full_sector():
    prim = P.Cone(R=np.eye(3), t=np.zeros(3), sector=360.0, top=1.0)
    pairs = prim.drawn_with_depth(_stub_proj())
    ops = [op for op, *_ in pairs]
    arcs = [o for o in ops if o[0] == "arc"]
    sils = [o for o in ops if o[0] == "line" and o[-1] == "sil"]
    assert len(arcs) == 2 and len(sils) == 2
    # generators at theta = 0 and pi: base pts x=+-2, top pts x=+-1
    ends = sorted((round(o[1], 6), round(o[3], 6)) for o in sils)
    assert ends == [(-2.0, -1.0), (2.0, 1.0)]


def test_cone_apex_no_top_arc():
    prim = P.Cone(R=np.eye(3), t=np.zeros(3), sector=360.0, top=0.0)
    ops = [op for op, *_ in prim.drawn_with_depth(_stub_proj())]
    assert len([o for o in ops if o[0] == "arc"]) == 1     # base rim only
    sils = [o for o in ops if o[0] == "line"]
    assert len(sils) == 2
    # every generator ends at the projected apex (0, 1)
    assert all(abs(o[3]) < 1e-9 and abs(o[4] - 1.0) < 1e-9 for o in sils)


def _smooth_shared_rims(prims):
    """Mirror of hlr's suppression rule: a rim is skipped iff a FULL-sector
    wall of equal slope continues on the opposite side of its plane."""
    from collections import defaultdict
    full_smooth = defaultdict(set)
    for p in prims:
        if p.is_full:
            for key, side, slope in p.wall_rims():
                full_smooth[key].add((side, slope))
    skip = set()
    for p in prims:
        for key, side, slope in p.wall_rims():
            if (-side, slope) in full_smooth[key]:
                skip.add((key, side))
    return skip


def test_shared_rim_arcs_suppressed_for_stacked_cones():
    # con1 stacked on con0: the joint circle (radius 1 at y=1) is a smooth
    # continuation, NOT an edge — 4589 showed a spurious black ring there.
    lower = P.Cone(R=np.eye(3), t=np.zeros(3), sector=360.0, top=1.0)
    upper = P.Cone(R=np.eye(3), t=np.array([0.0, 1.0, 0.0]), sector=360.0,
                   top=0.0)
    shared = _smooth_shared_rims([lower, upper])
    assert len(shared) == 2                     # both sides of the one joint
    ops_lower = [op for op, *_ in
                 lower.drawn_with_depth(_stub_proj(), skip_rims=shared)]
    ops_upper = [op for op, *_ in
                 upper.drawn_with_depth(_stub_proj(), skip_rims=shared)]
    # lower keeps only its base arc; upper (apex cone) loses its base arc
    assert len([o for o in ops_lower if o[0] == "arc"]) == 1
    assert len([o for o in ops_upper if o[0] == "arc"]) == 0
    # silhouette generator lines are unaffected
    assert [o for o in ops_lower if o[0] == "line"]


def test_same_side_shared_rims_kept():
    # 3941's base lip: quadrant walls END on the same circle as the body wall
    # (same side of the plane) — that rim is real silhouette closure, not a
    # smooth joint; suppressing it opened the historic base gap again.
    body = P.Cylinder(R=np.diag([20.0, -24.0, 20.0]),
                      t=np.array([0.0, 24.0, 0.0]), sector=360.0)
    lip = P.Cylinder(R=np.diag([20.0, -4.0, 20.0]),
                     t=np.array([0.0, 24.0, 0.0]), sector=90.0)
    assert _smooth_shared_rims([body, lip]) == set()


def test_partial_sector_opposite_wall_keeps_full_rim():
    # 3941's actual joint: full body wall (y0..20) meets 45-degree lip sectors
    # (y20..24) with cutout gaps. The lip sectors' rims vanish (the full body
    # continues them) but the body's own rim must stay — it is a real edge
    # across the cutouts, and the silhouette tangent lands on it.
    body = P.Cylinder(R=np.diag([20.0, 20.0, 20.0]), t=np.zeros(3),
                      sector=360.0)
    lip = P.Cylinder(R=np.diag([20.0, 4.0, 20.0]),
                     t=np.array([0.0, 20.0, 0.0]), sector=45.0)
    skip = _smooth_shared_rims([body, lip])
    body_rims = body.wall_rims()
    lip_rims = lip.wall_rims()
    assert (lip_rims[0][0], lip_rims[0][1]) in skip        # lip base: joint
    assert (body_rims[1][0], body_rims[1][1]) not in skip  # body top: real edge


def test_cone_on_cylinder_crease_rim_kept():
    # different slopes meeting at a shared circle = a real crease: keep arcs
    cyl = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    cone = P.Cone(R=np.eye(3), t=np.array([0.0, 1.0, 0.0]), sector=360.0,
                  top=0.0)
    assert _smooth_shared_rims([cyl, cone]) == set()


def test_unshared_rims_still_drawn():
    prim = P.Cone(R=np.eye(3), t=np.zeros(3), sector=360.0, top=1.0)
    ops = [op for op, *_ in prim.drawn_with_depth(_stub_proj(), skip_rims=set())]
    assert len([o for o in ops if o[0] == "arc"]) == 2


def test_cone_axis_on_view_no_generators():
    # A=x, B=z, Z=-y: looking down the cone axis
    proj = P.Projection(np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, -1.0]),
                        np.array([0.0, -1.0, 0.0]), 1.0, 0.0, 0.0, 0.0)
    prim = P.Cone(R=np.eye(3), t=np.zeros(3), sector=360.0, top=1.0)
    ops = [op for op, *_ in prim.drawn_with_depth(proj)]
    assert not [o for o in ops if o[0] == "line"]


def test_cylinder_depth_far_returns_second_hit():
    """Interior far-half wall faces need the FAR ray intersection; the near
    hit belongs to the front wall (ordering interior walls by the near hit
    painted them over geometry actually in front of them)."""
    import numpy as np
    from brick_icons import primitives as P
    R = np.eye(3)                       # axis +Y, but occluder spans C..C+A
    occ = P.CylinderOccluder(R, np.zeros(3), 360.0)
    O = np.array([[0.0, 0.5, -5.0]])
    F = np.array([0.0, 0.0, 1.0])
    near = float(occ.depth(O, F)[0])
    far = float(occ.depth_far(O, F)[0])
    assert abs(near - 4.0) < 1e-9       # z=-1 wall
    assert abs(far - 6.0) < 1e-9        # z=+1 wall


def test_projection_to_AB_matches_hlr_project():
    from brick_icons import hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, s=2.0, cx=1.0, cy=-3.0, half=100.0)
    Pw = np.array([[1.0, 2.0, 3.0], [-4.0, 0.5, 9.0]])
    a, b, z = proj.to_AB(Pw)
    ea, eb, ez = hlr.project(Pw, right, up, fwd)
    assert np.allclose(a, ea) and np.allclose(b, eb) and np.allclose(z, ez)


def test_projection_px_roundtrip_through_ray_origin():
    from brick_icons import hlr
    right, up, fwd = hlr.view_basis(20.0, 60.0)
    proj = P.Projection(right, up, fwd, s=3.0, cx=0.5, cy=1.5, half=200.0)
    Pw = np.array([[10.0, -5.0, 2.0]])
    px, py, _ = proj.to_px(Pw)
    O = proj.ray_origin(px, py)
    # the ray origin projects back to the same pixel (depth-free component)
    px2, py2, _ = proj.to_px(O)
    assert np.allclose(px, px2) and np.allclose(py, py2)


def test_projection_circle_matches_project_circle():
    from brick_icons import hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, s=2.0, cx=1.0, cy=-3.0, half=100.0)

    def to_AB(Pw):
        return hlr.project(np.atleast_2d(np.asarray(Pw, float)), right, up, fwd)

    ell_old = P.project_circle(np.eye(3), np.zeros(3), 2.0, to_AB,
                               s=2.0, cx=1.0, cy=-3.0, half=100.0)
    ell_new = proj.circle(np.eye(3), np.zeros(3), 2.0)
    assert np.allclose(ell_old.center, ell_new.center)
    assert np.allclose(ell_old.u, ell_new.u) and np.allclose(ell_old.v, ell_new.v)
    assert np.allclose(ell_old.depth_coeffs, ell_new.depth_coeffs)


def test_from_ref_constructs_each_kind():
    R, t = np.eye(3), np.zeros(3)
    e = P.from_ref("1-4edge.dat", R, t)
    assert isinstance(e, P.Edge) and e.kind == "edge" and e.sector == 90.0
    c = P.from_ref("4-4cylo.dat", R, t)          # cylo aliases to cylinder
    assert isinstance(c, P.Cylinder) and c.kind == "cyli" and c.is_full
    d = P.from_ref("3-4disc.dat", R, t)
    assert isinstance(d, P.Disc) and d.sector == 270.0
    r = P.from_ref("4-4ring3.dat", R, t)
    assert isinstance(r, P.Ring) and r.inner == 3
    k = P.from_ref("1-16con13.dat", R, t)
    assert isinstance(k, P.Cone) and k.top == 13.0 and np.isclose(k.sector, 22.5)
    assert P.from_ref("4-4ndis.dat", R, t) is None
    assert P.from_ref("1-4cyls.dat", R, t) is None


def test_primitive_normalizes_arrays_and_is_full():
    c = P.Cylinder(R=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], t=[0, 0, 0], sector=360.0)
    assert isinstance(c.R, np.ndarray) and isinstance(c.t, np.ndarray)
    assert c.is_full
    assert not P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=90.0).is_full


def test_occluder_types_and_caching():
    R, t = np.eye(3), np.zeros(3)
    assert P.Edge(R=R, t=t, sector=360.0).occluder() is None
    d = P.Disc(R=R, t=t, sector=360.0)
    assert isinstance(d.occluder(), P.DiscOccluder)
    assert np.isclose(d.occluder().inner, 0.0) and np.isclose(d.occluder().outer, 1.0)
    r = P.Ring(R=R, t=t, sector=360.0, inner=2)
    assert np.isclose(r.occluder().inner, 2.0) and np.isclose(r.occluder().outer, 3.0)
    c = P.Cylinder(R=R, t=t, sector=360.0)
    assert isinstance(c.occluder(), P.CylinderOccluder)
    k = P.Cone(R=R, t=t, sector=360.0, top=2.0)
    assert isinstance(k.occluder(), P.ConeOccluder) and k.occluder().top == 2.0
    # cached: same instance every call (hlr keys ordering maps off this)
    assert c.occluder() is c.occluder()


def test_primitive_identity_semantics():
    a = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    b = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    assert a != b and len({a, b}) == 2            # eq/hash by identity


def _parity_proj():
    # A=x, B=y, depth=-z  (to_AB: right=+x; B=-(P@up) => up=(0,-1,0); Z: fwd=(0,0,-1))
    return P.Projection(np.array([1.0, 0.0, 0.0]), np.array([0.0, -1.0, 0.0]),
                        np.array([0.0, 0.0, -1.0]), s=1.0, cx=0.0, cy=0.0, half=0.0)


def test_axis_on_cone_emits_no_generators():
    Rz = np.column_stack([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
    prim = P.Cone(R=Rz, t=np.zeros(3), sector=360.0, top=1.0)
    ops = [op for op, *_ in prim.drawn_with_depth(_parity_proj())]
    assert not [o for o in ops if o[0] == "line"]


def test_skip_rims_drop_matching_arcs():
    prim = P.Cone(R=np.eye(3), t=np.zeros(3), sector=360.0, top=1.0)
    rims = prim.wall_rims()
    all_skips = {(k, s) for k, s, _ in rims}
    base_only = {(rims[0][0], rims[0][1])}
    top_only = {(rims[1][0], rims[1][1])}
    n_arcs = lambda p, sk: len([op for op, *_ in p.drawn_with_depth(
        _parity_proj(), skip_rims=sk) if op[0] == "arc"])
    assert n_arcs(prim, all_skips) == 0 and n_arcs(prim, base_only) == 1 \
        and n_arcs(prim, top_only) == 1
    cyl = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    crims = cyl.wall_rims()
    assert n_arcs(cyl, {(k, s) for k, s, _ in crims}) == 0
    assert n_arcs(cyl, {(crims[0][0], crims[0][1])}) == 1


def test_faces_axis_on_cylinder_no_wall():
    from brick_icons import hlr
    # axis pointing at the camera: U.fwd == V.fwd == 0 -> no wall face
    right, up, fwd = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
    proj = P.Projection(right, up, fwd, s=1.0, cx=0.0, cy=0.0, half=0.0)
    R = np.column_stack([[1.0, 0, 0], [0, 0, 1.0], [0, 1.0, 0]])   # axis = +z
    assert P.Cylinder(R=R, t=np.zeros(3), sector=360.0).faces(proj) == []


def _cone10(top, ty=0.0):
    return P.Cone(R=np.diag([10.0, 10.0, 10.0]),
                  t=np.array([0.0, ty, 0.0]), sector=360.0, top=float(top))


def test_merge_smooth_walls_stacked_cones_one_prim():
    out = P.merge_smooth_walls([_cone10(2), _cone10(1, ty=10.0)])
    assert len(out) == 1
    merged = out[0]
    assert isinstance(merged, P.Cone) and merged.is_full
    # merged frustum: base radius 30 at y=0 -> radius 10 at y=20;
    # R scale = dr = 20, top = r1/dr = 0.5
    assert np.isclose(np.linalg.norm(merged.R[:, 0]), 20.0)
    assert np.isclose(merged.top, 0.5)
    assert np.allclose(merged.t, [0.0, 0.0, 0.0])


def test_merge_smooth_walls_stacked_cylinders():
    a = P.Cylinder(R=np.diag([10.0, 10.0, 10.0]), t=np.zeros(3), sector=360.0)
    b = P.Cylinder(R=np.diag([10.0, 10.0, 10.0]),
                   t=np.array([0.0, 10.0, 0.0]), sector=360.0)
    out = P.merge_smooth_walls([a, b])
    assert len(out) == 1 and isinstance(out[0], P.Cylinder)
    assert np.isclose(np.linalg.norm(out[0].R[:, 1]), 20.0)   # merged height


def test_merge_smooth_walls_keeps_creases_and_partial_sectors():
    lo = _cone10(2)
    crease = P.Cylinder(R=np.diag([10.0, 10.0, 10.0]),
                        t=np.array([0.0, 10.0, 0.0]), sector=360.0)
    assert len(P.merge_smooth_walls([lo, crease])) == 2       # slope mismatch
    part = P.Cone(R=np.diag([10.0, 10.0, 10.0]),
                  t=np.array([0.0, 10.0, 0.0]), sector=90.0, top=1.0)
    assert len(P.merge_smooth_walls([lo, part])) == 2         # partial sector


def test_merge_smooth_walls_passthrough_non_walls():
    ring = P.Ring(R=np.eye(3), t=np.zeros(3), sector=360.0, inner=2)
    out = P.merge_smooth_walls([ring])
    assert out == [ring]


def test_merge_smooth_walls_apex_terminated_chain():
    # con1 stacked with con0 on top: the upper end is a radius-0 apex,
    # which _rim_circles omits (no rim arc there) but _end_circles must
    # report so the chain still has exactly two free ends.
    out = P.merge_smooth_walls([_cone10(1), _cone10(0, ty=10.0)])
    assert len(out) == 1
    merged = out[0]
    assert isinstance(merged, P.Cone) and np.isclose(merged.top, 0.0)
    assert np.isclose(np.linalg.norm(merged.R[:, 0]), 20.0)   # dr = 20-0
    assert np.allclose(merged.t, [0.0, 0.0, 0.0])
    assert np.isclose(np.linalg.norm(merged.R[:, 1]), 20.0)   # full height
