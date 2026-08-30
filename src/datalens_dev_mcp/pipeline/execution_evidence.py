from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from datalens_dev_mcp.pipeline.workflow_events import canonical_hash

EVIDENCE_MODES = frozenset(
    {
        "internal_compiler_screening",
        "public_stdio_replay",
        "internal_controlled_live_runner",
        "public_eight_tool_live_lifecycle",
        "codex_in_the_loop",
        "browser_visual_attestation",
    }
)
EVIDENCE_FRESHNESS = frozenset({"current", "superseded"})
COVERAGE_STATES = frozenset({"mapped", "selected", "screened", "replayed", "live_verified", "closed"})
CALL_EFFECTS = frozenset({"read", "write"})


class EvidenceModelError(ValueError):
    code = "EVIDENCE_ARTIFACT_INVALID"


def build_execution_evidence_model(
    *,
    goal: dict[str, Any],
    build: dict[str, Any],
    records: list[dict[str, Any]],
    obligations: dict[str, str],
) -> dict[str, Any]:
    """Build one immutable owner for all final execution-evidence projections."""

    _require_hash(goal, "hash", owner="goal")
    if not str(goal.get("revision") or ""):
        raise EvidenceModelError("goal revision is missing")
    _require_hash(build, "tree_hash", owner="build", lengths=(40, 64))
    for field_name in ("package_hash", "tool_surface_hash"):
        _require_hash(build, field_name, owner="build")
    if not isinstance(obligations, dict) or not obligations:
        raise EvidenceModelError("execution obligations are missing")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identities: set[tuple[str, int]] = set()
    identity_hashes: dict[tuple[str, int], str] = {}
    for source in records:
        record = _validated_record(source)
        identity = (record["evidence_id"], record["sequence"])
        record_hash = canonical_hash(record)
        if identity in identities:
            if identity_hashes[identity] != record_hash:
                raise EvidenceModelError(
                    f"contradictory evidence records share evidence_id and sequence: {identity[0]}#{identity[1]}"
                )
            continue
        identities.add(identity)
        identity_hashes[identity] = record_hash
        grouped[record["evidence_id"]].append(record)

    normalized: list[dict[str, Any]] = []
    for evidence_id in sorted(grouped):
        rows = sorted(grouped[evidence_id], key=lambda item: item["sequence"])
        latest_sequence = rows[-1]["sequence"]
        for row in rows:
            row["freshness"] = "current" if row["sequence"] == latest_sequence else "superseded"
            normalized.append(row)

    payload = {
        "schema_id": "datalens_execution_evidence_model",
        "model_version": 1,
        "goal": deepcopy(goal),
        "build": deepcopy(build),
        "obligations": {str(key): str(value) for key, value in sorted(obligations.items())},
        "records": normalized,
    }
    payload["evidence_model_hash"] = canonical_hash(payload)
    return payload


def render_execution_evidence_views(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Render all summaries from the same validated model and bind its hash."""

    _validate_model_hash(model)
    model_hash = str(model["evidence_model_hash"])
    current = [row for row in model.get("records") or [] if row.get("freshness") == "current"]
    superseded = [row for row in model.get("records") or [] if row.get("freshness") == "superseded"]

    provider_reads = 0
    provider_writes = 0
    observed_methods: set[str] = set()
    counts_by_mode: dict[str, dict[str, int]] = {
        mode: {"provider_reads": 0, "provider_writes": 0} for mode in sorted(EVIDENCE_MODES)
    }
    cells: list[dict[str, str]] = []
    for record in current:
        mode = str(record["mode"])
        for call in record.get("observed_calls") or []:
            count = int(call["count"])
            effect = str(call["effect"])
            observed_methods.add(str(call["method"]))
            if effect == "read":
                provider_reads += count
                counts_by_mode[mode]["provider_reads"] += count
            else:
                provider_writes += count
                counts_by_mode[mode]["provider_writes"] += count
        for cell in record.get("coverage_cells") or []:
            cells.append(
                {
                    "cell": str(cell["cell"]),
                    "mode": mode,
                    "state": str(cell["state"]),
                }
            )
    cells.sort(key=lambda item: (item["cell"], item["mode"], item["state"]))

    current_statuses = {
        str(record["evidence_id"]): str(record["status"])
        for record in sorted(current, key=lambda item: item["evidence_id"])
    }
    obligations = dict(model.get("obligations") or {})
    completion_proven = bool(obligations) and all(
        value in {"complete", "satisfied", "not_applicable"} for value in obligations.values()
    )
    progress = _progress_projection(model, completion_proven=completion_proven)
    common = {"evidence_model_hash": model_hash}
    return {
        "final_report": {
            **common,
            "view": "final_report",
            "goal": deepcopy(model["goal"]),
            "build": deepcopy(model["build"]),
            "current_statuses": current_statuses,
            "obligations": obligations,
            "completion_proven": completion_proven,
            "progress": progress,
            "current_record_count": len(current),
            "superseded_record_count": len(superseded),
        },
        "coverage_matrix": {
            **common,
            "view": "coverage_matrix",
            "cells": cells,
            "modes": sorted({item["mode"] for item in cells}),
        },
        "call_counts": {
            **common,
            "view": "call_counts",
            "provider_reads": provider_reads,
            "provider_writes": provider_writes,
            "observed_methods": sorted(observed_methods),
            "counts_by_mode": counts_by_mode,
            "planned_methods_counted": False,
        },
        "canary_summary": {
            **common,
            "view": "canary_summary",
            "records": [
                {
                    "evidence_id": str(record["evidence_id"]),
                    "mode": str(record["mode"]),
                    "status": str(record["status"]),
                    "receipt_hash": str(record["receipt_hash"]),
                }
                for record in sorted(current, key=lambda item: (item["mode"], item["evidence_id"]))
                if record["mode"]
                in {
                    "internal_controlled_live_runner",
                    "public_eight_tool_live_lifecycle",
                    "codex_in_the_loop",
                    "browser_visual_attestation",
                }
            ],
        },
    }


def render_transfer_evidence(
    source: dict[str, Any],
    *,
    additional_receipts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Render export/import/cancel claims without strengthening source evidence."""

    material = deepcopy(source if isinstance(source, dict) else {})
    receipts = [deepcopy(item) for item in additional_receipts or [] if isinstance(item, dict)]
    passed_tokens = {"success", "passed", "completed", "export_completed", "import_completed"}
    export_value = material.get("export") or material.get("export_status") or ""
    import_value = material.get("import") or material.get("import_status") or ""
    export_raw = export_value.get("status") if isinstance(export_value, dict) else export_value
    import_raw = import_value.get("status") if isinstance(import_value, dict) else import_value
    export_status = "passed" if str(export_raw or "").lower() in passed_tokens else "partial"
    import_status = "passed" if str(import_raw or "").lower() in passed_tokens else "partial"
    counts_equal = bool(
        material.get("scope_type_counts_equal")
        or (material.get("semantic_comparison") or {}).get("scope_type_counts_equal")
    )
    semantic = dict(
        material.get("semantic_equivalence")
        or material.get("semantic_comparison")
        or {}
    )
    semantic_receipts = [item for item in receipts if item.get("kind") == "semantic_equivalence"]
    if semantic_receipts:
        semantic = semantic_receipts[-1]
    objects = semantic.get("objects") if isinstance(semantic.get("objects"), list) else []
    remapping = semantic.get("id_remapping") if isinstance(semantic.get("id_remapping"), dict) else {}
    semantic_pass = bool(
        str(semantic.get("status") or semantic.get("semantic_equivalence") or "")
        in {"passed", "semantic_equivalence_passed"}
        and objects
        and remapping
        and all(
            isinstance(item, dict)
            and item.get("source_id")
            and item.get("imported_id")
            and item.get("normalized_payload_hash")
            for item in objects
        )
    )
    property_names = (
        "acl", "secrets", "saved_revision_identity",
        "published_revision_identity", "external_references",
    )
    source_properties = semantic.get("properties") if isinstance(semantic.get("properties"), dict) else {}
    properties = {name: str(source_properties.get(name) or "unknown") for name in property_names}

    cancel = dict(material.get("cancel") or {})
    cancel_receipts = [item for item in receipts if item.get("kind") == "cancel_effect"]
    if cancel_receipts:
        cancel = {**cancel, **cancel_receipts[-1]}
    cancel_request = cancel.get("cancel_request") if isinstance(cancel.get("cancel_request"), dict) else {}
    post_cancel = cancel.get("post_cancel_observation") if isinstance(cancel.get("post_cancel_observation"), dict) else {}
    response_bound = bool(
        cancel.get("response_bound_to_export_id")
        or cancel.get("cancel_response_bound_to_exact_export")
        or cancel_request.get("response_bound_to_export_id")
        or material.get("cancel_response_bound_to_exact_export")
    )
    terminal = str(
        cancel.get("terminal_status")
        or post_cancel.get("terminal_status")
        or "unknown"
    ).lower()
    documented_effect = str(cancel.get("documented_effect") or cancel.get("effect_status") or "").lower()
    if documented_effect in {"observed", "cancelled", "canceled"} and cancel.get("evidence_refs"):
        effect_status = "observed"
    elif documented_effect in {"not_observable", "unobservable"}:
        effect_status = "not_observable"
    elif terminal == "success":
        effect_status = "raced_with_completion" if response_bound else "unknown"
    else:
        effect_status = "unknown"
    cleanup_value = material.get("cleanup") or {}
    if isinstance(cleanup_value, list):
        cleanup_passed = bool(cleanup_value) and all(item.get("absence_verified") is True for item in cleanup_value)
    else:
        cleanup_raw = str(material.get("cleanup_status") or cleanup_value.get("status") or "unknown").lower()
        cleanup_passed = cleanup_raw in {"passed", "success", "completed"}
    source_status = str(material.get("status") or "partial").lower()
    completion_proven = bool(
        source_status in {"passed", "completed"}
        and export_status == "passed"
        and import_status == "passed"
        and semantic_pass
        and effect_status in {"observed", "not_observable"}
        and cleanup_passed
    )
    payload = {
        "schema_id": "datalens_transfer_evidence_projection",
        "export": {"status": export_status},
        "import": {"status": import_status},
        "inventory_counts_equal": counts_equal,
        "semantic_equivalence": {
            "status": "passed" if semantic_pass else "partial",
            "object_count": len(objects),
            "id_remapping_count": len(remapping),
            "properties": properties,
        },
        "cancel_request": {
            "attempted": bool(cancel.get("attempted", response_bound)),
            "response_bound_to_export_id": response_bound,
            "status": "acknowledged" if response_bound else "unknown",
        },
        "post_cancel_observation": {"terminal_status": terminal},
        "cancel_effect": {
            "status": effect_status,
            "evidence_refs": [str(item) for item in cancel.get("evidence_refs") or [] if str(item)],
        },
        "cleanup": {"status": "passed" if cleanup_passed else "unknown"},
        "completion_proven": completion_proven,
    }
    payload["projection_hash"] = canonical_hash(payload)
    return payload


def _progress_projection(model: dict[str, Any], *, completion_proven: bool) -> dict[str, Any]:
    goal = dict(model.get("goal") or {})
    obligations = {str(key): str(value) for key, value in (model.get("obligations") or {}).items()}
    unresolved = sorted(
        key for key, value in obligations.items() if value not in {"complete", "satisfied", "not_applicable"}
    )
    completed_steps = [str(item) for item in goal.get("completed_steps") or []]
    candidate_frozen = bool(goal.get("candidate_frozen", False)) and not any(
        marker in key.lower() for key in unresolved for marker in ("activation", "candidate", "freeze")
    )
    display_fraction = None
    if completion_proven:
        total = len(completed_steps)
        display_fraction = f"{total}/{total}"
    return {
        "authoritative_goal_revision": str(goal.get("revision") or ""),
        "authoritative_goal_hash": str(goal.get("hash") or ""),
        "current_active_step": str(goal.get("current_active_step") or ""),
        "completed_steps": completed_steps,
        "newly_discovered_required_steps": [str(item) for item in goal.get("newly_discovered_required_steps") or []],
        "waiting_external_action": str(goal.get("waiting_external_action") or ""),
        "remaining_work_items": unresolved,
        "remaining_destructive_or_cleanup_obligations": [
            key
            for key in unresolved
            if any(marker in key.lower() for marker in ("cleanup", "delete", "restore", "destructive"))
        ],
        "remaining_activation_obligations": [
            key for key in unresolved if any(marker in key.lower() for marker in ("activation", "candidate", "freeze"))
        ],
        "candidate_frozen": candidate_frozen,
        "completion_proven": completion_proven,
        "display_fraction": display_fraction,
    }


def _validated_record(source: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise EvidenceModelError("evidence record must be an object")
    record = deepcopy(source)
    evidence_id = str(record.get("evidence_id") or "")
    if not evidence_id:
        raise EvidenceModelError("evidence record id is missing")
    sequence = record.get("sequence")
    if not isinstance(sequence, int) or sequence < 1:
        raise EvidenceModelError(f"evidence record sequence is invalid: {evidence_id}")
    mode = str(record.get("mode") or "")
    if mode not in EVIDENCE_MODES:
        raise EvidenceModelError(f"evidence record mode is invalid: {evidence_id}")
    if not str(record.get("status") or ""):
        raise EvidenceModelError(f"evidence record status is missing: {evidence_id}")
    _require_hash(record, "receipt_hash", owner=f"record {evidence_id}")

    calls = record.get("observed_calls") or []
    if not isinstance(calls, list):
        raise EvidenceModelError(f"observed_calls must be a list: {evidence_id}")
    for call in calls:
        if not isinstance(call, dict) or not str(call.get("method") or ""):
            raise EvidenceModelError(f"observed call method is missing: {evidence_id}")
        if call.get("effect") not in CALL_EFFECTS:
            raise EvidenceModelError(f"observed call effect is invalid: {evidence_id}")
        if not isinstance(call.get("count"), int) or int(call.get("count") or 0) < 1:
            raise EvidenceModelError(f"observed call count is invalid: {evidence_id}")

    planned = record.get("planned_methods") or []
    if not isinstance(planned, list) or any(not isinstance(item, str) or not item for item in planned):
        raise EvidenceModelError(f"planned_methods must contain method names: {evidence_id}")
    cells = record.get("coverage_cells") or []
    if not isinstance(cells, list):
        raise EvidenceModelError(f"coverage_cells must be a list: {evidence_id}")
    for cell in cells:
        if not isinstance(cell, dict) or not str(cell.get("cell") or ""):
            raise EvidenceModelError(f"coverage cell is invalid: {evidence_id}")
        if cell.get("state") not in COVERAGE_STATES:
            raise EvidenceModelError(f"coverage cell state is invalid: {evidence_id}")
    record.pop("freshness", None)
    return record


def _require_hash(
    payload: dict[str, Any],
    field_name: str,
    *,
    owner: str,
    lengths: tuple[int, ...] = (64,),
) -> None:
    value = str(payload.get(field_name) or "")
    if len(value) not in lengths or any(character not in "0123456789abcdef" for character in value):
        expected = " or ".join(str(length) for length in lengths)
        raise EvidenceModelError(f"{owner} {field_name} is not a {expected}-hex digest")


def _validate_model_hash(model: dict[str, Any]) -> None:
    if model.get("schema_id") != "datalens_execution_evidence_model":
        raise EvidenceModelError("execution evidence model schema mismatch")
    material = deepcopy(model)
    expected = str(material.pop("evidence_model_hash", "") or "")
    if not expected or canonical_hash(material) != expected:
        raise EvidenceModelError("execution evidence model hash mismatch")
    for record in model.get("records") or []:
        if record.get("freshness") not in EVIDENCE_FRESHNESS:
            raise EvidenceModelError("execution evidence record freshness is invalid")
