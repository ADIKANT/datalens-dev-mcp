from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import datalens_sdk
import httpx

from datalens_dev_mcp.api.errors import DataLensApiError, UncertainWriteError, safe_error_text
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
        value = self._get_domain(object_type, object_id, branch=branch, revision_id=revision_id)
        return _json_object(value)

    def _get_domain(
        self,
        object_type: str,
        object_id: str,
        *,
        branch: str = "saved",
        revision_id: str | None = None,
    ) -> Any:
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
        return getattr(self._sdk_client().get, getter_name)(**kwargs)

    def create(self, draft: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        """Execute one discriminated draft through the official SDK."""
        requested_type = str(draft.get("object_type") or "")
        if requested_type == "html_page":
            return self._html_create(draft, destination)
        if requested_type == "workbook":
            client = self._sdk_client()
            collection = datalens_sdk.EntryLocation.collection(str(destination["collection_id"])) if destination.get("collection_id") else None
            value = client.create.workbook(name=_draft_name(draft), collection=collection).build()
            return {"object_id": _result_id(value), "object": _json_object(value), "backend": "official_sdk"}
        object_type = _canonical_object_type(requested_type)
        location = _entry_location(destination)
        name = _draft_name(draft)
        client = self._sdk_client()
        try:
            if object_type == "editor_chart" and isinstance(draft.get("tabs"), dict):
                builder = getattr(client.create.editor_chart, _editor_factory(str(draft.get("variant") or "")))(
                    name=name, location=location
                )
                for filename, content in draft["tabs"].items():
                    tab = str(filename).split(".", 1)[0]
                    method = getattr(builder, tab, None)
                    if callable(method):
                        method(str(content))
                value = builder.build()
            else:
                snapshot = draft.get("snapshot")
                if not isinstance(snapshot, dict):
                    raise ValueError("draft.snapshot is required for this object type")
                factory = getattr(client.raw.create, object_type)
                value = factory(response_snapshot=snapshot, name=name, location=location).build()
            return {"object_id": _result_id(value), "object": _json_object(value), "backend": "official_sdk"}
        except httpx.TransportError as exc:
            raise UncertainWriteError("SDK create outcome is uncertain", method=f"create:{object_type}") from exc
        except (ValueError, TypeError):
            raise
        except Exception as exc:  # provider response or SDK validation is a definite error
            raise DataLensApiError(safe_error_text(exc), method=f"create:{object_type}", response_received=True) from exc

    def update(self, object_type: str, object_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        if object_type == "html_page":
            return self._html_update(object_id, snapshot, publish=False)
        if object_type == "workbook":
            target = self._get_domain("workbook", object_id)
            builder = target.update
            changed = False
            for field in ("name", "description"):
                if field in snapshot:
                    getattr(builder, field)(str(snapshot[field]))
                    changed = True
            if not changed:
                raise ValueError("workbook update supports name and description")
            value = builder.execute()
            return {"object_id": object_id, "object": _json_object(value), "backend": "official_sdk"}
        return self._replace(object_type, object_id, snapshot, publish=False)

    def publish(self, object_type: str, object_id: str, saved: dict[str, Any]) -> dict[str, Any]:
        if object_type == "html_page":
            return self._html_update(object_id, saved.get("object") or saved, publish=True)
        snapshot = saved.get("object") if isinstance(saved.get("object"), dict) else saved
        return self._replace(object_type, object_id, snapshot, publish=True)

    def delete(self, object_type: str, object_id: str) -> dict[str, Any]:
        if object_type == "html_page":
            from datalens_dev_mcp.api.client import DataLensApiClient

            if self._config is None:
                raise RuntimeError("DataLensConfig is required for HTML operations")
            return DataLensApiClient(self._config).write("deleteHtmlPage", {"entryId": object_id})
        try:
            target = self._get_domain(_canonical_object_type(object_type), object_id, branch="saved")
            target.delete()
            return {"object_id": object_id, "deleted": True, "backend": "official_sdk"}
        except httpx.TransportError as exc:
            raise UncertainWriteError("SDK delete outcome is uncertain", method=f"delete:{object_type}") from exc
        except Exception as exc:
            raise DataLensApiError(safe_error_text(exc), method=f"delete:{object_type}", response_received=True) from exc

    def _html_create(self, draft: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        from datalens_dev_mcp.api.client import DataLensApiClient
        from datalens_dev_mcp.maintenance import validate_html_content

        if self._config is None:
            raise RuntimeError("DataLensConfig is required for HTML operations")
        content = draft.get("content")
        validation = validate_html_content(content)
        if not validation["ok"]:
            raise ValueError(validation["issues"][0]["message"])
        payload = {"name": _draft_name(draft), "content": content}
        if destination.get("workbook_id"):
            payload["workbookId"] = destination["workbook_id"]
        result = DataLensApiClient(self._config).write("createHtmlPage", payload)
        return {"object_id": str(result.get("entryId") or result.get("id") or ""), "object": result, "backend": "public_api_adapter"}

    def _html_update(self, object_id: str, snapshot: dict[str, Any], *, publish: bool) -> dict[str, Any]:
        from datalens_dev_mcp.api.client import DataLensApiClient

        if self._config is None:
            raise RuntimeError("DataLensConfig is required for HTML operations")
        payload: dict[str, Any] = {"entryId": object_id, "mode": "publish" if publish else "save"}
        revision = snapshot.get("revId") or snapshot.get("rev_id")
        if revision:
            payload["revId"] = revision
        if not publish:
            if not isinstance(snapshot.get("content"), str):
                raise ValueError("HTML Page update requires content string")
            payload["content"] = snapshot["content"]
            if snapshot.get("name"):
                payload["name"] = snapshot["name"]
        result = DataLensApiClient(self._config).write("updateHtmlPage", payload)
        return {"object_id": object_id, "object": result, "backend": "public_api_adapter"}

    def _replace(
        self, object_type: str, object_id: str, snapshot: dict[str, Any], *, publish: bool
    ) -> dict[str, Any]:
        canonical = _canonical_object_type(object_type)
        if publish and canonical in {"connection", "dataset", "workbook"}:
            raise ValueError(f"{canonical} has no publish branch")
        client = self._sdk_client()
        try:
            target = self._get_domain(canonical, object_id, branch="saved")
            builder = getattr(client.raw.replace, canonical)(target=target, response_snapshot=snapshot)
            if canonical == "dashboard":
                value = builder.execute(publish=publish)
            elif canonical in {"wizard_chart", "editor_chart", "ql_chart"}:
                value = builder.mode("publish" if publish else "save").execute()
            else:
                value = builder.execute()
            return {"object_id": _result_id(value) or object_id, "object": _json_object(value), "backend": "official_sdk"}
        except httpx.TransportError as exc:
            raise UncertainWriteError("SDK write outcome is uncertain", method=f"replace:{canonical}") from exc
        except (ValueError, TypeError):
            raise
        except Exception as exc:
            raise DataLensApiError(safe_error_text(exc), method=f"replace:{canonical}", response_received=True) from exc

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


def _canonical_object_type(value: str) -> str:
    aliases = {
        "advanced-chart_node": "editor_chart",
        "advanced_chart": "editor_chart",
        "table_node": "editor_chart",
        "d3_node": "editor_chart",
        "markdown_node": "editor_chart",
        "control_node": "editor_chart",
    }
    canonical = aliases.get(value, value)
    if canonical not in {"workbook", "connection", "dataset", "wizard_chart", "editor_chart", "ql_chart", "dashboard"}:
        raise ValueError(f"unsupported SDK mutation object type: {value}")
    return canonical


def _entry_location(destination: dict[str, Any]) -> Any:
    values = [("workbook", destination.get("workbook_id")), ("collection", destination.get("collection_id")), ("path", destination.get("path"))]
    selected = [(kind, str(value)) for kind, value in values if value]
    if len(selected) != 1:
        raise ValueError("destination must contain exactly one of workbook_id, collection_id or path")
    kind, value = selected[0]
    return getattr(datalens_sdk.EntryLocation, kind)(value)


def _draft_name(draft: dict[str, Any]) -> str:
    name = str(draft.get("name") or "")
    if not name:
        contract = draft.get("visual_contract") or draft.get("config") or {}
        name = str(((contract.get("object_name") or {}).get("value")) or "") if isinstance(contract, dict) else ""
    if not name:
        raise ValueError("draft.name or visual_contract.object_name.value is required")
    return name


def _editor_factory(variant: str) -> str:
    mapping = {
        "advanced-chart_node": "advanced_chart",
        "advanced_chart": "advanced_chart",
        "d3_node": "gravity_charts",
        "gravity_charts": "gravity_charts",
        "markdown_node": "markdown",
        "markdown": "markdown",
        "control_node": "selector",
        "selector": "selector",
        "table_node": "table",
        "table": "table",
    }
    if variant not in mapping:
        raise ValueError(f"unsupported editor variant: {variant}")
    return mapping[variant]


def _result_id(value: Any) -> str:
    direct = getattr(value, "id", None)
    if direct:
        return str(direct)
    raw = _json_object(value)
    return str(raw.get("id") or raw.get("entryId") or raw.get("entry_id") or "")
