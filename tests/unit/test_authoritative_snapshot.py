import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.mcp.tools.pipeline import dl_readback_and_report
from datalens_dev_mcp.mcp.tools.snapshot import dl_snapshot_dashboard


CHART_IDS = [f"chart_{index:02d}" for index in range(1, 19)]
DATASET_IDS = ["dataset_entities", "dataset_events", "dataset_alerts"]
CONNECTION_ID = "connection_event_source"


def dashboard_tabs():
    sizes = [4, 4, 4, 3, 3]
    cursor = 0
    tabs = []
    for tab_index, size in enumerate(sizes, start=1):
        items = []
        for chart_id in CHART_IDS[cursor : cursor + size]:
            items.append({"id": f"item_{chart_id}", "type": "chart", "chartId": chart_id})
        cursor += size
        tabs.append({"id": f"tab_{tab_index}", "title": f"Tab {tab_index}", "items": items})
    return tabs


class EventSnapshotClient:
    def __init__(self):
        self.calls = []

    def rpc(self, method, payload):
        self.calls.append((method, payload))
        if method == "getDashboard":
            branch = payload.get("branch", "saved")
            return {
                "branch": branch,
                "entry": {
                    "entryId": "dashboard_events",
                    "workbookId": "workbook_events",
                    "scope": "dashboard",
                    "revId": f"{branch}_rev",
                    "savedId": "saved_rev",
                    "data": {"tabs": dashboard_tabs(), "links": []},
                },
            }
        if method == "getWorkbookEntries":
            entries = [
                {"entryId": "dashboard_events", "scope": "dashboard", "displayKey": "Event Operations"},
                *[
                    {"entryId": chart_id, "scope": "editor_chart" if index < 10 else "wizard_chart"}
                    for index, chart_id in enumerate(CHART_IDS)
                ],
                *[{"entryId": dataset_id, "scope": "dataset"} for dataset_id in DATASET_IDS],
                {"entryId": CONNECTION_ID, "scope": "connection"},
                {"entryId": "dormant_editor", "scope": "editor_chart"},
                {"entryId": "dormant_dataset", "scope": "dataset"},
            ]
            return {"entries": entries, "workbookId": payload["workbookId"]}
        if method == "getEntriesRelations":
            relations = []
            for index, chart_id in enumerate(CHART_IDS):
                relations.append(
                    {
                        "fromEntryId": chart_id,
                        "toEntryId": DATASET_IDS[index % len(DATASET_IDS)],
                        "relationType": "dataset",
                    }
                )
            for dataset_id in DATASET_IDS:
                relations.append({"fromEntryId": dataset_id, "toEntryId": CONNECTION_ID, "relationType": "connection"})
            return {"relations": relations}
        if method == "getEditorChart":
            chart_id = payload["chartId"]
            return {
                "entry": {
                    "entryId": chart_id,
                    "scope": "editor_chart",
                    "data": {"javascript": f"function chartCode() {{ return 'select secret_sql from {chart_id}'; }}"},
                }
            }
        if method == "getWizardChart":
            chart_id = payload["chartId"]
            return {
                "entry": {
                    "entryId": chart_id,
                    "scope": "wizard_chart",
                    "data": {"query": f"select secret_sql from {chart_id}", "visualization": "line"},
                }
            }
        if method == "getDataset":
            return {
                "dataset": {
                    "datasetId": payload["datasetId"],
                    "data": {"source": {"connectionId": CONNECTION_ID}, "sql": "select secret_sql from source"},
                }
            }
        if method == "getConnection":
            return {
                "connection": {
                    "connectionId": payload["connectionId"],
                    "data": {"host": "example.invalid", "token": "Bearer should-redact"},
                }
            }
        raise AssertionError(method)


class EventPayloadOnlyDependencyClient(EventSnapshotClient):
    def rpc(self, method, payload):
        if method == "getEntriesRelations":
            self.calls.append((method, payload))
            return {"relations": []}
        if method in {"getEditorChart", "getWizardChart"}:
            self.calls.append((method, payload))
            chart_id = payload["chartId"]
            dataset_id = DATASET_IDS[CHART_IDS.index(chart_id) % len(DATASET_IDS)]
            return {
                "entry": {
                    "entryId": chart_id,
                    "scope": "wizard_chart" if method == "getWizardChart" else "editor_chart",
                    "data": {"datasetId": dataset_id, "source": {"dataset_id": dataset_id}},
                }
            }
        return super().rpc(method, payload)


class ComputeInventorySnapshotClient(EventSnapshotClient):
    def rpc(self, method, payload):
        response = super().rpc(method, payload)
        if method == "getWorkbookEntries":
            response["entries"].append({"entryId": "compute_1", "scope": "compute", "type": ""})
        if method == "getEntriesRelations":
            response["relations"].append(
                {"fromEntryId": CHART_IDS[0], "toEntryId": "compute_1", "relationType": "compute_dependency"}
            )
        return response


class MetadataFetchSnapshotClient(EventSnapshotClient):
    def rpc_readonly(self, method, payload):
        return {"result": super().rpc(method, payload)}


class MixedEditorNodeSnapshotClient:
    ACTIVE_ENTRIES = {
        "table_01": "widget table_node",
        "control_01": "widget control_node",
        "markdown_01": "widget markdown_node",
        "d3_01": "widget d3_node",
        "editor_01": "editor_chart",
        "wizard_01": "graph_wizard_node",
        "ql_01": "graph_ql_node",
    }

    def __init__(self):
        self.calls = []

    def rpc(self, method, payload):
        self.calls.append((method, payload))
        if method == "getDashboard":
            return {
                "entry": {
                    "entryId": "dashboard_mixed_nodes",
                    "workbookId": "workbook_mixed_nodes",
                    "scope": "dashboard",
                    "data": {
                        "tabs": [
                            {
                                "id": "tab_01",
                                "items": [
                                    {"type": "table", "chartId": "table_01"},
                                    {"type": "selector", "chartId": "control_01"},
                                    {"type": "markdown", "chartId": "markdown_01"},
                                    {"type": "chart", "chartId": "d3_01"},
                                    {"type": "chart", "chartId": "editor_01"},
                                    {"type": "chart", "chartId": "wizard_01"},
                                    {"type": "chart", "chartId": "ql_01"},
                                ],
                            }
                        ]
                    },
                }
            }
        if method == "getWorkbookEntries":
            return {
                "entries": [
                    {"entryId": "dashboard_mixed_nodes", "scope": "dashboard"},
                    *[
                        {"entryId": entry_id, "scope": scope}
                        for entry_id, scope in self.ACTIVE_ENTRIES.items()
                    ],
                ]
            }
        if method == "getEntriesRelations":
            return {"relations": []}
        if method == "getEditorChart":
            return {
                "entry": {
                    "entryId": payload["chartId"],
                    "scope": self.ACTIVE_ENTRIES[payload["chartId"]],
                    "data": {},
                }
            }
        if method == "getWizardChart":
            return {"entry": {"entryId": payload["chartId"], "scope": "graph_wizard_node", "data": {}}}
        if method == "getQLChart":
            return {"entry": {"entryId": payload["chartId"], "scope": "graph_ql_node", "data": {}}}
        raise AssertionError(method)


class AuthoritativeSnapshotTests(unittest.TestCase):
    def test_event_dashboard_snapshot_is_compact_deduped_and_stable(self):
        client = EventSnapshotClient()
        with tempfile.TemporaryDirectory() as tmp:
            first = dl_snapshot_dashboard(
                project_root=tmp,
                dashboard_id="dashboard_events",
                workbook_id="workbook_events",
                snapshot_branch="both",
                include_dormant_summary=True,
                artifact_retention="latest_only",
                client=client,
            )
            second = dl_snapshot_dashboard(
                project_root=tmp,
                dashboard_id="dashboard_events",
                workbook_id="workbook_events",
                snapshot_branch="both",
                include_dormant_summary=True,
                artifact_retention="latest_only",
                client=client,
            )
            manifest = json.loads(Path(first["manifest"]["path"]).read_text(encoding="utf-8"))
            artifact_paths_exist = [Path(artifact["path"]).is_file() for artifact in manifest["object_artifacts"]]

        self.assertTrue(first["ok"], first.get("errors"))
        self.assertEqual(first["model_facing_tool_calls"], 1)
        self.assertLessEqual(len(json.dumps(first, ensure_ascii=False)), 12_000)
        self.assertEqual(first["tab_count"], 5)
        self.assertEqual(first["active_chart_count"], 18)
        self.assertEqual(first["counts_by_object_type"]["editor_chart"], 10)
        self.assertEqual(first["counts_by_object_type"]["wizard_chart"], 8)
        self.assertEqual(first["counts_by_object_type"]["dataset"], 3)
        self.assertEqual(first["counts_by_object_type"]["connection"], 1)
        self.assertEqual(first["dormant_summary"]["count"], 2)
        self.assertEqual(first["manifest"]["sha256"], second["manifest"]["sha256"])
        self.assertTrue(first["branch_comparison"]["available"])
        self.assertTrue(first["branch_comparison"]["same_normalized_structure"])

        inline = json.dumps(first, ensure_ascii=False)
        self.assertNotIn("secret_sql", inline)
        self.assertNotIn("chartCode", inline)

        artifacts = manifest["object_artifacts"]
        artifact_hashes = [artifact["sha256"] for artifact in artifacts]
        self.assertEqual(len(artifact_hashes), len(set(artifact_hashes)))
        self.assertTrue(all(artifact_paths_exist))

    def test_dashboard_report_keeps_minimal_readback_cheap_and_full_readback_authoritative(self):
        minimal_client = EventSnapshotClient()
        with tempfile.TemporaryDirectory() as tmp:
            minimal = dl_readback_and_report(
                project_root=tmp,
                target="dashboard",
                dashboard_id="dashboard_events",
                branch="saved",
                readback_mode="minimal",
                client=minimal_client,
            )
            full_client = EventSnapshotClient()
            full = dl_readback_and_report(
                project_root=tmp,
                target="dashboard",
                dashboard_id="dashboard_events",
                branch="saved",
                readback_mode="full",
                client=full_client,
            )

        self.assertEqual([call[0] for call in minimal_client.calls], ["getDashboard"])
        self.assertNotIn("snapshot_manifest", minimal["readback"])
        self.assertEqual(minimal["readback"]["counts_by_object_type"]["chart"], 0)
        self.assertIn("snapshot_manifest", full["readback"])
        self.assertEqual(full["readback"]["counts_by_object_type"]["chart"], 18)
        self.assertGreaterEqual(len(full["readback"]["active_graph_edges"]), 18)
        self.assertGreater(len(full_client.calls), len(minimal_client.calls))

    def test_snapshot_uses_chart_and_dataset_payload_dependencies_when_relations_are_empty(self):
        client = EventPayloadOnlyDependencyClient()
        with tempfile.TemporaryDirectory() as tmp:
            result = dl_snapshot_dashboard(
                project_root=tmp,
                dashboard_id="dashboard_events",
                workbook_id="workbook_events",
                snapshot_branch="saved",
                include_dormant_summary=True,
                artifact_retention="latest_only",
                client=client,
            )
            manifest = json.loads(Path(result["manifest"]["path"]).read_text(encoding="utf-8"))

        self.assertTrue(result["ok"], result.get("errors"))
        self.assertEqual(result["counts_by_object_type"]["chart"], 18)
        self.assertEqual(result["counts_by_object_type"]["dataset"], 3)
        self.assertEqual(result["counts_by_object_type"]["connection"], 1)
        self.assertNotIn("dataset_entities", {item["entry_id"] for item in result["dormant_summary"]["entries"]})
        self.assertEqual(manifest["graph"]["schema_version"], "2026-06-25.dashboard_object_graph.v1")
        self.assertEqual(len(manifest["graph"]["dataset_ids"]), 3)
        self.assertEqual(manifest["graph"]["connection_ids"], [CONNECTION_ID])

    def test_compute_scope_is_preserved_in_graph_and_dormant_inventory_without_hydration(self):
        client = ComputeInventorySnapshotClient()
        with tempfile.TemporaryDirectory() as tmp:
            result = dl_snapshot_dashboard(
                project_root=tmp,
                dashboard_id="dashboard_events",
                workbook_id="workbook_events",
                snapshot_branch="saved",
                include_dormant_summary=True,
                artifact_retention="latest_only",
                client=client,
            )

        self.assertTrue(result["ok"], result.get("errors"))
        self.assertEqual(result["dormant_summary"]["counts_by_object_type"]["compute"], 1)
        self.assertFalse(result["dormant_summary"]["hydrated"])
        compute_edges = [edge for edge in result["active_graph_edges"] if edge.get("target") == "compute_1"]
        self.assertEqual(len(compute_edges), 1)
        self.assertEqual(compute_edges[0]["target_type"], "compute")
        hydrated_methods = {"getEditorChart", "getWizardChart", "getQLChart", "getDataset", "getConnection"}
        self.assertFalse(
            any(payload.get("chartId") == "compute_1" for method, payload in client.calls if method in hydrated_methods)
        )

    def test_metadata_fetch_style_result_wrappers_are_snapshot_compatible(self):
        client = MetadataFetchSnapshotClient()
        with tempfile.TemporaryDirectory() as tmp:
            result = dl_snapshot_dashboard(
                project_root=tmp,
                dashboard_id="dashboard_events",
                workbook_id="workbook_events",
                snapshot_branch="saved",
                include_dormant_summary=True,
                artifact_retention="latest_only",
                client=client,
            )
            manifest = json.loads(Path(result["manifest"]["path"]).read_text(encoding="utf-8"))

        self.assertTrue(result["ok"], result.get("errors"))
        self.assertEqual(result["tab_count"], 5)
        self.assertEqual(result["active_chart_count"], 18)
        self.assertEqual(result["counts_by_object_type"]["dataset"], 3)
        self.assertEqual(result["counts_by_object_type"]["connection"], 1)
        self.assertEqual(manifest["schema_version"], "2026-06-25.dashboard_snapshot.v1")
        self.assertEqual(manifest["graph"]["schema_version"], "2026-06-25.dashboard_object_graph.v1")

    def test_active_editor_node_scopes_are_hydrated_without_changing_other_chart_routes(self):
        client = MixedEditorNodeSnapshotClient()
        with tempfile.TemporaryDirectory() as tmp:
            result = dl_snapshot_dashboard(
                project_root=tmp,
                dashboard_id="dashboard_mixed_nodes",
                workbook_id="workbook_mixed_nodes",
                snapshot_branch="saved",
                include_dormant_summary=True,
                artifact_retention="latest_only",
                client=client,
            )
            manifest = json.loads(Path(result["manifest"]["path"]).read_text(encoding="utf-8"))

        self.assertTrue(result["ok"], result.get("errors"))
        self.assertEqual(result["active_chart_count"], 7)
        self.assertEqual(result["omissions"], [])
        self.assertEqual(result["counts_by_object_type"]["table_node"], 1)
        self.assertEqual(result["counts_by_object_type"]["control_node"], 1)
        self.assertEqual(result["counts_by_object_type"]["markdown_node"], 1)
        self.assertEqual(result["counts_by_object_type"]["d3_node"], 1)
        self.assertEqual(result["counts_by_object_type"]["editor_chart"], 1)
        self.assertEqual(result["counts_by_object_type"]["wizard_chart"], 1)
        self.assertEqual(result["counts_by_object_type"]["ql_chart"], 1)

        calls_by_method = {}
        for method, payload in client.calls:
            calls_by_method.setdefault(method, []).append(payload)
        self.assertEqual(
            {payload["chartId"] for payload in calls_by_method["getEditorChart"]},
            {"table_01", "control_01", "markdown_01", "d3_01", "editor_01"},
        )
        self.assertEqual([payload["chartId"] for payload in calls_by_method["getWizardChart"]], ["wizard_01"])
        self.assertEqual([payload["chartId"] for payload in calls_by_method["getQLChart"]], ["ql_01"])
        self.assertEqual(
            {row["object_id"]: row["object_type"] for row in manifest["graph"]["active_objects"]},
            {
                "dashboard_mixed_nodes": "dashboard",
                "table_01": "table_node",
                "control_01": "control_node",
                "markdown_01": "markdown_node",
                "d3_01": "d3_node",
                "editor_01": "editor_chart",
                "wizard_01": "wizard_chart",
                "ql_01": "ql_chart",
            },
        )


if __name__ == "__main__":
    unittest.main()
