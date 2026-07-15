import json
import tempfile
import unittest


class OptimizedCodexWorkflowTests(unittest.TestCase):
    def test_reference_and_context_keep_one_prompt_workflow_compact(self):
        from datalens_dev_mcp.knowledge.reference import build_reference_response
        from datalens_dev_mcp.mcp.tools.pipeline import dl_start_pipeline
        from datalens_dev_mcp.server import list_tools

        with tempfile.TemporaryDirectory() as tmp:
            dl_start_pipeline(tmp, dashboard_name="Compact Workflow")
            reference = build_reference_response(mode="delivery_intent", query="обнови", max_chars=4000, project_root=tmp)
            tool_reference = build_reference_response(
                mode="tool_selection",
                query="startup",
                max_chars=4000,
                project_root=tmp,
            )
            docs_reference = build_reference_response(
                mode="current_docs_delta",
                query="dashboard tabs",
                max_chars=4000,
                project_root=tmp,
            )

        tool_chars = len(json.dumps({"tools": list_tools()}, ensure_ascii=False, separators=(",", ":")))
        self.assertLessEqual(tool_chars, 34_000)
        self.assertLessEqual(reference["response_chars"], 4000)
        self.assertLessEqual(tool_reference["response_chars"], 4000)
        self.assertLessEqual(docs_reference["response_chars"], 4000)
        self.assertEqual(reference["mode"], "delivery_intent")
        self.assertEqual(tool_reference["mode"], "tool_selection")
        self.assertEqual(docs_reference["mode"], "current_docs_delta")
        self.assertLessEqual(len(tool_reference["rules"]), 5)


if __name__ == "__main__":
    unittest.main()
