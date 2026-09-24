"""The review queue's routes: what displaced what, the pictures, the verdict.

Everything joined here changes on its own -- defects are closed, requests are
answered, a slot is redrawn again -- so the `review` row carries only what
was true at displacement, and each answer re-reads the rest.
"""
from __future__ import annotations

import json
import sqlite3
from xml.etree import ElementTree
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import db as corpus_db
from .. import goldens
from .. import requests as render_requests
from .. import review
from . import cells, defects

MEDIA_TYPES = {".svg": "image/svg+xml", ".png": "image/png",
               ".webp": "image/webp"}
VIEWS = ("linked", "all")
#: LDView's drawing of the part, in its authored LDraw colors. It is a corpus
#: slot baked for every part, not a live LDView call: the card has to show
#: the same reference the wall and every reference script use, and a
#: subprocess per card would draw a different one.
REFERENCE_SOURCE = "reference"


class Verdict(BaseModel):
    verdict: str
    note: str = ""


def _content(root: Path | str, *rels: str | None) -> dict:
    """Byte size and what the drawing is made OF, for the first of `rels`
    that resolves to a file inside root.

    Two renders that look alike can differ enormously in their makeup -- the
    same silhouette as a dozen arcs or as nine hundred facet edges -- and the
    diff panel cannot show it. Counts come from `goldens.summarize_svg`, the
    one place that parses a rendered SVG, and are None for a raster slot.
    """
    base = Path(root).resolve()
    path = None
    for rel in rels:
        if not rel:
            continue
        cand = (base / rel).resolve()
        if base in cand.parents and cand.is_file():
            path = cand
            break
    if path is None:
        return {"bytes": None, "shapes": None, "lines": None, "gradients": None}
    out = {"bytes": path.stat().st_size, "shapes": None, "lines": None,
           "gradients": None}
    if path.suffix == ".svg":
        try:
            s = goldens.summarize_svg(path.read_text())
        except (UnicodeDecodeError, ElementTree.ParseError):
            # a kept `.svg` can hold a raster: `keep_before` names the copy
            # after the row's slot, not after what the bytes are
            return out
        out.update(shapes=s["paths"], lines=s["lines"],
                   gradients=s["gradients"])
    return out


def _measurement(conn: sqlite3.Connection, run_id: int | None, part: str,
                 source: str) -> dict:
    if run_id is None:
        return {}
    row = conn.execute(
        "SELECT build, secs, extra_d99, missing_px, error FROM measurements "
        "WHERE run_id = ? AND part_id = ? AND engine = ? "
        "ORDER BY (source = ?) DESC LIMIT 1",
        (run_id, part, cells.engine_for(source), source)).fetchone()
    return dict(row) if row else {}


def _edge(conn: sqlite3.Connection, part: str, source: str, sha: str) -> dict | None:
    row = conn.execute(
        "SELECT declared_len, missing_len, missing_comps FROM edge_scores "
        "WHERE part_id = ? AND source = ? AND sha256 = ?",
        (part, source, sha)).fetchone()
    return dict(row) if row else None


def linked_defects(records: list[dict], part: str, source: str) -> list[dict]:
    """The open defects a verdict on this slot speaks to."""
    engine = cells.engine_for(source)
    return [r for r in records
            if r["part"] == part and r.get("status", "open") == "open"
            and engine in r.get("engines", ())]


def linked_request(asked: list[dict], part: str, source: str,
                   before_at: str) -> dict | None:
    """The latest redraw request for this slot that the after render
    answered: made before it landed, and before is what it was made against."""
    hits = [r for r in asked if r["part"] == part and r["source"] == source
            and r["at"] <= before_at]
    return max(hits, key=lambda r: r["at"]) if hits else None


def entry(conn: sqlite3.Connection, row: sqlite3.Row, records: list[dict],
          asked: list[dict], root: Path | str = ".") -> dict:
    part, source = row["part_id"], row["source"]
    title = conn.execute("SELECT title FROM parts WHERE id = ?",
                         (part,)).fetchone()
    held = conn.execute(
        "SELECT sha256, made_at FROM renders WHERE part_id = ? AND source = ?",
        (part, source)).fetchone()
    # The slot's own stamp while it still shows this drawing; the line's time
    # is when the displacement was recorded, which a backfill makes today.
    after_made = (held["made_at"] if held and held["sha256"] == row["after_sha"]
                  else row["at"])
    superseded = None
    if held is not None and held["sha256"] != row["after_sha"]:
        later = conn.execute(
            "SELECT id FROM review WHERE part_id = ? AND source = ? "
            "AND before_sha = ? ORDER BY at DESC LIMIT 1",
            (part, source, row["after_sha"])).fetchone()
        superseded = later["id"] if later else review.entry_id(
            source, part, held["sha256"])
    diffed = ({"components": row["diff_components"],
               "pixels": row["diff_pixels"], "width": row["diff_width"],
               "at": row["diff_at"]}
              if row["diff_components"] is not None else None)
    judged = ({"verdict": row["verdict"], "note": row["note"],
               "at": row["judged_at"], "by": row["judged_by"],
               "defects": json.loads(row["judged_defects"] or "[]")}
              if row["verdict"] else None)
    # The open defects a verdict would speak to, plus the ones a verdict
    # already did: `fixed` closes a defect, and a judged entry that lost its
    # link the moment it was judged could never be shown again.
    touched = set(judged["defects"]) if judged else set()
    linked = linked_defects(records, part, source)
    linked += [r for r in records if r["id"] in touched
               and r["id"] not in {d["id"] for d in linked}]
    base = f"/api/review/{row['id']}"
    return {
        "id": row["id"], "part": part, "title": title["title"] if title else None,
        "source": source, "engine": cells.engine_for(source),
        "at": row["at"], "run_id": row["run_id"], "by": row["made_by"],
        "before": {"path": row["before_path"], "sha256": row["before_sha"],
                   "made_at": row["before_made_at"],
                   "run_id": row["before_run_id"], "kept": row["before_kept"],
                   **_measurement(conn, row["before_run_id"], part, source),
                   "content": _content(root, row["before_kept"],
                                       row["before_path"]),
                   "edge": _edge(conn, part, source, row["before_sha"])},
        "after": {"path": row["after_path"], "sha256": row["after_sha"],
                  "made_at": after_made, "run_id": row["run_id"],
                  **_measurement(conn, row["run_id"], part, source),
                  "content": _content(root, row["after_path"]),
                  "edge": _edge(conn, part, source, row["after_sha"])},
        "diff": diffed,
        "defects": [{"id": r["id"], "title": r["title"], "status": r["status"],
                     "checked": (r.get("checked") or {}).get(source)}
                    for r in linked],
        "request": linked_request(asked, part, source, row["at"]),
        "judged": judged,
        "superseded_by": superseded,
        "urls": {"before": f"{base}/before", "after": f"{base}/after",
                 "diff": f"{base}/diff.png",
                 "reference": f"{base}/reference"},
    }


def in_view(item: dict, view: str, judged: bool) -> bool:
    """Whether the view is about this entry at all, before its diff is
    weighed."""
    if item["judged"] is not None and not judged:
        return False
    if view == "linked":
        return bool(item["defects"]) or item["request"] is not None
    return True


def over_bar(item: dict, min_components: int) -> bool:
    """An unmeasured entry is over the bar: a gate cannot judge a diff nobody
    has taken, and a screen that dropped them would hide the entries the
    measure button exists to reach."""
    d = item["diff"]
    return d is None or d["components"] >= min_components


def install(app: FastAPI, corpus_conn) -> None:
    def root() -> Path:
        return Path(app.state.root)

    def log() -> Path:
        return Path(app.state.review_path)

    def row_for(eid: str, conn: sqlite3.Connection) -> sqlite3.Row:
        review.ensure_schema(conn)
        row = conn.execute("SELECT * FROM review WHERE id = ?",
                           (eid,)).fetchone()
        if row is None:
            raise HTTPException(404, f"no review entry {eid!r}")
        return row

    def cache_dir() -> Path:
        return Path(app.state.cache_root) / "review"

    def sides(row: sqlite3.Row) -> tuple[Path, Path]:
        found = review.side_files(root(), row)
        if found is None:
            raise HTTPException(404, "a side of this entry is no longer on disk")
        return found

    def measure(conn: sqlite3.Connection, row: sqlite3.Row) -> Path:
        try:
            return review.measure(conn, root(), log(), cache_dir(), row)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from None
        except RuntimeError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/api/review")
    def list_entries(view: str = "linked", min_components: int = 1,
                     judged: bool = False, limit: int = Query(200, le=2000)):
        if view not in VIEWS:
            raise HTTPException(400, f"view must be one of {VIEWS}")
        conn = corpus_conn()
        try:
            review.ensure_schema(conn)
            records = defects.load(app.state.defects_path)
            asked = render_requests.load(app.state.requests_path)
            out, total, hidden = [], 0, 0
            for row in conn.execute("SELECT * FROM review ORDER BY at DESC"):
                item = entry(conn, row, records, asked, root())
                if not in_view(item, view, judged):
                    continue
                if not over_bar(item, min_components):
                    hidden += 1
                    continue
                total += 1
                if len(out) < limit:
                    out.append(item)
        finally:
            conn.close()
        return {"entries": out, "total": total, "hidden": hidden,
                "view": view, "verdicts": list(review.VERDICTS)}

    @app.get("/api/review/{eid:path}/before")
    def get_before(eid: str):
        conn = corpus_conn()
        try:
            before, _after = sides(row_for(eid, conn))
        finally:
            conn.close()
        return FileResponse(before, media_type=MEDIA_TYPES.get(
            before.suffix, "application/octet-stream"))

    @app.get("/api/review/{eid:path}/after")
    def get_after(eid: str):
        conn = corpus_conn()
        try:
            _before, after = sides(row_for(eid, conn))
        finally:
            conn.close()
        return FileResponse(after, media_type=MEDIA_TYPES.get(
            after.suffix, "application/octet-stream"))

    @app.get("/api/review/{eid:path}/diff.png")
    def get_diff(eid: str):
        conn = corpus_conn()
        try:
            panel = measure(conn, row_for(eid, conn))
        finally:
            conn.close()
        return FileResponse(panel, media_type="image/png")

    @app.post("/api/review/measure")
    def measure_unmeasured(limit: int = Query(20, le=500),
                           view: str | None = None):
        """Measure unmeasured entries, newest first, or only the ones `view`
        is about -- the queue cannot screen out an unchanged redraw until its
        diff has been taken, and taking every slot's would measure thousands
        to reach the hundred a defect is linked to."""
        if view is not None and view not in VIEWS:
            raise HTTPException(400, f"view must be one of {VIEWS}")
        conn = corpus_conn()
        try:
            only = None
            if view is not None:
                review.ensure_schema(conn)
                records = defects.load(app.state.defects_path)
                asked = render_requests.load(app.state.requests_path)
                only = [row["id"] for row
                        in conn.execute("SELECT * FROM review "
                                        "ORDER BY at DESC").fetchall()
                        if in_view(entry(conn, row, records, asked, root()), view,
                                   judged=False)]
            measured, failed = review.measure_unmeasured(
                conn, root(), log(), cache_dir(), limit, only=only)
        finally:
            conn.close()
        return {"measured": measured, "failed": failed}

    @app.post("/api/review/{eid:path}/verdict")
    def post_verdict(eid: str, body: Verdict):
        if body.verdict not in review.VERDICTS:
            raise HTTPException(400, f"verdict must be one of {review.VERDICTS}")
        conn = corpus_conn()
        try:
            row = row_for(eid, conn)
            records = defects.load(app.state.defects_path)
            touched, restore = [], {}
            stamp = f"{date.today().isoformat()} review {body.verdict}"
            line = f"{stamp}: {body.note.strip()}" if body.note.strip() else stamp
            # A defect this same entry already closed is no longer "linked" --
            # `linked_defects` returns open ones -- so without this a second
            # verdict on the entry that closed it speaks to nothing, and a
            # regression could never take the closure back.
            was = review.last_judged(log(), eid)
            spoke_to = set(was["defects"]) if was else set()
            speaking = linked_defects(records, row["part_id"], row["source"])
            speaking += [r for r in records if r["id"] in spoke_to
                         and r["id"] not in {d["id"] for d in speaking}]
            for record in speaking:
                # What the verdict is about to overwrite, so an undo puts it
                # back verbatim instead of reconstructing a previous sha it
                # has no other record of.
                restore[record["id"]] = {
                    "status": record.get("status", "open"),
                    "checked": dict(record.get("checked") or {}),
                    "notes": record.get("notes") or ""}
                changes = {"checked": {**(record.get("checked") or {}),
                                       row["source"]: row["after_sha"]},
                           "notes": "\n\n".join(
                               p for p in ((record.get("notes") or "").rstrip(),
                                           line) if p)}
                if body.verdict == "fixed":
                    changes["status"] = "fixed"
                elif body.verdict == "regression" and \
                        record.get("status") == "fixed":
                    # a fix recorded once and undone by a later redraw left
                    # the defect closed with the regression noted underneath,
                    # so nothing listed it as live and only a reader of the
                    # notes would know
                    changes["status"] = "open"
                updated = defects.update(app.state.defects_path, record["id"],
                                         changes)
                corpus_db.upsert_defect(conn, updated)
                touched.append(record["id"])
            review.record_judged(conn, log(), eid, body.verdict, body.note,
                                 by="lab", defects=touched, restore=restore)
            item = entry(conn, row_for(eid, conn),
                         defects.load(app.state.defects_path),
                         render_requests.load(app.state.requests_path),
                         root())
        finally:
            conn.close()
        return item

    @app.post("/api/review/{eid:path}/undo")
    def post_undo(eid: str):
        conn = corpus_conn()
        try:
            row = row_for(eid, conn)
            if not row["verdict"]:
                raise HTTPException(400, f"review entry {eid!r} is not judged")
            was = review.last_judged(log(), eid) or {}
            held = was.get("restore") or {}
            by_id = {r["id"]: r for r in
                     defects.load(app.state.defects_path)}
            for defect_id in json.loads(row["judged_defects"] or "[]"):
                if defect_id not in by_id:
                    continue
                if defect_id in held:
                    changes = {k: held[defect_id][k]
                               for k in ("status", "checked", "notes")}
                else:
                    # A verdict cast before `restore` existed. The previous
                    # sha is gone, so the slot goes back to never-judged
                    # rather than to a sha that would be a guess.
                    checked = dict(by_id[defect_id].get("checked") or {})
                    checked.pop(row["source"], None)
                    changes = {"status": "open", "checked": checked}
                updated = defects.update(app.state.defects_path, defect_id,
                                         changes)
                corpus_db.upsert_defect(conn, updated)
            review.record_unjudged(conn, log(), eid, by="lab")
            item = entry(conn, row_for(eid, conn),
                         defects.load(app.state.defects_path),
                         render_requests.load(app.state.requests_path),
                         root())
            item["restored"] = bool(held) or not row["judged_defects"] or \
                json.loads(row["judged_defects"]) == []
        finally:
            conn.close()
        return item

    @app.get("/api/review/{eid:path}/reference")
    def get_reference_panel(eid: str):
        conn = corpus_conn()
        try:
            row = row_for(eid, conn)
            held = conn.execute(
                "SELECT path FROM renders WHERE source = ? AND part_id = ? "
                "LIMIT 1", (REFERENCE_SOURCE, row["part_id"])).fetchone()
        finally:
            conn.close()
        if held is None:
            raise HTTPException(404, f"no {REFERENCE_SOURCE} render for "
                                     f"{row['part_id']}")
        base = Path(app.state.root).resolve()
        path = (base / held["path"]).resolve()
        if base not in path.parents or not path.is_file():
            raise HTTPException(404, "the reference render is not on disk")
        return FileResponse(path, media_type=MEDIA_TYPES.get(
            path.suffix, "application/octet-stream"))

    # Last: `{eid:path}` is greedy and would take `.../after` and
    # `.../diff.png` if it were registered before them.
    @app.get("/api/review/{eid:path}")
    def get_entry(eid: str):
        conn = corpus_conn()
        try:
            item = entry(conn, row_for(eid, conn),
                         defects.load(app.state.defects_path),
                         render_requests.load(app.state.requests_path),
                         root())
        finally:
            conn.close()
        return item
