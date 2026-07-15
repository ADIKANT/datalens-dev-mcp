from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from datalens_dev_mcp.server import JsonRpcServer, TOOLS, list_tools


class ProjectContextContractTests(unittest.TestCase):
    def test_memory_bank_tools_are_internal_python_compatibility_only(self) -> None:
        all_names = {tool["name"] for tool in list_tools("all")}
        self.assertNotIn("dl_load_project_context", TOOLS)
        self.assertNotIn("dl_update_project_memory", TOOLS)
        self.assertNotIn("dl_load_project_context", all_names)
        self.assertNotIn("dl_update_project_memory", all_names)

    def test_context_and_metadata_evidence_flow_into_hash_bound_plan_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            metadata_artifact = root / "artifacts" / "metadata_fetch" / "run.json"
            metadata_artifact.parent.mkdir(parents=True)
            metadata_artifact.write_text('{"ok":true}\n', encoding="utf-8")
            metadata_hash = hashlib.sha256(metadata_artifact.read_bytes()).hexdigest()
            context_ref = {
                "schema_version": "project_context_ref.v1",
                "workspace_root": str(root),
                "workspace_id": "fixture",
                "context_id": "ctx_fixture",
                "index_sha256": "a" * 64,
                "task": "plan a dashboard",
                "issued_at": "2026-07-14T00:00:00Z",
            }
            metadata_ref = {
                "schema_version": "evidence_ref.v1",
                "producer": "metadata-fetch",
                "workspace_root": str(root),
                "run_id": "metadata_fixture",
                "kind": "dashboard_context",
                "scope": "fixture",
                "artifact_path": metadata_artifact.relative_to(root).as_posix(),
                "sha256": metadata_hash,
                "generated_at": "2026-07-14T00:00:00Z",
                "freshness": "current",
                "summary": "Offline fixture evidence.",
            }
            server = JsonRpcServer(project_root=str(root))
            response = server._call_tool(
                {
                    "name": "dl_build_payload_plan",
                    "arguments": {
                        "project_root": str(root),
                        "workbook_id": "workbook_fixture",
                        "context_ref": context_ref,
                        "evidence_refs": [metadata_ref],
                    },
                }
            )
            body = json.loads(response["content"][0]["text"])

            self.assertFalse(response["isError"], body)
            self.assertEqual(body["project_context"]["context_id"], "ctx_fixture")
            self.assertEqual(body["consumed_evidence"][0]["sha256"], metadata_hash)
            produced = body["evidence_refs"][0]
            produced_path = root / produced["artifact_path"]
            self.assertEqual(produced["schema_version"], "evidence_ref.v1")
            self.assertEqual(produced["producer"], "datalens-dev-mcp")
            self.assertEqual(produced["sha256"], hashlib.sha256(produced_path.read_bytes()).hexdigest())
            self.assertTrue(body["suggested_records"])
            self.assertFalse((root / "AGENTS.md").exists())
            self.assertFalse((root / "memory-bank").exists())


if __name__ == "__main__":
    unittest.main()
