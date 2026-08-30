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

# A connector marking: LDraw authors a minifig neck as a 270-degree colour-16
# cylinder plus a 90-degree one in black, and the head covers that quarter on
# an assembled figure. Nothing in its authoring distinguishes it from print —
# 3942bp01's cone stripes partition their wall into coloured and colour-16
# sectors summing to 360 the same way — so it is caught by position and size
# together. Swept over all 11,220 printed parts (scripts/sweep-marker-prims.py):
# the two conditions isolate 1,388 torso necks, at clearance +4.0 and share
# 0.250 exactly, from 2,160 on-body prints at clearance <= 0. Either condition
# alone admits 29030p01's head print and 53983p01's turbine case.
MARKER_CLEARANCE = 0.05     # LDU it must stand proud of the body
MARKER_SHARE = 0.25 + 1e-6  # fraction of its surface's ring it may cover


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


LDRAW_UP = np.array([0.0, -1.0, 0.0])


def up_aligned(n):
    """(u, v) in the plane of `n`, with v the part's up.

    Seeding off a fixed axis instead leaves the rotation arbitrary — a decal
    on 3040bp08's slope unwrapped with v pointing DOWN the part, so its print
    laid flat upside down. u = v x n keeps the frame right-handed about the
    OUTWARD normal, which is what stops glyphs mirroring.
    """
    v = LDRAW_UP - n * float(LDRAW_UP @ n)
    if float(np.linalg.norm(v)) < 1e-6:
        # a top or bottom face has no up to inherit. +Z is where LDraw
        # authors put the top of a glyph on one — measured, not assumed:
        # 2431pt2's "Octan" and 3068bpfi's "FABULAND" lay out 180 deg off
        # under -Z
        alt = np.array([0.0, 0.0, 1.0])
        v = alt - n * float(alt @ n)
    v = v / np.linalg.norm(v)
    return np.cross(v, n), v


@dataclass
class Plane:
    """A flat carrier. Its unwrap is the identity in the face's own basis."""
    normal: np.ndarray
    offset: float
    _basis: tuple = field(default=None, repr=False)

    def basis(self):
        if self._basis is None:
            n = self.normal / np.linalg.norm(self.normal)
            self._basis = (n,) + up_aligned(n)
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


def texture_svg(carrier_uv, regions, px=900, ldraw_dir="vendor/ldraw",
                face=None, bg="#ffffff"):
    """The decal laid flat, canvas set by the carrier at ONE uniform scale.

    `face` is the carrier's own outline, drawn under the decal so the texture
    carries the shape it was lifted from — 30260p01's octagon, a torso's
    trapezoid — rather than reading as a print floating on a rectangle.
    """
    cu = np.asarray(carrier_uv, float)
    x0, y0 = cu.min(axis=0)
    x1, y1 = cu.max(axis=0)
    s = px / max(x1 - x0, y1 - y0, 1e-9)
    w, h = (x1 - x0) * s, (y1 - y0) * s
    body = []
    if bg and bg != "none":
        body.append(f'<rect width="{w:.0f}" height="{h:.0f}" fill="{bg}"/>')
    if face is not None and not face.is_empty:
        body.append(f'<path d="{_region_d(face, x0, y1, s)}" '
                    f'fill="#f2f2f2" fill-rule="evenodd"/>')
    for code, poly in regions:
        hex_str, _ = _colors.resolve(str(code), ldraw_dir)
        d = _region_d(poly, x0, y1, s)
        body.append(f'<path d="{d}" fill="#{hex_str[2:]}" '
                    f'fill-rule="evenodd"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
            f'height="{h:.0f}">' + "".join(body) + "</svg>")


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
        c = fit_circle(ring, tol)
        if c is not None:
            cx, cy, r = c
            arcs = geom2d.arc_candidates([(cx, cy, r, 0.0, 0.0, r,
                                           ARC_STEP, tol)])
        else:
            # the whole ring is not one circle, but parts of it may still
            # follow one — a union leaves strays, and an emblem can be several
            # concentric arcs joined by straight runs
            arcs = _circle_arcs(ring, max(tol, SNAP_TOL * tol / CIRCLE_TOL))
        parts.append(geom2d.path_d(geom2d.to_geom(ring), arcs=arcs))
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


PLANE_COS = 0.9994      # ~2 deg; an LDraw 16-gon steps 22.5, so merging this
                        # tightly cannot flatten a faceted wall into one plane


def planes_from(polys, inside=None):
    """A `Plane` per distinct facet plane, normals pointing away from `inside`.

    Winding is not trustworthy in raw LDraw geometry, so the outward sense
    comes from the part's own interior rather than the cross product's sign —
    an inward normal would hand `up_aligned` a mirrored frame.
    """
    inside = np.zeros(3) if inside is None else np.asarray(inside, float)
    norms, offs, out = np.empty((0, 3)), np.empty(0), []
    for p in polys:
        p = np.asarray(p, float)
        if len(p) < 3:
            continue
        n = np.cross(p[1] - p[0], p[2] - p[0])
        ln = float(np.linalg.norm(n))
        if ln < 1e-9:
            continue
        n = n / ln
        d = float(n @ p[0])
        if float(n @ inside) > d:
            n, d = -n, -d
        # matched by proximity, not by a rounded key: two facets of one face
        # differ in the 4th decimal, and a grid splits them whenever that
        # noise straddles a boundary — 10049p01's front came out as four
        # planes and took the decal's dominant group down with it
        if len(out) and np.any((norms @ n > PLANE_COS)
                               & (np.abs(offs - d) <= 0.05)):
            continue
        out.append(Plane(normal=n, offset=d))
        norms = np.vstack([norms, n])
        offs = np.append(offs, d)
    return out


def _surface_key(prim, tol=0.01):
    """The surface a primitive lies on, independent of the sector of it that
    the primitive covers and of its colour."""
    q = lambda v: tuple(np.round(np.asarray(v, float) / tol).astype(np.int64))
    return (prim.kind, q(prim.t), q(prim.R[:, 1]),
            int(round(float(np.linalg.norm(prim.R[:, 0])) / tol)))


def marker_prims(analytic, tris=None, tri_colors=None):
    """ids of coloured primitives that mark a connector rather than print it.

    See MARKER_CLEARANCE. Returns an empty set when the part has no body
    triangles to measure against, so an unmeasurable part keeps its geometry.
    """
    body = None
    if tris is not None and tri_colors is not None and len(tris):
        tris = np.asarray(tris, float)
        keep = np.asarray(tri_colors) == 16
        if keep.any():
            body = tris[keep]
    if body is None or not len(body):
        return set()
    top = float(body[..., 1].min())      # LDraw up is -y

    by_surface = {}
    for p in analytic:
        by_surface.setdefault(_surface_key(p), []).append(p)

    out = set()
    for prims in by_surface.values():
        if not any(getattr(p, "color", 16) == 16 for p in prims):
            continue
        total = sum(p.sector for p in prims)
        for c in {getattr(p, "color", 16) for p in prims} - {16}:
            members = [p for p in prims if getattr(p, "color", 16) == c]
            if sum(p.sector for p in members) / max(total, 1e-9) > MARKER_SHARE:
                continue
            pts = np.vstack([np.asarray(p.fit_pts(), float) for p in members])
            if top - float(pts[:, 1].max()) > MARKER_CLEARANCE:
                out.update(id(p) for p in members)
    return out


def prim_loop(prim, n=48):
    """The world-space boundary of a primitive's own surface, as one loop.

    A wall is bounded by its two end rings, a flat kind by its rim; either way
    the decal a coloured primitive paints IS that surface, so its outline is
    the primitive's own extent rather than anything fitted.
    """
    th = np.linspace(0.0, np.radians(prim.sector), n)
    inner = getattr(prim, "inner", None)
    if inner is not None:                       # ring: rim out, rim back in
        outer = prim.ring_pts(th, 0.0, radius=inner + 1)
        return np.vstack([outer, prim.ring_pts(th[::-1], 0.0, radius=inner)])
    if prim.kind in ("cyli", "con"):            # wall: base ring, top ring back
        return np.vstack([prim.ring_pts(th, 0.0),
                          prim.ring_pts(th[::-1], 1.0)])
    rim = prim.ring_pts(th, 0.0)                # disc: rim, closed at the axis
    return rim if prim.is_full else np.vstack([rim, prim.t[None, :]])


def prim_regions(analytic, carriers, skip=()):
    """[(colour, carrier, pts)] for every coloured primitive that binds.

    Decoration is not all triangles: 3942bp01's stripes are 16 coloured cone
    sectors and no coloured facets at all, so a triangle-only extraction
    emits an empty texture for it.
    """
    out = []
    for p in analytic:
        code = getattr(p, "color", 16)
        if code == 16 or id(p) in skip:
            continue
        pts = prim_loop(p)
        carrier = bind(pts, carriers)
        if carrier is not None:
            out.append((code, carrier, pts))
    return out


def carrier_face(carrier, tris, theta0=0.0, contains=None, extra=()):
    """The carrier's own face in UV — the surface the decal is printed on.

    A plane's face is the union of every facet lying in it, PRINT INCLUDED:
    decoration replaces the body facets under it, so unioning colour 16 alone
    leaves the leftover strips around 973p01's stripes instead of the torso's
    front. `contains` picks the component the decal sits in, since a part
    usually has other geometry in the same plane (30260p01 has 13 further
    coplanar scraps besides its octagon).
    """
    if not isinstance(carrier, Plane):
        return None
    tris = np.asarray(tris, float)
    if not len(tris):
        return None
    n = carrier.basis()[0]
    # one pass over every facet, not one per carrier: a high-poly torso is 58
    # carriers over 2,000 facets, and the per-triangle Python test dominated
    on = np.abs(tris @ n - carrier.offset).max(axis=1) <= BIND_TOL
    # `extra` carries the outlines of flat primitives lying in this plane. A
    # round tile's top face is a disc, so the facets alone describe only the
    # print on it, and the face came out as the emblem's own 48-gon instead of
    # the tile — faceted, where the primitive knows the true circle.
    src = [to_uv(t, carrier, theta0) for t in tris[on]]
    src += [to_uv(np.asarray(e, float), carrier, theta0) for e in extra
            if np.abs(np.asarray(e, float) @ n - carrier.offset).max() <= BIND_TOL]
    polys = []
    for uv in src:
        g = shapely.geometry.Polygon(uv)
        if not g.is_valid:
            g = g.buffer(0)
        if not g.is_empty:
            polys.append(g)
    if not polys:
        return None
    face = geom2d.union_all(polys)
    parts = list(getattr(face, "geoms", [face]))
    if contains is not None and len(parts) > 1:
        probe = shapely.geometry.MultiPoint(
            np.asarray(contains, float).reshape(-1, 2)).centroid
        parts.sort(key=lambda g: (not g.contains(probe), -g.area))
    else:
        parts.sort(key=lambda g: -g.area)
    return parts[0]


def decal_groups(tris, tri_colors, analytic):
    """[(carrier, theta0, regions, face)] for every decal a part carries.

    Decoration reaches here two ways — coloured facets and coloured
    primitives — and both have to be collected or a part extracts to an empty
    texture: 3942bp01 is 16 coloured cone sectors and no coloured facets at
    all, 973p01 is six facets and one primitive.

    Carriers are BODY surfaces only. Binding to a decoration primitive would
    make every one of 3942bp01's stripes its own carrier and its own texture,
    where they are four bands on one cone.
    """
    tris = np.asarray(tris, float) if len(tris) else np.empty((0, 3, 3))
    tri_colors = np.asarray(tri_colors)
    # only WALLS are curved carriers. A disc or ring is flat, but to_uv sends
    # every non-Plane carrier through the cylindrical map, where a flat
    # surface has one constant height — so a round tile's print, which sits on
    # a disc coincident with its top face, unwrapped to a zero-area line and
    # vanished. The plane over those same facets is the carrier it wants.
    body_prims = [p for p in analytic
                  if getattr(p, "color", 16) == 16 and p.kind in ("cyli", "con")]
    inside = tris.reshape(-1, 3).mean(axis=0) if len(tris) else None
    # a flat primitive contributes its plane: a round tile's top face IS a
    # disc, so it has no facets of its own and the only planes the triangles
    # could offer were the rim's 51 vertical ones — 146 of 14769pt1's 162
    # decoration facets bound to nothing at all
    flat = [prim_loop(p) for p in analytic
            if getattr(p, "color", 16) == 16 and p.kind in ("disc", "ring")]
    planes = planes_from([t for t, c in zip(tris, tri_colors) if c == 16]
                         + flat, inside=inside)
    skip = marker_prims(analytic, tris, tri_colors)

    families = {}         # surface -> every body section on it
    for p in body_prims:
        fam = _wall_family(p)
        if fam is not None:
            families.setdefault(fam, []).append(p)

    members = {}          # surface -> (carrier, [(code, world pts)])

    def add(carrier, code, pts):
        key = _group_key(carrier)
        if key in members:
            members[key][1].append((code, pts))
            return
        sections = families.get(key)
        span = (span_carrier(sections) if sections and len(sections) > 1
                else carrier)
        members[key] = (span, [(code, pts)])

    for t, code in zip(tris, tri_colors):
        if code == 16:
            continue
        carrier = bind(t, body_prims) or bind(t, planes)
        if carrier is not None:
            add(carrier, code, t)
    for code, carrier, pts in prim_regions(analytic, body_prims + planes, skip):
        add(carrier, code, pts)

    out = []
    for carrier, group in members.values():
        pts = np.vstack([p for _, p in group])
        theta0 = _seam_origin(pts, carrier)
        uv = [(code, to_uv(p, carrier, theta0)) for code, p in group]
        regions = merge_regions(uv)
        if not regions:
            continue
        face = carrier_face(carrier, tris, theta0,
                            contains=np.vstack([p for _, p in uv]),
                            extra=flat)
        if face is not None:
            face = _drop_collinear(face)
        out.append((carrier, theta0, regions, face))
    # biggest print first, so `<part>.decal.0.svg` is the one worth looking at:
    # a high-poly torso scatters across dozens of small facet planes and the
    # authored order buries its front among them
    out.sort(key=lambda g: -sum(r.area for _c, r in g[2]))
    return out


SLIVER_FRAC = 0.10      # drop a group below this share of the biggest print
SHATTER_SHARE = 0.10    # below this, the biggest print is itself a shard
MAX_DECALS = 4          # above this many survivors, one decoration cut across faces


def _print_area(group):
    return float(sum(r.area for _c, r in group[2]))


def significant_groups(groups):
    """Drop decoration that is not a usable decal, from `decal_groups` output.

    A print bound to facet planes rather than one carrier splits across them:
    a torso yields 59 groups where one is the garment, and a sculpted part
    yields hundreds of shards of a single decoration. Three different failures,
    so three rules. Slivers go by their share of the biggest print. Shatter is a
    part-level verdict: when even the biggest group holds almost none of the
    printed area, nothing survived intact and returning its largest shard
    would dress a fragment up as a decal. The count cap is the third, and neither
    ratio catches it: every survivor can clear the sliver bar while the
    dominant clears the shatter bar. Inspected across the corpus, a part above
    the cap is always ONE decoration split over faces rather than several
    prints -- 20460p09's five are panels of the same striped garment.

    Ratios, not absolute areas — measured over the extraction corpus, a real
    second print runs as low as 0.069 of its dominant while shards reach 0.82,
    so neither bound separates them alone. `scripts/measure-decal-slivers.py`
    re-derives both numbers.
    """
    areas = [_print_area(g) for g in groups]
    total = sum(areas)
    if not groups or total <= 0:
        return []
    top = max(areas)
    if top / total < SHATTER_SHARE:
        return []
    kept = [g for g, a in zip(groups, areas) if a >= top * SLIVER_FRAC]
    return [] if len(kept) > MAX_DECALS else kept


def decal_svgs(tris, tri_colors, analytic, px=900, ldraw_dir="vendor/ldraw",
               bg=None):
    """[svg] one per carrier the part carries a decal on."""
    svgs = []
    for carrier, _theta0, regions, face in significant_groups(
            decal_groups(tris, tri_colors, analytic)):
        # a merged region can come back with no ring at all — a sliver that
        # collapses to a line, which is not something to draw or to size a
        # canvas from
        rings = [r for _c, g in regions for r in _rings_of(g) if len(r)]
        if not rings:
            continue
        uv = np.vstack([np.asarray(r) for r in rings])
        ext = carrier_extent(carrier, uv if face is None
                             else np.asarray(face.exterior.coords))
        svgs.append(texture_svg(ext, regions, px=px, ldraw_dir=ldraw_dir,
                                face=face, bg=bg))
    return svgs


def _wall_family(prim, tol=0.01):
    """The infinite surface a wall section lies on, or None if not a wall.

    LDraw tiles a tall cone as stacked sections — 3942bp01's is four — and each
    is a separate primitive. They are one surface to a decal that runs down
    them, so grouping by primitive identity would cut its stripes into four
    textures. Keyed by the axis LINE, the taper, and the radius extrapolated to
    a datum shared by every section, so height along the axis drops out.
    """
    if prim.kind not in ("cyli", "con"):
        return None
    A = np.asarray(prim.R[:, 1], float)
    h = float(np.linalg.norm(A))
    if h < 1e-9:
        return None
    a = A / h
    if a[np.argmax(np.abs(a))] < 0:          # canonical: the line, not its sense
        a = -a
    t = np.asarray(prim.t, float)
    perp = t - a * float(t @ a)
    r = float(np.linalg.norm(prim.R[:, 0]))
    # both ends measured along the CANONICAL axis: taking the radii from the
    # primitive's own direction while measuring position along the flipped one
    # gives each section of a cone a different apex, and none of them merge
    s0, s1 = float(t @ a), float((t + A) @ a)
    r0, r1 = r * prim.radius_at(0.0), r * prim.radius_at(1.0)
    slope = (r1 - r0) / (s1 - s0) if abs(s1 - s0) > 1e-9 else 0.0
    q = lambda v: tuple(np.round(np.asarray(v, float) / tol).astype(np.int64))
    return (prim.kind, q(a), q(perp), int(round(slope / tol)),
            int(round((r0 - slope * s0) / tol)))


def _group_key(carrier):
    fam = _wall_family(carrier) if not isinstance(carrier, Plane) else None
    return fam if fam is not None else id(carrier)


def span_carrier(prims):
    """One primitive covering every section in a wall family.

    Merging sections but keeping one section's frame is not enough: `to_uv`
    scales arc length by the radius the cone's taper predicts at that height,
    so a point four sections away extrapolates past the apex and lands
    thousands of LDU off canvas. The spanning carrier makes those heights
    interior to its own extent.
    """
    from . import primitives

    ref = prims[0]
    A = np.asarray(ref.R[:, 1], float)
    a = A / np.linalg.norm(A)
    if a[np.argmax(np.abs(a))] < 0:
        a = -a
    ss, radii = [], []
    for p in prims:
        Ap = np.asarray(p.R[:, 1], float)
        rp = float(np.linalg.norm(p.R[:, 0]))
        for lvl, s in ((0.0, float(p.t @ a)), (1.0, float((p.t + Ap) @ a))):
            ss.append(s)
            radii.append(rp * p.radius_at(lvl))
    ss, radii = np.asarray(ss, float), np.asarray(radii, float)
    smin, smax = float(ss.min()), float(ss.max())
    if smax - smin < 1e-9:
        return ref
    # the two end radii, not a least-squares line: every radius on a cylinder
    # family is identical and the s values repeat, which is ill-conditioned
    # enough that polyfit returns a ~1e-6 slope and turns the wall into a
    # needle-thin cone
    rb = float(radii[np.isclose(ss, smin)].mean())
    rt = float(radii[np.isclose(ss, smax)].mean())

    _o, a_ref, _r, e1, e2, _h = _circle_frame(ref)
    if float(a_ref @ a) < 0:        # keep theta running the same way about `a`
        e2 = -e2
    t = np.asarray(ref.t, float)
    origin = t - a * float(t @ a) + a * smin
    H = smax - smin
    if abs(rt - rb) < 1e-6 * max(rb, 1.0):
        R = np.column_stack([e1 * rb, a * H, e2 * rb])
        return primitives.Cylinder(R=R, t=origin, sector=360.0, color=16)
    ru = rb - rt
    R = np.column_stack([e1 * ru, a * H, e2 * ru])
    return primitives.Cone(R=R, t=origin, sector=360.0, color=16,
                           top=rt / ru)


SNAP_TOL = 0.4          # LDU a vertex may sit off a recovered circle. The
                        # union of a 48-gon with a 16-gon leaves the coarser
                        # one's chord midpoints 0.345 inside the true rim
                        # (14769pt1), and those are on the intended circle.


def circle_candidates(ring, tol=SNAP_TOL, min_pts=6):
    """Circles the ring's vertices lie on, for per-run arc recovery.

    fit_circle answers "is this whole ring one circle", which a decal boundary
    usually is not: a union leaves strays, and a shape can be several
    concentric arcs joined by straight runs. Clustering radii about a common
    centre finds each circle present, and path_d converts only the runs that
    genuinely follow one — so an octagon, whose 8 vertices do share a radius,
    is still refused on ARC_STEP.
    """
    pts = np.asarray(ring, float)
    if len(pts) < min_pts:
        return []
    A = np.column_stack([2 * pts, np.ones(len(pts))])
    try:
        cx, cy, _k = np.linalg.lstsq(A, (pts ** 2).sum(axis=1), rcond=None)[0]
    except np.linalg.LinAlgError:
        return []
    rad = np.hypot(pts[:, 0] - cx, pts[:, 1] - cy)
    out, order = [], np.argsort(rad)
    start = 0
    for i in range(1, len(order) + 1):
        if i < len(order) and rad[order[i]] - rad[order[start]] <= tol:
            continue
        members = order[start:i]
        start_prev, start = start, i
        if len(members) < min_pts:
            continue
        # The centre above is fitted to the WHOLE ring, which is only
        # meaningful when the ring is concentric. On an arch (14769px2) it is
        # nowhere near the real arc centres, so a radius cluster there groups
        # unrelated vertices and invents a circle; snapping a run onto it
        # threw a stray arc clean outside the part's silhouette. Refit to the
        # cluster alone and keep it only if its own points truly lie on it.
        fit = fit_circle(pts[members], tol)
        if fit is None:
            continue
        fcx, fcy, fr = fit
        res = np.abs(np.hypot(pts[members, 0] - fcx,
                              pts[members, 1] - fcy) - fr).max()
        if res <= tol:
            out.append((fcx, fcy, fr))
    return out


def _circle_arcs(ring, tol):
    """arc_candidates for every circle `ring` follows, widest first."""
    cands = [(cx, cy, r, 0.0, 0.0, r, ARC_STEP, tol)
             for cx, cy, r in circle_candidates(ring, tol)]
    return geom2d.arc_candidates(sorted(cands, key=lambda c: -c[2])) or None
