from __future__ import annotations

from pathlib import Path
import tempfile

from datalens_dev_mcp.pipeline.reference_style_service import ReferenceStyleService
from datalens_dev_mcp.pipeline.style_binding_receipt import validate_style_binding_receipt
from datalens_dev_mcp.pipeline.task_contract import ReferenceContract, WorkspaceContract, create_task_contract


def test_exact_portfolio_binding_is_hash_bound_and_source_drift_is_visible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bundle = root / "portfolio" / "advanced"
        bundle.mkdir(parents=True)
        (bundle / "meta.json").write_text("{}\n", encoding="utf-8")
        (bundle / "sources.js").write_text("module.exports = {main: {data: []}};\n", encoding="utf-8")
        prepare = bundle / "prepare.js"
        prepare.write_text("function render(data) { return data; }\nmodule.exports = render;\n", encoding="utf-8")
        contract = create_task_contract(
            raw_request="Apply this exact style",
            mode="update",
            route="editor_advanced",
            workspace=WorkspaceContract(project_root=str(root)),
            reference=ReferenceContract(kind="portfolio_object", locator=str(bundle), required_exact_style=True),
        ).to_dict()
        first = ReferenceStyleService().bind(
            contract,
            target_graph={"nodes": [], "root_ids": []},
            baselines={},
            portfolio_root=str(root / "portfolio"),
        )
        prepare.write_text("function render(data) { return data.slice(); }\nmodule.exports = render;\n", encoding="utf-8")
        second = ReferenceStyleService().bind(
            contract,
            target_graph={"nodes": [], "root_ids": []},
            baselines={},
            portfolio_root=str(root / "portfolio"),
        )
    assert not validate_style_binding_receipt(first["style_binding"])
    assert first["reference_binding"]["source_hash"] != second["reference_binding"]["source_hash"]
    assert first["style_binding"]["binding_hash"] != second["style_binding"]["binding_hash"]
