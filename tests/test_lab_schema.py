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
