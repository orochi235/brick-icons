"""How a part is built, in the terms a defect gets filed against.

Sibling of `tags.py`. That module says what a part *is* -- theme, era, how
many sets it shipped in; this one says how it is *constructed*, so that a
defect class found on one part can be turned into the list of every other
part built the same way.

Everything here is derived from the `.dat` and the subfiles it resolves to,
which is what makes the table safe to rebuild wholesale. A hand-typed label
would go stale the first time the extractor learned something new, and
nothing would say so.

Two kinds of feature share one table. A **flag** is present or absent and
carries no value (`off-axis`, `torus`). A **measure** carries a number and is
meant to be compared (`tris`, `condlines`). The distinction is the value
column being NULL, not a separate name space.

The transform features are the ones worth having. Every circular LDraw
primitive is authored as a unit circle in its own XZ plane about local Y, so
what the enclosing matrices do to that frame decides whether the drawing sees
a circle, an ellipse, or something off every world axis -- which is the
difference between the cases the arc fitter handles and the ones it does not.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

#: How deep a reference chain is followed. `hlr.flatten` uses the same cap.
MAX_DEPTH = 30

#: Below this a matrix entry counts as zero, relative to the row's own scale.
TOL = 1e-6

_FRAC = r"(?:\d+-\d+)"

#: Primitive stem -> family, first match winning. Circular primitives all
#: carry a fraction prefix (`1-4`, `4-4`, `1-16`), which is what keeps `con`
#: from swallowing `connect`, `confric` and `connhol`.
_FAMILIES: tuple[tuple[str, re.Pattern], ...] = (
    ("ndis", re.compile(rf"^{_FRAC}ndis")),
    ("disc", re.compile(rf"^{_FRAC}disc")),
    ("cylinder", re.compile(rf"^{_FRAC}cyl")),
    ("cone", re.compile(rf"^{_FRAC}con")),
    ("ring", re.compile(rf"^{_FRAC}ri")),
    ("chord", re.compile(rf"^{_FRAC}chrd")),
    ("circle-edge", re.compile(rf"^{_FRAC}edge")),
    ("sphere", re.compile(rf"^{_FRAC}sphe")),
    ("torus", re.compile(r"^t\d\d[oiqs]")),
    ("stud", re.compile(r"^stu")),
    ("box", re.compile(r"^box")),
    ("rect", re.compile(r"^rect")),
)

#: Families authored as a circle in local XZ about local Y. `stud` is not one
#: of them: it is an assembly, and the walk reaches the cylinder and disc
#: inside it with the stud's own matrix already applied.
ROUND = frozenset({"ndis", "disc", "cylinder", "cone", "ring", "chord",
                   "circle-edge", "sphere", "torus"})

#: Flags, in the order they read best.
FLAGS = (*(name for name, _ in _FAMILIES), "round",
         "off-axis", "elliptical", "mirrored",
         "bfc-cw", "bfc-noclip", "invertnext")

#: Measures, each a count over the whole resolved subtree.
MEASURES = ("tris", "quads", "lines", "condlines", "subfiles", "depth",
            "skew-deg")


def family(name: str) -> str | None:
    """The primitive family a subfile name belongs to, or None for a part."""
    stem = name.replace("\\", "/").split("/")[-1].lower()
    stem = stem.removesuffix(".dat")
    for label, pattern in _FAMILIES:
        if pattern.match(stem):
            return label
    return None


def _matrix(tokens: list[str]) -> np.ndarray:
    """The linear part of a type-1 line. Translation is dropped: none of the
    features here can see where a primitive sits, only how it is turned and
    stretched, and dropping it collapses the 48 identical studs of a baseplate
    to one entry instead of 48."""
    a, b, c, d, e, f, g, h, i = (float(t) for t in tokens[5:14])
    return np.array([[a, b, c], [d, e, f], [g, h, i]], dtype=float)


def _axis_aligned(axis: np.ndarray) -> bool:
    n = float(np.linalg.norm(axis))
    if n < TOL:
        return True
    unit = np.abs(axis) / n
    return bool(np.count_nonzero(unit > TOL) == 1)


def skew_degrees(u: np.ndarray, v: np.ndarray, axis: np.ndarray) -> float:
    """How far the axis column leans out of the circle's own plane.

    Every vertex of a ring, disc or edge sits at local y=0, so that column is
    not read by the geometry and an author is free to leave it anywhere. The
    frame builder is not: `3820-c-grip-fills-solid` was two rings whose axis
    column sat 14 degrees out of their own plane, and occt.frame rejected
    both, dropping the part to tessellation.
    """
    normal = np.cross(u, v)
    n, a = float(np.linalg.norm(normal)), float(np.linalg.norm(axis))
    if n < TOL or a < TOL:
        return 0.0
    cos = abs(float(np.dot(normal / n, axis / a)))
    return float(np.degrees(np.arccos(min(1.0, cos))))


def _circular(u: np.ndarray, v: np.ndarray) -> bool:
    """Whether the circle's two in-plane axes still image a circle: equal
    length and still square to each other. Either failing draws an ellipse."""
    lu, lv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
    scale = max(lu, lv)
    if scale < TOL:
        return True
    if abs(lu - lv) > TOL * scale:
        return False
    return abs(float(np.dot(u, v))) <= TOL * scale * scale


class Extractor:
    """One pass over a library. Holds the per-file memo, so build it once and
    reuse it: `stud.dat` is referenced by 14,396 parts and is parsed once."""

    def __init__(self, roots: list[Path]):
        self.roots = roots
        self._file: dict[Path, dict] = {}
        self._rolled: dict[Path, dict] = {}

    # -- one file, nothing followed ------------------------------------

    def _resolve(self, name: str) -> Path | None:
        name = name.replace("\\", "/").strip()
        base = name.split("/")[-1]
        for root in self.roots:
            for cand in (root / name, root / base):
                if cand.exists():
                    return cand
        return None

    def _parse(self, path: Path) -> dict:
        got = self._file.get(path)
        if got is not None:
            return got
        refs: list[tuple[str, np.ndarray]] = []
        counts = {"tris": 0, "quads": 0, "lines": 0, "condlines": 0}
        flags: set[str] = set()
        try:
            text = path.read_text(errors="replace")
        except OSError:
            text = ""
        for raw in text.splitlines():
            tok = raw.split()
            if not tok:
                continue
            if tok[0] == "0":
                if len(tok) >= 3 and tok[1] == "BFC":
                    # NOCERTIFY is not among these: the vendored library has
                    # none, so a flag for it could only ever read false.
                    rest = tok[2:]
                    if "CW" in rest:
                        flags.add("bfc-cw")
                    if "NOCLIP" in rest:
                        flags.add("bfc-noclip")
                    if "INVERTNEXT" in rest:
                        flags.add("invertnext")
                continue
            if tok[0] == "1" and len(tok) >= 15:
                try:
                    refs.append((" ".join(tok[14:]), _matrix(tok)))
                except ValueError:
                    continue
            elif tok[0] == "2":
                counts["lines"] += 1
            elif tok[0] == "3":
                counts["tris"] += 1
            elif tok[0] == "4":
                counts["quads"] += 1
            elif tok[0] == "5":
                counts["condlines"] += 1
        got = {"refs": refs, "counts": counts, "flags": flags}
        self._file[path] = got
        return got

    # -- the subtree, in the file's own frame ---------------------------

    def _roll(self, path: Path, depth: int = 0) -> dict:
        """Everything the subtree contributes, expressed in `path`'s frame.

        `round` is a set of (family, matrix) with the matrix rounded and
        translation already gone, so identical instances collapse. Without
        that a baseplate carries one entry per stud and every ancestor
        re-multiplies all of them.
        """
        got = self._rolled.get(path)
        if got is not None:
            return got
        if depth >= MAX_DEPTH:
            return {"round": set(), "flags": set(), "files": {path},
                    "counts": {k: 0 for k in ("tris", "quads", "lines",
                                              "condlines")}, "depth": 0}
        here = self._parse(path)
        rounds: set[tuple[str, tuple]] = set()
        flags = set(here["flags"])
        counts = dict(here["counts"])
        files = {path}
        deepest = 0
        for name, M in here["refs"]:
            fam = family(name)
            child = self._resolve(name)
            if fam in ROUND:
                rounds.add((fam, tuple(np.round(M, 6).ravel())))
            if child is None or child == path:
                continue
            sub = self._roll(child, depth + 1)
            flags |= sub["flags"]
            files |= sub["files"]
            deepest = max(deepest, sub["depth"] + 1)
            for key in counts:
                counts[key] += sub["counts"][key]
            for fam2, m in sub["round"]:
                comp = M @ np.array(m, dtype=float).reshape(3, 3)
                rounds.add((fam2, tuple(np.round(comp, 6).ravel())))
        got = {"round": rounds, "flags": flags, "counts": counts,
               "files": files, "depth": deepest}
        self._rolled[path] = got
        return got

    # -- the answer for one part ---------------------------------------

    def extract(self, path: Path) -> dict[str, float | None]:
        """Every feature of one part: flags mapped to None, measures to their
        number. A part with no geometry at all still gets its measures, at 0."""
        rolled = self._roll(Path(path))
        out: dict[str, float | None] = {}
        seen_family: set[str] = set()
        skew = 0.0
        for fam, m in rolled["round"]:
            seen_family.add(fam)
            M = np.array(m, dtype=float).reshape(3, 3)
            if not _axis_aligned(M @ np.array([0.0, 1.0, 0.0])):
                out["off-axis"] = None
            if not _circular(M @ np.array([1.0, 0.0, 0.0]),
                             M @ np.array([0.0, 0.0, 1.0])):
                out["elliptical"] = None
            skew = max(skew, skew_degrees(M @ np.array([1.0, 0.0, 0.0]),
                                          M @ np.array([0.0, 0.0, 1.0]),
                                          M @ np.array([0.0, 1.0, 0.0])))
            if float(np.linalg.det(M)) < -TOL:
                out["mirrored"] = None
        # Families with no round frame of their own -- box, rect, stud -- are
        # read off the reference names instead, which is all they need.
        for f in rolled["files"]:
            fam = family(f.name)
            if fam is not None:
                seen_family.add(fam)
        for fam in seen_family:
            out[fam] = None
        for flag in rolled["flags"]:
            out[flag] = None
        if seen_family & ROUND:
            out["round"] = None
        out["skew-deg"] = round(skew, 3)
        out |= {k: float(v) for k, v in rolled["counts"].items()}
        out["subfiles"] = float(len(rolled["files"]) - 1)
        out["depth"] = float(rolled["depth"])
        return out


def default_roots(ldraw_dir: Path | str) -> list[Path]:
    """Where a subfile name is looked up, in LDraw's own order. `p/48` first
    means a part asking for `4-4cyli` gets the hi-res one where it exists,
    which is what the renderer resolves too."""
    ldraw_dir = Path(ldraw_dir)
    return [ldraw_dir / "p" / "48", ldraw_dir / "p",
            ldraw_dir / "parts", ldraw_dir / "parts" / "s",
            ldraw_dir / "models"]


def build(ldraw_dir: Path | str, ids: list[str] | None = None,
          progress=lambda msg: None):
    """Yield `(part_id, {feature: value})` for every part in the library.

    Streams rather than returning a dict: the whole library is 24,591 parts
    and a caller writing rows wants to write them as they come.
    """
    ldraw_dir = Path(ldraw_dir)
    ex = Extractor(default_roots(ldraw_dir))
    paths = sorted((ldraw_dir / "parts").glob("*.dat"))
    if ids is not None:
        want = set(ids)
        paths = [p for p in paths if p.stem in want]
    total = len(paths)
    for n, path in enumerate(paths, 1):
        feats = ex.extract(path)
        progress(f"{n}/{total} {path.stem}: "
                 f"{sum(1 for v in feats.values() if v is None)} flags")
        yield path.stem, feats
