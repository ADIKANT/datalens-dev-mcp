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
    return ET.fromstring(re.search(r"<svg\b.*?</svg>", html, re.DOTALL).group())


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
    assert 0 < baseline < float(svg.get("viewBox").split()[3])
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
    assert 0 <= ys[2] < ys[1] < ys[0] <= float(svg.get("viewBox").split()[3])
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


def test_positive_bars_keep_proportions_in_adaptive_plot():
    svg = chart([bar([5, 0, 10])])
    first, zero, last = rects(svg)
    baseline = zero_y(svg)
    assert float(zero.get("height")) == 0
    assert float(last.get("height")) == pytest.approx(2 * float(first.get("height")), abs=.2)
    assert all(float(r.get("y")) + float(r.get("height")) == pytest.approx(baseline, abs=.2)
               for r in (first, last))


def test_negative_only_bars_extend_down_from_zero():
    svg = chart([bar([-5, 0, -10])])
    baseline = zero_y(svg)
    assert baseline > 0
    assert all(float(r.get("y")) == baseline for r in rects(svg))
    heights = [float(r.get("height")) for r in rects(svg)]
    assert heights[1] == 0
    assert heights[2] == pytest.approx(2 * heights[0], abs=.2)


def test_positive_stacks_remain_contiguous_in_adaptive_plot():
    svg = chart([bar([5, 0, 5]), bar([5, 0, 5], "#234567")], stacked=True)
    first, second, zero, zero2, last, last2 = rects(svg)
    assert float(second.get("y")) + float(second.get("height")) == pytest.approx(float(first.get("y")), abs=.2)
    assert first.get("height") == second.get("height") == last.get("height") == last2.get("height")
    assert float(zero.get("height")) == float(zero2.get("height")) == 0


def test_fractional_bars_keep_units_and_proportions():
    svg = chart([bar([.5, 0, .25])], primaryFormat="decimal1")
    first, zero, last = rects(svg)
    assert float(first.get("height")) == pytest.approx(2 * float(last.get("height")), abs=.2)
    assert float(zero.get("height")) == 0
    ticks = [t.text for t in svg.findall("text") if t.get("text-anchor") == "end"]
    assert len(ticks) == len(set(ticks))
