import json
import subprocess

from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.editor.validation import validate_editor_draft


def render(recipe, bindings, size, presentation=None):
    bundle = compile_recipe(recipe, bindings, presentation, user_config_path="/nonexistent/profile.json")
    assert validate_editor_draft(bundle["draft"])["ok"]
    script = "global.Editor={wrapFn:({fn,args})=>(o)=>fn(o,...args),generateHtml:x=>x};\n"
    script += bundle["draft"]["tabs"]["prepare.js"]
    script += "\nconsole.log(JSON.stringify(module.exports.render(" + json.dumps(size) + ")));"
    return json.loads(subprocess.check_output(["node", "-e", script], text=True))


def test_kpi_responsive_badge_previous_and_area():
    bindings = {
        "metric": {"label": "Orders", "unit": "count"},
        "date": {},
        "comparison": {"label": "VS PREV WINDOW"},
        "prepared_data": {
            "value": 12345,
            "previous": 9876,
            "points": [{"date": "2026-01-01", "value": 10}, {"date": "2026-01-02", "value": 15}],
        },
    }
    small = render("kpi_sparkline", bindings, {"width": 320, "height": 180})
    large = render("kpi_sparkline", bindings, {"width": 640, "height": 260})
    assert "12 345" in small and "9 876" in small
    assert "font-size:48px" in large and "font-size:32px" in small
    assert 'data-id="kpi-delta"' in small and "+25%" in small
    assert 'data-id="sparkline-area"' in small
    assert "text-transform:uppercase" in small and "background:transparent" in small


def test_version_statuses_and_ancestor_groups():
    statuses = ["noChange", "hwChange", "swChange", "blChange", "missing", "manual_not_applicable", "config_error"]
    columns = [{"key": str(i), "headers": [str(i), "SW", "CI", "Ready", "Yes", "Version"]} for i in range(7)]
    bindings = {
        "metric": {},
        "rows": [],
        "columns": columns,
        "prepared_data": {
            "columns": columns,
            "rows": [{"label": "Component", "cells": [{"value": "v1", "status": s} for s in statuses]}],
        },
    }
    html = render("comparison_matrix", bindings, {"width": 900, "height": 500})
    assert "span 7;grid-row:2" not in html
    assert "font-family:ui-monospace" in html
    assert "white-space:nowrap;overflow:hidden;cursor:help" in html
    assert "--g-color-text-positive" in html
    assert "background-color:" in html and "position:absolute;inset:0" in html
    for color in ["#B8F6D6", "#FFF2B8", "#BBD8FF", "#FFE1D6"]:
        assert color in html
    assert ">NA<" in html and ">CONFIG ERROR<" in html and ">-<" in html
    # Sticky labels must cover scrolled cells even outside a host theme.
    from html.parser import HTMLParser

    class StickyLabels(HTMLParser):
        def handle_starttag(self, tag, attrs):
            style = dict(attrs).get("style", "")
            if "position:sticky;left:0;z-index:5" in style:
                assert "background:var(--g-color-base-background,#ffffff)" in style

    StickyLabels().feed(html)


def test_period_series_compiles_js_family_with_comparison_and_hover():
    bindings = {
        "metric": {"label": "Session trend"},
        "date": {},
        "comparison": {"method": "previous_window"},
        "prepared_data": {
            "categories": ["2026-01-01", "2026-01-02"],
            "comparisonCategories": ["2025-12-30", "2025-12-31"],
            "series": [
                {
                    "name": "Sessions",
                    "type": "line",
                    "color": "#2B75E2",
                    "values": [10, 20],
                    "comparisonValues": [8, 15],
                    "comparisonLegendName": "Previous sessions",
                }
            ],
        },
    }
    html = render("period_series", bindings, {"width": 900, "height": 420})
    assert 'stroke-width="2.4"' in html
    assert 'stroke-dasharray="6 5"' in html
    assert "combo-bucket-0" in html and "Previous sessions" in html


def test_weekly_shell_keeps_manual_height_and_missing_values():
    bindings = {
        "metric": {"label": "Orders"},
        "date": {},
        "group": {},
        "prepared_data": {
            "weeks": [{"label": "26w01"}, {"label": "26w02"}],
            "rows": [{"label": "Campaign A", "values": [0, None], "total": 0}],
            "total_values": [0, None],
            "grand_total": 0,
        },
    }
    html = render("weekly_totals_table", bindings, {"width": 640, "height": 150})
    assert "border-radius:8px" in html
    assert "min-height:180px" not in html
    assert ">—<" in html
    assert "right:0" in html and "left:0" in html


def test_nonadditive_weekly_requires_source_totals():
    import pytest

    with pytest.raises(ValueError, match="source-computed totals"):
        compile_recipe(
            "weekly_totals_table",
            {
                "group": {},
                "date": {},
                "metric": {"aggregation": "count_distinct"},
                "prepared_data": {"weeks": [{"label": "26w01"}], "rows": [{"label": "A", "values": [5]}]},
            },
            user_config_path="/nonexistent/profile.json",
        )


def test_period_series_rejects_misaligned_comparison():
    import pytest

    with pytest.raises(ValueError, match="aligned"):
        compile_recipe(
            "period_series",
            {
                "metric": {},
                "date": {},
                "comparison": {},
                "prepared_data": {
                    "categories": ["a", "b"],
                    "series": [{"name": "A", "type": "line", "values": [1, 2], "comparisonValues": [3]}],
                },
            },
            user_config_path="/nonexistent/profile.json",
        )


def test_nonadditive_null_totals_stay_missing():
    html = render(
        "weekly_totals_table",
        {
            "metric": {"aggregation": "ratio"},
            "date": {},
            "group": {},
            "prepared_data": {
                "weeks": [{"label": "26w01"}],
                "rows": [{"label": "A", "values": [0.5], "total": None}],
                "total_values": [None],
                "grand_total": None,
            },
        },
        {"width": 640, "height": 200},
    )
    assert ">—</div></div>" in html
    assert 'data-id="weekly-row-total-0"' in html


def test_numeric_matrix_does_not_invent_release_headers():
    html = render(
        "comparison_matrix",
        {"metric": {}, "rows": [], "prepared_data": {"rows": [{"label": "A", "current": 12, "previous": 10}]}},
        {"width": 640, "height": 200},
    )
    assert "RELEASE SCOPE" not in html
    assert "Current" in html and "Previous" in html


def test_kpi_fractional_precision_groups_only_integer_part():
    html = render(
        "kpi_sparkline",
        {
            "metric": {"label": "Ratio", "precision": 4},
            "date": {},
            "comparison": {},
            "prepared_data": {"value": 1234.5678, "previous": 1000.1234, "points": []},
        },
        {"width": 640, "height": 260},
    )
    assert "1 234.5678" in html and "1 000.1234" in html


def test_kpi_previous_keeps_metric_unit_without_inventing_missing_value():
    bindings = {
        "metric": {"label": "Conversion", "unit": "%", "precision": 2},
        "date": {},
        "comparison": {},
        "prepared_data": {"value": 84.21, "previous": 80.15, "points": []},
    }
    html = render("kpi_sparkline", bindings, {"width": 320, "height": 180})
    previous = html.split('data-id="kpi-previous"', 1)[1].split('</div>', 1)[0]
    assert '80.15 <small>%</small>' in previous
    bindings["prepared_data"]["previous"] = None
    missing = render("kpi_sparkline", bindings, {"width": 320, "height": 180})
    previous = missing.split('data-id="kpi-previous"', 1)[1].split('</div>', 1)[0]
    assert '>—' in previous and '%' not in previous
