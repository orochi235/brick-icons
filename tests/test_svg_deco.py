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


_FILLS = [{"d": "M0 0L10 0L10 10Z", "fill": "#858585"},
          {"d": "M2 2L4 2L4 4Z", "fill": "#b40000", "deco": True}]


def _path(svg, d):
    return next(line for line in svg.splitlines() if f'd="{d}"' in line)


def test_solid_deco_keeps_decoration_opaque_and_the_body_translucent(tmp_path):
    svg = trace.segments_to_svg([], 20, 20, tmp_path / "p.svg", fills=_FILLS,
                                opacity=0.5, solid_deco=True).read_text()
    body, deco = _path(svg, "M0 0L10 0L10 10Z"), _path(svg, "M2 2L4 2L4 4Z")
    assert 'opacity="0.5"' in body and "stroke=" not in body
    # opaque, so it takes the seam stroke an opaque fill does
    assert "opacity" not in deco and 'stroke="#b40000"' in deco


def test_without_solid_deco_decoration_is_as_translucent_as_the_body(tmp_path):
    svg = trace.segments_to_svg([], 20, 20, tmp_path / "p.svg", fills=_FILLS,
                                opacity=0.5).read_text()
    assert 'opacity="0.5"' in _path(svg, "M2 2L4 2L4 4Z")


def test_solid_deco_changes_nothing_on_an_opaque_render(tmp_path):
    a = trace.segments_to_svg([], 20, 20, tmp_path / "a.svg", fills=_FILLS).read_text()
    b = trace.segments_to_svg([], 20, 20, tmp_path / "b.svg", fills=_FILLS,
                              solid_deco=True).read_text()
    assert a == b
