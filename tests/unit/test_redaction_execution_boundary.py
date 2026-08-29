from __future__ import annotations

from copy import deepcopy
import json
import tempfile


def test_environment_secret_classification_uses_credential_role_not_public_session_role() -> None:
    from datalens_dev_mcp.validators.redaction import secret_values_from_mapping

    public_session_id = "01b04d9d-ac5b-7102-b36b-d35e6ff58863"
    fake_iam_token = "y0_" + "a" * 32
    secrets = secret_values_from_mapping(
        {
            "WORKFLOW_SESSION_ID": public_session_id,
            "DATALENS_IAM_TOKEN": fake_iam_token,
        }
    )

    assert public_session_id not in secrets
    assert fake_iam_token in secrets


def test_public_projection_redacts_credentials_without_mutating_canonical_value_or_hash() -> None:
    from datalens_dev_mcp.pipeline.workflow_events import canonical_hash
    from datalens_dev_mcp.serialization import sanitize_response

    fake_iam_token = "y0_" + "b" * 32
    canonical = {
        "project_root": "/tmp/01b04d9d-ac5b-7102-b36b-d35e6ff58863/project",
        "object_id": "synthetic_object_123",
        "revision": "synthetic_revision_456",
        "headers": {"Authorization": f"Bearer {fake_iam_token}"},
    }
    before = deepcopy(canonical)
    digest = canonical_hash(canonical)

    projected = sanitize_response(canonical)

    assert canonical == before
    assert canonical_hash(canonical) == digest
    assert projected["project_root"] == canonical["project_root"]
    assert projected["object_id"] == canonical["object_id"]
    assert projected["revision"] == canonical["revision"]
    assert projected["headers"]["Authorization"] == "<redacted>"


def test_workflow_input_hash_binds_canonical_value_not_sanitized_projection() -> None:
    from datalens_dev_mcp.pipeline.workflow_events import canonical_hash, create_workflow_event

    canonical_input = {
        "project_root": "/tmp/01b04d9d-ac5b-7102-b36b-d35e6ff58863/project",
        "object_id": "synthetic_object_123",
        "expected_revision": "synthetic_revision_456",
    }
    event = create_workflow_event(
        event_id=1,
        previous_hash="",
        task_id="synthetic-task",
        transition="RESOLVED -> BASELINE_READ",
        input_value=canonical_input,
        result_receipt="artifact://synthetic",
        status="success",
        timestamp="2026-08-29T00:00:00Z",
        idempotency_key="synthetic-idempotency",
    )

    assert event["input_hash"] == canonical_hash(canonical_input)


def test_task_resource_redacts_projected_copy_without_rewriting_canonical_receipt() -> None:
    from datalens_dev_mcp.mcp.task_resources import read_task_resource, task_resource_uri
    from datalens_dev_mcp.pipeline.artifacts import read_json
    from datalens_dev_mcp.pipeline.project_journal import ProjectJournal
    from datalens_dev_mcp.pipeline.task_contract import WorkspaceContract, create_task_contract

    fake_iam_token = "y0_" + "c" * 32
    with tempfile.TemporaryDirectory() as tmp:
        contract = create_task_contract(
            raw_request="Review a synthetic target",
            mode="review",
            route="read_only",
            workspace=WorkspaceContract(project_root=tmp),
        ).to_dict()
        journal = ProjectJournal(tmp, contract["task_id"])
        journal.initialize(contract)
        receipt_uri = journal.write_receipt(
            "projection-boundary",
            {
                "object_id": "synthetic_object_123",
                "revision": "synthetic_revision_456",
                "authorization": f"Bearer {fake_iam_token}",
            },
        )
        relative = receipt_uri.split(f"artifact://tasks/{journal.task_id}/", 1)[1]
        canonical_path = journal.root / relative
        before = read_json(canonical_path, {})

        resource = read_task_resource(
            task_resource_uri(journal.task_id, relative),
            project_root=tmp,
        )
        projected = json.loads(resource["text"])
        after = read_json(canonical_path, {})

    assert before == after
    assert after["authorization"] == f"Bearer {fake_iam_token}"
    assert projected["authorization"] == "<redacted>"
    assert projected["object_id"] == after["object_id"]
    assert projected["revision"] == after["revision"]
