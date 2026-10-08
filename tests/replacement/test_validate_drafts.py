from __future__ import annotations

import json
from pathlib import Path

from datalens_dev_mcp import server
from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.editor.validation import validate_editor_draft
from datalens_dev_mcp.sdk import validate_drafts

VALID_WIZARD = {
    "client_ref": "table",
    "object_type": "wizard_chart",
    "name": "Synthetic table",
    "wizard": {
        "dataset_id": "synthetic-dataset",
        "visualization": "flat_table",
        "roles": {"columns": ["synthetic-field"]},
    },
}

VALID_EDITOR = {
    "client_ref": "advanced",
    "object_type": "advanced-chart_node",
    "name": "Synthetic advanced chart",
    "variant": "advanced-chart_node",
    "tabs": {
        "meta.json": "{}",
        "params.js": "module.exports = {};",
        "sources.js": "module.exports = {};",
        "prepare.js": "module.exports = {};",
        "controls.js": "module.exports = {};",
    },
    "source_aliases": [],
}


VALID_DATASET = {
    "client_ref": "dataset",
    "object_type": "dataset",
    "name": "Synthetic dataset",
    "dataset": {
        "connection_id": "connection-synthetic",
        "source": {
            "alias": "Synthetic events",
            "source_type": "CH_SUBSELECT",
            "parameters": {"manual": True, "subsql": "SELECT 1 AS value"},
        },
        "fields": [
            {
                "guid": "value-guid",
                "title": "Value",
                "kind": "measure",
                "source": "value",
                "aggregation": "sum",
            }
        ],
    },
}


VALID_TYPED_DASHBOARD = {
    "client_ref": "dashboard",
    "object_type": "dashboard",
    "name": "Synthetic dashboard",
    "dashboard": {
        "tabs": [
            {
                "title": "Overview",
                "tab_id": "overview",
                "items": [
                    {
                        "kind": "chart", "hint": "Sum within the selected date scope.",
                        "chart_id": "chart-synthetic",
                        "title": "Synthetic chart",
                        "item_id": "chart",
                        "at": [0, 0, 12, 8],
                    }
                ],
            }
        ],
        "settings": {"hide_dash_title": False},
    },
}


def test_validate_drafts_reports_empty_batch_without_provider_writes() -> None:
    result = validate_drafts([])

    assert result == {
        "ok": False,
        "items": [],
        "errors": [
            {
                "code": "batch_empty",
                "path": "drafts",
                "message": "validate_drafts requires at least one draft",
            }
        ],
        "provider_writes": 0,
        "proof_level": "static_validity_only",
    }


def test_validate_drafts_keeps_valid_neighbor_when_other_types_fail() -> None:
    malformed = {
        "client_ref": "broken",
        "object_type": "wizard_chart",
        "name": "Broken chart",
        "wizard": {"visualization": "flat_table", "roles": {}},
    }
    unknown = {"client_ref": "other", "object_type": "arbitrary_html", "name": "Other"}

    result = validate_drafts([VALID_WIZARD, malformed, unknown])

    assert result["ok"] is False
    assert [item["status"] for item in result["items"]] == ["valid", "invalid", "unsupported"]
    assert [item["client_ref"] for item in result["items"]] == ["table", "broken", "other"]
    assert result["items"][1]["errors"][0]["code"] == "wizard_dataset_missing"
    assert result["items"][2]["errors"][0]["code"] == "object_type_unsupported"
    assert result["provider_writes"] == 0


def test_validate_drafts_requires_typed_dataset_members_under_dataset() -> None:
    misplaced = {
        "client_ref": "dataset",
        "object_type": "dataset",
        "name": "Misplaced dataset",
        **VALID_DATASET["dataset"],
    }

    result = validate_drafts([misplaced])

    assert result["ok"] is False
    assert result["items"][0]["errors"] == [
        {
            "code": "dataset_contract_missing",
            "path": "dataset",
            "message": "Dataset draft requires a nested dataset object or a provider snapshot",
        }
    ]


def test_validate_drafts_checks_typed_dataset_source_before_provider_write() -> None:
    malformed = {
        **VALID_DATASET,
        "dataset": {
            **VALID_DATASET["dataset"],
            "connection_id": "",
            "source": {"alias": "", "source_type": "", "parameters": []},
        },
    }

    result = validate_drafts([malformed])

    assert result["ok"] is False
    assert {(error["code"], error["path"]) for error in result["items"][0]["errors"]} == {
        ("dataset_connection_missing", "dataset/connection_id"),
        ("dataset_source_alias_missing", "dataset/source/alias"),
        ("dataset_source_type_missing", "dataset/source/source_type"),
        ("dataset_source_parameters_invalid", "dataset/source/parameters"),
    }


def test_validate_drafts_accepts_complete_typed_dataset_contract() -> None:
    result = validate_drafts([VALID_DATASET])

    assert result["ok"] is True
    assert result["items"][0]["checks"] == ["dataset_static_contract"]


def test_validate_drafts_rejects_typed_dashboard_type_and_split_geometry() -> None:
    malformed = {
        **VALID_TYPED_DASHBOARD,
        "dashboard": {
            "tabs": [
                {
                    "title": "Overview",
                    "items": [
                        {
                            "type": "chart",
                            "chart_id": "chart-synthetic",
                            "title": "Synthetic chart",
                            "x": 0,
                            "y": 0,
                            "w": 12,
                            "h": 8,
                        }
                    ],
                }
            ]
        },
    }

    result = validate_drafts([malformed])

    assert result["ok"] is False
    assert {(error["code"], error["path"]) for error in result["items"][0]["errors"]} == {
        ("dashboard_item_kind_invalid", "dashboard/tabs/0/items/0/kind"),
        ("dashboard_item_at_invalid", "dashboard/tabs/0/items/0/at"),
    }


def test_validate_drafts_accepts_complete_typed_dashboard_contract() -> None:
    result = validate_drafts([VALID_TYPED_DASHBOARD])

    assert result["ok"] is True
    assert result["items"][0]["checks"] == ["dashboard_static_contract"]


def test_validate_drafts_rejects_wizard_setting_not_supported_by_builder() -> None:
    result = validate_drafts(
        [
            {
                **VALID_WIZARD,
                "wizard": {**VALID_WIZARD["wizard"], "params": {"priority_filter": "All"}},
            }
        ]
    )

    assert result["ok"] is False
    errors = result["items"][0]["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == "wizard_setting_unsupported"
    assert errors[0]["path"] == "wizard/params"
    assert errors[0]["message"].startswith("unsupported Wizard setting: params; allowed:")


def test_validate_drafts_requires_selector_parameter_in_every_declared_consumer() -> None:
    matrix = compile_recipe(
        "comparison_matrix",
        {
            "rows": [{"field_guid": "priority"}],
            "metric": {"field_guid": "current"},
            "prepared_data": {"rows": [{"label": "Blocker", "current": 3, "previous": 2}]},
        },
    )["draft"]
    matrix.update(client_ref="matrix", name="Matrix")
    selector = compile_recipe(
        "selector",
        {
            "parameter": {"name": "priority_filter", "default": []},
            "options": ["Blocker"],
            "consumers": ["matrix"],
        },
    )["draft"]
    selector.update(client_ref="selector", name="Selector")

    result = validate_drafts([matrix, selector])

    assert result["ok"] is False
    assert result["items"][1]["errors"][-1] == {
        "code": "selector_consumer_parameter_unbound",
        "path": "drafts/1/bindings/consumers/0",
        "message": "consumer matrix does not declare selector parameter priority_filter",
    }


def test_validate_drafts_accepts_dataset_source_consumer_with_matching_parameter() -> None:
    matrix = compile_recipe(
        "comparison_matrix",
        {
            "dataset_id": "dataset-synthetic",
            "fields": [
                {"guid": "priority", "title": "Priority"},
                {"guid": "current", "title": "Current"},
                {"guid": "previous", "title": "Previous"},
            ],
            "rows": [{"field_guid": "priority"}],
            "metric": {"field_guid": "current"},
            "comparison": {"field_guid": "previous"},
            "selectors": [
                {
                    "param_name": "priority_filter",
                    "field_guid": "priority",
                    "default": [],
                    "empty_selection": "all",
                }
            ],
        },
    )["draft"]
    matrix.update(client_ref="matrix", name="Matrix")
    selector = compile_recipe(
        "selector",
        {
            "parameter": {"name": "priority_filter", "default": []},
            "options": ["Blocker"],
            "consumers": ["matrix"],
        },
    )["draft"]
    selector.update(client_ref="selector", name="Selector")

    result = validate_drafts([matrix, selector])

    assert result["ok"] is True


def test_validate_drafts_resolves_inline_and_artifact_inputs_compactly(tmp_path: Path) -> None:
    artifact = tmp_path / "advanced.json"
    artifact.write_text(json.dumps(VALID_EDITOR), encoding="utf-8")

    result = validate_drafts([VALID_WIZARD, {"artifact_path": str(artifact), "client_ref": "from-file"}])

    assert result["ok"] is True
    assert [(item["index"], item["client_ref"], item["object_type"], item["status"]) for item in result["items"]] == [
        (0, "table", "wizard_chart", "valid"),
        (1, "from-file", "advanced-chart_node", "valid"),
    ]
    assert "tabs" not in result["items"][1]
    assert result["items"][1]["checks"] == ["artifact_resolved", "editor_static_contract"]


def test_validate_drafts_returns_missing_artifact_as_one_item_error(tmp_path: Path) -> None:
    result = validate_drafts([VALID_WIZARD, {"artifact_path": str(tmp_path / "missing.json"), "client_ref": "missing"}])

    assert [item["status"] for item in result["items"]] == ["valid", "invalid"]
    assert result["items"][1]["errors"][0]["code"] == "artifact_unreadable"
    assert result["provider_writes"] == 0


def test_validate_drafts_marks_duplicate_missing_and_cyclic_dependencies() -> None:
    duplicate = validate_drafts([VALID_WIZARD, {**VALID_EDITOR, "client_ref": "table"}])
    missing = validate_drafts([{**VALID_EDITOR, "depends_on": ["absent"]}])
    cyclic = validate_drafts(
        [
            {**VALID_WIZARD, "client_ref": "a", "depends_on": ["b"]},
            {**VALID_EDITOR, "client_ref": "b", "depends_on": ["a"]},
        ]
    )

    assert [item["status"] for item in duplicate["items"]] == ["invalid", "invalid"]
    assert {error["code"] for item in duplicate["items"] for error in item["errors"]} == {"client_ref_duplicate"}
    assert missing["items"][0]["errors"][0]["code"] == "dependency_missing"
    assert {error["code"] for item in cyclic["items"] for error in item["errors"]} == {"dependency_cycle"}


def test_mcp_and_python_facade_share_batch_validation_while_single_editor_validation_remains() -> None:
    assert server.dl_editor_validate(drafts=[VALID_WIZARD]) == validate_drafts([VALID_WIZARD])
    assert validate_editor_draft(VALID_EDITOR)["ok"] is True
    tool = {item["name"]: item for item in server.list_tools()}["dl_editor_validate"]
    assert tool["inputSchema"]["oneOf"] == [{"required": ["draft"]}, {"required": ["drafts"]}]
    assert tool["annotations"]["readOnlyHint"] is True


def test_wizard_rejected_shape_supplies_allowed_values_for_one_repair():
    from copy import deepcopy

    draft = deepcopy(VALID_WIZARD)
    draft['wizard']['visualization'] = 'flatTable'
    draft['wizard']['columns'] = ['synthetic-field']
    response = server.call_tool('dl_editor_validate', {'drafts': [draft]})['structuredContent']
    errors = {error['path']: error['message'] for error in response['items'][0]['errors']}
    assert 'allowed:' in errors['wizard/visualization']
    assert 'flat_table' in errors['wizard/visualization']
    assert 'allowed:' in errors['wizard/columns']
    assert 'roles' in errors['wizard/columns']
    del draft['wizard']['columns']
    draft['wizard']['visualization'] = 'flat_table'
    repaired = server.call_tool('dl_editor_validate', {'drafts': [draft]})['structuredContent']
    assert repaired['ok'] and repaired['provider_writes'] == 0



def test_dashboard_wire_preparation_uses_actual_sdk_without_dispatch(tmp_path, monkeypatch):
    import hashlib

    import httpx

    from datalens_dev_mcp.api import sdk_adapter
    from datalens_dev_mcp.api.sdk_adapter import SdkAdapter
    from datalens_dev_mcp.config import DataLensConfig

    draft = {"client_ref": "rates", "object_type": "dashboard", "name": "Synthetic rates",
             "dashboard": {"tabs": [{"tab_id": "rates", "title": "Rates", "items": [
                 {"kind": "selector_group", "item_id": "rates", "at": [0, 0, 36, 4],
                  "members": [{"item_id": "rate_" + key, "title": key, "param_name": "rate_" + key,
                               "element": "input", "default_value": value, "required": True}
                              for key, value in zip("abc", ["50", "10", "100"])]}]}]}}
    requests = []
    original = sdk_adapter._ConfiguredHTTPClient
    def handle(request):
        requests.append(request)
        return httpx.Response(500, json={"code": "INTERNAL_ERROR"})
    monkeypatch.setattr(sdk_adapter, "_ConfiguredHTTPClient",
                        lambda *a, **kw: original(*a, **kw, transport=httpx.MockTransport(handle)))
    result = server.dl_editor_validate(drafts=[draft], destination={"workbook_id": "synthetic"},
                                       output_dir=str(tmp_path))
    assert result["ok"] and result["proof_level"] == "static_validity_only"
    assert requests == [] and result["provider_writes"] == 0
    prepared = result["items"][0]["prepared_request"]
    artifact = Path(prepared["artifact_path"])
    wire = artifact.read_bytes()
    assert artifact.stat().st_mode & 0o777 == 0o600
    assert hashlib.sha256(wire).hexdigest() == prepared["request_sha256"]
    group = json.loads(wire)["entry"]["data"]["tabs"][0]["items"][0]["data"]["group"]
    assert [m["source"]["defaultValue"] for m in group] == ["50", "10", "100"]
    assert all("fieldType" not in m["source"] for m in group)
    adapter = SdkAdapter(DataLensConfig(org_id="synthetic", iam_token="synthetic"))
    try:
        import pytest

        from datalens_dev_mcp.api.errors import DataLensApiError
        with pytest.raises(DataLensApiError):
            adapter.create(draft, {"workbook_id": "synthetic"})
    finally:
        adapter.close()
    assert len(requests) == 1 and requests[0].content == wire
