"""Connection counts and sizes, the records collego's classifier reads."""
import json

import numpy as np
import pytest

from brick_icons import facts, features


def lib_facts(ldraw_dir, *ids):
    walker = facts.Walker(features.default_roots(ldraw_dir))
    return {i: walker.facts(ldraw_dir / "parts" / f"{i}.dat") for i in ids}


def test_the_side_stud_on_87087_reads_as_side(ldraw_dir):
    got = lib_facts(ldraw_dir, "87087")["87087"]
    assert got["features"]["stud"] == {"up": 1, "down": 0, "side": 1}
    assert (got["w"], got["l"], got["h"]) == (1, 1, 3)


def test_a_brick_counts_its_studs_up_and_its_tubes_down(ldraw_dir):
    got = lib_facts(ldraw_dir, "3001")["3001"]
    assert got["features"]["stud"] == {"up": 8, "down": 0, "side": 0}
    assert got["features"]["antistud"]["down"] == 3
    # Studs stand 4 LDU proud of the top; left in, a brick would be 3.5 plates.
    assert (got["w"], got["l"], got["h"]) == (2, 4, 3)


def test_a_through_hole_is_one_hole_not_two_ends(ldraw_dir):
    got = lib_facts(ldraw_dir, "3700", "3894")
    assert got["3700"]["features"]["pinhole"] == {"up": 0, "down": 0, "side": 1}
    assert got["3894"]["features"]["pinhole"]["side"] == 5


def test_an_axle_is_not_an_axle_hole(ldraw_dir):
    """`axlehol8` draws the perimeter of an axle as well as of a hole."""
    got = lib_facts(ldraw_dir, "4519", "32064b")
    assert "axlehole" not in got["4519"]["features"]
    assert got["32064b"]["features"]["axlehole"]["side"] == 1


def test_a_tile_has_no_studs_and_is_one_plate(ldraw_dir):
    got = lib_facts(ldraw_dir, "3070b")["3070b"]
    assert "stud" not in got["features"]
    assert got["h"] == 1


def test_a_pins_bore_is_not_a_bar(ldraw_dir):
    assert "bar" not in lib_facts(ldraw_dir, "2780")["2780"]["features"]


@pytest.mark.parametrize("d, want", [
    ((0, -1, 0), "up"), ((0, 1, 0), "down"), ((1, 0, 0), "side"),
    # 9 degrees off vertical is still up; 11 is side.
    ((np.sin(np.radians(9)), -np.cos(np.radians(9)), 0), "up"),
    ((np.sin(np.radians(11)), -np.cos(np.radians(11)), 0), "side"),
])
def test_facing_is_within_ten_degrees_of_vertical(d, want):
    assert facts.facing(np.array(d, dtype=float)) == want


def test_a_record_is_json_with_only_the_kinds_present(ldraw_dir):
    got = lib_facts(ldraw_dir, "3023")["3023"]
    assert set(got["features"]) <= set(facts.KINDS)
    assert all(any(c.values()) for c in got["features"].values())
    json.dumps(got)


def test_a_bore_declared_inside_out_is_not_a_bar(ldraw_dir):
    """A minifig hand's grip is a radius-4 cylinder under BFC INVERTNEXT."""
    got = lib_facts(ldraw_dir, "3820", "30374")
    assert "bar" not in got["3820"]["features"]
    assert got["30374"]["features"]["bar"] == {"up": 1, "down": 0, "side": 0}
