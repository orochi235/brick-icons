"""The handoff's defect list is generated, so it cannot disagree with the
store. A hand edit inside the markers is overwritten, which is the point."""
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
d2h = importlib.import_module("defects-to-handoff")

ONE = {
    "id": "3941-occt-borehole", "part": "3941", "engines": ["occt"],
    "status": "open", "title": "borehole rim not drawn",
    "mark": {"x": 0.4, "y": 0.5, "w": 0.1, "h": 0.1},
    "seen": {"angle": "30,25"}, "filed": "2026-08-31", "notes": "",
}

MARKED = """# Handoff

## Open

<!-- defects:begin -->
stale text
<!-- defects:end -->

## Traps
"""


def test_renders_a_defect_as_a_bullet():
    text = d2h.render([ONE])
    assert "**`3941`" in text
    assert "borehole rim not drawn" in text
    assert "occt" in text


def test_groups_by_status_with_open_first():
    fixed = {**ONE, "id": "x", "status": "fixed", "title": "done one"}
    text = d2h.render([fixed, ONE])
    assert text.index("borehole rim not drawn") < text.index("done one")


def test_omits_a_status_with_no_defects():
    assert "wontfix" not in d2h.render([ONE])


def test_says_so_when_there_are_none():
    assert "no defects" in d2h.render([]).lower()


def test_notes_are_carried_but_indented():
    text = d2h.render([{**ONE, "notes": "only at 30,25"}])
    assert "  only at 30,25" in text


def test_replaces_only_between_the_markers(tmp_path):
    path = tmp_path / "HANDOFF.md"
    path.write_text(MARKED)
    d2h.write_into(path, [ONE])
    got = path.read_text()
    assert "stale text" not in got
    assert got.startswith("# Handoff")
    assert "## Traps" in got
    assert "borehole rim not drawn" in got


def test_is_idempotent(tmp_path):
    path = tmp_path / "HANDOFF.md"
    path.write_text(MARKED)
    d2h.write_into(path, [ONE])
    once = path.read_text()
    d2h.write_into(path, [ONE])
    assert path.read_text() == once


def test_a_missing_begin_marker_is_an_error(tmp_path):
    path = tmp_path / "HANDOFF.md"
    path.write_text("# Handoff\n\nno markers here\n")
    with pytest.raises(SystemExit):
        d2h.write_into(path, [ONE])


def test_markers_out_of_order_is_an_error(tmp_path):
    path = tmp_path / "HANDOFF.md"
    path.write_text("<!-- defects:end -->\n<!-- defects:begin -->\n")
    with pytest.raises(SystemExit):
        d2h.write_into(path, [ONE])


def test_the_repo_handoff_has_the_markers():
    """The generator is useless against a handoff that never got them."""
    text = (Path(__file__).resolve().parent.parent / "HANDOFF.md").read_text()
    assert text.count("<!-- defects:begin -->") == 1
    assert text.count("<!-- defects:end -->") == 1
