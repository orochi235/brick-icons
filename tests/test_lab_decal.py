"""Decal extraction for the lab, cached like the LDView reference.

Extraction re-parses the part, so it is cached on everything that changes the
picture. A part with no decoration is not an error -- it is the answer.
"""
import pytest

from brick_icons.lab import decal


def test_same_request_gives_the_same_key():
    assert decal.key("3941", 900, "none") == decal.key("3941", 900, "none")


def test_resolution_changes_the_key():
    assert decal.key("3941", 900, "none") != decal.key("3941", 1200, "none")


def test_background_changes_the_key():
    assert decal.key("3941", 900, "none") != decal.key("3941", 900, "#fff")


def test_key_is_filesystem_safe():
    k = decal.key("3941", 900, "none")
    assert k.isalnum() and len(k) == 16


def test_extracts_a_printed_part(tmp_path, ldraw_dir):
    got = decal.extract("3005p01", root=".", cache_root=tmp_path)
    assert got["ok"], got["error"]
    assert got["names"], "a printed part should yield at least one decal"
    assert (tmp_path / got["key"] / got["names"][0]).exists()


def test_an_unprinted_part_yields_nothing_and_is_not_an_error(tmp_path, ldraw_dir):
    got = decal.extract("3005", root=".", cache_root=tmp_path)
    assert got["ok"] is True
    assert got["names"] == []


def test_second_request_is_cached(tmp_path, ldraw_dir):
    decal.extract("3005p01", root=".", cache_root=tmp_path)
    again = decal.extract("3005p01", root=".", cache_root=tmp_path)
    assert again["cached"] is True


def test_a_part_that_does_not_exist_is_reported(tmp_path, ldraw_dir):
    got = decal.extract("no-such-part-9999", root=".", cache_root=tmp_path)
    assert got["ok"] is False
    assert got["error"]


def test_names_are_ordered_largest_print_first(tmp_path, ldraw_dir):
    """`decal_one` writes `.0` as the biggest print; the pane shows that one."""
    got = decal.extract("3005p01", root=".", cache_root=tmp_path)
    if len(got["names"]) > 1:
        assert got["names"][0].endswith(".0.svg")
