"""Geometry assertions against the actual compiled renderer executed by Node."""
import re
import xml.etree.ElementTree as ET

import pytest

from test_visual_fidelity import render


def chart(series, **options):
    html = render(
        "period_series",
        {"metric": {}, "date": {}, "comparison": {}, "prepared_data": {
            "categories": ["a", "b", "c"], "series": series, **options,
        }},
        {"width": 900, "height": 420},
    )
    return ET.fromstring(re.search(r"<svg\b.*?</svg>", html, re.S).group())


def bar(values, color="#123456"):
    return {"name": "A", "type": "bar", "color": color, "values": values}


def rects(svg):
    return [r for r in svg.findall("rect") if r.get("opacity") == "0.90"]


def zero_y(svg):
    return next(float(t.get("y")) - 4 for t in svg.findall("text")
                if t.get("text-anchor") == "end" and t.text == "0")


def test_negative_zero_positive_bars_share_zero_baseline():
    svg = chart([bar([-5, 0, 10])])
    negative, zero, positive = rects(svg)
    baseline = zero_y(svg)
    assert 34 < baseline < 272
    assert float(negative.get("y")) == pytest.approx(baseline, abs=.11)
    assert float(negative.get("height")) > 0
    assert float(zero.get("height")) == 0
    assert float(positive.get("y")) + float(positive.get("height")) == pytest.approx(baseline, abs=.11)
    assert float(positive.get("height")) == pytest.approx(2 * float(negative.get("height")), abs=.2)
    assert "-5" in [t.text for t in svg.findall("text") if t.get("text-anchor") == "middle"]


@pytest.mark.parametrize("axis", ["left", "right"])
def test_signed_line_and_comparison_fit_plot_and_break_at_missing(axis):
    svg = chart([{"name": "A", "type": "line", "axis": axis, "color": "#123456",
                  "values": [-5, 0, 10], "comparisonValues": [-10, None, 5]}])
    line = next(p for p in svg.findall("polyline") if p.get("stroke-width") == "2.4")
    ys = [float(pair.split(",")[1]) for pair in line.get("points").split()]
    assert 34 <= ys[2] < ys[1] < ys[0] <= 272
    assert not any(p.get("stroke-dasharray") for p in svg.findall("polyline"))


def test_mixed_stacks_accumulate_separately_above_and_below_zero():
    svg = chart([bar([10, None, None]), bar([-5, None, None], "#234567"),
                 bar([3, None, None], "#345678"), bar([-2, None, None], "#456789")], stacked=True)
    positive, negative, positive2, negative2 = rects(svg)
    baseline = zero_y(svg)
    assert float(positive.get("y")) + float(positive.get("height")) == pytest.approx(baseline, abs=.11)
    assert float(negative.get("y")) == pytest.approx(baseline, abs=.11)
    assert float(negative.get("height")) > 0
    assert float(positive2.get("y")) + float(positive2.get("height")) == pytest.approx(float(positive.get("y")), abs=.11)
    assert float(negative2.get("y")) == pytest.approx(float(negative.get("y")) + float(negative.get("height")), abs=.11)
    labels = [t.text for t in svg.findall("text") if t.get("text-anchor") == "middle"]
    assert "13" in labels and "-7" in labels


def test_positive_reference_geometry_is_preserved():
    svg = chart([bar([5, 0, 10])])
    assert [(r.get("y"), r.get("height")) for r in rects(svg)] == [
        ("153.0", "119.0"), ("272.0", "0.0"), ("34.0", "238.0"),
    ]
    assert zero_y(svg) == 272


def test_negative_only_bars_extend_down_from_zero():
    svg = chart([bar([-5, 0, -10])])
    assert zero_y(svg) == 34
    assert all(float(r.get("y")) == 34 for r in rects(svg))
    assert [float(r.get("height")) for r in rects(svg)] == [119, 0, 238]


def test_positive_stack_reference_geometry_is_preserved():
    svg = chart([bar([5, 0, 5]), bar([5, 0, 5], "#234567")], stacked=True)
    assert [(r.get("y"), r.get("height")) for r in rects(svg)] == [
        ("153.0", "119.0"), ("34.0", "119.0"),
        ("272.0", "0.0"), ("272.0", "0.0"),
        ("153.0", "119.0"), ("34.0", "119.0"),
    ]


def test_positive_fractional_reference_keeps_existing_minimum_scale():
    svg = chart([bar([.5, 0, .25])], primaryFormat="decimal1")
    assert [(r.get("y"), r.get("height")) for r in rects(svg)] == [
        ("153.0", "119.0"), ("272.0", "0.0"), ("212.5", "59.5"),
    ]
