from __future__ import annotations

from pathlib import Path
import tempfile

from datalens_dev_mcp.pipeline.reference_style_service import ReferenceStyleService
from datalens_dev_mcp.pipeline.task_contract import ReferenceContract, WorkspaceContract, create_task_contract


def _contract(root: Path, *, locator: str, exact: bool = True) -> dict:
    return create_task_contract(
        raw_request="Use the exact synthetic style",
        mode="update",
        route="editor_advanced",
        workspace=WorkspaceContract(project_root=str(root)),
        reference=ReferenceContract(
            kind="portfolio_object",
            locator=locator,
            required_exact_style=exact,
        ),
    ).to_dict()


def test_exact_portfolio_style_binds_tabs_and_protected_runtime() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bundle = root / "portfolio" / "trend"
        bundle.mkdir(parents=True)
        (bundle / "meta.json").write_text('{"title":"Synthetic"}\n', encoding="utf-8")
        (bundle / "sources.js").write_text("module.exports = {main: {data: []}};\n", encoding="utf-8")
        (bundle / "prepare.js").write_text(
            "function render(rows) { return rows; }\nmodule.exports = render;\n",
            encoding="utf-8",
        )
        result = ReferenceStyleService().bind(
            _contract(root, locator=str(bundle)),
            target_graph={"nodes": [], "root_ids": []},
            baselines={},
            portfolio_root=str(root / "portfolio"),
        )
    assert result["status"] == "success"
    assert result["reference_binding"]["source_kind"] == "portfolio_path"
    assert result["style_binding"]["tab_order"] == ["meta.json", "sources.js", "prepare.js"]
    assert result["style_binding"]["protected_runtime_hash"]
    assert result["style_binding"]["binding_hash"]


def test_reference_path_outside_allowed_workspace_is_blocked() -> None:
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
        root = Path(tmp)
        result = ReferenceStyleService().bind(
            _contract(root, locator=outside),
            target_graph={"nodes": [], "root_ids": []},
            baselines={},
            portfolio_root=str(root),
        )
    assert result["status"] == "blocked"
    assert "outside" in result["reason"]


def test_exact_live_reference_url_is_resolved_to_fresh_graph_object() -> None:
    target_graph = {
        "root_ids": ["target_chart"],
        "graph_hash": "t" * 64,
        "nodes": [
            {
                "object_type": "editor_chart",
                "object_id": "target_chart",
                "technology": "editor_advanced",
                "saved_revision": "r8",
            }
        ],
    }
    reference_graph = {
        "root_ids": ["abc123456789"],
        "graph_hash": "r" * 64,
        "nodes": [
            {
                "object_type": "editor_chart",
                "object_id": "abc123456789",
                "technology": "editor_advanced",
                "saved_revision": "r7",
                "payload_hash": "a" * 64,
            }
        ],
    }
    contract = _contract(
        Path("."),
        locator="https://datalens.example/abc123456789-reference",
    )
    contract["reference"]["kind"] = "live_object"
    result = ReferenceStyleService().bind(
        contract,
        target_graph=target_graph,
        baselines={},
        reference_target_graph=reference_graph,
        reference_baselines={"chart-abc123456789-saved": {"data": {"meta": "{}"}}},
    )
    assert result["status"] == "success"
    assert result["reference_binding"]["object_id"] == "abc123456789"
    assert result["reference_binding"]["revision"] == "r7"


def test_exact_portfolio_style_with_mismatched_target_technology_is_blocked() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bundle = root / "portfolio" / "advanced"
        bundle.mkdir(parents=True)
        (bundle / "meta.json").write_text("{}\n", encoding="utf-8")
        (bundle / "sources.js").write_text("module.exports = {main: {data: []}};\n", encoding="utf-8")
        (bundle / "prepare.js").write_text("module.exports = data => data;\n", encoding="utf-8")
        result = ReferenceStyleService().bind(
            _contract(root, locator=str(bundle)),
            target_graph={
                "nodes": [
                    {
                        "object_type": "wizard_chart",
                        "object_id": "wizard_demo",
                        "technology": "wizard_native",
                    }
                ]
            },
            baselines={},
            portfolio_root=str(root / "portfolio"),
        )
    assert result["status"] == "blocked"
    assert "does not match" in result["reason"]
