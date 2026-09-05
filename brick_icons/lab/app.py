"""The lab's HTTP surface.

Routes only: every answer comes from a module that is testable without a
server, and nothing here decides anything about rendering.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from .. import colors as ldraw_colors
from ..config import load_config
from . import (cache, corpus, decal, defects, diff, goldens_status, jobs,
               partindex, reference, runner, schema)


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
               defects_path: Path | str | None = None) -> FastAPI:
    root = Path(root)
    app = FastAPI(title="brick-icons lab")
    app.state.root = root
    app.state.cache_root = Path(cache_root)
    app.state.ldraw_dir = load_config(root=str(root)).ldraw_dir
    app.state.index = None
    app.state.jobs = jobs.Registry()
    app.state.defects_path = Path(defects_path) if defects_path else (
        root / defects.DEFAULT_PATH)
    app.state.reference_root = Path(cache_root) / "reference"
    app.state.decal_root = Path(cache_root) / "decal"

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

        return {"job": app.state.jobs.start("goldens", cases, work),
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

        return {"job": app.state.jobs.start("batch", argvs, work),
                "count": len(argvs)}

    ldraw = app.state.ldraw_dir
    if Path(ldraw).is_dir():
        app.mount("/ldraw", StaticFiles(directory=str(ldraw)), name="ldraw")

    return app
