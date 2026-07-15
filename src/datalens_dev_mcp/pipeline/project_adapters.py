from __future__ import annotations

from pathlib import Path
from typing import Any


EXPECTED_STANDARD_LAYOUT = [
    "dashboard/*/bundle.json",
    "artifacts/payload_plan.json",
    "artifacts/safe_apply_plan.json",
    "requirements/implementation_plan.md",
    "datalens_mapping/governance_memory_registry.json",
]
REQUIRED_MIGRATION_MANIFEST_FIELDS = [
    "workbook_id",
    "dashboard_ids",
    "workflows[].<action>.command",
    "workflows[].<action>.summary_path",
    "workflows[].<action>.evidence_checks",
    "workflows[].<action>.summary_requirements.branch_status",
    "workflows[].<action>.summary_requirements.required_fields",
    "workflows[].expected_changed_object_groups",
    "workflows[].affected_objects",
    "workflows[].safe_constraints",
]
MIGRATION_SUMMARY_REQUIRED_FIELDS = [
    "workbook_id",
    "dashboard_ids",
    "target_ids",
    "branch_status",
    "changed_object_counts",
    "evidence_paths",
]
BLOCKED_DIRECT_RPC_OPERATIONS = [
    "direct updateDashboard/updateEditorChart/updateDataset execution",
    "direct publish from scripts",
    "delete/move/permission mutations in normal actions",
    "shell command strings or inline interpreter commands",
    "ambient credential/env inheritance",
]
ADAPTER_REGISTRY: dict[str, dict[str, Any]] = {
    "standard_bundle": {
        "status": "supported",
        "description": "MCP-generated dashboard bundles with payload and safe-apply artifacts.",
        "migration_path": "Use dl_validate_project, dl_build_payload_plan, dl_create_safe_apply_plan, then guarded readback.",
    },
    "repo_live_workflow_manifest": {
        "status": "supported",
        "description": "Project declares existing validate/dry-run/apply/readback scripts through a local manifest.",
        "migration_path": "Use manifest-backed project-live tools; start with dry-run and summary validation.",
    },
    "dataset_update_workflow": {
        "status": "adapter_required",
        "description": "Dataset SQL/GUID-preserving update workflow detected; require manifest or dedicated guarded tool.",
        "migration_path": (
            "Wrap validateDataset/updateDataset scripts in a manifest with target IDs, "
            "changed counts, and readback evidence."
        ),
    },
    "advanced_editor_project": {
        "status": "adapter_required",
        "description": "Advanced Editor source project detected; require payload manifest before live writes.",
        "migration_path": (
            "Build or reference Editor payload artifacts, then route saves through a manifest "
            "or standard bundle safe-apply plan."
        ),
    },
    "legacy_direct_rpc_quarantine": {
        "status": "quarantined",
        "description": "Standalone direct-RPC scripts were detected without an MCP migration manifest.",
        "migration_path": (
            "Do not execute direct-RPC scripts through MCP until they are wrapped in a "
            "dry-run-first manifest with safe constraints and evidence."
        ),
    },
    "unknown_custom_layout": {
        "status": "adapter_required",
        "description": "Custom layout is not understood safely by generic MCP planning.",
        "migration_path": "Add a manifest or convert to the standard MCP bundle layout before planning writes.",
    },
}
MANIFEST_NAMES = (".datalens-mcp.json", "datalens-mcp.project.json", ".datalens-mcp.yaml", ".datalens-mcp.yml")
DIRECT_RPC_TERMS = (
    "updateDashboard",
    "updateEditorChart",
    "updateDataset",
    "validateDataset",
    "createDashboard",
    "createEditorChart",
    "publishWorkbookEntry",
    "publishEntry",
    "publish_saved",
    "DATALENS_IAM_TOKEN",
    "YC_IAM_TOKEN",
)
DIRECT_RPC_SCRIPT_PATTERNS = (
    "*.py",
    "scripts/*.py",
    "scripts/**/*.py",
    "discovery/*.py",
    "discovery/**/*.py",
)


def detect_project_adapter(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    detected_files = _detected_files(root)
    manifest_paths = [name for name in MANIFEST_NAMES if (root / name).is_file()]
    if manifest_paths:
        return {
            "ok": True,
            "adapter": "repo_live_workflow_manifest",
            "status": "supported",
            "project_root": str(root),
            "detected_files": detected_files,
            "manifest_paths": manifest_paths,
            "adapter_registry": ADAPTER_REGISTRY,
            "manifest_requirements": _manifest_requirements(),
            "migration_guidance": _migration_guidance("repo_live_workflow_manifest", evidence=manifest_paths),
            "recommended_next_actions": [
                "Run dl_list_project_live_workflows or dl_detect_project_live_workflows.",
                "Run dl_plan_project_live_workflow before any execution.",
                "Run dry-run first and review summary evidence before apply.",
                "Keep may_execute_command=false until dry-run summaries and evidence paths are reviewed.",
            ],
        }
    bundle_paths = sorted(root.glob("dashboard/*/bundle.json"))
    payload_plan = root / "artifacts" / "payload_plan.json"
    standard_markers = [
        bool(bundle_paths),
        payload_plan.is_file(),
        (root / "requirements").is_dir() and (root / "datalens_mapping").is_dir(),
    ]
    if any(standard_markers):
        return {
            "ok": True,
            "adapter": "standard_bundle",
            "status": "supported",
            "project_root": str(root),
            "detected_files": detected_files,
            "expected_standard_layout": EXPECTED_STANDARD_LAYOUT,
            "adapter_registry": ADAPTER_REGISTRY,
            "manifest_requirements": _manifest_requirements(),
            "migration_guidance": _migration_guidance("standard_bundle", evidence=[str(path) for path in bundle_paths[:5]]),
            "recommended_next_actions": [
                "Run dl_build_payload_plan before dl_create_safe_apply_plan when dashboard bundles changed.",
                "Run dl_create_safe_apply_plan only after payload_plan contains the intended actions.",
            ],
        }
    inferred = _infer_custom_adapter(root, detected_files)
    return {
        "ok": False,
        "adapter": inferred["adapter"],
        "status": inferred["status"],
        "project_root": str(root),
        "detected_files": detected_files,
        "expected_standard_layout": EXPECTED_STANDARD_LAYOUT,
        "adapter_registry": ADAPTER_REGISTRY,
        "evidence": inferred["evidence"],
        "direct_rpc_evidence": inferred.get("direct_rpc_evidence", []),
        "manifest_requirements": _manifest_requirements(),
        "migration_guidance": _migration_guidance(inferred["adapter"], evidence=inferred["evidence"]),
        "blocked_operations": _blocked_operations(inferred["adapter"]),
        "recommended_next_actions": [
            "Add a project live workflow manifest before live planning.",
            "Declare script argv, modes, required env names, affected DataLens objects, expected artifacts, and evidence checks.",
            "Use may_execute_command=false for new migration manifests until dry-run evidence is reviewed.",
            "Do not treat an empty generic plan as successful for custom layouts.",
        ],
    }


def list_project_adapter_registry() -> dict[str, Any]:
    return {
        "ok": True,
        "adapters": ADAPTER_REGISTRY,
        "manifest_requirements": _manifest_requirements(),
        "blocked_direct_rpc_operations": BLOCKED_DIRECT_RPC_OPERATIONS,
    }


def _detected_files(root: Path) -> list[str]:
    patterns = [
        "README.md",
        *MANIFEST_NAMES,
        "dashboard",
        "dashboard/*/bundle.json",
        "dashboard/**/*.js",
        "artifacts",
        "artifacts/payload_plan.json",
        "datalens_mapping",
        "requirements",
        "requirements/**/*.sql",
        "scripts",
        "scripts/*.py",
        "discovery",
        "discovery/*.py",
        "source_inventory",
        "*.py",
    ]
    detected: list[str] = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.exists():
                rel = path.relative_to(root)
                rendered = str(rel)
                if rendered not in detected:
                    detected.append(rendered)
    return detected[:80]


def _infer_custom_adapter(root: Path, detected_files: list[str]) -> dict[str, Any]:
    lowered = " ".join(detected_files).lower()
    direct_rpc_evidence = _detect_direct_rpc_scripts(root)
    dataset_patterns = [
        "dataset",
        "updatedataset",
        "validate_dataset",
        "apply_cpc",
        "source_freshness",
    ]
    if any(pattern in lowered for pattern in dataset_patterns):
        return {
            "adapter": "dataset_update_workflow",
            "status": "adapter_required",
            "evidence": ["dataset/update script or SQL artifact detected"],
            "direct_rpc_evidence": direct_rpc_evidence,
        }
    if any(path.endswith(("sources.js", "prepare.js", "params.js", "bundle.json")) for path in detected_files) or (
        root / "dashboard"
    ).is_dir():
        return {
            "adapter": "advanced_editor_project",
            "status": "adapter_required",
            "evidence": ["Advanced Editor/dashboard source layout detected without MCP payload plan"],
            "direct_rpc_evidence": direct_rpc_evidence,
        }
    if direct_rpc_evidence:
        return {
            "adapter": "legacy_direct_rpc_quarantine",
            "status": "quarantined",
            "evidence": ["standalone direct-RPC script detected without manifest"],
            "direct_rpc_evidence": direct_rpc_evidence,
        }
    return {"adapter": "unknown_custom_layout", "status": "adapter_required", "evidence": []}


def _detect_direct_rpc_scripts(root: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in DIRECT_RPC_SCRIPT_PATTERNS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            if rel in seen:
                continue
            seen.add(rel)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:200_000]
            except OSError:
                continue
            matched = [term for term in DIRECT_RPC_TERMS if term in text]
            if matched:
                evidence.append({"path": rel, "matched_terms": matched[:8]})
    return evidence[:25]


def _manifest_requirements() -> dict[str, Any]:
    return {
        "required_fields": REQUIRED_MIGRATION_MANIFEST_FIELDS,
        "summary_required_fields": MIGRATION_SUMMARY_REQUIRED_FIELDS,
        "default_may_execute_command": False,
        "dry_run_first": True,
        "target_ids_required": True,
    }


def _migration_guidance(adapter: str, *, evidence: list[Any]) -> dict[str, Any]:
    common = {
        "adapter": adapter,
        "evidence": evidence,
        "required_next_files": [".datalens-mcp.json", "reports/<action>_summary.json", "artifacts/readback/<target>.json"],
        "manifest_examples": [
            "templates/project_live_workflows/dry_run_manifest.json",
            "templates/project_live_workflows/save_manifest.json",
            "templates/project_live_workflows/publish_manifest.json",
        ],
        "evidence_requirements": [
            "target workbook/dashboard ids",
            "action-specific summary paths",
            "branch status",
            "changed object counts",
            "target ids",
            "dashboard payload preflight",
            "static SQL lint or declared not applicable evidence",
            "saved/published readback paths when applicable",
        ],
        "adoption_report_contract": {
            "compact_inline_fields": ["adapter", "status", "detected_file_count", "blocked_operations", "next_action"],
            "artifact_path": "artifacts/project_migration_adapter_report.json",
        },
    }
    if adapter == "legacy_direct_rpc_quarantine":
        return {
            **common,
            "next_action": "Inventory the script, create a dry-run-only manifest, and keep execution blocked until evidence is reviewed.",
            "blocked_operations": BLOCKED_DIRECT_RPC_OPERATIONS,
        }
    if adapter == "dataset_update_workflow":
        return {
            **common,
            "next_action": (
                "Declare validate, dry_run, save, saved_readback, publish, and "
                "published_readback summaries before updateDataset execution."
            ),
            "blocked_operations": _blocked_operations(adapter),
        }
    if adapter == "advanced_editor_project":
        return {
            **common,
            "next_action": "Bind Editor source files to target chart/dashboard ids and require payload preflight before save.",
            "blocked_operations": _blocked_operations(adapter),
        }
    if adapter == "repo_live_workflow_manifest":
        return {
            **common,
            "next_action": "Plan a selected manifest action, execute dry-run only when reviewed, then validate summary evidence.",
            "blocked_operations": _blocked_operations(adapter),
        }
    if adapter == "standard_bundle":
        return {
            **common,
            "next_action": "Use the standard payload and safe-apply pipeline; no migration wrapper is required.",
            "required_next_files": EXPECTED_STANDARD_LAYOUT,
            "blocked_operations": _blocked_operations(adapter),
        }
    return {
        **common,
        "next_action": "Add a manifest or convert the project to the standard MCP bundle before any live write plan.",
        "blocked_operations": _blocked_operations(adapter),
    }


def _blocked_operations(adapter: str) -> list[str]:
    if adapter in {"legacy_direct_rpc_quarantine", "dataset_update_workflow", "advanced_editor_project", "unknown_custom_layout"}:
        return BLOCKED_DIRECT_RPC_OPERATIONS
    return ["delete/move/permission mutations in normal actions", "publish without saved readback evidence"]
