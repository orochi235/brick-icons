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


_SHADED = [{"d": "M2 2L4 2L4 4Z", "fill": "#b40000", "deco": True,
            "shade": {"gradient": {"x1": 0, "y1": 0, "x2": 9, "y2": 0,
                                   "stops": [(0.0, 0.0), (1.0, 0.4)]}}},
           {"d": "M5 5L7 5L7 7Z", "fill": "#b40000", "deco": True,
            "shade": {"alpha": 0.35, "d_seamed": "M4 4L8 4L8 8Z"}}]


def test_an_opaque_shaded_print_s_layer_covers_its_seam(tmp_path):
    svg = trace.segments_to_svg([], 20, 20, tmp_path / "p.svg",
                                fills=_SHADED).read_text()
    assert '<path d="M4 4L8 4L8 8Z" class="deco shade"' in svg
    see = trace.segments_to_svg([], 20, 20, tmp_path / "t.svg", fills=_SHADED,
                                opacity=0.5).read_text()
    # a translucent print draws no seam, so its layer is the bare region
    assert '<path d="M5 5L7 5L7 7Z" class="deco shade"' in see


def test_a_shaded_print_is_its_color_then_its_region_again_in_black(tmp_path):
    svg = trace.segments_to_svg([], 20, 20, tmp_path / "p.svg",
                                fills=_SHADED).read_text()
    lines = [ln for ln in svg.splitlines() if 'd="M2 2L4 2L4 4Z"' in ln]
    assert len(lines) == 2 and 'fill="#b40000"' in lines[0]
    layer = lines[1]
    assert 'class="deco shade"' in layer and "stroke" not in layer
    gid = layer.split('fill="url(#', 1)[1].split(")", 1)[0]
    grad = svg.split(f'id="{gid}"', 1)[1].split("</linearGradient>", 1)[0]
    assert 'stop-color="#000000" stop-opacity="0.4"' in grad
    flat = _path(svg, "M4 4L8 4L8 8Z\" class=\"deco shade")
    assert 'fill="#000000" fill-opacity="0.35"' in flat
    # the decoration mask whites the layer out with the print it shades
    assert "path.deco{" in trace.deco_mask_svg(svg)


def test_a_translucent_shaded_print_composites_with_its_layer_first(tmp_path):
    svg = trace.segments_to_svg([], 20, 20, tmp_path / "p.svg", fills=_SHADED,
                                opacity=0.5).read_text()
    assert '<g opacity="0.5"><path d="M2 2L4 2L4 4Z" class="deco" ' \
           'fill="#b40000" fill-rule="evenodd"/><path d="M2 2L4 2L4 4Z" ' \
           'class="deco shade"' in svg.replace("\n", "")
    solid = trace.segments_to_svg([], 20, 20, tmp_path / "s.svg", fills=_SHADED,
                                  opacity=0.5, solid_deco=True).read_text()
    assert '<g opacity' not in solid and 'stroke="#b40000"' in solid


def test_solid_deco_changes_nothing_on_an_opaque_render(tmp_path):
    a = trace.segments_to_svg([], 20, 20, tmp_path / "a.svg", fills=_FILLS).read_text()
    b = trace.segments_to_svg([], 20, 20, tmp_path / "b.svg", fills=_FILLS,
                              solid_deco=True).read_text()
    assert a == b
