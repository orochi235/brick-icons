import numpy as np
from brick_icons import shade, hlr


def test_cull_self_depth_keeps_own_curved_face():
    """A curved wall face must NOT cull itself: with self-depth taken from its
    OWN occluder at the centroid (not the band mean), and the own-occluder
    excluded from the scan, an isolated wall survives."""
    import numpy as np
    from brick_icons import shade

    class FakeOcc:                       # returns a fixed near depth at any ray
        def __init__(self, d): self.d = d
        def depth(self, O, F): return np.array([self.d], float)

    own = FakeOcc(1.0)                   # wall's near surface at depth 1.0
    face = {"poly": np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float),
            "depth": 5.0, "kind": "cyli"}        # band MEAN is 5.0 (farther)
    def ray_origin(xs, ys): return np.zeros((len(xs), 3))
    kept = shade.cull_occluded_faces(
        [face], occluders=[own], ray_origin=ray_origin, fwd=np.array([0, 0, 1.0]),
        eps=1e-3, kinds=("tri", "disc", "ring", "cyli"),
        own_occ={id(face): own})
    assert kept == [face]               # not culled by its own near surface


def test_cull_self_depth_removes_occluded_interior_face():
    import numpy as np
    from brick_icons import shade

    class FakeOcc:
        def __init__(self, d): self.d = d
        def depth(self, O, F): return np.array([self.d], float)

    own = FakeOcc(5.0)                   # interior tube near surface at 5.0
    wall = FakeOcc(1.0)                  # outer wall nearer, at 1.0
    face = {"poly": np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float),
            "depth": 5.0, "kind": "cyli"}
    def ray_origin(xs, ys): return np.zeros((len(xs), 3))
    kept = shade.cull_occluded_faces(
        [face], occluders=[own, wall], ray_origin=ray_origin,
        fwd=np.array([0, 0, 1.0]), eps=1e-3,
        kinds=("tri", "disc", "ring", "cyli"), own_occ={id(face): own})
    assert kept == []                   # outer wall occludes it -> culled


def test_cull_passthrough_for_untested_kinds():
    """A face whose kind is not in `kinds` passes through untouched."""
    import numpy as np
    from brick_icons import shade
    class FakeOcc:
        def depth(self, O, F): return np.array([0.0], float)   # always nearest
    face = {"poly": np.array([[0, 0], [1, 0], [0, 1]], float),
            "depth": 9.0, "kind": "tri"}
    def ray_origin(xs, ys): return np.zeros((len(xs), 3))
    kept = shade.cull_occluded_faces([face], occluders=[FakeOcc()],
                                     ray_origin=ray_origin, fwd=np.array([0, 0, 1.0]),
                                     eps=1e-3, kinds=("disc",))   # tri not listed
    assert kept == [face]


def test_faces_from_analytic_cylinder_gradient_and_disc():
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    R = np.eye(3); t = np.zeros(3)
    cyl = {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": t}
    disc = {"kind": "disc", "sector": 360.0, "inner": 0, "R": R, "t": t}
    faces = shade.faces_from_analytic([cyl, disc], right, up, fwd,
                                      s=2.0, cx=0.0, cy=0.0, half=50.0)
    kinds = [f["kind"] for f in faces]
    assert kinds.count("disc") == 1
    assert kinds.count("cyli") == 1              # one smooth arc-region wall, not bands
    disc_face = next(f for f in faces if f["kind"] == "disc")
    assert disc_face["poly"].shape[1] == 2 and abs(np.linalg.norm(disc_face["normal"]) - 1) < 1e-6
    cyl_face = next(f for f in faces if f["kind"] == "cyli")
    assert "grad_axis" in cyl_face and len(cyl_face["grad_samples"]) >= 2
    assert cyl_face["poly"].shape[1] == 2


def test_faces_from_analytic_ring_is_annulus_not_solid_disc():
    """A 'ring' primitive (inner radius N, outer N+1) must shade as an annulus
    with the center hole cut out — not a filled disc that covers the bore.
    View is set face-on to the ring so screen radii track world radii."""
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    # ring axis -> camera; U=right, V=up so it projects to a true (annular) circle
    R = np.stack([right, -fwd, up], axis=1)
    ring = {"kind": "ring", "sector": 360.0, "inner": 2, "R": R, "t": np.zeros(3)}
    faces = shade.faces_from_analytic([ring], right, up, fwd,
                                      s=1.0, cx=0.0, cy=0.0, half=0.0)
    poly = next(f for f in faces if f["kind"] == "ring")["poly"]
    c = poly.mean(axis=0)
    rad = np.linalg.norm(poly - c, axis=1)
    # inner arc at ~2, outer arc at ~3 -> clear inner/outer separation (ratio ~1.5).
    # A solid disc would put every vertex at the outer radius (ratio ~1.0).
    assert rad.max() / rad.min() > 1.3


def test_faces_from_tris_culls_back_and_projects():
    # a single CCW triangle in the z=0 plane (LDraw world)
    tri = np.array([[[0, 0, 0], [10, 0, 0], [0, 10, 0]]], float)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    faces = shade.faces_from_tris(tri, right, up, fwd, s=2.0, cx=0.0, cy=0.0, half=50.0)
    assert len(faces) in (0, 1)
    for f in faces:
        assert f["poly"].shape == (3, 2)
        assert abs(np.linalg.norm(f["normal"]) - 1.0) < 1e-6
        assert np.isfinite(f["depth"])
        assert f["kind"] == "tri"


def test_faces_from_tris_culls_backface_no_flip():
    """A triangle whose outward normal points AWAY from the camera is dropped,
    not flipped up into a bright top tone. Winding is now trusted."""
    import numpy as np
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    # Build a tri whose geometric normal points along +fwd (away from camera).
    # cross(v1-v0, v2-v0) should be ~ +fwd.
    v0 = np.zeros(3)
    v1 = right * 10.0
    v2 = np.cross(fwd, right) * 10.0        # so cross(v1,v2) proportional to fwd
    tri = np.array([[v0, v1, v2]], float)
    n = np.cross(v1 - v0, v2 - v0); n /= np.linalg.norm(n)
    assert n @ fwd > 0.5                      # confirm it's a back-face
    faces = shade.faces_from_tris(tri, right, up, fwd, s=2.0, cx=0, cy=0, half=50.0)
    assert faces == []                        # culled, not flipped


def test_flat3_tone_by_orientation():
    from brick_icons import shade
    style = shade.Flat3Style(part_color=(160, 160, 160))
    top = style.tone(np.array([0.0, 1.0, -0.1]))
    left = style.tone(np.array([-1.0, 0.0, -0.1]))
    right = style.tone(np.array([1.0, 0.0, -0.1]))
    assert top != left != right and top != right
    def lum(h): return int(h[1:3], 16)
    assert lum(top) > lum(left) > lum(right)


def test_parse_hex_color():
    from brick_icons import shade
    assert shade.parse_hex_color("0xFF8040") == (255, 128, 64)
    assert shade.parse_hex_color("#00ff00") == (0, 255, 0)
    assert shade.parse_hex_color(None) == (157, 157, 157)
    assert shade.parse_hex_color("nonsense") == (157, 157, 157)


def test_fill_ops_painter_sorted_back_to_front():
    from brick_icons import shade
    style = shade.Flat3Style()
    faces = [
        {"poly": np.array([[0, 0], [1, 0], [0, 1]]), "normal": np.array([0, 1, -1.0]),
         "depth": 5.0, "kind": "tri"},   # far
        {"poly": np.array([[0, 0], [2, 0], [0, 2]]), "normal": np.array([0, 1, -1.0]),
         "depth": 1.0, "kind": "tri"},   # near
    ]
    ops = shade.fill_ops(faces, style)
    assert [o["depth"] for o in ops] == [5.0, 1.0]   # far first
    assert "d" in ops[0] and ops[0]["fill"].startswith("#")


def test_fill_ops_unified_depth_sort_across_kinds():
    """Occlusion is by depth, NOT by flat-vs-curved. An interior curved face
    BEHIND a flat wall (larger depth) must paint under it; a stud curved face
    IN FRONT of a flat surface (smaller depth) must paint over it. A single
    far->near sort across all kinds achieves both."""
    from brick_icons import shade
    style = shade.Flat3Style()
    n = np.array([0.0, 1.0, -1.0])
    faces = [
        {"poly": np.array([[0, 0], [1, 0], [0, 1]]), "normal": n, "depth": 2.0, "kind": "tri"},   # front wall
        {"poly": np.array([[0, 0], [1, 0], [0, 1]]), "normal": n, "depth": 5.0, "kind": "disc"},  # interior tube (far)
        {"poly": np.array([[0, 0], [1, 0], [0, 1]]), "normal": n, "depth": 1.0, "kind": "disc"},  # stud top (near)
    ]
    ops = shade.fill_ops(faces, style)
    assert [o["depth"] for o in ops] == [5.0, 2.0, 1.0]   # strictly far->near, kind-agnostic


def test_highlight_ops_only_for_upfacing_discs():
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    R = np.eye(3); t = np.zeros(3)
    disc_up = {"kind": "disc", "sector": 360.0, "inner": 0, "R": R, "t": t}
    hi = shade.highlight_ops([disc_up], right, up, fwd, s=2.0, cx=0.0, cy=0.0,
                             half=50.0, strength=0.15)
    assert len(hi) == 1
    assert hi[0]["opacity"] <= 0.15 and hi[0]["cx"] is not None


def test_remap_highlights_applies_affine_and_strength():
    from brick_icons import shade
    out = shade.remap_highlights([{"cx": 10.0, "cy": 20.0, "r": 5.0, "opacity": 1.0}],
                                 f=2.0, ox=1.0, oy=3.0, strength=0.15)
    assert out[0] == {"cx": 21.0, "cy": 43.0, "r": 10.0, "opacity": 0.15}


def test_cull_multisample_keeps_face_with_occluded_centroid():
    """A small near feature (stud) covering only the CENTROID of a big face
    must not cull the whole face: 3001's top quad-tris have centroids inside
    stud footprints. Cull requires EVERY sample occluded, not just one."""
    import numpy as np
    from brick_icons import shade

    class StudOcc:                       # occludes only a small spot at (50,50)
        def depth(self, O, F):
            d = np.hypot(O[:, 0] - 50.0, O[:, 1] - 50.0)
            return np.where(d < 10.0, 1.0, np.inf)

    face = {"poly": np.array([[0, 0], [100, 0], [100, 100], [0, 100]], float),
            "depth": 5.0, "zs": np.full(4, 5.0), "kind": "tri"}
    def ray_origin(xs, ys):
        return np.stack([xs, ys, np.zeros_like(xs)], axis=1)
    kept = shade.cull_occluded_faces(
        [face], occluders=[StudOcc()], ray_origin=ray_origin,
        fwd=np.array([0, 0, 1.0]), eps=1e-3)
    assert kept == [face]                # corners visible -> face survives


def test_cull_multisample_still_removes_fully_hidden_face():
    """All samples behind a big wall -> culled (the sliver case must not
    regress from multi-sampling)."""
    import numpy as np
    from brick_icons import shade

    class WallOcc:                       # nearer everywhere
        def depth(self, O, F):
            return np.full(O.shape[0], 1.0)

    face = {"poly": np.array([[0, 0], [100, 0], [100, 100], [0, 100]], float),
            "depth": 5.0, "zs": np.full(4, 5.0), "kind": "tri"}
    def ray_origin(xs, ys):
        return np.stack([xs, ys, np.zeros_like(xs)], axis=1)
    kept = shade.cull_occluded_faces(
        [face], occluders=[WallOcc()], ray_origin=ray_origin,
        fwd=np.array([0, 0, 1.0]), eps=1e-3)
    assert kept == []
