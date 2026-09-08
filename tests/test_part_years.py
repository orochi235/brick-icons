"""Which catalog number a part's years are read off.

The routes are ranked, and the ranking is the whole content of `match`: a print
that falls through to its base part inherits the plain mould's span, set count
and colors, which is wrong in all three columns.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
years = importlib.import_module("fetch-part-years")

# (first year, last year, sets, colors)
FACTS = {
    "3005": (1954, 2026, 5144, 77),
    "3005pr0018": (2018, 2018, 1, 1),
}


def _dat(tmp_path: Path, name: str, *header: str) -> Path:
    path = tmp_path / f"{name}.dat"
    path.write_text("\n".join([f"0 {name}", *header, "1 16 0 0 0 1 0 0 0 1 0 0 0 1 x.dat"]))
    return path


def test_a_print_takes_its_own_number_over_the_plain_brick(tmp_path):
    """3005pz0 is the Gryffindor crest brick, made for one 2018 set. Read off
    3005 it claims 1954-2026 in 77 colors, which is the brick's history and
    not the print's."""
    dat = _dat(tmp_path, "3005pz0",
               "0 !KEYWORDS Brickheadz, BrickLink 3005pb031, Harry Potter",
               "0 !KEYWORDS Rebrickable 3005pr0018, Set 41615")
    assert years.keyword_parts(dat) == ["3005pr0018", "3005pb031"]
    assert years.match("3005pz0", FACTS, {}, years.keyword_parts(dat)) == (
        {"3005pr0018"}, "named")


def test_the_base_part_is_still_there_when_no_number_is_named(tmp_path):
    dat = _dat(tmp_path, "3005pq9", "0 !KEYWORDS Harry Potter")
    assert years.match("3005pq9", FACTS, {}, years.keyword_parts(dat)) == (
        {"3005"}, "base")


def test_a_named_number_the_inventories_do_not_have_is_skipped(tmp_path):
    """A keyword can name a part Rebrickable never inventoried. The route has
    to fall through rather than report a match with no years behind it."""
    dat = _dat(tmp_path, "3005pq8", "0 !KEYWORDS Rebrickable 3005pr9999")
    assert years.match("3005pq8", FACTS, {}, years.keyword_parts(dat)) == (
        {"3005"}, "base")


def test_the_parts_own_id_still_wins(tmp_path):
    """`exact` stays first: if the LDraw id IS a Rebrickable part number, no
    keyword can improve on it."""
    dat = _dat(tmp_path, "3005", "0 !KEYWORDS Rebrickable 3005pr0018")
    assert years.match("3005", FACTS, {}, years.keyword_parts(dat)) == (
        {"3005"}, "exact")


def test_keywords_below_the_header_are_not_read(tmp_path):
    """The scan stops at the first geometry line, so a stray keyword further
    down the file cannot rename the part."""
    path = tmp_path / "3005pq7.dat"
    path.write_text("0 name\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 x.dat\n"
                    "0 !KEYWORDS Rebrickable 3005pr0018\n")
    assert years.keyword_parts(path) == []
