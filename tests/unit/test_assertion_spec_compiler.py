from __future__ import annotations

from datalens_dev_mcp.pipeline.assertion_spec_compiler import AssertionSpecCompiler
from datalens_dev_mcp.pipeline.task_data_proof_service import _sanitize_assertions


def test_compiler_binds_fresh_assertions_to_planning_and_target_hashes() -> None:
    contract = {
        "task_id": "task_demo",
        "contract_hash": "a" * 64,
        "acceptance": [
            {
                "kind": "no_nulls",
                "statement": '{"fields":["guid_metric"]}',
                "hard": True,
            }
        ],
    }
    probe_plan = {
        "dataset_id": "dataset_demo",
        "field_catalog": [{"guid": "guid_metric", "name": "Metric", "type": "float"}],
        "queries": [
            {
                "payload": {
                    "datasetId": "dataset_demo",
                    "workbookId": "book_demo",
                    "columns": ["guid_metric"],
                    "filters": [],
                    "params": [],
                    "sort": [],
                    "limit": 100,
                },
                "paging": {"tie_breaker_fields": []},
            }
        ],
    }
    compiled = AssertionSpecCompiler().compile(
        contract,
        probe_plan,
        planning_profile={"profile_hash": "b" * 64, "query_set_hash": "c" * 64, "schema_hash": "d" * 64},
        target_binding={"binding_hash": "e" * 64},
    )

    assert compiled["ok"] is True
    assert compiled["fresh_required"] is True
    assert compiled["assertions"][0] == {"kind": "not_empty", "scope": "sample"}
    assert compiled["assertions"][1]["kind"] == "no_nulls"
    assert compiled["planning_profile_hash"] == "b" * 64


def test_compiler_rejects_unknown_field_guid_without_guessing() -> None:
    compiled = AssertionSpecCompiler().compile(
        {
            "task_id": "task_demo",
            "contract_hash": "a" * 64,
            "acceptance": [{"kind": "unique_key", "statement": '{"fields":["missing"]}', "hard": True}],
        },
        {
            "dataset_id": "dataset_demo",
            "field_catalog": [{"guid": "known", "name": "Known", "type": "string"}],
            "queries": [{"payload": {"datasetId": "dataset_demo", "columns": ["known"]}, "paging": {}}],
        },
        planning_profile={"profile_hash": "b" * 64, "query_set_hash": "c" * 64, "schema_hash": "d" * 64},
        target_binding={"binding_hash": "e" * 64},
    )
    assert compiled["ok"] is False
    assert compiled["issues"] == ["assertion references unknown field GUID: missing"]


def test_sensitive_assertion_metrics_keep_counts_but_redact_values() -> None:
    sanitized = _sanitize_assertions(
        [
            {
                "kind": "value_domain",
                "status": "failed",
                "explanation": "Assertion failed",
                "metrics": {"outside_domain": ["secret-value"], "outside_count": 1},
            }
        ],
        {"value_domain"},
    )
    assert sanitized[0]["metrics"] == {
        "outside_count": 1,
        "values_redacted_or_hashed": True,
    }
    assert "secret-value" not in str(sanitized)
