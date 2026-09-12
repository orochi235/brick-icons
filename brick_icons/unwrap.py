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

import math
from dataclasses import dataclass, field

import numpy as np
import shapely

from . import colors as _colors
from . import geom2d

BIND_TOL = 0.5          # LDU; see the plan's measured table

# A connector marking: LDraw authors a minifig neck as a 270-degree color-16
# cylinder plus a 90-degree one in black, and the head covers that quarter on
# an assembled figure. Nothing in its authoring distinguishes it from print —
# 3942bp01's cone stripes partition their wall into colored and color-16
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


def _scale(prim):
    """(world radius, world height) — the lengths the UV metric is in."""
    return (float(np.linalg.norm(prim.R[:, 0])),
            float(np.linalg.norm(prim.R[:, 1])) or 1.0)


def _local_arc(pts, prim):
    """(theta, level) on the primitive's own wall, exact under scale and
    shear. The orthonormalized frame `_circle_frame` builds is a CIRCLE, and
    a sheared carrier's section is an ellipse that meets it in one place."""
    p = _local(pts, prim)
    return np.arctan2(p[:, 2], p[:, 0]), p[:, 1]


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
    top = getattr(prim, "level_top", 1.0) + BIND_TOL / h
    bot = getattr(prim, "level_bot", 0.0) - BIND_TOL / h
    if np.any(y < bot) or np.any(y > top):
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
    arc, _level = _local_arc(np.asarray(pts, float).reshape(-1, 3), carrier)
    th = np.sort(np.mod(arc, 2 * np.pi))
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


def standoff(pts, carrier) -> float:
    """How far `pts` stand PROUD of the carrier surface; 0 if they do not.

    A print on a curved wall is inscribed in it -- its facets are chords, so
    every vertex reads at or inside the surface, 3941p01 and 3062bp01 by
    0.02 at worst. A FORMED STICKER is a separate part laid on top and reads
    outside it, 15068dy6 by 0.29, and binds all the same at BIND_TOL.
    Reconstructing that on the carrier drops it under its own uncolored
    geometry, which then paints over the print.

    Raising a decoration that had nothing under it changes nothing, which is
    what makes this safe to apply to all of them: 3068bp01 and 11055d0d read
    0.45 and draw the same pixels either way.

    The outermost vertex, not the mean: what this raises has to clear every
    facet it was built from. A defect cannot raise it far -- geometry
    further out than BIND_TOL does not bind at all.
    """
    pts = np.asarray(pts, float).reshape(-1, 3)
    if isinstance(carrier, Plane):
        n = carrier.normal / np.linalg.norm(carrier.normal)
        return max(0.0, float(np.max(pts @ n - carrier.offset)))
    p = _local(pts, carrier)
    r = float(np.linalg.norm(carrier.R[:, 0]))
    want = np.array([carrier.radius_at(float(v)) for v in p[:, 1]])
    return max(0.0, float(np.max(np.hypot(p[:, 0], p[:, 2]) - want)) * r)


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


#: How far off square to LDraw's up axis a carrier may lean before its own
#: axis still settles which way is up. Past it the carrier is lying on its
#: side, and +Z decides — the same fallback `up_aligned` takes above.
AXIS_UP_TOL = 0.05
AXIS_UP_ALT = np.array([0.0, 0.0, 1.0])


def axis_reversed(carrier) -> bool:
    """Whether a curved carrier's authored axis runs against the part's up.

    `up_aligned` settles this for a plane; a cylinder or cone instead inherits
    whatever direction the author gave `R[:, 1]`, and a minifig head's is +Y,
    which is LDraw DOWN — so its face unwrapped upside down. Asks only about
    the declared coordinate frame, so a cracked or unwelded carrier answers
    the same as a sound one.
    """
    A = np.asarray(carrier.R[:, 1], float)
    n = float(np.linalg.norm(A))
    if n < 1e-9:
        return False
    a = A / n
    d = float(a @ LDRAW_UP)
    return (float(a @ AXIS_UP_ALT) if abs(d) < AXIS_UP_TOL else d) < 0


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


@dataclass
class Skirt:
    """A wall carrier continued past its own ends, over what it runs into.

    A minifig head's print does not stop where its r=13 wall does -- it runs
    onto the jaw at one end and over the crown at the other, both of which
    LDraw builds from `t04o6250` quarter-torus subfiles that arrive
    tessellated. `bind` had nothing to bind that ink to and `bind_groups`
    dropped it.

    Everything the unwrap needs from a carrier it asks `radius_at` for -- the
    bind test's target radius, the arc-length scale `to_uv` gives u, and the
    radius `to_xyz` puts a point back at. So continuing a surface is a matter
    of answering that question outside [0, 1], and no other rule changes.

    BOTH ends, because a wall is not special at one of them: 3626bp63's
    forehead lines run over the crown, and a skirt built only past level 1
    left its upper line clipped exactly as the jaw's ink had been.

    The profile is sampled off the part's own tessellation rather than read
    from the torus that declares it: `primitives.parse_primitive` matches only
    `<num>-<den><family>` and has no torus case, so the declaration is gone by
    the time geometry arrives here. Teaching the loader that family is the
    durable fix and this is not it.
    """
    base: object
    hi: tuple = None          # (levels ascending from 1, radii) or None
    lo: tuple = None          # (levels ascending to 0, radii) or None

    @property
    def R(self):
        return self.base.R

    @property
    def t(self):
        return self.base.t

    @property
    def kind(self):
        return self.base.kind

    @property
    def color(self):
        return getattr(self.base, "color", 16)

    @property
    def level_top(self):
        return 1.0 if self.hi is None else float(self.hi[0][-1])

    @property
    def level_bot(self):
        return 0.0 if self.lo is None else float(self.lo[0][0])

    def radius_at(self, level):
        level = float(level)
        if level > 1.0 and self.hi is not None:
            return float(np.interp(level, self.hi[0], self.hi[1]))
        if level < 0.0 and self.lo is not None:
            return float(np.interp(level, self.lo[0], self.lo[1]))
        return self.base.radius_at(min(max(level, 0.0), 1.0))


#: How close two levels must be to count as the same latitude ring, in LDU,
#: and how far past a section to continue a wall, as a multiple of the
#: section's height. A fixed band grid was the first try and it conflated
#: 3626bp39's last two rings -- 0.31 LDU apart, inside one band -- so the
#: profile stopped at the wrong radius and the jaw's last course of ink was
#: left a separate slab under the beard. A surface of revolution arrives as
#: rings; read the rings.
SKIRT_RING = 0.05
SKIRT_REACH = 0.5


def _skirt_side(y, rad, carrier, reach, up):
    """(levels, radii) continuing one end of a section, or None.

    `up` picks the end: past level 1, or before level 0. Written once and
    called twice, because a wall is not special at either end.
    """
    h = float(np.linalg.norm(carrier.R[:, 1])) or 1.0
    edge = 1.0 if up else 0.0
    away = (y - edge) if up else (edge - y)          # distance past the end
    keep = (away > 0) & (away <= reach)
    if not keep.any():
        return None
    away, r = away[keep], rad[keep]
    order = np.argsort(away)
    away, r = away[order], r[order]
    # one sample per latitude ring, cut where the level jumps by more than a
    # ring's worth. A gap between rings is a coarse tessellation, not the end
    # of the surface, so it splits clusters and nothing more.
    cuts = np.flatnonzero(np.diff(away) > SKIRT_RING / h) + 1
    dists, radii = [0.0], [float(carrier.radius_at(edge))]
    for grp in np.split(np.arange(len(away)), cuts):
        d = float(np.median(away[grp]))
        if d <= dists[-1]:
            continue
        dists.append(d)
        # the median, and never wider than the ring nearer the section: a
        # skirt curves inward, and a ring left holding only its outer
        # vertices where decoration cut it away would otherwise read as the
        # wall flaring back out
        radii.append(min(float(np.median(r[grp])), radii[-1]))
    if len(dists) < 3:
        return None
    dists = np.asarray(dists, float)
    radii = np.asarray(radii, float)
    if up:
        return edge + dists, radii
    return (edge - dists)[::-1], radii[::-1]         # ascending levels


def skirt(carrier, pts, reach=SKIRT_REACH):
    """`carrier` continued over the geometry past either end, or unchanged.

    Every triangle, not the color-16 ones: decoration lies on the same
    surface, and a print that COVERS a skirt leaves almost no body
    tessellation to read it from. 3626bp39's beard wraps the whole jaw.

    `reach` bounds how far past a section to look -- a wall does not continue
    forever, and without a bound the profile swallows the neck and then the
    torso.
    """
    if isinstance(carrier, Plane) or carrier is None:
        return carrier
    pts = np.asarray(pts, float).reshape(-1, 3)
    if not len(pts):
        return carrier
    p = _local(pts, carrier)
    y, rad = p[:, 1], np.hypot(p[:, 0], p[:, 2])
    hi = _skirt_side(y, rad, carrier, reach, up=True)
    lo = _skirt_side(y, rad, carrier, reach, up=False)
    if hi is None and lo is None:
        return carrier
    return Skirt(base=carrier, hi=hi, lo=lo)


def to_uv(pts, carrier, theta0=0.0):
    """Carrier parameter space, in LDU on both axes so one uniform scale
    keeps the texture isometric. `theta0` places the branch cut."""
    pts = np.asarray(pts, float)
    if isinstance(carrier, Mesh):
        return carrier.at(pts)
    if isinstance(carrier, Plane):
        n, u, v = carrier.basis()
        return np.column_stack([pts @ u, pts @ v])
    r, h = _scale(carrier)
    arc, level = _local_arc(pts, carrier)
    uv = np.column_stack([_radius(carrier, level, r) * _wrap(arc - theta0),
                          level * h])
    # Negating BOTH components is a 180-degree rotation, so a reversed axis
    # turns the print upright without mirroring its glyphs.
    return -uv if axis_reversed(carrier) else uv


def to_xyz(uv, carrier, theta0=0.0, standoff=0.0):
    """Back onto the EXACT surface — this is where the sagitta closes.

    `standoff` raises the result that far along the outward normal, for a
    decal that sits proud of its carrier rather than printed on it. The
    ANGLE still comes from the carrier's own radius, so raising a region
    lifts it without sliding it around the part.
    """
    uv = np.asarray(uv, float)
    if isinstance(carrier, Mesh):
        # no standoff: a mesh carrier IS the tessellation the ink sits on, so
        # there is no gap between the two to raise the result out of
        return carrier.to_world(uv)
    if isinstance(carrier, Plane):
        n, u, v = carrier.basis()
        return (np.outer(uv[:, 0], u) + np.outer(uv[:, 1], v)
                + (carrier.offset + standoff) * n)
    if axis_reversed(carrier):
        uv = -uv
    r, h = _scale(carrier)
    level = uv[:, 1] / h
    rad = _radius(carrier, level, r)
    th = uv[:, 0] / rad + theta0
    # A local radial scale, which is what `Cylinder.raised` does to the depth
    # source: the two have to lift a region by the same amount or the boolean
    # clip cuts the drawing away against its own occluder.
    out = (rad + standoff) / r
    local = np.column_stack([out * np.cos(th), level, out * np.sin(th)])
    return np.asarray(carrier.t, float) + local @ np.asarray(carrier.R, float).T


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


def _extent_size(carrier_uv):
    """(w, h) of a carrier extent, in LDU."""
    cu = np.asarray(carrier_uv, float)
    lo, hi = cu.min(axis=0), cu.max(axis=0)
    return float(hi[0] - lo[0]), float(hi[1] - lo[1])


def _panel_paths(carrier_uv, regions, s, ldraw_dir, face):
    """One decal's `<path>` elements, drawn at the scale it is handed.

    Split out of `texture_svg` so a sheet can draw several panels at ONE
    scale; `texture_svg` is this at the scale that makes a single panel fill
    its canvas.
    """
    cu = np.asarray(carrier_uv, float)
    x0, _y0 = cu.min(axis=0)
    _x1, y1 = cu.max(axis=0)
    body = []
    if face is not None and not face.is_empty:
        body.append(f'<path d="{_region_d(face, x0, y1, s)}" '
                    f'fill="#f2f2f2" fill-rule="evenodd"/>')
    for code, poly in regions:
        hex_str, _ = _colors.resolve(str(code), ldraw_dir)
        d = _region_d(poly, x0, y1, s)
        body.append(f'<path d="{d}" fill="#{hex_str[2:]}" '
                    f'fill-rule="evenodd"/>')
    return body


def texture_svg(carrier_uv, regions, px=900, ldraw_dir="vendor/ldraw",
                face=None, bg="#ffffff"):
    """The decal laid flat, canvas set by the carrier at ONE uniform scale.

    `face` is the carrier's own outline, drawn under the decal so the texture
    carries the shape it was lifted from — 30260p01's octagon, a torso's
    trapezoid — rather than reading as a print floating on a rectangle.
    """
    ew, eh = _extent_size(carrier_uv)
    s = px / max(ew, eh, 1e-9)
    w, h = ew * s, eh * s
    body = []
    if bg and bg != "none":
        body.append(f'<rect width="{w:.0f}" height="{h:.0f}" fill="{bg}"/>')
    body += _panel_paths(carrier_uv, regions, s, ldraw_dir, face)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
            f'height="{h:.0f}">' + "".join(body) + "</svg>")


def _corners(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])


def carrier_extent(carrier, uv=None):
    """The canvas the texture is drawn on, as UV corners. A curved carrier
    knows its own extent — full wrap by full height — so the decal sits where
    it really lies on the part; a plane has none, and falls back to the
    decal's own bounds.

    A curved carrier's extent is a floor, not a bound. A minifig head's print
    runs onto the dome the wall cylinder stops at, so its ink reaches past
    both ends of that 13-LDU section — and the canvas is the SVG's viewport,
    so whatever sits outside is cut rather than merely off-centre. Measured
    over 400 parts: 29% of curved carriers overrun, by 3.7% of the canvas at
    the median and 7.7% at the worst, always at the top and bottom of a face.
    Where the ink does fit, the union is the carrier's own rectangle and the
    drawing is unchanged."""
    if isinstance(carrier, (Plane, Mesh)) or carrier is None:
        pts = np.asarray(uv, float).reshape(-1, 2)
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        return _corners(x0, y0, x1, y1)
    r = float(np.linalg.norm(carrier.R[:, 0]))
    h = float(np.linalg.norm(carrier.R[:, 1]))
    top = getattr(carrier, "level_top", 1.0) * h
    bot = getattr(carrier, "level_bot", 0.0) * h
    ext = np.array([[-np.pi * r, bot], [np.pi * r, bot],
                    [np.pi * r, top], [-np.pi * r, top]])
    if axis_reversed(carrier):
        ext = -ext
    if uv is None:
        return ext
    pts = np.asarray(uv, float).reshape(-1, 2)
    if not len(pts):
        return ext
    lo = np.minimum(ext.min(axis=0), pts.min(axis=0))
    hi = np.maximum(ext.max(axis=0), pts.max(axis=0))
    return _corners(lo[0], lo[1], hi[0], hi[1])


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
    """Union same-color facets in UV. Interior facet edges vanish with the
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
PLANE_OFF = 0.05        # LDU between two planes that are the same plane


def _plane_seen(norms, offs, n, d) -> bool:
    """Whether (n, d) is already in the parallel arrays, by proximity."""
    return bool(len(norms) and np.any((norms @ n > PLANE_COS)
                                      & (np.abs(offs - d) <= PLANE_OFF)))


def dedupe_planes(planes):
    """`planes` with near-duplicates of one surface dropped, first kept.

    A rounded key is not enough: two facets of one face differ in the 4th
    decimal, and a grid splits them whenever that noise straddles a boundary.
    """
    out, norms, offs = [], np.empty((0, 3)), np.empty(0)
    for p in planes:
        n = np.asarray(p.normal, float)
        ln = float(np.linalg.norm(n))
        if ln < 1e-9:
            continue
        n, d = n / ln, float(p.offset) / ln
        if _plane_seen(norms, offs, n, d):
            continue
        out.append(p)
        norms = np.vstack([norms, n])
        offs = np.append(offs, d)
    return out


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
        # matched by proximity, not by a rounded key: 10049p01's front came
        # out as four planes and took the decal's dominant group down with it
        if _plane_seen(norms, offs, n, d):
            continue
        out.append(Plane(normal=n, offset=d))
        norms = np.vstack([norms, n])
        offs = np.append(offs, d)
    return out


def reseat_plane(carrier, pts, inside=None):
    """`carrier` moved onto the plane `pts` lie in, pointing away from `inside`.

    A decal lies ON the face it decorates, so its carrier's outward normal
    points at it. Artwork covering a face edge to edge leaves that face with
    no body facets at all, so `planes_from` never builds its plane and `bind`
    matches the face BEHIND the sheet — antiparallel, which hands
    `up_aligned` a mirrored frame. 6041468c and its Mirrored twin 6041468d
    came out the wrong way round and 6041468k backwards throughout; 190265d,
    the same 0.25 LDU sticker but with an unprinted border, read correctly on
    the strength of the 311 body facets that border leaves behind.
    """
    if not isinstance(carrier, Plane):
        return carrier
    n = np.asarray(carrier.normal, float)
    ln = float(np.linalg.norm(n))
    pts = np.asarray(pts, float).reshape(-1, 3)
    if ln < 1e-9 or not len(pts):
        return carrier
    n = n / ln
    # median, not mean: a decal with a facet straying off its face must not
    # drag the carrier off it
    d = float(np.median(pts @ n))
    inside = np.zeros(3) if inside is None else np.asarray(inside, float)
    if float(n @ inside) > d:
        n, d = -n, -d
    return Plane(normal=n, offset=d)


def _surface_key(prim, tol=0.01):
    """The surface a primitive lies on, independent of the sector of it that
    the primitive covers and of its color."""
    q = lambda v: tuple(np.round(np.asarray(v, float) / tol).astype(np.int64))
    return (prim.kind, q(prim.t), q(prim.R[:, 1]),
            int(round(float(np.linalg.norm(prim.R[:, 0])) / tol)))


def marker_prims(analytic, tris=None, tri_colors=None):
    """ids of colored primitives that mark a connector rather than print it.

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
    the decal a colored primitive paints IS that surface, so its outline is
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
    """[(color, carrier, pts)] for every colored primitive that binds.

    Decoration is not all triangles: 3942bp01's stripes are 16 colored cone
    sectors and no colored facets at all, so a triangle-only extraction
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
    decoration replaces the body facets under it, so unioning color 16 alone
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

    Decoration reaches here two ways — colored facets and colored
    primitives — and both have to be collected or a part extracts to an empty
    texture: 3942bp01 is 16 colored cone sectors and no colored facets at
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

    # One carrier per wall SURFACE, continued over whatever it runs into,
    # and built before anything binds. Lazily, a skirt exists only once its
    # wall has been bound to -- and by then a facet plane over the jaw's own
    # tessellation has already claimed the ink sitting on it, which scattered
    # 20 of 3626bp39's beard triangles into shards and left a 1.5-LDU band of
    # its chin blank between the wall and what the skirt did recover.
    all_pts = tris.reshape(-1, 3) if len(tris) else tris
    carriers = []
    for fam, sections in families.items():
        span = span_carrier(sections) if len(sections) > 1 else sections[0]
        carriers.append(skirt(span, all_pts))
    carriers += [p for p in body_prims if _wall_family(p) is None]

    members = {}          # surface -> (carrier, [(code, world pts)])

    def add(carrier, code, pts):
        members.setdefault(_group_key(carrier), (carrier, []))[1].append(
            (code, pts))

    for t, code in zip(tris, tri_colors):
        if code == 16:
            continue
        carrier = bind(t, carriers) or bind(t, planes)
        if carrier is not None:
            add(carrier, code, t)
    for code, carrier, pts in prim_regions(analytic, carriers + planes, skip):
        add(carrier, code, pts)

    out = []
    for carrier, group in members.values():
        pts = np.vstack([p for _, p in group])
        carrier = reseat_plane(carrier, pts, inside)
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


def significant_groups(groups, cap: int | None = MAX_DECALS,
                       shatter: bool = True):
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

    `cap=None` and `shatter=False` turn off the two rules that read a count
    as evidence of breakage, for groups that cannot break that way: a welded
    mesh carries each island of ink whole, so seventeen of them is a print
    with seventeen islands -- 30117p62's insectoid markings -- and not one
    print in seventeen pieces. The sliver rule survives either way, because a
    region far smaller than the biggest is noise under both readings.
    """
    areas = [_print_area(g) for g in groups]
    total = sum(areas)
    if not groups or total <= 0:
        return []
    top = max(areas)
    if shatter and top / total < SHATTER_SHARE:
        return []
    kept = [g for g, a in zip(groups, areas) if a >= top * SLIVER_FRAC]
    return [] if cap is not None and len(kept) > cap else kept


#: LDU within which two decoration vertices are the same vertex. LDraw parts
#: arrive unwelded, so a parameterization has no connectivity to work with
#: until they are merged. Not a tuned number: over 250 parts the count that
#: welds into a single piece is 100 / 110 / 108 at 0.001 / 0.01 / 0.1.
WELD_TOL = 0.01

#: What a flattening has to clear to be worth drawing. A patch that is not a
#: disk -- a torso closing round, a cap closing over -- folds onto itself,
#: and overlapping ink unions into a different picture rather than a
#: distorted one. `scripts/unwrap-decal-mesh.py` re-derives both: area spread
#: is bimodal over the same 250 parts, 69% under 1.5 and the top decile past
#: 37, so a bound anywhere between separates them.
MESH_FLIP_MAX = 0.02
MESH_STRETCH_MAX = 4.0


@dataclass
class Mesh:
    """A carrier that is the print's own triangles, flattened.

    A sculpted mould declares no surface, so there is nothing for the
    cylindrical map to be the arc length of and every facet plane claims its
    own shard of the ink. The print is a triangle patch either way, so this
    carries it as one: `uv` is a conformal flattening, and the map either way
    is piecewise linear over the same triangles. Exact on the tessellation --
    which, on a part with no analytic surface, is the surface, so there is no
    sagitta left for `to_xyz` to close.
    """
    V: np.ndarray                        # welded world vertices
    F: np.ndarray                        # triangles, indices into V
    uv: np.ndarray                       # one uv per vertex
    kind = "mesh"
    color = 16
    _lookup: dict = field(default=None, repr=False)
    _tree: object = field(default=None, repr=False)

    def at(self, pts):
        """uv for points that are the mesh's own vertices."""
        if self._lookup is None:
            self._lookup = {tuple(k): i for i, k in
                            enumerate(np.round(self.V / WELD_TOL).astype(np.int64))}
        pts = np.asarray(pts, float).reshape(-1, 3)
        keys = np.round(pts / WELD_TOL).astype(np.int64)
        out = np.empty((len(pts), 2))
        for i, k in enumerate(keys):
            j = self._lookup.get(tuple(k))
            if j is None:                # not a welded vertex: nearest one
                j = int(np.argmin(np.linalg.norm(self.V - pts[i], axis=1)))
            out[i] = self.uv[j]
        return out

    def to_world(self, uv):
        """Back onto the mesh, barycentrically in the triangle that holds
        each uv point."""
        if self._tree is None:
            self._tree = shapely.STRtree(
                [shapely.Polygon(self.uv[f]) for f in self.F])
        uv = np.asarray(uv, float).reshape(-1, 2)
        out = np.empty((len(uv), 3))
        for i, p in enumerate(uv):
            hits = self._tree.query(shapely.Point(p))
            f = self.F[hits[0]] if len(hits) else self.F[
                int(np.argmin(np.linalg.norm(self.uv[self.F[:, 0]] - p, axis=1)))]
            a, b, c = self.uv[f]
            M = np.array([[b[0] - a[0], c[0] - a[0]],
                          [b[1] - a[1], c[1] - a[1]]])
            try:
                st = np.linalg.solve(M, p - a)
            except np.linalg.LinAlgError:
                st = np.zeros(2)
            A, B, C = self.V[f]
            out[i] = A + st[0] * (B - A) + st[1] * (C - A)
        return out


def weld_decoration(tris, tri_colors, tol: float = WELD_TOL):
    """(V, F, codes) -- every decoration triangle, vertices merged by
    position. Body facets are left out: the carrier is the print itself."""
    keep = [(np.asarray(t, float).reshape(3, 3), c)
            for t, c in zip(tris, tri_colors) if c != 16 and c != 24]
    if not keep:
        return np.zeros((0, 3)), np.zeros((0, 3), int), []
    P = np.vstack([t for t, _c in keep])
    q = np.round(P / tol).astype(np.int64)
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    V = np.zeros((len(uniq), 3))
    np.add.at(V, inv, P)
    V /= np.bincount(inv, minlength=len(uniq))[:, None]
    return V, inv.reshape(-1, 3), [c for _t, c in keep]


def mesh_pieces(V, F):
    """Face indices of each connected piece, largest first. A piece is an
    island of ink -- two eyes and a mouth are three, and each flattens on its
    own -- not a shard of one print, which is what facet binding produces."""
    parent = np.arange(len(V))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for f in F:
        for a, b in ((f[0], f[1]), (f[1], f[2])):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    root = np.array([find(int(v)) for v in F[:, 0]])
    order = sorted(set(root.tolist()),
                   key=lambda r: -int((root == r).sum()))
    return [np.flatnonzero(root == r) for r in order]


def _triangle_frames(V, F):
    """Each triangle flattened isometrically into its own plane, and its
    area."""
    p1, p2, p3 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    a, b = p2 - p1, p3 - p1
    la = np.linalg.norm(a, axis=1)
    e1 = a / np.maximum(la, 1e-12)[:, None]
    n = np.cross(a, b)
    area = 0.5 * np.linalg.norm(n, axis=1)
    nh = n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    e2 = np.cross(nh, e1)
    zero = np.zeros(len(F))
    X = np.column_stack([zero, la, (b * e1).sum(1)])
    Y = np.column_stack([zero, zero, (b * e2).sum(1)])
    return X, Y, area


def _lsq_cg(rows, cols, vals, rhs, n, iters=4000, tol=1e-12):
    """Least squares by conjugate gradient on the normal equations, Jacobi
    preconditioned, with the matrix held as COO triples.

    numpy only, deliberately: scipy is not a dependency of the renderer, and
    a node that syncs without it still has to draw -- the `census` extra
    exists because one that did not killed every worker on the import.
    """
    def A(x):
        return np.bincount(rows, weights=vals * x[cols], minlength=len(rhs))

    def AT(y):
        return np.bincount(cols, weights=vals * y[rows], minlength=n)

    diag = np.bincount(cols, weights=vals * vals, minlength=n)
    inv = np.where(diag > 1e-14, 1.0 / np.maximum(diag, 1e-14), 1.0)
    x = np.zeros(n)
    r = AT(rhs)
    z = inv * r
    p = z.copy()
    rz = float(r @ z)
    start = rz
    for _ in range(iters):
        Ap = AT(A(p))
        denom = float(p @ Ap)
        if abs(denom) < 1e-300:
            break
        alpha = rz / denom
        x += alpha * p
        r -= alpha * Ap
        z = inv * r
        rz_new = float(r @ z)
        if rz_new <= tol * max(start, 1e-30):
            break
        p = z + (rz_new / rz) * p
        rz = rz_new
    return x


def lscm(V, F, pins):
    """Conformal uv for every vertex, with `pins` -- two vertex indices --
    laid on the u axis, which fixes the map's rotation, translation and scale
    and nothing else. Levy's least squares conformal maps."""
    X, Y, area = _triangle_frames(V, F)
    live = area > 1e-12
    F, X, Y, area = F[live], X[live], Y[live], area[live]
    w = 1.0 / np.sqrt(area)
    # W_j = (x_{j+2} - x_{j+1}) + i (y_{j+2} - y_{j+1}), the conformality
    # residual of the linear system
    Wr = np.column_stack([X[:, 2] - X[:, 1], X[:, 0] - X[:, 2],
                          X[:, 1] - X[:, 0]]) * w[:, None]
    Wi = np.column_stack([Y[:, 2] - Y[:, 1], Y[:, 0] - Y[:, 2],
                          Y[:, 1] - Y[:, 0]]) * w[:, None]

    m, nt = len(V), len(F)
    free = np.setdiff1d(np.arange(m), pins)
    col = -np.ones(m, int)
    col[free] = np.arange(len(free))
    nf = len(free)
    pin_uv = np.zeros((m, 2))
    pin_uv[pins[1]] = (1.0, 0.0)

    t = np.arange(nt)
    rows, cols, vals = [], [], []
    rhs = np.zeros(2 * nt)
    for j in range(3):
        v = F[:, j]
        held = col[v] < 0
        for off, (cr, ci) in ((0, (Wr[:, j], -Wi[:, j])),
                              (nt, (Wi[:, j], Wr[:, j]))):
            for block, coef in ((0, cr), (nf, ci)):
                rows.append(off + t[~held])
                cols.append(block + col[v[~held]])
                vals.append(coef[~held])
                if held.any():
                    np.add.at(rhs, off + t[held],
                              -coef[held] * pin_uv[v[held], 0 if block == 0 else 1])
    sol = _lsq_cg(np.concatenate(rows), np.concatenate(cols),
                  np.concatenate(vals), rhs, 2 * nf)
    uv = np.zeros((m, 2))
    uv[free, 0] = sol[:nf]
    uv[free, 1] = sol[nf:]
    uv[list(pins)] = pin_uv[list(pins)]
    return uv, F


def flatten_quality(V, F, uv):
    """(flipped share, area-scale spread). A conformal map keeps angles and
    pays in area, so the spread is what it cost; a flipped triangle is not a
    cost but a fold, and ink on both sides of one unions into a shape the
    part does not carry."""
    _x, _y, area3 = _triangle_frames(V, F)
    a = uv[F[:, 1]] - uv[F[:, 0]]
    b = uv[F[:, 2]] - uv[F[:, 0]]
    signed = 0.5 * (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
    if not len(signed):
        return 1.0, float("inf")
    flipped = float(min((signed > 0).mean(), (signed < 0).mean()))
    live = (area3 > 1e-12) & (np.abs(signed) > 1e-18)
    if live.sum() < 4:
        return flipped, float("inf")
    s = np.sqrt(np.abs(signed[live]) / area3[live])
    lo, hi = np.percentile(s, 5), np.percentile(s, 95)
    return flipped, float(hi / max(lo, 1e-12))


def mesh_groups(tris, tri_colors, tol: float = WELD_TOL):
    """[(carrier, theta0, regions, face)] from the print's own mesh.

    The shape `decal_groups` returns, so everything downstream is unchanged:
    `theta0` is 0 because a flattening has no seam to place, and `face` is
    None because a mesh carrier has no outline of its own to draw the print
    against.
    """
    V, F, codes = weld_decoration(tris, tri_colors, tol)
    if not len(F):
        return []
    codes = np.asarray(codes)
    out = []
    for faces in mesh_pieces(V, F):
        used = np.unique(F[faces])
        remap = -np.ones(len(V), int)
        remap[used] = np.arange(len(used))
        Vc, Fc = V[used], remap[F[faces]]
        if len(Fc) < 2:
            continue
        d = np.linalg.norm(Vc - Vc.mean(0), axis=1)
        p0 = int(d.argmax())
        p1 = int(np.linalg.norm(Vc - Vc[p0], axis=1).argmax())
        if p0 == p1:
            continue
        uv, Fk = lscm(Vc, Fc, (p0, p1))
        flipped, spread = flatten_quality(Vc, Fk, uv)
        if flipped > MESH_FLIP_MAX or spread > MESH_STRETCH_MAX:
            continue
        keep = codes[faces][:len(Fk)] if len(Fk) != len(faces) else codes[faces]
        regions = merge_regions([(c, uv[f]) for f, c in zip(Fk, keep)])
        if regions:
            out.append((Mesh(Vc, Fk, uv), 0.0, regions, None))
    out.sort(key=lambda g: -sum(r.area for _c, r in g[2]))
    return out


def decal_panels(tris, tri_colors, analytic):
    """[(extent, regions, face)] for every decal a part is worth drawing.

    Carrier first, mesh second, and only where the first found nothing: a
    declared surface puts the ink back where it really lies and closes the
    sagitta, which a flattening of the author's tessellation cannot. The
    fallback is for the moulds that declare no surface at all -- where the
    tessellation is all there is, so nothing is given up by using it.
    """
    groups = significant_groups(decal_groups(tris, tri_colors, analytic))
    if not groups:
        groups = significant_groups(mesh_groups(tris, tri_colors), cap=None,
                                    shatter=False)
    out = []
    for carrier, _theta0, regions, face in groups:
        # a merged region can come back with no ring at all — a sliver that
        # collapses to a line, which is not something to draw or to size a
        # canvas from
        rings = [r for _c, g in regions for r in _rings_of(g) if len(r)]
        if not rings:
            continue
        uv = np.vstack([np.asarray(r) for r in rings])
        # Both, so the canvas holds the print AND the carrier's own outline:
        # passing the face alone let ink outside it fall off the viewport.
        held = uv if face is None else np.vstack(
            [uv, np.asarray(face.exterior.coords, float)])
        ext = carrier_extent(carrier, held)
        out.append((ext, regions, face))
    return out


def decal_svgs(tris, tri_colors, analytic, px=900, ldraw_dir="vendor/ldraw",
               bg=None):
    """[svg] one per carrier the part carries a decal on."""
    return [texture_svg(ext, regions, px=px, ldraw_dir=ldraw_dir,
                        face=face, bg=bg)
            for ext, regions, face in decal_panels(tris, tri_colors, analytic)]


#: Space between panels on a sheet, as a share of the largest cell's longer
#: edge. Enough to read two prints as two, and no more: the panels carry no
#: frame, so the gap is the only thing separating them.
SHEET_GUTTER = 0.04


def sheet_grid(n):
    """(cols, rows) for `n` panels. Square-ish rather than a row: four panels
    side by side make a canvas four times as wide as it is tall, which is
    thumbnailed down to nothing on the wall."""
    if n <= 1:
        return 1, 1
    if n == 2:
        return 2, 1
    cols = math.ceil(math.sqrt(n))
    return cols, math.ceil(n / cols)


def decal_sheet(tris, tri_colors, analytic, px=900, ldraw_dir="vendor/ldraw",
                bg=None):
    """Every decal a part carries, on one canvas, or None if it carries none.

    One drawing per part, because that is what the render store keys: a part
    printed front and back is one row, not two. All panels share ONE LDU
    scale, so a torso's back still reads larger than the small print on its
    front — the same property `texture_svg` gives a single panel, held across
    a sheet. A part above `MAX_DECALS` arrives here empty and stays that way;
    what it has is one decoration shattered over facet planes, and tiling the
    shards produces a mosaic rather than a picture of anything.
    """
    panels = [(ext, regions, face, *_extent_size(ext))
              for ext, regions, face in decal_panels(tris, tri_colors, analytic)]
    if not panels:
        return None
    if len(panels) == 1:
        ext, regions, face, _w, _h = panels[0]
        return texture_svg(ext, regions, px=px, ldraw_dir=ldraw_dir,
                           face=face, bg=bg)

    cols, rows = sheet_grid(len(panels))
    cell_w = max(p[3] for p in panels)
    cell_h = max(p[4] for p in panels)
    gutter = SHEET_GUTTER * max(cell_w, cell_h)
    sheet_w = cols * cell_w + (cols + 1) * gutter
    sheet_h = rows * cell_h + (rows + 1) * gutter
    # px is the sheet's longer edge, as it is a single panel's -- so a part
    # with four prints draws each of them smaller, rather than returning a
    # canvas four times the size the flag asked for.
    s = px / max(sheet_w, sheet_h, 1e-9)
    w, h = sheet_w * s, sheet_h * s

    body = []
    if bg and bg != "none":
        body.append(f'<rect width="{w:.0f}" height="{h:.0f}" fill="{bg}"/>')
    for i, (ext, regions, face, pw, ph) in enumerate(panels):
        col, row = i % cols, i // cols
        dx = (gutter + col * (cell_w + gutter) + (cell_w - pw) / 2) * s
        dy = (gutter + row * (cell_h + gutter) + (cell_h - ph) / 2) * s
        paths = _panel_paths(ext, regions, s, ldraw_dir, face)
        body.append(f'<g transform="translate({dx:.2f} {dy:.2f})">'
                    + "".join(paths) + "</g>")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
            f'height="{h:.0f}">' + "".join(body) + "</svg>")


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
