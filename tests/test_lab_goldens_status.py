from pathlib import Path

from brick_icons.lab import goldens_status

ROOT = Path(__file__).resolve().parent.parent


def test_parses_case_names_into_combo_and_part(tmp_path):
    path = tmp_path / "hashes.txt"
    path.write_text("abc123  outline-flat3__3941\ndef456  outline__3941\n")
    rows = goldens_status.frozen(path)
    assert rows["3941"] == {"outline-flat3": "abc123", "outline": "def456"}


def test_ignores_comments_and_blank_lines(tmp_path):
    path = tmp_path / "hashes.txt"
    path.write_text("# a comment\n\naaa  outline__3005\n")
    assert goldens_status.frozen(path) == {"3005": {"outline": "aaa"}}


def test_a_missing_file_is_empty(tmp_path):
    assert goldens_status.frozen(tmp_path / "nope.txt") == {}


def test_status_reports_a_part_with_no_goldens(tmp_path):
    path = tmp_path / "hashes.txt"
    path.write_text("aaa  outline__3005\n")
    assert goldens_status.status(path, "9999") == {"part": "9999",
                                                   "cases": {}, "known": False}


def test_status_lists_a_parts_cases(tmp_path):
    path = tmp_path / "hashes.txt"
    path.write_text("aaa  outline__3005\nbbb  outline-flat3__3005\n")
    got = goldens_status.status(path, "3005")
    assert got["known"] is True
    assert set(got["cases"]) == {"outline", "outline-flat3"}


def test_reads_the_repos_own_frozen_hashes():
    """The layout the parser must match is the one freeze-goldens.py writes."""
    rows = goldens_status.frozen(ROOT / "tests/goldens/hashes.txt")
    assert set(rows["3001"]) >= {"outline", "outline-flat3", "wireframe"}
    assert all(len(h) == 64 for h in rows["3001"].values())


def test_cases_for_pairs_a_part_with_each_combos_argv():
    cases = goldens_status.cases_for(ROOT, "3941")
    names = {c["case"] for c in cases}
    assert "outline-flat3__3941" in names
    one = next(c for c in cases if c["case"] == "outline-flat3__3941")
    assert one["argv"][0] == "3941"
    assert "--shade-style" in one["argv"]


def test_cases_for_an_unknown_part_is_empty():
    assert goldens_status.cases_for(ROOT, "not-a-part") == []


def test_compare_case_reports_match_when_the_digest_is_equal(tmp_path):
    svg = tmp_path / "3005.svg"
    svg.write_text("<svg/>")
    from brick_icons import goldens
    got = goldens_status.compare_case(svg, goldens.sha256("<svg/>"))
    assert got == {"state": "match", "frozen": goldens.sha256("<svg/>"),
                   "fresh": goldens.sha256("<svg/>")}


def test_compare_case_reports_moved_when_it_is_not(tmp_path):
    svg = tmp_path / "3005.svg"
    svg.write_text("<svg/>")
    assert goldens_status.compare_case(svg, "deadbeef")["state"] == "moved"


def test_compare_case_reports_a_missing_render(tmp_path):
    assert goldens_status.compare_case(tmp_path / "gone.svg", "deadbeef")["state"] \
        == "missing"


def test_compare_case_reports_a_case_that_was_never_frozen(tmp_path):
    svg = tmp_path / "3005.svg"
    svg.write_text("<svg/>")
    assert goldens_status.compare_case(svg, None)["state"] == "unfrozen"


def test_summarize_counts_the_states():
    got = goldens_status.summarize([
        {"state": "match"}, {"state": "match"}, {"state": "moved"}])
    assert got == {"total": 3, "match": 2, "moved": 1, "missing": 0, "unfrozen": 0}


def test_summarize_of_nothing_is_all_zero():
    assert goldens_status.summarize([])["total"] == 0
