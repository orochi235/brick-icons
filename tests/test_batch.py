import json

from brick_icons import batch


def _spin(_):
    while True:
        pass


def test_a_timeout_is_a_row_not_the_end_of_the_run(tmp_path):
    log = tmp_path / "out.jsonl"
    runner = batch.Runner(log, timeout=0.2)
    done = [runner.run(item, _spin if item == "b" else (lambda i: {"item": i}))
            for item in ("a", "b", "c")]
    assert [d["item"] for d in done] == ["a", "b", "c"]
    assert ["error" in d for d in done] == [False, True, False]
    assert done[1]["error"] == "TimeoutError"
    assert [json.loads(l)["item"] for l in log.read_text().splitlines()] == \
        ["a", "b", "c"]


def test_resume_skips_what_is_done_and_buries_what_crashed(tmp_path):
    log = tmp_path / "out.jsonl"
    log.write_text(json.dumps({"item": "a"}) + "\n")
    (tmp_path / "out.jsonl.inflight").write_text("b")
    runner = batch.Runner(log, timeout=0)
    assert runner.remaining(["a", "b", "c"]) == ["c"]
    rows = [json.loads(l) for l in log.read_text().splitlines()]
    assert rows[-1] == {"item": "b", "error": "ProcessDied",
                        "detail": "killed mid-render; not retried"}


def test_every_row_carries_the_run_wide_fields(tmp_path):
    """The census keys measurements by engine, so a row it writes without one
    -- a crash burial especially -- cannot be imported."""
    log = tmp_path / "out.jsonl"
    (tmp_path / "out.jsonl.inflight").write_text("b")
    runner = batch.Runner(log, key="part", extra={"engine": "occt"})
    assert runner.remaining(["a", "b"]) == ["a"]
    runner.run("a", lambda p: {"part": p})
    rows = [json.loads(l) for l in log.read_text().splitlines()]
    assert [r["part"] for r in rows] == ["b", "a"]
    assert [r["engine"] for r in rows] == ["occt", "occt"]


def test_a_raising_item_is_a_row_and_the_inflight_marker_is_cleared(tmp_path):
    log = tmp_path / "out.jsonl"
    runner = batch.Runner(log)

    def boom(_):
        raise RuntimeError("no such part")

    row = runner.run("a", boom)
    assert row["error"] == "RuntimeError"
    assert row["detail"] == "no such part"
    assert not (tmp_path / "out.jsonl.inflight").exists()
