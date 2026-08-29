from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from datalens_dev_mcp.pipeline.artifacts import read_json, write_json
from datalens_dev_mcp.pipeline.dataset_context_profile import (
    build_dataset_context_profile,
    dataset_context_profile_hash,
)
from datalens_dev_mcp.pipeline.execution_authorization import resolve_execution_authorization
from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
from datalens_dev_mcp.pipeline.public_plan_builder import PublicPlanBuilder, public_plan_hash
from datalens_dev_mcp.pipeline.semantic_change_planner import SemanticChangePlanner
from datalens_dev_mcp.pipeline.task_contract import (
    AcceptanceCriterion,
    DeliveryContract,
    EffectContract,
    ScopeContract,
    TargetContract,
    VerificationContract,
    WorkspaceContract,
    create_task_contract,
)


def build_public_plan_fixture(root: Path) -> tuple[ProjectJournal, dict, dict]:
    contract = create_task_contract(
        raw_request="Set the synthetic series label and save it",
        mode="update",
        route="editor_advanced",
        workspace=WorkspaceContract(project_root=str(root)),
        target=TargetContract(
            workbook_id="book_demo",
            object_ids=("chart_demo",),
            object_types=("editor_chart",),
        ),
        scope=ScopeContract(
            allowed_objects=("chart_demo",),
            allowed_tabs=("prepare.js",),
            allowed_semantic_slots=("series_label",),
        ),
        delivery=DeliveryContract(save=True, publish=False),
        acceptance=(
            AcceptanceCriterion(
                kind="semantic_change",
                statement='{"slot_id":"series_label","target_id":"chart_demo","value":"Revenue"}',
            ),
        ),
    ).to_dict()
    journal = ProjectJournal(root, contract["task_id"])
    journal.initialize(contract)
    write_json(journal.execution_authorization_path, resolve_execution_authorization(contract))
    write_json(journal.reference_binding_path, {"binding_hash": "c" * 64})
    write_json(
        journal.style_binding_path,
        {"binding_hash": "d" * 64, "technology": "editor_advanced"},
    )
    graph = {
        "graph_hash": "e" * 64,
        "nodes": [
            {
                "object_type": "editor_chart",
                "object_id": "chart_demo",
                "technology": "editor_advanced",
                "saved_revision": "r3",
            }
        ],
        "edges": [],
    }
    write_json(journal.target_graph_path, graph)
    baseline = {
        "result": {
            "chart": {
                "entry": {"entryId": "chart_demo", "revId": "r3"},
                "data": {
                    "meta": "{}",
                    "sources": "module.exports={main:{data:[]}};",
                    "prepare": (
                        "/* datalens-protected:runtime:start */function ratio(a,b){return b?a/b:null;}"
                        "/* datalens-protected:runtime:end */\n"
                        "const title='/* datalens-slot:series_label:text:start */Old"
                        "/* datalens-slot:series_label:end */';"
                    ),
                },
            }
        }
    }
    semantic = SemanticChangePlanner().plan(
        contract,
        target_graph=graph,
        baselines={"chart-chart_demo-saved": baseline},
        binding_hashes={
            "target_binding_hash": str((read_json(journal.target_binding_path, {}) or {}).get("binding_hash") or ""),
            "style_binding_hash": "d" * 64,
            "dataset_context_profile_hash": "f" * 64,
        },
    )
    assert semantic["ok"] is True
    profile = build_dataset_context_profile(
        dataset_id="dataset_demo",
        workbook_id="book_demo",
        dataset_revision="r2",
        query_set_hash="a" * 64,
        schema_hash="b" * 64,
        field_catalog=[{"guid": "metric_guid", "name": "value", "type": "float"}],
        rows=[{"metric_guid": 1.0}],
        pages_read=1,
        requested_limit=100,
        deterministic=False,
        observed_at="2026-08-27T00:00:00Z",
    )
    write_json(
        journal.root / "plans" / "data-proof-plan.json",
        {"schema_id": "dataset_probe_plan", "query_set_hash": "a" * 64},
    )
    plan = PublicPlanBuilder(journal, contract).build(
        semantic_result=semantic,
        context_profile=profile,
    )
    return journal, contract, plan


def test_public_plan_materializes_nonempty_hash_bound_artifact_set() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, plan = build_public_plan_fixture(Path(tmp))
        issues = PublicPlanBuilder(journal, contract).validate_current()
        semantic = read_json(journal.root / "plans" / "semantic-patch-plan.json", {})
        safe_apply = read_json(journal.root / "plans" / "safe-apply-plan.json", {})
        schema = read_json(Path(__file__).resolve().parents[2] / "schemas" / "public-task-plan.schema.json", {})
        schema_issues = list(Draft202012Validator(schema).iter_errors(plan))
    assert not issues
    assert not schema_issues
    assert plan["schema_id"] == "datalens_public_task_plan"
    assert plan["safe_apply_action_count"] == 1
    assert plan["dataset_context_profile_hash"]
    assert semantic["bindings"]["style_binding_hash"] == "d" * 64
    assert safe_apply["actions"][0]["method"] == "updateEditorChart"
    assert all(not item["artifact_uri"].startswith("/") for item in plan["artifacts"])


def test_codex_task_id_in_project_root_is_not_redacted_from_executable_plan() -> None:
    session_id = "01a04d9d-ac5b-7102-b36b-d35e6ff58862"
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp) / session_id / "owned-canary-write-state" / "project"
        project_root.mkdir(parents=True)
        with patch.dict(
            "os.environ",
            {"CODEX_SESSION_ID": session_id, "CODEX_THREAD_ID": session_id},
            clear=False,
        ):
            journal, _, _ = build_public_plan_fixture(project_root)
        safe_apply = read_json(journal.root / "plans" / "safe-apply-plan.json", {})

    assert safe_apply["project_root"] == str(journal.project_root)
    assert "<redacted>" not in safe_apply["project_root"]


def test_public_routing_session_id_in_project_root_is_not_redacted_from_executable_plan() -> None:
    session_id = "01b04d9d-ac5b-7102-b36b-d35e6ff58863"
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp) / session_id / "owned-canary-write-state" / "project"
        project_root.mkdir(parents=True)
        with patch.dict(
            "os.environ",
            {"WORKFLOW_SESSION_ID": session_id},
            clear=False,
        ):
            journal, _, _ = build_public_plan_fixture(project_root)
        safe_apply = read_json(journal.root / "plans" / "safe-apply-plan.json", {})

    assert safe_apply["project_root"] == str(journal.project_root)
    assert "<redacted>" not in safe_apply["project_root"]


def test_modified_plan_artifact_is_rejected_before_execute() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, _ = build_public_plan_fixture(Path(tmp))
        path = journal.root / "plans" / "semantic-patch-plan.json"
        modified = read_json(path, {})
        modified["targets"][0]["expected_after_hash"] = "0" * 64
        write_json(path, modified)
        issues = PublicPlanBuilder(journal, contract).validate_current()
    assert any("semantic_patch_plan" in item for item in issues)


def test_rehashed_route_tampering_is_rejected_by_contract_projection() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, _ = build_public_plan_fixture(Path(tmp))
        path = journal.root / "plans" / "plan.json"
        modified = read_json(path, {})
        modified["route"] = "wizard_native"
        modified["plan_hash"] = public_plan_hash(modified)
        write_json(path, modified)
        issues = PublicPlanBuilder(journal, contract).validate_current()
    assert "public plan contract projection is stale: route" in issues


def test_rehashed_action_count_tampering_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, _ = build_public_plan_fixture(Path(tmp))
        path = journal.root / "plans" / "plan.json"
        modified = read_json(path, {})
        modified["safe_apply_action_count"] = 2
        modified["plan_hash"] = public_plan_hash(modified)
        write_json(path, modified)
        issues = PublicPlanBuilder(journal, contract).validate_current()
    assert "public plan safe apply action count mismatch" in issues


def test_stale_dataset_context_profile_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        journal, contract, _ = build_public_plan_fixture(Path(tmp))
        path = journal.root / "data" / "context-profile.json"
        modified = read_json(path, {})
        modified["sample_scope"]["rows_observed"] = 99
        modified["profile_hash"] = dataset_context_profile_hash(modified)
        write_json(path, modified)
        issues = PublicPlanBuilder(journal, contract).validate_current()
    assert "dataset context binding is stale" in issues


def test_verify_existing_effect_plan_is_nonempty_hash_bound_and_zero_mutation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        contract = create_task_contract(
            raw_request="I already published dashboard:dash_verify; verify it",
            mode="review",
            route="read_only",
            operation_kind="verify_existing_effect",
            effect=EffectContract(kind="published", expected_state="published_revision_matches_saved"),
            verification=VerificationContract(
                required_live_reads=("current_object", "saved_or_published_revision", "relations"),
                acceptance_required=True,
                remediation_enabled=False,
                remediation_requires_new_user_scope=True,
            ),
            workspace=WorkspaceContract(project_root=str(root)),
            target=TargetContract(
                workbook_id="book_verify",
                dashboard_id="dash_verify",
                object_ids=("dash_verify",),
                object_types=("dashboard",),
            ),
            delivery=DeliveryContract(),
            acceptance=(
                AcceptanceCriterion(kind="existing_effect", statement='{"effect_kind":"published"}'),
            ),
        ).to_dict()
        journal = ProjectJournal(root, contract["task_id"])
        journal.initialize(contract)
        write_json(journal.execution_authorization_path, resolve_execution_authorization(contract))
        write_json(journal.reference_binding_path, {"binding_hash": "c" * 64})
        write_json(journal.style_binding_path, {"binding_hash": "d" * 64, "technology": "dashboard"})
        write_json(
            journal.target_binding_path,
            {"binding_hash": "e" * 64, "source": "live_discovery", "technology": "dashboard"},
        )
        write_json(
            journal.target_graph_path,
            {"graph_hash": "f" * 64, "nodes": [{"object_id": "dash_verify"}], "edges": []},
        )

        plan = PublicPlanBuilder(journal, contract).build_verification()
        issues = PublicPlanBuilder(journal, contract).validate_current()

    assert not issues
    assert plan["plan_kind"] == "verify_existing_effect"
    assert plan["safe_apply_action_count"] == 0
    assert plan["acceptance"]
    assert plan["delivery"] == {"save": False, "publish": False, "destructive": False}
    assert all(not item["artifact_uri"].startswith("/") for item in plan["artifacts"])
