from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from datalens_dev_mcp.objects.read import ObjectReadService
from datalens_dev_mcp.objects.relations import compact_object_index
from datalens_dev_mcp.server import list_tools


class FakeApi:
    def __init__(self, replies: dict[str, list[dict[str, Any]]]) -> None:
        self.replies = {name: list(values) for name, values in replies.items()}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def read(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((method, dict(payload)))
        return self.replies[method].pop(0)


class FakeSdk:
    def __init__(self, objects: dict[tuple[str, str, str], dict[str, Any]]) -> None:
        self.objects = objects
        self.calls: list[tuple[str, str, str, str | None]] = []

    def get_object(
        self,
        object_type: str,
        object_id: str,
        *,
        branch: str = "saved",
        revision_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((object_type, object_id, branch, revision_id))
        return self.objects[(object_type, object_id, branch)]


def test_workbook_entries_follow_all_pages_and_report_completeness() -> None:
    api = FakeApi(
        {
            "getWorkbookEntries": [
                {"entries": [{"entryId": "b", "scope": "dataset"}], "nextPageToken": "next-1"},
                {"entries": [{"entryId": "a", "scope": "dash"}]},
            ]
        }
    )
    service = ObjectReadService(api=api, sdk=FakeSdk({}))

    result = service.workbook_entries("wb-1", page_size=1, max_pages=4)

    assert result["complete"] is True
    assert result["page_count"] == 2
    assert [item["id"] for item in result["objects"]] == ["a", "b"]
    assert api.calls == [
        ("getWorkbookEntries", {"workbookId": "wb-1", "pageSize": 1}),
        ("getWorkbookEntries", {"workbookId": "wb-1", "pageSize": 1, "pageToken": "next-1"}),
    ]


def test_workbook_entries_are_explicitly_partial_at_bound() -> None:
    api = FakeApi({"getWorkbookEntries": [{"entries": [{"entryId": "a", "scope": "dash"}], "nextPageToken": "next-1"}]})
    result = ObjectReadService(api=api, sdk=FakeSdk({})).workbook_entries("wb-1", max_pages=1)
    assert result["complete"] is False
    assert result["partial_reason"] == "page_limit_reached"
    assert result["next_page_token"] == "next-1"


def test_typed_object_get_preserves_requested_branch_and_revision() -> None:
    sdk = FakeSdk({("wizard_chart", "chart-1", "published"): {"id": "chart-1", "rev_id": "rev-7"}})
    result = ObjectReadService(api=FakeApi({}), sdk=sdk).object_get(
        "wizard_chart", "chart-1", branch="published", revision_id="rev-7"
    )
    assert result["identity"] == {
        "object_type": "wizard_chart",
        "object_id": "chart-1",
        "branch": "published",
        "revision_id": "rev-7",
    }
    assert sdk.calls == [("wizard_chart", "chart-1", "published", "rev-7")]


def test_unbranched_object_reports_actual_semantics() -> None:
    sdk = FakeSdk({("dataset", "dataset-1", "published"): {"id": "dataset-1", "revId": "rev-2"}})
    result = ObjectReadService(api=FakeApi({}), sdk=sdk).object_get("dataset", "dataset-1", branch="published")
    assert result["identity"]["branch"] == "unbranched"


@pytest.mark.parametrize(
    ("branch", "expected"),
    [("saved", "saved-rev"), ("published", "published-rev")],
)
def test_dashboard_revision_is_read_from_nested_entry(branch: str, expected: str) -> None:
    payload = {
        "entry": {
            "entryId": "dash-1",
            "savedId": "saved-rev",
            "publishedId": "published-rev",
            "data": {"tabs": []},
        }
    }
    sdk = FakeSdk({("dashboard", "dash-1", branch): payload})

    result = ObjectReadService(api=FakeApi({}), sdk=sdk).object_get("dashboard", "dash-1", branch=branch)

    assert result["identity"]["revision_id"] == expected


def test_object_relations_follow_provider_page_tokens() -> None:
    api = FakeApi(
        {
            "getEntriesRelations": [
                {"relations": [{"entryId": "chart-1", "scope": "wizard_chart"}], "nextPageToken": "p2"},
                {"relations": [{"entryId": "dataset-1", "scope": "dataset"}]},
            ]
        }
    )
    result = ObjectReadService(api=api, sdk=FakeSdk({})).object_relations("dash-1", page_size=1)
    assert result["complete"] is True
    assert [item["id"] for item in result["relations"]] == ["chart-1", "dataset-1"]
    assert api.calls[-1][1]["pageToken"] == "p2"


def test_dashboard_snapshot_reads_only_relation_dependencies() -> None:
    sdk = FakeSdk(
        {
            ("dashboard", "dash-1", "saved"): {
                "id": "dash-1",
                "workbook_id": "wb-1",
                "rev_id": "dash-rev",
                "data": {"tabs": [{"id": "tab-1", "items": [{"chartId": "chart-1"}]}]},
            },
            ("wizard_chart", "chart-1", "saved"): {
                "id": "chart-1",
                "data": {"datasetId": "dataset-1"},
            },
            ("dataset", "dataset-1", "saved"): {"id": "dataset-1", "result_schema": []},
        }
    )
    api = FakeApi(
        {
            "getEntriesRelations": [
                {
                    "entries": [
                        {"entryId": "chart-1", "scope": "wizard"},
                        {"entryId": "dataset-1", "scope": "dataset"},
                    ]
                }
            ]
        }
    )
    result = ObjectReadService(api=api, sdk=sdk).dashboard_snapshot("dash-1", branch="saved")

    assert result["complete"] is True
    assert [item["identity"]["object_id"] for item in result["dependencies"]] == ["chart-1", "dataset-1"]
    assert [call[1] for call in sdk.calls] == ["dash-1", "chart-1", "dataset-1"]
    assert all(method != "getWorkbookEntries" for method, _ in api.calls)


def test_reference_is_never_substituted_for_target() -> None:
    sdk = FakeSdk(
        {
            ("dashboard", "target", "saved"): {"id": "target", "data": {}},
            ("dashboard", "reference", "saved"): {"id": "reference", "data": {}},
        }
    )
    api = FakeApi({"getEntriesRelations": [{"entries": []}, {"entries": []}]})
    service = ObjectReadService(api=api, sdk=sdk)
    result = service.dashboard_snapshot("target", reference_dashboard_id="reference")
    assert result["target"]["identity"]["object_id"] == "target"
    assert result["reference"]["identity"]["object_id"] == "reference"


def test_reads_create_no_project_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    sdk = FakeSdk({("dataset", "dataset-1", "saved"): {"id": "dataset-1"}})
    ObjectReadService(api=FakeApi({}), sdk=sdk).object_get("dataset", "dataset-1")
    assert list(tmp_path.iterdir()) == []


def test_compact_index_does_not_inline_payloads() -> None:
    result = compact_object_index(
        [{"entryId": "chart-1", "scope": "wizard", "name": "Synthetic chart", "data": {"large": "x" * 1000}}]
    )
    assert result == [{"id": "chart-1", "type": "wizard", "name": "Synthetic chart"}]


def test_l03_tools_are_direct_and_closed() -> None:
    schemas = {tool["name"]: tool for tool in list_tools()}
    for name in (
        "dl_workbooks_list",
        "dl_workbook_entries",
        "dl_object_get",
        "dl_object_relations",
        "dl_dashboard_snapshot",
    ):
        assert schemas[name]["annotations"]["readOnlyHint"] is True
        assert schemas[name]["inputSchema"]["additionalProperties"] is False
    json.dumps(schemas, sort_keys=True)


def test_inspect_skill_routes_reads_without_legacy_state() -> None:
    root = Path(__file__).resolve().parents[2]
    skill = (root / "skills/datalens-inspect/SKILL.md").read_text(encoding="utf-8")
    reference = (root / "skills/datalens-inspect/references/direct-reads.md").read_text(encoding="utf-8")
    assert "legacy manifest" in skill
    assert "dl_dashboard_snapshot" in reference
    assert "target" in reference and "reference" in reference
