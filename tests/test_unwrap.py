import re

import numpy as np
import pytest

from brick_icons import geom2d, unwrap


class FakeCylinder:
    """Stand-in for primitives.Cylinder: unit circle in R's x/z, axis R[:,1]."""
    sector = 360.0

    def __init__(self, r=20.0, h=24.0, sector=360.0):
        self.R = np.diag([r, h, r]).astype(float)
        self.t = np.zeros(3)
        self.sector = sector

    def radius_at(self, level):
        return 1.0


class FakeCone(FakeCylinder):
    """primitives.Cone's law: local radius top+1 at the base, top at the top."""
    def __init__(self, r=20.0, h=24.0, top=0.5, sector=360.0):
        super().__init__(r=r, h=h, sector=sector)
        self.top = float(top)

    def radius_at(self, level):
        return self.top + 1 - level


def test_binds_a_facet_on_the_wall_to_its_cylinder():
    cyl = FakeCylinder(r=20.0)
    on_wall = np.array([[20.0, 1.0, 0.0], [19.6, 1.0, 4.0], [20.0, 5.0, 0.0]])
    assert unwrap.bind(on_wall, [cyl]) is cyl


def test_flat_ink_at_a_rounded_corner_does_not_bind_to_the_corner_wall():
    """6148328s's red field runs to its tile's rounded corners, within reach of
    the 1.5-LDU corner cylinders. Walls are tried first, so all 46 corner
    triangles bound there and unwrapped to zero width."""
    corner = FakeCylinder(r=1.5, h=2.0)
    flat = np.array([[1.5, 0.5, 0.0], [1.6, 0.5, 0.3], [1.3, 0.5, 0.4]])
    assert unwrap.bind(flat, [corner]) is None
    top = unwrap.Plane(normal=np.array([0.0, 1.0, 0.0]), offset=0.5)
    assert unwrap.bind(flat, [top]) is top


def test_the_plane_a_print_lies_along_beats_a_nearer_tilted_one():
    """4215ad0a's sticker covers its face, so the nearest plane parallel to the
    print is 0.25 LDU behind it, and planes of the mould's tiny tilted facets
    cross the letters nearer than that."""
    print_ = np.array([[0.0, 0.0, 0.3], [1.0, 0.0, 0.3], [0.0, 1.0, 0.3]])
    face = unwrap.Plane(normal=np.array([0.0, 0.0, 1.0]), offset=0.0)
    s, c = np.sin(np.radians(7.0)), np.cos(np.radians(7.0))
    tilted = unwrap.Plane(normal=np.array([s, 0.0, c]), offset=0.3 * c + 0.06)
    assert unwrap._gap(print_, tilted) < unwrap._gap(print_, face)
    assert unwrap.bind(print_, [tilted, face]) is face
    assert unwrap.bind(print_, [face, tilted]) is face


def test_does_not_bind_geometry_further_than_the_tolerance():
    cyl = FakeCylinder(r=20.0)
    standoff = np.array([[24.0, 1.0, 0.0], [24.0, 1.0, 4.0], [24.0, 5.0, 0.0]])
    assert unwrap.bind(standoff, [cyl]) is None


def test_tolerance_is_half_an_ldu():
    """0.5 LDU binds every measured case (3040bp08 worst at 0.345) with an
    order of magnitude under the smallest real feature (a stud is 12 across)."""
    assert unwrap.BIND_TOL == 0.5


def test_unbound_geometry_is_left_as_authored():
    """An unrecognized construction must degrade to today's output, never
    raise — 4,764 printed parts, most never eyeballed."""
    weird = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    assert unwrap.bind(weird, []) is None


def test_cylinder_unwrap_uses_arc_length_not_degrees():
    """Degrees against LDU is an arbitrary aspect; arc length makes the
    texture isometric with the surface, so a round lamp stays round."""
    cyl = FakeCylinder(r=20.0)
    quarter = np.array([[20.0, 0.0, 0.0], [0.0, 0.0, 20.0]])
    uv = unwrap.to_uv(quarter, cyl)
    assert uv[:, 1] == pytest.approx([0.0, 0.0])
    # a quarter turn at r=20 is 20 * pi/2 of arc. Magnitude, because this
    # cylinder's axis is +Y and `axis_reversed` turns its unwrap 180 degrees.
    assert abs(uv[1, 0] - uv[0, 0]) == pytest.approx(20.0 * np.pi / 2, rel=1e-6)


def test_cylinder_unwrap_round_trips():
    cyl = FakeCylinder(r=20.0)
    pts = np.array([[20.0, 3.0, 0.0], [0.0, 7.0, 20.0], [-20.0, 1.0, 0.0]])
    back = unwrap.to_xyz(unwrap.to_uv(pts, cyl), cyl)
    assert back == pytest.approx(pts, abs=1e-9)


class FakeShearedCylinder(FakeCylinder):
    """15068d02's carrier: LDraw's unit `cyli` through a shearing matrix, so
    the section is an ellipse. Both radial columns are the same length and
    square to the axis, but they are 108.2 degrees apart, not 90."""

    def __init__(self, r=49.39, h=40.0, shear_deg=108.2):
        super().__init__(r=r, h=h)
        th = np.radians(shear_deg)
        self.R = np.column_stack([[r, 0.0, 0.0],
                                  [0.0, h, 0.0],
                                  [r * np.cos(th), 0.0, r * np.sin(th)]])


def _on_wall(prim, theta, level):
    """Points on a primitive's EXACT wall, shear and all."""
    local = np.column_stack([np.cos(theta), level, np.sin(theta)])
    return np.asarray(prim.t, float) + local @ np.asarray(prim.R, float).T


def test_a_sheared_cylinder_round_trips():
    """The unwrap read every carrier as circular, so a decal on a sheared one
    came back on a circle that meets the true section in one place -- 15068d02
    hinged its sticker there and lifted the rest 8.2 LDU off the slope."""
    cyl = FakeShearedCylinder()
    pts = _on_wall(cyl, np.linspace(0.1, 1.2, 6), np.linspace(0.1, 0.9, 6))
    back = unwrap.to_xyz(unwrap.to_uv(pts, cyl), cyl)
    assert back == pytest.approx(pts, abs=1e-9)


def test_faceted_ring_reprojects_onto_the_exact_radius():
    """The point of the whole exercise: chord midpoints authored at r=19.616
    (a 16-gon inscribed in r=20) come back at exactly 20."""
    cyl = FakeCylinder(r=20.0)
    th = np.linspace(0, 2 * np.pi, 17)[:-1] + np.pi / 16
    chord = np.column_stack([19.616 * np.cos(th),
                             np.zeros(16), 19.616 * np.sin(th)])
    back = unwrap.to_xyz(unwrap.to_uv(chord, cyl), cyl)
    assert np.hypot(back[:, 0], back[:, 2]) == pytest.approx(20.0, abs=1e-9)


def test_planar_unwrap_is_the_identity_in_the_face_basis():
    plane = unwrap.Plane(normal=np.array([0.0, 1.0, 0.0]), offset=2.0)
    pts = np.array([[3.0, 2.0, 5.0], [-1.0, 2.0, 4.0]])
    back = unwrap.to_xyz(unwrap.to_uv(pts, plane), plane)
    assert back == pytest.approx(pts, abs=1e-9)


def test_texture_canvas_comes_from_the_carrier_not_the_decal():
    """Scaling the decal's own bbox to a fixed canvas warps it — round lamps
    become ellipses. The carrier's extent and ONE scale factor fix that."""
    carrier_uv = np.array([[0.0, 0.0], [40.0, 0.0], [40.0, 20.0], [0.0, 20.0]])
    decal_uv = [np.array([[10.0, 8.0], [14.0, 8.0], [14.0, 12.0], [10.0, 12.0]])]
    svg = unwrap.texture_svg(carrier_uv, [(4, decal_uv[0])], px=400)
    assert 'width="400"' in svg and 'height="200"' in svg   # 40:20, not 1:1


def test_texture_paints_each_region_in_its_ldraw_color():
    carrier_uv = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    region = np.array([[2.0, 2.0], [8.0, 2.0], [8.0, 8.0], [2.0, 8.0]])
    svg = unwrap.texture_svg(carrier_uv, [(14, region)], px=100)
    assert "#fac80a" in svg.lower()      # LDraw 14, Yellow


def test_curved_carrier_supplies_its_own_canvas_extent():
    """A cylinder's canvas is its full wrap by its full height, so the decal
    sits where it really lies on the part rather than filling the frame."""
    ext = unwrap.carrier_extent(FakeCylinder(r=20.0, h=24.0))
    assert ext[:, 0].min() == pytest.approx(-20.0 * np.pi)
    assert ext[:, 0].max() == pytest.approx(20.0 * np.pi)
    # Spans, not endpoints: this cylinder's axis is +Y, so its canvas runs
    # -h to 0 rather than 0 to h. Same rectangle either way.
    assert ext[:, 1].max() - ext[:, 1].min() == pytest.approx(24.0)


def _axis(vec, r=20.0, h=24.0):
    """A cylinder whose axis is `vec`, everything else square."""
    cyl = FakeCylinder(r=r, h=h)
    a = np.asarray(vec, float)
    a = a / np.linalg.norm(a)
    other = np.array([1.0, 0.0, 0.0])
    if abs(float(a @ other)) > 0.9:
        other = np.array([0.0, 0.0, 1.0])
    e1 = np.cross(a, other)
    e1 /= np.linalg.norm(e1)
    cyl.R = np.column_stack([r * e1, h * a, r * np.cross(a, e1)])
    return cyl


def test_an_axis_pointing_ldraw_down_is_reversed():
    """A minifig head's wall cylinder is authored +Y, which is LDraw DOWN, so
    its face unwrapped upside down until the axis was oriented."""
    assert unwrap.axis_reversed(_axis([0.0, 1.0, 0.0]))
    assert not unwrap.axis_reversed(_axis([0.0, -1.0, 0.0]))


def test_a_carrier_on_its_side_is_decided_by_plus_z():
    """No up to inherit, so +Z breaks the tie — the same fallback
    `up_aligned` takes on a top or bottom face."""
    assert not unwrap.axis_reversed(_axis([0.0, 0.0, 1.0]))
    assert unwrap.axis_reversed(_axis([0.0, 0.0, -1.0]))
    # and the tie-break must not reach a carrier that does have an up
    assert not unwrap.axis_reversed(_axis([0.0, -1.0, 0.2]))


def test_reversing_an_axis_rotates_rather_than_mirrors():
    """Both components negate together, so glyphs turn instead of flipping.
    A mirror would reverse the sign of the unwrap's cross product."""
    down, up = _axis([0.0, 1.0, 0.0]), _axis([0.0, -1.0, 0.0])
    pts = np.array([[20.0, 4.0, 0.0], [0.0, 4.0, 20.0], [20.0, 9.0, 0.0]])

    def handedness(cyl):
        uv = unwrap.to_uv(pts, cyl)
        e0, e1 = uv[1] - uv[0], uv[2] - uv[0]
        return np.sign(e0[0] * e1[1] - e0[1] * e1[0])

    assert handedness(down) == handedness(up)


def test_a_reversed_carrier_still_round_trips():
    cyl = _axis([0.0, 1.0, 0.0])
    assert unwrap.axis_reversed(cyl)
    pts = np.array([[20.0, 3.0, 0.0], [0.0, 7.0, 20.0], [-20.0, 1.0, 0.0]])
    back = unwrap.to_xyz(unwrap.to_uv(pts, cyl), cyl)
    assert back == pytest.approx(pts, abs=1e-9)


def test_a_curved_canvas_holds_ink_that_overruns_the_wall():
    """A minifig head's print runs onto the dome its wall cylinder stops at.
    The canvas is the SVG's viewport, so ink past the section is cut, not
    merely off-center."""
    cyl = _axis([0.0, -1.0, 0.0], r=20.0, h=24.0)
    over = np.array([[-3.0, -1.5], [5.0, 25.5]])
    ext = unwrap.carrier_extent(cyl, over)
    assert (ext[:, 1].min(), ext[:, 1].max()) == pytest.approx((-1.5, 25.5))


def test_a_narrow_print_on_a_wide_wall_fills_its_canvas():
    """15068dy6 prints 35 LDU of ink on a 45-degree wall whose full turn is
    310 LDU; a canvas the size of the turn drew it as a speck."""
    cyl = _axis([0.0, -1.0, 0.0], r=20.0, h=24.0)
    ink = np.array([[2.0, 3.0], [9.0, 20.0]])
    ext = unwrap.carrier_extent(cyl, ink)
    assert (ext[:, 0].min(), ext[:, 0].max()) == pytest.approx((2.0, 9.0))
    assert (ext[:, 1].min(), ext[:, 1].max()) == pytest.approx((3.0, 20.0))


def test_a_plane_falls_back_to_the_decal_bounds():
    plane = unwrap.Plane(normal=np.array([0.0, 1.0, 0.0]), offset=0.0)
    uv = np.array([[1.0, 2.0], [5.0, 2.0], [5.0, 9.0]])
    ext = unwrap.carrier_extent(plane, uv)
    assert (ext[:, 0].min(), ext[:, 0].max()) == pytest.approx((1.0, 5.0))
    assert (ext[:, 1].min(), ext[:, 1].max()) == pytest.approx((2.0, 9.0))


def test_a_cylinder_does_not_bind_past_its_own_ends():
    """A cylinder's radial gap alone is an INFINITE cylinder: 3941p01's panel
    facets sat at stud radius far below the studs and bound to them, landing
    at v = -794 LDU on the texture."""
    cyl = FakeCylinder(r=20.0, h=24.0)
    below = np.array([[20.0, -60.0, 0.0], [19.6, -60.0, 4.0],
                      [20.0, -56.0, 0.0]])
    assert unwrap.bind(below, [cyl]) is None


def test_a_sector_bounds_what_a_primitive_draws_not_where_its_surface_is():
    """3941p01's r=20 wall is substituted only over two 90 deg sectors; the
    rest is hand-authored facets, and the panel sits at 125 deg. Same axis,
    same radius and an overlapping height IS the same surface of revolution,
    so the drawn sector must not gate the bind or no panel binds at all."""
    quarter_wall = FakeCylinder(r=20.0, h=24.0, sector=90.0)
    off_sector = np.array([[-20.0, 1.0, 0.0], [-19.6, 1.0, -4.0],
                           [-20.0, 5.0, 0.0]])
    assert unwrap.bind(off_sector, [quarter_wall]) is quarter_wall


def test_a_cone_binds_on_its_taper_not_on_one_radius():
    """3942bp01's stripes ride a cone, whose radius is 30 LDU at the base and
    10 at the top. Measuring against the single radius |R[:,0]| = 20 binds
    neither ring; the taper law binds both."""
    cone = FakeCone(r=20.0, h=24.0, top=0.5)
    base = np.array([[30.0, 0.0, 0.0], [29.4, 0.0, 6.0], [29.6, 1.0, 0.0]])
    assert unwrap.bind(base, [cone]) is cone
    # 20 LDU is the cone's radius only halfway up, not at the base
    off = np.array([[20.0, 0.0, 0.0], [19.6, 0.0, 4.0], [20.0, 1.0, 0.0]])
    assert unwrap.bind(off, [cone]) is None


def test_two_facets_sharing_an_edge_merge_to_one_four_corner_region():
    a = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
    b = np.array([[2.0, 0.0], [4.0, 0.0], [4.0, 2.0], [2.0, 2.0]])
    merged = unwrap.merge_regions([(4, a), (4, b)])
    assert len(merged) == 1
    code, g = merged[0]
    assert code == 4
    rings = geom2d.rings(g)
    assert len(rings) == 1
    assert len(rings[0]) == 4                  # the shared edge is gone


def test_different_colors_stay_separate_regions():
    a = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
    b = np.array([[2.0, 0.0], [4.0, 0.0], [4.0, 2.0], [2.0, 2.0]])
    assert len(unwrap.merge_regions([(4, a), (14, b)])) == 2


def test_a_hole_survives_the_merge():
    """3941p01's buttons are body-colored discs INSIDE the black panel: the
    panel region must keep them as holes, not swallow them."""
    outer = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    merged = unwrap.merge_regions([(0, outer)],
                                  holes=[np.array([[4.0, 4.0], [6.0, 4.0],
                                                   [6.0, 6.0], [4.0, 6.0]])])
    assert len(merged) == 1
    assert unwrap.region_has_hole(merged[0][1])


def _wall_quads(cyl, a0_deg, a1_deg, v0, v1, step=10):
    """Triangles tiling a patch of a cylinder wall between two angles."""
    r = float(np.linalg.norm(cyl.R[:, 0]))
    tris = []
    edges = np.radians(np.arange(a0_deg, a1_deg + step, step))
    for t0, t1 in zip(edges[:-1], edges[1:]):
        c = [(np.array([r * np.cos(t), v, r * np.sin(t)]))
             for t in (t0, t1) for v in (v0, v1)]
        tris += [np.array([c[0], c[2], c[3]]), np.array([c[0], c[3], c[1]])]
    return tris


def test_a_decal_straddling_the_branch_cut_stays_one_region():
    """3941p01's second panel sits across theta = +-pi. Cutting the cylinder
    at a fixed angle splits it into two regions that can never merge, fit as
    one rounded rectangle, or stroke as one boundary."""
    cyl = FakeCylinder(r=20.0, h=24.0)
    tris = _wall_quads(cyl, 160, 200, 4.0, 8.0)
    (_carrier, _t0, regions), = unwrap.bind_groups(tris, [4] * len(tris), [cyl])
    merged = unwrap.merge_regions(regions)
    assert len(merged) == 1
    assert len(geom2d.rings(merged[0][1])) == 1


def test_the_branch_cut_does_not_move_a_decal_that_never_crosses_it():
    cyl = FakeCylinder(r=20.0, h=24.0)
    tris = _wall_quads(cyl, 10, 50, 4.0, 8.0)
    (_carrier, _t0, regions), = unwrap.bind_groups(tris, [4] * len(tris), [cyl])
    merged = unwrap.merge_regions(regions)
    assert len(geom2d.rings(merged[0][1])) == 1


def test_a_16gon_fan_is_recovered_as_a_circle():
    """3040bp08's lamps and 3941p01's buttons are 16-gon fans, not circles."""
    th = np.linspace(0, 2 * np.pi, 17)[:-1]
    poly = np.column_stack([3.0 + 2.0 * np.cos(th), 5.0 + 2.0 * np.sin(th)])
    fit = unwrap.fit_circle(poly)
    assert fit is not None
    cx, cy, r = fit
    assert (cx, cy) == pytest.approx((3.0, 5.0), abs=1e-6)
    assert r == pytest.approx(2.0, rel=1e-3)


def test_a_square_is_not_mistaken_for_a_circle():
    square = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])
    assert unwrap.fit_circle(square) is None


def test_a_poor_fit_is_rejected_rather_than_forced():
    """An egg — a circle stretched 30% on one axis — must not pass."""
    th = np.linspace(0, 2 * np.pi, 17)[:-1]
    egg = np.column_stack([2.6 * np.cos(th), 2.0 * np.sin(th)])
    assert unwrap.fit_circle(egg) is None


def test_region_path_emits_arc_commands_for_a_recovered_circle():
    th = np.linspace(0, 2 * np.pi, 17)[:-1]
    poly = np.column_stack([3.0 + 2.0 * np.cos(th), 5.0 + 2.0 * np.sin(th)])
    # the fitted outline is the first subpath; the polygon under it follows
    d = unwrap.region_path(geom2d.to_geom(poly)).split(" Z")[0]
    assert "A" in d              # true arcs, not 16 L commands
    assert d.count("L") <= 2


def _rounded_rect_ring(x0, y0, x1, y1, r, n=4):
    """A rounded rectangle drawn the way LDraw authors one: straight runs
    joined by corner fans of `n` segments each."""
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, 270.0), (x1 - r, y1 - r, 0.0),
                       (x0 + r, y1 - r, 90.0), (x0 + r, y0 + r, 180.0)):
        for a in np.linspace(a0, a0 + 90.0, n + 1):
            t = np.radians(a)
            pts.append([cx + r * np.cos(t), cy + r * np.sin(t)])
    return np.array(pts)


def test_a_rounded_rectangle_is_recovered_from_its_corner_fans():
    """3941p01's panel and 3040bp08's border are this shape, and both emit as
    many-vertex polygons with square corners until it is recognised."""
    ring = _rounded_rect_ring(-8.0, 2.0, 8.0, 12.0, 2.0)
    fit = unwrap.fit_rounded_rect(ring)
    assert fit is not None
    assert fit == pytest.approx((-8.0, 2.0, 8.0, 12.0, 2.0), abs=1e-6)


def test_a_plain_rectangle_reports_no_corner_radius():
    """Four L commands is already the minimal emission; a forced rx would
    round corners the part does not round."""
    square = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])
    assert unwrap.fit_rounded_rect(square) is None


def test_a_circle_is_not_mistaken_for_a_rounded_rectangle():
    th = np.linspace(0, 2 * np.pi, 17)[:-1]
    circle = np.column_stack([2.0 * np.cos(th), 2.0 * np.sin(th)])
    assert unwrap.fit_rounded_rect(circle) is None


def test_region_path_rounds_the_corners_of_a_panel():
    ring = _rounded_rect_ring(-8.0, 2.0, 8.0, 12.0, 2.0)
    d = unwrap.region_path(geom2d.to_geom(ring)).split(" Z")[0]
    assert d.count("L") == 4          # one per straight run, not 20 chords
    assert d.count("A") == 4          # one per corner


def test_reprojection_closes_the_sagitta_gap():
    """3941p01's panel is authored as a 16-gon inscribed in the r=20 wall, so
    its chord midpoints fall 0.384 LDU inside the cylinder and open a white
    seam. After the round trip every point is ON the wall."""
    cyl = FakeCylinder(r=20.0)
    th = np.linspace(0, 2 * np.pi, 17)[:-1]
    verts = np.column_stack([20.0 * np.cos(th), np.zeros(16),
                             20.0 * np.sin(th)])
    mids = (verts + np.roll(verts, -1, axis=0)) / 2
    assert np.hypot(mids[:, 0], mids[:, 2]).min() < 19.7          # the gap
    fixed = unwrap.to_xyz(unwrap.to_uv(mids, cyl), cyl)
    assert np.hypot(fixed[:, 0], fixed[:, 2]) == pytest.approx(20.0, abs=1e-9)


def test_geometry_binding_to_no_carrier_is_untouched():
    """4,764 printed parts, most never eyeballed: an unrecognized
    construction must degrade to today's output, not raise."""
    weird = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]])
    assert unwrap.decorate(weird, [4], carriers=[]) == []


def test_decorate_returns_one_region_per_color_on_a_carrier():
    cyl = FakeCylinder(r=20.0, h=24.0)
    tris = _wall_quads(cyl, 10, 50, 4.0, 8.0)
    out = unwrap.decorate(tris, [4] * len(tris), [cyl])
    assert len(out) == 1
    code, carrier, _theta0, g = out[0]
    assert code == 4 and carrier is cyl
    assert len(geom2d.rings(g)) == 1


def test_decorate_leaves_body_geometry_alone():
    cyl = FakeCylinder(r=20.0, h=24.0)
    tris = _wall_quads(cyl, 10, 50, 4.0, 8.0)
    assert unwrap.decorate(tris, [16] * len(tris), [cyl]) == []


def test_a_reprojected_region_lands_back_on_the_wall():
    """The whole point: the boundary comes back on the exact carrier, which
    is what closes the sagitta seam under the print."""
    cyl = FakeCylinder(r=20.0, h=24.0)
    tris = _wall_quads(cyl, 10, 50, 4.0, 8.0)
    code, carrier, theta0, g = unwrap.decorate(tris, [4] * len(tris), [cyl])[0]
    ring = geom2d.rings(g)[0]
    back = unwrap.to_xyz(ring, carrier, theta0)
    assert np.hypot(back[:, 0], back[:, 2]) == pytest.approx(20.0, abs=1e-6)


def test_cone_unwrap_round_trips_on_the_taper():
    """A cone's radius varies with height, so mapping back at the base radius
    puts every point on a cylinder instead — 3942bp01's stripes would land off
    the wall, further out the higher they sit."""
    cone = FakeCone(r=20.0, h=24.0, top=0.5)
    pts = []
    for level in (0.0, 0.4, 1.0):
        rad = 20.0 * (0.5 + 1 - level)
        for th in (0.3, 2.0, -1.7):
            pts.append([rad * np.cos(th), level * 24.0, rad * np.sin(th)])
    pts = np.array(pts)
    back = unwrap.to_xyz(unwrap.to_uv(pts, cone), cone)
    assert back == pytest.approx(pts, abs=1e-9)


def test_decal_paints_its_ldraw_color_as_one_element(tmp_path):
    """The panel never painted at all before the color rode out of flatten,
    and painted as six separately-stroked fragments before the union moved to
    UV. One path in the part's own black is both fixes at once."""
    import re

    from brick_icons import cli

    out = tmp_path / "o"
    cli.main(["3941p01", "--root", ".", "--format", "svg",
              "--shading", "outline", "--shade-style", "flat3",
              "--out", str(out)])
    svg = (out / "3941p01.svg").read_text()
    assert len(re.findall(r'fill="#1b2a34"', svg)) == 1     # LDraw 0, Black


# --- extraction: the `decal` subcommand's pipeline ---------------------------

def _quad_tris(corners):
    """Two CCW triangles for a planar quad, as faces_from_tris expects."""
    p = np.asarray(corners, float)
    return [p[[0, 1, 2]], p[[0, 2, 3]]]


def test_a_flat_print_binds_to_its_face_not_a_nearby_primitive():
    """890p01's stop sign sits on a flat octagon, but the only carriers the
    extraction offered were analytic PRIMITIVES, so it snapped to a disc of
    the clip behind it and unwrapped through a circle frame."""
    from brick_icons import primitives

    face = _quad_tris([[-20, 0, -10], [20, 0, -10], [20, 40, -10], [-20, 40, -10]])
    print_ = _quad_tris([[-5, 10, -10], [5, 10, -10], [5, 20, -10], [-5, 20, -10]])
    disc = primitives.Disc(R=np.diag([6.0, 1.0, 6.0]), t=np.array([0.0, 0.0, -9.0]),
                           sector=360.0, color=16)
    tris = face + print_
    colors = [16, 16, 4, 4]
    groups = unwrap.decal_groups(tris, colors, [disc])
    assert len(groups) == 1
    carrier, _theta0, regions, _face = groups[0]
    assert isinstance(carrier, unwrap.Plane)
    assert len(regions) == 1


#: LDraw up is -y, so a sticker's printed side is its -y face and the sheet
#: is 0.25 LDU thick.
STICKER_TOP, STICKER_BACK = -0.25, 0.0


def _sticker(margin: bool):
    """(tris, colors) for a printed sheet, with or without a bare border.

    `margin` is the whole variable: 190265d leaves unprinted sticker around
    its artwork and reads correctly, while 6041468c is printed edge to edge
    and comes out mirrored.
    """
    back = _quad_tris([[-20, STICKER_BACK, -10], [20, STICKER_BACK, -10],
                       [20, STICKER_BACK, 10], [-20, STICKER_BACK, 10]])
    if margin:
        border = _quad_tris([[-20, STICKER_TOP, -10], [20, STICKER_TOP, -10],
                             [20, STICKER_TOP, -8], [-20, STICKER_TOP, -8]])
        print_ = _quad_tris([[-20, STICKER_TOP, -8], [20, STICKER_TOP, -8],
                             [20, STICKER_TOP, 10], [-20, STICKER_TOP, 10]])
        return back + border + print_, [16, 16, 16, 16, 4, 4]
    print_ = _quad_tris([[-20, STICKER_TOP, -10], [20, STICKER_TOP, -10],
                         [20, STICKER_TOP, 10], [-20, STICKER_TOP, 10]])
    return back + print_, [16, 16, 4, 4]


def _only_carrier(tris, colors):
    groups = unwrap.decal_groups(tris, colors, [])
    assert len(groups) == 1
    return groups[0][0]


def test_a_full_bleed_print_carries_on_the_face_it_is_printed_on():
    """Artwork covering its face edge to edge leaves that face with no body
    facets, so no plane is built for it and the print binds to the face
    BEHIND it -- whose outward normal is antiparallel, which hands
    `up_aligned` a mirrored frame."""
    tris, colors = _sticker(margin=False)
    carrier = _only_carrier(tris, colors)
    n = carrier.basis()[0]
    print_pts = np.vstack(tris[-2:])
    # the print lies ON its carrier, never a sheet's thickness behind it
    assert float(np.median(print_pts @ n)) - carrier.offset == pytest.approx(0.0, abs=1e-6)


def test_a_bare_margin_does_not_change_which_way_a_print_reads():
    """The two sticker shapes differ only in whether the printed face keeps
    any unprinted body, which must not decide the print's handedness."""
    full = _only_carrier(*_sticker(margin=False))
    margined = _only_carrier(*_sticker(margin=True))
    # basis() is (normal, u, v); a flipped normal flips u and mirrors the UV
    assert np.allclose(full.basis()[1], margined.basis()[1])
    assert np.allclose(full.basis()[2], margined.basis()[2])


def test_the_carrier_face_is_the_whole_face_print_included():
    """The print REPLACES the body facets under it, so unioning color 16
    alone leaves the strips around a torso's stripes, not the torso's front."""
    left = _quad_tris([[-20, 0, 0], [-5, 0, 0], [-5, 40, 0], [-20, 40, 0]])
    right = _quad_tris([[5, 0, 0], [20, 0, 0], [20, 40, 0], [5, 40, 0]])
    stripe = _quad_tris([[-5, 0, 0], [5, 0, 0], [5, 40, 0], [-5, 40, 0]])
    tris = left + right + stripe
    colors = [16, 16, 16, 16, 4, 4]
    groups = unwrap.decal_groups(tris, colors, [])
    assert len(groups) == 1
    face = groups[0][3]
    assert face is not None
    # one rectangle spanning both body strips AND the print between them
    assert face.area == pytest.approx(40.0 * 40.0)


def test_stacked_wall_sections_extract_as_one_texture():
    """LDraw tiles a tall cone as stacked sections — 3942bp01's is four. Left
    as separate carriers a stripe running down them becomes four textures."""
    from brick_icons import primitives

    lower = primitives.Cylinder(R=np.diag([10.0, 12.0, 10.0]),
                                t=np.zeros(3), sector=360.0, color=16)
    upper = primitives.Cylinder(R=np.diag([10.0, 12.0, 10.0]),
                                t=np.array([0.0, 12.0, 0.0]),
                                sector=360.0, color=16)
    assert unwrap._wall_family(lower) == unwrap._wall_family(upper)
    span = unwrap.span_carrier([lower, upper])
    assert float(np.linalg.norm(span.R[:, 1])) == pytest.approx(24.0)
    assert float(np.linalg.norm(span.R[:, 0])) == pytest.approx(10.0)


def test_a_cylinder_family_does_not_become_a_needle_cone():
    """Every radius in a cylinder family is identical and its heights repeat,
    which is ill-conditioned enough that a least-squares slope comes back at
    ~1e-6 — and the wall spans a radius of 8e-5 instead of 20."""
    from brick_icons import primitives

    secs = [primitives.Cylinder(R=np.diag([20.0, 4.0, 20.0]),
                                t=np.array([0.0, y, 0.0]),
                                sector=360.0, color=16)
            for y in (0.0, 4.0, 8.0)]
    span = unwrap.span_carrier(secs)
    assert span.kind == "cyli"
    assert float(np.linalg.norm(span.R[:, 0])) == pytest.approx(20.0)


def test_a_connector_marking_is_not_extracted():
    """LDraw authors a minifig neck as a 270-degree color-16 cylinder plus a
    90-degree one in black. The head covers it, and nothing in its authoring
    tells it from print."""
    from brick_icons import primitives

    body = _quad_tris([[-19, 0, -10], [19, 0, -10], [19, 32, -10], [-19, 32, -10]])
    neck = primitives.Cylinder(R=np.diag([6.0, -8.0, 6.0]),
                               t=np.array([0.0, -4.0, 0.0]),
                               sector=270.0, color=16)
    mark = primitives.Cylinder(R=np.diag([6.0, -8.0, 6.0]),
                               t=np.array([0.0, -4.0, 0.0]),
                               sector=90.0, color=0)
    marks = unwrap.marker_prims([neck, mark], body, [16, 16])
    assert id(mark) in marks and id(neck) not in marks


def test_a_print_on_the_body_survives_the_marker_filter():
    """3942bp01's stripes partition their wall into colored and color-16
    sectors summing to 360 exactly as the neck does — only position separates
    them, so a share test alone would drop real print."""
    from brick_icons import primitives

    body = _quad_tris([[-20, 0, -10], [20, 0, -10], [20, 40, -10], [-20, 40, -10]])
    wall = primitives.Cylinder(R=np.diag([10.0, 8.0, 10.0]),
                               t=np.array([0.0, 10.0, 0.0]),
                               sector=270.0, color=16)
    stripe = primitives.Cylinder(R=np.diag([10.0, 8.0, 10.0]),
                                 t=np.array([0.0, 10.0, 0.0]),
                                 sector=90.0, color=4)
    assert unwrap.marker_prims([wall, stripe], body, [16, 16]) == set()


def test_an_unmeasurable_part_keeps_its_decoration():
    """With no body triangles there is nothing to measure clearance against,
    so the filter must abstain rather than guess."""
    from brick_icons import primitives

    mark = primitives.Cylinder(R=np.diag([6.0, -8.0, 6.0]),
                               t=np.array([0.0, -4.0, 0.0]),
                               sector=90.0, color=0)
    assert unwrap.marker_prims([mark], [], []) == set()


def test_decoration_authored_as_primitives_is_extracted():
    """3942bp01 is 16 colored cone sectors and NO colored facets, so a
    triangle-only extraction emits an empty texture for it."""
    from brick_icons import primitives

    body = _quad_tris([[-20, 0, -10], [20, 0, -10], [20, 40, -10], [-20, 40, -10]])
    wall = primitives.Cylinder(R=np.diag([10.0, 8.0, 10.0]),
                               t=np.array([0.0, 10.0, 0.0]),
                               sector=360.0, color=16)
    stripe = primitives.Cylinder(R=np.diag([10.0, 8.0, 10.0]),
                                 t=np.array([0.0, 10.0, 0.0]),
                                 sector=90.0, color=4)
    groups = unwrap.decal_groups(body, [16, 16], [wall, stripe])
    assert any(any(code == 4 for code, _g in regions)
               for _c, _t, regions, _f in groups)


def test_the_texture_background_is_optional():
    """A decal is a texture; a white ground makes a white print invisible."""
    carrier_uv = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    region = np.array([[2.0, 2.0], [8.0, 2.0], [8.0, 8.0], [2.0, 8.0]])
    assert "<rect" not in unwrap.texture_svg(carrier_uv, [(15, region)],
                                             px=100, bg=None)
    assert "<rect" in unwrap.texture_svg(carrier_uv, [(15, region)],
                                         px=100, bg="#ffffff")


def test_extraction_needs_no_view_pipeline():
    """Decoration binds in world space, so a decal needs flatten + repair and
    nothing a camera does. Going through visible_segments for it costs 99
    seconds on a high-poly torso against 0.04 — but only if the geometry it
    hands over is the same geometry."""
    from brick_icons import hlr
    from brick_icons.config import load_config

    cfg = load_config()
    res = hlr.visible_segments("3941p01", cfg.ldraw_dir, render_px=400)
    tri, tri_colors, analytic = hlr.part_geometry("3941p01", cfg.ldraw_dir)
    assert (unwrap.decal_svgs(tri, tri_colors, analytic,
                              ldraw_dir=cfg.ldraw_dir)
            == unwrap.decal_svgs(res.tri, res.tri_colors, res.analytic,
                                 ldraw_dir=cfg.ldraw_dir))


def test_circle_candidates_finds_concentric_rings():
    """An emblem is often several concentric arcs joined by straight runs, so
    'is this whole ring one circle' is the wrong question to ask of it."""
    th = np.linspace(0, 2 * np.pi, 33)[:-1]
    ring = np.vstack([np.column_stack([r * np.cos(th), r * np.sin(th)])
                      for r in (6.0, 18.0)])
    radii = sorted(round(r, 2) for _cx, _cy, r in unwrap.circle_candidates(ring))
    assert radii == pytest.approx([6.0, 18.0], abs=0.05)


def test_a_ring_with_strays_still_recovers_its_circle():
    """Unioning a 48-gon with a 16-gon leaves the coarser one's chord
    midpoints 0.345 LDU inside the rim (14769pt1's emblem), which is 17x
    CIRCLE_TOL — enough to make a whole-ring fit refuse a true circle."""
    th = np.linspace(0, 2 * np.pi, 49)[:-1]
    pts = np.column_stack([18 * np.cos(th), 18 * np.sin(th)])
    pts[::6] *= 17.655 / 18.0                    # the coarse polygon's midpoints
    assert unwrap.fit_circle(pts) is None        # whole-ring fit refuses it
    cands = unwrap.circle_candidates(pts)
    assert cands and cands[0][2] == pytest.approx(18.0, abs=0.15)


def test_an_octagon_is_not_rounded_into_a_circle():
    """30260p01's stop sign has 8 vertices on a common radius, so a circle fit
    matches it exactly. ARC_STEP is what keeps it a sign: 45 degrees a step is
    too coarse to read as an arc."""
    th = np.linspace(0, 2 * np.pi, 9)[:-1] + np.pi / 8
    octagon = np.column_stack([20 * np.cos(th), 20 * np.sin(th)])
    d = unwrap.region_path(geom2d.to_geom(octagon))
    assert "A" not in d
    assert d.count("L") == 8         # 7 edges plus the closing one


def test_a_round_tile_binds_its_print_to_the_face_not_the_disc():
    """to_uv sends every non-Plane carrier through the cylindrical map, where
    a flat surface has ONE height — so a print on a round tile's top, which is
    a disc primitive, unwrapped to a zero-area line and vanished entirely."""
    from brick_icons import primitives

    disc = primitives.Disc(R=np.diag([20.0, 1.0, 20.0]), t=np.zeros(3),
                           sector=360.0, color=16)
    th = np.linspace(0, 2 * np.pi, 25)[:-1]
    rim = np.column_stack([18 * np.cos(th), np.zeros(len(th)), 18 * np.sin(th)])
    tris = [np.array([rim[i], rim[(i + 1) % len(rim)], [0.0, 0.0, 0.0]])
            for i in range(len(rim))]
    groups = unwrap.decal_groups(tris, [4] * len(tris), [disc])
    assert groups, "a flat print on a disc must not unwrap to nothing"
    assert sum(r.area for _c, r in groups[0][2]) > 100.0


def _group(area):
    """A decal_groups tuple whose only load-bearing field is its print area."""
    class _R:
        def __init__(self, a): self.area = a
    return (None, 0.0, [(4, _R(area))], None)


def test_slivers_below_a_fraction_of_the_main_print_are_dropped():
    """A torso scatters one print across dozens of facet planes: 16360pd1d
    emits 59 groups of which only .0 is the garment. The rest are shards a
    tenth the size or less and nothing renders them usefully."""
    groups = [_group(100.0), _group(30.0), _group(9.0), _group(0.4)]
    kept = unwrap.significant_groups(groups)
    assert [g[2][0][1].area for g in kept] == [100.0, 30.0]


def test_a_shattered_print_yields_nothing_rather_than_its_biggest_shard():
    """10128p01 splits one decoration across 156 carriers, the largest holding
    8.7% of the printed area. Its .0 and .1 are both structureless fragments,
    so emitting the biggest would hand back a shard dressed as a decal."""
    groups = [_group(10.0), _group(8.0)] + [_group(7.0)] * 12
    assert unwrap.significant_groups(groups) == []


def test_a_dominant_print_survives_alongside_a_real_second_face():
    """The gate keys on the LARGEST group's share of total print area, so a
    part with a front and a back print keeps both — the failure to avoid is
    mistaking two-sided decoration for shatter."""
    groups = [_group(100.0), _group(80.0)]
    kept = unwrap.significant_groups(groups)
    assert [g[2][0][1].area for g in kept] == [100.0, 80.0]


def test_a_part_that_stays_a_pile_after_filtering_yields_nothing():
    """Third part-level verdict, after slivers and shatter. 22472p01 keeps 18
    groups and 1023000p02 keeps 12: each survivor clears the sliver bar and the
    dominant clears the shatter bar, so neither existing rule fires. What comes
    out is one decoration cut across faces, not many prints -- 20460p09's five
    are the panels of a single striped garment -- so emitting the pile dresses
    the failure up as a result.
    """
    groups = [_group(100.0)] * (unwrap.MAX_DECALS + 1)
    assert unwrap.significant_groups(groups) == []


def test_the_cap_counts_survivors_not_raw_groups():
    """The cap is on what a part EMITS, not on how finely decal_groups cut it.
    A clean dominant print surrounded by dust is a success the sliver rule
    already handles -- counting raw groups instead would silence 52 corpus
    parts whose single print is intact, a torso among them."""
    groups = [_group(100.0)] + [_group(0.1)] * 40
    kept = unwrap.significant_groups(groups)
    assert [g[2][0][1].area for g in kept] == [100.0]


def test_a_part_at_the_cap_still_emits():
    groups = [_group(100.0)] * unwrap.MAX_DECALS
    assert len(unwrap.significant_groups(groups)) == unwrap.MAX_DECALS


def test_a_single_print_is_never_treated_as_shatter():
    groups = [_group(12.0)]
    assert unwrap.significant_groups(groups) == groups


def test_facet_normal_noise_does_not_split_one_plane():
    """The `plane` key shade builds is a rounded grid, and one flat face's
    facets differ in the 4th decimal — 10049p01's claw print bound a few
    facets to each of 36 carriers and reached the SVG as fragments."""
    n = np.array([0.0, -0.7071, -0.7071])
    planes = [unwrap.Plane(normal=n + np.array([d, 0.0, 0.0]), offset=7.07)
              for d in (0.0, -1e-4, -2e-4)]
    assert len(unwrap.dedupe_planes(planes)) == 1


def test_planes_a_facet_apart_stay_apart():
    """An LDraw 16-gon steps 22.5 degrees, so the merge must not flatten a
    faceted wall into one plane."""
    planes = [unwrap.Plane(normal=np.array([1.0, 0.0, 0.0]), offset=0.0),
              unwrap.Plane(normal=np.array([0.924, 0.383, 0.0]), offset=0.0)]
    assert len(unwrap.dedupe_planes(planes)) == 2


def test_parallel_planes_at_different_offsets_stay_apart():
    planes = [unwrap.Plane(normal=np.array([0.0, 1.0, 0.0]), offset=0.0),
              unwrap.Plane(normal=np.array([0.0, 1.0, 0.0]), offset=4.0)]
    assert len(unwrap.dedupe_planes(planes)) == 2


def _panel(ext_w, ext_h, region):
    """A `decal_panels` entry: a rectangular carrier extent and one region."""
    ext = np.array([[0.0, 0.0], [ext_w, 0.0], [ext_w, ext_h], [0.0, ext_h]])
    return (ext, [(4, np.asarray(region, float))], None)


def _panel_groups(svg):
    """[(dx, dy, path_d)] one per `<g>` a sheet drew."""
    out = []
    for chunk in re.findall(r'<g transform="translate\(([-\d.]+) ([-\d.]+)\)">'
                            r'(.*?)</g>', svg):
        dx, dy, inner = chunk
        d = re.search(r'<path d="([^"]+)"', inner).group(1)
        out.append((float(dx), float(dy), d))
    return out


def _path_width(d):
    xs = [float(m) for m in re.findall(r'[ML]\s*([-\d.]+)', d)]
    return max(xs) - min(xs)


def test_sheet_grid_stays_square_ish():
    """Four panels in a row make a canvas 4:1, which the wall thumbnails into
    a sliver."""
    assert unwrap.sheet_grid(1) == (1, 1)
    assert unwrap.sheet_grid(2) == (2, 1)
    assert unwrap.sheet_grid(3) == (2, 2)
    assert unwrap.sheet_grid(4) == (2, 2)


def test_a_single_decal_sheet_is_the_panel_itself(monkeypatch):
    """One print is one drawing, unchanged: the sheet layout exists for the
    parts that carry several, and must not re-render the common case."""
    panel = _panel(20.0, 10.0, [[2, 2], [8, 2], [8, 8], [2, 8]])
    monkeypatch.setattr(unwrap, "decal_panels", lambda *a, **k: [panel])
    sheet = unwrap.decal_sheet(None, None, None, px=400)
    assert sheet == unwrap.texture_svg(panel[0], panel[1], px=400,
                                       face=None, bg=None)
    assert "<g transform" not in sheet


def test_a_part_with_no_decal_yields_no_sheet(monkeypatch):
    monkeypatch.setattr(unwrap, "decal_panels", lambda *a, **k: [])
    assert unwrap.decal_sheet(None, None, None) is None


def test_every_panel_on_a_sheet_is_drawn_at_one_scale(monkeypatch):
    """The point of the sheet over separate files: a small print stays small
    against a large one. Two carriers of different size, each printed with the
    SAME region, so one scale means one drawn width."""
    region = [[2, 2], [6, 2], [6, 6], [2, 6]]
    monkeypatch.setattr(unwrap, "decal_panels", lambda *a, **k: [
        _panel(40.0, 40.0, region), _panel(20.0, 20.0, region)])
    groups = _panel_groups(unwrap.decal_sheet(None, None, None, px=600))
    assert len(groups) == 2
    a, b = (_path_width(g[2]) for g in groups)
    assert a == pytest.approx(b, rel=1e-6)


def test_sheet_panels_do_not_sit_on_top_of_each_other(monkeypatch):
    region = [[1, 1], [3, 1], [3, 3], [1, 3]]
    monkeypatch.setattr(unwrap, "decal_panels", lambda *a, **k: [
        _panel(10.0, 10.0, region)] * 4)
    groups = _panel_groups(unwrap.decal_sheet(None, None, None, px=600))
    assert len({(g[0], g[1]) for g in groups}) == 4


def test_px_sizes_the_whole_sheet_not_each_panel(monkeypatch):
    """`--texture-px` is the canvas's longer edge, and stays so once the
    canvas holds four prints."""
    region = [[1, 1], [3, 1], [3, 3], [1, 3]]
    monkeypatch.setattr(unwrap, "decal_panels", lambda *a, **k: [
        _panel(10.0, 10.0, region)] * 4)
    sheet = unwrap.decal_sheet(None, None, None, px=600)
    assert 'width="600"' in sheet and 'height="600"' in sheet


def test_a_print_inscribed_in_its_wall_stands_off_by_nothing():
    """Every measured pattern reads at or inside its carrier -- its facets
    are chords -- so the standoff is the one that must stay exactly zero:
    it is what keeps a print's reconstruction where it is today."""
    cyl = FakeCylinder(r=20.0)
    th = np.linspace(0, np.pi / 2, 5)
    chord = np.column_stack([19.6 * np.cos(th), np.full(5, 4.0),
                             19.6 * np.sin(th)])
    assert unwrap.standoff(chord, cyl) == 0.0


def test_a_sticker_laid_on_the_wall_reads_its_own_thickness():
    cyl = FakeCylinder(r=20.0)
    th = np.linspace(0, np.pi / 2, 5)
    proud = np.column_stack([20.3 * np.cos(th), np.full(5, 4.0),
                             20.3 * np.sin(th)])
    assert unwrap.standoff(proud, cyl) == pytest.approx(0.3, abs=1e-9)


def test_standoff_clears_the_outermost_vertex_not_the_average():
    """It is what the reconstruction is raised by, and the point of raising
    it is to clear the geometry it was built from -- all of it."""
    cyl = FakeCylinder(r=20.0)
    mixed = np.array([[20.1, 4.0, 0.0], [20.4, 4.0, 0.0], [20.2, 4.0, 0.0]])
    assert unwrap.standoff(mixed, cyl) == pytest.approx(0.4, abs=1e-9)


def test_a_plane_carrier_measures_standoff_along_its_normal():
    plane = unwrap.Plane(normal=np.array([0.0, 1.0, 0.0]), offset=2.0)
    assert unwrap.standoff(np.array([[3.0, 2.25, 5.0]]), plane) \
        == pytest.approx(0.25, abs=1e-9)


def test_raising_the_reconstruction_keeps_its_place_on_the_wall():
    """Only the radius moves: raised by exactly the distance they stand off
    a r=20 wall, points authored at r=20.3 come back where they started --
    not turned around the part."""
    cyl = FakeCylinder(r=20.0)
    pts = np.array([[20.3, 3.0, 0.0], [0.0, 7.0, 20.3], [-20.3, 1.0, 0.0]])
    back = unwrap.to_xyz(unwrap.to_uv(pts, cyl), cyl, standoff=0.3)
    assert back == pytest.approx(pts, abs=1e-9)


def test_a_raised_plane_reconstruction_moves_along_the_normal():
    plane = unwrap.Plane(normal=np.array([0.0, 1.0, 0.0]), offset=2.0)
    pts = np.array([[3.0, 2.0, 5.0]])
    back = unwrap.to_xyz(unwrap.to_uv(pts, plane), plane, standoff=0.25)
    assert back == pytest.approx(np.array([[3.0, 2.25, 5.0]]), abs=1e-9)


def _crown_pts(r=20.0, drop=4.0, rings=(0.25, 0.5, 0.75, 1.0)):
    """The skirt at the OTHER end: curving inward below the wall's base."""
    pts = []
    for f in rings:
        t = f * np.pi / 2
        rr = r - (r * 0.4) * (1 - np.cos(t))
        y = -drop * np.sin(t)
        for th in np.linspace(0, 2 * np.pi, 24, endpoint=False):
            pts.append([rr * np.cos(th), y, rr * np.sin(th)])
    return np.array(pts, float)


def _jaw_pts(r=20.0, h=24.0, drop=4.0, rings=(0.25, 0.5, 0.75, 1.0)):
    """Tessellation of a wall plus the skirt it runs into: a quarter ellipse
    from (r, top) inward, sampled as latitude rings the way LDraw's torus
    subfiles arrive."""
    pts = []
    for lvl in (0.0, 0.5, 1.0):                     # the wall itself
        for th in np.linspace(0, 2 * np.pi, 24, endpoint=False):
            pts.append([r * np.cos(th), lvl * h, r * np.sin(th)])
    for f in rings:                                 # the skirt, curving in
        t = f * np.pi / 2
        rr = r - (r * 0.4) * (1 - np.cos(t))
        y = h + drop * np.sin(t)
        for th in np.linspace(0, 2 * np.pi, 24, endpoint=False):
            pts.append([rr * np.cos(th), y, rr * np.sin(th)])
    return np.array(pts, float)


def test_skirt_continues_a_wall_over_what_it_runs_into():
    cyl = FakeCylinder(r=20.0, h=24.0)
    s = unwrap.skirt(cyl, _jaw_pts())
    assert isinstance(s, unwrap.Skirt)
    assert s.level_top > 1.0
    # inside its own section it is still the wall, exactly
    assert s.radius_at(0.5) == pytest.approx(1.0)
    # and past it the radius follows the tessellation inward
    assert s.radius_at(s.level_top) < 0.95


def test_a_skirt_binds_ink_its_own_section_cannot_reach():
    cyl = FakeCylinder(r=20.0, h=24.0)
    pts = _jaw_pts()
    s = unwrap.skirt(cyl, pts)
    on_skirt = pts[pts[:, 1] > 24.0 + 1e-9][:3]
    assert unwrap.bind(on_skirt, [cyl]) is None
    assert unwrap.bind(on_skirt, [s]) is s


def test_a_skirt_round_trips_ink_back_onto_the_skirt_not_the_wall():
    """The reason `to_xyz` has to know the profile: a cylinder's radius_at is
    1.0 at every level, so ink bound past the section came back at the WALL
    radius, off the surface it was lifted from."""
    cyl = FakeCylinder(r=20.0, h=24.0)
    pts = _jaw_pts()
    s = unwrap.skirt(cyl, pts)
    on_skirt = pts[pts[:, 1] > 26.0][:1]
    back = unwrap.to_xyz(unwrap.to_uv(on_skirt, s), s)
    assert back == pytest.approx(on_skirt, abs=0.3)
    naive = unwrap.to_xyz(unwrap.to_uv(on_skirt, cyl), cyl)
    assert np.hypot(naive[0, 0], naive[0, 2]) == pytest.approx(20.0, abs=1e-6)


def test_a_gap_between_latitude_rings_does_not_end_the_skirt():
    """A coarsely tessellated skirt has bare bands between its rings, and
    stopping at the first one truncated 3626bp39's jaw to a third of itself."""
    cyl = FakeCylinder(r=20.0, h=24.0)
    sparse = unwrap.skirt(cyl, _jaw_pts(rings=(0.25, 1.0)))
    dense = unwrap.skirt(cyl, _jaw_pts())
    assert sparse.level_top == pytest.approx(dense.level_top, abs=0.05)


def test_a_wall_with_nothing_past_it_is_left_alone():
    cyl = FakeCylinder(r=20.0, h=24.0)
    wall_only = _jaw_pts(rings=())
    assert unwrap.skirt(cyl, wall_only) is cyl


def test_a_skirt_never_flares_back_out():
    """Decoration cuts bands of the skirt away, and a band left holding only
    its outer vertices would otherwise read as the wall widening again."""
    cyl = FakeCylinder(r=20.0, h=24.0)
    pts = _jaw_pts()
    stray = np.array([[20.0, 24.0 + 3.9, 0.0]])      # an outlier near the top
    s = unwrap.skirt(cyl, np.vstack([pts, stray]))
    assert np.all(np.diff(s.hi[1]) <= 1e-9)


def test_a_skirt_continues_both_ends_of_a_wall():
    """A wall is not special at one end. 3626bp63's forehead lines run over
    the crown, and a skirt built only past level 1 left the upper one
    clipped exactly as the jaw's ink had been."""
    cyl = FakeCylinder(r=20.0, h=24.0)
    s = unwrap.skirt(cyl, np.vstack([_jaw_pts(), _crown_pts()]))
    assert s.level_top > 1.0
    assert s.level_bot < 0.0
    assert s.radius_at(s.level_bot) < 0.95
    assert s.radius_at(0.5) == pytest.approx(1.0)


def test_ink_over_the_crown_binds_and_round_trips():
    cyl = FakeCylinder(r=20.0, h=24.0)
    crown = _crown_pts()
    s = unwrap.skirt(cyl, np.vstack([_jaw_pts(), crown]))
    over = crown[crown[:, 1] < -2.0][:1]
    assert unwrap.bind(over, [cyl]) is None
    assert unwrap.bind(over, [s]) is s
    assert unwrap.to_xyz(unwrap.to_uv(over, s), s) == pytest.approx(over,
                                                                   abs=0.3)


def test_a_planar_carrier_has_no_skirt():
    plane = unwrap.Plane(normal=np.array([0.0, 0.0, 1.0]), offset=2.0)
    assert unwrap.skirt(plane, _jaw_pts()) is plane


def _panel_areas(part, ldraw_dir):
    from brick_icons import hlr
    tri, tri_colors, analytic = hlr.part_geometry(part, ldraw_dir)
    return sorted((sum(g.area for _c, g in regions)
                   for _ext, regions, _face in
                   unwrap.decal_panels(tri, tri_colors, analytic)),
                  reverse=True)


def test_an_arm_placed_in_its_own_color_is_not_print(ldraw_dir):
    """76382p0u is 973p0u with arms placed in color 71 and hands in 78. A
    sub-part's color is the color it was moulded in, so the arms are body --
    read as print, their shoulders outnumbered MAX_DECALS and the torso's own
    print went to the mesh fallback, rotated and cut into pieces."""
    assert _panel_areas("76382p0u", ldraw_dir) == pytest.approx(
        _panel_areas("973p0u", ldraw_dir), rel=0.01)


def test_a_printed_arm_keeps_its_print(ldraw_dir):
    """76382p0033's arms are 3818pv0 in color 191: the 191 is body, and the
    black shoulder the arm file declares is still print, beside the torso's."""
    torso = _panel_areas("973pv1", ldraw_dir)
    assert _panel_areas("76382p0033", ldraw_dir)[:2] == pytest.approx(
        torso, rel=0.01)


def test_a_sticker_placed_in_a_color_is_still_print(ldraw_dir):
    """3004d01 places its sticker in color 0. A sticker's faces are its
    print, so that color is decoration, not a moulded body."""
    from brick_icons import hlr
    tri, tri_colors, analytic = hlr.part_geometry("3004d01", ldraw_dir)
    panels = unwrap.decal_panels(tri, tri_colors, analytic)
    assert panels and 0 in {c for _e, regions, _f in panels
                            for c, _g in regions}


def _book(print_a, print_b, reverse=False):
    """(tris, colors) for a sheet bent 30 degrees about a vertical crease at
    x=10, with a color-4 print strip on each leaf. `print_a` and `print_b` are
    (start, end) distances from the crease along each leaf; a strip reaching 0
    shares the crease vertices with its twin, so the two weld into one piece.
    """
    c, s = np.cos(np.radians(30.0)), np.sin(np.radians(30.0))

    def on_a(d, y):
        return [10.0 - d, y, 0.0]

    def on_b(d, y):
        return [10.0 + d * c, y, d * s]

    def quad(f, d0, d1, y0, y1, n=3):
        # several cells, not one: a flattening needs a few triangles to
        # measure its own distortion against
        ds = np.linspace(d0, d1, n + 1)
        return [t for a, b in zip(ds[:-1], ds[1:])
                for t in _quad_tris([f(a, y0), f(b, y0), f(b, y1), f(a, y1)])]

    body = quad(on_a, 0.0, 10.0, -10.0, 0.0) + quad(on_b, 0.0, 10.0, -10.0, 0.0)
    ink = (quad(on_a, *print_a, -6.0, -4.0) + quad(on_b, *print_b, -6.0, -4.0))
    if reverse:
        ink = [t[::-1] for t in ink]
    tris = [np.asarray(t, float) for t in body + ink]
    return tris, [16] * len(body) + [4] * len(ink)


def test_a_print_bent_over_a_crease_draws_as_one_panel():
    """6155286wc01's sign is one print on a sheet formed over facets; binding
    each facet's share to its own plane drew it as two halves, and the mesh
    flattening that keeps it whole only ran when no carrier bound anything."""
    tris, colors = _book((0.0, 6.0), (0.0, 4.0))
    panels = unwrap.decal_panels(tris, colors, [])
    assert len(panels) == 1
    area = sum(g.area for _c, g in panels[0][1])
    assert area == pytest.approx(12.0 + 8.0, rel=0.01)


def test_prints_on_two_faces_that_do_not_touch_stay_two_panels():
    tris, colors = _book((2.0, 6.0), (2.0, 6.0))
    assert len(unwrap.decal_panels(tris, colors, [])) == 2


@pytest.mark.parametrize("reverse", [False, True])
def test_a_flattened_print_reads_the_way_its_plane_does(reverse):
    """A conformal flattening fixes rotation by which two vertices it pins and
    handedness by the authored winding, which LDraw does not guarantee:
    4174735bc01's band came off it rotated. On a flat print it must agree
    with the plane unwrap, which settles both."""
    tris, colors = _book((0.0, 6.0), (0.0, 0.0), reverse=reverse)
    # the whole body, so the part has an inside to be outward from; ink on
    # the first leaf only, so one plane carries it
    area = [np.linalg.norm(np.cross(t[1] - t[0], t[2] - t[0])) for t in tris]
    keep = [i for i, t in enumerate(tris)
            if colors[i] == 16 or (t[:, 2].max() == 0 and area[i] > 0)]
    tris, colors = [tris[i] for i in keep], [colors[i] for i in keep]
    (plane, theta0, _r, _f), = unwrap.decal_groups(tris, colors, [])
    (mesh, _t, _r2, _f2), = unwrap.mesh_groups(tris, colors)
    p = np.array([[4.0, -6.0, 0.0], [10.0, -6.0, 0.0], [4.0, -4.0, 0.0]])
    flat, bent = unwrap.to_uv(p, plane, theta0), mesh.at(p)
    for k in (1, 2):
        a, b = flat[k] - flat[0], bent[k] - bent[0]
        cos = float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))
        assert cos == pytest.approx(1.0, abs=1e-3)


def test_winding_is_made_to_agree_across_shared_edges():
    # two faces over edge 1-2, both authored 1 -> 2
    F = unwrap.consistent_winding([[0, 1, 2], [1, 2, 3]])
    directed = [{(f[0], f[1]), (f[1], f[2]), (f[2], f[0])} for f in F]
    assert (1, 2) in directed[0] and (2, 1) in directed[1]


def test_a_region_drawn_with_arcs_still_covers_its_own_polygon(tmp_path, ldraw_dir):
    """A hole fitted as a circle is larger than the 16-gon it was fitted to,
    so the fill around it lost a sliver beyond every chord -- and a neighbor
    drawn as the polygon left those slivers showing as ground: 4531d01's dots,
    98138p16's heart seam."""
    import io
    import subprocess

    import shapely
    from PIL import Image, ImageDraw

    th = np.radians(np.arange(16) * 22.5)
    hole = np.column_stack([500 + 300 * np.cos(th), 500 + 300 * np.sin(th)])
    square = np.array([[100.0, 100.0], [900.0, 100.0], [900.0, 900.0], [100.0, 900.0]])
    region = shapely.Polygon(square, [hole])
    canvas = np.array([[0.0, 0.0], [1000.0, 0.0], [1000.0, 1000.0], [0.0, 1000.0]])
    path, = unwrap._panel_paths(canvas, [(0, region)], 1.0, ldraw_dir, None)
    svg = tmp_path / "region.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1000" '
                   'height="1000"><rect width="1000" height="1000" fill="white"/>'
                   + path + "</svg>")
    png = subprocess.run(["resvg", str(svg), "-c"], capture_output=True,
                         check=True).stdout
    ink = np.asarray(Image.open(io.BytesIO(png)).convert("L")) < 128
    truth = Image.new("L", (1000, 1000), 0)
    draw = ImageDraw.Draw(truth)
    draw.polygon([(x, 1000 - y) for x, y in square], fill=255)
    draw.polygon([(x, 1000 - y) for x, y in hole], fill=0)
    missed = (np.asarray(truth) > 0) & ~ink
    # one pixel of erosion clears antialias fringe; a chord's sliver is
    # about six pixels deep at this radius and survives it
    from scipy import ndimage
    assert ndimage.binary_erosion(missed).sum() == 0


def test_a_print_that_only_spills_onto_a_second_face_stays_on_its_carrier():
    """u9102p04's strap is 92% on the helmet's front plane and 8% on the
    skirt below it. Flattening it on its own split it from the dots printed
    beside it; losing the spill on the carrier's drawing is the smaller harm."""
    tris, colors = _book((0.0, 6.0), (0.0, 0.5))
    panels = unwrap.decal_panels(tris, colors, [])
    assert panels and panels[0][2] is not None      # a carrier panel keeps its face


def test_a_print_around_a_sticker_edge_is_not_one_surface():
    """u9533's print wraps a 0.25 LDU sheet's edge from its front to its back.
    Front and back are parallel planes: nothing is cut across facets, so the
    two sides stay two panels instead of unfolding into one strip."""
    def quad(a, b, c, d):
        return _quad_tris([a, b, c, d])

    body = (quad([0, -10, 0], [10, -10, 0], [10, 0, 0], [0, 0, 0])
            + quad([10, -10, -0.25], [0, -10, -0.25], [0, 0, -0.25], [10, 0, -0.25])
            + quad([10, -10, 0], [10, -10, -0.25], [10, 0, -0.25], [10, 0, 0]))
    ink = []
    for x0, x1 in ((4.0, 6.0), (6.0, 8.0), (8.0, 10.0)):
        ink += quad([x0, -6, 0], [x1, -6, 0], [x1, -4, 0], [x0, -4, 0])
        ink += quad([x1, -6, -0.25], [x0, -6, -0.25], [x0, -4, -0.25], [x1, -4, -0.25])
    ink += quad([10, -6, 0], [10, -6, -0.25], [10, -4, -0.25], [10, -4, 0])
    tris = [np.asarray(t, float) for t in body + ink]
    colors = [16] * len(body) + [4] * len(ink)
    panels = unwrap.decal_panels(tris, colors, [])
    assert len(panels) == 2 and all(face is not None for _e, _r, face in panels)


def test_a_wall_family_that_widens_along_its_axis_still_carries_its_print():
    """43898p02's dish is stacked cone sections authored axis-down, so they
    widen along the axis span_carrier picks. Its end radii went into a cone
    with a negative taper, a negative radius law, and a wall 24 LDU from where
    the sections are: all 32 blue stripes bound to nothing."""
    from brick_icons import primitives

    R = np.array([[2.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -2.0]])
    upper = primitives.Cone(R=R, t=np.array([0.0, 0.0, 0.0]), sector=360.0,
                            color=16, top=4.0)       # radius 10 at y=0, 8 at y=-1
    lower = primitives.Cone(R=R, t=np.array([0.0, -1.0, 0.0]), sector=360.0,
                            color=16, top=3.0)       # radius 8 at y=-1, 6 at y=-2
    th = np.radians([0.0, 4.0, 2.0])
    rad = np.array([9.0, 9.0, 9.2])
    y = np.array([-0.5, -0.5, -0.4])
    stripe = np.column_stack([rad * np.cos(th), y, rad * np.sin(th)])
    span = unwrap.span_carrier([upper, lower])
    assert unwrap._gap(stripe, span) < 0.05
    assert len(unwrap.decal_groups([stripe], [1], [upper, lower])) == 1


def test_a_round_carrier_face_is_still_filled(tmp_path, ldraw_dir):
    """A round tile's face fits as a circle and carries its polygon beneath,
    the same as a print region; drawn evenodd the two cancelled and 98138p83's
    tile lost its face."""
    import io
    import subprocess

    import shapely
    from PIL import Image

    th = np.radians(np.arange(16) * 22.5)
    disc = shapely.Polygon(np.column_stack([500 + 300 * np.cos(th),
                                            500 + 300 * np.sin(th)]))
    canvas = np.array([[0.0, 0.0], [1000.0, 0.0], [1000.0, 1000.0], [0.0, 1000.0]])
    path, = unwrap._panel_paths(canvas, [], 1.0, ldraw_dir, disc)
    svg = tmp_path / "face.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1000" '
                   'height="1000"><rect width="1000" height="1000" fill="white"/>'
                   + path + "</svg>")
    png = subprocess.run(["resvg", str(svg), "-c"], capture_output=True,
                         check=True).stdout
    painted = np.asarray(Image.open(io.BytesIO(png)).convert("L")) < 250
    assert painted[500, 500] and painted.sum() > 0.9 * disc.area


def test_a_print_lying_on_two_planes_at_a_crease_takes_the_nearer():
    """4740p03's silver band crosses the crease between its dish's flat floor
    and a facet 6 degrees off, and one triangle lies on both within 0.004 LDU.
    Taking the more parallel plane split it from its neighbors and drew a stub
    across the band; tangency only has a say among planes a print is not on."""
    # a sliver along the crease line x=0, parallel to the floor
    print_ = np.array([[0.0, 0.0, 0.003], [0.0, 1.0, 0.003], [0.02, 0.5, 0.003]])
    floor = unwrap.Plane(normal=np.array([0.0, 0.0, 1.0]), offset=0.009)
    s, c = np.sin(np.radians(6.0)), np.cos(np.radians(6.0))
    facet = unwrap.Plane(normal=np.array([s, 0.0, c]), offset=0.0)
    assert unwrap._gap(print_, facet) < unwrap._gap(print_, floor) <= 0.01
    assert unwrap.bind(print_, [floor, facet]) is facet


def _bodyless_sticker():
    """(tris, colors) for a 10 x 10 sticker 0.25 thick with no color-16
    geometry at all: a printed side facing LDraw up in colors 4 and 0, and a
    back and rim in the sheet's own color 4 -- 4297014e's construction."""
    def quad(a, b, c, d):
        return _quad_tris([a, b, c, d])

    top, back = -0.25, 0.0
    front = (quad([0, top, 0], [5, top, 0], [5, top, 10], [0, top, 10])
             + quad([5, top, 0], [10, top, 0], [10, top, 10], [5, top, 10]))
    sheet = quad([0, back, 0], [0, back, 10], [10, back, 10], [10, back, 0])
    rim = []
    for (x0, z0), (x1, z1) in (((0, 0), (10, 0)), ((10, 0), (10, 10)),
                               ((10, 10), (0, 10)), ((0, 10), (0, 0))):
        rim += quad([x0, top, z0], [x1, top, z1], [x1, back, z1], [x0, back, z0])
    tris = [np.asarray(t, float) for t in front + sheet + rim]
    return tris, [4, 4, 0, 0] + [4] * (len(sheet) + len(rim))


def test_a_sticker_with_no_body_carries_its_print_on_its_own_sheet():
    """Every face of 4297014e is in a color, so no plane was ever built to
    carry the print, and front and back weld into a slab that will not
    flatten. Its own facets are the carrier; the back, one region of the
    sheet's color filling its face, is not print."""
    tris, colors = _bodyless_sticker()
    panels = unwrap.decal_panels(tris, colors, [])
    assert len(panels) == 1
    assert {int(c) for c, _g in panels[0][1]} == {0, 4}
