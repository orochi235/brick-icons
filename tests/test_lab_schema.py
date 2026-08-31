"""The schema is derived, never written by hand: a flag the CLI grows must
appear in the lab's control panel without anyone editing the frontend."""
from brick_icons import cli
from brick_icons.lab import schema


def test_every_optional_flag_appears():
    fields = {f["key"]: f for f in schema.config_schema()}
    parser_dests = {a.dest for a in cli.build_parser()._actions
                    if a.option_strings and a.dest != "help"}
    assert parser_dests == set(fields)


def test_carries_flag_choices_and_help():
    fields = {f["key"]: f for f in schema.config_schema()}
    assert fields["engine"]["flag"] == "--engine"
    assert fields["engine"]["choices"] == ["naive", "occt"]
    assert fields["shade_style"]["flag"] == "--shade-style"
    assert "outline" in fields["shading"]["choices"]
    assert fields["opacity"]["help"]


def test_types_are_named_for_the_frontend():
    fields = {f["key"]: f for f in schema.config_schema()}
    assert fields["render_px"]["type"] == "int"
    assert fields["opacity"]["type"] == "float"
    assert fields["weld_corners"]["type"] == "bool"
    assert fields["angle"]["type"] == "str"


def test_nargs_fields_report_their_arity():
    fields = {f["key"]: f for f in schema.config_schema()}
    assert fields["label_mm"]["nargs"] == 2
    assert fields["levels"]["nargs"] == 2


def test_builds_argv_in_flag_order():
    argv = schema.to_argv("3001", {"engine": "occt", "shading": "outline"})
    assert argv[0] == "3001"
    assert "--engine" in argv and argv[argv.index("--engine") + 1] == "occt"
    assert "--shading" in argv and argv[argv.index("--shading") + 1] == "outline"


def test_omits_none_and_renders_flags_as_bare_switches():
    argv = schema.to_argv("3001", {"engine": None, "weld_corners": True})
    assert "--engine" not in argv
    assert "--weld-corners" in argv
    assert argv[argv.index("--weld-corners"):] == ["--weld-corners"]


def test_a_false_switch_is_absent_not_negated():
    assert "--weld-corners" not in schema.to_argv("3001", {"weld_corners": False})


def test_multi_value_flags_expand():
    argv = schema.to_argv("3001", {"label_mm": [40.0, 20.0]})
    i = argv.index("--label-mm")
    assert argv[i + 1:i + 3] == ["40.0", "20.0"]


def test_argv_round_trips_through_the_cli(tmp_path):
    """The whole point: what the lab runs parses to what the CLI would."""
    cfgd = {"engine": "occt", "shading": "outline", "shade_style": "flat3",
            "angle": "30,25", "opacity": 0.55}
    argv = schema.to_argv("3941", cfgd)
    args = cli._parse_args(argv)
    assert args.parts == ["3941"]
    assert (args.engine, args.shading, args.shade_style) == ("occt", "outline", "flat3")
    assert args.angle == "30,25"
    assert args.opacity == 0.55


def test_an_unknown_key_is_rejected_rather_than_dropped():
    import pytest
    with pytest.raises(KeyError):
        schema.to_argv("3001", {"not_a_flag": 1})
