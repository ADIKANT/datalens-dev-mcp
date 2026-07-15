import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ["scripts", "src", "tests", "config", "schemas", "templates", "docs"]
SKIP_PARTS = {
    ".git",
    "__pycache__",
    "artifacts",
    "docs/reports",
}
SKIP_FILES = {
    "config/datalens_mcp.local.json",
    "config/datalens_mcp.local.example.json",
}


class PortableTempPathTests(unittest.TestCase):
    def test_source_tree_has_no_hardcoded_user_or_private_tmp_paths(self):
        forbidden = ["/private" + "/tmp", "/Users" + "/alexandr"]
        hits = []
        for root_name in SCAN_ROOTS:
            root = ROOT / root_name
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix not in {".py", ".md", ".json", ".jsonl", ".js"}:
                    continue
                rel = path.relative_to(ROOT).as_posix()
                if rel in SKIP_FILES or any(rel == part or rel.startswith(part + "/") for part in SKIP_PARTS):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for pattern in forbidden:
                    if pattern in text:
                        hits.append(f"{rel}: {pattern}")

        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
