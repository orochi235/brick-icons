"""--solid-deco on a translucent render: print is opaque, so the edges the
see-through body shows behind it are cut, and nothing else is."""
import pytest
import shapely

from brick_icons import cli, geom2d, hlr, process, render, shade
from brick_icons.config import load_config

W = 512


def _drawn(part, ldraw_dir):
    lat, long = render.resolve_latlong("iso")
    res = hlr.visible_segments(part, ldraw_dir, lat=lat, long=long, cull=False,
                               engine="occt")
    fit = hlr.fit_affine(res.bbox, W, W, 6, 1.0)
    faces = shade.apply_affine_faces(res.faces, *fit)
    ops = [op if len(op) != 5 else ("line",) + tuple(op)
           for op in hlr.fit_segments(res.segs, res.bbox, W, W, 6, 1.0)]
    return faces, ops


def _cfg(**over):
    return load_config(root="/nonexistent", overrides={"opacity": 0.5, **over})


def _inside(op, region):
    """Per sample, every half px along the op: is it inside `region`?"""
    line = shapely.LineString(process.op_points(op, 64)).segmentize(0.5)
    xs, ys = zip(*line.coords)
    return shapely.contains_xy(region, xs, ys)


@pytest.mark.parametrize("part", ["3068bp01", "3039p03", "14716d01"])
def test_strokes_behind_print_go_and_the_rest_stay(ldraw_dir, part):
    faces, ops = _drawn(part, ldraw_dir)
    line = 2.0
    cut = cli._print_cut(_cfg(solid_deco=True), faces, ops, line)
    cover = shade.print_cover(faces, line / 2.0, close=line)
    assert cover is not None
    assert any(_inside(op, cover).any() for op in ops), \
        f"{part} draws nothing behind its print to cut"
    core = cover.buffer(-0.5)
    assert not any(_inside(op, core).any() for op in cut)
    # an op that never enters the print comes through untouched
    near = cover.buffer(0.5)
    clear = [op for op in ops if not _inside(op, near).any()]
    assert clear and all(op in cut for op in clear)


def test_the_tube_under_a_printed_tile_is_gone(ldraw_dir):
    faces, ops = _drawn("3068bp01", ldraw_dir)
    cut = cli._print_cut(_cfg(solid_deco=True), faces, ops, 2.0)
    print_area = geom2d.union_all(
        [geom2d.to_geom(f["poly"], f.get("holes")) for f in faces
         if f.get("color", 16) != 16]).buffer(2.0)
    under = [op for op in ops if op[0] == "arc" and _inside(op, print_area).all()]
    assert under, "3068bp01's tube should draw under its print"
    assert not any(op in cut for op in under)


def test_without_the_flag_or_at_full_opacity_nothing_is_cut(ldraw_dir):
    faces, ops = _drawn("3068bp01", ldraw_dir)
    assert cli._print_cut(_cfg(), faces, ops, 2.0) == ops
    assert cli._print_cut(_cfg(opacity=1.0, solid_deco=True),
                          faces, ops, 2.0) == ops
