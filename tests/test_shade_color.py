import numpy as np

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
            "grad_samples": [(0.0, np.array([0.0, 0.0, -1.0])),
                             (1.0, np.array([0.0, 0.0, -1.0]))]}
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
