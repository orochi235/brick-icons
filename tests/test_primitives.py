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


def test_cylinder_occluder_elliptical_exact():
    # 30136's logs are elliptically scaled quarter-cylinders; the occluder
    # must hit the true ellipse, not a mean-radius circular proxy (the proxy
    # leaked fully hidden edges through as floating dash strokes).
    R = np.diag([2.0, 1.0, 1.0])                  # ellipse semi-axes 2 (x), 1 (z)
    cyl = P.CylinderOccluder(R, np.zeros(3), sector=360.0)
    F = np.array([0.0, 0.0, 1.0])
    O = np.array([[1.8, 0.5, -5.0],               # inside ellipse, outside r=1.5 proxy
                  [2.2, 0.5, -5.0]])               # outside the ellipse entirely
    d = cyl.depth(O, F)
    z = math.sqrt(1.0 - 1.8 ** 2 / 4.0)
    assert np.isclose(d[0], 5.0 - z, atol=1e-6)
    assert np.isinf(d[1])


def test_cylinder_occluder_elliptical_sector():
    # sector clamping must use the ellipse PARAM angle (unit local frame),
    # not the world angle warped by unequal axis scale
    R = np.diag([2.0, 1.0, 1.0])
    cyl = P.CylinderOccluder(R, np.zeros(3), sector=90.0)
    F = np.array([0.0, 0.0, 1.0])
    x = 2.0 * math.cos(math.radians(45.0))
    z = math.sin(math.radians(45.0))
    # near intersection (param -45deg) is outside the 0..90 sector; the far
    # one (param +45deg) is inside, so the near valid hit is the FAR wall
    d = cyl.depth(np.array([[x, 0.5, -5.0]]), F)
    assert np.isclose(d[0], 5.0 + z, atol=1e-6)


def test_drawn_cylinder_elliptical_silhouette_on_true_normal():
    # silhouette generators sit where the TRUE surface normal is
    # perpendicular to the view; for an elliptical wall that is not where
    # the radial direction is perpendicular to the view
    R = np.diag([2.0, 1.0, 1.0])
    fwd = np.array([1.0, 0.0, 1.0]) / math.sqrt(2.0)
    up = np.array([0.0, 1.0, 0.0])
    right = np.cross(up, fwd)
    proj = P.Projection(right, up, fwd, 1.0, 0.0, 0.0, 0.0)
    prim = P.Cylinder(R=R, t=np.zeros(3), sector=360.0)
    sils = [op for op, *_ in prim.drawn_with_depth(proj)
            if op[0] == "line" and op[-1] == "sil"]
    assert len(sils) == 2
    base = proj.circle(R, np.zeros(3), 1.0)
    Minv = np.linalg.inv(R)
    ths = np.radians(np.arange(0.0, 360.0, 0.05))
    pts = base.points(ths)
    for op in sils:
        i = int(np.argmin(np.hypot(pts[:, 0] - op[1], pts[:, 1] - op[2])))
        n = Minv.T @ np.array([math.cos(ths[i]), 0.0, math.sin(ths[i])])
        n /= np.linalg.norm(n)
        assert abs(float(n @ fwd)) < 5e-3


def test_disc_occluder_elliptical_exact():
    R = np.diag([2.0, 1.0, 1.0])                  # elliptical disc, semi-axes 2/1
    disc = P.DiscOccluder(R, np.zeros(3), sector=360.0, inner=0.0, outer=1.0)
    F = np.array([0.0, 1.0, 0.0])
    O = np.array([[1.8, -5.0, 0.0],               # inside the ellipse
                  [2.2, -5.0, 0.0]])               # outside
    d = disc.depth(O, F)
    assert np.isclose(d[0], 5.0) and np.isinf(d[1])


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
    """hlr's suppression rule, shared with the real pipeline."""
    from brick_icons import hlr
    return hlr.smooth_rim_skips(prims)


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
    assert not _smooth_shared_rims([body, lip])


def test_partial_sector_opposite_wall_splits_rim():
    # 3941's actual joint: full body wall (y0..20) meets 45-degree lip sectors
    # (y20..24) with cutout gaps. The lip sectors' rims vanish (the full body
    # continues them); the body's own rim survives ONLY across the cutouts —
    # where the lip continues the wall the seam is smooth, not an edge
    # (physically one cylinder with bites, same class as 60474's side wall).
    body = P.Cylinder(R=np.diag([20.0, 20.0, 20.0]), t=np.zeros(3),
                      sector=360.0)
    lip = P.Cylinder(R=np.diag([20.0, 4.0, 20.0]),
                     t=np.array([0.0, 20.0, 0.0]), sector=45.0)
    skip = _smooth_shared_rims([body, lip])
    body_rims = body.wall_rims()
    lip_rims = lip.wall_rims()
    assert (lip_rims[0][0], lip_rims[0][1]) in skip        # lip base: joint
    assert (body_rims[1][0], body_rims[1][1]) in skip      # body top: masked
    ops_lip = [op for op, *_ in
               lip.drawn_with_depth(_stub_proj(), skip_rims=skip)]
    assert not any(o[0] == "arc" and abs(o[2] - 20.0) < 1e-6 for o in ops_lip)
    # body: top rim (projected center y = +20 under _stub_proj, y-down) keeps
    # only the uncovered 315 degrees, base rim (y=0 -> center y 0) is whole
    ops_body = [op for op, *_ in
                body.drawn_with_depth(_stub_proj(), skip_rims=skip)]
    top_arcs = [o for o in ops_body if o[0] == "arc" and o[2] > 10.0]
    assert 312.0 < sum(o[8] - o[7] for o in top_arcs) < 316.0


def test_bite_interrupted_wall_seam_kept_only_at_gaps():
    # 60474's side wall: a full upper wall over a lower wall that covers only
    # 240 degrees (the rest are "bites"). The shared circle must be drawn
    # only across the uncovered 120 degrees; the lower wall's own rim arcs
    # at the joint vanish entirely (the full upper wall continues them).
    upper = P.Cylinder(R=np.diag([40.0, 4.0, 40.0]), t=np.zeros(3),
                       sector=360.0)
    lower = P.Cylinder(R=np.diag([40.0, 4.0, 40.0]),
                       t=np.array([0.0, 4.0, 0.0]), sector=240.0)
    skip = _smooth_shared_rims([upper, lower])
    ops_up = [op for op, *_ in
              upper.drawn_with_depth(_stub_proj(), skip_rims=skip)]
    # upper wall: base rim (y=0) intact, seam rim (projected center y=+4)
    # only over the bare 120 degrees the lower wall leaves uncovered
    seam = [o for o in ops_up if o[0] == "arc" and o[2] > 2.0]
    assert 116.0 < sum(o[8] - o[7] for o in seam) < 122.0
    ops_lo = [op for op, *_ in
              lower.drawn_with_depth(_stub_proj(), skip_rims=skip)]
    assert not any(o[0] == "arc" and abs(o[2] - 4.0) < 1e-6 for o in ops_lo)


def _wall_quad_tris(radius, y0, y1, deg0, deg1, step=6.0):
    """Triangulated quad band ON the cylinder wall r=radius spanning heights
    y0..y1 over world angles deg0..deg1 (facet-authored wall, like 60474's
    stretches beside each bite)."""
    tris = []
    d = deg0
    while d < deg1 - 1e-9:
        e = min(d + step, deg1)
        a0, a1 = math.radians(d), math.radians(e)
        p = lambda a, y: np.array([radius * math.cos(a), y,
                                   radius * math.sin(a)])
        tris.append([p(a0, y0), p(a0, y1), p(a1, y0)])
        tris.append([p(a1, y0), p(a0, y1), p(a1, y1)])
        d = e
    return np.array(tris)


def test_facet_authored_wall_counts_as_seam_coverage():
    # 60474's real authoring: the lower wall runs 240 degrees of analytic
    # sections, then RESUMES AS RAW QUADS over part of the rest (the bites
    # in between stay open). The quad stretch is just as smooth a joint as
    # the analytic one — the seam must be suppressed over it, and survive
    # only across the true gaps.
    from brick_icons import hlr
    upper = P.Cylinder(R=np.diag([40.0, 4.0, 40.0]), t=np.zeros(3),
                       sector=360.0)
    lower = P.Cylinder(R=np.diag([40.0, 4.0, 40.0]),
                       t=np.array([0.0, 4.0, 0.0]), sector=240.0)
    quads = _wall_quad_tris(40.0, 4.0, 8.0, 260.0, 340.0)
    skip = hlr.smooth_rim_skips([upper, lower], quads)
    ops_up = [op for op, *_ in
              upper.drawn_with_depth(_stub_proj(), skip_rims=skip)]
    # seam rim (projected center y=+4): analytic 240 + quads 80 covered,
    # two true gaps of 20 degrees each remain
    seam = [o for o in ops_up if o[0] == "arc" and o[2] > 2.0]
    assert 36.0 < sum(o[8] - o[7] for o in seam) < 44.0


def test_on_plane_cap_facets_do_not_cover_seam():
    # a disc facet in the rim plane touches the circle with every vertex
    # but is NOT wall surface: it must contribute no coverage (guards: no
    # extent away from the plane; wide chords span the interior).
    from brick_icons import hlr
    upper = P.Cylinder(R=np.diag([40.0, 4.0, 40.0]), t=np.zeros(3),
                       sector=360.0)
    fan = []
    c = np.array([0.0, 4.0, 0.0])
    for d in range(0, 360, 30):
        a0, a1 = math.radians(d), math.radians(d + 30)
        p = lambda a: np.array([40.0 * math.cos(a), 4.0, 40.0 * math.sin(a)])
        fan.append([c, p(a0), p(a1)])
    assert not hlr.smooth_rim_skips([upper], np.array(fan))


def test_cone_on_cylinder_crease_rim_kept():
    # different slopes meeting at a shared circle = a real crease: keep arcs
    cyl = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    cone = P.Cone(R=np.eye(3), t=np.array([0.0, 1.0, 0.0]), sector=360.0,
                  top=0.0)
    assert not _smooth_shared_rims([cyl, cone])


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


def test_partial_disc_face_closes_through_center():
    # stud10's cap is a 3-4disc (270 deg) tiled with hand-authored fan tris
    # over the last quarter; a face polygon closed along the arc-end chord
    # instead of through the center covers a phantom triangle of that
    # quarter, double-painting the coplanar fan (visible at opacity < 1).
    from shapely.geometry import Point, Polygon
    right, up, fwd = (np.array([1.0, 0, 0]), np.array([0, 0, 1.0]),
                      np.array([0, -1.0, 0]))
    proj = P.Projection(right, up, fwd, s=1.0, cx=0.0, cy=0.0, half=0.0)
    disc = P.Disc(R=np.eye(3), t=np.zeros(3), sector=270.0)
    (face,) = disc.faces(proj)
    poly = Polygon(face["poly"]).buffer(0)

    def screen_pt(deg):
        th = math.radians(deg)
        w = np.array([[0.5 * math.cos(th), 0.0, 0.5 * math.sin(th)]])
        px, py, _ = proj.to_px(w)
        return Point(float(px[0]), float(py[0]))

    assert not poly.contains(screen_pt(315.0))    # mid missing quarter
    for deg in (45.0, 135.0, 225.0):              # mid covered sector
        assert poly.contains(screen_pt(deg))


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
