from brick_icons.colors import (Color, load_palette, normalize_name,
                                parse_ldconfig)

LDCFG = """\
0 LDraw.org Configuration File
0 // Colour definitions
0 !COLOUR Black          CODE     0   VALUE #1B2A34   EDGE #808080
0                              // LEGOID  26 - Black
0 !COLOUR Red            CODE     4   VALUE #B40000   EDGE #333333
0 !COLOUR Light_Bluish_Grey CODE 71   VALUE #969696   EDGE #333333
0 !COLOUR Trans_Red      CODE    36   VALUE #C91A09   EDGE #660D05   ALPHA 128
"""


def test_parse_ldconfig_reads_code_name_value():
    cs = {c.code: c for c in parse_ldconfig(LDCFG.splitlines())}
    assert set(cs) == {0, 4, 71, 36}
    assert cs[4] == Color(code=4, name="Red", rgb=(0xB4, 0x00, 0x00), alpha=255)
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
    assert len(parse_ldconfig(["0 // not a colour", "0 // LEGOID 26 - Black"])) == 0


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
    import pytest
    with pytest.raises(FileNotFoundError):
        load_palette(tmp_path / "nope")
