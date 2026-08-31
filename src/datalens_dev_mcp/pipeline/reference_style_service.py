from __future__ import annotations

from pathlib import Path
from typing import Any

from datalens_dev_mcp.editor.protected_regions import build_protected_regions
from datalens_dev_mcp.editor.semantic_slots import discover_semantic_slots
from datalens_dev_mcp.editor.style_registry import select_style_profile
from datalens_dev_mcp.editor.style_scanner import TAB_ORDER, scan_portfolio_style_registry
from datalens_dev_mcp.pipeline.effective_visual_contract import resolve_effective_visual_contract
from datalens_dev_mcp.pipeline.project_decision_context import resolve_project_decision_context
from datalens_dev_mcp.pipeline.reference_binding import build_reference_binding
from datalens_dev_mcp.pipeline.style_binding_receipt import build_style_binding_receipt, style_binding_hash
from datalens_dev_mcp.pipeline.target_discovery import parse_target_url
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


class ReferenceStyleService:
    def bind(
        self,
        contract: dict[str, Any],
        *,
        target_graph: dict[str, Any],
        baselines: dict[str, dict[str, Any]],
        reference_target_graph: dict[str, Any] | None = None,
        reference_baselines: dict[str, dict[str, Any]] | None = None,
        portfolio_root: str = "",
    ) -> dict[str, Any]:
        reference = contract.get("reference") or {}
        locator = str(reference.get("locator") or "")
        exact_required = bool(reference.get("required_exact_style"))
        if locator and str(reference.get("kind") or "") in {"portfolio_object", "portfolio_path", "local_path"}:
            result = self._bind_portfolio(
                contract,
                locator=locator,
                portfolio_root=portfolio_root,
                exact_required=exact_required,
            )
        else:
            result = self._bind_live_target(
                locator=locator,
                exact_required=exact_required,
                target_graph=(reference_target_graph or target_graph) if locator else target_graph,
                baselines=(reference_baselines or baselines) if locator else baselines,
            )
        compatible = _assert_technology_compatibility(
            result,
            target_graph=target_graph,
            exact_required=exact_required,
        )
        if compatible.get("status") != "success":
            return compatible
        decision_context = resolve_project_decision_context(contract, target_graph=target_graph)
        if decision_context.get("status") == "blocked":
            return {
                "status": "blocked",
                "reason": str(decision_context.get("reason") or "project decision context is invalid"),
            }
        style_binding = dict(compatible["style_binding"])
        style_binding["protected_regions"] = list(compatible.get("protected_regions") or [])
        style_binding["semantic_slots"] = list(compatible.get("semantic_slots") or [])
        if decision_context.get("status") == "success":
            style_binding.update(
                {
                    "decision_context_hash": str(decision_context.get("context_hash") or ""),
                    "project_profile_hash": str(decision_context.get("project_profile_hash") or ""),
                    "accepted_exemplar_hash": str(decision_context.get("accepted_exemplar_hash") or ""),
                    "decision_context": {
                        key: value
                        for key, value in decision_context.items()
                        if key != "status"
                    },
                }
            )
            compatible["decision_context"] = {
                key: value for key, value in decision_context.items() if key != "status"
            }
        effective = resolve_effective_visual_contract(
            contract,
            target_graph=target_graph,
            baselines=baselines,
            style_binding=style_binding,
            decision_context=(
                {key: value for key, value in decision_context.items() if key != "status"}
                if decision_context.get("status") == "success"
                else {}
            ),
        )
        if effective.get("status") != "success":
            return {
                "status": "blocked",
                "reason": str(effective.get("reason") or "effective visual contract is invalid"),
                "conflicts": list(effective.get("conflicts") or []),
            }
        public_effective = {key: value for key, value in effective.items() if key != "status"}
        style_binding["effective_visual_contract_hash"] = str(effective.get("contract_hash") or "")
        style_binding["effective_visual_contract"] = public_effective
        style_binding.pop("binding_hash", None)
        style_binding["binding_hash"] = style_binding_hash(style_binding)
        compatible["style_binding"] = style_binding
        compatible["effective_visual_contract"] = public_effective
        return compatible

    def _bind_portfolio(
        self,
        contract: dict[str, Any],
        *,
        locator: str,
        portfolio_root: str,
        exact_required: bool,
    ) -> dict[str, Any]:
        workspace = contract.get("workspace") or {}
        allowed = Path(portfolio_root or str(workspace.get("project_root") or ".")).resolve()
        source = Path(locator).expanduser().resolve()
        if source != allowed and allowed not in source.parents:
            return {
                "status": "blocked",
                "reason": "reference path is outside the explicitly allowed portfolio workspace",
            }
        scan_root = source if source.is_dir() else source.parent
        registry = scan_portfolio_style_registry(scan_root, max_profiles=64)
        selection = select_style_profile(
            registry,
            {
                "explicit_reference_path": str(source),
                "existing_object_path": str(source),
                "cookbook_available": not exact_required,
            },
        )
        profile = selection.get("profile")
        if not profile:
            return {
                "status": "blocked",
                "reason": "exact portfolio style reference was not found" if exact_required else "portfolio style unavailable",
            }
        tabs = _read_profile_tabs(profile)
        return _binding_result(
            source_kind="portfolio_path",
            locator_hash=canonical_hash({"relative": (profile.get("source") or {}).get("relative_path")}),
            object_id="",
            revision=str((profile.get("source") or {}).get("commit_sha") or ""),
            source_hash=str((profile.get("source") or {}).get("source_hash") or ""),
            technology=str(profile.get("technology") or ""),
            exact_required=exact_required,
            tabs=tabs,
            protected_regions=list(profile.get("protected_regions") or []),
            semantic_slots=list(profile.get("semantic_slots") or []),
        )

    def _bind_live_target(
        self,
        *,
        locator: str,
        exact_required: bool,
        target_graph: dict[str, Any],
        baselines: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        nodes = [item for item in target_graph.get("nodes") or [] if isinstance(item, dict)]
        target_id = parse_target_url(locator) or locator or next(
            (str(item.get("object_id") or "") for item in nodes if "chart" in str(item.get("object_type") or "")),
            str((target_graph.get("root_ids") or [""])[0]),
        )
        node = next((item for item in nodes if str(item.get("object_id") or "") == target_id), None)
        if node is None:
            if exact_required:
                return {"status": "blocked", "reason": "exact live reference is not in the fresh target graph"}
            node = nodes[0] if nodes else {}
        baseline = next(
            (value for key, value in baselines.items() if str(node.get("object_id") or "") in key),
            {},
        )
        tabs = _extract_tabs(baseline)
        technology = str(node.get("technology") or "")
        source_hash = str(node.get("payload_hash") or canonical_hash(baseline))
        if exact_required and not source_hash:
            return {"status": "blocked", "reason": "exact live reference has no fresh source hash"}
        return _binding_result(
            source_kind="live_object" if locator else "live_target",
            locator_hash=canonical_hash({"object_id": str(node.get("object_id") or "")}),
            object_id=str(node.get("object_id") or ""),
            revision=str(node.get("saved_revision") or ""),
            source_hash=source_hash,
            technology=technology,
            exact_required=exact_required,
            tabs=tabs,
            protected_regions=build_protected_regions(tabs) if tabs else [],
            semantic_slots=discover_semantic_slots(tabs) if tabs else [],
        )


def _binding_result(
    *,
    source_kind: str,
    locator_hash: str,
    object_id: str,
    revision: str,
    source_hash: str,
    technology: str,
    exact_required: bool,
    tabs: dict[str, str],
    protected_regions: list[dict[str, Any]],
    semantic_slots: list[dict[str, Any]],
) -> dict[str, Any]:
    reference = build_reference_binding(
        source_kind=source_kind,
        locator_hash=locator_hash,
        object_id=object_id,
        revision=revision,
        source_hash=source_hash,
        technology=technology,
        exact_required=exact_required,
    )
    order = [name for name in TAB_ORDER if name in tabs]
    style = build_style_binding_receipt(
        source_kind=source_kind,
        reference_binding_hash=str(reference["binding_hash"]),
        technology=technology,
        tab_order=order,
        tab_hashes={name: canonical_hash(tabs[name]) for name in order},
        protected_regions=protected_regions,
        semantic_slots=semantic_slots,
        source_hash=source_hash,
    )
    return {
        "status": "success",
        "reference_binding": reference,
        "style_binding": style,
        "protected_regions": protected_regions,
        "semantic_slots": semantic_slots,
    }


def _extract_tabs(value: Any) -> dict[str, str]:
    found: dict[str, str] = {}
    aliases = {
        "meta": "meta.json",
        "params": "params.js",
        "sources": "sources.js",
        "controls": "controls.js",
        "prepare": "prepare.js",
        "config": "config.js",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            name = aliases.get(key, key if key in TAB_ORDER else "")
            if name and isinstance(item, str):
                found[name] = item
            else:
                found.update(_extract_tabs(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_extract_tabs(item))
    return found


def _read_profile_tabs(profile: dict[str, Any]) -> dict[str, str]:
    source = Path(str((profile.get("source") or {}).get("absolute_path") or "")).resolve()
    return {name: (source / name).read_text(encoding="utf-8") for name in TAB_ORDER if (source / name).is_file()}


def _assert_technology_compatibility(
    result: dict[str, Any],
    *,
    target_graph: dict[str, Any],
    exact_required: bool,
) -> dict[str, Any]:
    if result.get("status") != "success" or not exact_required:
        return result
    reference_technology = str((result.get("style_binding") or {}).get("technology") or "")
    target_technologies = {
        str(item.get("technology") or "")
        for item in target_graph.get("nodes") or []
        if isinstance(item, dict)
        and "chart" in str(item.get("object_type") or "")
        and str(item.get("technology") or "") not in {"", "mixed"}
    }
    if target_technologies and reference_technology and reference_technology not in target_technologies:
        return {
            "status": "blocked",
            "reason": (
                "exact reference technology does not match the fresh target technology: "
                f"{reference_technology} vs {','.join(sorted(target_technologies))}"
            ),
        }
    return result
