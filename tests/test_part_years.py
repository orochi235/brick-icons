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
    "11477": (2013, 2026, 3335, 41),
    "003238": (1979, 1979, 1, 1),
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


def test_a_sticker_numbered_like_a_mould_reads_as_the_mould(tmp_path):
    """A sticker's id is the sheet number plus a letter, so `11477dya` looks
    like one sticker off sheet 11477. The corpus holds 11477 as a plain slope,
    which makes it the mould this is a decoration of -- and 3,335 sets the
    slope's figure, not this print's."""
    dat = _dat(tmp_path, "11477dya", "0 !KEYWORDS Speed Champions")
    assert years.match("11477dya", FACTS, {}, years.keyword_parts(dat),
                       moulds={"11477"}) == ({"11477"}, "base")


def test_a_sticker_off_a_real_sheet_keeps_the_sheet_route(tmp_path):
    """003238 is a sheet Rebrickable inventories and the corpus does not hold
    as a part, so its count ships with the sticker and is the sticker's."""
    dat = _dat(tmp_path, "003238a", "0 !KEYWORDS Set 375-2")
    assert years.match("003238a", FACTS, {}, years.keyword_parts(dat),
                       moulds={"11477"}) == ({"003238"}, "sheet")


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


def test_a_print_s_own_sets_outrank_its_base_mould(tmp_path):
    """3622p04 names 3622pr0003, which no inventory holds, and set 70810.
    Falling through to 3622 dated a 2014 print 1978-2026."""
    facts = {"3622": (1978, 2026, 3222, 62)}
    dat = _dat(tmp_path, "3622p04",
               "0 !KEYWORDS BrickLink 3622pb052, Queasy Kitty",
               "0 !KEYWORDS Rebrickable 3622pr0003, Set 70810, The LEGO Movie")
    assert years.year_row("3622p04", dat, facts, {}, {"70810-1": 2014},
                          {"70810": [2014]}) == (
        "3622p04", 2014, 2014, 0, "keywords", 0)


def test_a_print_naming_no_dated_set_still_falls_back_to_its_mould(tmp_path):
    dat = _dat(tmp_path, "3005pq9", "0 !KEYWORDS Harry Potter")
    assert years.year_row("3005pq9", dat, FACTS, {}, {}, {}) == (
        "3005pq9", 1954, 2026, 5144, "base", 77)


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


def test_a_mould_never_sold_plain_takes_the_span_of_its_prints():
    """11778, an eagle's wing, is in no inventory: it is only ever sold with
    feathers on it. Its two prints ran 2013-2014 and 2018-2018, and they share
    no year -- the mould that cut both was in production across the whole
    span, so it is the envelope and not the overlap."""
    plain = {"11778": True, "11778p01": False, "11778p02": False}
    spans = {"11778p01": (2013, 2014), "11778p02": (2018, 2018)}
    assert years.from_prints(plain, spans) == [("11778", 2013, 2018, 0, "prints", 0)]


def test_an_inherited_span_counts_no_sets_and_no_colors():
    """The reverse direction is the known trap -- a print reads its plain
    tile's 5,766 sets and passes for popular. Neither number travels."""
    got, = years.from_prints({"3001": True, "3001p01": False},
                             {"3001p01": (1999, 2001)})
    assert (got[3], got[5]) == (0, 0)


def test_a_base_the_inventories_already_know_keeps_its_own_years():
    assert years.from_prints({"3001": True, "3001p01": False},
                             {"3001": (1954, 2026), "3001p01": (1999, 2001)}) == []


def test_a_printed_part_inherits_nothing_from_its_own_prints():
    """A print of a print is still a print, and the ask is about base moulds."""
    assert years.from_prints({"3001p01": False, "3001p01p9": False},
                             {"3001p01p9": (1999, 2001)}) == []


def test_a_retired_print_still_dates_a_mould_that_is_current():
    plain = {"11778": True, "11778p01": False}
    assert years.from_prints(plain, {"11778p01": (2013, 2014)},
                             obsolete={"11778p01"}) == [
        ("11778", 2013, 2014, 0, "prints", 0)]


def test_an_obsolete_base_gets_no_row():
    assert years.from_prints({"11778": True, "11778p01": False},
                             {"11778p01": (2013, 2014)},
                             obsolete={"11778"}) == []


def test_a_base_whose_prints_are_all_undated_gets_no_row():
    assert years.from_prints({"11778": True, "11778p01": False}, {}) == []


def test_a_single_theme_dominates():
    assert years.dominant_theme(["246", "246", "246"]) == ("246", 1.0)


def test_exactly_the_threshold_dominates():
    assert years.dominant_theme(["246", "246", "246", "246", "1"]) == ("246", 0.8)


def test_below_the_threshold_dominates_nothing():
    assert years.dominant_theme(["246", "246", "246", "1", "1"]) is None


def test_no_themed_sets_dominates_nothing():
    assert years.dominant_theme([]) is None
