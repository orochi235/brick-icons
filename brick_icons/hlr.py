from __future__ import annotations
import math
from pathlib import Path
import numpy as np

_text_cache: dict[Path, list[str]] = {}


def default_roots(ldraw_dir: Path) -> list[Path]:
    ldraw_dir = Path(ldraw_dir)
    return [ldraw_dir / "p" / "48", ldraw_dir / "p",
            ldraw_dir / "parts", ldraw_dir / "parts" / "s", ldraw_dir / "models"]


def resolve(name: str, roots: list[Path]) -> Path | None:
    name = name.replace("\\", "/").strip()
    base = name.split("/")[-1]
    for root in roots:
        for cand in (root / name, root / base):
            if cand.exists():
                return cand
    return None


def _lines(path: Path) -> list[str]:
    if path not in _text_cache:
        _text_cache[path] = Path(path).read_text(errors="replace").splitlines()
    return _text_cache[path]


def flatten(path: Path, R: np.ndarray, t: np.ndarray, out: dict,
            roots: list[Path], depth: int = 0) -> None:
    if depth > 30:
        return
    for ln in _lines(path):
        tok = ln.split()
        if not tok:
            continue
        typ = tok[0]
        if typ == "1" and len(tok) >= 15:
            x, y, z = map(float, tok[2:5])
            a, b, c, d, e, f, g, h, i = map(float, tok[5:14])
            M = np.array([[a, b, c], [d, e, f], [g, h, i]], float)
            T = np.array([x, y, z], float)
            sub = resolve(" ".join(tok[14:]), roots)
            if sub is not None:
                flatten(sub, R @ M, R @ T + t, out, roots, depth + 1)
        elif typ in ("2", "5") and len(tok) >= 8:
            pts = np.array(list(map(float, tok[2:])), float).reshape(-1, 3)
            out[typ].append(pts @ R.T + t)
        elif typ in ("3", "4"):
            n = 3 if typ == "3" else 4
            if len(tok) >= 2 + 3 * n:
                pts = np.array(list(map(float, tok[2:2 + 3 * n])), float).reshape(n, 3) @ R.T + t
                if n == 3:
                    out["tri"].append(pts)
                else:
                    out["tri"].append(pts[[0, 1, 2]])
                    out["tri"].append(pts[[0, 2, 3]])
