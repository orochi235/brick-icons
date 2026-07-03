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
