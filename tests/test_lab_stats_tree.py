"""Turning one row's phase dict into the nesting it describes."""
from __future__ import annotations

from brick_icons.lab import stats


def at(nodes, path):
    for node in nodes:
        if node["path"] == path:
            return node
        found = at(node["children"], path)
        if found:
            return found
    return None


def test_a_path_becomes_a_parent_and_a_child():
    t = stats.tree({"render": 1.0, "render/geometry": 0.6})
    assert [n["path"] for n in t] == ["render"]
    assert at(t, "render/geometry")["secs"] == 0.6


def test_what_a_level_does_not_name_is_its_rest():
    t = stats.tree({"render": 1.0, "render/geometry": 0.6, "render/fill": 0.1})
    rest = at(t, "render/rest")
    assert rest["secs"] == 0.3
    assert rest["children"] == []


def test_a_level_its_children_fill_gets_no_rest():
    t = stats.tree({"render": 1.0, "render/geometry": 1.0})
    assert at(t, "render/rest") is None


def test_float_noise_is_not_an_unnamed_stage():
    """Three-decimal rounding leaves parents a hair under their children."""
    t = stats.tree({"render": 1.0, "render/geometry": 0.9995})
    assert at(t, "render/rest") is None


def test_a_leaf_never_gains_a_rest():
    """A stage with nothing measured under it is fully accounted for. A
    `rest` there would claim the whole stage was unnamed."""
    t = stats.tree({"render": 1.0})
    assert at(t, "render")["children"] == []


def test_children_come_back_biggest_first():
    t = stats.tree({"render": 1.0, "render/fill": 0.1, "render/geometry": 0.6})
    assert [c["name"] for c in at(t, "render")["children"]] \
        == ["geometry", "fill", "rest"]


def test_the_top_stacks_in_the_order_a_render_happens():
    t = stats.tree({"compare": 0.1, "render": 1.0, "truth_mask": 0.2,
                    "rasterize": 0.3})
    assert [n["name"] for n in t] == ["render", "rasterize", "truth_mask",
                                      "compare"]


def test_a_legacy_row_lands_where_its_phases_actually_ran():
    """Rows written before `timing` recorded paths name bare `geometry` and
    `fill`. Left at the top they would sit beside `render` as if they were
    not part of it."""
    t = stats.tree({"render": 1.0, "geometry": 0.6, "fill": 0.2})
    assert at(t, "render/geometry")["secs"] == 0.6
    assert at(t, "render/fill")["secs"] == 0.2
    assert at(t, "render/rest")["secs"] == 0.2


def test_a_legacy_decoration_stays_beside_geometry_rather_than_inside_it():
    """`decoration` runs inside `geometry`, but the old accumulator subtracted
    nested time, so a legacy `geometry` does not contain it. Nesting it there
    would read that exclusive number as inclusive and take the same tenth off
    `render`'s leftover twice."""
    t = stats.tree({"render": 1.0, "geometry": 0.6, "decoration": 0.1})
    assert at(t, "render/decoration")["secs"] == 0.1
    assert at(t, "render/geometry")["children"] == []
    assert at(t, "render/rest")["secs"] == 0.3


def test_an_unrecognized_bare_name_is_not_guessed_at():
    t = stats.tree({"render": 1.0, "mystery": 0.4})
    assert at(t, "mystery") is not None
    assert at(t, "render/mystery") is None


def test_a_path_whose_parent_was_never_recorded_still_draws():
    """A row can name a deep seam and not the band above it; dropping it
    would silently lose the only number that row carried."""
    t = stats.tree({"render/geometry/engine/hlr": 0.4})
    assert at(t, "render/geometry/engine/hlr")["secs"] == 0.4
    assert at(t, "render")["secs"] == 0.0


def test_summing_trees_adds_the_same_path_across_parts():
    rows = [{"nodes": stats.tree({"render": 1.0, "render/geometry": 0.6})},
            {"nodes": stats.tree({"render": 3.0, "render/geometry": 2.4})}]
    summed = stats._sum_trees(rows)
    assert at(summed, "render")["secs"] == 4.0
    assert at(summed, "render/geometry")["secs"] == 3.0


def test_a_summed_node_says_how_many_parts_reached_it():
    """A seam added halfway through a census is measured over the parts that
    carry it. Without `n` its share reads as though every part had it."""
    rows = [{"nodes": stats.tree({"render": 1.0, "render/geometry": 0.6})},
            {"nodes": stats.tree({"render": 1.0})}]
    summed = stats._sum_trees(rows)
    assert at(summed, "render")["n"] == 2
    assert at(summed, "render/geometry")["n"] == 1


def test_a_rest_is_re_derived_when_summing_rather_than_added_up():
    """Two parts whose rests come from different stages must not have those
    rests carried forward as if they were one named thing."""
    rows = [{"nodes": stats.tree({"render": 1.0, "render/geometry": 0.6})},
            {"nodes": stats.tree({"render": 1.0, "render/fill": 0.5})}]
    summed = stats._sum_trees(rows)
    assert at(summed, "render/rest")["secs"] == 0.9
    assert at(summed, "render/rest")["children"] == []


def test_normalize_folds_a_legacy_name_onto_a_path_already_present():
    assert stats.normalize({"geometry": 0.2, "render/geometry": 0.3}) \
        == {"render/geometry": 0.5}


def test_a_derived_rest_carries_no_part_count():
    """`n` says how many parts reached a stage. `rest` is arithmetic, so a 0
    there reads as "no part got here" rather than "this is not measured"."""
    rows = [{"nodes": stats.tree({"render": 1.0, "render/geometry": 0.6})}]
    summed = stats._sum_trees(rows)
    assert "n" not in at(summed, "render/rest")
    assert at(summed, "render/geometry")["n"] == 1
