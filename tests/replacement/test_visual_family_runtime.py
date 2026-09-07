from __future__ import annotations

import json
import subprocess
from importlib.resources import files

from datalens_dev_mcp.authoring.recipes import compile_recipe, list_recipes


def _run_renderer(asset: str, data: dict, contract: dict, *, target_id: str = "") -> dict[str, str]:
    source = files("datalens_dev_mcp.assets.recipes").joinpath(asset).read_text(encoding="utf-8")
    script = "const vm = require('node:vm'); const Editor = {generateHtml: x => x, wrapFn: x => x};\n" + source
    script += "\nconst exported = module.exports(" + json.dumps(data) + "," + json.dumps(contract) + ");"
    script += "const render = vm.runInNewContext('(' + exported.render.fn.toString() + ')', {Editor});"
    script += "const html = render({width:360,height:220}, ...exported.render.args);"
    script += "let tooltip = '';"
    script += "if (exported.tooltip) { const tip = vm.runInNewContext('(' + exported.tooltip.renderer.fn.toString() + ')', {Editor});"
    script += "tooltip = tip({target:{getAttribute:() => " + json.dumps(target_id) + "}}, ...exported.tooltip.renderer.args); }"
    script += "console.log(JSON.stringify({html, tooltip}));"
    return json.loads(subprocess.check_output(["node", "-e", script], text=True))


def test_kpi_runtime_applies_hint_spacing_auto_theme_and_semantic_tooltip(tmp_path) -> None:
    result = compile_recipe(
        "kpi_sparkline",
        {
            "prepared_data": {
                "value": 12,
                "previous": 10,
                "points": [{"date": "2026-09-01", "value": 10}, {"date": "2026-09-02", "value": 12}],
                "current_period": "2026-09-02",
                "previous_period": "2026-09-01",
            },
            "metric": {"field_guid": "metric-guid", "label": "Synthetic orders", "unit": "orders"},
            "date": {"field_guid": "date-guid", "label": "Day"},
            "comparison": {"method": "previous_period", "label": "vs prior day"},
        },
        {
            "spacing": 18,
            "hint": {"enabled": True, "text": "Synthetic definition"},
            "states_theme": {"theme": "auto"},
        },
        user_config_path=tmp_path / "absent.json",
    )
    rendered = _run_renderer(
        "kpi_sparkline_renderer.js",
        result["draft"]["bindings"]["prepared_data"],
        result["draft"]["visual_contract"],
        target_id="kpi-value",
    )

    assert "padding:18px" in rendered["html"]
    assert "data-id=\"kpi-hint\"" in rendered["html"]
    assert "background:var(--g-color-base-background,transparent)" in rendered["html"]
    assert "title=\"" not in rendered["html"]
    assert "Current" in rendered["tooltip"]
    assert "Previous" in rendered["tooltip"]
    assert "2026-09-02" in rendered["tooltip"]
    assert "orders" in rendered["tooltip"]


def test_matrix_runtime_has_dynamic_six_level_headers_sticky_first_column_and_dynamic_legend(tmp_path) -> None:
    result = compile_recipe(
        "comparison_matrix",
        {
            "prepared_data": {
                "columns": [
                    {"key": "hw", "headers": ["Scope A", "Target A", "CI 1", "Released", "Yes", "HW"]},
                    {"key": "sw", "headers": ["Scope A", "Target A", "CI 1", "Released", "Yes", "SW"]},
                ],
                "rows": [
                    {
                        "label": "Synthetic ECU",
                        "cells": [
                            {"value": "1.2", "status": "unchanged"},
                            {"value": "NA", "status": "manual_not_applicable"},
                        ],
                    }
                ],
            },
            "rows": [{"field_guid": "row-guid", "label": "ECU"}],
            "metric": {"field_guid": "metric-guid", "label": "Version"},
        },
        {
            "table": {
                "header_rows": ["Release scope", "Release target", "CI / IS", "Release status", "For assembly", "Version type"],
                "first_column_label": "ECU",
            },
            "legend": {
                "items": [
                    {"status": "unchanged", "label": "No change"},
                    {"status": "manual_not_applicable", "label": "Manual N/A"},
                ]
            },
        },
        user_config_path=tmp_path / "absent.json",
    )
    rendered = _run_renderer(
        "version_matrix_renderer.js",
        result["draft"]["bindings"]["prepared_data"],
        result["draft"]["visual_contract"],
    )["html"]

    for label in ("Release scope", "Release target", "CI / IS", "Release status", "For assembly", "Version type"):
        assert label in rendered
    assert "position:sticky;left:0" in rendered
    assert "overflow:auto" in rendered
    assert "Manual N/A" in rendered
    assert "NA" in rendered
    assert "Current" not in rendered


def test_weekly_totals_runtime_has_iso_columns_sticky_edges_totals_and_configurable_widths(tmp_path) -> None:
    result = compile_recipe(
        "weekly_totals_table",
        {
            "prepared_data": {
                "weeks": [
                    {"key": "2026-W36", "label": "26w36", "date_from": "2026-08-31", "date_to": "2026-09-06"}
                ],
                "rows": [{"label": "Synthetic campaign", "values": [7], "total": 7}],
                "total_values": [7],
                "grand_total": 7,
            },
            "group": {"field_guid": "group-guid", "label": "Campaign"},
            "date": {"field_guid": "date-guid", "label": "ISO week"},
            "metric": {"field_guid": "metric-guid", "label": "Orders", "unit": "orders"},
        },
        {
            "table": {"widths": {"first": 140, "period": 90, "total": 110}},
            "geometry": {"height": 14, "preserve_manual": True},
        },
        user_config_path=tmp_path / "absent.json",
    )
    rendered = _run_renderer(
        "weekly_totals_renderer.js",
        result["draft"]["bindings"]["prepared_data"],
        result["draft"]["visual_contract"],
        target_id="weekly-cell-0-0",
    )

    assert "26w36" in rendered["html"]
    assert "flex:0 0 140px" in rendered["html"]
    assert "flex:0 0 90px" in rendered["html"]
    assert "flex:0 0 110px" in rendered["html"]
    assert "position:sticky;left:0" in rendered["html"]
    assert "position:sticky;right:0" in rendered["html"]
    assert "TOTAL" in rendered["html"]
    assert "2026-08-31" in rendered["tooltip"]
    assert result["draft"]["visual_contract"]["geometry"]["preserve_manual"] is True


def test_supported_recipe_catalog_includes_three_exact_reference_families() -> None:
    recipes = list_recipes()
    assert recipes["kpi_sparkline"]["reference_family"] == "standalone_kpi_with_sparkline"
    assert recipes["comparison_matrix"]["reference_family"] == "multi_level_version_matrix"
    assert recipes["weekly_totals_table"]["reference_family"] == "iso_week_totals_table"
