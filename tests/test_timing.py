"""What a phase records, and under what name."""
from __future__ import annotations

import pytest

from brick_icons import timing


@pytest.fixture(autouse=True)
def _clean():
    timing.reset()
    yield
    timing.reset()


def test_a_nested_phase_names_its_parent():
    with timing.phase("render"):
        with timing.phase("geometry"):
            with timing.phase("hlr"):
                pass
    assert set(timing.phases()) == {"render", "render/geometry",
                                    "render/geometry/hlr"}


def test_a_parent_keeps_the_time_its_children_spent():
    """Inclusive, so adding a seam below a band never shrinks the band. The
    leftover at a level is `parent - sum(children)`, worked out when the tree
    is read."""
    with timing.phase("render"):
        _spin()
        with timing.phase("geometry"):
            _spin()
    p = timing.phases()
    assert p["render"] >= p["render/geometry"] > 0


def test_the_same_phase_entered_twice_accumulates():
    """`decoration` runs once per carrier. Reporting the last one would say a
    part with forty decals spent as long as a part with one."""
    with timing.phase("render"):
        for _ in range(3):
            with timing.phase("fill"):
                _spin()
    p = timing.phases()
    assert p["render/fill"] > 0
    assert p["render"] >= p["render/fill"]


def test_siblings_are_separate_entries():
    with timing.phase("render"):
        with timing.phase("geometry"):
            pass
        with timing.phase("fill"):
            pass
    assert set(timing.phases()) == {"render", "render/geometry", "render/fill"}


def test_the_stack_unwinds_through_an_exception():
    with pytest.raises(RuntimeError):
        with timing.phase("render"):
            with timing.phase("geometry"):
                raise RuntimeError("boom")
    assert "render/geometry" in timing.phases()
    # A later phase must not be recorded under the failed one.
    with timing.phase("rasterize"):
        pass
    assert "rasterize" in timing.phases()


def test_a_separator_in_a_name_is_refused():
    """The separator is the only thing distinguishing a path from a name; a
    phase called `a/b` would read back as a child of `a` that never ran."""
    with pytest.raises(ValueError, match="cannot contain"):
        with timing.phase("geometry/hlr"):
            pass


def test_the_decorator_records_the_function_as_a_phase():
    @timing.timed("geometry")
    def work():
        return 7

    with timing.phase("render"):
        assert work() == 7
    assert "render/geometry" in timing.phases()


def _spin():
    import time
    t = time.perf_counter()
    while time.perf_counter() - t < 0.002:
        pass
