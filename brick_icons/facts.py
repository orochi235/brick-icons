"""What a part connects with, and how big it is, for collego's classifier.

Sibling of `features.py`, which says how a part is *drawn*; this says how it
*connects*. Each part gets the record collego's `PartFacts` type reads:

    {"features": {"stud": {"up": 1, "down": 0, "side": 1}, ...},
     "w": 1, "l": 1, "h": 3}

`features` counts connection primitives by kind and by where the primitive's
outward axis points after every enclosing transform: within `FACING_DEG` of
LDraw's up (-Y) is `up`, of +Y is `down`, anything else `side`. A kind with
no instances is left out. `w <= l` are studs (20 LDU), `h` is plates (8 LDU),
read off the geometry's bounding box with studs left out, to the half unit.

Every LDraw connection primitive is authored with its outward direction along
local -Y: a stud rises to y=-4, a tube is placed with a negative Y scale so
its -Y faces down, a peg hole end's +Y points into the hole. That one rule is
the facing of every kind.

Which primitives are which kind, and what they miss:

| kind | primitives | counted per | misses |
|---|---|---|---|
| stud | `hlr.is_stud`: `p/stud*` not titled a tube or underside | position | studs modeled as raw triangles |
| antistud | `p/stud*` and `p/N-Mstud*` titled "Stud Tube" or "Underside" | position | receptacles with no tube: a 1 x 1 has none, a 2 x 4 has 3, not 8 |
| pinhole | `peghole*` | axis line | holes drawn without a peghole end |
| axlehole | `axl*hole`, `axlehol4/5`, the `axlNhol8` hole perimeters (not `axlehol8`, which an axle draws too) | axis line | the axis sign is arbitrary, so a vertical one may read up or down |
| bar | any cylinder of radius 4 LDU, 6 LDU or longer, outside a connection or pin primitive | axis line | can't tell an inside surface (a minifig hand's grip) from a bar |
| clip | `clip1`..`clip16` | position | facing is the side the clip's own geometry lies on |

A hole or bar is one line however many primitives draw it, so a through hole
with a peghole at each end is one hole; it reads `up` if any end faces up.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import features, hlr

KINDS = ("stud", "antistud", "pinhole", "axlehole", "bar", "clip")

FACING_DEG = 10.0
_COS = float(np.cos(np.radians(FACING_DEG)))

STUD_LDU = 20.0
PLATE_LDU = 8.0

BAR_RADIUS = 4.0
BAR_MIN_LENGTH = 6.0

_PINHOLE = re.compile(r"^peghole\d*$")
_AXLEHOLE = re.compile(r"^(axl\d?hole|axlehol[45]|axl\dhol8)$")
_CLIP = re.compile(r"^clip\d+$")
#: Pin primitives carry radius-4 bores and slots that are not bars. Pins are
#: not a collego kind, so they are walked for size and nothing else.
_PIN = re.compile(r"^(connect|confric|conscala)")
_TUBE_NAME = re.compile(r"^(\d+-\d+)?stud")

_UP = np.array([0.0, -1.0, 0.0])
_X, _Y, _Z = np.eye(3)

#: Above this many points a file's vertices are cut to their convex hull,
#: which keeps the bounding box exact under any later transform.
_HULL_OVER = 48


def _title(path: Path) -> str:
    try:
        with path.open(errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return ""
    return first[1:].strip().lower() if first.startswith("0") else ""


def _is_primitive(path: Path) -> bool:
    return "p" in (path.parent.name.lower(), path.parent.parent.name.lower())


def kind_of(path: Path) -> str | None:
    """The connection kind a resolved subfile *is*, or None to walk into it."""
    if not _is_primitive(path):
        return None
    stem = path.stem.lower()
    if hlr.is_stud(path):
        return "stud"
    if _TUBE_NAME.match(stem):
        title = _title(path)
        if title.startswith("stud tube") or "underside" in title:
            return "antistud"
        return None
    if _PINHOLE.match(stem):
        return "pinhole"
    if _AXLEHOLE.match(stem):
        return "axlehole"
    if _CLIP.match(stem):
        return "clip"
    return None


def _reduce(points: np.ndarray) -> np.ndarray:
    if len(points) <= _HULL_OVER:
        return points
    points = np.unique(np.round(points, 3), axis=0)
    if len(points) <= _HULL_OVER:
        return points
    try:
        from scipy.spatial import ConvexHull
        return points[ConvexHull(points).vertices]
    except Exception:
        # Coplanar or collinear: qhull refuses, and the box corners of the
        # points are a superset that a rotation could inflate. Rare enough
        # (a flat sticker under a turned reference) to accept.
        lo, hi = points.min(axis=0), points.max(axis=0)
        return np.array([[x, y, z] for x in (lo[0], hi[0])
                         for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])


class _Node:
    """One file's contribution, in its own frame.

    `pts` has one row per connection instance: origin, outward direction,
    and kind index. `bars` has one row per candidate cylinder: origin, the
    axis column (its length), and the two in-plane columns (its radius).
    `verts` excludes everything under a stud.
    """
    __slots__ = ("pts", "kinds", "bars", "verts")

    def __init__(self, pts, kinds, bars, verts):
        self.pts, self.kinds, self.bars, self.verts = pts, kinds, bars, verts


_EMPTY = _Node(np.zeros((0, 6)), np.zeros(0, dtype=int), np.zeros((0, 12)),
               np.zeros((0, 3)))


class Walker:
    """One pass over a library. Build once and reuse: subfiles under `p/`
    and `parts/s/` are memoized, which is where the sharing is."""

    def __init__(self, roots: list[Path]):
        self.roots = roots
        self._memo: dict[Path, _Node] = {}
        self._kind: dict[Path, str | None] = {}
        self._where: dict[str, Path | None] = {}

    def _resolve(self, name: str) -> Path | None:
        name = name.replace("\\", "/").strip().lower()
        if name in self._where:
            return self._where[name]
        base = name.split("/")[-1]
        found = None
        for root in self.roots:
            for cand in (root / name, root / base):
                if cand.exists():
                    found = cand
                    break
            if found:
                break
        self._where[name] = found
        return found

    def _kind_of(self, path: Path) -> str | None:
        if path not in self._kind:
            self._kind[path] = kind_of(path)
        return self._kind[path]

    def node(self, path: Path, depth: int = 0) -> _Node:
        got = self._memo.get(path)
        if got is not None:
            return got
        if depth >= features.MAX_DEPTH:
            return _EMPTY
        try:
            text = path.read_text(errors="replace")
        except OSError:
            return _EMPTY
        verts: list[np.ndarray] = []
        pts: list[np.ndarray] = []
        kinds: list[np.ndarray] = []
        bars: list[np.ndarray] = []
        own: list[list[float]] = []
        for raw in text.splitlines():
            tok = raw.split()
            if not tok:
                continue
            if tok[0] in ("3", "4"):
                n = 3 if tok[0] == "3" else 4
                try:
                    own.extend(np.array(tok[2:2 + 3 * n], dtype=float)
                               .reshape(n, 3).tolist())
                except ValueError:
                    pass
                continue
            if tok[0] != "1" or len(tok) < 15:
                continue
            try:
                vals = np.array(tok[2:14], dtype=float)
            except ValueError:
                continue
            t, M = vals[:3], vals[3:].reshape(3, 3)
            name = " ".join(tok[14:])
            child = self._resolve(name)
            if features.family(name) == "cylinder":
                bars.append(np.concatenate([t, M @ _Y, M @ _X, M @ _Z]))
            if child is None or child == path:
                continue
            kind = self._kind_of(child)
            sub = self.node(child, depth + 1)
            if kind is not None:
                if kind == "clip" and len(sub.verts):
                    # A clip's opening is not on a common axis; the side its
                    # own geometry lies on is the best general guess.
                    c = sub.verts.mean(axis=0)
                    out = M @ (c if np.linalg.norm(c) > 1e-6 else -_Y)
                else:
                    out = M @ -_Y
                pts.append(np.concatenate([t, out])[None])
                kinds.append(np.array([KINDS.index(kind)]))
                if kind != "stud" and len(sub.verts):
                    verts.append(sub.verts @ M.T + t)
                continue
            if len(sub.verts):
                verts.append(sub.verts @ M.T + t)
            if len(sub.pts):
                pts.append(np.concatenate(
                    [sub.pts[:, :3] @ M.T + t, sub.pts[:, 3:] @ M.T], axis=1))
                kinds.append(sub.kinds)
            if len(sub.bars) and not (_is_primitive(child)
                                      and _PIN.match(child.stem.lower())):
                b = sub.bars
                bars.append(np.concatenate(
                    [b[:, :3] @ M.T + t, b[:, 3:6] @ M.T,
                     b[:, 6:9] @ M.T, b[:, 9:] @ M.T], axis=1))
        if own:
            verts.append(np.array(own))
        node = _Node(
            np.vstack(pts) if pts else _EMPTY.pts,
            np.concatenate(kinds) if kinds else _EMPTY.kinds,
            np.vstack([b.reshape(-1, 12) for b in bars]) if bars else _EMPTY.bars,
            _reduce(np.vstack(verts)) if verts else _EMPTY.verts)
        if _shared(path):
            self._memo[path] = node
        return node

    def facts(self, path: Path) -> dict:
        """The `PartFacts` record for one part file."""
        node = self.node(Path(path))
        verts = node.verts
        if not len(verts):
            # Nothing but studs, or nothing at all: size from what there is.
            verts = node.pts[:, :3] if len(node.pts) else np.zeros((1, 3))
        lo, hi = verts.min(axis=0), verts.max(axis=0)
        ext = hi - lo
        a, b = _half(ext[0] / STUD_LDU), _half(ext[2] / STUD_LDU)
        out: dict = {"features": {}}
        for k, kind in enumerate(KINDS):
            if kind == "bar":
                counts = _bars(node.bars, (lo[1] + hi[1]) / 2)
            else:
                sel = node.kinds == k
                p, d = node.pts[sel, :3], node.pts[sel, 3:]
                counts = (_by_line(p, d) if kind in ("pinhole", "axlehole")
                          else _by_position(p, d))
            if any(counts.values()):
                out["features"][kind] = counts
        out["w"], out["l"] = min(a, b), max(a, b)
        out["h"] = _half(ext[1] / PLATE_LDU)
        return out


def _shared(path: Path) -> bool:
    parent = path.parent.name.lower()
    return _is_primitive(path) or parent == "s"


def _half(x: float) -> float:
    v = round(float(x) * 2) / 2
    return int(v) if v == int(v) else v


def facing(d: np.ndarray) -> str:
    n = float(np.linalg.norm(d))
    if n < 1e-9:
        return "side"
    c = float(np.dot(d / n, _UP))
    return "up" if c >= _COS else "down" if c <= -_COS else "side"


def _blank() -> dict[str, int]:
    return {"up": 0, "down": 0, "side": 0}


def _by_position(p: np.ndarray, d: np.ndarray, tol: float = 1.0) -> dict:
    """One per distinct (position, facing): two primitives drawing one stud
    -- a stud and its extension ring -- count once."""
    counts = _blank()
    kept: dict[str, list[np.ndarray]] = {"up": [], "down": [], "side": []}
    for pos, dir_ in zip(p, d):
        f = facing(dir_)
        if any(np.linalg.norm(pos - q) < tol for q in kept[f]):
            continue
        kept[f].append(pos)
        counts[f] += 1
    return counts


def _unit_axis(d: np.ndarray) -> np.ndarray:
    a = d / np.linalg.norm(d)
    i = int(np.argmax(np.abs(a)))
    return -a if a[i] < 0 else a


def _lines(p: np.ndarray, d: np.ndarray, tol: float = 0.5):
    """Group instances lying on one axis line. Yields member indices."""
    groups: list[tuple[np.ndarray, np.ndarray, list[int]]] = []
    for i, (pos, dir_) in enumerate(zip(p, d)):
        if np.linalg.norm(dir_) < 1e-9:
            continue
        a = _unit_axis(dir_)
        off = pos - np.dot(pos, a) * a
        for ga, goff, members in groups:
            if (np.linalg.norm(np.cross(a, ga)) < 0.02
                    and np.linalg.norm(off - goff) < tol):
                members.append(i)
                break
        else:
            groups.append((a, off, [i]))
    return groups


def _by_line(p: np.ndarray, d: np.ndarray) -> dict:
    counts = _blank()
    for a, _, members in _lines(p, d):
        faces = {facing(d[i]) for i in members}
        if facing(a) == "side":
            counts["side"] += 1
        else:
            counts["up" if "up" in faces else "down"] += 1
    return counts


def _bars(bars: np.ndarray, mid_y: float) -> dict:
    """Radius-4 cylinders, merged into runs along each axis line; a run of
    `BAR_MIN_LENGTH` or more is one bar. The length floor is what drops the
    4 LDU bore of a hand-modeled hollow stud, which is radius 4 as well."""
    counts = _blank()
    if not len(bars):
        return counts
    o, ax, u, v = bars[:, :3], bars[:, 3:6], bars[:, 6:9], bars[:, 9:]
    ru, rv = np.linalg.norm(u, axis=1), np.linalg.norm(v, axis=1)
    keep = ((np.abs(ru - BAR_RADIUS) < 0.1) & (np.abs(rv - BAR_RADIUS) < 0.1)
            & (np.linalg.norm(ax, axis=1) > 1e-6))
    o, ax = o[keep], ax[keep]
    for a, off, members in _lines(o, ax):
        spans = sorted(sorted((float(np.dot(o[i], a)),
                               float(np.dot(o[i] + ax[i], a))))
                       for i in members)
        runs: list[list[float]] = []
        for s, e in spans:
            if runs and s <= runs[-1][1] + 1.0:
                runs[-1][1] = max(runs[-1][1], e)
            else:
                runs.append([s, e])
        for s, e in runs:
            if e - s < BAR_MIN_LENGTH:
                continue
            if facing(a) == "side":
                counts["side"] += 1
            else:
                y = off[1] + a[1] * (s + e) / 2
                counts["up" if y <= mid_y + 0.5 else "down"] += 1
    return counts


def build(ldraw_dir: Path | str, ids: list[str] | None = None,
          progress=lambda msg: None):
    """Yield `(part_id, facts)` for every part in the library, in id order."""
    import time
    ldraw_dir = Path(ldraw_dir)
    walker = Walker(features.default_roots(ldraw_dir))
    paths = sorted((ldraw_dir / "parts").glob("*.dat"))
    if ids is not None:
        want = set(ids)
        paths = [p for p in paths if p.stem in want]
    total = len(paths)
    for n, path in enumerate(paths, 1):
        t0 = time.perf_counter()
        try:
            got = walker.facts(path)
        except Exception as exc:  # one bad file must not end the run
            progress(f"{n}/{total} {path.stem} error {type(exc).__name__}: {exc}")
            continue
        ms = (time.perf_counter() - t0) * 1000
        progress(f"{n}/{total} {path.stem} {ms:7.1f}ms "
                 f"{_brief(got)}")
        yield path.stem, got


def _brief(f: dict) -> str:
    parts = [f"{f['w']}x{f['l']}x{f['h']}"]
    for kind, c in f["features"].items():
        parts.append(f"{kind}:{c['up']}/{c['down']}/{c['side']}")
    return " ".join(parts)
