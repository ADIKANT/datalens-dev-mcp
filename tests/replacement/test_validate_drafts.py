from __future__ import annotations

import json
from pathlib import Path

from datalens_dev_mcp import server
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
