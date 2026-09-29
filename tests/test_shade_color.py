import numpy as np
import pytest

from brick_icons import shade


class FakeProj:
    right = np.array([1.0, 0.0, 0.0])
    up = np.array([0.0, 1.0, 0.0])
    fwd = np.array([0.0, 0.0, -1.0])

    def to_px(self, v):
        return v[:, 0] * 10, v[:, 1] * 10, v[:, 2]


def test_faces_carry_their_triangle_color():
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[2, 0, 0], [3, 0, 0], [2, 1, 0]],
    ], float)
    faces = shade.faces_from_tris(tri, FakeProj(), colors=[16, 14])
    assert [f["color"] for f in faces] == [16, 14]


def test_faces_default_to_the_part_color_when_none_given():
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], float)
    faces = shade.faces_from_tris(tri, FakeProj())
    assert [f["color"] for f in faces] == [16]


def test_coplanar_faces_of_different_colors_do_not_union():
    """A decal quad is coplanar with its carrier and shares an edge with it.
    Unioning them is what erases flat prints today."""
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],      # carrier
        [[1, 0, 0], [1, 1, 0], [0, 1, 0]],      # decal, shares an edge
    ], float)
    faces = shade.faces_from_tris(tri, FakeProj(), colors=[16, 14])
    assert faces[0]["group"] != faces[1]["group"]


def test_coplanar_faces_of_the_same_color_still_union():
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[1, 0, 0], [1, 1, 0], [0, 1, 0]],
    ], float)
    faces = shade.faces_from_tris(tri, FakeProj(), colors=[16, 16])
    assert faces[0]["group"] == faces[1]["group"]


def test_decoration_fills_use_the_ldraw_color():
    """Color 16 takes the part color and shades; anything else paints its
    own LDraw color, so a print reads as print rather than as engraving."""
    face_body = {"normal": np.array([0.0, 0.0, -1.0]), "color": 16}
    face_deco = {"normal": np.array([0.0, 0.0, -1.0]), "color": 4}
    style = shade.Flat3Style(part_color=(157, 157, 157))
    assert shade.face_fill(face_body, style, "vendor/ldraw") == \
        style.tone(face_body["normal"])
    assert shade.face_fill(face_deco, style, "vendor/ldraw").lower() == "#b40000"


def test_analytic_faces_carry_the_primitive_color():
    from brick_icons import hlr, primitives as P
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, 2.0, 0.0, 0.0, 50.0)
    disc = P.Disc(R=np.diag([4.0, 1.0, 4.0]), t=np.zeros(3), color=14)
    faces = shade.faces_from_analytic([disc], proj)
    assert faces, "the disc should produce at least one face"
    assert all(f["color"] == 14 for f in faces)


def test_analytic_primitives_default_to_the_part_color():
    from brick_icons import hlr, primitives as P
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, 2.0, 0.0, 0.0, 50.0)
    disc = P.Disc(R=np.diag([4.0, 1.0, 4.0]), t=np.zeros(3))
    faces = shade.faces_from_analytic([disc], proj)
    assert all(f["color"] == 16 for f in faces)


def test_decoration_on_a_curved_wall_paints_flat_not_gradient():
    """A print is ink on a surface, not relief, so it does not catch a
    shading ramp. 3942bp01's stripes are Cone primitives, and every curved
    face shades with a gradient — which ignored the LDraw color entirely,
    so the cone rendered with no red at all."""
    style = shade.Flat3Style(part_color=(157, 157, 157))
    deco = {"poly": np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]),
            "normal": np.array([0.0, 0.0, -1.0]), "depth": 1.0, "color": 4,
            "grad_axis": ((0.0, 0.0), (10.0, 10.0)),
            "grad_samples": [(0.0, np.array([0.0, 0.0, -1.0])),
                             (1.0, np.array([0.0, 0.0, -1.0]))]}
    ops = shade.fill_ops([deco], style, clip=False, ldraw_dir="vendor/ldraw")
    assert ops, "the face should emit an op"
    assert "gradient" not in ops[0], "decoration must not shade as a gradient"
    assert ops[0]["fill"].lower() == "#b40000"


def test_body_geometry_on_a_curved_wall_still_shades_as_a_gradient():
    style = shade.Flat3Style(part_color=(157, 157, 157))
    body = {"poly": np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]),
            "normal": np.array([0.0, 0.0, -1.0]), "depth": 1.0, "color": 16,
            "grad_axis": ((0.0, 0.0), (10.0, 10.0)),
            # normals sweep, so the ramp has somewhere to go: one repeated
            # normal is a one-color ramp, which now paints flat
            "grad_samples": [(0.0, np.array([-1.0, 0.0, 0.0])),
                             (0.5, np.array([0.0, 0.0, -1.0])),
                             (1.0, np.array([1.0, 0.0, 0.0]))]}
    ops = shade.fill_ops([body], style, clip=False, ldraw_dir="vendor/ldraw")
    assert ops and "gradient" in ops[0]


def test_decoration_facets_union_across_a_curved_carrier():
    """A print is ONE region however its carrier curves. 3941p01's panel is 36
    hand-authored quads wrapping a cylinder: adjacent facets sit 7.5 degrees
    apart so they are not coplanar, and the part carries no conditional lines
    to seam them, so the panel shattered into separately-stroked fragments."""
    a = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    # shares edge (1,0,0)-(0,1,0), tilted well past the coplanarity threshold
    b = np.array([[1.0, 0.0, 0.0], [1.0, 1.0, 0.4], [0.0, 1.0, 0.0]])
    faces = shade.faces_from_tris(np.array([a, b]), FakeProj(), colors=[4, 4])
    assert len(faces) == 2, "both facets should survive culling"
    assert faces[0]["group"] == faces[1]["group"]


def test_body_facets_still_need_coplanarity_or_a_seam_to_union():
    a = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    b = np.array([[1.0, 0.0, 0.0], [1.0, 1.0, 0.4], [0.0, 1.0, 0.0]])
    faces = shade.faces_from_tris(np.array([a, b]), FakeProj(), colors=[16, 16])
    assert len(faces) == 2
    assert faces[0]["group"] != faces[1]["group"]


def test_a_gradient_whose_stops_are_one_color_paints_flat():
    """A curved face whose every binned stop rounds to the same grey is a
    flat fill wearing a gradient def. 44300's boss carried one with 9 stops
    and 1 distinct color; the def costs bytes and paints nothing a plain
    fill would not."""
    style = shade.Flat3Style(part_color=(157, 157, 157))
    n = np.array([0.0, 0.0, -1.0])
    body = {"poly": np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]),
            "normal": n, "depth": 1.0, "color": 16,
            "grad_axis": ((0.0, 0.0), (10.0, 10.0)),
            "grad_samples": [(t / 8, n) for t in range(9)]}
    ops = shade.fill_ops([body], style, clip=False, ldraw_dir="vendor/ldraw")
    assert ops
    assert "gradient" not in ops[0], "one-color stops should collapse to a flat fill"
    assert ops[0]["fill"] == style.ramp(n)


_SQUARE = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
_WALL_SAMPLES = [(0.0, np.array([-1.0, 0.0, 0.0])),
                 (0.5, np.array([0.0, 0.0, -1.0])),
                 (1.0, np.array([1.0, 0.0, 0.0]))]


def _wall(color):
    return {"poly": _SQUARE, "normal": np.array([0.0, 0.0, -1.0]),
            "depth": 1.0, "color": color, "grad_axis": ((0.0, 0.0), (10.0, 0.0)),
            "grad_samples": _WALL_SAMPLES}


def test_decoration_on_a_curved_wall_takes_the_wall_s_shading_as_a_layer():
    """A printed stud wall (2552p01's blue studs) keeps its print color and
    gains the gradient a plain wall draws, as black stops whose alpha is how
    far each plain stop falls below a top face."""
    style = shade.Flat3Style(part_color=(157, 157, 157))
    body = shade.fill_ops([_wall(16)], style, clip=False)[0]
    deco = shade.fill_ops([_wall(1)], style, clip=False)[0]
    assert deco["fill"].lower() == "#1e5aa8" and "gradient" not in deco
    layer = deco["shade"]["gradient"]
    for key in ("x1", "y1", "x2", "y2"):
        assert layer[key] == body["gradient"][key]
    top = int(style.tone(np.array([0.0, 1.0, 0.0]))[1:3], 16)
    for (o, a), (ob, c) in zip(layer["stops"], body["gradient"]["stops"]):
        assert o == ob
        assert a == pytest.approx(1 - min(1.0, int(c[1:3], 16) / top), abs=0.01)


def test_a_print_on_a_top_face_stays_flat_and_one_on_a_side_darkens():
    """Printing is authored as it looks lit from above, so a top face's print
    keeps its exact color and one on a shadowed side darkens as the side does."""
    style = shade.Flat3Style(part_color=(157, 157, 157))
    top = {"poly": _SQUARE, "normal": np.array([0.0, 1.0, 0.0]),
           "depth": 1.0, "color": 4}
    side = dict(top, normal=np.array([0.7, 0.0, -0.7]))
    ops = shade.fill_ops([top], style, clip=False) \
        + shade.fill_ops([side], style, clip=False)
    assert "shade" not in ops[0]
    assert ops[1]["shade"]["alpha"] == pytest.approx(
        1 - style.DARK / style.TOP, abs=1e-3)
    # the layer reaches over the print's seam stroke, or that rim stays bright
    assert ops[1]["shade"]["d_seamed"] != ops[1]["d"]


def test_the_white_style_and_the_flag_leave_printing_flat():
    white = shade.fill_ops([_wall(1)], shade.WhiteStyle(), clip=False)[0]
    off = shade.fill_ops([_wall(1)], shade.Flat3Style(), clip=False,
                         deco_shade=False)[0]
    assert "shade" not in white and "shade" not in off
    assert shade.fill_ops([_wall(1)], shade.Flat3Style(), clip=False)[0]["shade"]


def test_a_print_on_a_facet_plane_shades_as_the_body_face_on_that_plane():
    """4740p03's print binds to the dish's facet planes. Toned by its own
    facet it came out one flat tone per facet -- a dark patch where a facet
    crossed the side threshold -- while the dish under it is one gradient."""
    from brick_icons import unwrap
    style = shade.Flat3Style()
    body = dict(_wall(16), normal=np.array([0.0, 1.0, 0.0]),
                plane=(0.0, -1.0, 0.0, 4.0))
    printed = {"poly": _SQUARE * 0.5 + 2.0, "normal": np.array([0.0, 1.0, 0.0]),
               "depth": 0.5, "color": 4,
               "carrier": unwrap.Plane(normal=np.array([0.0, -1.0, 0.0]),
                                       offset=4.0)}
    ops = shade.fill_ops([body, printed], style, clip=False)
    deco = next(op for op in ops if op.get("deco"))
    assert "gradient" in deco["shade"]
    assert deco["shade"]["gradient"]["x1"] == body["grad_axis"][0][0]


def test_a_region_on_a_curved_carrier_shades_across_its_facets():
    """3941p01's panel is one region merged from facets around a cylinder;
    it shades along the direction those facets' normals turn, not by the
    first facet's tone."""
    members = []
    for i, th in enumerate(np.linspace(-1.2, 1.2, 9)):
        x = 10.0 * i
        members.append({"poly": np.array([[x, 0.0], [x + 10, 0.0],
                                          [x + 10, 30.0], [x, 30.0]]),
                        "normal": np.array([np.sin(th), 0.0, -np.cos(th)])})
    poly = np.array([[0.0, 0.0], [90.0, 0.0], [90.0, 30.0], [0.0, 30.0]])
    g = shade._member_gradient(members, poly)
    (x0, y0), (x1, y1) = g["grad_axis"]
    assert abs(x1 - x0) == pytest.approx(90.0) and abs(y1 - y0) < 1e-6
    f = {"poly": poly, "normal": members[0]["normal"], "depth": 1.0,
         "color": 4, "deco_grad": g}
    assert "gradient" in shade._deco_shade(f, shade.Flat3Style())
