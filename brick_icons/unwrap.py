"""Map a decal into its carrier's parameter space and back onto the exact
surface.

Every carrier goes through here — planar, cylinder and cone — because the
planar map being the identity is a degenerate case of the general one, not a
reason to skip it. One path means the flat case cannot drift; and unwrapping
first dissolves authored faceting (3941p01's panel is 36 quads approximating a
16-gon, which in (theta, h) is one rounded rectangle), so re-projection onto
the analytic carrier yields exact arcs instead of inheriting the author's
segment count.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import shapely

from . import colors as _colors
from . import geom2d

BIND_TOL = 0.5          # LDU; see the plan's measured table


def _axis_frame(prim):
    """(origin, axis unit vector, radius) for a cylinder/cone-like primitive."""
    A = prim.R[:, 1]
    h = float(np.linalg.norm(A))
    return prim.t, A / h if h else A, float(np.linalg.norm(prim.R[:, 0]))


def _circle_frame(prim):
    """(origin, axis, radius, e1, e2) with theta running the way LDraw's own
    cylinder primitives do — vertex k at (cos, y, sin) in the prim's columns.
    Cross-product e2 keeps the basis orthogonal even when R is slightly off;
    the sign check keeps it pointing where an inverted matrix says it should."""
    o, a, r = _axis_frame(prim)
    e1 = prim.R[:, 0] / np.linalg.norm(prim.R[:, 0])
    e2 = np.cross(e1, a)
    if float(e2 @ prim.R[:, 2]) < 0:
        e2 = -e2
    return o, a, r, e1, e2, float(np.linalg.norm(prim.R[:, 1])) or 1.0


def _local(pts, prim):
    """`pts` in the primitive's own frame, where the wall is the unit circle
    and the axis runs y = 0 to 1. Exact under scale and shear, which a
    world-space radius is not."""
    return (np.asarray(pts, float) - prim.t) @ np.linalg.inv(prim.R).T


def _radial_gap(pts, prim) -> float:
    """LDU off the wall, or inf when the geometry falls outside the extent the
    primitive actually spans. Without the extent test a primitive is an
    INFINITE surface, and a panel facet sitting at stud radius far below the
    studs binds to one."""
    p = _local(pts, prim)
    r = float(np.linalg.norm(prim.R[:, 0]))
    h = float(np.linalg.norm(prim.R[:, 1]))
    y = p[:, 1]
    if np.any(y < -BIND_TOL / h) or np.any(y > 1.0 + BIND_TOL / h):
        return np.inf
    want = np.array([prim.radius_at(float(v)) for v in y])
    return float(np.max(np.abs(np.hypot(p[:, 0], p[:, 2]) - want)) * r)


def _radius(prim, level, r):
    """World radius at each level along the axis. Constant for a cylinder,
    tapering for a cone — mapping a cone back at its base radius would put
    every point on a cylinder instead."""
    return r * np.array([prim.radius_at(float(v)) for v in np.atleast_1d(level)])


def _wrap(th):
    return (np.asarray(th, float) + np.pi) % (2 * np.pi) - np.pi


def _seam_origin(pts, carrier) -> float:
    """Put the branch cut in the widest angular gap the decal leaves empty.
    A fixed cut splits any decal that straddles it into two regions that can
    never merge, fit as one shape, or stroke as one boundary."""
    if isinstance(carrier, Plane):
        return 0.0
    o, a, r, e1, e2, _h = _circle_frame(carrier)
    d = np.asarray(pts, float).reshape(-1, 3) - o
    perp = d - np.outer(d @ a, a)
    th = np.sort(np.mod(np.arctan2(perp @ e2, perp @ e1), 2 * np.pi))
    if len(th) < 2:
        return 0.0
    gaps = np.diff(np.concatenate([th, th[:1] + 2 * np.pi]))
    i = int(np.argmax(gaps))
    return float(th[i] + gaps[i] / 2 - np.pi)


def _gap(pts, carrier) -> float:
    """Distance from `pts` to the carrier surface, by carrier kind. A planar
    carrier measures offset FROM the face; a radial metric would report
    position ALONG it, which is why 6141p01 and 3001p01 read 6.5 and 2.0 LDU
    under the axis measure — artifacts, not standoffs."""
    if isinstance(carrier, Plane):
        n = carrier.normal / np.linalg.norm(carrier.normal)
        return float(np.max(np.abs(np.asarray(pts, float) @ n - carrier.offset)))
    return _radial_gap(pts, carrier)


def bind(pts, carriers, tol: float = BIND_TOL):
    """The carrier `pts` lies on, or None. None means 'leave as authored'."""
    best, best_gap = None, tol
    for c in carriers:
        try:
            gap = _gap(pts, c)
        except (AttributeError, ValueError, IndexError):
            continue
        if gap <= best_gap:
            best, best_gap = c, gap
    return best


@dataclass
class Plane:
    """A flat carrier. Its unwrap is the identity in the face's own basis."""
    normal: np.ndarray
    offset: float
    _basis: tuple = field(default=None, repr=False)

    def basis(self):
        if self._basis is None:
            n = self.normal / np.linalg.norm(self.normal)
            seed = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 \
                else np.array([1.0, 0.0, 0.0])
            u = np.cross(n, seed)
            u /= np.linalg.norm(u)
            self._basis = (n, u, np.cross(n, u))
        return self._basis


def to_uv(pts, carrier, theta0=0.0):
    """Carrier parameter space, in LDU on both axes so one uniform scale
    keeps the texture isometric. `theta0` places the branch cut."""
    pts = np.asarray(pts, float)
    if isinstance(carrier, Plane):
        n, u, v = carrier.basis()
        return np.column_stack([pts @ u, pts @ v])
    o, a, r, e1, e2, h = _circle_frame(carrier)
    d = pts - o
    height = d @ a
    perp = d - np.outer(height, a)
    th = np.arctan2(perp @ e2, perp @ e1) - theta0
    return np.column_stack([_radius(carrier, height / h, r) * _wrap(th), height])


def to_xyz(uv, carrier, theta0=0.0):
    """Back onto the EXACT surface — this is where the sagitta closes."""
    uv = np.asarray(uv, float)
    if isinstance(carrier, Plane):
        n, u, v = carrier.basis()
        return (np.outer(uv[:, 0], u) + np.outer(uv[:, 1], v)
                + carrier.offset * n)
    o, a, r, e1, e2, h = _circle_frame(carrier)
    rad = _radius(carrier, uv[:, 1] / h, r)
    th = uv[:, 0] / rad + theta0
    return (o + np.outer(rad * np.cos(th), e1)
            + np.outer(rad * np.sin(th), e2) + np.outer(uv[:, 1], a))


def _region_d(poly, x0, y1, s):
    """Path data in canvas pixels, shapes recovered where the region is one.
    The fit tolerance is LDU, so it scales with the canvas."""
    if hasattr(poly, "geom_type"):
        return region_path(_scaled(poly, x0, y1, s), tol=CIRCLE_TOL * s)
    ring = _scaled_pts(np.asarray(poly, float), x0, y1, s)
    return " ".join(f"{'M' if i == 0 else 'L'}{p[0]:.2f},{p[1]:.2f}"
                    for i, p in enumerate(ring)) + " Z"


def _scaled_pts(pts, x0, y1, s):
    return np.column_stack([(pts[:, 0] - x0) * s, (y1 - pts[:, 1]) * s])


def _scaled(g, x0, y1, s):
    """Transform in place through shapely so exteriors, holes and multi-part
    structure survive; rebuilding from a flat ring list makes a second
    polygon's exterior into the first one's hole."""
    return shapely.transform(
        g, lambda a: np.column_stack([(a[:, 0] - x0) * s, (y1 - a[:, 1]) * s]))


def _rings_of(poly):
    """Boundary rings of a merged region, or the one ring of a raw polygon."""
    if hasattr(poly, "geom_type"):
        return geom2d.rings(poly)
    return [np.asarray(poly, float)]


def texture_svg(carrier_uv, regions, px=900, ldraw_dir="vendor/ldraw"):
    """The decal laid flat, canvas set by the carrier at ONE uniform scale."""
    cu = np.asarray(carrier_uv, float)
    x0, y0 = cu.min(axis=0)
    x1, y1 = cu.max(axis=0)
    s = px / max(x1 - x0, y1 - y0, 1e-9)
    w, h = (x1 - x0) * s, (y1 - y0) * s
    body = []
    for code, poly in regions:
        hex_str, _ = _colors.resolve(str(code), ldraw_dir)
        d = _region_d(poly, x0, y1, s)
        body.append(f'<path d="{d}" fill="#{hex_str[2:]}" '
                    f'fill-rule="evenodd"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
            f'height="{h:.0f}"><rect width="{w:.0f}" height="{h:.0f}" '
            f'fill="#ffffff"/>' + "".join(body) + "</svg>")


def carrier_extent(carrier, uv=None):
    """The canvas the texture is drawn on, as UV corners. A curved carrier
    knows its own extent — full wrap by full height — so the decal sits where
    it really lies on the part; a plane has none, and falls back to the
    decal's own bounds."""
    if isinstance(carrier, Plane) or carrier is None:
        pts = np.asarray(uv, float).reshape(-1, 2)
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    r = float(np.linalg.norm(carrier.R[:, 0]))
    h = float(np.linalg.norm(carrier.R[:, 1]))
    return np.array([[-np.pi * r, 0.0], [np.pi * r, 0.0],
                     [np.pi * r, h], [-np.pi * r, h]])


def bind_groups(tris, tri_colors, carriers):
    """[(carrier, theta0, [(code, uv_poly)])] for every decoration triangle
    that binds. Triangles binding to nothing are dropped, and their caller
    leaves the authored geometry alone."""
    groups = {}
    for tri, code in zip(np.asarray(tris, float), tri_colors):
        if code == 16:
            continue
        carrier = bind(tri, carriers)
        if carrier is None:
            continue
        groups.setdefault(id(carrier), (carrier, []))[1].append((code, tri))
    out = []
    for carrier, members in groups.values():
        pts = np.vstack([t for _, t in members])
        theta0 = _seam_origin(pts, carrier)
        out.append((carrier, theta0,
                    [(code, to_uv(t, carrier, theta0)) for code, t in members]))
    return out


def merge_regions(regions, holes=None):
    """Union same-colour facets in UV. Interior facet edges vanish with the
    union — a decal is one region, not a mesh."""
    by_code = {}
    for code, poly in regions:
        by_code.setdefault(code, []).append(
            geom2d.to_geom(np.asarray(poly, float)))
    cut = [geom2d.to_geom(np.asarray(h, float)) for h in (holes or [])]
    out = []
    for code, geoms in by_code.items():
        g = geom2d.union_all(geoms)
        for h in cut:
            g = geom2d.difference(g, h)
        out.append((code, _drop_collinear(g)))
    return out


def _drop_collinear(g):
    """A union leaves a vertex wherever a facet edge used to meet the boundary.
    They are no longer corners, and every one of them rides through the fit and
    into the emitted path."""
    try:
        s = g.simplify(geom2d.GRID, preserve_topology=True)
        return s if not s.is_empty else g
    except Exception:
        return g


def region_has_hole(g) -> bool:
    return any(len(getattr(part, "interiors", ())) for part in
               (getattr(g, "geoms", None) or [g]))


CIRCLE_TOL = 0.02       # LDU of residual; a 16-gon's own sagitta at r=2 is
                        # 0.038, so fit the VERTICES, not the chords
ARC_STEP = 25.0         # deg; an LDraw 16-gon steps 22.5 and the default 15
                        # would refuse to read its vertices as one arc


def fit_circle(poly, tol: float = CIRCLE_TOL):
    """(cx, cy, r) when `poly`'s vertices lie on a common circle, else None.
    Returning None is the normal outcome for a square and must stay cheap —
    most decal regions are not circles."""
    pts = np.asarray(poly, float)
    if len(pts) < 8:                     # too few to distinguish from a box
        return None
    # Kasa: |p|^2 = 2 p.c + (r^2 - |c|^2), linear in (cx, cy, k)
    A = np.column_stack([2 * pts, np.ones(len(pts))])
    try:
        cx, cy, k = np.linalg.lstsq(A, (pts ** 2).sum(axis=1), rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    rsq = k + cx * cx + cy * cy
    if rsq <= 0:
        return None
    r = float(np.sqrt(rsq))
    resid = np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - r)
    return (float(cx), float(cy), r) if float(resid.max()) <= tol else None


def fit_rounded_rect(poly, tol: float = CIRCLE_TOL):
    """(x0, y0, x1, y1, r) when `poly` is an axis-aligned rectangle with four
    equal-radius corner arcs, else None.

    Solve r from each corner vertex rather than from where the straight runs
    end: an arc runs within tol of its own tangent line for several vertices
    either side of the tangency, so a run measured that way reads long and r
    reads short (3941p01's panel: 1.087 against a true 1.261)."""
    pts = np.asarray(poly, float)
    if len(pts) < 8:
        return None
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    w, h = x1 - x0, y1 - y0
    if min(w, h) <= 2 * tol:
        return None
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    radii = []
    for ex, ey in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
        quad = pts[((pts[:, 0] < mx) == (ex == x0))
                   & ((pts[:, 1] < my) == (ey == y0))]
        a, b = np.abs(quad[:, 0] - ex), np.abs(quad[:, 1] - ey)
        on_arc = (a > tol) & (b > tol)
        if not np.any(on_arc):
            return None                  # a square corner, or no corner at all
        a, b = a[on_arc], b[on_arc]
        radii.append(np.median(a + b + np.sqrt(2 * a * b)))
    r = float(np.median(radii))
    if r <= tol or max(abs(v - r) for v in radii) > tol:
        return None
    if r >= min(w, h) / 2 - tol:
        return None                      # no straight run left: that's a circle
    inner = np.clip(pts, [x0 + r, y0 + r], [x1 - r, y1 - r])
    if float(np.abs(np.linalg.norm(pts - inner, axis=1) - r).max()) > tol:
        return None
    return (float(x0), float(y0), float(x1), float(y1), r)


def _rounded_rect_d(x0, y0, x1, y1, r):
    """One subpath, four arcs. Emitted directly rather than through path_d's
    candidate matching: a corner sweeps exactly 90 deg, which lands on the
    wrong side of that emitter's 90 deg chunk boundary by one float bit and
    doubles every corner."""
    def f(v):
        return f"{v:.2f}"
    a = f"A {f(r)} {f(r)} 0 0 1 "
    return (f"M {f(x0 + r)} {f(y0)} L {f(x1 - r)} {f(y0)} "
            + a + f"{f(x1)} {f(y0 + r)} "
            + f"L {f(x1)} {f(y1 - r)} " + a + f"{f(x1 - r)} {f(y1)} "
            + f"L {f(x0 + r)} {f(y1)} " + a + f"{f(x0)} {f(y1 - r)} "
            + f"L {f(x0)} {f(y0 + r)} " + a + f"{f(x0 + r)} {f(y0)} Z")


def region_path(g, tol=CIRCLE_TOL):
    """SVG path data for a UV region, with recovered shapes as A commands.
    Rounded rectangles are tried before circles: it is the commonest decal
    shape, and a circle fit would reject it anyway."""
    parts = []
    for ring in geom2d.rings(g):
        rr = fit_rounded_rect(ring, tol)
        if rr is not None:
            parts.append(_rounded_rect_d(*rr))
            continue
        cands = []
        c = fit_circle(ring, tol)
        if c is not None:
            cx, cy, r = c
            cands = [(cx, cy, r, 0.0, 0.0, r, ARC_STEP, tol)]
        parts.append(geom2d.path_d(
            geom2d.to_geom(ring),
            arcs=geom2d.arc_candidates(cands) if cands else None))
    return " ".join(x for x in parts if x)


def decorate(tris, tri_colors, carriers):
    """[(code, carrier, theta0, region)] for every decoration group that binds.
    Triangles binding to no carrier are omitted, and their caller leaves the
    authored geometry alone."""
    out = []
    for carrier, theta0, members in bind_groups(tris, tri_colors, carriers):
        for code, g in merge_regions(members):
            if not g.is_empty:
                out.append((code, carrier, theta0, g))
    return out


def densify(ring, step=0.25):
    """Resample a UV ring so its chords stay under `step` LDU. A curve
    recovered in UV re-projects through a camera, where it is no longer a
    circle, so the boundary has to carry its own resolution across."""
    pts = np.asarray(ring, float)
    closed = np.vstack([pts, pts[:1]])
    out = []
    for a, b in zip(closed[:-1], closed[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        out.append(a + np.outer(np.arange(n) / n, b - a))
    return np.vstack(out)
