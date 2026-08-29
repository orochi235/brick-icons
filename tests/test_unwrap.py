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
    # a quarter turn at r=20 is 20 * pi/2 of arc
    assert uv[1, 0] - uv[0, 0] == pytest.approx(20.0 * np.pi / 2, rel=1e-6)


def test_cylinder_unwrap_round_trips():
    cyl = FakeCylinder(r=20.0)
    pts = np.array([[20.0, 3.0, 0.0], [0.0, 7.0, 20.0], [-20.0, 1.0, 0.0]])
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


def test_texture_paints_each_region_in_its_ldraw_colour():
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
    assert (ext[:, 1].min(), ext[:, 1].max()) == pytest.approx((0.0, 24.0))


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


def test_different_colours_stay_separate_regions():
    a = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
    b = np.array([[2.0, 0.0], [4.0, 0.0], [4.0, 2.0], [2.0, 2.0]])
    assert len(unwrap.merge_regions([(4, a), (14, b)])) == 2


def test_a_hole_survives_the_merge():
    """3941p01's buttons are body-coloured discs INSIDE the black panel: the
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
