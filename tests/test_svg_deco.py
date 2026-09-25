from brick_icons import trace


def test_decoration_fills_are_marked_and_body_fills_are_not(tmp_path):
    fills = [{"d": "M0 0L10 0L10 10Z", "fill": "#858585"},
             {"d": "M2 2L4 2L4 4Z", "fill": "#b40000", "deco": True}]
    svg = trace.segments_to_svg([], 20, 20, tmp_path / "p.svg", fills=fills).read_text()
    assert '<path d="M0 0L10 0L10 10Z" fill="#858585"' in svg
    assert '<path d="M2 2L4 2L4 4Z" class="deco" fill="#b40000"' in svg


def test_the_root_says_decoration_is_marked(tmp_path):
    svg = trace.segments_to_svg([], 20, 20, tmp_path / "p.svg").read_text()
    assert trace.DECO_MARKED in svg.split(">", 1)[0]


def test_the_mask_is_none_for_a_render_that_marks_nothing():
    assert trace.deco_mask_svg('<svg viewBox="0 0 1 1"><path d="M0 0" fill="#000"/></svg>') is None
