import numpy as np

from brick_icons import shade


class FakeProj:
    right = np.array([1.0, 0.0, 0.0])
    up = np.array([0.0, 1.0, 0.0])
    fwd = np.array([0.0, 0.0, -1.0])

    def to_px(self, v):
        return v[:, 0] * 10, v[:, 1] * 10, v[:, 2]


def test_faces_carry_their_triangle_colour():
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[2, 0, 0], [3, 0, 0], [2, 1, 0]],
    ], float)
    faces = shade.faces_from_tris(tri, FakeProj(), colors=[16, 14])
    assert [f["color"] for f in faces] == [16, 14]


def test_faces_default_to_the_part_colour_when_none_given():
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], float)
    faces = shade.faces_from_tris(tri, FakeProj())
    assert [f["color"] for f in faces] == [16]


def test_coplanar_faces_of_different_colours_do_not_union():
    """A decal quad is coplanar with its carrier and shares an edge with it.
    Unioning them is what erases flat prints today."""
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],      # carrier
        [[1, 0, 0], [1, 1, 0], [0, 1, 0]],      # decal, shares an edge
    ], float)
    faces = shade.faces_from_tris(tri, FakeProj(), colors=[16, 14])
    assert faces[0]["group"] != faces[1]["group"]


def test_coplanar_faces_of_the_same_colour_still_union():
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[1, 0, 0], [1, 1, 0], [0, 1, 0]],
    ], float)
    faces = shade.faces_from_tris(tri, FakeProj(), colors=[16, 16])
    assert faces[0]["group"] == faces[1]["group"]


def test_decoration_fills_use_the_ldraw_colour():
    """Colour 16 takes the part colour and shades; anything else paints its
    own LDraw colour, so a print reads as print rather than as engraving."""
    face_body = {"normal": np.array([0.0, 0.0, -1.0]), "color": 16}
    face_deco = {"normal": np.array([0.0, 0.0, -1.0]), "color": 4}
    style = shade.Flat3Style(part_color=(157, 157, 157))
    assert shade.face_fill(face_body, style, "vendor/ldraw") == \
        style.tone(face_body["normal"])
    assert shade.face_fill(face_deco, style, "vendor/ldraw").lower() == "#b40000"


def test_analytic_faces_carry_the_primitive_colour():
    from brick_icons import hlr, primitives as P
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, 2.0, 0.0, 0.0, 50.0)
    disc = P.Disc(R=np.diag([4.0, 1.0, 4.0]), t=np.zeros(3), color=14)
    faces = shade.faces_from_analytic([disc], proj)
    assert faces, "the disc should produce at least one face"
    assert all(f["color"] == 14 for f in faces)


def test_analytic_primitives_default_to_the_part_colour():
    from brick_icons import hlr, primitives as P
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, 2.0, 0.0, 0.0, 50.0)
    disc = P.Disc(R=np.diag([4.0, 1.0, 4.0]), t=np.zeros(3))
    faces = shade.faces_from_analytic([disc], proj)
    assert all(f["color"] == 16 for f in faces)
