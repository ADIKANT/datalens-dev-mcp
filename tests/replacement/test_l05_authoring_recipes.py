from __future__ import annotations

import json
from pathlib import Path

from datalens_dev_mcp.authoring.profiles import get_authoring_defaults
from datalens_dev_mcp.authoring.recipes import compile_recipe, list_recipes
from datalens_dev_mcp.editor.validation import validate_editor_draft
from datalens_dev_mcp.sdk import compile_recipe as public_compile_recipe
from datalens_dev_mcp.server import list_tools

REQUIRED_RECIPES = {
    "kpi_sparkline",
    "time_comparison",
    "categorical_bar",
    "comparison_matrix",
    "cross_tab_totals",
    "native_detail_table",
    "selector",
}


def test_registry_contains_exact_reusable_families_and_synthetic_examples() -> None:
    registry = list_recipes()
    assert set(registry) == REQUIRED_RECIPES
    for recipe in registry.values():
        assert recipe["example"]["data_class"] == "synthetic"
        contract = recipe["visual_contract"]
        for key in (
            "object_name",
            "visible_title",
            "hint",
            "tooltip",
            "axes_gridlines",
            "labels",
            "legend",
            "comparison",
            "kpi",
            "table",
            "selector",
            "geometry",
            "states_theme",
        ):
            assert key in contract, (recipe["id"], key)


def test_defaults_precedence_is_generic_user_project_reference_explicit(tmp_path: Path) -> None:
    user = tmp_path / "user-authoring.json"
    project = tmp_path / "project"
    (project / ".datalens").mkdir(parents=True)
    user.write_text(
        json.dumps({"defaults": {"theme": "dark", "title": {"owner": "body"}}, "families": {"kpi_sparkline": {"technology": "advanced_chart"}}, "reference_files": ["references/kpi.json"]}),
        encoding="utf-8",
    )
    (project / ".datalens/authoring.json").write_text(
        json.dumps({"defaults": {"theme": "light", "spacing": 12}}), encoding="utf-8"
    )

    result = get_authoring_defaults(
        project_root=project,
        family="kpi_sparkline",
        user_config_path=user,
        reference={"title": {"owner": "widget"}, "spacing": 16},
        explicit={"spacing": 20},
    )

    assert result["values"]["theme"] == "light"
    assert result["values"]["technology"] == "advanced_chart"
    assert result["values"]["title"]["owner"] == "widget"
    assert result["values"]["spacing"] == 20
    assert result["precedence"] == ["generic", "user", "project", "reference", "explicit"]
    assert result["allowed_reference_files"] == [str((tmp_path / "references/kpi.json").resolve())]


def test_compile_kpi_materializes_visual_fields_and_reuses_renderer(tmp_path: Path) -> None:
    result = compile_recipe(
        "kpi_sparkline",
        bindings={
            "metric": {"field_guid": "metric-guid", "label": "Synthetic revenue", "unit": "currency"},
            "date": {"field_guid": "date-guid", "label": "Day"},
            "comparison": {"method": "previous_period", "label": "vs previous period"},
        },
        presentation={"visible_title": {"text": "Synthetic revenue", "owner": "body"}},
        output_dir=tmp_path,
    )
    assert result["ok"] is True
    contract = result["summary"]["visual_contract"]
    assert contract["visible_title"] == {"text": "Synthetic revenue", "owner": "body", "visible": True}
    assert contract["object_name"]["value"] == "Synthetic revenue"
    assert contract["hint"]["enabled"] is True
    assert contract["tooltip"]["comparison"]["absolute_delta"] is True
    assert contract["kpi"]["sparkline"] is True
    assert contract["states_theme"]["states"] == ["loading", "error", "no_data", "business_zero"]
    assert "renderer.js" in result["files"]
    renderer = Path(result["files"]["renderer.js"])
    assert renderer.read_text(encoding="utf-8") == result["draft"]["tabs"]["prepare.js"]
    assert "Synthetic revenue" not in renderer.read_text(encoding="utf-8")


def test_recipe_bindings_change_config_not_canonical_renderer() -> None:
    first = compile_recipe(
        "comparison_matrix",
        bindings={"rows": [{"field_guid": "row-a", "label": "A"}], "metric": {"field_guid": "m-a", "label": "Metric A"}},
    )
    second = compile_recipe(
        "comparison_matrix",
        bindings={"rows": [{"field_guid": "row-b", "label": "B"}], "metric": {"field_guid": "m-b", "label": "Metric B"}},
    )
    assert first["draft"]["tabs"]["prepare.js"] == second["draft"]["tabs"]["prepare.js"]
    assert first["draft"]["config"] != second["draft"]["config"]
    assert first["summary"]["visual_contract"]["legend"]["mode"] == "fixed_semantic"


def test_selector_recipe_has_parameter_and_consumer_contract() -> None:
    result = compile_recipe(
        "selector",
        bindings={
            "parameter": {"name": "region", "type": "string", "default": "all"},
            "consumers": ["chart-a", "chart-b"],
        },
    )
    selector = result["summary"]["visual_contract"]["selector"]
    assert selector["param_name"] == "region"
    assert selector["consumers"] == ["chart-a", "chart-b"]
    assert selector["reset"] is False


def test_editor_variants_have_distinct_required_tabs_and_runtime_limits() -> None:
    variants = {
        "table_node": {"meta.json": "{}", "params.js": "module.exports = {};", "sources.js": "module.exports = {};", "prepare.js": "module.exports = {};", "config.js": "module.exports = {};"},
        "d3_node": {"meta.json": "{}", "params.js": "module.exports = {};", "sources.js": "module.exports = {};", "prepare.js": "module.exports = {};", "controls.js": "module.exports = {};"},
        "advanced-chart_node": {"meta.json": "{}", "params.js": "module.exports = {};", "sources.js": "module.exports = {};", "prepare.js": "module.exports = {};", "controls.js": "module.exports = {};"},
        "markdown_node": {"meta.json": "{}", "params.js": "module.exports = {};", "prepare.js": "module.exports = {};"},
        "control_node": {"meta.json": "{}", "params.js": "module.exports = {};", "controls.js": "module.exports = {};"},
    }
    for variant, tabs in variants.items():
        result = validate_editor_draft({"variant": variant, "tabs": tabs, "source_aliases": []})
        assert result["ok"] is True, (variant, result)
        assert result["runtime"]["live_result_checked"] is False
    assert validate_editor_draft({"variant": "table_node", "tabs": {"prepare.js": "module.exports = {};"}})["ok"] is False


def test_editor_validation_rejects_node_sql_lib_and_duplicate_aliases() -> None:
    result = validate_editor_draft(
        {
            "variant": "advanced-chart_node",
            "tabs": {
                "meta.json": "{}",
                "params.js": "module.exports = {};",
                "sources.js": "const q = require('libs/sql/v1');",
                "prepare.js": "module.exports = {};",
                "controls.js": "module.exports = {};",
            },
            "source_aliases": ["source", "source"],
        }
    )
    codes = {issue["code"] for issue in result["issues"]}
    assert {"unsupported_sql_library", "source_alias_duplicate"}.issubset(codes)


def test_public_python_and_mcp_use_same_authoring_function() -> None:
    assert public_compile_recipe is compile_recipe
    schemas = {tool["name"]: tool for tool in list_tools()}
    assert schemas["dl_authoring_defaults"]["annotations"]["readOnlyHint"] is True
    assert schemas["dl_compile_recipe"]["inputSchema"]["required"] == ["recipe_id", "bindings"]
    assert schemas["dl_editor_validate"]["annotations"]["readOnlyHint"] is True
