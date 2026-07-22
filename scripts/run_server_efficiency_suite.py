#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CHART_IDS = [f"chart_{index:02d}" for index in range(12)]
DATASET_IDS = ["dataset_a", "dataset_b"]
CONNECTION_ID = "connection_a"
SIMULATED_READ_DELAY_SEC = 1.5
WALL_CLOCK_SCALE = 1 / 30


class RevisionedSnapshotClient:
    def __init__(self, *, max_read_concurrency: int = 3, wall_delay_sec: float = 0.0) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.config = SimpleNamespace(max_read_concurrency=max_read_concurrency)
        self.wall_delay_sec = max(0.0, wall_delay_sec)
        self._calls_lock = Lock()

    def rpc(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.wall_delay_sec:
            time.sleep(self.wall_delay_sec)
        with self._calls_lock:
            self.calls.append((method, payload))
        if method == "getDashboard":
            return {
                "entry": {
                    "entryId": "dashboard_efficiency",
                    "workbookId": "workbook_efficiency",
                    "revId": "dashboard_rev_1",
                    "savedId": "dashboard_saved_1",
                    "data": {"tabs": [{"id": "main", "items": [{"chartId": item} for item in CHART_IDS]}]},
                }
            }
        if method == "getWorkbookEntries":
            entries = [
                {"entryId": "dashboard_efficiency", "scope": "dashboard"},
                *[{"entryId": item, "scope": "editor_chart"} for item in CHART_IDS],
                *[{"entryId": item, "scope": "dataset"} for item in DATASET_IDS],
                {"entryId": CONNECTION_ID, "scope": "connection"},
            ]
            return {
                "entries": [
                    {**entry, "revId": f"revision:{entry['entryId']}"}
                    for entry in entries
                ]
            }
        if method == "getEntriesRelations":
            return {
                "relations": [
                    *[
                        {
                            "fromEntryId": chart_id,
                            "toEntryId": DATASET_IDS[index % len(DATASET_IDS)],
                            "relationType": "dataset",
                        }
                        for index, chart_id in enumerate(CHART_IDS)
                    ],
                    *[
                        {
                            "fromEntryId": dataset_id,
                            "toEntryId": CONNECTION_ID,
                            "relationType": "connection",
                        }
                        for dataset_id in DATASET_IDS
                    ],
                ]
            }
        if method == "getEditorChart":
            index = CHART_IDS.index(str(payload["chartId"]))
            return {
                "entry": {
                    "entryId": payload["chartId"],
                    "scope": "editor_chart",
                    "data": {"datasetId": DATASET_IDS[index % len(DATASET_IDS)]},
                }
            }
        if method == "getDataset":
            return {
                "dataset": {
                    "datasetId": payload["datasetId"],
                    "data": {"source": {"connectionId": CONNECTION_ID}},
                }
            }
        if method == "getConnection":
            return {"connection": {"connectionId": payload["connectionId"], "data": {"host": "example.invalid"}}}
        raise AssertionError(method)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += max(0.0, seconds)


def _timed(call):
    started = time.perf_counter()
    value = call()
    return value, round((time.perf_counter() - started) * 1000, 3)


def run_suite() -> dict[str, Any]:
    from datalens_dev_mcp.mcp.tools.pipeline import (
        _PROJECT_VALIDATION_CACHE,
        _delivery_stage_snapshot,
        dl_validate_project,
    )
    from datalens_dev_mcp.api.scheduler import DataLensRequestScheduler
    from datalens_dev_mcp.editor.authoring_profiles import (
        _packaged_template_set_identity,
        authoring_profile_template_set_identity,
    )
    from datalens_dev_mcp.mcp.heavy_response import project_heavy_tool_response
    from datalens_dev_mcp.mcp.response_projection import stable_json_text
    from datalens_dev_mcp.mcp.tools.runtime import _EDITOR_VALIDATION_CACHE, dl_validate_editor_runtime_contract
    from datalens_dev_mcp.mcp.tools.snapshot import dl_snapshot_dashboard
    from datalens_dev_mcp.runtime_resources import _package_manifest, resource_manifest

    issues: list[str] = []
    _package_manifest.cache_clear()
    _, manifest_cold_ms = _timed(resource_manifest)
    _, manifest_warm_ms = _timed(resource_manifest)
    manifest_cache = _package_manifest.cache_info()
    if manifest_cache.misses != 1 or manifest_cache.hits < 1:
        issues.append(f"runtime resource manifest cache contract failed: {manifest_cache}")

    _packaged_template_set_identity.cache_clear()
    profile_template_set_cold, profile_template_set_cold_ms = _timed(
        lambda: authoring_profile_template_set_identity(
            "templates/datalens/standard_chart_templates.json"
        )
    )
    profile_template_set_warm, profile_template_set_warm_ms = _timed(
        lambda: authoring_profile_template_set_identity(
            "templates/datalens/standard_chart_templates.json"
        )
    )
    profile_template_set_cache = _packaged_template_set_identity.cache_info()
    if (
        profile_template_set_cold != profile_template_set_warm
        or profile_template_set_cache.misses != 1
        or profile_template_set_cache.hits < 1
        or profile_template_set_warm_ms >= profile_template_set_cold_ms
    ):
        issues.append(
            "authoring-profile template-set cache changed identity or missed the warm path: "
            f"cold={profile_template_set_cold_ms}ms warm={profile_template_set_warm_ms}ms "
            f"cache={profile_template_set_cache}"
        )

    with tempfile.TemporaryDirectory() as tmp:
        client = RevisionedSnapshotClient()
        first, snapshot_cold_ms = _timed(
            lambda: dl_snapshot_dashboard(
                project_root=tmp,
                dashboard_id="dashboard_efficiency",
                workbook_id="workbook_efficiency",
                snapshot_branch="saved",
                client=client,
            )
        )
        cold_rpc_count = len(client.calls)
        second, snapshot_warm_ms = _timed(
            lambda: dl_snapshot_dashboard(
                project_root=tmp,
                dashboard_id="dashboard_efficiency",
                workbook_id="workbook_efficiency",
                snapshot_branch="saved",
                client=client,
            )
        )
        warm_rpc_count = len(client.calls) - cold_rpc_count
    if not second.get("snapshot_reused") or warm_rpc_count != 2 or second.get("hydration_rpc_count") != 0:
        issues.append(
            "revision-validated snapshot reuse failed: "
            f"reused={second.get('snapshot_reused')} warm_rpc_count={warm_rpc_count}"
        )

    _PROJECT_VALIDATION_CACHE.clear()
    with tempfile.TemporaryDirectory() as tmp:
        requirements = Path(tmp) / "requirements"
        requirements.mkdir()
        (requirements / "fixture.sql").write_text("SELECT 1\n", encoding="utf-8")
        first_validation, validation_cold_ms = _timed(lambda: dl_validate_project(tmp))
        second_validation, validation_warm_ms = _timed(lambda: dl_validate_project(tmp))
    if (
        second_validation.get("validation_cache", {}).get("hit") is not True
        or first_validation.get("status") != second_validation.get("status")
        or first_validation.get("issues") != second_validation.get("issues")
    ):
        issues.append("project validation cache changed validation quality or missed an unchanged tree")

    heavy_result = {
        "ok": True,
        "executed": True,
        "status": "completed",
        "completed_action_count": 3,
        "actions": [{"payload": "x" * 20_000} for _ in range(3)],
        "stdout": "y" * 20_000,
        "publish_results": [{"payload": "z" * 20_000}],
    }
    raw_chars = len(json.dumps(heavy_result, separators=(",", ":")))
    compact_chars = len(json.dumps(_delivery_stage_snapshot(heavy_result), separators=(",", ":")))
    if compact_chars >= raw_chars * 0.1:
        issues.append(f"delivery summary compaction is below 90%: raw={raw_chars} compact={compact_chars}")

    fake_clock = FakeClock()
    scheduler = DataLensRequestScheduler(clock=fake_clock, sleeper=fake_clock.sleep)
    request_starts: list[float] = []
    for _ in range(5):
        scheduler.execute(
            key="https://api.datalens.tech",
            method="getDashboard",
            readonly=True,
            interval_sec=1.05,
            max_read_concurrency=3,
            operation=lambda: request_starts.append(fake_clock()) or b"{}",
        )
    spacings = [
        round(current - previous, 6)
        for previous, current in zip(request_starts, request_starts[1:])
    ]
    scheduler_metrics = scheduler.snapshot()
    if any(spacing < 1.05 for spacing in spacings):
        issues.append(f"process scheduler request spacing fell below 1.05 seconds: {spacings}")
    if float(scheduler_metrics["effective_request_starts_per_minute"] or 0) > 57.15:
        issues.append(
            "process scheduler effective rate exceeds the configured safety budget: "
            f"{scheduler_metrics['effective_request_starts_per_minute']}"
        )

    scaled_wall_delay = SIMULATED_READ_DELAY_SEC * WALL_CLOCK_SCALE
    with tempfile.TemporaryDirectory() as serial_tmp, tempfile.TemporaryDirectory() as parallel_tmp:
        serial_result, serial_ms = _timed(
            lambda: dl_snapshot_dashboard(
                project_root=serial_tmp,
                dashboard_id="dashboard_efficiency",
                workbook_id="workbook_efficiency",
                snapshot_branch="saved",
                client=RevisionedSnapshotClient(
                    max_read_concurrency=1,
                    wall_delay_sec=scaled_wall_delay,
                ),
            )
        )
        parallel_result, parallel_ms = _timed(
            lambda: dl_snapshot_dashboard(
                project_root=parallel_tmp,
                dashboard_id="dashboard_efficiency",
                workbook_id="workbook_efficiency",
                snapshot_branch="saved",
                client=RevisionedSnapshotClient(
                    max_read_concurrency=3,
                    wall_delay_sec=scaled_wall_delay,
                ),
            )
        )
    speedup_percent = round((1 - parallel_ms / serial_ms) * 100, 1)
    if speedup_percent < 25:
        issues.append(
            f"scaled 1.5-second read scenario improved by only {speedup_percent}% "
            f"(serial={serial_ms}ms parallel={parallel_ms}ms)"
        )
    if serial_result["compact_graph"]["sha256"] != parallel_result["compact_graph"]["sha256"]:
        issues.append("parallel snapshot changed the compact graph payload")

    _EDITOR_VALIDATION_CACHE.clear()
    editor_payload = {"prepare": "module.exports = {render: () => ''};"}
    first_editor = dl_validate_editor_runtime_contract(sections=editor_payload)
    second_editor = dl_validate_editor_runtime_contract(sections=editor_payload)
    if first_editor["findings"] != second_editor["findings"] or not second_editor["validation_cache"]["hit"]:
        issues.append("Editor validation cache changed findings or missed an identical payload")

    with tempfile.TemporaryDirectory() as tmp:
        heavy_projection = project_heavy_tool_response(
            "dl_create_safe_apply_plan",
            {
                "ok": True,
                "status": "completed",
                "actions": [{"method": "updateDashboard", "payload": "x" * 50_000} for _ in range(3)],
            },
            response_mode="summary",
            inline_char_budget=15_000,
            project_root=tmp,
        )
    heavy_inline_chars = len(stable_json_text(heavy_projection))
    if heavy_inline_chars > 15_000:
        issues.append(f"heavy response exceeded 15K inline budget: {heavy_inline_chars}")

    return {
        "ok": not issues,
        "issues": issues,
        "runtime_resource_manifest": {
            "cold_ms": manifest_cold_ms,
            "warm_ms": manifest_warm_ms,
            "cache_hits": manifest_cache.hits,
            "cache_misses": manifest_cache.misses,
        },
        "authoring_profile_template_set": {
            "cold_ms": profile_template_set_cold_ms,
            "warm_ms": profile_template_set_warm_ms,
            "cache_hits": profile_template_set_cache.hits,
            "cache_misses": profile_template_set_cache.misses,
            "identity_preserved": profile_template_set_cold == profile_template_set_warm,
            **profile_template_set_warm,
        },
        "snapshot": {
            "cold_ms": snapshot_cold_ms,
            "warm_ms": snapshot_warm_ms,
            "cold_rpc_count": cold_rpc_count,
            "warm_rpc_count": warm_rpc_count,
            "rpc_reduction_percent": round((1 - warm_rpc_count / cold_rpc_count) * 100, 1),
            "first_response_chars": len(json.dumps(first, ensure_ascii=False)),
            "warm_response_chars": len(json.dumps(second, ensure_ascii=False)),
        },
        "project_validation": {
            "cold_ms": validation_cold_ms,
            "warm_ms": validation_warm_ms,
            "cache_hit": second_validation.get("validation_cache", {}).get("hit"),
            "status_preserved": first_validation.get("status") == second_validation.get("status"),
            "issues_preserved": first_validation.get("issues") == second_validation.get("issues"),
        },
        "delivery_summary": {
            "raw_chars": raw_chars,
            "compact_chars": compact_chars,
            "reduction_percent": round((1 - compact_chars / raw_chars) * 100, 1),
        },
        "request_scheduler": {
            "request_starts": request_starts,
            "spacings_sec": spacings,
            "effective_request_starts_per_minute": scheduler_metrics["effective_request_starts_per_minute"],
            "max_read_concurrency": scheduler_metrics["max_read_concurrency"],
        },
        "parallel_snapshot": {
            "simulated_read_delay_sec": SIMULATED_READ_DELAY_SEC,
            "wall_clock_scale": WALL_CLOCK_SCALE,
            "serial_ms": serial_ms,
            "parallel_ms": parallel_ms,
            "speedup_percent": speedup_percent,
            "quality_sha256_preserved": (
                serial_result["compact_graph"]["sha256"] == parallel_result["compact_graph"]["sha256"]
            ),
        },
        "editor_validation_cache": {
            "cache_hit": second_editor["validation_cache"]["hit"],
            "findings_preserved": first_editor["findings"] == second_editor["findings"],
        },
        "heavy_response": {
            "inline_chars": heavy_inline_chars,
            "budget_chars": 15_000,
            "canonical_artifact_sha256": heavy_projection["canonical_artifact"]["sha256"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic stdio-server efficiency regressions.")
    parser.add_argument(
        "--out",
        default=str(ROOT / "artifacts" / "server_efficiency" / "summary.json"),
        help="Path for the JSON report.",
    )
    parser.add_argument("--strict", action="store_true", help="Fail when an efficiency contract is violated.")
    args = parser.parse_args(argv)
    summary = run_suite()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
