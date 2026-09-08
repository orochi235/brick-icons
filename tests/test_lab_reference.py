"""LDView is a subprocess per frame, so a reference is cached by everything
that changes the picture and by nothing else."""
import pytest

from brick_icons.lab import reference


def test_same_request_gives_the_same_key():
    a = reference.key("3941", "30,25", 900, None)
    b = reference.key("3941", "30,25", 900, None)
    assert a == b


def test_angle_changes_the_key():
    assert reference.key("3941", "30,25", 900, None) \
        != reference.key("3941", "45,45", 900, None)


def test_color_changes_the_key():
    assert reference.key("3941", "30,25", 900, None) \
        != reference.key("3941", "30,25", 900, "0xc91a09")


def test_resolution_changes_the_key():
    assert reference.key("3941", "30,25", 900, None) \
        != reference.key("3941", "30,25", 1200, None)


def test_key_is_filesystem_safe():
    k = reference.key("3941", "30,25", 900, "0xc91a09")
    assert k.isalnum() and len(k) == 16


def test_renders_a_part(tmp_path, ldraw_dir):
    if not reference.available("."):
        pytest.skip("LDView not installed; run scripts/setup-ldview.sh")
    got = reference.render_reference("3005", "30,25", root=".", cache_root=tmp_path)
    assert got["ok"], got["error"]
    assert (tmp_path / got["key"] / got["name"]).exists()


def test_second_request_is_cached(tmp_path, ldraw_dir):
    if not reference.available("."):
        pytest.skip("LDView not installed; run scripts/setup-ldview.sh")
    reference.render_reference("3005", "30,25", root=".", cache_root=tmp_path)
    again = reference.render_reference("3005", "30,25", root=".", cache_root=tmp_path)
    assert again["cached"] is True


def test_a_missing_ldview_is_a_message_not_a_traceback(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "available", lambda root: False)
    got = reference.render_reference("3005", "30,25", root=".", cache_root=tmp_path)
    assert got["ok"] is False
    assert "setup-ldview" in got["error"]


def test_a_bad_angle_is_reported(tmp_path):
    got = reference.render_reference("3005", "not-an-angle", root=".", cache_root=tmp_path)
    assert got["ok"] is False
    assert "angle" in got["error"].lower()
