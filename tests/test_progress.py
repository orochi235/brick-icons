"""What a render reports of its own progress, and in what order."""
from __future__ import annotations

import pytest

from brick_icons import progress, timing


@pytest.fixture(autouse=True)
def _clean():
    timing.reset()
    yield
    progress.watch(None)
    timing.reset()


class _Cfg:
    def __init__(self, engine="occt", draws_fills=True):
        self.engine, self.draws_fills = engine, draws_fills


def _watched(engine="occt", fills=True):
    seen = []
    progress.watch(lambda phase, f: seen.append((phase, f)), _Cfg(engine, fills))
    return seen


def test_a_phase_opening_moves_the_bar_to_where_it_starts():
    seen = _watched()
    with timing.phase("render"):
        with timing.phase("geometry"):
            with timing.phase("engine"):
                pass
    assert seen[-1] == ("geometry/engine",
                        progress.STARTS["occt"]["geometry/engine"])


def test_a_step_spreads_across_its_phase_band_and_no_further():
    seen = _watched()
    lo = progress.STARTS["occt"]["fill"]
    with timing.phase("fill"):
        progress.step(1, 2)
        progress.step(9, 2)
    assert seen[-2][1] == pytest.approx(lo + (1 - lo) / 2)
    assert seen[-1][1] == pytest.approx(1.0)


def test_the_bar_never_moves_back():
    """`order_faces` runs again inside a later band, and repeated phases
    reopen earlier ones; neither may pull the bar back."""
    seen = _watched()
    with timing.phase("fill"):
        progress.step(1, 2)
    with timing.phase("geometry"):
        progress.step(0, 10)
    fractions = [f for _, f in seen]
    assert fractions == sorted(fractions)


def test_a_tight_loop_reports_once_per_percent():
    seen = _watched()
    with timing.phase("fill"):
        for i in range(10_000):
            progress.step(i, 10_000)
    assert len(seen) <= 102


def test_nobody_watching_costs_nothing_and_says_nothing():
    progress.step(1, 2)
    with timing.phase("geometry"):
        pass
    assert progress._on is None


def test_an_unknown_engine_still_names_its_phases():
    seen = _watched("cadquery")
    with timing.phase("geometry"):
        pass
    assert seen == [("geometry", 0.0)]


def test_without_fills_the_render_ends_where_fill_would_start():
    """An outline drawing never opens `fill`, so its last band would be a
    stretch of bar no work fills."""
    seen = _watched(fills=False)
    with timing.phase("studs"):
        pass
    occt = progress.STARTS["occt"]
    assert seen[-1][1] == pytest.approx(occt["studs"] / occt["fill"])


def test_a_step_is_labelled_with_the_phase_still_open():
    seen = _watched()
    with timing.phase("geometry"):
        with timing.phase("decoration"):
            pass
        progress.step(1, 2)
    assert seen[-1][0] == "geometry"
