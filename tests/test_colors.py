import pytest

from brick_icons.colors import (Color, UnknownColorError, load_palette,
                                normalize_name, parse_ldconfig, resolve)

LDCFG = """\
0 LDraw.org Configuration File
0 // Color definitions
0 !COLOUR Black          CODE     0   VALUE #1B2A34   EDGE #808080
0                              // LEGOID  26 - Black
0 !COLOUR Red            CODE     4   VALUE #B40000   EDGE #333333
0 !COLOUR Light_Bluish_Grey CODE 71   VALUE #969696   EDGE #333333
0 !COLOUR Trans_Red      CODE    36   VALUE #C91A09   EDGE #660D05   ALPHA 128
"""


def test_parse_ldconfig_reads_code_name_value():
    cs = {c.code: c for c in parse_ldconfig(LDCFG.splitlines())}
    assert set(cs) == {0, 4, 71, 36}
    assert cs[4] == Color(code=4, name="Red", rgb=(0xB4, 0x00, 0x00), alpha=255,
                          lego_id=26)
    assert cs[71].name == "Light_Bluish_Grey"
    assert cs[71].rgb == (0x96, 0x96, 0x96)


def test_parse_ldconfig_reads_alpha():
    cs = {c.code: c for c in parse_ldconfig(LDCFG.splitlines())}
    assert cs[36].alpha == 128
    assert cs[36].opacity == 128 / 255
    assert cs[0].alpha == 255 and cs[0].opacity == 1.0


def test_color_hex_is_canonical_lowercase():
    assert Color(code=4, name="Red", rgb=(0xB4, 0, 0)).hex == "0xb40000"


def test_parse_ldconfig_ignores_comments_and_legoid_lines():
    assert len(parse_ldconfig(["0 // not a color", "0 // LEGOID 26 - Black"])) == 0


def test_normalize_name_folds_case_separators_and_gray():
    assert normalize_name("Light_Bluish_Grey") == "lightbluishgrey"
    assert normalize_name("light-bluish-gray") == "lightbluishgrey"
    assert normalize_name("Light Bluish Gray") == "lightbluishgrey"
    assert normalize_name("RED") == "red"


def test_load_palette_indexes_both_ways(tmp_path):
    (tmp_path / "LDConfig.ldr").write_text(LDCFG)
    pal = load_palette(tmp_path)
    assert pal.by_code[4].name == "Red"
    assert pal.by_name["red"].code == 4
    assert pal.by_name["lightbluishgrey"].code == 71
    # by_name is keyed by normalized names; callers normalize their lookup,
    # which is what folds the American spelling onto LDConfig's British one
    assert pal.by_name[normalize_name("Light Bluish Gray")].code == 71


def test_load_palette_is_cached(tmp_path):
    (tmp_path / "LDConfig.ldr").write_text(LDCFG)
    assert load_palette(tmp_path) is load_palette(tmp_path)


def test_load_palette_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_palette(tmp_path / "nope")


@pytest.fixture
def ld(tmp_path):
    (tmp_path / "LDConfig.ldr").write_text(LDCFG)
    return tmp_path


def test_resolve_hex_forms_pass_through(ld):
    for spec in ("0xc91a09", "#c91a09", "c91a09", "0xC91A09"):
        assert resolve(spec, ld) == ("0xc91a09", None)


def test_resolve_code(ld):
    assert resolve("4", ld) == ("0xb40000", None)
    assert resolve("71", ld) == ("0x969696", None)


def test_resolve_code_carries_alpha(ld):
    assert resolve("36", ld) == ("0xc91a09", 128)


def test_resolve_name(ld):
    assert resolve("red", ld) == ("0xb40000", None)
    assert resolve("Light Bluish Gray", ld) == ("0x969696", None)
    assert resolve("trans_red", ld) == ("0xc91a09", 128)


def test_six_digits_is_hex_but_short_digits_are_a_code(ld):
    # the precedence rule that keeps pre-existing 0xRRGGBB configs working
    assert resolve("000016", ld) == ("0x000016", None)   # hex, not code 16
    assert resolve("0x16", ld) == ("0x000016", None)     # explicit hex
    assert resolve("4", ld) == ("0xb40000", None)        # code, not hex 0x04


def test_unknown_code_and_name_raise(ld):
    with pytest.raises(UnknownColorError, match="999"):
        resolve("999", ld)
    with pytest.raises(UnknownColorError, match="chartreuse"):
        resolve("chartreuse", ld)


def test_malformed_hex_raises(ld):
    with pytest.raises(UnknownColorError):
        resolve("0xzzzzzz", ld)


def test_ldraw_codes_above_999_resolve():
    """LDConfig defines 118 of them; a 3-digit cap made every one unreachable
    and took u9496p01's whole decal down with it."""
    assert resolve("20015", "vendor/ldraw")[0] == "0xf4f4f4"


def test_six_digits_is_still_hex_not_a_code():
    """'000016' is hex, '16' is LDraw code 16 — widening the code pattern must
    not eat the hex form."""
    assert resolve("000016", "vendor/ldraw")[0] == "0x000016"


CATEGORISED = """0 // LDraw Solid Colours
0 !COLOUR Black          CODE     0   VALUE #1B2A34   EDGE #808080
0 // LDraw Rubber Colours
0 !COLOUR Rubber_Black   CODE 10000   VALUE #1B2A34   EDGE #808080
0 // LDraw Obsolete Colours
0 !COLOUR Old_Thing      CODE   500   VALUE #FF0000   EDGE #000000
""".splitlines()


def test_a_color_carries_the_heading_it_was_listed_under():
    by_code = {c.code: c for c in parse_ldconfig(CATEGORISED)}
    assert by_code[0].category == "Solid"
    assert by_code[10000].category == "Rubber"
    assert by_code[500].category == "Obsolete"


def test_a_color_listed_under_no_heading_has_no_category():
    [c] = parse_ldconfig(["0 !COLOUR Black CODE 0 VALUE #1B2A34 EDGE #808080"])
    assert c.category == ""


LEGOID_LINES = """0 // LDraw Solid Colours
0                              // LEGOID  26 - Black
0 !COLOUR Black          CODE     0   VALUE #1B2A34   EDGE #808080
0 !COLOUR Rubber_Black   CODE   256   VALUE #1B2A34   EDGE #808080
0                              // LEGOID  23 - Bright Blue
0 !COLOUR Blue           CODE     1   VALUE #1E5AA8   EDGE #333333
""".splitlines()


def test_a_color_takes_the_lego_id_declared_above_it():
    by_code = {c.code: c for c in parse_ldconfig(LEGOID_LINES)}
    assert by_code[0].lego_id == 26
    assert by_code[1].lego_id == 23


# The id is consumed by the colour it precedes: LDConfig carries one only for
# the colours LEGO itself numbers, and the rest must not inherit the last one.
def test_a_color_with_no_lego_id_of_its_own_has_none():
    by_code = {c.code: c for c in parse_ldconfig(LEGOID_LINES)}
    assert by_code[256].lego_id is None
