from __future__ import annotations

import tempfile
from pathlib import Path

from datalens_dev_mcp.pipeline.browser_qa import (
    BROWSER_QA_RESULT_SCHEMA_ID,
    build_qa_attestation,
)
from tests.integration.public_proof_support import execute_public_proof_workflow, plan_ready_task


class CountingAdapter:
    def __init__(
        self,
        artifact: Path,
        *,
        wrong_revision: bool = False,
        omit_real_scroll: bool = False,
    ) -> None:
        self.artifact = artifact
        self.wrong_revision = wrong_revision
        self.omit_real_scroll = omit_real_scroll
        self.calls = 0

    def __call__(self, plan: dict) -> dict:
        self.calls += 1
        self.artifact.write_text("synthetic rendered evidence", encoding="utf-8")
        target = plan["target"]
        results = []
        for width in [item["width"] for item in plan["viewports"]]:
            for tab_id in target["tab_ids"]:
                for scroll_position in ("top", "bottom"):
                    results.append(
                        {
                            "schema_id": BROWSER_QA_RESULT_SCHEMA_ID,
                            "viewport": {"width": width, "height": 900},
                            "tab_id": tab_id,
                            "scroll_position": scroll_position,
                            "scroll_reached_bottom": (
                                scroll_position == "bottom" and not self.omit_real_scroll
                            ),
                            "loading_chart_count": 0,
                            "visible_error_count": 0,
                            "passed": True,
                            "assertions": {
                                item["id"]: True for item in plan["evaluate"]["assertions"]
                            },
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
            browser_metrics={
                "browser_calls_before_final_visual_stage": 0,
                "browser_calls_to_non_dashboard_objects": 0,
                "browser_mutation_attempts": 0,
                "browser_tabs_fully_scrolled": len(target["tab_ids"]),
            },
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
