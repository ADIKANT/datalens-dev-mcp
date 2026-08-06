import copy
import unittest
from unittest.mock import patch

from datalens_dev_mcp.editor import render_contract as render_contract_module
from datalens_dev_mcp.editor.render_contract import (
    DashboardRenderContractError,
    canonical_sha256,
    load_dashboard_render_profiles,
    resolve_dashboard_render_contract,
    upgrade_renderer_visual_spec_v5,
    validate_renderer_visual_spec_v5,
)
from datalens_dev_mcp.editor.title_contract import normalize_title_contract


PROFILE_ID = "standard_dashboard_v1"


def _plain(value):
    if hasattr(value, "items"):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _title_contract(*, family: str) -> dict:
    contract = normalize_title_contract(
        route="editor_advanced",
        family=family,
        display_title="Synthetic title",
        title_mode="embedded_title",
    )
    assert contract["ok"]
    return contract


class DashboardRenderContractTests(unittest.TestCase):
    def test_packaged_profile_hashes_are_deterministic_and_result_is_immutable(self):
        registry = load_dashboard_render_profiles()
        profile = registry["profiles"][PROFILE_ID]
        profile_without_hash = {
            key: value for key, value in profile.items() if key != "sha256"
        }
        registry_without_hash = {
            key: value for key, value in registry.items() if key != "sha256"
        }

        self.assertEqual(profile["sha256"], canonical_sha256(profile_without_hash))
        self.assertEqual(registry["sha256"], canonical_sha256(registry_without_hash))
        self.assertEqual(profile["registered_family_count"], 39)

        first = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="line_chart",
        )
        second = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="line_chart",
        )
        self.assertEqual(first["composite_sha256"], second["composite_sha256"])
        with self.assertRaises(TypeError):
            first["family"] = "pie"
        with self.assertRaises(TypeError):
            first["effective_tokens"]["kpi"]["surface"]["radius_px"] = 6

    def test_registry_and_profile_fingerprints_fail_closed_on_token_drift(self):
        tampered = _plain(load_dashboard_render_profiles())
        tampered["profiles"][PROFILE_ID]["core"]["kpi"]["surface"]["radius_px"] = 4
        load_dashboard_render_profiles.cache_clear()
        try:
            with patch.object(
                render_contract_module,
                "resource_json",
                return_value=tampered,
            ):
                with self.assertRaises(DashboardRenderContractError) as error:
                    load_dashboard_render_profiles()
            self.assertEqual(
                error.exception.category,
                "dashboard_render_profile_registry_hash_mismatch",
            )
        finally:
            load_dashboard_render_profiles.cache_clear()

    def test_unknown_profile_family_adapter_and_implicit_fallback_are_rejected(self):
        with self.assertRaises(DashboardRenderContractError) as profile_error:
            resolve_dashboard_render_contract(
                profile_id="unregistered_profile",
                family="line_chart",
            )
        self.assertEqual(
            profile_error.exception.category,
            "unknown_dashboard_render_profile",
        )

        with self.assertRaises(DashboardRenderContractError) as family_error:
            resolve_dashboard_render_contract(
                profile_id=PROFILE_ID,
                family="unregistered_family",
            )
        self.assertEqual(family_error.exception.category, "unregistered_render_family")
        self.assertIn("implicit generic fallback is forbidden", str(family_error.exception))

        corrupt_registry = _plain(load_dashboard_render_profiles())
        corrupt_registry["profiles"][PROFILE_ID]["family_map"]["line_chart"][
            "adapter"
        ] = "missing_adapter"
        with patch.object(
            render_contract_module,
            "load_dashboard_render_profiles",
            return_value=corrupt_registry,
        ):
            with self.assertRaises(DashboardRenderContractError) as adapter_error:
                resolve_dashboard_render_contract(
                    profile_id=PROFILE_ID,
                    family="line_chart",
                )
        self.assertEqual(adapter_error.exception.category, "unknown_render_adapter")

    def test_overrides_are_bounded_and_adapter_capabilities_are_enforced(self):
        with self.assertRaises(DashboardRenderContractError) as unknown:
            resolve_dashboard_render_contract(
                profile_id=PROFILE_ID,
                family="line_chart",
                overrides={"padding_px": 99},
            )
        self.assertEqual(unknown.exception.category, "unknown_render_override")

        with self.assertRaises(DashboardRenderContractError) as invalid:
            resolve_dashboard_render_contract(
                profile_id=PROFILE_ID,
                family="line_chart",
                overrides={"density": "dense"},
            )
        self.assertEqual(invalid.exception.category, "invalid_render_override_value")

        with self.assertRaises(DashboardRenderContractError) as not_applicable:
            resolve_dashboard_render_contract(
                profile_id=PROFILE_ID,
                family="line_chart",
                overrides={"horizontal_adapter": "scroll"},
            )
        self.assertEqual(
            not_applicable.exception.category,
            "render_override_not_applicable",
        )

        with self.assertRaises(DashboardRenderContractError) as owner_error:
            resolve_dashboard_render_contract(
                profile_id=PROFILE_ID,
                family="horizontal_bar",
                overrides={"tooltip_owner": "renderer"},
            )
        self.assertEqual(
            owner_error.exception.category,
            "invalid_render_override_value",
        )

        accepted = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="horizontal_bar",
            overrides={
                "density": "compact",
                "legend_typography": "readable",
                "horizontal_adapter": "scroll",
                "tooltip_owner": "native",
            },
        )
        self.assertEqual(accepted["adapter_ids"], ("horizontal_rank_scroll_v1",))
        self.assertEqual(accepted["effective_tokens"]["density"]["mode"], "compact")
        self.assertEqual(
            accepted["effective_tokens"]["typography"]["legend"]["active"],
            {"font_size_px": 14, "line_height_px": 18},
        )
        self.assertEqual(accepted["effective_tokens"]["tooltip"]["owner"], "native")

        registry = load_dashboard_render_profiles()
        profile = registry["profiles"][PROFILE_ID]
        self.assertEqual(profile["override_contract"]["tooltip_owner"], ("native",))
        for adapter_id, adapter in profile["adapters"].items():
            with self.subTest(adapter_id=adapter_id):
                self.assertEqual(adapter["allowed_tooltip_owners"], ("native",))

    def test_v5_upgrade_enforces_kpi_legend_tooltip_selector_and_comparison_invariants(self):
        contract = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="horizontal_bar",
            overrides={"tooltip_owner": "native"},
        )
        title_contract = _title_contract(family="horizontal_bar")
        upgraded = upgrade_renderer_visual_spec_v5(
            {
                "chart_purpose": "Rank categories",
                "legend": {
                    "show": True,
                    "font_size_px": 40,
                },
                "tooltip": {
                    "owners": ["native", "renderer"],
                    "include_values": True,
                },
                "kpi_context": {
                    "surface": {
                        "background": "white",
                        "border": {"style": "solid", "width_px": 1},
                    }
                },
            },
            render_contract=contract,
            title_contract=title_contract,
            comparison_enabled=True,
        )

        self.assertEqual(
            validate_renderer_visual_spec_v5(
                upgraded,
                render_contract=contract,
                title_contract=title_contract,
            ),
            (),
        )
        self.assertEqual(upgraded["kpi_context"]["surface"]["background"], "transparent")
        self.assertEqual(
            upgraded["kpi_context"]["surface"]["border"],
            {"style": "none", "width_px": 0},
        )
        self.assertEqual(upgraded["kpi_context"]["surface"]["radius_px"], 0)
        self.assertEqual(
            upgraded["kpi_context"]["surface"]["outline"],
            {"style": "none", "width_px": 0},
        )
        self.assertEqual(upgraded["kpi_context"]["surface"]["shadow"], "none")
        self.assertEqual(
            upgraded["kpi_context"]["content"],
            {
                "value_marker": "kpi-value",
                "value_required": True,
                "value_must_be_visible": True,
            },
        )
        self.assertEqual(
            upgraded["kpi_context"]["layout"],
            {
                "update_policy": "preserve_fresh_saved_geometry",
                "equal_height_within_kpi_set": True,
                "runtime_policy": "content_visible_without_clipping",
            },
        )
        self.assertEqual(upgraded["legend"]["typography_token"], "legend.default")
        self.assertNotIn("font_size_px", upgraded["legend"])
        self.assertEqual(upgraded["tooltip"]["owner"], "native")
        self.assertNotIn("owners", upgraded["tooltip"])
        self.assertEqual(
            upgraded["tooltip"]["surface"]["outline"],
            {"style": "none", "width_px": 0},
        )
        self.assertEqual(upgraded["tooltip"]["surface"]["shadow"], "none")
        self.assertFalse(upgraded["tooltip"]["redundant_row_title"])
        self.assertEqual(upgraded["tooltip"]["comparison_mode"], "comparison")
        self.assertEqual(upgraded["tooltip"]["period_value_source"], "normalized")
        self.assertTrue(upgraded["tooltip"]["show_current_label"])
        self.assertTrue(upgraded["tooltip"]["show_vs_separator"])
        self.assertTrue(upgraded["tooltip"]["show_comparison_period"])
        self.assertFalse(upgraded["tooltip"]["allow_empty_comparison_period"])
        self.assertEqual(upgraded["selector_contract"]["update_mode"], "immediate")
        self.assertEqual(
            upgraded["selector_contract"]["control_max_width_percent"],
            94,
        )
        self.assertEqual(upgraded["selector_contract"]["row_height_px"], 44)
        self.assertEqual(
            upgraded["selector_contract"]["dashboard_grid_height_units"],
            2,
        )
        self.assertEqual(upgraded["selector_contract"]["label_placement"], "left")
        self.assertEqual(
            upgraded["selector_contract"]["blank_multiselect_semantics"],
            "all",
        )
        self.assertTrue(upgraded["selector_contract"]["period_first_if_present"])
        self.assertFalse(upgraded["selector_contract"]["single_row"])
        self.assertEqual(
            upgraded["selector_contract"]["row_target_width_percent"],
            94,
        )
        self.assertEqual(
            upgraded["selector_contract"]["row_width_tolerance_percent"],
            0,
        )
        self.assertEqual(upgraded["comparison_context"]["block_count"], 1)
        self.assertEqual(
            upgraded["comparison_context"]["render_mode"],
            "single_text_block",
        )
        self.assertEqual(
            upgraded["comparison_context"]["required_fields"],
            ["method", "selected_range", "comparison_range"],
        )
        self.assertFalse(
            upgraded["comparison_context"]["duplicate_chart_captions"]
        )
        self.assertEqual(upgraded["comparison_context"]["minimum_height_px"], 24)
        self.assertEqual(
            upgraded["comparison_context"]["dashboard_grid_height_units"],
            1,
        )
        self.assertEqual(
            upgraded["horizontal_rank"]["preferred_bar_width_px"],
            234,
        )
        self.assertEqual(
            upgraded["typography"]["axis"],
            {"font_size_px": 12, "line_height_px": 16},
        )
        self.assertEqual(
            upgraded["typography"]["table"],
            {"font_size_px": 12, "line_height_px": 17},
        )
        self.assertEqual(upgraded["semantic_colors"]["success"], "#6CBF84")

        broken = copy.deepcopy(upgraded)
        broken["kpi_context"]["surface"]["border"] = {
            "style": "solid",
            "width_px": 1,
        }
        broken["legend"]["font_size_px"] = 15
        broken["tooltip"]["owners"] = ["native", "renderer"]
        broken["tooltip"]["comparison_mode"] = "single_period"
        broken["tooltip"]["show_vs_separator"] = False
        broken["selector_contract"]["control_max_width_percent"] = 95
        broken["selector_contract"]["period_first_if_present"] = False
        broken["comparison_context"]["block_count"] = 2
        issues = validate_renderer_visual_spec_v5(
            broken,
            render_contract=contract,
            title_contract=title_contract,
        )

        self.assertIn("kpi.surface.border_must_be_none", issues)
        self.assertIn("legend.inline_typography_forbidden", issues)
        self.assertIn("tooltip.multiple_owner_fields_forbidden", issues)
        self.assertIn("tooltip.comparison_mode_mismatch", issues)
        self.assertIn(
            "tooltip.show_vs_separator_must_match_comparison_mode",
            issues,
        )
        self.assertIn("selector.control_max_width_must_not_exceed_94", issues)
        self.assertIn(
            "selector.period_first_if_present_profile_token_mismatch",
            issues,
        )
        self.assertIn("comparison_context.exactly_one_block_when_enabled", issues)

    def test_composite_hash_changes_with_adapter_and_bounded_override(self):
        generic = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="horizontal_bar",
        )
        scroll = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="horizontal_bar",
            overrides={"horizontal_adapter": "scroll"},
        )
        compact = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="horizontal_bar",
            overrides={"density": "compact"},
        )
        readable = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="horizontal_bar",
            overrides={"legend_typography": "readable"},
        )

        hashes = {
            generic["composite_sha256"],
            scroll["composite_sha256"],
            compact["composite_sha256"],
            readable["composite_sha256"],
        }
        self.assertEqual(len(hashes), 4)
        self.assertFalse(generic["effective_tokens"]["horizontal_rank"]["scroll"])
        self.assertTrue(scroll["effective_tokens"]["horizontal_rank"]["scroll"])

    def test_single_period_tooltip_removes_all_comparison_chrome(self):
        contract = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="line_chart",
        )
        title_contract = _title_contract(family="line_chart")
        upgraded = upgrade_renderer_visual_spec_v5(
            {
                "tooltip": {
                    "comparison_mode": "comparison",
                    "show_current_label": True,
                    "show_vs_separator": True,
                    "show_comparison_period": True,
                }
            },
            render_contract=contract,
            title_contract=title_contract,
            comparison_enabled=False,
        )

        self.assertEqual(upgraded["tooltip"]["comparison_mode"], "single_period")
        self.assertEqual(upgraded["tooltip"]["period_value_source"], "normalized")
        self.assertFalse(upgraded["tooltip"]["show_current_label"])
        self.assertFalse(upgraded["tooltip"]["show_vs_separator"])
        self.assertFalse(upgraded["tooltip"]["show_comparison_period"])
        self.assertFalse(upgraded["tooltip"]["allow_empty_comparison_period"])
        self.assertEqual(
            validate_renderer_visual_spec_v5(
                upgraded,
                render_contract=contract,
                title_contract=title_contract,
            ),
            (),
        )

    def test_typography_and_spacing_tokens_are_consistent_across_families(self):
        family_contracts = [
            resolve_dashboard_render_contract(profile_id=PROFILE_ID, family=family)
            for family in (
                "kpi_value_only",
                "line_chart",
                "horizontal_bar",
                "pie",
                "resource_schedule_exception",
                "table_node",
                "single_select_dropdown",
            )
        ]
        expected_typography = _plain(family_contracts[0]["effective_tokens"]["typography"])
        expected_shell = _plain(family_contracts[0]["effective_tokens"]["shell"])
        for contract in family_contracts[1:]:
            with self.subTest(family=contract["family"]):
                self.assertEqual(
                    _plain(contract["effective_tokens"]["typography"]),
                    expected_typography,
                )
                self.assertEqual(
                    _plain(contract["effective_tokens"]["shell"]),
                    expected_shell,
                )

        self.assertEqual(expected_typography["body"], {"font_size_px": 12, "line_height_px": 16})
        self.assertEqual(
            expected_typography["tooltip"],
            {"font_size_px": 12, "line_height_px": 16},
        )
        self.assertEqual(
            expected_typography["legend"]["active"],
            {"font_size_px": 12, "line_height_px": 16},
        )
        metric = resolve_dashboard_render_contract(
            profile_id=PROFILE_ID,
            family="kpi_value_only",
        )
        self.assertEqual(metric["effective_tokens"]["viewport"]["min_height_px"], 96)
        self.assertEqual(
            metric["effective_tokens"]["component"]["height_policy"],
            "shared_layout_grid",
        )
        self.assertEqual(
            _plain(metric["effective_tokens"]["kpi"]["layout"]),
            {
                "update_policy": "preserve_fresh_saved_geometry",
                "equal_height_within_kpi_set": True,
                "runtime_policy": "content_visible_without_clipping",
            },
        )
        self.assertEqual(
            _plain(metric["effective_tokens"]["layout_grid"]["native_height_units"]),
            {
                "title_creation_default": 2,
                "selector_creation_default": 2,
                "selector_two_row_default": 3,
                "comparison_context_minimum": 1,
                "comparison_context_maximum": 3,
                "kpi_creation_default": 8,
                "kpi_compact_default": 6,
            },
        )
        self.assertEqual(
            _plain(family_contracts[0]["effective_tokens"]["semantic_colors"]),
            {
                "primary": "#2B75E2",
                "success": "#6CBF84",
                "failure": "#E57373",
                "comparison": "#8A919C",
            },
        )


if __name__ == "__main__":
    unittest.main()
