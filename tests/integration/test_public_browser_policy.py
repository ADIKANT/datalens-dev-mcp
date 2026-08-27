from __future__ import annotations

import tempfile
from pathlib import Path

from datalens_dev_mcp.pipeline.browser_qa import (
    BROWSER_QA_ASSERTIONS,
    BROWSER_QA_RESULT_SCHEMA_ID,
    build_qa_attestation,
)
from tests.integration.public_proof_support import execute_public_proof_workflow, plan_ready_task


class CountingAdapter:
    def __init__(self, artifact: Path, *, wrong_revision: bool = False) -> None:
        self.artifact = artifact
        self.wrong_revision = wrong_revision
        self.calls = 0

    def __call__(self, plan: dict) -> dict:
        self.calls += 1
        self.artifact.write_text("synthetic rendered evidence", encoding="utf-8")
        target = plan["target"]
        results = []
        for width in (720, 1200, 1440):
            for tab_id in target["tab_ids"]:
                for scroll_position in ("top", "bottom"):
                    results.append(
                        {
                            "schema_id": BROWSER_QA_RESULT_SCHEMA_ID,
                            "viewport": {"width": width, "height": 900},
                            "tab_id": tab_id,
                            "scroll_position": scroll_position,
                            "passed": True,
                            "assertions": {item["id"]: True for item in BROWSER_QA_ASSERTIONS},
                            "observations": {"selector_clear_interactions": []},
                        }
                    )
        saved_revision = "wrong-revision" if self.wrong_revision else target["saved_revision"]
        return build_qa_attestation(
            plan=plan,
            viewport_results=results,
            dashboard_id=target["dashboard_id"],
            saved_revision=saved_revision,
            published_revision=saved_revision,
            runtime_errors=[],
            artifact_paths=[str(self.artifact)],
        )


def test_forbidden_browser_policy_makes_zero_adapter_calls() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _ = plan_ready_task(root, publish=True, browser="forbidden")
        adapter = CountingAdapter(root / "forbidden.png")
        state, _executor, _ = execute_public_proof_workflow(
            journal,
            contract,
            client,
            browser_adapter=adapter,
        )
    assert state.current_state == "COMPLETED"
    assert adapter.calls == 0


def test_required_browser_policy_blocks_when_adapter_is_unavailable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _ = plan_ready_task(root, publish=True, browser="required")
        state, _executor, _ = execute_public_proof_workflow(journal, contract, client)
    assert state.current_state == "BLOCKED"


def test_required_browser_policy_calls_once_and_accepts_exact_attestation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _ = plan_ready_task(root, publish=True, browser="required")
        adapter = CountingAdapter(root / "required.png")
        state, _executor, _ = execute_public_proof_workflow(
            journal,
            contract,
            client,
            browser_adapter=adapter,
        )
    assert state.current_state == "COMPLETED"
    assert adapter.calls == 1


def test_required_browser_policy_rejects_revision_mismatch() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        journal, contract, client, _ = plan_ready_task(root, publish=True, browser="required")
        adapter = CountingAdapter(root / "mismatch.png", wrong_revision=True)
        state, _executor, _ = execute_public_proof_workflow(
            journal,
            contract,
            client,
            browser_adapter=adapter,
        )
    assert state.current_state == "BLOCKED"
    assert adapter.calls == 1
