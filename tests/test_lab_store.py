"""Which of a render's files the store keeps."""
import pytest

from brick_icons.lab import store


def test_an_svg_outranks_a_raster():
    assert store.drawing_in(["3001.png", "3001.svg"], "occt") == "3001.svg"


def test_a_raster_slot_keeps_its_png():
    assert store.drawing_in(["3001.png"], "occt") == "3001.png"


def test_a_decal_with_nothing_to_draw_is_none():
    assert store.drawing_in([], "decal") is None


def test_any_other_slot_drawing_nothing_is_an_error():
    with pytest.raises(RuntimeError, match="render produced no drawing"):
        store.drawing_in(["3001.json"], "occt")
