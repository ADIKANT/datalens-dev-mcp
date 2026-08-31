from __future__ import annotations

import hashlib
import json

from datalens_dev_mcp.pipeline.reference_style_service import ReferenceStyleService
from datalens_dev_mcp.pipeline.project_decision_context import validate_project_decision_context
from datalens_dev_mcp.pipeline.workflow_events import canonical_hash


def _write_project_context(tmp_path, *, workbook_id: str = "workbook_alpha") -> dict:
    profile = {
        "accepted_layout": ["comparison, source, methodology"],
        "selector_semantics": "empty arrays mean all values",
        "title_hint_policy": "one visible title owner",
        "superseded_decisions": ["duplicated embedded title"],
    }
    exemplar = {
        "exemplar_id": "SYNTHETIC-ALPHA-COMPARISON",
        "object_id": "chart_alpha",
        "visual_family": "comparison_matrix",
        "accepted_revision": "revision_alpha_1",
        "adaptation_rule": "replace every source-specific field",
    }
    descriptor = {
        "schema_id": "datalens_project_decision_context",
        "context_version": 1,
        "project_id": "synthetic_alpha",
        "match": {"workbook_ids": [workbook_id], "dashboard_ids": ["dashboard_alpha"]},
        "profile": profile,
        "accepted_exemplars": [exemplar],
        "corrections": [
            {
                "decision_id": "CORRECTION-ONE-TITLE",
                "status": "active",
                "statement": "remove the duplicated embedded title",
                "source_sha256": "a" * 64,
            }
        ],
        "source_hashes": ["b" * 64],
    }
    descriptor_path = tmp_path / "decision-context.json"
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    descriptor_sha256 = hashlib.sha256(descriptor_path.read_bytes()).hexdigest()
    (tmp_path / ".datalens-mcp.json").write_text(
        json.dumps(
            {
                "project_name": "Synthetic Alpha",
                "workbook_id": workbook_id,
                "dashboard_ids": ["dashboard_alpha"],
                "decision_context": {
                    "descriptor_path": "decision-context.json",
                    "sha256": descriptor_sha256,
                },
            }
        ),
        encoding="utf-8",
    )
    return {"profile": profile, "exemplar": exemplar, "descriptor": descriptor}


def test_reference_style_binding_selects_hash_locked_project_profile_and_exemplar(tmp_path) -> None:
    expected = _write_project_context(tmp_path)
    contract = {
        "workspace": {"project_root": str(tmp_path)},
        "target": {"workbook_id": "workbook_alpha", "dashboard_id": "dashboard_alpha"},
        "reference": {"kind": "none", "locator": "", "required_exact_style": False},
    }
    target_graph = {
        "root_ids": ["dashboard_alpha"],
        "nodes": [
            {
                "object_id": "chart_alpha",
                "object_type": "editor_chart",
                "technology": "editor_advanced",
                "saved_revision": "revision_alpha_1",
                "payload_hash": "c" * 64,
            }
        ],
    }

    result = ReferenceStyleService().bind(
        contract,
        target_graph=target_graph,
        baselines={"chart_alpha": {"prepare": "module.exports = {};"}},
    )

    assert result["status"] == "success"
    assert result["decision_context"]["project_id"] == "synthetic_alpha"
    assert result["decision_context"]["project_profile_hash"] == canonical_hash(expected["profile"])
    assert result["decision_context"]["accepted_exemplar_hash"] == canonical_hash(expected["exemplar"])
    assert result["decision_context"]["bounded_decisions"] == {
        "accepted_layout": ["comparison, source, methodology"],
        "selector_semantics": "empty arrays mean all values",
        "title_hint_policy": "one visible title owner",
        "active_corrections": ["remove the duplicated embedded title"],
        "superseded_decisions": ["duplicated embedded title"],
    }
    assert result["style_binding"]["decision_context_hash"] == result["decision_context"]["context_hash"]


def test_project_decision_context_does_not_leak_to_another_workbook(tmp_path) -> None:
    _write_project_context(tmp_path, workbook_id="workbook_alpha")
    contract = {
        "workspace": {"project_root": str(tmp_path)},
        "target": {"workbook_id": "workbook_beta", "dashboard_id": "dashboard_beta"},
        "reference": {"kind": "none", "locator": "", "required_exact_style": False},
    }

    result = ReferenceStyleService().bind(
        contract,
        target_graph={
            "root_ids": ["dashboard_beta"],
            "nodes": [
                {
                    "object_id": "dashboard_beta",
                    "object_type": "dashboard",
                    "workbook_id": "workbook_beta",
                    "technology": "dashboard",
                    "saved_revision": "revision_beta_1",
                    "payload_hash": "d" * 64,
                }
            ],
        },
        baselines={"dashboard_beta": {"tabs": []}},
    )

    assert result == {
        "status": "blocked",
        "reason": "decision_context target does not match the current project target",
    }


def test_v2_active_decision_requires_typed_final_state_provenance() -> None:
    descriptor = {
        "schema_id": "datalens_project_decision_context",
        "context_version": 2,
        "project_id": "synthetic_alpha",
        "match": {"workbook_ids": ["workbook_alpha"]},
        "profile": {"legend": {"show": False}, "advanced_editor": {"protected_regions": []}},
        "decisions": [
            {
                "decision_id": "legend-hidden",
                "category": "legend",
                "scope": "project",
                "status": "active",
                "applies_to": {"object_types": ["editor_chart"], "visualization_families": [], "object_ids": []},
                "statement": "Hide the legend for this chart family.",
                "typed_value": {"show": False},
                "source_refs": ["datalens://source/legend-review"],
                "final_state_refs": [],
                "supersedes": [],
            }
        ],
    }

    assert validate_project_decision_context(descriptor) == (
        "decisions[0].final_state_refs is required for an active decision",
    )
