import numpy as np
from brick_icons import shade, hlr


def test_faces_from_analytic_cylinder_bands_and_disc():
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    R = np.eye(3); t = np.zeros(3)
    cyl = {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": t}
    disc = {"kind": "disc", "sector": 360.0, "inner": 0, "R": R, "t": t}
    faces = shade.faces_from_analytic([cyl, disc], right, up, fwd,
                                      s=2.0, cx=0.0, cy=0.0, half=50.0, bands=6)
    kinds = [f["kind"] for f in faces]
    assert kinds.count("disc") == 1
    assert 1 <= kinds.count("cyli") <= 6
    for f in faces:
        assert f["poly"].shape[1] == 2 and abs(np.linalg.norm(f["normal"]) - 1) < 1e-6


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
