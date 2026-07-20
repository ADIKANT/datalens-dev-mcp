import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOWER_LAYER_DIRS = ("editor", "knowledge", "pipeline", "validators")
FORBIDDEN_PREFIX = "datalens_dev_mcp.mcp"


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_layers_do_not_import_mcp_transport_layer(self):
        violations: list[str] = []
        for directory in LOWER_LAYER_DIRS:
            for path in sorted((ROOT / "src" / "datalens_dev_mcp" / directory).rglob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        imported = node.module or ""
                        if imported == FORBIDDEN_PREFIX or imported.startswith(f"{FORBIDDEN_PREFIX}."):
                            violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {imported}")
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name == FORBIDDEN_PREFIX or alias.name.startswith(f"{FORBIDDEN_PREFIX}."):
                                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {alias.name}")

        self.assertEqual(
            violations,
            [],
            "Domain layers must depend on neutral modules, not the MCP transport layer:\n"
            + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
