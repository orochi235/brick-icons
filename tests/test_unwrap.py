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
    d = unwrap.region_path(geom2d.to_geom(poly))
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
    d = unwrap.region_path(geom2d.to_geom(ring))
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


def test_decorate_returns_one_region_per_colour_on_a_carrier():
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


def test_decal_paints_its_ldraw_colour_as_one_element(tmp_path):
    """The panel never painted at all before the colour rode out of flatten,
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


def test_the_carrier_face_is_the_whole_face_print_included():
    """The print REPLACES the body facets under it, so unioning colour 16
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
    """LDraw authors a minifig neck as a 270-degree colour-16 cylinder plus a
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
    """3942bp01's stripes partition their wall into coloured and colour-16
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
    """3942bp01 is 16 coloured cone sectors and NO coloured facets, so a
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
