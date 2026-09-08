import json
import re
import sqlite3

import pytest

from brick_icons import db, goldens


def test_connect_creates_the_schema(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "parts", "runs", "renders",
            "measurements", "defects", "notes"} <= names


def test_connect_is_idempotent(tmp_path):
    path = tmp_path / "corpus.db"
    db.connect(path).close()
    conn = db.connect(path)
    assert conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == \
        str(db.SCHEMA_VERSION)


def test_a_newer_database_is_refused(tmp_path):
    path = tmp_path / "corpus.db"
    conn = db.connect(path)
    conn.execute("UPDATE meta SET value='99' WHERE key='schema_version'")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="schema version 99"):
        db.connect(path)


def _library(tmp_path):
    parts = tmp_path / "ldraw" / "parts"
    parts.mkdir(parents=True)
    (parts / "3001.dat").write_text("0 Brick  2 x  4\n")
    (parts / "3004p01.dat").write_text("0 Brick  1 x  2 with Cat Pattern\n")
    (parts / "3005.dat").write_text("0 ~Moved to 3005a\n")
    (parts / "u9236.dat").write_text("0 _Shortcut Something\n")
    return tmp_path / "ldraw"


def test_seeding_reads_the_description_not_the_id(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    assert db.seed_parts(conn, _library(tmp_path)) == 4
    rows = {r["id"]: r for r in conn.execute("SELECT * FROM parts")}
    assert rows["3001"]["title"] == "Brick  2 x  4"
    assert rows["3001"]["category"] == "Brick"
    assert rows["3001"]["printed"] == 0
    assert rows["3004p01"]["printed"] == 1
    assert rows["3005"]["obsolete"] == 1
    assert rows["u9236"]["obsolete"] == 1
    assert rows["3001"]["status"] == "unreviewed"


def test_reseeding_keeps_a_status_a_human_set(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    library = _library(tmp_path)
    db.seed_parts(conn, library)
    conn.execute("UPDATE parts SET status='broken' WHERE id='3001'")
    conn.commit()
    db.seed_parts(conn, library)
    assert conn.execute(
        "SELECT status FROM parts WHERE id='3001'").fetchone()[0] == "broken"


def test_a_run_records_its_arguments_and_closes(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    run_id = db.start_run(conn, "census", {"engine": "naive", "timeout": 120},
                          commit_sha="abc1234")
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    assert row["kind"] == "census"
    assert json.loads(row["args"])["engine"] == "naive"
    assert row["started"] and row["finished"] is None

    db.finish_run(conn, run_id, note="8235 parts")
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    assert row["finished"] and row["note"] == "8235 parts"


MEASURED = {
    "part": "93064", "engine": "naive", "angle": "iso",
    "extra_px": 17197, "missing_px": 2595,
    "extra_dist_px": {"50": 0.4, "90": 1.9, "99": 2.57, "100": 3.09},
    "missing": [{"px": 459, "x": [96.5, 102.2], "y": [153.2, 155.5]}],
    "extra": [], "secs": 49.0,
}
FAILED = {
    "part": "92738", "engine": "occt", "angle": "iso",
    "error": "ProcessDied", "detail": "killed mid-render; not retried",
    "secs": 0.0,
}


def test_importing_a_census_jsonl(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    run_id = db.start_run(conn, "census", {}, commit_sha="abc1234")
    path = tmp_path / "naive-s0.jsonl"
    path.write_text(json.dumps(MEASURED) + "\n" + json.dumps(FAILED) + "\n")

    assert db.import_census_jsonl(conn, run_id, path) == 2
    rows = {r["part_id"]: r for r in conn.execute("SELECT * FROM measurements")}
    assert rows["93064"]["missing_px"] == 2595
    assert rows["93064"]["missing_comps"] == 1
    assert rows["93064"]["extra_d99"] == 2.57
    assert rows["93064"]["error"] is None
    assert rows["92738"]["error"] == "ProcessDied"
    assert rows["92738"]["missing_px"] is None


def test_reimporting_the_same_run_replaces_rather_than_duplicates(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    run_id = db.start_run(conn, "census", {}, commit_sha="abc1234")
    path = tmp_path / "naive-s0.jsonl"
    path.write_text(json.dumps(MEASURED) + "\n")
    db.import_census_jsonl(conn, run_id, path)
    db.import_census_jsonl(conn, run_id, path)
    assert conn.execute("SELECT count(*) FROM measurements").fetchone()[0] == 1


SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180">'
       '<path d="M 10 10 L 20 20" stroke="black"/></svg>')


def test_recording_a_render_stores_its_path_hash_and_size(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    svg = tmp_path / "renders" / "naive" / "3001.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text(SVG)

    key = db.record_render(conn, "3001", "naive", svg, root=tmp_path)
    row = conn.execute("SELECT * FROM renders").fetchone()
    assert row["path"] == "renders/naive/3001.svg"
    assert row["config_key"] == key
    assert row["sha256"] == goldens.sha256(SVG)
    assert (row["width"], row["height"]) == (240.0, 180.0)


def test_a_second_render_of_the_same_config_replaces_the_row(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    svg = tmp_path / "renders" / "naive" / "3001.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text(SVG)
    db.record_render(conn, "3001", "naive", svg, root=tmp_path)
    svg.write_text(SVG.replace("240", "300"))
    db.record_render(conn, "3001", "naive", svg, root=tmp_path)
    rows = conn.execute("SELECT * FROM renders").fetchall()
    assert len(rows) == 1 and rows[0]["width"] == 300.0


def test_an_unknown_source_is_refused(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    svg = tmp_path / "x.svg"
    svg.write_text(SVG)
    with pytest.raises(ValueError, match="source"):
        db.record_render(conn, "3001", "wireframe", svg, root=tmp_path)


DEFECT = {
    "id": "3941-occt-borehole",
    "part": "3941",
    "engines": ["occt"],
    "status": "open",
    "title": "borehole rim not drawn",
    "classes": ["arc-loss"],
    "mark": {"x": 0.42, "y": 0.55, "w": 0.11, "h": 0.09},
    "filed": "2026-08-31",
    "notes": "occt draws nothing at all",
}


def test_defects_round_trip_through_the_database(tmp_path):
    from brick_icons.lab import defects as defects_toml

    conn = db.connect(tmp_path / "corpus.db")
    path = tmp_path / "defects.toml"
    defects_toml.save(path, [DEFECT])

    assert db.import_defects(conn, path) == 1
    row = conn.execute("SELECT * FROM defects").fetchone()
    assert row["part_id"] == "3941"
    assert json.loads(row["engines"]) == ["occt"]
    assert json.loads(row["mark"])["x"] == 0.42

    out = tmp_path / "again.toml"
    db.export_defects(conn, out)
    assert defects_toml.load(out) == [DEFECT]


def test_a_defect_can_carry_two_symptom_classes(tmp_path):
    """53119 shows stray lines and banding at once; one column would have to
    drop one of them."""
    from brick_icons.lab import defects as defects_toml

    conn = db.connect(tmp_path / "corpus.db")
    path = tmp_path / "defects.toml"
    defects_toml.save(path, [{**DEFECT, "classes": ["stray-ink", "banding"]}])
    db.import_defects(conn, path)
    row = conn.execute("SELECT classes FROM defects").fetchone()
    assert json.loads(row["classes"]) == ["stray-ink", "banding"]


def test_an_unclassed_defect_stores_null_not_an_empty_list(tmp_path):
    """`classes IS NOT NULL` is how the crossing query finds the classed rows;
    an empty list would pass that test and contribute nothing."""
    from brick_icons.lab import defects as defects_toml

    conn = db.connect(tmp_path / "corpus.db")
    path = tmp_path / "defects.toml"
    bare = {k: v for k, v in DEFECT.items() if k != "classes"}
    defects_toml.save(path, [bare])
    db.import_defects(conn, path)
    assert conn.execute("SELECT classes FROM defects").fetchone()[0] is None


def test_a_database_made_before_classes_existed_gains_the_column(tmp_path):
    """Several sessions share one corpus.db, so an additive column has to
    arrive without a rebuild."""
    import sqlite3

    path = tmp_path / "corpus.db"
    conn = db.connect(path)
    conn.execute("ALTER TABLE defects DROP COLUMN classes")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(path)
    assert "classes" not in {r[1] for r in
                             conn.execute("PRAGMA table_info(defects)")}
    conn.close()

    conn = db.connect(path)
    assert "classes" in {r["name"] for r in
                         conn.execute("PRAGMA table_info(defects)")}


def test_part_features_are_derived_and_replaced_whole(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    ldraw = _library(tmp_path)
    (ldraw / "p").mkdir()
    (ldraw / "p" / "4-4cyli.dat").write_text("0 Cylinder\n")
    (ldraw / "parts" / "3001.dat").write_text(
        "0 Brick  2 x  4\n1 16 0 0 0  3 0 0  0 1 0  0 0 1 4-4cyli.dat\n")

    assert db.seed_part_features(conn, ldraw) > 0
    got = {r["feature"] for r in conn.execute(
        "SELECT feature FROM part_features WHERE part_id='3001'")}
    assert {"cylinder", "round", "elliptical"} <= got

    # A part that stops carrying a feature must stop reporting it.
    (ldraw / "parts" / "3001.dat").write_text("0 Brick  2 x  4\n")
    db.seed_part_features(conn, ldraw)
    got = {r["feature"] for r in conn.execute(
        "SELECT feature FROM part_features WHERE part_id='3001'")}
    assert "cylinder" not in got and "tris" in got


def test_setting_a_status_and_adding_notes(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    db.seed_parts(conn, _library(tmp_path))

    db.set_status(conn, "3001", "suspect", note="stud row looks thin")
    row = conn.execute("SELECT * FROM parts WHERE id='3001'").fetchone()
    assert row["status"] == "suspect"
    assert row["status_note"] == "stud row looks thin"
    assert row["status_at"]

    db.add_note(conn, "measured 2595px missing", part_id="3001")
    assert [n["body"] for n in db.notes_for(conn, part_id="3001")] == [
        "measured 2595px missing"]


def test_an_unknown_status_is_refused(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    db.seed_parts(conn, _library(tmp_path))
    with pytest.raises(ValueError, match="status"):
        db.set_status(conn, "3001", "haunted")


def test_statuses_and_notes_round_trip_through_toml(tmp_path):
    library = _library(tmp_path)
    conn = db.connect(tmp_path / "corpus.db")
    db.seed_parts(conn, library)
    db.set_status(conn, "3001", "broken", note="no stud row at all")
    db.add_note(conn, "second look agrees", part_id="3001")
    path = tmp_path / "part-status.toml"
    db.export_statuses(conn, path)

    fresh = db.connect(tmp_path / "fresh.db")
    db.seed_parts(fresh, library)
    assert db.import_statuses(fresh, path) == 1
    row = fresh.execute("SELECT * FROM parts WHERE id='3001'").fetchone()
    assert (row["status"], row["status_note"]) == ("broken", "no stud row at all")
    assert [n["body"] for n in db.notes_for(fresh, part_id="3001")] == [
        "second look agrees"]


def test_a_part_left_unreviewed_is_not_written_out(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    db.seed_parts(conn, _library(tmp_path))
    path = tmp_path / "part-status.toml"
    assert db.export_statuses(conn, path) == 0
    assert "[[part]]" not in path.read_text()


def test_rebuild_walks_renders_and_toml_and_jsonl(tmp_path):
    library = _library(tmp_path)
    svg = tmp_path / "renders" / "naive" / "3001.svg"
    svg.parent.mkdir(parents=True)
    svg.write_text(SVG)
    (tmp_path / "census").mkdir()
    (tmp_path / "census" / "naive-s0.jsonl").write_text(json.dumps(MEASURED) + "\n")

    defects = tmp_path / "defects.toml"
    defects.write_text("")

    counts = db.rebuild(tmp_path / "corpus.db", ldraw_dir=library,
                        root=tmp_path, census_dirs=[tmp_path / "census"],
                        defects_path=defects, years_path=tmp_path / "none.csv",
                        successors_path=tmp_path / "none.csv",
                        # without this the rebuild reads the repo's own status
                        # file, so the count is whatever the lab last filed
                        status_path=tmp_path / "none.toml",
                        commit_sha="abc1234")
    # Popped rather than pinned: the number is one row per feature per part,
    # so pinning it would make every new feature a failing rebuild test.
    assert counts.pop("features") > 0
    assert counts == {"parts": 4, "renders": 1, "measurements": 1,
                      "skipped": 0, "replaced": 0, "defects": 0,
                      "statuses": 0, "years": 0, "successors": 0}

    conn = db.connect(tmp_path / "corpus.db")
    assert conn.execute("SELECT path FROM renders").fetchone()[0] == \
        "renders/naive/3001.svg"


def test_rebuild_starts_from_empty_each_time(tmp_path):
    library = _library(tmp_path)
    (tmp_path / "census").mkdir()
    (tmp_path / "census" / "naive-s0.jsonl").write_text(json.dumps(MEASURED) + "\n")
    for _ in range(2):
        db.rebuild(tmp_path / "corpus.db", ldraw_dir=library, root=tmp_path,
                   census_dirs=[tmp_path / "census"], commit_sha="abc1234")
    conn = db.connect(tmp_path / "corpus.db")
    assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM measurements").fetchone()[0] == 1


def test_storing_a_render_puts_it_under_source_and_part(tmp_path):
    conn = db.connect(tmp_path / "corpus.db")
    conn.execute("INSERT INTO parts (id, title, printed, obsolete) "
                 "VALUES ('3001', 'Brick 2 x 4', 0, 0)")
    made = tmp_path / "work" / "3001.svg"
    made.parent.mkdir()
    made.write_text(SVG)

    path = db.store_render(conn, "3001", "naive", made, root=tmp_path)
    assert path == tmp_path / "renders" / "naive" / "3001.svg"
    assert path.read_text() == SVG
    row = conn.execute("SELECT path, sha256 FROM renders").fetchone()
    assert row["path"] == "renders/naive/3001.svg"
    assert row["sha256"] == goldens.sha256(SVG)


def test_a_second_source_does_not_overwrite_the_first(tmp_path):
    """Two sources of the same part are two rows AND two files. A source whose
    renders share a path would let the second silently replace the first."""
    conn = db.connect(tmp_path / "corpus.db")
    conn.execute("INSERT INTO parts (id, title, printed, obsolete) "
                 "VALUES ('3001', 'Brick 2 x 4', 0, 0)")
    made = tmp_path / "work" / "3001.svg"
    made.parent.mkdir()
    made.write_text(SVG)

    kept = [db.store_render(conn, "3001", s, made, root=tmp_path)
            for s in ("naive", "occt")]
    assert len(set(kept)) == 2
    assert all(p.exists() for p in kept)
    assert conn.execute("SELECT count(*) FROM renders").fetchone()[0] == 2


def test_every_svg_source_asks_the_cli_for_an_svg(tmp_path):
    """The store holds SVG. A canonical config that defaults to PNG renders
    fine and then has nothing to store, which the CLI reports as success."""
    for source in ("naive", "occt", "decal"):
        argv = db.canonical_argv("3001", source)
        assert argv[argv.index("--format") + 1] == "svg"


def test_a_second_writer_waits_instead_of_failing(tmp_path):
    """The store job shards, so several processes write renders at once. A
    default connection raises 'database is locked' on the second writer, and
    under a batch runner that becomes an error row the resume then skips."""
    path = tmp_path / "corpus.db"
    a = db.connect(path)
    b = db.connect(path)
    a.execute("INSERT INTO parts (id, title, printed, obsolete) "
              "VALUES ('3001', 'Brick', 0, 0)")
    a.commit()
    b.execute("INSERT INTO parts (id, title, printed, obsolete) "
              "VALUES ('3004', 'Brick', 0, 0)")
    b.commit()
    assert a.execute("SELECT count(*) FROM parts").fetchone()[0] == 2
    assert a.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_opening_a_half_created_database_is_not_a_crash(tmp_path):
    """Two processes opening a fresh DB race: one creates `meta` and the other
    reads it before the schema_version row is in it. Reading that row as if it
    must exist took out five of eight store shards at once."""
    path = tmp_path / "corpus.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()
    assert db.connect(path).execute(
        "SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] \
        == str(db.SCHEMA_VERSION)


def test_the_census_renders_are_their_own_sources(tmp_path):
    """The census draws strokeless -- fills carry the silhouette -- so its
    renders are not the drawing canonical_argv names and cannot share its
    config_key. One source per engine, because the census writes
    out/census/renders/<engine>/<part>.svg and the path has no room for both."""
    for source, engine in (("silhouette-naive", "naive"), ("silhouette-occt", "occt")):
        argv = db.canonical_argv("3001", source)
        assert argv[argv.index("--engine") + 1] == engine
        assert argv[argv.index("--line-width") + 1] == "0"
        assert argv[argv.index("--silhouette-width") + 1] == "0"
        assert "--out" not in argv, "a temp path would poison the config key"
    assert db.canonical_argv("3001", "silhouette-naive") != \
        db.canonical_argv("3001", "naive")


def test_a_facet_tree_does_not_replace_the_oracle_it_sits_beside(tmp_path):
    """A render's config_key comes from its source alone, so two census trees
    that resolve to one source overwrite each other part for part -- the wall
    keeps drawing silhouette-naive and the drawing underneath has changed."""
    lib = _library(tmp_path)
    for dirname in ("census", "census-white-naive"):
        d = tmp_path / "out" / dirname / "renders" / "naive"
        d.mkdir(parents=True)
        (d / "3001.svg").write_text(SVG)

    counts = db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path,
                        census_dirs=[tmp_path / "out" / "census",
                                     tmp_path / "out" / "census-white-naive"])
    conn = db.connect(tmp_path / "corpus.db")
    rows = {r["source"]: r["path"] for r in
            conn.execute("SELECT source, path FROM renders")}
    assert rows == {"silhouette-naive": "out/census/renders/naive/3001.svg",
                    "white-naive":
                        "out/census-white-naive/renders/naive/3001.svg"}
    assert counts["renders"] == 2 and counts["replaced"] == 0
    assert db.canonical_argv("3001", "white-naive") != \
        db.canonical_argv("3001", "silhouette-naive")


def test_a_measurement_records_which_facet_it_measured(tmp_path):
    """engine alone cannot say: two facets of one engine are both "naive", so
    a reader taking the newest run per engine hands the oracle slot the other
    facet's numbers -- silently, since both are valid rows for that engine."""
    lib = _library(tmp_path)
    for dirname, d99 in (("census", 0.45), ("census-white-naive", 1.01)):
        d = tmp_path / "out" / dirname
        d.mkdir(parents=True)
        (d / "naive-r0.jsonl").write_text(json.dumps(
            {**MEASURED, "engine": "naive", "extra_dist_px": {"99": d99}}) + "\n")

    db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path,
               census_dirs=[tmp_path / "out" / "census",
                            tmp_path / "out" / "census-white-naive"])
    conn = db.connect(tmp_path / "corpus.db")
    got = {r["source"]: r["extra_d99"] for r in
           conn.execute("SELECT source, extra_d99 FROM measurements")}
    assert got == {"silhouette-naive": 0.45, "white-naive": 1.01}


def test_a_measurement_records_a_kernel_call_the_engine_worked_around(tmp_path):
    """`UnifySameDomain` segfaults on cracked meshes, so occt probes it in a
    forked child and draws the part with its faces unmerged when the child
    dies. The child leaves a crash report naming no part; without this column
    nothing in the corpus says which parts were drawn that way."""
    lib = _library(tmp_path)
    d = tmp_path / "out" / "census"
    d.mkdir(parents=True)
    (d / "occt-r0.jsonl").write_text("\n".join(
        json.dumps(r) for r in (
            {**MEASURED, "part": "93064", "engine": "occt",
             "counts": {"unify_crash": 1}},
            {**MEASURED, "part": "3001", "engine": "occt"})) + "\n")

    db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path,
               census_dirs=[d])
    conn = db.connect(tmp_path / "corpus.db")
    got = {r["part_id"]: r["counts"] for r in
           conn.execute("SELECT part_id, counts FROM measurements")}
    assert got == {"93064": '{"unify_crash": 1}', "3001": None}


def test_a_measurement_keeps_the_build_that_drew_it(tmp_path):
    """Two passes over the same part at different engine revisions land in one
    tree, and the ingest sees only its own checkout -- so without the row's
    own stamp both come back attributed to whoever rebuilt the database."""
    lib = _library(tmp_path)
    for dirname, build in (("census", "801.aaaaaaa"), ("census-white-naive", "808.b86e88c")):
        d = tmp_path / "out" / dirname
        d.mkdir(parents=True)
        (d / "naive-r0.jsonl").write_text(json.dumps(
            {**MEASURED, "engine": "naive", "build": build}) + "\n")

    db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path,
               census_dirs=[tmp_path / "out" / "census",
                            tmp_path / "out" / "census-white-naive"],
               commit_sha="ffffff0")
    conn = db.connect(tmp_path / "corpus.db")
    got = {r["source"]: r["build"] for r in
           conn.execute("SELECT source, build FROM measurements")}
    assert got == {"silhouette-naive": "801.aaaaaaa",
                   "white-naive": "808.b86e88c"}


def test_a_row_written_before_builds_were_stamped_still_ingests(tmp_path):
    lib = _library(tmp_path)
    d = tmp_path / "out" / "census"
    d.mkdir(parents=True)
    (d / "naive-r0.jsonl").write_text(json.dumps({**MEASURED, "engine": "naive"}) + "\n")
    db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path, census_dirs=[d])
    conn = db.connect(tmp_path / "corpus.db")
    assert conn.execute("SELECT build FROM measurements").fetchone()["build"] is None


def test_the_build_names_a_revision_and_flags_an_uncommitted_engine():
    import brick_icons
    b = brick_icons.build()
    assert b == "unknown" or re.fullmatch(r"\d+\.[0-9a-f]{7,}\+?", b), b


def test_census_source_repeats_no_engine_it_is_already_named_with():
    assert db.census_source("out/census", "naive") == "silhouette-naive"
    assert db.census_source("out/census-naive", "naive") == "silhouette-naive"
    assert db.census_source("out/census-white-occt", "occt") == \
        "white-occt"


def test_a_rebuild_indexes_the_census_renders_too(tmp_path):
    conn_path = tmp_path / "corpus.db"
    lib = _library(tmp_path)
    for engine in ("naive", "occt"):
        d = tmp_path / "out" / "census" / "renders" / engine
        d.mkdir(parents=True)
        (d / "3001.svg").write_text(SVG)
    counts = db.rebuild(conn_path, lib, root=tmp_path,
                        census_dirs=[tmp_path / "out" / "census"])
    conn = db.connect(conn_path)
    sources = {r["source"] for r in conn.execute("SELECT source FROM renders")}
    assert sources == {"silhouette-naive", "silhouette-occt"}
    assert counts["renders"] == 2
    paths = {r["path"] for r in conn.execute("SELECT path FROM renders")}
    assert paths == {"out/census/renders/naive/3001.svg",
                     "out/census/renders/occt/3001.svg"}


def test_rebuild_takes_several_census_directories(tmp_path):
    # Two nodes ran the census, each into its own tree; one engine per tree.
    lib = _library(tmp_path)
    for engine, dirname in (("occt", "census"), ("naive", "census-naive")):
        d = tmp_path / "out" / dirname / "renders" / engine
        d.mkdir(parents=True)
        (d / "3001.svg").write_text(SVG)
        (tmp_path / "out" / dirname / f"{engine}-r0.jsonl").write_text(
            json.dumps({**MEASURED, "engine": engine}) + "\n")

    counts = db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path,
                        census_dirs=[tmp_path / "out" / "census",
                                     tmp_path / "out" / "census-naive"])
    assert counts["renders"] == 2
    assert counts["measurements"] == 2

    conn = db.connect(tmp_path / "corpus.db")
    assert {r["source"] for r in conn.execute("SELECT source FROM renders")} \
        == {"silhouette-occt", "silhouette-naive"}


def test_each_census_directory_is_its_own_run(tmp_path):
    # Run 1's archive holds the same rows as the live tree it is a prefix of,
    # so only the run they were imported under tells them apart.
    lib = _library(tmp_path)
    for dirname in ("census", "census-run1"):
        d = tmp_path / "out" / dirname
        d.mkdir(parents=True)
        (d / "naive-r0.jsonl").write_text(json.dumps(MEASURED) + "\n")

    db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path,
               census_dirs=[tmp_path / "out" / "census",
                            tmp_path / "out" / "census-run1"])
    conn = db.connect(tmp_path / "corpus.db")
    runs = conn.execute("SELECT id, args FROM runs ORDER BY id").fetchall()
    assert len(runs) == 2
    assert [json.loads(r["args"])["dir"] for r in runs] == \
        ["out/census", "out/census-run1"]
    assert conn.execute("SELECT count(*) FROM measurements").fetchone()[0] == 2


def test_rebuild_finds_jsonl_below_the_census_directory(tmp_path):
    # The backfill gives each batch its own JSONL in a subdirectory.
    lib = _library(tmp_path)
    d = tmp_path / "out" / "census"
    (d / "backfill").mkdir(parents=True)
    (d / "occt-r0.jsonl").write_text(json.dumps(MEASURED) + "\n")
    (d / "backfill" / "occt-3709a.jsonl").write_text(
        json.dumps({**MEASURED, "part": "3001"}) + "\n")

    counts = db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path,
                        census_dirs=[d])
    assert counts["measurements"] == 2


def test_an_inflight_marker_is_not_read_as_measurements(tmp_path):
    # `Runner` rewrites <jsonl>.inflight per item; it holds a part id, not JSON.
    lib = _library(tmp_path)
    d = tmp_path / "out" / "census"
    d.mkdir(parents=True)
    (d / "occt-r0.jsonl").write_text(json.dumps(MEASURED) + "\n")
    (d / "occt-r0.jsonl.inflight").write_text("3001\n")

    counts = db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path,
                        census_dirs=[d])
    assert counts["measurements"] == 1


def test_a_census_directory_that_is_not_there_is_skipped(tmp_path):
    # The naive node's tree does not exist on a machine that never ran it.
    lib = _library(tmp_path)
    d = tmp_path / "out" / "census"
    d.mkdir(parents=True)
    (d / "occt-r0.jsonl").write_text(json.dumps(MEASURED) + "\n")

    counts = db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path,
                        census_dirs=[d, tmp_path / "out" / "census-naive"])
    assert counts["measurements"] == 1


def test_the_default_finds_every_census_tree_under_root(tmp_path):
    # The trap this closes: a caller using defaults indexed out/census alone
    # and dropped the naive node's whole tree, with no error to notice.
    lib = _library(tmp_path)
    for engine, dirname in (("occt", "census"), ("naive", "census-naive")):
        d = tmp_path / "out" / dirname / "renders" / engine
        d.mkdir(parents=True)
        (d / "3001.svg").write_text(SVG)

    counts = db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path)
    assert counts["renders"] == 2

    conn = db.connect(tmp_path / "corpus.db")
    assert {r["source"] for r in conn.execute("SELECT source FROM renders")} \
        == {"silhouette-occt", "silhouette-naive"}


def test_census_trees_ignores_a_file_named_like_one(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "census").mkdir()
    (tmp_path / "out" / "census-stream.log").write_text("not a tree\n")
    assert db.census_trees(tmp_path) == [tmp_path / "out" / "census"]


def test_one_part_in_two_trees_is_counted_not_swallowed(tmp_path):
    # One row, and the tree sorting last wins it. The count is what says so:
    # renders stays at 1, and `replaced` is the only sign the other tree drew
    # the same part.
    lib = _library(tmp_path)
    for dirname in ("census", "census-run2"):
        d = tmp_path / "out" / dirname / "renders" / "occt"
        d.mkdir(parents=True)
        (d / "3001.svg").write_text(SVG)

    counts = db.rebuild(tmp_path / "corpus.db", lib, root=tmp_path)
    assert counts["renders"] == 1
    assert counts["replaced"] == 1

    conn = db.connect(tmp_path / "corpus.db")
    assert conn.execute("SELECT path FROM renders").fetchone()[0] == \
        "out/census-run2/renders/occt/3001.svg"


def test_a_rebuild_keeps_the_part_years(tmp_path):
    library = _library(tmp_path)
    years = tmp_path / "part-years.csv"
    years.write_text("part_id,year_from,year_to,sets,matched,colors\n"
                     "3001,1979,2026,4252,exact,57\n")
    out = tmp_path / "corpus.db"
    counts = db.rebuild(out, ldraw_dir=library, root=tmp_path,
                        census_dirs=[], years_path=years)
    assert counts["years"] == 1
    conn = db.connect(out)
    try:
        row = conn.execute("SELECT * FROM part_years WHERE part_id = '3001'").fetchone()
    finally:
        conn.close()
    assert (row["year_from"], row["year_to"], row["sets"], row["colors"]) == \
        (1979, 2026, 4252, 57)


def test_a_raster_slot_keeps_its_own_extension_and_its_bytes(tmp_path):
    """ldview is a PNG slot. A store that assumed .svg wrote the file under a
    name it is not, and read it as text on the way in, which corrupts it."""
    png = tmp_path / "made" / "3001.png"
    png.parent.mkdir(parents=True)
    raw = bytes(range(256)) * 4                    # not valid UTF-8
    png.write_bytes(raw)

    conn = db.connect(tmp_path / "corpus.db")
    dest = db.store_render(conn, "3001", "ldview", png, root=tmp_path)
    assert dest.name == "3001.png"
    assert dest.read_bytes() == raw

    row = conn.execute("SELECT path, width, height FROM renders").fetchone()
    assert row["path"] == "renders/ldview/3001.png"
    assert row["width"] is None and row["height"] is None


def test_the_rebuild_indexes_every_render_format_it_declares():
    """A format missing from `RENDER_SUFFIXES` is silently invisible.

    Re-encoding the ldview slot to WebP dropped all 3,896 of its rows on the
    next rebuild and took the slot out of the wall's picker, which lists
    whatever `renders` has rows for.
    """
    assert ".webp" in db.RENDER_SUFFIXES
    assert set(db.RENDER_SUFFIXES) >= {".svg", ".png", ".webp"}
