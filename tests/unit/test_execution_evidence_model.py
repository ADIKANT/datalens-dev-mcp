from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from datalens_dev_mcp.pipeline.execution_evidence import (
    EvidenceModelError,
    build_execution_evidence_model,
    render_execution_evidence_views,
)


def _record(
    evidence_id: str,
    sequence: int,
    mode: str,
    status: str,
    *,
    observed_calls: list[dict] | None = None,
    planned_methods: list[str] | None = None,
    coverage_cells: list[dict] | None = None,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "sequence": sequence,
        "mode": mode,
        "status": status,
        "receipt_hash": f"{sequence:064x}",
        "observed_calls": observed_calls or [],
        "planned_methods": planned_methods or [],
        "coverage_cells": coverage_cells or [],
    }


def test_latest_green_probe_supersedes_stale_auth_pending_and_all_views_share_one_model() -> None:
    model = build_execution_evidence_model(
        goal={"revision": "rev4+rev4.1", "hash": "a" * 64},
        build={"tree_hash": "b" * 64, "package_hash": "c" * 64, "tool_surface_hash": "d" * 64},
        records=[
            _record("credential_probe", 1, "public_stdio_replay", "auth_pending"),
            _record(
                "credential_probe",
                2,
                "public_stdio_replay",
                "passed",
                observed_calls=[{"method": "getWorkbook", "effect": "read", "count": 1}],
            ),
            _record(
                "compiler_screen",
                1,
                "internal_compiler_screening",
                "passed",
                planned_methods=["getDashboard", "updateDashboard"],
                coverage_cells=[{"cell": "route_selection", "state": "screened"}],
            ),
            _record(
                "live_data_probe",
                1,
                "internal_controlled_live_runner",
                "passed",
                observed_calls=[{"method": "getDatasetData", "effect": "read", "count": 3}],
                coverage_cells=[{"cell": "data_context", "state": "live_verified"}],
            ),
            _record(
                "browser_direct_url",
                1,
                "browser_visual_attestation",
                "passed",
                coverage_cells=[{"cell": "direct_url_render", "state": "closed"}],
            ),
        ],
        obligations={"live": "partial", "activation": "pending", "cleanup": "pending"},
    )
    views = render_execution_evidence_views(model)

    credential_rows = [row for row in model["records"] if row["evidence_id"] == "credential_probe"]
    assert [row["freshness"] for row in credential_rows] == ["superseded", "current"]
    assert views["final_report"]["current_statuses"]["credential_probe"] == "passed"
    assert views["call_counts"]["provider_reads"] == 4
    assert views["call_counts"]["provider_writes"] == 0
    assert "updateDashboard" not in views["call_counts"]["observed_methods"]
    assert views["coverage_matrix"]["cells"] == [
        {"cell": "data_context", "mode": "internal_controlled_live_runner", "state": "live_verified"},
        {"cell": "direct_url_render", "mode": "browser_visual_attestation", "state": "closed"},
        {"cell": "route_selection", "mode": "internal_compiler_screening", "state": "screened"},
    ]
    assert len({view["evidence_model_hash"] for view in views.values()}) == 1
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "schemas" / "execution-evidence-model.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert not list(Draft202012Validator(schema).iter_errors(model))


def test_same_sequence_contradiction_is_a_hard_failure() -> None:
    with pytest.raises(EvidenceModelError, match="contradictory evidence records"):
        build_execution_evidence_model(
            goal={"revision": "rev4+rev4.1", "hash": "a" * 64},
            build={"tree_hash": "b" * 64, "package_hash": "c" * 64, "tool_surface_hash": "d" * 64},
            records=[
                _record("same_receipt", 1, "public_stdio_replay", "passed"),
                _record("same_receipt", 1, "public_stdio_replay", "auth_pending"),
            ],
            obligations={"live": "partial", "activation": "pending", "cleanup": "pending"},
        )


def test_progress_cannot_report_n_over_n_with_remaining_obligations() -> None:
    model = build_execution_evidence_model(
        goal={
            "revision": "rev4+rev4.1",
            "hash": "a" * 64,
            "current_active_step": "canonical direct URLs and truthful progress",
            "completed_steps": ["goal continuity", "typed evidence"],
            "newly_discovered_required_steps": ["cleanup-route-before-create"],
            "waiting_external_action": "",
        },
        build={
            "tree_hash": "b" * 40,
            "package_hash": "c" * 64,
            "tool_surface_hash": "d" * 64,
        },
        records=[],
        obligations={"direct_urls": "partial", "activation": "pending", "cleanup": "pending"},
    )

    progress = render_execution_evidence_views(model)["final_report"]["progress"]
    assert progress["current_active_step"] == "canonical direct URLs and truthful progress"
    assert progress["remaining_destructive_or_cleanup_obligations"] == ["cleanup"]
    assert progress["candidate_frozen"] is False
    assert progress["completion_proven"] is False
    assert progress["display_fraction"] is None


def test_mode_specific_coverage_is_not_promoted_to_another_mode() -> None:
    model = build_execution_evidence_model(
        goal={"revision": "rev4+rev4.1", "hash": "a" * 64},
        build={"tree_hash": "b" * 64, "package_hash": "c" * 64, "tool_surface_hash": "d" * 64},
        records=[
            _record(
                "compile_only",
                1,
                "internal_compiler_screening",
                "passed",
                coverage_cells=[{"cell": "followup_semantics", "state": "screened"}],
            )
        ],
        obligations={"live": "pending", "activation": "pending", "cleanup": "pending"},
    )

    cells = render_execution_evidence_views(model)["coverage_matrix"]["cells"]
    assert cells == [{"cell": "followup_semantics", "mode": "internal_compiler_screening", "state": "screened"}]
    assert not any(row["mode"] == "codex_in_the_loop" for row in cells)
