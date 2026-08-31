#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from acceptance_shards import ROOT, compact_report, py, run_acceptance


OWNER_PATHS = {
    "visual-contract": (
        "src/datalens_dev_mcp/pipeline/project_decision_context.py",
        "src/datalens_dev_mcp/pipeline/effective_visual_contract.py",
        "src/datalens_dev_mcp/pipeline/reference_style_service.py",
        "src/datalens_dev_mcp/pipeline/semantic_change_planner.py",
        "src/datalens_dev_mcp/pipeline/visual_decisions.py",
        "src/datalens_dev_mcp/pipeline/task_planning_stage_services.py",
        "src/datalens_dev_mcp/pipeline/public_plan_builder.py",
    ),
    "public-workflow": (
        "src/datalens_dev_mcp/pipeline/target_discovery.py",
        "src/datalens_dev_mcp/mcp/task_projection.py",
        "src/datalens_dev_mcp/mcp/tools/tasks.py",
        "src/datalens_dev_mcp/server.py",
        "src/datalens_dev_mcp/pipeline/workflow_engine.py",
    ),
    "browser-qa": (
        "src/datalens_dev_mcp/pipeline/browser_qa.py",
        "src/datalens_dev_mcp/pipeline/task_qa_service.py",
    ),
    "render-profile": (
        "src/datalens_dev_mcp/editor/render_contract.py",
        "config/dashboard_render_profiles.json",
        "src/datalens_dev_mcp/assets/config/dashboard_render_profiles.json",
    ),
    "workflow-guards": (
        "AGENTS.md",
        "scripts/run_affected_acceptance.py",
        "scripts/run_full_acceptance.py",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run only acceptance owned by changed server paths.")
    parser.add_argument("--base", help="Git base revision used to derive changed paths.")
    parser.add_argument("--head", default="HEAD", help="Git head revision used with --base.")
    parser.add_argument("--changed-path", action="append", default=[], help="Explicit changed path; repeatable.")
    parser.add_argument("--all", action="store_true", help="Select every affected owner group.")
    parser.add_argument(
        "--release-gate",
        action="store_true",
        help="Explicitly authorize --all for release verification.",
    )
    args = parser.parse_args()
    if args.all and not args.release_gate:
        parser.error("--all requires --release-gate")

    changed_paths = _changed_paths(
        explicit=args.changed_path,
        base=str(args.base or ""),
        head=str(args.head or "HEAD"),
    )
    selected = sorted(OWNER_PATHS) if args.all else _selected_groups(changed_paths)
    if not selected:
        print(
            json.dumps(
                {
                    "ok": True,
                    "status": "not_required",
                    "changed_paths": changed_paths,
                    "selected_owner_groups": [],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    shards = [_shard(group) for group in selected]
    report = run_acceptance("affected", shards, surface="autonomous-v2")
    compact = compact_report(report)
    compact["status"] = "passed" if report["ok"] else "failed"
    compact["changed_paths"] = changed_paths
    compact["selected_owner_groups"] = selected
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def _changed_paths(*, explicit: list[str], base: str, head: str) -> list[str]:
    if explicit:
        return sorted({_normalize_path(value) for value in explicit if _normalize_path(value)})
    command = (
        ["git", "diff", "--name-only", f"{base}...{head}"]
        if base
        else ["git", "diff", "--name-only", head]
    )
    result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    paths = {_normalize_path(value) for value in result.stdout.splitlines() if _normalize_path(value)}
    if not base and head == "HEAD":
        cached = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        paths.update(_normalize_path(value) for value in cached.stdout.splitlines() if _normalize_path(value))
    return sorted(paths)


def _normalize_path(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return ""
    return path.as_posix().removeprefix("./")


def _selected_groups(paths: list[str]) -> list[str]:
    return sorted(
        group
        for group, owners in OWNER_PATHS.items()
        if any(path == owner or path.startswith(owner.rstrip("/") + "/") for path in paths for owner in owners)
    )


def _shard(group: str) -> dict[str, object]:
    if group == "visual-contract":
        return {
            "name": group,
            "command": py(
                "-m", "pytest", "-q",
                "tests/unit/test_project_decision_context_binding.py",
                "tests/unit/test_effective_visual_contract.py",
                "tests/unit/test_semantic_change_planner.py",
                "tests/integration/test_public_plan_style_preservation.py",
            ),
            "timeout_sec": 300,
        }
    if group == "public-workflow":
        return {
            "name": group,
            "command": py(
                "-m", "pytest", "-q",
                "tests/unit/test_target_discovery.py",
                "tests/unit/test_autonomous_tool_surface.py",
                "tests/integration/test_public_task_discovery.py",
            ),
            "timeout_sec": 300,
        }
    if group == "browser-qa":
        return {
            "name": group,
            "command": py(
                "-m", "pytest", "-q",
                "tests/unit/test_browser_qa_one_pass_plan.py",
                "tests/integration/test_public_browser_policy.py",
            ),
            "timeout_sec": 300,
        }
    if group == "render-profile":
        return {
            "name": group,
            "command": py(
                "-m", "pytest", "-q",
                "tests/unit/test_dashboard_render_contract.py",
                "tests/unit/test_standard_dashboard_contract.py",
            ),
            "timeout_sec": 300,
        }
    return {
        "name": group,
        "commands": [
            py("scripts/check_acceptance_surface_isolation.py"),
            py("scripts/lint_local.py"),
        ],
        "timeout_sec": 180,
    }


if __name__ == "__main__":
    raise SystemExit(main())
