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


def test_root_theme_walks_a_chain_to_its_root():
    tree = {"30": ("City Hall", "20"), "20": ("Town Center", "10"),
            "10": ("Town", None)}
    assert years.root_theme("30", tree, {}) == "10"


def test_root_theme_stops_at_a_missing_parent():
    tree = {"30": ("City Hall", "20")}   # "20" is not in the dump
    assert years.root_theme("30", tree, {}) == "20"


def test_root_theme_stops_at_a_cycle():
    """A corrupt or cyclic dump ends the walk instead of hanging it."""
    tree = {"a": ("A", "b"), "b": ("B", "a")}
    assert years.root_theme("a", tree, {}) == "a"


def test_theme_rows_covers_the_known_routes(tmp_path):
    """One id per route `theme_rows` treats differently: the OWN routes roll
    the part's own inventory sets up to a theme; `base` and `design` fall
    through with no row.

    Every "no row" id here has real themed sets of its own behind it, so the
    assertion is on the ROUTE being excluded, not on there being nothing to
    find -- widening OWN_ROUTES locally to include `base` and `design` turns
    every one of them into a row and fails this test.
    """
    facts = {
        "7000pr01": (0, 0, 3, 0),  # the print's own Rebrickable number
        "8000": (0, 0, 5, 0),      # base mould only -- 8000p01 reads as "base"
        "099999": (0, 0, 2, 0),    # a real sticker sheet -- "sheet"
        "055555": (0, 0, 2, 0),    # a corpus mould -- 055555a reads as "base"
        "7777": (0, 0, 2, 0),      # reached only via a design id -- "design"
    }
    sets_with = {
        "7000pr01": {"S1", "S2", "S3"},
        "8000": {"S8"},
        "099999": {"S4", "S5"},
        "055555": {"S6", "S7"},
        "7777": {"S9", "S10"},
    }
    # S3 has a theme_id ("999") the dump never defines -- dropped, not
    # KeyError'd, and not counted toward `sets`.
    set_theme = {"S1": "30", "S2": "30", "S3": "999", "S4": "77", "S5": "77",
                "S6": "10", "S7": "10", "S8": "10", "S9": "10", "S10": "10"}
    # A 3-level chain: S1/S2's theme (30) sits under 20, which sits under the
    # root 10 -- root_theme has to walk all the way, not stop at the first hop.
    tree = {"10": ("Town", None), "20": ("Town Center", "10"),
            "30": ("City Hall", "20"), "77": ("Space", None)}
    moulds = frozenset({"055555"})   # not "099999" -- that one is a real sheet
    designs = {"9999": {"7777"}}     # 9999p01's design id -- "design"

    parts = tmp_path / "parts"
    parts.mkdir()
    _dat(parts, "7000pr01")   # exact: the id IS the Rebrickable number
    _dat(parts, "8000p01")    # base-only print -- reads as "base"
    _dat(parts, "099999a")    # sheet sticker
    _dat(parts, "055555a")    # sticker off a corpus mould -- reads as "base"
    _dat(parts, "9999p01")    # only a design id names it -- reads as "design"

    rows = years.theme_rows(
        ["7000pr01", "8000p01", "099999a", "055555a", "9999p01"], parts,
        facts, sets_with, designs, set_theme, tree, moulds)

    assert rows == [("7000pr01", "Town", "1.00", 2),
                    ("099999a", "Space", "1.00", 2)]


def test_theme_rows_drops_a_named_hit_that_is_really_the_base_mould(tmp_path):
    """109373p01's own `!KEYWORDS` line names 109373 -- its plain mould, not a
    print number of its own -- so the `named` route must not read the mould's
    sets as if they were the print's."""
    facts = {"109373": (0, 0, 4, 0)}
    sets_with = {"109373": {"S1", "S2", "S3", "S4"}}
    set_theme = {"S1": "10", "S2": "10", "S3": "10", "S4": "10"}
    tree = {"10": ("Town", None)}
    parts = tmp_path / "parts"
    parts.mkdir()
    _dat(parts, "109373p01", "0 !KEYWORDS Rebrickable 109373")

    assert years.theme_rows(["109373p01"], parts, facts, sets_with, {},
                            set_theme, tree, frozenset()) == []


def test_theme_rows_keeps_a_named_hit_that_is_not_the_base_mould(tmp_path):
    """A real sticker-sheet match like 004695a->4695 must not be dropped just
    because 4695 happens to be in `moulds`."""
    facts = {"4695": (0, 0, 2, 0)}
    sets_with = {"4695": {"S1", "S2"}}
    set_theme = {"S1": "10", "S2": "10"}
    tree = {"10": ("Town", None)}
    parts = tmp_path / "parts"
    parts.mkdir()
    _dat(parts, "004695a", "0 !KEYWORDS Rebrickable 4695")

    assert years.theme_rows(["004695a"], parts, facts, sets_with, {},
                            set_theme, tree, frozenset({"4695"})) == [
        ("004695a", "Town", "1.00", 2)]


def test_theme_rows_drops_a_named_hit_for_a_composite_print(tmp_path):
    """`_PRINT_SUFFIX` can't parse a composite's print suffix, so
    3677c01p01's own `!KEYWORDS` number (3677c01, its mould) slipped past the
    plain-mould guard; the guard has to catch this shape too."""
    facts = {"3677c01": (0, 0, 4, 0)}
    sets_with = {"3677c01": {"S1", "S2", "S3", "S4"}}
    set_theme = {"S1": "10", "S2": "10", "S3": "10", "S4": "10"}
    tree = {"10": ("Town", None)}
    parts = tmp_path / "parts"
    parts.mkdir()
    _dat(parts, "3677c01p01", "0 !KEYWORDS Rebrickable 3677c01")

    assert years.theme_rows(["3677c01p01"], parts, facts, sets_with, {},
                            set_theme, tree, frozenset()) == []
