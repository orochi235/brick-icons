import numpy as np
from brick_icons import repair


def _unit_tetra():
    """A small closed tetrahedron (4 tris) around the origin, CCW-outward."""
    v = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    return np.array([[v[a], v[b], v[c]] for a, b, c in faces], float)


def test_ray_crossings_counts_forward_hits():
    tris = _unit_tetra()
    # A ray from far outside on +X pointing back through the solid crosses 2 faces.
    origin = np.array([10.0, 0.0, 0.0])
    direction = np.array([-1.0, 0.0, 0.0])
    assert repair.ray_crossings(origin, direction, tris) == 2


def test_ray_crossings_from_inside_is_odd():
    tris = _unit_tetra()
    origin = np.array([0.0, 0.0, 0.0])          # centroid, inside
    direction = np.array([1.0, 0.0, 0.0])
    assert repair.ray_crossings(origin, direction, tris) % 2 == 1


def test_ray_crossings_behind_origin_excluded():
    tris = _unit_tetra()
    origin = np.array([10.0, 0.0, 0.0])
    direction = np.array([1.0, 0.0, 0.0])   # solid is behind (negative lambda)
    assert repair.ray_crossings(origin, direction, tris) == 0
