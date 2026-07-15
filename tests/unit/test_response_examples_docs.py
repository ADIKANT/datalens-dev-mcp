import json
import unittest
from pathlib import Path


class ResponseExamplesDocsTests(unittest.TestCase):
    def test_response_contract_examples_are_valid_json(self):
        for path in sorted(Path("examples/response_contracts").glob("*.json")):
            with self.subTest(path=path):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)

    def test_response_docs_cover_required_scenarios(self):
        response_contracts = Path("docs/mcp/response_contracts.md").read_text(encoding="utf-8")
        model_examples = Path("docs/datalens/model_response_examples.md").read_text(encoding="utf-8")
        combined = response_contracts + "\n" + model_examples

        for phrase in [
            "Requirements Ingestion",
            "Dashboard Planning",
            "Wizard Standard Chart",
            "Advanced Editor JS",
            "Dataset/Connector/Field",
            "Selector Relation",
            "Safe Apply plan",
            "Missing Input",
            "BLOCKED_LIVE_CREDENTIALS",
            "source_static",
        ]:
            self.assertIn(phrase, combined)

    def test_implemented_charts_docs_include_native_metadata(self):
        docs = Path("docs/datalens/implemented_charts.md").read_text(encoding="utf-8")

        self.assertIn("native title/hint", docs.lower())
        self.assertIn("hideTitle", docs)
        self.assertIn("enableHint", docs)


if __name__ == "__main__":
    unittest.main()
