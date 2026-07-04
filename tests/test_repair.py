import numpy as np
from brick_icons import repair


def _unit_tetra():
    """A small closed tetrahedron (4 tris) around the origin, CCW-outward."""
    v = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)
    faces = [(0, 1, 2), (0, 3, 1), (0, 2, 3), (1, 3, 2)]
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


def _outward(tri, centroid):
    n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
    return float(n @ (tri.mean(axis=0) - centroid)) > 0


def test_repaired_tris_certified_uses_invert_flag(tmp_path):
    tris = _unit_tetra()
    centroid = tris.reshape(-1, 3).mean(axis=0)
    # Deliberately reverse two faces and flag them invert=True; repair must
    # restore outward winding for ALL faces.
    raw = [t.copy() for t in tris]
    meta = [{"certified": True, "invert": False} for _ in tris]
    raw[0] = raw[0][[0, 2, 1]]; meta[0]["invert"] = True
    raw[3] = raw[3][[0, 2, 1]]; meta[3]["invert"] = True
    fixed = repair.repaired_tris(np.array(raw), meta, cache_dir=tmp_path)
    assert all(_outward(t, centroid) for t in fixed)


def test_repaired_tris_uncertified_uses_raycast(tmp_path):
    tris = _unit_tetra()
    centroid = tris.reshape(-1, 3).mean(axis=0)
    raw = [t.copy() for t in tris]
    raw[1] = raw[1][[0, 2, 1]]           # inward-wound, no trustworthy flag
    meta = [{"certified": False, "invert": False} for _ in tris]
    fixed = repair.repaired_tris(np.array(raw), meta, cache_dir=tmp_path)
    assert all(_outward(t, centroid) for t in fixed)


def test_repaired_tris_cache_hit_skips_recompute(tmp_path):
    tris = _unit_tetra()
    meta = [{"certified": True, "invert": False} for _ in tris]
    a = repair.repaired_tris(tris, meta, cache_dir=tmp_path)
    files = list(tmp_path.glob("*.npz"))
    assert len(files) == 1                # wrote one cache entry
    b = repair.repaired_tris(tris, meta, cache_dir=tmp_path)   # second call
    assert np.array_equal(a, b)
    assert list(tmp_path.glob("*.npz")) == files   # no new file written
