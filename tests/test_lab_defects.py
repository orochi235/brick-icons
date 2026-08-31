import pytest

from brick_icons.lab import defects

ONE = {
    "id": "3941-occt-borehole",
    "part": "3941",
    "engines": ["occt"],
    "status": "open",
    "title": "borehole rim not drawn",
    "mark": {"x": 0.42, "y": 0.55, "w": 0.11, "h": 0.09},
    "seen": {"angle": "30,25", "shading": "outline", "shade_style": "flat3"},
    "filed": "2026-08-31",
    "notes": "the near lip is legitimately hidden; occt draws nothing at all",
}


def test_reading_a_missing_file_is_an_empty_list(tmp_path):
    assert defects.load(tmp_path / "defects.toml") == []


def test_a_defect_round_trips(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    assert defects.load(path) == [ONE]


def test_multiline_notes_survive(tmp_path):
    path = tmp_path / "defects.toml"
    d = {**ONE, "notes": "first line\nsecond line"}
    defects.save(path, [d])
    assert defects.load(path)[0]["notes"] == "first line\nsecond line"


def test_a_quote_in_a_title_survives(tmp_path):
    path = tmp_path / "defects.toml"
    d = {**ONE, "title": 'the "near" lip'}
    defects.save(path, [d])
    assert defects.load(path)[0]["title"] == 'the "near" lip'


def test_adding_keeps_the_existing_defects(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    second = {**ONE, "id": "4070-occt-ledge", "part": "4070"}
    defects.add(path, second)
    assert [d["id"] for d in defects.load(path)] == [ONE["id"], second["id"]]


def test_adding_a_duplicate_id_is_refused(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    with pytest.raises(ValueError):
        defects.add(path, dict(ONE))


def test_update_changes_one_field(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    defects.update(path, ONE["id"], {"status": "fixed"})
    assert defects.load(path)[0]["status"] == "fixed"
    assert defects.load(path)[0]["title"] == ONE["title"]


def test_update_rejects_an_unknown_status(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    with pytest.raises(ValueError):
        defects.update(path, ONE["id"], {"status": "maybe"})


def test_update_of_a_missing_defect_is_an_error(tmp_path):
    path = tmp_path / "defects.toml"
    defects.save(path, [ONE])
    with pytest.raises(KeyError):
        defects.update(path, "no-such-id", {"status": "fixed"})
