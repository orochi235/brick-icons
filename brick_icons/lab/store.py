"""Draw one part into the tracked render store.

Shared by `scripts/build-render-store.py` and the lab's Redraw, so a drawing
the lab makes is the one a store run would have made.
"""
from __future__ import annotations

from pathlib import Path

from .. import db
from . import cache
from . import runner as lab_runner


def drawing_in(names: list[str], source: str) -> str | None:
    """The file a render made that the store keeps: its SVG where it drew one,
    the raster otherwise -- ldview has no vector form, and picking by
    extension alone would take a thumbnail.

    None for a decal that drew nothing. That is not a failure: most of the
    library carries no print, and a part whose decoration shattered past
    unwrap.MAX_DECALS is declining to draw rather than erroring. Any other
    slot drawing nothing raises.
    """
    drawn = ([n for n in names if n.endswith(".svg")]
             or [n for n in names if n.endswith(".png")])
    if drawn:
        return drawn[0]
    if source == "decal":
        return None
    raise RuntimeError(f"render produced no drawing: {names}")


def render_into_store(part: str, source: str, run_id: int | None, conn,
                      force: bool, store_root: Path | str = ".",
                      lab_root: Path | str = cache.DEFAULT_ROOT) -> dict:
    store_root, lab_root = Path(store_root), Path(lab_root)
    have = list((store_root / "renders" / source).glob(f"{part}.*"))
    if have and not force:
        return {"part": part, "source": source, "state": "present"}
    argv = db.canonical_argv(part, source)
    result = lab_runner.render(argv, root=lab_root, force=force)
    if not result["ok"]:
        raise RuntimeError(result["error"])
    name = drawing_in([a["name"] for a in result["artifacts"]], source)
    if name is None:
        # Logged, so a later pass can tell a part that was tried and had
        # nothing from one nobody has reached.
        return {"part": part, "source": source, "state": "none"}
    made = cache.dir_for(argv, root=lab_root) / name
    db.store_render(conn, part, source, made, root=store_root, run_id=run_id)
    return {"part": part, "source": source,
            "state": "cached" if result["cached"] else "stored"}
