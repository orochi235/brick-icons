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
