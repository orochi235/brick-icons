"""Which analytic quadric a declared-smooth facet region is a tessellation of.

A region is facets joined across type-5 conditional lines (see
shade.declared_regions): the author's declaration that they are one smooth
surface, and the only license to treat them as one. Given that, `classify`
asks whether a sphere, an ellipsoid, or a cone (a cylinder is the cone with
no taper) passes through the region's vertices, trying them in that order,
each behind a residual gate relative to the surface's own size. A region
none of them fits is `None` -- freeform -- and is left to the shading it
already had.

Nothing here reads a dihedral angle: the region is given, and the fit only
says which surface it is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: Disarm to fit nothing: every region shades by its normals and outlines
#: by its facets, as before any quadric was fitted.
ARMED = True
#: A region whose normals all agree to within this (1 - cos) is flat, and no
#: quadric is fitted: 3040bp08's printed panel, a coplanar union, passed the
#: cone gate as a cylinder of enormous radius. The same bound the renderer
#: uses to keep a group flat-toned (shade.attach_group_gradients).
FLAT_SPREAD = 0.002
#: A fitted radius past this many times the region's own half-extent is a
#: curvature no shading can show: 3040bp08's flat print panel, with sliver
#: triangles that defeat the spread test, fit a sphere of radius 79189 LDU.
#: 51283 sits at 1.0; a shallow dish at a few.
MAX_RADIUS = 20.0
#: Fewest facets a region needs before a fit is attempted: below it a
#: sphere passes through almost anything.
MIN_FACETS = 16
#: Largest RMS distance from the fitted surface, over its radius (mean
#: semi-axis for an ellipsoid; see _extent), that still counts as a fit. A
#: vertex of an authored tessellation lies ON the surface, so an honest fit is
#: limited by authoring precision, not facet size. Measured (sphere residual,
#: scripts/measure-smooth-fit.py): 51283 0.0058, 3960 0.0019, 22119 0.0000;
#: freeform 3262's capsule 0.0226, 3626cp7d's head 0.0423.
SPHERE_TOL = 0.012
ELLIPSOID_TOL = 0.012
CONE_TOL = 0.02
#: A sphere that passes its gate still loses to an ellipsoid fitting far
#: better: 90370's spheroid fits a sphere to 0.0106 and an ellipsoid to
#: 0.0000, and its limb drawn as a circle would miss the outline. A sphere
#: keeps it within twice the ellipsoid's residual plus this.
SPHERE_SLACK = 0.002
#: An ellipsoid this elongated is a strip's curve being bridged by a
#: quadric, not a solid of revolution the author faceted.
MAX_AXIS_RATIO = 3.0
#: Taper (radius change per unit length along the axis) below which a cone
#: is reported as a cylinder.
CYLINDER_TAPER = 0.02


@dataclass
class Fit:
    kind: str                      # sphere | ellipsoid | cylinder | cone
    residual: float                # RMS distance over size
    center: np.ndarray
    radii: np.ndarray              # (r,) sphere; semi-axes ellipsoid; (r0, k) cone
    axes: np.ndarray = field(default_factory=lambda: np.eye(3))


def _unique(P, decimals=3):
    P = np.asarray(P, float).reshape(-1, 3)
    _, idx = np.unique(np.round(P, decimals), axis=0, return_index=True)
    return P[np.sort(idx)]


def _extent(P):
    """Half the diagonal of the points' box. Residuals are taken over the
    smaller of this and the fitted radius: over the radius alone, a nearly
    flat region fits a huge sphere with a residual that rounds to nothing."""
    return float(np.linalg.norm(np.ptp(P, axis=0))) / 2.0 or 1.0


def fit_sphere(P):
    """Algebraic least-squares sphere through the points; None if they are
    too few or coplanar."""
    P = _unique(P)
    if len(P) < 5:
        return None
    A = np.column_stack([2 * P, np.ones(len(P))])
    b = (P * P).sum(axis=1)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    c = sol[:3]
    r2 = float(sol[3] + c @ c)
    if r2 <= 0:
        return None
    r = np.sqrt(r2)
    res = float(np.sqrt(np.mean((np.linalg.norm(P - c, axis=1) - r) ** 2)))
    return Fit("sphere", res / min(r, _extent(P)), c, np.array([r]))


def fit_ellipsoid(P):
    """General quadric through the points, accepted only as a bounded,
    well-determined ellipsoid. None if the points do not pin one quadric
    down (two rings of a strip lie on a whole family of them)."""
    P = _unique(P)
    if len(P) < 12:
        return None
    m = P.mean(axis=0)
    s = float(np.abs(P - m).max()) or 1.0
    X = (P - m) / s
    x, y, z = X.T
    D = np.column_stack([x * x, y * y, z * z, 2 * x * y, 2 * x * z, 2 * y * z,
                         2 * x, 2 * y, 2 * z, np.ones(len(X))])
    _, sv, vt = np.linalg.svd(D, full_matrices=False)
    if sv[-2] < 1e-6 or sv[-1] / sv[-2] > 0.1:
        return None                         # a family of quadrics, not one
    q = vt[-1]
    M = np.array([[q[0], q[3], q[4]], [q[3], q[1], q[5]], [q[4], q[5], q[2]]])
    g = q[6:9]
    try:
        c = -np.linalg.solve(M, g)
    except np.linalg.LinAlgError:
        return None
    k = float(c @ M @ c + 2 * g @ c + q[9])
    w, V = np.linalg.eigh(M)
    ax2 = -k / w
    if np.any(ax2 <= 0):
        return None                         # not bounded: a hyperboloid or worse
    ax = np.sqrt(ax2)
    if ax.max() / ax.min() > MAX_AXIS_RATIO:
        return None
    # distance to the surface, to first order: |Q(p)| / |grad Q(p)|
    Qv = np.einsum("ij,jk,ik->i", X, M, X) + 2 * X @ g + q[9]
    grad = 2 * (X @ M + g)
    d = np.abs(Qv) / np.maximum(np.linalg.norm(grad, axis=1), 1e-12)
    res = float(np.sqrt(np.mean(d * d)) / min(ax.mean(), _extent(X)))
    return Fit("ellipsoid", res, c * s + m, ax * s, V)


def fit_cone(P, cents, normals):
    """Cone (or cylinder) through facets: every facet normal of a surface of
    revolution meets the axis, and a cone's normals keep one angle to it.

    `cents`/`normals` are per facet, `P` the region's vertices. Normals may
    arrive with either sign, so they are oriented away from the region's
    centroid first -- which is what fails on a nearly flat cone, and that
    region is then freeform rather than wrongly fitted."""
    N = np.asarray(normals, float)
    C = np.asarray(cents, float)
    if len(N) < 3:
        return None
    N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    N = N * np.sign(np.einsum("ij,ij->i", N, C - C.mean(axis=0)) + 1e-12)[:, None]
    _, sv, vt = np.linalg.svd(N - N.mean(axis=0), full_matrices=False)
    a = vt[-1]
    # the axis passes nearest every normal line, within the plane across it
    Ms, bs = np.zeros((3, 3)), np.zeros(3)
    for c, n in zip(C, N):
        Pn = np.eye(3) - np.outer(n, n)
        Ms += Pn
        bs += Pn @ c
    Ms += np.outer(a, a) * len(C)
    bs += np.outer(a, a) @ C.sum(axis=0)
    try:
        x0 = np.linalg.solve(Ms, bs)
    except np.linalg.LinAlgError:
        return None
    V = _unique(P) - x0
    h = V @ a
    r = np.linalg.norm(V - np.outer(h, a), axis=1)
    if np.ptp(h) < 1e-9:
        return None
    A = np.column_stack([np.ones(len(h)), h])
    (r0, k), *_ = np.linalg.lstsq(A, r, rcond=None)
    rm = min(float(r.mean()), _extent(V)) or 1.0
    res = float(np.sqrt(np.mean((r - (r0 + k * h)) ** 2)) / rm)
    kind = "cylinder" if abs(k) < CYLINDER_TAPER else "cone"
    return Fit(kind, res, x0, np.array([r0, k]), np.array([a]))


def classify(verts, normals):
    """The quadric a region tessellates, or None (freeform).

    `verts`: per facet, its (k,3) vertices; `normals`: per facet, a unit
    normal (either sign). A cone or cylinder is asked first, though it is the
    loosest model: a band only two rings of vertices deep lies EXACTLY on a
    sphere and on a cone at once -- 3649's 80-facet chamfer rings fit a
    sphere to 0.0001 -- and such a band is a turned surface, not a ball. A
    real sphere or ellipsoid misfits the cone by 0.07 or more (51283 0.34).
    Then a sphere, unless an ellipsoid fits far better."""
    if len(verts) < MIN_FACETS:
        return None
    N = np.asarray(normals, float)
    N = N[np.linalg.norm(N, axis=1) > 0.5]       # a sliver has no normal
    if not len(N) or float(np.abs(N @ N.T).min()) > 1.0 - FLAT_SPREAD:
        return None          # flat: a plane fits every model at a huge radius
    P = np.vstack([np.asarray(v, float) for v in verts])
    cents = [np.asarray(v, float).mean(axis=0) for v in verts]
    ext = _extent(P)
    f = fit_cone(P, cents, normals)
    if f is not None and f.residual <= CONE_TOL \
            and abs(float(f.radii[0])) <= MAX_RADIUS * ext:
        return f
    sph, ell = fit_sphere(P), fit_ellipsoid(P)
    if sph is not None and float(sph.radii[0]) > MAX_RADIUS * ext:
        sph = None
    if ell is not None and (ell.residual > ELLIPSOID_TOL
                            or float(ell.radii.max()) > MAX_RADIUS * ext):
        ell = None
    if sph is not None and sph.residual <= SPHERE_TOL and (
            ell is None or sph.residual <= 2 * ell.residual + SPHERE_SLACK):
        return sph
    return ell


def residuals(verts, normals):
    """Every model's residual, for measurement (None where it cannot fit)."""
    P = np.vstack([np.asarray(v, float) for v in verts])
    cents = [np.asarray(v, float).mean(axis=0) for v in verts]
    out = {}
    for name, fn in (("sphere", lambda: fit_sphere(P)),
                     ("ellipsoid", lambda: fit_ellipsoid(P)),
                     ("cone", lambda: fit_cone(P, cents, normals))):
        f = fn()
        out[name] = None if f is None else (f.kind, f.residual)
    return out


def regions_of(tris, colors, cond, min_facets=MIN_FACETS):
    """Triangle-index lists of the declared-smooth regions worth fitting:
    `min_facets` or more body-color triangles that actually curve -- so they
    joined across at least one conditional line, coplanar union being the
    only other join a body triangle gets (shade.declared_regions)."""
    from . import shade
    tris = np.asarray(tris, float).reshape(-1, 3, 3)
    if not len(tris):
        return []
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    cond = cond if cond is not None and len(cond) else np.zeros((0, 2, 3))
    labels = shade.declared_regions(list(tris), list(n), list(colors), cond)
    groups = {}
    for i, g in enumerate(labels):
        groups.setdefault(g, []).append(i)
    regions = []
    for ids in groups.values():
        if len(ids) < min_facets or colors[ids[0]] != 16:
            continue
        N = n[ids]
        if float(1.0 - (N @ N.T).min()) < FLAT_SPREAD:
            continue                         # flat: coplanar union only
        regions.append(ids)
    return regions


def load(part, ldraw_dir):
    """A part flattened, swept and repaired the way the engines see it."""
    from . import hlr, repair, sweep
    roots = hlr.default_roots(Path(ldraw_dir))
    path = hlr._resolve_input(part, roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(path, np.eye(3), np.zeros(3), out, roots)
    sweep.substitute(out)
    if out["tri"]:
        out["tri"] = list(repair.repaired_tris(
            np.array(out["tri"]), out["tri_meta"], hlr.MESH_CACHE_DIR))
    out["tri_colors"] = [m["color"] for m in out["tri_meta"]]
    return out


def part_regions(part, ldraw_dir, min_facets=MIN_FACETS, out=None):
    """Every declared-smooth faceted region of a part, geometry only (no
    view, no render): [(verts per tri, normal per tri)]."""
    out = out or load(part, ldraw_dir)
    tris = np.asarray(out["tri"], float).reshape(-1, 3, 3)
    res = []
    for ids in regions_of(tris, out["tri_colors"], out["5"], min_facets):
        T = tris[ids]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        res.append((list(T), list(n / np.linalg.norm(n, axis=1, keepdims=True))))
    return res


# --- the fitted surface's own outline ------------------------------------
# A fitted sphere or ellipsoid has an exact limb: the curve where its normal
# turns edge-on to the view. The facets' silhouette is a chord polygon inside
# it, so the contour and the conditional lines that read as silhouettes are
# re-read onto that limb -- the way arcfit re-reads a hand-faceted round.

def _key(p):
    return tuple(np.round(np.asarray(p, float), 3))


def fitted_regions(out):
    """The regions of `out` a sphere or ellipsoid fits, each as {fit, P (its
    vertices), keys (its vertex keys), step (its facets' angular size, deg)}.
    Empty when disarmed. Cones and cylinders are left out: their limbs are
    straight, and the silhouette chords already lie along them."""
    if not ARMED or not out.get("tri"):
        return []
    tris = np.asarray(out["tri"], float).reshape(-1, 3, 3)
    colors = out.get("tri_colors") or [16] * len(tris)
    found = []
    for ids in regions_of(tris, colors, out.get("5")):
        T = tris[ids]
        n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        fit = classify(list(T), list(n / np.linalg.norm(n, axis=1, keepdims=True)))
        if fit is None or fit.kind not in ("sphere", "ellipsoid"):
            continue
        P = _unique(T.reshape(-1, 3))
        edge = np.linalg.norm(T - np.roll(T, 1, axis=1), axis=2).ravel()
        step = float(np.degrees(np.median(edge) / float(np.mean(fit.radii))))
        found.append({"fit": fit, "P": P, "keys": {_key(p) for p in P},
                      "step": step})
    _share_spheres(found)
    return found


def _share_spheres(found):
    """Regions of one sphere take one fit, refitted over all their vertices.

    20401's and 32474's balls are two hemispheres authored apart; fitted
    separately their limbs differed in the fourth digit, so the two arcs
    never merged and the contour barbed where they met."""
    pools = []
    for r in found:
        f = r["fit"]
        if f.kind != "sphere":
            continue
        rad = float(f.radii[0])
        for pool in pools:
            f0 = pool[0]["fit"]
            if (np.linalg.norm(f.center - f0.center) <= 0.01 * rad
                    and abs(rad - float(f0.radii[0])) <= 0.01 * rad):
                pool.append(r)
                break
        else:
            pools.append([r])
    for pool in pools:
        if len(pool) < 2:
            continue
        joint = fit_sphere(np.vstack([r["P"] for r in pool]))
        if joint is None:
            continue
        for r in pool:
            r["fit"] = joint


def shape_matrix(fit):
    """A with (x - center)^T A (x - center) = 1 on the surface."""
    if fit.kind == "sphere":
        return np.eye(3) / float(fit.radii[0]) ** 2
    V = np.asarray(fit.axes, float)
    return V @ np.diag(1.0 / np.asarray(fit.radii, float) ** 2) @ V.T


def limb(fit, fwd):
    """The 3-D limb (C, U, V): point(t) = C + cos t*U + sin t*V is where the
    surface's normal is perpendicular to `fwd` -- for an ellipsoid a plane
    section through the center, whose projection is the outline."""
    A = shape_matrix(fit)
    C = np.asarray(fit.center, float)
    m = A @ np.asarray(fwd, float)
    m /= np.linalg.norm(m)
    e1 = np.cross(m, [1.0, 0.0, 0.0])
    if np.linalg.norm(e1) < 0.1:
        e1 = np.cross(m, [0.0, 1.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(m, e1)
    E = np.column_stack([e1, e2])
    w, W = np.linalg.eigh(E.T @ A @ E)
    return C, E @ W[:, 0] / np.sqrt(w[0]), E @ W[:, 1] / np.sqrt(w[1])


def region_of_condline(q, regions):
    """The fitted region a conditional line seams, or None: both its ends
    are vertices of that region."""
    a, b = _key(q[0]), _key(q[1])
    for r in regions:
        if a in r["keys"] and b in r["keys"]:
            return r
    return None


def limb_candidate(region, C, U, V, to_px, px=1.0):
    """Arc candidate (cx, cy, ux, uy, vx, vy, step, snap_tol) for the limb in
    the space `to_px` maps world points into; `px` is one render pixel there.

    The snap tolerance is how far inside the limb the facet polygon runs:
    per angular bin, the outermost region vertex's gap to the ellipse, over
    the bins the region reaches (90th percentile, so a truncated zone's open
    side does not set it). Margin and cap are the fitted-round candidates'."""
    x, y, _ = to_px(np.stack([C, C + U, C + V]))
    c = np.array([x[0], y[0]])
    M = np.array([[x[1] - c[0], x[2] - c[0]], [y[1] - c[1], y[2] - c[1]]])
    if abs(np.linalg.det(M)) < 1e-12:
        return None
    Minv = np.linalg.inv(M)
    px_, py_, _ = to_px(region["P"])
    d = np.stack([px_ - c[0], py_ - c[1]], 1)
    m = d @ Minv.T
    ru = np.hypot(m[:, 0], m[:, 1])
    th = np.arctan2(m[:, 1], m[:, 0])
    pr = np.hypot(d[:, 0], d[:, 1])
    bins = ((th + np.pi) / (2 * np.pi) * 72).astype(int) % 72
    gaps = []
    for b in np.unique(bins):
        k = np.flatnonzero(bins == b)
        j = k[np.argmax(ru[k])]
        if ru[j] > 0.5:
            gaps.append(abs(1.0 - ru[j]) * pr[j] / max(ru[j], 1e-9))
    dev = float(np.percentile(gaps, 90)) if gaps else 0.0
    return (float(c[0]), float(c[1]), float(M[0, 0]), float(M[1, 0]),
            float(M[0, 1]), float(M[1, 1]),
            min(region["step"] * 1.5 + 1.0, 46.0),
            min(dev * 1.25 + 0.5 * px, 6.0 * px))
