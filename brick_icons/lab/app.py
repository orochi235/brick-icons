"""The lab's HTTP surface.

Routes only: every answer comes from a module that is testable without a
server, and nothing here decides anything about rendering.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from ..config import load_config
from . import cache, corpus, goldens_status, partindex, schema


def create_app(root: Path | str = ".",
               cache_root: Path | str = cache.DEFAULT_ROOT) -> FastAPI:
    root = Path(root)
    app = FastAPI(title="brick-icons lab")
    app.state.root = root
    app.state.cache_root = Path(cache_root)
    app.state.ldraw_dir = load_config(root=str(root)).ldraw_dir
    app.state.index = None

    def index() -> dict:
        if app.state.index is None:
            app.state.index = partindex.build(app.state.ldraw_dir)
        return app.state.index

    @app.get("/api/schema")
    def get_schema():
        return {"fields": schema.config_schema()}

    @app.get("/api/lists")
    def get_lists():
        return {"lists": corpus.lists(root=root)}

    @app.get("/api/parts")
    def get_parts(q: str = Query(""), limit: int = Query(25, le=200)):
        return {"results": partindex.search(index(), q, limit=limit)}

    @app.get("/api/goldens")
    def get_goldens(part: str):
        return goldens_status.status(root / goldens_status.DEFAULT_PATH, part)

    ldraw = app.state.ldraw_dir
    if Path(ldraw).is_dir():
        app.mount("/ldraw", StaticFiles(directory=str(ldraw)), name="ldraw")

    return app
