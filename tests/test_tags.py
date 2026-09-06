"""What a part is, in tags."""
from brick_icons import tags


def test_a_categorys_ldraw_marker_does_not_change_what_it_is():
    assert tags.normalize_category("~Technic") == "technic"
    assert tags.normalize_category("=Sticker") == "sticker"
    assert tags.normalize_category(None) == ""


def test_a_part_still_in_sets_is_not_retired():
    assert tags.tags_for("Brick", False, False, year_to=2026, sets=50,
                         this_year=2026) == []


def test_a_part_whose_last_set_is_old_is_retired():
    assert "retired" in tags.tags_for("Brick", False, False, year_to=2019,
                                      sets=50, this_year=2026)


def test_last_year_is_not_yet_retired():
    assert "retired" not in tags.tags_for("Brick", False, False, year_to=2025,
                                          sets=50, this_year=2026)


def test_a_part_in_hundreds_of_sets_is_popular():
    assert "popular" in tags.tags_for("Brick", False, False, year_to=2026,
                                      sets=4252, this_year=2026)


def test_a_part_in_one_set_is_obscure():
    assert "obscure" in tags.tags_for("Brick", False, False, year_to=1967,
                                      sets=1, this_year=2026)


def test_a_sideline_theme_is_obscure_however_many_sets_it_had():
    assert "obscure" in tags.tags_for("Fabuland", False, False, year_to=1985,
                                      sets=90, this_year=2026)
    assert "obscure" in tags.tags_for("Modulex", False, False)


def test_an_uncatalogued_part_is_neither_popular_nor_obscure():
    assert tags.tags_for("Brick", False, False) == []


def test_the_library_flags_carry_through():
    assert tags.tags_for("Sticker", True, True) == ["sticker", "printed", "obsolete"]
