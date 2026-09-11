"""What a part is, in tags."""
from brick_icons import tags


def test_a_categorys_ldraw_marker_does_not_change_what_it_is():
    assert tags.normalize_category("~Technic") == "technic"
    assert tags.normalize_category("=Sticker") == "sticker"
    assert tags.normalize_category(None) == ""


def test_a_part_still_in_sets_is_not_retired():
    assert tags.tags_for("Brick", False, year_to=2026, sets=50,
                         this_year=2026) == []


def test_a_part_whose_last_set_is_old_is_retired():
    assert "retired" in tags.tags_for("Brick", False, year_to=2019,
                                      sets=50, this_year=2026)


def test_last_year_is_not_yet_retired():
    assert "retired" not in tags.tags_for("Brick", False, year_to=2025,
                                          sets=50, this_year=2026)


def test_a_part_in_hundreds_of_sets_is_popular():
    assert "popular" in tags.tags_for("Brick", False, year_to=2026,
                                      sets=4252, this_year=2026)


def test_a_part_in_one_set_is_obscure():
    assert "obscure" in tags.tags_for("Brick", False, year_to=1967,
                                      sets=1, this_year=2026)


def test_a_sideline_theme_is_weird_however_many_sets_it_had():
    assert "weird" in tags.tags_for("Figure", False, year_to=1985,
                                    sets=90, this_year=2026,
                                    title="~Figure Fabuland Neck")
    assert "weird" in tags.tags_for(None, False, title="Modulex Brick 1 x 1")


def test_a_theme_named_deep_in_a_description_is_describing_a_picture():
    # 363 Fabuland parts are filed under `Figure`, so the category cannot find
    # them -- but "Tile 1 x 1 with Rainbow and Cloud Pattern" is not a Cloud
    # part, which is why only the opening words count.
    assert not tags.is_weird("Tile  1 x  1 with Rainbow and Cloud Pattern")
    assert not tags.is_weird("Sticker  3.0 x  3.6 with Airplane above Sun and Clouds")
    assert tags.is_weird("Mursten Window Pane  1 x  4 x  2")


def test_electric_and_magnet_come_from_the_category():
    assert "electric" in tags.tags_for("Electric", False)
    assert "magnet" in tags.tags_for("~Magnet", False)


def test_an_assembly_is_composite():
    assert "composite" in tags.tags_for("Brick", False, part_id="3815c01")
    assert "composite" not in tags.tags_for("Brick", False, part_id="3001")


def test_a_replaced_part_is_updated_rather_than_retired():
    stopped = dict(year_to=2021, sets=2492, this_year=2026)
    assert "retired" in tags.tags_for("Electric", False, **stopped)
    replaced = tags.tags_for("Electric", False, successor="61332", **stopped)
    assert "replaced" in replaced
    assert "retired" not in replaced


def test_a_part_still_being_made_is_neither_however_many_successors():
    assert tags.tags_for("Brick", False, year_to=2026, sets=50,
                         this_year=2026, successor="99999") == []


def test_an_uncatalogued_part_is_neither_popular_nor_obscure():
    assert tags.tags_for("Brick", False) == []


def test_a_printed_part_says_so():
    assert tags.tags_for("Brick", True) == ["printed"]


def test_a_sticker_is_not_a_printed_part():
    # `partindex.printed` is true for both -- its description test reads
    # "pattern" or "sticker" -- but a print is moulded into the brick and a
    # sticker is a sheet item you apply. One badge each, never both.
    assert tags.tags_for("Sticker", True) == ["sticker"]


def test_every_tag_but_obscure_answers_exactly_one_axis():
    # The axes are what filtering reads, so a tag in none of them would widen
    # the working set instead of narrowing it, and one in two would narrow
    # against itself. `obscure` has no badge, so the legend never offers it.
    claimed = [t for axis in tags.TAG_AXES for t in axis]
    assert sorted(claimed) == sorted(set(tags.TAGS) - {"obscure"})
    assert len(claimed) == len(set(claimed))


def test_by_axis_splits_the_picks_and_keeps_an_unclaimed_tag():
    assert tags.by_axis(["technic", "duplo", "printed"]) == [
        ["technic", "duplo"], ["printed"]]
    assert tags.by_axis([]) == []
    assert tags.by_axis(["obscure"]) == [["obscure"]]
