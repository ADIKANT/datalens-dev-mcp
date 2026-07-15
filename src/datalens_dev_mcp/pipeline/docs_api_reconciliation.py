from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from datalens_dev_mcp.runtime_resources import RuntimeResourceError, resource_json


@dataclass(frozen=True)
class DocsApiReconciliationStatus:
    ok: bool
    docs_cluster_count: int
    api_operation_count: int
    openapi_sha256: str
    required_cluster_ids: list[str]
    missing_cluster_ids: list[str]
    schema_version: str = "2026-07-01.docs_api_reconciliation_v2"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DocsApiReconciliation:
    REQUIRED_CLUSTER_IDS = [
        "editor_widgets_advanced",
        "visual_table",
        "visual_map",
        "dashboard_tabs",
        "dashboard_title",
        "editor_cross_filtration",
        "dataset_cache_invalidation",
    ]

    def __init__(
        self,
        *,
        docs_feature_policy: dict[str, Any] | None = None,
        api_operation_policy: dict[str, Any] | None = None,
    ) -> None:
        self.docs_feature_policy = docs_feature_policy or _load_json("config/datalens_docs_feature_policy.json")
        self.api_operation_policy = api_operation_policy or _load_json("config/datalens_api_operation_policy.json")

    def status(self) -> DocsApiReconciliationStatus:
        clusters = self.docs_feature_policy.get("clusters") or []
        cluster_ids = {str(item.get("id")) for item in clusters}
        missing = [item for item in self.REQUIRED_CLUSTER_IDS if item not in cluster_ids]
        operations = self.api_operation_policy.get("operations") or []
        openapi_hash = ""
        for operation in operations:
            source = operation.get("source") if isinstance(operation.get("source"), dict) else {}
            if source.get("openapi_sha256"):
                openapi_hash = str(source["openapi_sha256"])
                break
        return DocsApiReconciliationStatus(
            ok=not missing and len(operations) >= 80 and bool(openapi_hash),
            docs_cluster_count=len(clusters),
            api_operation_count=len(operations),
            openapi_sha256=openapi_hash,
            required_cluster_ids=self.REQUIRED_CLUSTER_IDS,
            missing_cluster_ids=missing,
        )

    def method_status(self, method_name: str) -> dict[str, Any]:
        for operation in self.api_operation_policy.get("operations") or []:
            if operation.get("method_name") == method_name:
                return {
                    "method_name": operation.get("method_name"),
                    "status": operation.get("status"),
                    "owning_mcp_tool": operation.get("owning_mcp_tool"),
                    "path": operation.get("path"),
                }
        return {"method_name": method_name, "status": "missing"}


def _load_json(resource_name: str) -> dict[str, Any]:
    try:
        return resource_json(resource_name)
    except RuntimeResourceError:
        return {}
