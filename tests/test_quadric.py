"""Declared-smooth regions, the quadric fitted to one, and what 51283 (a
hand-faceted sphere) draws because of it."""
import math
import re

import numpy as np
import pytest

from brick_icons import quadric, shade


def _uv_sphere(r=10.0, c=(1.0, 2.0, 3.0), nlat=8, nlon=16, lat0=-70, lat1=70):
    """Triangles of a UV-tessellated sphere zone, vertices ON the sphere, and
    the conditional lines along every interior edge."""
    c = np.asarray(c, float)
    lats = np.radians(np.linspace(lat0, lat1, nlat + 1))
    lons = np.radians(np.linspace(0, 360, nlon, endpoint=False))

    def p(i, j):
        la, lo = lats[i], lons[j % nlon]
        return c + r * np.array([math.cos(la) * math.cos(lo), math.sin(la),
                                 math.cos(la) * math.sin(lo)])
    tris, cond = [], []
    for i in range(nlat):
        for j in range(nlon):
            a, b, cc, d = p(i, j), p(i, j + 1), p(i + 1, j + 1), p(i + 1, j)
            tris += [np.array([a, b, cc]), np.array([a, cc, d])]
            cond.append(np.array([b, cc]))            # meridian edge
            if i:
                cond.append(np.array([a, b]))         # parallel edge
    return np.array(tris), np.array(cond)


def _normals(tris):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    return n / np.linalg.norm(n, axis=1, keepdims=True)


# --- region detection ------------------------------------------------------

def test_a_conditional_line_joins_two_facets_and_a_bare_crease_does_not():
    a = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float)
    b = np.array([[1, 0, 0], [0, 1, 0], [1, 1, 0.5]], float)   # bent 25 deg
    tris = [a, b]
    n = list(_normals(np.array(tris)))
    seam = np.array([[[1, 0, 0], [0, 1, 0]]], float)
    joined = shade.declared_regions(tris, n, [16, 16], seam)
    apart = shade.declared_regions(tris, n, [16, 16], np.zeros((0, 2, 3)))
    assert joined[0] == joined[1]
    assert apart[0] != apart[1]


def test_a_sphere_s_facets_are_one_region():
    tris, cond = _uv_sphere()
    regions = quadric.regions_of(tris, [16] * len(tris), cond)
    assert [len(r) for r in regions] == [len(tris)]


def test_51283_is_one_region_of_192_triangles(ldraw_dir):
    out = quadric.load("51283", ldraw_dir)
    regions = quadric.regions_of(out["tri"], out["tri_colors"], out["5"])
    assert sorted(len(r) for r in regions)[-1] == 192


# --- the fit ---------------------------------------------------------------

def test_a_tessellated_sphere_fits_a_sphere():
    tris, _ = _uv_sphere(r=7.0, c=(3, -2, 5))
    fit = quadric.classify(list(tris), list(_normals(tris)))
    assert fit is not None and fit.kind == "sphere"
    assert fit.residual < 1e-6
    assert np.allclose(fit.center, [3, -2, 5], atol=1e-6)
    assert fit.radii[0] == pytest.approx(7.0)


def test_a_tessellated_ellipsoid_fits_an_ellipsoid():
    tris, _ = _uv_sphere(r=1.0, c=(0, 0, 0))
    tris = tris * np.array([6.0, 4.0, 5.0])
    fit = quadric.classify(list(tris), list(_normals(tris)))
    assert fit is not None and fit.kind == "ellipsoid"
    assert sorted(fit.radii) == pytest.approx([4.0, 5.0, 6.0], rel=1e-6)


def test_a_faceted_cylinder_fits_a_cylinder():
    th = np.radians(np.arange(0, 360, 22.5))
    ring = np.stack([5 * np.cos(th), np.zeros_like(th), 5 * np.sin(th)], 1)
    tris = []
    for k in range(3):
        lo, hi = ring + [0, 4 * k, 0], ring + [0, 4 * (k + 1), 0]
        for j in range(len(th)):
            a, b = lo[j], lo[(j + 1) % len(th)]
            c, d = hi[(j + 1) % len(th)], hi[j]
            tris += [np.array([a, b, c]), np.array([a, c, d])]
    tris = np.array(tris)
    fit = quadric.classify(list(tris), list(_normals(tris)))
    assert fit is not None and fit.kind == "cylinder"
    assert fit.radii[0] == pytest.approx(5.0, rel=0.01)


def test_a_flat_region_fits_nothing():
    """A coplanar union fits every model at a huge radius; 3040bp08's
    printed panel came out as a 'cylinder' before the flat guard."""
    xs, ys = np.meshgrid(np.arange(5.0), np.arange(5.0))
    P = np.stack([xs, ys, np.zeros_like(xs)], -1)
    tris = []
    for i in range(4):
        for j in range(4):
            tris += [np.array([P[i, j], P[i, j + 1], P[i + 1, j + 1]]),
                     np.array([P[i, j], P[i + 1, j + 1], P[i + 1, j]])]
    tris = np.array(tris)
    assert quadric.classify(list(tris), list(_normals(tris))) is None


def test_a_torus_patch_is_freeform():
    """A bent tube is the case the tone bands exist for; no quadric may claim
    it."""
    R, r = 10.0, 3.0
    us = np.radians(np.linspace(0, 120, 9))
    vs = np.radians(np.arange(0, 360, 30))

    def p(u, v):
        return np.array([(R + r * math.cos(v)) * math.cos(u), r * math.sin(v),
                         (R + r * math.cos(v)) * math.sin(u)])
    tris = []
    for i in range(len(us) - 1):
        for j in range(len(vs)):
            a, b = p(us[i], vs[j]), p(us[i + 1], vs[j])
            c, d = p(us[i + 1], vs[(j + 1) % len(vs)]), p(us[i], vs[(j + 1) % len(vs)])
            tris += [np.array([a, b, c]), np.array([a, c, d])]
    tris = np.array(tris)
    assert quadric.classify(list(tris), list(_normals(tris))) is None


def test_a_sphere_s_limb_is_the_circle_across_the_view():
    tris, _ = _uv_sphere(r=4.0, c=(0, 0, 0))
    fit = quadric.classify(list(tris), list(_normals(tris)))
    fwd = np.array([0.3, -0.5, 0.8]) / np.linalg.norm([0.3, -0.5, 0.8])
    C, U, V = quadric.limb(fit, fwd)
    assert np.linalg.norm(U) == pytest.approx(4.0)
    assert np.linalg.norm(V) == pytest.approx(4.0)
    assert abs(U @ fwd) < 1e-9 and abs(V @ fwd) < 1e-9 and abs(U @ V) < 1e-9


# --- 51283: what the fit draws ----------------------------------------------

def _render(part, slot, tmp_path, armed=True):
    from brick_icons import cli, db
    saved = quadric.ARMED
    quadric.ARMED = armed
    try:
        args = cli._parse_args(db.canonical_argv(part, slot) + ["--out", str(tmp_path)])
        cli.process_one(cli._config_from_args(args), part, tmp_path)
    finally:
        quadric.ARMED = saved
    return (tmp_path / f"{part}.svg").read_text()


def _sphere_gradient(svg):
    """(stops as gray levels, focal) of the widest radial gradient."""
    best = None
    for m in re.finditer(r'<radialGradient[^>]*fx="([-\d.]+)" fy="([-\d.]+)"'
                         r'[^>]*matrix\(([\d.]+)[^>]*>(.*?)</radialGradient>', svg):
        stops = [int(c[:2], 16) for c in
                 re.findall(r'stop-color="#([0-9a-f]{6})"', m.group(4))]
        if best is None or float(m.group(3)) > best[0]:
            best = (float(m.group(3)), stops)
    return None if best is None else best[1]


def _contour_lines(svg):
    m = re.search(r'<path d="([^"]*)"[^>]*stroke-miterlimit="5"', svg)
    return m.group(1).count("L") if m else None


@pytest.mark.parametrize("slot", ["occt", "naive"])
def test_51283_shades_as_one_sphere_with_a_falling_ramp(slot, tmp_path, ldraw_dir):
    """Fitted, the sphere is one radial ramp computed from the sphere: a
    handful of stops, falling from the highlight to the limb. Disarmed, occt
    posterized it facet by facet (its far half sampled as a mirror of the
    near), and naive binned 10 stops off the facets."""
    stops = _sphere_gradient(_render("51283", slot, tmp_path / "on"))
    assert stops is not None and len(stops) <= shade.SPHERE_STOPS
    assert all(a >= b for a, b in zip(stops, stops[1:]))
    before = _sphere_gradient(_render("51283", slot, tmp_path / "off", armed=False))
    assert before is None or len(before) > shade.SPHERE_STOPS


@pytest.mark.parametrize("slot", ["occt", "naive"])
def test_51283_outline_is_the_fitted_limb(slot, tmp_path, ldraw_dir):
    """The contour runs along the sphere's limb as arcs, not along the facet
    polygon: 16 chords of it came out as L commands before."""
    assert _contour_lines(_render("51283", slot, tmp_path / "on")) <= 4
    assert _contour_lines(_render("51283", slot, tmp_path / "off", armed=False)) >= 12
