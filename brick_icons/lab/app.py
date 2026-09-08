"""The lab's HTTP surface.

Routes only: every answer comes from a module that is testable without a
server, and nothing here decides anything about rendering.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from .. import colors as ldraw_colors
from .. import features
from .. import tags
from ..config import load_config
from . import (cache, cells, corpus, decal, defects, diff, findings,
               goldens_status, jobs, partindex, reference, runner, schema, sizes,
               stats)
from .. import db as corpus_db_module

# One entry per `db.RENDER_SUFFIXES`: a slot's renders are whatever the engine
# that filled it wrote, and the wall's render URL ends `.svg` for every one of
# them.
RENDER_MEDIA_TYPES = {".svg": "image/svg+xml", ".png": "image/png",
                      ".webp": "image/webp"}

# How long a footprint answer stands before the next request walks again. The
# numbers move when a census lands, not between two clicks of Reload.
SIZES_TTL = 300.0


def _artifact_path(root: Path, key: str, name: str) -> Path:
    """A cached file under `root`, or a 400.

    Every artifact route serves a caller-supplied key and name off a cache
    root, so the traversal guard belongs here rather than at each of them.
    """
    if not key.isalnum() or "/" in name or ".." in name:
        raise HTTPException(400, "bad artifact path")
    return root / key / name


class RenderRequest(BaseModel):
    part: str
    config: dict = {}
    force: bool = False


class GoldenCheckRequest(BaseModel):
    part: str


class BatchRequest(BaseModel):
    parts: list[str]
    config: dict = {}
    force: bool = False


def create_app(root: Path | str = ".",
               cache_root: Path | str = cache.DEFAULT_ROOT,
               defects_path: Path | str | None = None,
               corpus_db: Path | str | None = None,
               thumbs_root: Path | str | None = None) -> FastAPI:
    root = Path(root)
    app = FastAPI(title="brick-icons lab")
    # 24,591 cells is ~6.5MB of JSON and highly repetitive; gzip takes it under
    # a megabyte for the cost of one line.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.state.root = root
    app.state.cache_root = Path(cache_root)
    app.state.ldraw_dir = load_config(root=str(root)).ldraw_dir
    app.state.index = None
    app.state.sizes = None
    app.state.jobs = jobs.Registry()
    app.state.defects_path = Path(defects_path) if defects_path else (
        root / defects.DEFAULT_PATH)
    app.state.reference_root = Path(cache_root) / "reference"
    app.state.decal_root = Path(cache_root) / "decal"
    app.state.corpus_db = Path(corpus_db) if corpus_db else (
        root / corpus_db_module.DEFAULT_PATH)
    app.state.thumbs_root = Path(thumbs_root) if thumbs_root else (
        root / "out" / "thumbs")

    def index() -> dict:
        if app.state.index is None:
            app.state.index = partindex.build(app.state.ldraw_dir)
        return app.state.index

    @app.get("/api/schema")
    def get_schema():
        return {"fields": schema.config_schema(root=root)}

    @app.get("/api/colors")
    def get_colors():
        pal = ldraw_colors.load_palette(app.state.ldraw_dir)
        return {"colors": [
            {"code": c.code, "name": c.name.replace("_", " "),
             "hex": "#%02x%02x%02x" % tuple(c.rgb), "alpha": c.alpha,
             "category": c.category, "legoId": c.lego_id}
            for c in (pal.by_code[k] for k in sorted(pal.by_code))]}

    @app.get("/api/lists")
    def get_lists():
        return {"lists": corpus.lists(root=root)}

    @app.get("/api/parts")
    def get_parts(q: str = Query(""), limit: int = Query(25, le=200)):
        return {"results": partindex.search(index(), q, limit=limit)}

    @app.get("/api/goldens")
    def get_goldens(part: str):
        return goldens_status.status(root / goldens_status.DEFAULT_PATH, part)

    @app.get("/api/combos")
    def get_combos():
        return {"combos": corpus.combos(root=root)}

    @app.post("/api/goldens/check")
    def post_goldens_check(req: GoldenCheckRequest):
        frozen = goldens_status.frozen(root / goldens_status.DEFAULT_PATH)
        digests = frozen.get(req.part, {})
        cases = goldens_status.cases_for(root, req.part)

        def work(case, emit, cancel):
            result = runner.render(case["argv"], root=app.state.cache_root,
                                   cancel=cancel)
            svg = app.state.cache_root / result["key"] / f"{req.part}.svg"
            compared = goldens_status.compare_case(svg, digests.get(case["combo"]))
            emit(f"{case['case']}: {compared['state']}")
            return {"case": case["case"], "combo": case["combo"], **compared}

        return {"job": app.state.jobs.start("goldens", cases, work,
                                            workers=runner.worker_count()),
                "count": len(cases)}

    @app.post("/api/render")
    def post_render(req: RenderRequest):
        try:
            argv = schema.to_argv(req.part, req.config)
        except KeyError as e:
            raise HTTPException(400, str(e)) from None

        def work(item, emit, cancel):
            result = runner.render(item, root=app.state.cache_root,
                                   force=req.force, cancel=cancel)
            emit(f"{req.part}: {'cached' if result['cached'] else 'rendered'}")
            if not result["ok"]:
                raise RuntimeError(result["error"])
            return result

        return {"job": app.state.jobs.start("render", [argv], work),
                "argv": argv, "command": " ".join(["brick-icons", *argv])}

    @app.get("/api/command")
    def get_command(part: str, config: str = "{}"):
        try:
            parsed = json.loads(config)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"bad config JSON: {e}") from None
        try:
            argv = schema.to_argv(part, parsed)
        except KeyError as e:
            raise HTTPException(400, str(e)) from None
        return {"argv": argv, "command": " ".join(["brick-icons", *argv])}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        record = app.state.jobs.get(job_id)
        if record is None:
            raise HTTPException(404, "no such job")
        return record

    @app.post("/api/jobs/{job_id}/cancel")
    def post_cancel(job_id: str):
        return {"cancelled": app.state.jobs.cancel(job_id)}

    @app.get("/api/artifact/{key}/{name}")
    def get_artifact(key: str, name: str):
        path = _artifact_path(app.state.cache_root, key, name)
        if not path.is_file():
            raise HTTPException(404, "no such artifact")
        return FileResponse(path)

    @app.get("/api/diff")
    def get_diff(a_key: str, a_name: str, b_key: str, b_name: str,
                 min_size: int = 4):
        paths = [_artifact_path(app.state.cache_root, a_key, a_name),
                 _artifact_path(app.state.cache_root, b_key, b_name)]
        if not all(p.is_file() for p in paths):
            raise HTTPException(404, "no such artifact")
        # The engines emit SVG and the differ needs pixels, so an SVG side is
        # rasterized with resvg -- the project's antialias reference -- into
        # the same cache directory the artifact came from.
        try:
            rasters = [diff.as_raster(p, p.parent) for p in paths]
            vis = app.state.cache_root / a_key / f"diff-{b_key}.png"
            result = diff.compare(*[Image.open(r) for r in rasters],
                                  min_size=min_size, out_png=vis)
        except RuntimeError as e:
            raise HTTPException(400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {**result, "url": f"/api/artifact/{a_key}/{vis.name}"}

    @app.get("/api/reference")
    def get_reference(part: str, angle: str, render_px: int | None = None,
                      part_color: str | None = None):
        got = reference.render_reference(
            part, angle, root=root, cache_root=app.state.reference_root,
            render_px=render_px, part_color=part_color)
        if not got["ok"]:
            code = 503 if "not installed" in (got["error"] or "") else 400
            raise HTTPException(code, got["error"])
        return {**got, "url": f"/api/reference-artifact/{got['key']}/{got['name']}"}

    @app.get("/api/reference-artifact/{key}/{name}")
    def get_reference_artifact(key: str, name: str):
        path = _artifact_path(app.state.reference_root, key, name)
        if not path.is_file():
            raise HTTPException(404, "no such reference")
        return FileResponse(path)

    @app.get("/api/decal")
    def get_decal(part: str, texture_px: int = decal.DEFAULT_PX,
                  svg_bg: str = decal.DEFAULT_BG):
        got = decal.extract(part, root=root, cache_root=app.state.decal_root,
                            texture_px=texture_px, svg_bg=svg_bg)
        if not got["ok"]:
            raise HTTPException(400, got["error"])
        return {**got, "urls": [f"/api/decal-artifact/{got['key']}/{n}"
                                for n in got["names"]]}

    @app.get("/api/decal-artifact/{key}/{name}")
    def get_decal_artifact(key: str, name: str):
        path = _artifact_path(app.state.decal_root, key, name)
        if not path.is_file():
            raise HTTPException(404, "no such decal")
        return FileResponse(path)

    @app.get("/api/defects")
    def get_defects(part: str | None = None, status: str | None = None):
        rows = defects.load(app.state.defects_path)
        if part:
            rows = [d for d in rows if d["part"] == part]
        if status:
            rows = [d for d in rows if d["status"] == status]
        return {"defects": rows}

    @app.post("/api/defects")
    def post_defect(record: dict):
        try:
            return defects.add(app.state.defects_path, record)
        except ValueError as e:
            code = 409 if "already exists" in str(e) else 400
            raise HTTPException(code, str(e)) from None

    @app.patch("/api/defects/{defect_id}")
    def patch_defect(defect_id: str, changes: dict):
        try:
            return defects.update(app.state.defects_path, defect_id, changes)
        except KeyError:
            raise HTTPException(404, f"no defect {defect_id!r}") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/api/batch")
    def post_batch(req: BatchRequest):
        try:
            argvs = [schema.to_argv(p, req.config) for p in req.parts]
        except KeyError as e:
            raise HTTPException(400, str(e)) from None

        def work(item, emit, cancel):
            result = runner.render(item, root=app.state.cache_root,
                                   force=req.force, cancel=cancel)
            emit(f"{item[0]}: {'cached' if result['cached'] else 'rendered'}")
            if not result["ok"]:
                raise RuntimeError(result["error"])
            return result

        return {"job": app.state.jobs.start("batch", argvs, work,
                                            workers=runner.worker_count()),
                "count": len(argvs)}

    def corpus_conn():
        if not Path(app.state.corpus_db).is_file():
            raise HTTPException(503, "no corpus database; run "
                                     "scripts/build-corpus-db.py")
        return corpus_db_module.connect(app.state.corpus_db)

    def _check_source(source: str) -> None:
        if source not in corpus_db_module.SOURCES:
            raise HTTPException(400, f"no such slot: {source}")

    def _slot(source: str) -> Path:
        _check_source(source)
        return Path(app.state.thumbs_root) / source

    @app.get("/api/corpus/cells")
    def get_cells(source: str = "silhouette-naive", since: str | None = None):
        conn = corpus_conn()
        try:
            return cells.cells(conn, source=source, since=since)
        finally:
            conn.close()

    @app.get("/api/corpus/sources")
    def get_sources():
        """The slots that have renders, most-populated first."""
        conn = corpus_conn()
        try:
            return {"sources": [dict(r) for r in conn.execute(
                "SELECT source, count(*) AS n FROM renders "
                "GROUP BY source ORDER BY n DESC")]}
        finally:
            conn.close()

    @app.get("/api/corpus/summary")
    def get_corpus_summary():
        conn = corpus_conn()
        try:
            return findings.summary(conn)
        finally:
            conn.close()

    @app.get("/api/corpus/stats")
    def get_corpus_stats(kind: str = "all", moved: bool = False,
                         out_of_scope: bool = True,
                         excluded: list[str] = Query(default=[]),
                         badges: list[str] = Query(default=[])):
        """Every tally the dashboard draws, over one working set."""
        if kind not in stats.KINDS:
            raise HTTPException(422, f"kind must be one of {stats.KINDS}")
        conn = corpus_conn()
        try:
            return stats.stats(conn, kind=kind, moved=moved,
                               out_of_scope=out_of_scope,
                               excluded=tuple(excluded), badges=tuple(badges))
        finally:
            conn.close()

    @app.get("/api/corpus/sizes")
    def get_corpus_sizes(refresh: bool = False):
        """What the corpus costs on disk.

        Its own route rather than a field on `/api/corpus/stats`, because
        that one re-polls while a run is open and this walks `out/` -- seven
        seconds over a few hundred thousand files. Memoized for
        `SIZES_TTL`; `?refresh=1` forces the walk.
        """
        held = app.state.sizes
        if held is not None and not refresh and \
                time.monotonic() - held[0] < SIZES_TTL:
            return held[1]
        conn = corpus_conn()
        try:
            answer = sizes.footprint(conn, root, app.state.ldraw_dir)
        finally:
            conn.close()
        app.state.sizes = (time.monotonic(), answer)
        return answer

    @app.get("/api/corpus/part/{part_id}")
    def get_corpus_part(part_id: str):
        conn = corpus_conn()
        try:
            row = conn.execute("SELECT * FROM parts WHERE id = ?",
                               (part_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "no such part")
            # `findings` matches `part` with LIKE, so 3001 would drag in
            # 3001a. The detail view is about one part.
            found = [f for f in findings.findings(conn, part=part_id,
                                                  limit=50)["rows"]
                     if f["part_id"] == part_id]
            runs = [dict(r) for r in conn.execute(
                "SELECT r.id, r.kind, r.started, r.commit_sha, m.engine, "
                "m.extra_d99, m.missing_px, m.secs, m.error "
                "FROM measurements m JOIN runs r ON r.id = m.run_id "
                "WHERE m.part_id = ? ORDER BY r.started DESC LIMIT 20",
                (part_id,))]
            slots = [dict(r) for r in conn.execute(
                "SELECT source, sha256, made_at FROM renders WHERE part_id = ? "
                "ORDER BY source", (part_id,))]
            states = cells.slot_states(conn, part_id,
                                       [s["source"] for s in slots])
            years = conn.execute(
                "SELECT year_from, year_to, sets FROM part_years WHERE part_id = ?",
                (part_id,)).fetchone()
            # In the module's own order, and a flag keeps its null value: the
            # page tells a flag from a measure by that null and so never has
            # to carry a copy of the vocabulary.
            held = {r["feature"]: r["value"] for r in conn.execute(
                "SELECT feature, value FROM part_features WHERE part_id = ?",
                (part_id,))}
            built = {name: held[name]
                     for name in (*features.FLAGS, *features.MEASURES)
                     if name in held}
        finally:
            conn.close()
        part = dict(row)
        part["year_from"] = years["year_from"] if years else None
        part["year_to"] = years["year_to"] if years else None
        part["sets"] = years["sets"] if years else None
        part["tags"] = tags.tags_for(part["category"], bool(part["printed"]),
                                     bool(part["obsolete"]),
                                     part["year_to"], part["sets"])
        part["out_of_scope"] = part["category"] in cells.OUT_OF_SCOPE_CATEGORIES
        for slot in slots:
            slot.update(states[slot["source"]])
        return {"part": part, "findings": found, "runs": runs,
                "slots": slots, "features": built,
                "defects": [d for d in defects.load(app.state.defects_path)
                            if d["part"] == part_id]}

    @app.get("/api/thumbs/{source}/sheet-{level}.png")
    def get_sheet(source: str, level: int):
        path = _slot(source) / f"sheet-{level}.png"
        if not path.is_file():
            raise HTTPException(404, "no such sheet; run scripts/bake-thumbs.py")
        return FileResponse(path)

    @app.get("/api/thumbs/{source}/sheet-{level}.json")
    def get_sheet_manifest(source: str, level: int):
        path = _slot(source) / f"sheet-{level}.json"
        if not path.is_file():
            raise HTTPException(404, "no such sheet manifest")
        return FileResponse(path)

    @app.get("/api/thumbs/{source}/{level}/{name}")
    def get_thumb(source: str, level: int, name: str):
        if "/" in name or ".." in name or not name.endswith(".png"):
            raise HTTPException(400, "bad thumbnail path")
        path = _slot(source) / str(level) / name
        if not path.is_file():
            raise HTTPException(404, "no such thumbnail")
        return FileResponse(path)

    @app.get("/api/corpus/render/{source}/{part_id}.svg")
    def get_corpus_render(source: str, part_id: str):
        """A part's rendered SVG for a slot, for the wall's vector rung.

        The path a caller could smuggle in is never trusted -- only `source`
        and `part_id` reach the filesystem, and only after `renders` names a
        row for them, so there is nothing here to traverse with.
        """
        _check_source(source)
        conn = corpus_conn()
        try:
            row = conn.execute(
                "SELECT path FROM renders WHERE source = ? AND part_id = ? "
                "LIMIT 1", (source, part_id)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise HTTPException(404, "no such render")
        render_root = Path(app.state.root).resolve()
        path = (render_root / row["path"]).resolve()
        if render_root not in path.parents or not path.is_file():
            raise HTTPException(404, "no such render")
        return FileResponse(path, media_type=RENDER_MEDIA_TYPES.get(
            path.suffix, "application/octet-stream"))

    ldraw = app.state.ldraw_dir
    if Path(ldraw).is_dir():
        app.mount("/ldraw", StaticFiles(directory=str(ldraw)), name="ldraw")

    return app
