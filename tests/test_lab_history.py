from brick_icons import db
from brick_icons.lab import history


def test_history_dates_a_point_by_its_drawing_and_falls_back_to_its_build(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "_commit_date",
                        lambda root, sha: "2026-09-01T00:00:00+00:00" if sha == "abc1234" else None)
    conn = db.connect(tmp_path / "corpus.db")
    run = db.start_run(conn, "census", {}, "x")
    conn.executemany(
        "INSERT INTO measurements (run_id, part_id, engine, source, build, secs, "
        "bytes, objects, drawn_at) VALUES (?, '3001', ?, ?, ?, ?, ?, ?, ?)",
        [(run, "occt", "occt", "10.abc1234+", 2.0, None, None, None),
         (run, "naive", "naive", "11.def5678", 3.0, 900, 7, "2026-09-12T00:00:00+00:00"),
         (run, "white-naive", None, None, 1.0, None, None, None)])
    got = {s["source"]: s["points"] for s in history.part_history(conn, "3001", tmp_path)["series"]}
    assert got["occt"][0]["at"] == "2026-09-01T00:00:00+00:00"
    assert got["occt"][0]["dated_by"] == "build"
    assert got["naive"][0] == {**got["naive"][0], "bytes": 900, "objects": 7,
                               "dated_by": "drawn"}
    assert "white-naive" not in got          # no drawing and no build: undatable


def test_a_build_names_its_commit():
    assert history._build_sha("1494.3c9e936+") == "3c9e936"
    assert history._build_sha(None) is None
