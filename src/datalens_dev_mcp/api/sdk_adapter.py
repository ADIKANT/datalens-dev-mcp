from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import datalens_sdk

from datalens_dev_mcp.config import DataLensConfig

SDK_VERSION = "0.9.0"

WIZARD_VARIANTS = {
    "area",
    "area_100p",
    "bar",
    "bar_100p",
    "column",
    "column_100p",
    "combined_chart",
    "donut",
    "flat_table",
    "funnel",
    "geolayer",
    "indicator",
    "line",
    "pie",
    "pivot_table",
    "scatter",
    "treemap",
}
EDITOR_VARIANTS = {"advanced_chart", "gravity_charts", "markdown", "selector", "table"}


class SdkAdapter:
    def __init__(self, config: DataLensConfig | None = None, *, client: Any | None = None) -> None:
        actual = getattr(datalens_sdk, "__version__", "")
        if actual != SDK_VERSION:
            raise RuntimeError(f"datalens-sdk version mismatch: expected {SDK_VERSION}, got {actual or '<unknown>'}")
        self._config = config
        self._client = client

    def _sdk_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._config is None:
            raise RuntimeError("DataLensConfig is required for SDK operations")
        self._config.require_auth()
        auth = datalens_sdk.StaticYCIAMAuthProvider(org_id=self._config.org_id, token=self._config.iam_token)
        self._client = datalens_sdk.DataLensClientYC(
            auth=auth,
            base_url=self._config.base_url,
        )
        return self._client

    def get_object(
        self,
        object_type: str,
        object_id: str,
        *,
        branch: str = "saved",
        revision_id: str | None = None,
    ) -> dict[str, Any]:
        getters = {
            "workbook": "workbook",
            "connection": "connection",
            "dataset": "dataset",
            "wizard_chart": "wizard_chart",
            "editor_chart": "editor_chart",
            "table_node": "editor_chart",
            "d3_node": "editor_chart",
            "markdown_node": "editor_chart",
            "control_node": "editor_chart",
            "advanced_chart": "editor_chart",
            "ql_chart": "ql_chart",
            "dashboard": "dashboard",
        }
        getter_name = getters.get(object_type)
        if getter_name is None:
            raise ValueError(f"unsupported SDK object type: {object_type}")
        if branch not in {"saved", "published"}:
            raise ValueError("branch must be 'saved' or 'published'")
        kwargs: dict[str, Any] = {"by_id": object_id}
        if object_type not in {"workbook", "connection", "dataset"}:
            kwargs["branch"] = branch
        if revision_id and object_type != "workbook":
            kwargs["rev_id"] = revision_id
        value = getattr(self._sdk_client().get, getter_name)(**kwargs)
        return _json_object(value)

    def describe_factory(self, resource: str, variant: str) -> dict[str, object]:
        supported = (
            variant in WIZARD_VARIANTS
            if resource == "wizard"
            else variant in EDITOR_VARIANTS
            if resource == "editor"
            else False
        )
        return {
            "sdk_version": SDK_VERSION,
            "resource": resource,
            "variant": variant,
            "supported": supported,
            "effect": "mutation_on_build" if supported else "unsupported",
        }

    def close(self) -> None:
        if self._client is not None and hasattr(self._client, "close"):
            self._client.close()


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    snapshot = getattr(value, "response_snapshot", None)
    if isinstance(snapshot, dict) and snapshot:
        return dict(snapshot)
    raw = getattr(value, "raw", None)
    if isinstance(raw, dict) and raw:
        return dict(raw)
    if is_dataclass(value):
        result = asdict(value)
        result.pop("_operations", None)
        return result
    raise TypeError(f"SDK returned an unsupported object representation: {type(value).__name__}")
