from pathlib import Path

from brick_icons.lab import corpus

ROOT = Path(__file__).resolve().parent.parent


def test_lists_every_source():
    names = {c["name"] for c in corpus.lists(root=ROOT)}
    assert {"parts", "specimens", "manifest:all", "manifest:unprinted",
            "manifest:spread"} <= names


def test_parts_txt_drops_comments_and_blanks():
    got = {c["name"]: c for c in corpus.lists(root=ROOT)}["parts"]
    assert "3001" in got["parts"]
    assert not any(p.startswith("#") for p in got["parts"])
    assert "" not in got["parts"]


def test_specimens_strips_inline_comments():
    got = {c["name"]: c for c in corpus.lists(root=ROOT)}["specimens"]
    assert "3941" in got["parts"]
    assert not any(" " in p for p in got["parts"])


def test_manifest_lists_come_from_the_toml():
    got = {c["name"]: c for c in corpus.lists(root=ROOT)}["manifest:spread"]
    assert got["parts"][0] == "3005"
    assert "3649" in got["parts"]


def test_a_missing_source_is_skipped_not_fatal(tmp_path):
    assert corpus.lists(root=tmp_path) == []


def test_combos_come_from_the_manifest():
    names = {c["name"] for c in corpus.combos(root=ROOT)}
    assert {"outline-flat3", "outline", "wireframe"} <= names


def test_a_combo_carries_its_args():
    got = {c["name"]: c for c in corpus.combos(root=ROOT)}["outline"]
    assert "--shading" in got["args"]
    assert got["args"][got["args"].index("--shading") + 1] == "outline"


def test_a_combo_resolves_its_parts_list():
    got = {c["name"]: c for c in corpus.combos(root=ROOT)}["outline"]
    assert "3941" in got["parts"]
    assert "3941p01" not in got["parts"]      # `outline` runs unprinted only


def test_combos_are_empty_without_a_manifest(tmp_path):
    assert corpus.combos(root=tmp_path) == []


def test_combos_for_names_only_the_ones_a_part_is_in():
    names = {c["name"] for c in corpus.combos_for(ROOT, "3941p01")}
    assert "outline-flat3" in names
    assert "outline" not in names             # printed parts are out of that gate


def test_combos_for_an_unknown_part_is_empty():
    assert corpus.combos_for(ROOT, "not-a-part") == []
