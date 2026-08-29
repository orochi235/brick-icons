"""A decal must lay flat on the surface it is actually printed on.

`_unwrap` used to fit ONE carrier to ALL of a part's decoration with nothing
checking the fit. A minifig torso print is 99% its flat front plus a few
collar facets, so the fit landed on neither: 973p55's circular Explorien logo
came out squashed (worst at the edges, where the cylindrical map bends most)
and 973p0c's letter V collapsed into two slivers.
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from brick_icons import unwrap

ROOT = Path(__file__).resolve().parent.parent
PARTS = ROOT / "vendor" / "ldraw" / "parts"

pytestmark = pytest.mark.skipif(not PARTS.exists(),
                                reason="run scripts/setup-ldraw.sh")


@pytest.fixture(scope="module")
def pd():
    spec = importlib.util.spec_from_file_location(
        "proof_decals", ROOT / "scripts" / "proof-decals.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["proof_decals"] = mod
    spec.loader.exec_module(mod)
    return mod


def _unwrap(pd, pid):
    polys = []
    pd.flatten(PARTS / f"{pid}.dat", np.eye(3), np.zeros(3), 16, polys)
    deco = [(c, p) for c, p in polys if c not in (16, 24)]
    body = [(c, p) for c, p in polys if c == 16]
    return pd._unwrap(deco, body)


@pytest.mark.parametrize("pid,kind,facets", [
    ("3941p01", "cylinder", 308),       # panel on a real round wall
    ("3942bp01", "cone", 160),          # stripes on a real cone
    ("3068bp00", "flat", 11),           # arrow on a real plane
    ("3040bp08", "flat", 71),           # border on a real slope
])
def test_a_decal_on_one_real_surface_keeps_that_carrier(pd, pid, kind, facets):
    """The gate specimens must not move: the fix adds a branch for decals that
    fit neither a plane nor a curve, and takes nothing off the other paths."""
    flat, _carrier, got, ghosts = _unwrap(pd, pid)
    assert (got, len(flat), ghosts) == (kind, facets, [])


def test_a_torso_print_binds_to_its_face_not_a_fitted_cylinder(pd):
    """973p55 measures 7.209 LDU off its fitted cylinder and 5.338 off its
    best-fit plane — four collar facets defeat a fit over all 501."""
    flat, _carrier, kind, ghosts = _unwrap(pd, "973p55")
    assert kind == "plane"
    assert (len(flat), len(ghosts)) == (497, 4)


def test_the_torso_logo_comes_out_a_circle(pd):
    """The symptom that named the bug: the Explorien logo is a circle on the
    part, and laid flat it has to still be one."""
    flat, _carrier, _kind, _ghosts = _unwrap(pd, "973p55")
    regions = [g for c, ps in
               [(c, [p for cc, p in flat if cc == c]) for c in {c for c, _ in flat}]
               for g in pd._union(ps)]
    ring = np.asarray(max(regions, key=lambda g: g.area).exterior.coords)[:-1]
    assert unwrap.fit_circle(ring, tol=0.25) is not None


def test_a_torso_print_gets_the_carrier_its_face_spans(pd):
    """The dashed bound comes from body facets on the bound plane. Under the
    fitted cylinder none of 973p55's 252 body facets qualified, so the cell
    drew no bound at all."""
    _flat, carrier, _kind, _ghosts = _unwrap(pd, "973p55")
    assert len(carrier) == 1
    (x0, y0), (x1, y1) = carrier[0][1].min(axis=0), carrier[0][1].max(axis=0)
    assert x1 - x0 > 25 and y1 - y0 > 25       # the whole torso front, in LDU


def test_planes_from_ignores_winding():
    """Raw LDraw winding is not trustworthy, so a plane's outward sense comes
    from the part's interior; the two windings of one face are one carrier."""
    sq = np.array([[-1., -1., 5.], [1., -1., 5.], [1., 1., 5.], [-1., 1., 5.]])
    planes = unwrap.planes_from([sq, sq[::-1]])
    assert len(planes) == 1
    assert planes[0].normal == pytest.approx([0.0, 0.0, 1.0])
    assert planes[0].offset == pytest.approx(5.0)


def test_planes_from_points_normals_away_from_the_interior():
    sq = np.array([[-1., -1., 5.], [1., -1., 5.], [1., 1., 5.], [-1., 1., 5.]])
    plane, = unwrap.planes_from([sq], inside=np.array([0.0, 0.0, 9.0]))
    assert plane.normal == pytest.approx([0.0, 0.0, -1.0])
    assert plane.offset == pytest.approx(-5.0)
