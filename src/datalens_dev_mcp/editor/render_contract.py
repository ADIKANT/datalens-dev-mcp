from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from types import MappingProxyType
from typing import Any

from datalens_dev_mcp.runtime_resources import resource_json


DASHBOARD_RENDER_PROFILE_RESOURCE = "config/dashboard_render_profiles.json"
DASHBOARD_RENDER_PROFILE_SCHEMA_VERSION = "2026-07-29.dashboard_render_profiles.v2"
RENDERER_VISUAL_SPEC_V4 = "2026-07-28.renderer_visual_spec.v4"

_ALLOWED_OVERRIDE_VALUES = {
    "density": ("compact", "comfortable"),
    "legend_typography": ("compact", "readable"),
    "horizontal_adapter": ("generic", "scroll"),
    "tooltip_owner": ("native",),
}
_TOOLTIP_OWNERS = frozenset({"native"})
_INLINE_LEGEND_TYPOGRAPHY_KEYS = frozenset(
    {
        "font_family",
        "font_size",
        "font_size_px",
        "font_weight",
        "line_height",
        "line_height_px",
        "typography",
        "typography_tokens",
    }
)


class DashboardRenderContractError(ValueError):
    """A fail-closed render-profile or Renderer Visual Spec violation."""

    def __init__(self, category: str, message: str):
        self.category = category
        self.message = message
        super().__init__(f"{category}: {message}")

    def as_dict(self) -> dict[str, str]:
        return {"category": self.category, "message": self.message}


def canonical_sha256(value: Any) -> str:
    """Return a stable SHA-256 over the JSON-compatible representation."""

    canonical = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_contract_to_dict(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a mutable JSON-compatible copy for bundle persistence."""

    return _jsonable(value)


@lru_cache(maxsize=1)
def load_dashboard_render_profiles() -> Mapping[str, Any]:
    """Load and fingerprint-check the packaged render-profile registry."""

    raw = resource_json(DASHBOARD_RENDER_PROFILE_RESOURCE)
    _validate_registry(raw)
    return _freeze(raw)


def resolve_dashboard_render_contract(
    *,
    profile_id: str = "",
    family: str,
    overrides: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Resolve one registered family to an immutable, exact render contract."""

    registry = load_dashboard_render_profiles()
    selected_profile_id = str(profile_id or registry.get("default_profile_id") or "").strip()
    profiles = registry.get("profiles")
    if not isinstance(profiles, Mapping) or selected_profile_id not in profiles:
        available = ", ".join(sorted(str(value) for value in (profiles or {})))
        raise DashboardRenderContractError(
            "unknown_dashboard_render_profile",
            f"unknown profile {selected_profile_id!r}; registered profiles: {available}",
        )
    family_id = str(family or "").strip()
    profile = profiles[selected_profile_id]
    family_map = profile.get("family_map")
    if not isinstance(family_map, Mapping) or family_id not in family_map:
        raise DashboardRenderContractError(
            "unregistered_render_family",
            (
                f"family {family_id!r} is not explicitly registered in profile "
                f"{selected_profile_id!r}; implicit generic fallback is forbidden"
            ),
        )

    normalized_overrides = _validate_requested_overrides(profile, overrides)
    family_rule = family_map[family_id]
    adapter_id = str(family_rule.get("adapter") or "")
    if "horizontal_adapter" in normalized_overrides:
        if family_rule.get("horizontal_adapter_override") is not True:
            raise DashboardRenderContractError(
                "render_override_not_applicable",
                f"horizontal_adapter is not supported by family {family_id!r}",
            )
        horizontal_adapters = profile.get("horizontal_adapters")
        adapter_id = str(horizontal_adapters.get(normalized_overrides["horizontal_adapter"]) or "")

    adapters = profile.get("adapters")
    adapter = adapters.get(adapter_id) if isinstance(adapters, Mapping) else None
    if not isinstance(adapter, Mapping):
        raise DashboardRenderContractError(
            "unknown_render_adapter",
            f"family {family_id!r} resolved to unknown adapter {adapter_id!r}",
        )

    core = _thaw(profile["core"])
    resolved_adapter = _thaw(adapter)
    effective_tokens = _deep_merge(core, resolved_adapter.get("tokens") or {})
    _apply_density_override(effective_tokens, normalized_overrides.get("density"))
    _apply_legend_override(effective_tokens, normalized_overrides.get("legend_typography"))

    tooltip_owner = str(
        normalized_overrides.get("tooltip_owner")
        or _mapping_at(effective_tokens, "tooltip").get("owner")
        or ""
    )
    permitted_owners = {
        str(value) for value in (resolved_adapter.get("allowed_tooltip_owners") or [])
    }
    if tooltip_owner not in permitted_owners:
        raise DashboardRenderContractError(
            "tooltip_owner_not_permitted",
            (
                f"adapter {adapter_id!r} does not permit tooltip owner "
                f"{tooltip_owner!r}; permitted owners: {', '.join(sorted(permitted_owners))}"
            ),
        )
    _mapping_at(effective_tokens, "tooltip")["owner"] = tooltip_owner

    resolved = {
        "schema_version": DASHBOARD_RENDER_PROFILE_SCHEMA_VERSION,
        "profile_id": selected_profile_id,
        "profile_sha256": str(profile["sha256"]),
        "registry_sha256": str(registry["sha256"]),
        "family": family_id,
        "adapter_ids": [adapter_id],
        "core": core,
        "adapters": {adapter_id: resolved_adapter},
        "overrides": normalized_overrides,
        "effective_tokens": effective_tokens,
    }
    composite_payload = {
        "profile_id": selected_profile_id,
        "profile_sha256": resolved["profile_sha256"],
        "family": family_id,
        "adapter_ids": resolved["adapter_ids"],
        "overrides": normalized_overrides,
        "effective_tokens": effective_tokens,
    }
    resolved["composite_sha256"] = canonical_sha256(composite_payload)
    return _freeze(resolved)


def upgrade_renderer_visual_spec_v4(
    visual_spec: Mapping[str, Any] | None,
    *,
    render_contract: Mapping[str, Any],
    comparison_enabled: bool | None = None,
) -> dict[str, Any]:
    """Merge semantic fields with strict profile tokens and validate the v4 result."""

    _require_resolved_contract(render_contract)
    result = copy.deepcopy(_jsonable(visual_spec or {}))
    tokens = _jsonable(render_contract["effective_tokens"])
    if comparison_enabled is None:
        comparison_enabled = _comparison_is_enabled(result)
    comparison_enabled = bool(comparison_enabled)
    result["schema_version"] = RENDERER_VISUAL_SPEC_V4
    result["render_contract"] = {
        "profile_id": str(render_contract["profile_id"]),
        "profile_sha256": str(render_contract["profile_sha256"]),
        "family": str(render_contract["family"]),
        "adapter_ids": list(render_contract["adapter_ids"]),
        "overrides": _jsonable(render_contract["overrides"]),
        "composite_sha256": str(render_contract["composite_sha256"]),
    }

    density = _mapping_at(tokens, "density")
    typography = _mapping_at(tokens, "typography")
    shell = _mapping_at(tokens, "shell")
    viewport = _mapping_at(tokens, "viewport")
    result["scale_contract"] = {
        "viewport": copy.deepcopy(viewport),
        "density": copy.deepcopy(density),
    }
    result["typography"] = {
        "font_family": copy.deepcopy(typography.get("font_family") or []),
        "title": copy.deepcopy(typography.get("title") or {}),
        "body": copy.deepcopy(typography.get("body") or {}),
        "axis": copy.deepcopy(typography.get("axis") or {}),
        "legend": copy.deepcopy(typography.get("legend") or {}),
        "tooltip": copy.deepcopy(typography.get("tooltip") or {}),
        "table": copy.deepcopy(typography.get("table") or {}),
    }
    result["spacing"] = {
        "shell_padding_px": copy.deepcopy(shell.get("padding_px") or {}),
        "shell_gap_px": copy.deepcopy(shell.get("gap_px") or {}),
        "plot_area": copy.deepcopy(_mapping_at(tokens, "plot_area")),
    }
    result["layout_grid"] = copy.deepcopy(_mapping_at(tokens, "layout_grid"))
    result["series_visibility"] = copy.deepcopy(
        _mapping_at(tokens, "series_visibility")
    )
    result["semantic_colors"] = copy.deepcopy(
        _mapping_at(tokens, "semantic_colors")
    )
    result["number_format"] = copy.deepcopy(_mapping_at(tokens, "number_format"))
    result["component_contract"] = copy.deepcopy(
        _mapping_at(tokens, "component")
    )
    horizontal_rank = _mapping_at(tokens, "horizontal_rank")
    if horizontal_rank:
        result["horizontal_rank"] = copy.deepcopy(horizontal_rank)
    else:
        result.pop("horizontal_rank", None)

    kpi_context = _dict_at(result, "kpi_context")
    kpi = _mapping_at(tokens, "kpi")
    kpi_context["surface"] = copy.deepcopy(kpi.get("surface") or {})
    kpi_context["padding_px"] = copy.deepcopy(kpi.get("padding_px") or {})
    kpi_context["label_typography"] = copy.deepcopy(kpi.get("label_typography") or {})
    kpi_context["value_typography"] = copy.deepcopy(kpi.get("value_typography") or {})
    kpi_context["content"] = copy.deepcopy(kpi.get("content") or {})
    kpi_context["layout"] = copy.deepcopy(kpi.get("layout") or {})
    kpi_context["sparkline_policy"] = str(kpi.get("sparkline_policy") or "")

    legend = _dict_at(result, "legend")
    for key in _INLINE_LEGEND_TYPOGRAPHY_KEYS:
        legend.pop(key, None)
    legend_tokens = _mapping_at(typography, "legend")
    legend["typography_token"] = str(legend_tokens.get("active_token") or "")
    legend["single_typography_token"] = True

    tooltip = _dict_at(result, "tooltip")
    tooltip_tokens = _mapping_at(tokens, "tooltip")
    tooltip.pop("owners", None)
    tooltip.pop("native_owner", None)
    tooltip.pop("renderer_owner", None)
    tooltip["owner"] = str(tooltip_tokens.get("owner") or "")
    tooltip["single_owner"] = True
    tooltip["max_width_px"] = int(tooltip_tokens.get("max_width_px") or 0)
    tooltip["padding_px"] = copy.deepcopy(tooltip_tokens.get("padding_px") or {})
    tooltip["surface"] = copy.deepcopy(tooltip_tokens.get("surface") or {})
    tooltip["redundant_row_title"] = bool(
        tooltip_tokens.get("redundant_row_title")
    )
    tooltip["comparison_mode"] = (
        "comparison" if comparison_enabled else "single_period"
    )
    tooltip["period_value_source"] = str(
        tooltip_tokens.get("period_value_source") or ""
    )
    tooltip["show_current_label"] = comparison_enabled
    tooltip["show_vs_separator"] = comparison_enabled
    tooltip["show_comparison_period"] = comparison_enabled
    tooltip["allow_empty_comparison_period"] = False

    selector_contract = _dict_at(result, "selector_contract")
    selector = _mapping_at(tokens, "selector")
    selector_contract["update_mode"] = str(selector.get("update_mode") or "")
    selector_contract["apply_button"] = bool(selector.get("apply_button"))
    selector_contract["control_max_width_percent"] = int(
        selector.get("control_max_width_percent") or 0
    )
    selector_contract["row_height_px"] = int(selector.get("row_height_px") or 0)
    native_heights = _mapping_at(_mapping_at(tokens, "layout_grid"), "native_height_units")
    selector_contract["dashboard_grid_height_units"] = int(
        native_heights.get("selector_creation_default") or 0
    )
    selector_contract["label_placement"] = str(
        selector.get("label_placement") or ""
    )
    selector_contract["blank_multiselect_semantics"] = str(
        selector.get("blank_multiselect_semantics") or ""
    )
    selector_contract["period_first_if_present"] = bool(
        selector.get("period_first_if_present")
    )
    selector_contract["single_row"] = bool(selector.get("single_row"))
    selector_contract["row_target_width_percent"] = int(
        selector.get("row_target_width_percent") or 0
    )
    selector_contract["row_width_tolerance_percent"] = int(
        selector.get("row_width_tolerance_percent") or 0
    )

    comparison = _dict_at(result, "comparison_context")
    comparison["enabled"] = comparison_enabled
    comparison["block_count"] = 1 if comparison_enabled else 0
    comparison["render_mode"] = "single_text_block" if comparison_enabled else "none"
    comparison["placement"] = str(
        _mapping_at(tokens, "comparison_context").get("placement") or ""
    )
    comparison["single_shared_summary"] = True
    comparison_tokens = _mapping_at(tokens, "comparison_context")
    comparison["required_fields"] = copy.deepcopy(
        comparison_tokens.get("required_fields") or []
    )
    comparison["duplicate_chart_captions"] = bool(
        comparison_tokens.get("duplicate_chart_captions")
    )
    comparison["minimum_height_px"] = int(
        comparison_tokens.get("minimum_height_px") or 0
    )
    comparison["dashboard_grid_height_units"] = int(
        native_heights.get("comparison_context_minimum") or 0
    )
    comparison["semantic_line_count"] = int(
        comparison_tokens.get("semantic_line_count") or 0
    )

    issues = validate_renderer_visual_spec_v4(result, render_contract=render_contract)
    if issues:
        raise DashboardRenderContractError(
            "invalid_renderer_visual_spec_v4",
            "; ".join(issues),
        )
    return result


def validate_renderer_visual_spec_v4(
    visual_spec: Mapping[str, Any],
    *,
    render_contract: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return stable issue codes for hard render-contract violations."""

    _require_resolved_contract(render_contract)
    spec = _jsonable(visual_spec)
    tokens = _jsonable(render_contract["effective_tokens"])
    issues: list[str] = []

    if spec.get("schema_version") != RENDERER_VISUAL_SPEC_V4:
        issues.append("schema_version.must_be_renderer_visual_spec_v4")

    binding = spec.get("render_contract") if isinstance(spec.get("render_contract"), dict) else {}
    expected_binding = {
        "profile_id": str(render_contract["profile_id"]),
        "profile_sha256": str(render_contract["profile_sha256"]),
        "family": str(render_contract["family"]),
        "adapter_ids": list(render_contract["adapter_ids"]),
        "overrides": _jsonable(render_contract["overrides"]),
        "composite_sha256": str(render_contract["composite_sha256"]),
    }
    if binding != expected_binding:
        issues.append("render_contract.binding_mismatch")

    expected_typography = _mapping_at(tokens, "typography")
    expected_scale = {
        "viewport": _mapping_at(tokens, "viewport"),
        "density": _mapping_at(tokens, "density"),
    }
    if spec.get("scale_contract") != expected_scale:
        issues.append("scale_contract.profile_token_mismatch")
    expected_typography_contract = {
        "font_family": expected_typography.get("font_family") or [],
        "title": expected_typography.get("title") or {},
        "body": expected_typography.get("body") or {},
        "axis": expected_typography.get("axis") or {},
        "legend": expected_typography.get("legend") or {},
        "tooltip": expected_typography.get("tooltip") or {},
        "table": expected_typography.get("table") or {},
    }
    if spec.get("typography") != expected_typography_contract:
        issues.append("typography.profile_token_mismatch")
    expected_shell = _mapping_at(tokens, "shell")
    expected_spacing = {
        "shell_padding_px": expected_shell.get("padding_px") or {},
        "shell_gap_px": expected_shell.get("gap_px") or {},
        "plot_area": _mapping_at(tokens, "plot_area"),
    }
    if spec.get("spacing") != expected_spacing:
        issues.append("spacing.profile_token_mismatch")
    if spec.get("layout_grid") != _mapping_at(tokens, "layout_grid"):
        issues.append("layout_grid.profile_token_mismatch")
    if spec.get("series_visibility") != _mapping_at(tokens, "series_visibility"):
        issues.append("series_visibility.profile_token_mismatch")
    if spec.get("semantic_colors") != _mapping_at(tokens, "semantic_colors"):
        issues.append("semantic_colors.profile_token_mismatch")
    if spec.get("number_format") != _mapping_at(tokens, "number_format"):
        issues.append("number_format.profile_token_mismatch")
    if spec.get("component_contract") != _mapping_at(tokens, "component"):
        issues.append("component_contract.profile_token_mismatch")
    expected_horizontal_rank = _mapping_at(tokens, "horizontal_rank")
    if expected_horizontal_rank:
        if spec.get("horizontal_rank") != expected_horizontal_rank:
            issues.append("horizontal_rank.profile_token_mismatch")
    elif "horizontal_rank" in spec:
        issues.append("horizontal_rank.not_applicable")

    kpi_context = spec.get("kpi_context") if isinstance(spec.get("kpi_context"), dict) else {}
    kpi_surface = (
        kpi_context.get("surface") if isinstance(kpi_context.get("surface"), dict) else {}
    )
    expected_kpi = _mapping_at(tokens, "kpi")
    if kpi_surface.get("background") != "transparent":
        issues.append("kpi.surface.background_must_be_transparent")
    if kpi_surface.get("border") != {"style": "none", "width_px": 0}:
        issues.append("kpi.surface.border_must_be_none")
    if kpi_surface.get("radius_px") != 0:
        issues.append("kpi.surface.radius_must_be_zero")
    if kpi_surface.get("outline") != {"style": "none", "width_px": 0}:
        issues.append("kpi.surface.outline_must_be_none")
    if kpi_surface.get("shadow") != "none":
        issues.append("kpi.surface.shadow_must_be_none")
    if kpi_surface != expected_kpi.get("surface"):
        issues.append("kpi.surface.profile_token_mismatch")
    if kpi_context.get("padding_px") != expected_kpi.get("padding_px"):
        issues.append("kpi.padding.profile_token_mismatch")
    if kpi_context.get("content") != expected_kpi.get("content"):
        issues.append("kpi.content.profile_token_mismatch")
    if kpi_context.get("layout") != expected_kpi.get("layout"):
        issues.append("kpi.layout.profile_token_mismatch")
    if kpi_context.get("sparkline_policy") != expected_kpi.get("sparkline_policy"):
        issues.append("kpi.sparkline_policy.profile_token_mismatch")

    legend = spec.get("legend") if isinstance(spec.get("legend"), dict) else {}
    legend_tokens = _mapping_at(_mapping_at(tokens, "typography"), "legend")
    if legend.get("typography_token") != legend_tokens.get("active_token"):
        issues.append("legend.typography_token_mismatch")
    if legend.get("single_typography_token") is not True:
        issues.append("legend.single_typography_token_required")
    if _INLINE_LEGEND_TYPOGRAPHY_KEYS.intersection(legend):
        issues.append("legend.inline_typography_forbidden")

    tooltip = spec.get("tooltip") if isinstance(spec.get("tooltip"), dict) else {}
    expected_tooltip = _mapping_at(tokens, "tooltip")
    if tooltip.get("owner") != expected_tooltip.get("owner"):
        issues.append("tooltip.owner_mismatch")
    if tooltip.get("single_owner") is not True:
        issues.append("tooltip.single_owner_required")
    if any(key in tooltip for key in ("owners", "native_owner", "renderer_owner")):
        issues.append("tooltip.multiple_owner_fields_forbidden")
    if tooltip.get("max_width_px") != expected_tooltip.get("max_width_px"):
        issues.append("tooltip.max_width_profile_token_mismatch")
    if tooltip.get("padding_px") != expected_tooltip.get("padding_px"):
        issues.append("tooltip.padding_profile_token_mismatch")
    if tooltip.get("surface") != expected_tooltip.get("surface"):
        issues.append("tooltip.surface_profile_token_mismatch")
    if tooltip.get("redundant_row_title") is not False:
        issues.append("tooltip.redundant_row_title_must_be_false")
    comparison = (
        spec.get("comparison_context")
        if isinstance(spec.get("comparison_context"), dict)
        else {}
    )
    comparison_enabled = comparison.get("enabled") is True
    expected_tooltip_mode = "comparison" if comparison_enabled else "single_period"
    if tooltip.get("comparison_mode") != expected_tooltip_mode:
        issues.append("tooltip.comparison_mode_mismatch")
    if tooltip.get("period_value_source") != expected_tooltip.get(
        "period_value_source"
    ):
        issues.append("tooltip.period_value_source_mismatch")
    for key in (
        "show_current_label",
        "show_vs_separator",
        "show_comparison_period",
    ):
        if tooltip.get(key) is not comparison_enabled:
            issues.append(f"tooltip.{key}_must_match_comparison_mode")
    if tooltip.get("allow_empty_comparison_period") is not False:
        issues.append("tooltip.empty_comparison_period_forbidden")

    selector = (
        spec.get("selector_contract")
        if isinstance(spec.get("selector_contract"), dict)
        else {}
    )
    expected_selector = _mapping_at(tokens, "selector")
    if selector.get("update_mode") != "immediate":
        issues.append("selector.update_mode_must_be_immediate")
    if selector.get("apply_button") is not False:
        issues.append("selector.apply_button_must_be_absent")
    selector_max_width = selector.get("control_max_width_percent")
    if (
        not isinstance(selector_max_width, int)
        or isinstance(selector_max_width, bool)
        or selector_max_width <= 0
        or selector_max_width > 94
    ):
        issues.append("selector.control_max_width_must_not_exceed_94")
    if selector_max_width != expected_selector.get("control_max_width_percent"):
        issues.append("selector.control_max_width_profile_token_mismatch")
    if selector.get("row_height_px") != expected_selector.get("row_height_px"):
        issues.append("selector.row_height_profile_token_mismatch")
    native_heights = _mapping_at(_mapping_at(tokens, "layout_grid"), "native_height_units")
    if (
        selector.get("dashboard_grid_height_units")
        != native_heights.get("selector_creation_default")
    ):
        issues.append("selector.grid_height_profile_token_mismatch")
    if selector.get("label_placement") != expected_selector.get("label_placement"):
        issues.append("selector.label_placement_profile_token_mismatch")
    if (
        selector.get("blank_multiselect_semantics")
        != expected_selector.get("blank_multiselect_semantics")
    ):
        issues.append("selector.blank_multiselect_profile_token_mismatch")
    for key in ("period_first_if_present", "single_row"):
        if selector.get(key) is not expected_selector.get(key):
            issues.append(f"selector.{key}_profile_token_mismatch")
    for key in ("row_target_width_percent", "row_width_tolerance_percent"):
        if selector.get(key) != expected_selector.get(key):
            issues.append(f"selector.{key}_profile_token_mismatch")

    expected_block_count = 1 if comparison_enabled else 0
    if comparison.get("block_count") != expected_block_count:
        issues.append("comparison_context.exactly_one_block_when_enabled")
    expected_render_mode = "single_text_block" if comparison_enabled else "none"
    if comparison.get("render_mode") != expected_render_mode:
        issues.append("comparison_context.render_mode_mismatch")
    if comparison.get("single_shared_summary") is not True:
        issues.append("comparison_context.single_shared_summary_required")
    expected_placement = _mapping_at(tokens, "comparison_context").get("placement")
    if comparison.get("placement") != expected_placement:
        issues.append("comparison_context.placement_profile_token_mismatch")
    expected_comparison = _mapping_at(tokens, "comparison_context")
    if comparison.get("required_fields") != expected_comparison.get("required_fields"):
        issues.append("comparison_context.required_fields_profile_token_mismatch")
    if comparison.get("duplicate_chart_captions") is not False:
        issues.append("comparison_context.duplicate_chart_captions_forbidden")
    for key in (
        "minimum_height_px",
        "semantic_line_count",
    ):
        if comparison.get(key) != expected_comparison.get(key):
            issues.append(f"comparison_context.{key}_profile_token_mismatch")
    if (
        comparison.get("dashboard_grid_height_units")
        != native_heights.get("comparison_context_minimum")
    ):
        issues.append("comparison_context.dashboard_grid_height_units_profile_token_mismatch")

    return tuple(dict.fromkeys(issues))


def assert_renderer_visual_spec_v4(
    visual_spec: Mapping[str, Any],
    *,
    render_contract: Mapping[str, Any],
) -> None:
    issues = validate_renderer_visual_spec_v4(
        visual_spec,
        render_contract=render_contract,
    )
    if issues:
        raise DashboardRenderContractError(
            "invalid_renderer_visual_spec_v4",
            "; ".join(issues),
        )


def _validate_registry(registry: Any) -> None:
    if not isinstance(registry, dict):
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile_registry",
            "registry must be a JSON object",
        )
    if registry.get("schema_version") != DASHBOARD_RENDER_PROFILE_SCHEMA_VERSION:
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile_registry",
            "unsupported registry schema_version",
        )
    expected_registry_sha256 = str(registry.get("sha256") or "").lower()
    actual_registry_sha256 = canonical_sha256(_without_key(registry, "sha256"))
    if not _is_sha256(expected_registry_sha256) or expected_registry_sha256 != actual_registry_sha256:
        raise DashboardRenderContractError(
            "dashboard_render_profile_registry_hash_mismatch",
            "registry canonical fingerprint changed; register a reviewed version",
        )

    profiles = registry.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile_registry",
            "profiles must be a non-empty object",
        )
    default_profile_id = str(registry.get("default_profile_id") or "")
    if default_profile_id not in profiles:
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile_registry",
            "default_profile_id must identify a registered profile",
        )
    for profile_id, profile in profiles.items():
        _validate_profile(str(profile_id), profile)


def _validate_profile(profile_id: str, profile: Any) -> None:
    if not isinstance(profile, dict):
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} must be an object",
        )
    expected_profile_sha256 = str(profile.get("sha256") or "").lower()
    actual_profile_sha256 = canonical_sha256(_without_key(profile, "sha256"))
    if not _is_sha256(expected_profile_sha256) or expected_profile_sha256 != actual_profile_sha256:
        raise DashboardRenderContractError(
            "dashboard_render_profile_hash_mismatch",
            f"profile {profile_id!r} canonical fingerprint changed; register a reviewed version",
        )

    core = profile.get("core")
    adapters = profile.get("adapters")
    family_map = profile.get("family_map")
    if not isinstance(core, dict) or not isinstance(adapters, dict) or not adapters:
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} requires core and non-empty adapters objects",
        )
    if not isinstance(family_map, dict) or not family_map or "*" in family_map:
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} requires explicit family registrations and forbids '*'",
        )
    if profile.get("fallback_policy") != "registered_families_only":
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} must block implicit generic fallback",
        )
    if profile.get("registered_family_count") != len(family_map):
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} registered_family_count does not match family_map",
        )

    for adapter_id, adapter in adapters.items():
        if not isinstance(adapter, dict):
            raise DashboardRenderContractError(
                "invalid_render_adapter",
                f"adapter {adapter_id!r} must be an object",
            )
        owners = adapter.get("allowed_tooltip_owners")
        if (
            not isinstance(owners, list)
            or not owners
            or any(str(value) not in _TOOLTIP_OWNERS for value in owners)
        ):
            raise DashboardRenderContractError(
                "invalid_render_adapter",
                f"adapter {adapter_id!r} has invalid allowed_tooltip_owners",
            )
        if not isinstance(adapter.get("tokens"), dict):
            raise DashboardRenderContractError(
                "invalid_render_adapter",
                f"adapter {adapter_id!r} requires a tokens object",
            )
    for family, rule in family_map.items():
        if not isinstance(rule, dict) or str(rule.get("adapter") or "") not in adapters:
            raise DashboardRenderContractError(
                "unknown_render_adapter",
                f"family {family!r} references an unknown adapter",
            )

    horizontal_adapters = profile.get("horizontal_adapters")
    if not isinstance(horizontal_adapters, dict):
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} requires horizontal_adapters",
        )
    for mode in _ALLOWED_OVERRIDE_VALUES["horizontal_adapter"]:
        if str(horizontal_adapters.get(mode) or "") not in adapters:
            raise DashboardRenderContractError(
                "unknown_render_adapter",
                f"horizontal mode {mode!r} references an unknown adapter",
            )

    override_contract = profile.get("override_contract")
    if not isinstance(override_contract, dict) or set(override_contract) != set(
        _ALLOWED_OVERRIDE_VALUES
    ):
        raise DashboardRenderContractError(
            "invalid_render_override_contract",
            f"profile {profile_id!r} must declare exactly the bounded override keys",
        )
    for key, values in _ALLOWED_OVERRIDE_VALUES.items():
        declared = override_contract.get(key)
        if not isinstance(declared, list) or tuple(str(value) for value in declared) != values:
            raise DashboardRenderContractError(
                "invalid_render_override_contract",
                f"profile {profile_id!r} has invalid values for override {key!r}",
            )

    default_tooltip_owner = str(_mapping_at(core, "tooltip").get("owner") or "")
    if default_tooltip_owner not in _TOOLTIP_OWNERS:
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} has an invalid default tooltip owner",
        )
    _validate_core_geometry(profile_id, core)


def _validate_core_geometry(profile_id: str, core: dict[str, Any]) -> None:
    grid = _mapping_at(core, "layout_grid")
    native_heights = _mapping_at(grid, "native_height_units")
    selector = _mapping_at(core, "selector")
    comparison = _mapping_at(core, "comparison_context")
    kpi = _mapping_at(core, "kpi")
    kpi_layout = _mapping_at(kpi, "layout")
    if native_heights != {
        "title_creation_default": 2,
        "selector_creation_default": 2,
        "comparison_context_minimum": 3,
        "kpi_creation_default": 6,
    }:
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} has invalid native dashboard height defaults",
        )
    if (
        grid.get("update_policy") != "preserve_fresh_saved_geometry"
        or grid.get("runtime_relation") != "measured_independently_from_native_units"
        or grid.get("equal_height_within_semantic_row") is not True
        or grid.get("overflow_policy") != "expand_or_scroll_never_clip"
        or selector.get("row_height_px") != 44
        or comparison.get("minimum_height_px") != 70
        or kpi_layout
        != {
            "update_policy": "preserve_fresh_saved_geometry",
            "equal_height_within_kpi_set": True,
            "runtime_policy": "content_visible_without_clipping",
        }
    ):
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} has inconsistent semantic object heights",
        )
    plot = _mapping_at(_mapping_at(core, "plot_area"), "inset_px")
    if plot != {
        "top": 22,
        "right": {"compact": 10, "normal": 16},
        "bottom": 34,
        "left": "family_axis_owned",
    }:
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} has inconsistent coordinate plot insets",
        )
    visibility = _mapping_at(core, "series_visibility")
    if any(
        visibility.get(key) != "active_series_only"
        for key in ("legend", "marks", "tooltip")
    ) or visibility.get("source") != "filtered_result_rows":
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"profile {profile_id!r} must bind legends and marks to filtered rows",
        )


def _validate_requested_overrides(
    profile: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> dict[str, str]:
    if overrides is None:
        return {}
    if not isinstance(overrides, Mapping):
        raise DashboardRenderContractError(
            "invalid_render_override",
            "overrides must be an object",
        )
    unknown = sorted(str(key) for key in overrides if key not in _ALLOWED_OVERRIDE_VALUES)
    if unknown:
        raise DashboardRenderContractError(
            "unknown_render_override",
            f"unknown override keys: {', '.join(unknown)}",
        )
    declared = profile.get("override_contract")
    normalized: dict[str, str] = {}
    for key, raw_value in overrides.items():
        value = str(raw_value or "").strip()
        allowed = tuple(str(item) for item in declared[key])
        if value not in allowed:
            raise DashboardRenderContractError(
                "invalid_render_override_value",
                f"override {key!r} must be one of: {', '.join(allowed)}",
            )
        normalized[str(key)] = value
    return normalized


def _apply_density_override(tokens: dict[str, Any], density_override: str | None) -> None:
    density = _mapping_at(tokens, "density")
    selected = density_override or "responsive"
    density["mode"] = selected
    if selected == "compact":
        density["active_variant"] = "compact"
    elif selected == "comfortable":
        density["active_variant"] = "normal"
    else:
        density["active_variant"] = "viewport"


def _apply_legend_override(tokens: dict[str, Any], legend_override: str | None) -> None:
    typography = _mapping_at(tokens, "typography")
    legend = _mapping_at(typography, "legend")
    selected = legend_override or "default"
    variant = legend.get(selected)
    if not isinstance(variant, dict):
        raise DashboardRenderContractError(
            "invalid_dashboard_render_profile",
            f"legend typography token {selected!r} is absent",
        )
    legend["active_token"] = f"legend.{selected}"
    legend["active"] = copy.deepcopy(variant)


def _comparison_is_enabled(spec: Mapping[str, Any]) -> bool:
    comparison = spec.get("comparison_context")
    if isinstance(comparison, Mapping) and isinstance(comparison.get("enabled"), bool):
        return bool(comparison["enabled"])
    kpi_context = spec.get("kpi_context")
    if isinstance(kpi_context, Mapping) and bool(kpi_context.get("comparator")):
        return True
    tooltip = spec.get("tooltip")
    return isinstance(tooltip, Mapping) and bool(tooltip.get("include_comparator"))


def _require_resolved_contract(render_contract: Mapping[str, Any]) -> None:
    required = {
        "profile_id",
        "profile_sha256",
        "family",
        "adapter_ids",
        "overrides",
        "effective_tokens",
        "composite_sha256",
    }
    if not isinstance(render_contract, Mapping) or not required.issubset(render_contract):
        raise DashboardRenderContractError(
            "invalid_resolved_render_contract",
            "render_contract is not a resolved dashboard render profile",
        )


def _dict_at(value: dict[str, Any], key: str) -> dict[str, Any]:
    current = value.get(key)
    if isinstance(current, dict):
        return current
    value[key] = {}
    return value[key]


def _mapping_at(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    current = value.get(key)
    if isinstance(current, dict):
        return current
    if isinstance(current, Mapping):
        converted = _thaw(current)
        if isinstance(value, dict):
            value[key] = converted
        return converted
    if isinstance(value, dict):
        value[key] = {}
        return value[key]
    return {}


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(_jsonable(value))
    return merged


def _without_key(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {str(item_key): item_value for item_key, item_value in value.items() if item_key != key}


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return copy.deepcopy(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
