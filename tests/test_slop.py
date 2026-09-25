"""Sending renders to the slopboard wall and reading a verdict back.

`slop` is stood in for by a script that does what the real one does -- copies
the file into an inbox and prints where it landed -- so these test this module's
half of the protocol without a daemon.
"""
import json
import os
import textwrap
from pathlib import Path

import pytest

from brick_icons import slop

FAKE_SLOP = """#!/bin/sh
# Stands in for bin/slop: records the arguments, copies the last one into the
# inbox under a name of its own, and prints where it landed.
set -eu
printf '%s\\n' "$@" >> "$SLOP_ROOT/argv"
for last; do :; done
mkdir -p "$SLOP_ROOT/inbox"
n=$(ls "$SLOP_ROOT/inbox" | wc -l | tr -d ' ')
dest="$SLOP_ROOT/inbox/take$n.png"
cp "$last" "$dest"
echo "$dest"
"""


@pytest.fixture
def wall(tmp_path, monkeypatch):
    """A fake wall: `SLOP_BIN` points at the script above and `SLOP_ROOT` at a
    directory this test owns."""
    root = tmp_path / "slop"
    root.mkdir()
    fake = tmp_path / "slop-bin"
    fake.write_text(FAKE_SLOP)
    fake.chmod(0o755)
    monkeypatch.setenv("SLOP_BIN", str(fake))
    monkeypatch.setenv("SLOP_ROOT", str(root))
    return root


def _render(tmp_path, name="3001.png"):
    path = tmp_path / name
    path.write_bytes(b"\x89PNG not really")
    return path


def argv(root):
    return (root / "argv").read_text().split("\n")


def answer(root, dest, blob):
    out = root / "answers"
    out.mkdir(exist_ok=True)
    (out / dest.name).write_text(blob)


def test_sends_a_take_with_its_question_and_its_chips(wall, tmp_path):
    sent = slop.send(_render(tmp_path), run="sweep", question="reads?",
                     why="what is off about it?", of=3, label="outline sweep")
    said = argv(wall)
    assert "--run" in said and "sweep" in said
    assert "--of" in said and "3" in said
    assert "--run-label" in said and "outline sweep" in said
    assert said.count("--choice") == len(slop.VERDICTS)
    assert "what is off about it?" in said
    # A run answers per take, so the send returns rather than blocking and the
    # caller collects on its own schedule.
    assert "--no-wait" in said
    assert sent.dest.exists()
    assert sent.about == "3001"


def test_offers_no_comment_box_unless_one_was_asked_for(wall, tmp_path):
    slop.send(_render(tmp_path), question="reads?")
    assert "--why" not in argv(wall)


def test_passes_apps_and_links_through_as_slop_takes_them(wall, tmp_path):
    slop.send(_render(tmp_path), apps=["LDView=parts/3001.dat"],
              links=["part 3001=https://example.com/3001"])
    said = argv(wall)
    assert "--app" in said and "LDView=parts/3001.dat" in said
    assert "--link" in said and "part 3001=https://example.com/3001" in said


def test_refuses_a_file_the_wall_does_not_hold(wall, tmp_path):
    svg = tmp_path / "3001.svg"
    svg.write_text("<svg/>")
    # Refused here rather than by `slop`, so a run of traced outlines says what
    # is wrong in the caller's own traceback.
    with pytest.raises(ValueError, match="does not hold"):
        slop.send(svg)


def test_reads_a_chip_and_a_comment_out_of_the_answer_file(wall, tmp_path):
    sent = slop.send(_render(tmp_path), question="reads?")
    answer(wall, sent.dest, "answered\nworse\ntoo dark\nby a lot")
    verdict = slop.collect(sent, timeout=2)
    assert verdict is not None
    assert (verdict.choice, verdict.text) == ("worse", "too dark\nby a lot")
    assert verdict.answered
    # Read and removed: nothing else ever cleans the answers directory.
    assert not (wall / "answers" / sent.dest.name).exists()


def test_reads_a_free_text_answer_whose_first_line_is_not_a_choice(wall, tmp_path):
    sent = slop.send(_render(tmp_path), question="what is wrong with it?")
    answer(wall, sent.dest, "answered\n\nworse\nthan before")
    verdict = slop.collect(sent, timeout=2)
    assert verdict is not None
    assert verdict.choice is None
    assert verdict.text == "worse\nthan before"


def test_reports_a_take_dropped_without_a_verdict(wall, tmp_path):
    sent = slop.send(_render(tmp_path), question="reads?")
    answer(wall, sent.dest, "dismissed\n\n")
    verdict = slop.collect(sent, timeout=2)
    assert verdict is not None
    assert (verdict.status, verdict.choice, verdict.answered) == ("dismissed", None, False)


def test_gives_up_rather_than_hanging_on_a_take_nobody_looked_at(wall, tmp_path):
    sent = slop.send(_render(tmp_path), question="reads?")
    assert slop.collect(sent, timeout=0.1, poll=0.05) is None


def test_a_sweep_goes_up_as_one_run_and_reports_each_verdict(wall, tmp_path, capsys):
    paths = [_render(tmp_path, f"300{n}.png") for n in range(3)]
    # Answered before the collect, since nothing here is watching the wall.
    # The fake names its copies in order, so these are the three takes.
    for n in range(3):
        answer(wall, wall / "inbox" / f"take{n}.png", "answered\nbetter\n")
    verdicts = slop.review_many(paths, question="reads?", label="sweep",
                                timeout=2, root=tmp_path)
    assert [v.choice for v in verdicts] == ["better"] * 3
    assert [v.about for v in verdicts] == ["3000", "3001", "3002"]
    # One run id for the lot, and the run told the wall how many were coming.
    said = argv(wall)
    assert said.count("--run") == 3
    assert said.count("--of") == 3
    # Progress as it goes, not a summary at the end.
    out = capsys.readouterr().out
    assert "[1/3] 3000: better" in out
    assert "[3/3] 3002: better" in out


def test_writes_a_manifest_so_a_later_collect_knows_the_part(wall, tmp_path):
    sent = [slop.send(_render(tmp_path, "3001.png"), about="3001", run="r")]
    slop.write_manifest("r", sent, root=tmp_path)
    assert slop.runs(root=tmp_path) == ["r"]
    back = slop.load_manifest("r", root=tmp_path)
    assert (back[0].about, back[0].dest) == ("3001", sent[0].dest)

    answer(wall, sent[0].dest, "answered\nfixed\n")
    verdicts = slop.collect_run("r", root=tmp_path)
    assert [(v.about, v.choice) for v in verdicts] == [("3001", "fixed")]


def test_keeps_only_the_last_ten_manifests(wall, tmp_path):
    for n in range(13):
        slop.write_manifest(f"r{n:02d}", [], root=tmp_path)
        # mtime is the order, and a whole sweep can be written inside one tick.
        os.utime(tmp_path / slop.RUNS_DIR / f"r{n:02d}.json", (n, n))
    held = slop.runs(root=tmp_path)
    assert len(held) == slop.RUNS_KEPT
    assert held[0] == "r12"
    assert "r02" not in held


def test_collects_what_has_been_answered_without_waiting_for_the_rest(wall, tmp_path):
    sent = [slop.send(_render(tmp_path, f"300{n}.png"), about=f"300{n}", run="r")
            for n in range(2)]
    slop.write_manifest("r", sent, root=tmp_path)
    answer(wall, sent[1].dest, "answered\nfixed\n")
    verdicts = slop.collect_run("r", root=tmp_path)
    assert [(v.about, v.choice) for v in verdicts] == [("3001", "fixed")]


def test_the_verdicts_are_the_five_the_wall_draws_in_that_order():
    assert slop.VERDICTS == ("no change", "worse", "neutral", "better", "fixed")
    # Four of them are the review log's own vocabulary, under one other name.
    from brick_icons import review
    assert set(review.VERDICTS) - set(slop.VERDICTS) == {"regression"}


def test_finds_slop_by_env_then_path_then_the_usual_place(tmp_path, monkeypatch):
    monkeypatch.setenv("SLOP_BIN", "/nowhere/slop")
    assert slop.slop_bin() == Path("/nowhere/slop")
    monkeypatch.delenv("SLOP_BIN")
    monkeypatch.setattr(slop.shutil, "which", lambda _: None)
    assert slop.slop_bin().parts[-3:] == ("slopboard", "bin", "slop")


def test_a_manifest_reads_as_json_a_person_can_open(wall, tmp_path):
    sent = [slop.send(_render(tmp_path), about="3001", run="r")]
    path = slop.write_manifest("r", sent, root=tmp_path)
    blob = json.loads(path.read_text())
    assert blob["run"] == "r"
    assert blob["takes"][0]["about"] == "3001"
    assert textwrap.dedent(path.read_text()).endswith("\n")


def _fake_render(monkeypatch):
    """A render without LDView or LDraw, as `test_cli` does it."""
    import numpy as np
    from PIL import Image
    from brick_icons import cli

    def fake(cfg, part, out_png, **kw):
        out_png.parent.mkdir(parents=True, exist_ok=True)
        arr = np.zeros((300, 400, 4), np.uint8)
        arr[40:-40, 40:-40, :3] = 90
        arr[40:-40, 40:-40, 3] = 255
        Image.fromarray(arr, "RGBA").save(out_png)
        return out_png
    monkeypatch.setattr(cli.render, "render_part", fake)


def test_the_cli_sends_a_loose_run_and_collects_it_later(wall, tmp_path, capsys,
                                                         monkeypatch):
    from brick_icons import cli

    _fake_render(monkeypatch)
    assert cli.main(["3001", "--mode", "mono", "--review", "loose",
                     "--out", str(tmp_path / "out"), "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "on the wall as review-" in out
    assert "collect with --collect" in out
    run = slop.runs(root=tmp_path)[0]
    takes = slop.load_manifest(run, root=tmp_path)
    assert [t.about for t in takes] == ["3001"]

    answer(wall, takes[0].dest, "answered\nbetter\ncleaner corners")
    assert cli.main(["--collect", run, "--root", str(tmp_path)]) == 0
    assert "[1/1] 3001: better" in capsys.readouterr().out


def test_the_cli_says_which_runs_it_still_has_a_manifest_for(tmp_path, capsys):
    from brick_icons import cli

    assert cli.main(["--collect", "nosuch", "--root", str(tmp_path)]) == 2
    assert "no manifest for nosuch" in capsys.readouterr().out
    assert cli.main(["--collect", "latest", "--root", str(tmp_path)]) == 2
    assert "no run has a manifest left" in capsys.readouterr().out


def test_writes_its_manifest_where_it_was_told_and_nowhere_else(wall, tmp_path):
    """The repo's own `.cache` is not a scratch directory: a default root that
    leaked into it is how the first version of this dropped five manifests in
    the checkout while its tests passed."""
    here = set(Path(".").glob(".cache/slop-runs/*.json"))
    slop.review_many([_render(tmp_path)], question="reads?", timeout=0.05,
                     root=tmp_path)
    assert slop.runs(root=tmp_path)
    assert set(Path(".").glob(".cache/slop-runs/*.json")) == here
