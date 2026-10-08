from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import datalens_sdk
import httpx
from datalens_sdk.errors import DataLensAPIError as SdkApiError
from datalens_sdk.errors import DataLensTransportError as SdkTransportError
from datalens_sdk.http import DEFAULT_RETRY_POLICY, DataLensHTTPClient

from datalens_dev_mcp.api.budget import check_dispatch, current_budget, read_budget
from datalens_dev_mcp.api.client import _retry_after
from datalens_dev_mcp.api.errors import (
    DataLensApiError,
    InputContractError,
    UncertainWriteError,
    WritePreconditionError,
    response_diagnostics,
    safe_error_text,
)
from datalens_dev_mcp.authoring.validation import validate_entry_name
from datalens_dev_mcp.config import DataLensConfig

SDK_VERSION = "3.2.0"

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


class _ConfiguredHTTPClient(DataLensHTTPClient):
    """Use the public SDK transport and its sole retry loop with configured limits."""

    def __init__(self, config: DataLensConfig, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.config = config

    def post_json(self, path, body, *, retry_policy=DEFAULT_RETRY_POLICY, accept_response=None):
        from datalens_dev_mcp.api.schemas import OperationRegistry

        method = path.rsplit("/", 1)[-1]
        try:
            readonly = OperationRegistry.load().get(method)["effect"] == "read"
        except KeyError:
            readonly = False
        budget = current_budget.get()
        seconds = budget.check() if budget else self.config.read_budget_sec
        policy = replace(retry_policy, total_timeout=seconds,
                         request_timeout=self.config.request_timeout_sec,
                         connect_timeout=self.config.request_timeout_sec,
                         max_attempts=self.config.read_retries + 1 if readonly else 1)
        try:
            return super().post_json(path, body, retry_policy=policy, accept_response=accept_response)
        except (SdkTransportError, SdkApiError) as exc:
            exc._datalens_request_diagnostics = _request_diagnostics(body)
            # Classify at this RPC, not the outer SDK operation: a subsequent
            # read can fail to connect after a successful mutation. These HTTPX
            # phases precede request bytes and this mutation has just one attempt.
            if (not readonly and isinstance(exc, SdkTransportError) and exc.attempts == 1
                    and isinstance(exc.__cause__, (httpx.ConnectTimeout, httpx.ConnectError, httpx.PoolTimeout))):
                failure = _provider_error(exc, method)
                failure.dispatch_state = "not_dispatched"
                raise failure from exc
            raise


class _ProviderAuth(httpx.Auth):
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    def auth_flow(self, request):
        request.headers.update(self.provider.get_headers())
        yield request


class _BudgetedStream(httpx.SyncByteStream):
    def __init__(self, response: httpx.Response, budget: Any) -> None:
        self.stream, self.budget = response.stream, budget
        self.method = response.request.url.path.rsplit("/", 1)[-1]
        self.http_status = response.status_code
        self.diagnostics = response_diagnostics(response.headers)

    def __iter__(self):
        for chunk in self.stream:
            try:
                self.budget.check()
            except DataLensApiError as exc:
                exc.dispatch_state = "dispatched"
                exc.response_received = True
                exc.http_status = self.http_status
                exc.stage = "response_read"
                exc.method = self.method
                exc.request_id = self.diagnostics["request_id"]
                exc.trace_id = self.diagnostics["trace_id"]
                raise
            yield chunk

    def close(self) -> None:
        self.stream.close()


class SdkAdapter:
    def __init__(
        self,
        config: DataLensConfig | None = None,
        *,
        client: Any | None = None,
        token_refresher: Callable[[], str] | None = None,
    ) -> None:
        actual = getattr(datalens_sdk, "__version__", "")
        if actual != SDK_VERSION:
            raise RuntimeError(f"datalens-sdk version mismatch: expected {SDK_VERSION}, got {actual or '<unknown>'}")
        # SDK 3.2.0 logs raw provider message/details (including SQL or HTML).
        # Keep failures in our sanitized tool results; do not duplicate bodies on stderr.
        logging.getLogger("datalens_sdk.http").disabled = True
        self._config = config
        self._client = client
        self._http_client: _ConfiguredHTTPClient | None = None
        self._token_refresher = token_refresher
        self._write_dispatches = 0
        self._responses = 0
        self._tracks_dispatch = False

    @property
    def config(self) -> DataLensConfig | None:
        return self._config

    def replace_config(self, config: DataLensConfig) -> None:
        budget = current_budget.get()
        if budget is not None:
            budget.sdk_targets.clear()
        self.close()
        self._config = config
        self._client = None

    def _sdk_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._config is None:
            raise RuntimeError("DataLensConfig is required for SDK operations")
        self._config.require_auth()
        if self._config.installation == "enterprise":
            auth = datalens_sdk.AuthorizationTokenAuthProvider(token=self._config.iam_token, token_type="Bearer")
            client_type = datalens_sdk.DataLensClientEnterprise
        else:
            auth = datalens_sdk.StaticYCIAMAuthProvider(org_id=self._config.org_id, token=self._config.iam_token)
            client_type = datalens_sdk.DataLensClientYC
        self._http_client = _ConfiguredHTTPClient(
            self._config, installation=self._config.installation, sdk_version=SDK_VERSION,
            auth=_ProviderAuth(auth), base_url=self._config.base_url,
            event_hooks={"request": [self._observe_dispatch], "response": [self._observe_response]},
        )
        self._client = client_type(http_client=self._http_client)
        self._tracks_dispatch = True
        return self._client

    def _observe_response(self, response: httpx.Response) -> None:
        self._responses += 1
        self._observe_rate_limit(response)
        # The SDK reads response.content itself. Consume decoded HTTPX chunks
        # under the owned limit before its parser can materialize unbounded JSON.
        limit = self._config.max_response_bytes if self._config else 32 * 1024 * 1024
        content = bytearray()
        try:
            for chunk in response.iter_bytes(chunk_size=min(65536, limit + 1)):
                if len(content) + len(chunk) > limit:
                    raise DataLensApiError("SDK response exceeds configured decoded byte limit",
                                           method=response.request.url.path.rsplit("/", 1)[-1],
                                           remote_code="response_too_large", stage="response_read",
                                           http_status=response.status_code, response_received=True,
                                           dispatch_state="dispatched", **response_diagnostics(response.headers))
                content.extend(chunk)
            # HTTPX read() uses this same cache. Preserve the original response
            # and headers for the pinned SDK instead of decoding JSON twice.
            response._content = bytes(content)
        finally:
            response.close()

    @staticmethod
    def _observe_rate_limit(response: httpx.Response) -> None:
        # SDK 3.2.0 retries 429 before translation with a backoff that ignores
        # Retry-After. Surface it before that loop; do not add another retry owner.
        budget = current_budget.get()
        if budget is not None:
            response.stream = _BudgetedStream(response, budget)
        if response.status_code != 429:
            return
        method = response.request.url.path.rsplit("/", 1)[-1]
        failure = DataLensApiError(
            "DataLens request failed with HTTP 429", method=method, http_status=429,
            response_received=True, stage="provider_response",
            retry_after_sec=_retry_after(response.headers.get("Retry-After")),
            **response_diagnostics(response.headers),
        )
        response.close()
        raise failure

    def _observe_dispatch(self, request: httpx.Request) -> None:
        from datalens_dev_mcp.api.schemas import OperationRegistry

        method = request.url.path.rsplit("/", 1)[-1]
        try:
            readonly = OperationRegistry.load().get(method)["effect"] == "read"
        except KeyError:
            readonly = False
        remaining = check_dispatch(readonly=readonly)
        if remaining is not None or self._config is not None:
            # HTTPX owns the actual request timeout; the hook also runs for SDK retries.
            timeout = request.extensions.get("timeout") or {}
            limit = self._config.request_timeout_sec if self._config else 30.0
            limit = min(limit, remaining) if remaining is not None else limit
            request.extensions["timeout"] = {key: min(value if value is not None else limit, limit)
                for key, value in {"connect": limit, "read": limit, "write": limit, "pool": limit, **timeout}.items()}
        if not readonly:
            # HTTPX calls request hooks after encoding/auth, just before send.
            self._write_dispatches += 1

    def _mutation_error(self, exc: Exception, method: str, *, effect_started: bool,
                        dispatch_before: int, direct: bool = False) -> Exception:
        count = self._write_dispatches - dispatch_before
        before_dispatch = not effect_started or (self._tracks_dispatch and count == 0 and not direct)
        if isinstance(exc, UncertainWriteError):
            return exc
        if direct and count == 0 and (isinstance(exc, InputContractError)
                                     or getattr(exc, "dispatch_state", None) == "not_dispatched"):
            return exc
        if before_dispatch:
            if isinstance(exc, (InputContractError, WritePreconditionError)):
                return exc
            if isinstance(exc, (ValueError, TypeError, KeyError)):
                return InputContractError(safe_error_text(exc))
            failure = _provider_error(exc, method)
            failure.dispatch_state = "not_dispatched"
            return failure
        if count > 1 or isinstance(exc, (httpx.TransportError, SdkTransportError, ValueError, TypeError)):
            failure = _provider_error(exc, method)
            return UncertainWriteError("SDK mutation may have applied; do not replay", method=failure.method or method,
                                       http_status=failure.http_status, remote_code=failure.remote_code,
                                       response_received=failure.response_received,
                                       retry_after_sec=failure.retry_after_sec,
                                       stage=failure.stage, request_id=failure.request_id, trace_id=failure.trace_id,
                                       provider_diagnostics=failure.provider_diagnostics)
        return _provider_error(exc, method)

    def get_object(
        self,
        object_type: str,
        object_id: str,
        *,
        branch: str = "saved",
        revision_id: str | None = None,
    ) -> dict[str, Any]:
        value = self._get_domain(object_type, object_id, branch=branch, revision_id=revision_id)
        budget = current_budget.get()
        if budget is not None and branch == "saved" and revision_id is None:
            budget.sdk_targets[(_canonical_object_type(object_type), object_id)] = value
        snapshot = _json_object(value)
        if _canonical_object_type(object_type) in {"chart", "wizard_chart", "editor_chart", "ql_chart"}:
            try:
                return _chart_entry(snapshot)
            except (ValueError, TypeError) as exc:
                raise DataLensApiError("Invalid chart response envelope", remote_code="invalid_response",
                                       stage="response_validation", response_received=True,
                                       dispatch_state="dispatched") from exc
        return snapshot

    def _get_domain(
        self,
        object_type: str,
        object_id: str,
        *,
        branch: str = "saved",
        revision_id: str | None = None,
    ) -> Any:
        # Include auth refresh and all SDK attempts in the same logical read.
        with read_budget(self._config.read_budget_sec if self._config else 60):
            return self._read_domain(object_type, object_id, branch=branch, revision_id=revision_id)

    def _read_domain(self, object_type: str, object_id: str, *, branch: str,
                     revision_id: str | None) -> Any:
        object_type = _canonical_object_type(object_type)
        getter_name = object_type
        if branch not in {"saved", "published"}:
            raise ValueError("branch must be 'saved' or 'published'")
        kwargs: dict[str, Any] = {"by_id": object_id}
        if object_type not in {"workbook", "connection", "dataset"}:
            kwargs["branch"] = branch
        if revision_id and object_type != "workbook":
            kwargs["rev_id"] = revision_id
        auth_refreshed = False
        while True:
            responses_before = self._responses
            try:
                return getattr(self._sdk_client().get, getter_name)(**kwargs)
            except SdkApiError as exc:
                if exc.context.status_code == 401 and not auth_refreshed and self._token_refresher is not None:
                    token = self._token_refresher().strip()
                    if not token:
                        raise DataLensApiError(
                            "DataLens token refresh returned no credential",
                            method=f"get:{object_type}",
                        ) from exc
                    if self._config is not None and self._config.iam_token != token:
                        self.replace_config(replace(self._config, iam_token=token, credential_source="runtime_refresh"))
                    auth_refreshed = True
                    continue
                raise _provider_error(exc, f"get:{object_type}") from exc
            except (httpx.TransportError, SdkTransportError) as exc:
                raise _provider_error(exc, f"get:{object_type}") from exc
            except (ValueError, TypeError, KeyError) as exc:
                if self._responses > responses_before:
                    raise DataLensApiError("SDK could not decode the object response", method=f"get:{object_type}",
                                           remote_code="invalid_response", stage="response_validation",
                                           response_received=True, dispatch_state="dispatched") from exc
                raise InputContractError(safe_error_text(exc)) from exc

    def get_dataset_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the bounded preview query through the installed v3 DTO."""
        with read_budget(self._config.read_budget_sec if self._config else 60):
            return self._read_dataset_data(payload)

    def _read_dataset_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        auth_refreshed = False
        while True:
            responses_before = self._responses
            try:
                value = self._sdk_client().data.get_dataset_data(
                    dataset_id=payload["datasetId"], columns=payload["columns"],
                    filters=[datalens_sdk.DatasetDataFilter(field=item["guid"], operation=item["operation"].upper(),
                             values=tuple(item.get("values", []))) for item in payload.get("filters", [])],
                    params=[datalens_sdk.DatasetDataParameter(field=item["guid"], value=item["value"])
                            for item in payload.get("params", [])],
                    sort=[datalens_sdk.DatasetDataSort(field=item["guid"], direction=item["direction"])
                          for item in payload.get("sort", [])],
                    limit=payload["limit"], offset=payload.get("offset"),
                )
                return {"schema": [asdict(column) for column in value.schema], "rows": [list(row) for row in value.rows]}
            except SdkApiError as exc:
                if exc.context.status_code == 401 and not auth_refreshed and self._token_refresher is not None:
                    token = self._token_refresher().strip()
                    if not token:
                        raise DataLensApiError("DataLens token refresh returned no credential", method="getDatasetData") from exc
                    if self._config is not None and self._config.iam_token != token:
                        self.replace_config(replace(self._config, iam_token=token, credential_source="runtime_refresh"))
                    auth_refreshed = True
                    continue
                raise _provider_error(exc, "getDatasetData") from exc
            except (httpx.TransportError, SdkTransportError) as exc:
                raise _provider_error(exc, "getDatasetData") from exc
            except (ValueError, TypeError, KeyError) as exc:
                if self._responses > responses_before:
                    raise DataLensApiError("SDK could not decode the Dataset data response", method="getDatasetData",
                                           remote_code="invalid_response", stage="response_validation",
                                           response_received=True, dispatch_state="dispatched") from exc
                raise InputContractError(safe_error_text(exc)) from exc
            except Exception as exc:
                raise _provider_error(exc, "getDatasetData") from exc

    def validate_create_batch(self, drafts: list[dict[str, Any]], destination: dict[str, Any], *,
                              skip_indices: set[int] | None = None) -> list[tuple[int, Exception]]:
        """Compile every typed Wizard before any batch write, with scoped field reads.

        Pure validate_drafts remains offline. Here existing Dataset metadata can
        be read; pending Dataset GUIDs come from the batch's own declared fields.
        No build/save/publish is called, and write-time freshness checks still run.
        """
        from datalens_sdk.converter.wizard import WizardChartConverter

        from datalens_dev_mcp.wizard.authoring import wizard_builder

        datasets: dict[str, Any] = {}
        errors: list[tuple[int, Exception]] = []
        for index, draft in enumerate(drafts):
            if index in (skip_indices or set()):
                continue
            specification = draft.get("wizard")
            if not isinstance(specification, dict):
                continue
            dataset_ref = specification.get("dataset_id")
            try:
                if isinstance(dataset_ref, dict):
                    ref = dataset_ref["$object_ref"]
                    source = next(item for item in drafts if item.get("client_ref") == ref)
                    fields = (source.get("dataset") or {}).get("fields")
                    if not fields:
                        raise InputContractError("pending Wizard Dataset requires declared dataset.fields for preflight")
                    rows = [{**field, "type": str(field.get("kind") or field.get("type")).upper(),
                             "data_type": field.get("cast") or field.get("data_type")} for field in fields]
                    dataset = datalens_sdk.Dataset(id=ref, result_schema=tuple(rows))
                else:
                    if dataset_ref not in datasets:
                        datasets[dataset_ref] = self._get_domain("dataset", str(dataset_ref))
                    dataset = datasets[dataset_ref]
                builder = wizard_builder(self._sdk_client(), dataset, specification,
                                         name=_draft_name(draft), location=_entry_location(destination))
                WizardChartConverter.from_domain_create(builder.to_spec()).to_payload()
            except (ValueError, TypeError, KeyError, StopIteration) as exc:
                errors.append((index, InputContractError(f"wizard: {safe_error_text(exc)}")))
            except SdkApiError as exc:
                errors.append((index, _provider_error(exc, "getDataset")))
            except DataLensApiError as exc:
                errors.append((index, exc))
            except (httpx.TransportError, SdkTransportError) as exc:
                errors.append((index, _provider_error(exc, "getDataset")))

        return errors

    def create(self, draft: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        """Execute one discriminated draft through the official SDK."""
        requested_type = str(draft.get("object_type") or "")
        if requested_type == "html_page":
            return self._html_create(draft, destination)
        object_type = _canonical_object_type(requested_type)
        location = _entry_location(destination) if requested_type != "workbook" else None
        name = _draft_name(draft)
        if self._config is not None:
            validate_entry_name(name, object_type, installation=self._config.installation, base_url=self._config.base_url)
        expected_readback = None
        effect_started = False
        dispatch_before = self._write_dispatches
        try:
            client = self._sdk_client()
            if requested_type == "workbook":
                collection = (datalens_sdk.EntryLocation.collection(str(destination["collection_id"]))
                              if destination.get("collection_id") else None)
                builder = client.create.workbook(name=name, collection=collection)
                effect_started = True
                value = builder.build()
            elif object_type == "wizard_chart" and "wizard" in draft:
                from datalens_sdk.converter.wizard import WizardChartConverter

                from datalens_dev_mcp.wizard.authoring import wizard_builder

                specification = draft["wizard"]
                if not isinstance(specification, dict):
                    raise ValueError("draft.wizard must be an object")
                dataset = self._get_domain("dataset", str(specification["dataset_id"]))
                client = self._sdk_client()
                builder = wizard_builder(client, dataset, specification, name=name, location=location)
                payload = WizardChartConverter.from_domain_create(builder.to_spec()).to_payload()
                expected_readback = {"data": payload["data"]}
                effect_started = True
                value = builder.build()
            elif object_type == "editor_chart" and isinstance(draft.get("tabs"), dict):
                builder = getattr(client.create.editor_chart, _editor_factory(str(draft.get("variant") or "")))(
                    name=name, location=location
                )
                from datalens_dev_mcp.editor.validation import TAB_FIELDS, allowed_editor_fields, validate_editor_source

                allowed = allowed_editor_fields(str(draft.get("variant") or ""))
                issues = validate_editor_source(draft["tabs"])
                if issues:
                    raise InputContractError(f"{issues[0]['path']}: {issues[0]['message']}")
                expected_tabs = {}
                for filename, content in draft["tabs"].items():
                    tab = TAB_FIELDS.get(filename)
                    if tab not in allowed:
                        raise InputContractError(f"unsupported tab for selected Editor variant: {filename}")
                    method = getattr(builder, tab, None) if tab else None
                    if not callable(method):
                        raise InputContractError(
                            f"SDK 3.2.0 create carrier does not support {filename}; "
                            "the documented tab is retained in the draft, no create was dispatched")
                    if not isinstance(content, str):
                        raise ValueError(f"Editor tab must contain source text: {filename}")  # noqa: TRY004
                    method(content)
                    expected_tabs[tab] = content
                expected_readback = {"data": expected_tabs}
                effect_started = True
                value = builder.build()
            elif object_type == "dataset" and isinstance(draft.get("dataset"), dict):
                from datalens_dev_mcp.authoring.typed_graph import dataset_builder

                specification = draft["dataset"]
                connection_id = specification.get("connection_id")
                if not isinstance(connection_id, str) or not connection_id:
                    raise ValueError("typed Dataset requires connection_id")
                connection = self._get_domain("connection", connection_id)
                client = self._sdk_client()
                builder = dataset_builder(client, connection, specification, name=name, location=location)
                expected_readback = {"name": name}
                effect_started = True
                value = builder.build()
            elif object_type == "dashboard" and isinstance(draft.get("dashboard"), dict):
                builder, payload = _dashboard_create(client, draft, destination)
                expected_readback = {"entry": {"data": payload["entry"]["data"]}}
                effect_started = True
                value = builder.build()
            else:
                snapshot = draft.get("snapshot")
                if not isinstance(snapshot, dict):
                    raise ValueError("draft.snapshot is required for this object type")
                if object_type == "dashboard":
                    _validate_dashboard_snapshot(snapshot, from_artifact=True)
                    # The SDK uses the source identity to decode an import, but
                    # create assigns a new identity. Verify the fields actually
                    # forwarded by the raw-create converter, not the source ID.
                    entry = snapshot.get("entry", snapshot)
                    expected_readback = {key: entry[key] for key in ("data", "meta", "annotation") if key in entry}
                    expected_readback["name"] = name
                if object_type == "editor_chart":
                    _validate_editor_changes(_chart_entry(snapshot), {"data": {}})
                if object_type == "wizard_chart":
                    _validate_wizard_snapshot(_chart_entry(snapshot))
                factory = getattr(client.raw.create, object_type)
                builder = factory(response_snapshot=snapshot, name=name, location=location)
                if object_type == "connection":
                    from datalens_sdk.converter.connection import ConnectionConverter
                    from datalens_sdk.domain.specs.raw_resource import RawCreateSpec

                    # Verify fields actually sent, not the import's source id/name.
                    expected_readback = ConnectionConverter.from_raw_create(
                        RawCreateSpec(response_snapshot=snapshot, name=name, location=location), overrides=None,
                        installation=self._config.installation if self._config else "yacloud",
                    ).to_payload()
                effect_started = True
                value = builder.build()
            result = {"object_id": _result_id(value), "object": _json_object(value), "backend": "official_sdk"}
            if expected_readback is not None:
                result["expected_readback"] = expected_readback
            return result
        except Exception as exc:
            raise self._mutation_error(exc, f"create:{object_type}", effect_started=effect_started,
                                       dispatch_before=dispatch_before) from exc

    def update(self, object_type: str, object_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        if object_type == "html_page":
            return self._html_update(object_id, snapshot, publish=False)
        if object_type == "workbook":
            effect_started = False
            dispatch_before = self._write_dispatches
            try:
                target = self._get_domain("workbook", object_id)
                builder = target.update
                changed = False
                for field in ("name", "description"):
                    if field in snapshot:
                        getattr(builder, field)(str(snapshot[field]))
                        changed = True
                if not changed:
                    raise InputContractError("workbook update supports name and description")
                effect_started = True
                value = builder.execute()
                return {"object_id": object_id, "object": _json_object(value), "backend": "official_sdk"}
            except Exception as exc:
                raise self._mutation_error(exc, "update:workbook", effect_started=effect_started,
                                           dispatch_before=dispatch_before) from exc
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
        effect_started = False
        dispatch_before = self._write_dispatches
        try:
            budget = current_budget.get()
            target = budget.sdk_targets.pop((_canonical_object_type(object_type), object_id), None) if budget else None
            if target is None:
                target = self._get_domain(_canonical_object_type(object_type), object_id, branch="saved")
            effect_started = True
            target.delete()
            return {"object_id": object_id, "deleted": True, "backend": "official_sdk"}
        except Exception as exc:
            raise self._mutation_error(exc, f"delete:{object_type}", effect_started=effect_started,
                                       dispatch_before=dispatch_before) from exc

    def _html_create(self, draft: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        raise InputContractError(
            "HTML Page content readback is unavailable in the verified API v3 contract; "
            "retain a local HTML artifact. Page content create/update is unsupported by this adapter."
        )

    def _html_update(self, object_id: str, snapshot: dict[str, Any], *, publish: bool) -> dict[str, Any]:
        from datalens_dev_mcp.api.client import DataLensApiClient

        if not publish:
            return self._html_create(snapshot, {})
        if self._config is None:
            raise RuntimeError("DataLensConfig is required for HTML operations")
        revision = _saved_revision(snapshot)
        if not revision:
            raise WritePreconditionError("HTML Page publication requires the observed saved revision")
        api = DataLensApiClient(self._config)
        try:
            latest = api.read("getHtmlPage", {"entryId": object_id, "branch": "saved"})
        except DataLensApiError as exc:
            exc.dispatch_state = "not_dispatched"
            raise
        if latest.get("entryId") != object_id or _saved_revision(latest) != revision:
            raise WritePreconditionError("HTML Page saved identity/revision changed; re-read before publishing")
        if latest.get("branch", "saved") != "saved":
            raise WritePreconditionError("HTML Page target is not the saved branch")
        result = api.write("updateHtmlPage", {"entryId": object_id, "mode": "publish", "revId": revision})
        entry = result.get("entry") if isinstance(result.get("entry"), dict) else result
        return {"object_id": object_id, "object": entry, "backend": "public_api_adapter",
                "publication_semantics": "existing_revision"}

    def _replace(self, object_type: str, object_id: str, snapshot: dict[str, Any], *, publish: bool) -> dict[str, Any]:
        canonical = _canonical_object_type(object_type)
        if publish and canonical in {"connection", "dataset", "workbook"}:
            raise ValueError(f"{canonical} has no publish branch")
        effect_started = False
        direct = False
        dispatch_before = self._write_dispatches
        try:
            target = self._get_domain(canonical, object_id, branch="saved")
            client = self._sdk_client()
            latest = _json_object(target)
            if canonical in {"wizard_chart", "editor_chart", "ql_chart"}:
                latest = _chart_entry(latest)
            # This is a second read after the service merged its patch. Never
            # attach that older snapshot to a newly observed revision. This
            # preflight is not an atomic provider-side CAS guarantee.
            expected_revision = _saved_revision(snapshot)
            if expected_revision:
                observed_revision = _saved_revision(latest)
                if observed_revision != expected_revision:
                    raise WritePreconditionError("saved revision changed during SDK target fetch; re-read before retry")
            from datalens_dev_mcp.objects.relations import object_identity

            for state in (latest, snapshot):
                observed_id, _ = object_identity(state)
                entry = state.get("entry") if isinstance(state.get("entry"), dict) else state
                if observed_id and observed_id != object_id:
                    raise WritePreconditionError("SDK target identity changed; re-read the exact target")
                if canonical not in {"dataset", "connection", "workbook"} and entry.get("branch", "saved") != "saved":
                    raise WritePreconditionError("SDK target branch changed; re-read the saved target")
            if canonical == "editor_chart":
                _validate_editor_changes(snapshot, latest)
            if canonical == "wizard_chart":
                _validate_wizard_snapshot(snapshot)
            if canonical == "dashboard":
                _validate_dashboard_snapshot(snapshot)
            if publish and canonical in {"dashboard", "wizard_chart", "editor_chart"}:
                if not expected_revision:
                    raise WritePreconditionError("Publish requires an observed saved revision")
                effect_started = True
                value = target.publish_revision(rev_id=expected_revision)
                return {"object_id": object_id, "object": _json_object(value), "backend": "official_sdk",
                        "publication_semantics": "existing_revision"}
            rename_to = None
            if not publish and "name" in snapshot and snapshot["name"] != latest.get("name"):
                old_content = {key: value for key, value in latest.items() if key != "name"}
                new_content = {key: value for key, value in snapshot.items() if key != "name"}
                if not isinstance(snapshot["name"], str) or not snapshot["name"]:
                    raise ValueError("object name must be a nonempty string")
                if self._config is not None:
                    validate_entry_name(snapshot["name"], canonical,
                                        installation=self._config.installation, base_url=self._config.base_url)
                if old_content == new_content:
                    effect_started = True
                    value = target.rename(snapshot["name"])
                    return {"object_id": object_id, "object": _json_object(value), "backend": "official_sdk"}
                rename_to = snapshot["name"]
            if canonical == "dataset":
                # SDK 3.2.0 raw replacement still strips dataset.revision_id.
                # Keep one narrow full-state API v3 adapter with both revision
                # guards; see docs/testing/sdk-v3-compatibility.md.
                from datalens_dev_mcp.api.client import DataLensApiClient

                content = snapshot.get("dataset")
                observed = latest.get("dataset")
                revision = content.get("revision_id") if isinstance(content, dict) else None
                if (not isinstance(content, dict) or "revision_id" not in content
                        or (revision is not None and (not isinstance(revision, str) or not revision))):
                    raise WritePreconditionError("Dataset update requires the observed dataset.revision_id")
                if (not isinstance(observed, dict) or "revision_id" not in observed
                        or observed["revision_id"] != revision):
                    raise WritePreconditionError("Dataset revision changed during target fetch; re-read before retry")
                # API v3 can explicitly return null for the inner revision.
                # Preserve it, but require the independently checked outer revision;
                # an absent inner field is not equivalent to an observed null.
                if revision is None and not expected_revision:
                    raise WritePreconditionError("Dataset update with null inner revision requires the saved revision")
                if self._config is None:
                    raise RuntimeError("DataLensConfig is required for Dataset update")
                effect_started = True
                direct = True
                value = DataLensApiClient(self._config).write(
                    "updateDataset", {"datasetId": object_id, "data": {"dataset": deepcopy(content)}}
                )
            else:
                builder = getattr(client.raw.replace, canonical)(target=target, response_snapshot=snapshot)
            if canonical == "dataset":
                pass
            elif canonical == "dashboard":
                effect_started = True
                value = builder.execute(publish=publish)
            elif canonical in {"wizard_chart", "editor_chart", "ql_chart"}:
                builder = builder.mode("publish" if publish else "save")
                effect_started = True
                value = builder.execute()
            else:
                effect_started = True
                value = builder.execute()
            if rename_to is not None:
                try:
                    rename_target = value if callable(getattr(value, "rename", None)) else target
                    value = rename_target.rename(rename_to)
                except Exception as exc:
                    # The save already returned. Even a definite rename rejection
                    # is a partial object update, never a safe-to-replay failure.
                    raise UncertainWriteError(
                        "content saved; rename not confirmed; preserve the operation and do not replay", method=f"rename:{canonical}"
                    ) from exc
            return {
                "object_id": _result_id(value) or object_id,
                "object": _json_object(value),
                "backend": "public_api_adapter" if canonical == "dataset" else "official_sdk",
            }
        except Exception as exc:
            raise self._mutation_error(exc, f"replace:{canonical}", effect_started=effect_started,
                                       dispatch_before=dispatch_before, direct=direct) from exc

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
        if self._http_client is not None:
            self._http_client.close()
            self._http_client = None


def _chart_entry(snapshot: dict[str, Any]) -> dict[str, Any]:
    if "entry" in snapshot:
        if not isinstance(snapshot["entry"], dict):
            raise InputContractError("chart snapshot.entry must be an object")
        entry = dict(snapshot["entry"])
    else:
        entry = dict(snapshot)
    key = entry.get("key")
    if not entry.get("name") and isinstance(key, str) and key.rsplit("/", 1)[-1]:
        entry["name"] = key.rsplit("/", 1)[-1]
    return entry


def _saved_revision(snapshot: dict[str, Any]) -> str | None:
    containers = [snapshot]
    entry = snapshot.get("entry")
    if isinstance(entry, dict):
        containers.append(entry)
    for container in containers:
        for key in ("revId", "rev_id", "savedId", "saved_id"):
            value = container.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _dashboard_create(client: Any, draft: dict[str, Any], destination: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    from datalens_sdk.converter.dashboard import DashboardConverter

    from datalens_dev_mcp.authoring.typed_graph import dashboard_builder

    builder = dashboard_builder(client, draft["dashboard"], name=_draft_name(draft), location=_entry_location(destination))
    payload = getattr(builder, "response_snapshot", None)
    if payload is None:
        payload = DashboardConverter.from_domain_create(builder.to_spec()).to_payload()
    return builder, payload


def prepare_dashboard_wire(draft: dict[str, Any], destination: dict[str, Any], *, installation: str) -> bytes:
    """Use the create converter and HTTPX JSON encoder, with no transport available."""
    if getattr(datalens_sdk, "__version__", "") != SDK_VERSION:
        raise InputContractError("Installed SDK differs from the supported pin")
    if draft.get("object_type") != "dashboard" or not isinstance(draft.get("dashboard"), dict):
        raise InputContractError("wire preparation supports concrete typed dashboard drafts only")
    if installation not in {"yacloud", "enterprise"}:
        raise InputContractError("wire preparation requires yacloud or enterprise installation")
    client_type = datalens_sdk.DataLensClientEnterprise if installation == "enterprise" else datalens_sdk.DataLensClientYC
    # Builders and converters cannot dispatch through this sentinel.
    client = client_type(http_client=object())
    _, payload = _dashboard_create(client, draft, destination)
    return httpx.Request("POST", "https://example.invalid", json=payload).content


def _request_diagnostics(body: Any) -> dict[str, Any]:
    wire = httpx.Request("POST", "https://example.invalid", json=body).content
    return _wire_diagnostics(wire)


def _wire_diagnostics(wire: bytes) -> dict[str, Any]:
    from datalens_dev_mcp import __version__

    return {"request_sha256": hashlib.sha256(wire).hexdigest(), "request_bytes": len(wire),
            "runtime_version": __version__, "sdk_version": SDK_VERSION,
            "observed_at": datetime.now(UTC).isoformat()}


def _allowed_provider_code(value: Any) -> str | None:
    # Known codes only: an identifier-shaped arbitrary value may still be a secret.
    known = {"VALIDATION_ERROR", "INVALID_ARGUMENT", "BAD_REQUEST", "NOT_FOUND", "CONFLICT",
             "INTERNAL_ERROR", "INTERNAL_SERVER_ERROR", "UNAUTHORIZED", "FORBIDDEN", "ENTRY_TYPE_MISMATCH",
             "ERR.DS_API.DB.CH.READONLY_USER", "ERR.DS_API.DB.INDEX_NOT_USED", "ERR.DS_API.DB.EST_EXEC_TOO_LONG"}
    return value if isinstance(value, str) and value in known else None


def _body_diagnostics(response: httpx.Response | None) -> dict[str, Any]:
    result: dict[str, Any] = {"body_available": False, "body_status": "unavailable", "redacted": True,
                              "reason": None, "field_path": None}
    if response is None or not response.is_stream_consumed:
        return result
    body = response.content
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    result.update(body_available=True, body_bytes=len(body), body_sha256=hashlib.sha256(body).hexdigest(),
                  content_type=content_type if content_type in {"application/json", "text/html", "text/plain"} else "other",
                  truncated=len(body) > 65536, body_status="unusable")
    try:
        result.update(_wire_diagnostics(response.request.content))
    except (ValueError, httpx.RequestNotRead):
        pass
    if len(body) > 65536 or content_type != "application/json":
        return result
    try:
        value = json.loads(body)
    except (ValueError, RecursionError):
        return result
    if not isinstance(value, dict):
        return result
    result["body_status"] = "structured_redacted"
    # Only documented-style error envelopes; never recurse into arbitrary details.
    for _ in range(3):
        if isinstance(value.get("error"), dict):
            value = value["error"]
        else:
            break
    code = _allowed_provider_code(value.get("code"))
    result["code"] = code
    result["reason"] = {"VALIDATION_ERROR": "validation", "INVALID_ARGUMENT": "validation",
                        "BAD_REQUEST": "validation", "CONFLICT": "conflict", "NOT_FOUND": "not_found",
                        "UNAUTHORIZED": "authentication", "FORBIDDEN": "permission",
                        "INTERNAL_ERROR": "internal", "INTERNAL_SERVER_ERROR": "internal"}.get(code)
    path = value.get("path")
    allowed = {"entry", "data", "tabs", "items", "layout", "source", "fieldType", "elementType", "fieldName",
               "defaultValue", "required", "meta", "name", "workbookId", "group", "defaults", "id", "type",
               "settings", "connections", "aliases", "params", "mode", "x", "y", "w", "h", "i"}
    if isinstance(path, str) and len(path) <= 240:
        tokens = re.split(r"[./\[\]]+", path)
        if any(tokens) and all(token in allowed or bool(re.fullmatch(r"[0-9]{1,6}", token)) for token in tokens if token):
            result["field_path"] = path
    return result


def _provider_error(exc: Exception, method: str) -> DataLensApiError:
    if isinstance(exc, DataLensApiError):
        return exc
    if isinstance(exc, (httpx.TransportError, SdkTransportError)):
        # SDK 3.2.0 chains the actual HTTPX transport error. Its reason/URL can
        # contain private content: retain only a known class and the RPC basename.
        cause = exc.__cause__ if isinstance(exc, SdkTransportError) else exc
        transport_codes = {
            httpx.ConnectTimeout: ("connect_timeout", "transport_connect"),
            httpx.ReadTimeout: ("read_timeout", "transport_read"),
            httpx.WriteTimeout: ("write_timeout", "transport_write"),
            httpx.PoolTimeout: ("pool_timeout", "transport_pool"),
            httpx.ConnectError: ("connect_error", "transport_connect"),
            httpx.ReadError: ("read_error", "transport_read"),
            httpx.WriteError: ("write_error", "transport_write"),
            httpx.CloseError: ("close_error", "transport_close"),
            httpx.LocalProtocolError: ("local_protocol_error", "transport_protocol"),
            httpx.RemoteProtocolError: ("remote_protocol_error", "transport_protocol"),
            httpx.ProxyError: ("proxy_error", "transport_proxy"),
            httpx.UnsupportedProtocol: ("unsupported_protocol", "transport_protocol"),
        }
        code, stage = transport_codes.get(type(cause), ("transport_error", "transport"))
        if isinstance(exc, SdkTransportError):
            method = urlsplit(exc.url).path.rsplit("/", 1)[-1] or method
        budget = current_budget.get()
        if budget is not None:
            try:
                budget.check()
            except DataLensApiError as stopped:
                return DataLensApiError(str(stopped), method=method, remote_code=stopped.remote_code,
                                        dispatch_state="dispatched", stage=stage,
                                        response_received=False if stage in {"transport_connect", "transport_pool"} else None)
        return DataLensApiError("SDK request failed during transport", method=method,
                               remote_code=code, stage=stage,
                               provider_diagnostics=getattr(exc, "_datalens_request_diagnostics", None),
                               response_received=False if stage in {"transport_connect", "transport_pool"} else None)
    if isinstance(exc, SdkApiError):
        # The SDK message/details can contain SQL, data or an entire HTML body.
        # SDK 3.2.0 chains the HTTPStatusError; context itself has no headers.
        # Read bounded structured diagnostics from the actual response only.
        # Messages, details and business values are never returned.
        cause = exc.__cause__
        headers = (cause.response.headers if isinstance(cause, httpx.HTTPStatusError)
                   and cause.response.status_code == exc.context.status_code else None)
        diagnostics = response_diagnostics(headers)
        body_diagnostics = _body_diagnostics(cause.response if headers is not None else None)
        body_diagnostics.update(getattr(exc, "_datalens_request_diagnostics", {}))
        provider_method = urlsplit(exc.context.request_url or "").path.rsplit("/", 1)[-1] or method
        return DataLensApiError(
            f"DataLens request failed with HTTP {exc.context.status_code}",
            method=provider_method,
            http_status=exc.context.status_code,
            response_received=True,
            remote_code=body_diagnostics.pop("code", None) or _allowed_provider_code(exc.context.code) or "",
            provider_diagnostics=body_diagnostics,
            stage="provider_response",
            request_id=diagnostics["request_id"] or exc.context.request_id,
            trace_id=diagnostics["trace_id"],
            retry_after_sec=_retry_after(headers.get("Retry-After") if headers is not None else None),
        )
    return DataLensApiError("SDK operation failed without a classified provider response", method=method,
                           response_received=None, stage="sdk_operation")


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
    raise DataLensApiError("SDK returned an unsupported object representation", remote_code="invalid_response",
                           stage="response_validation", response_received=True, dispatch_state="dispatched")


def _canonical_object_type(value: str) -> str:
    from datalens_dev_mcp.objects.relations import canonical_object_type

    canonical = canonical_object_type(value)
    if canonical == "html_page":
        raise InputContractError("html_page reads use the typed API route")
    return canonical


def _entry_location(destination: dict[str, Any]) -> Any:
    values = [
        ("workbook", destination.get("workbook_id")),
        ("collection", destination.get("collection_id")),
        ("path", destination.get("path")),
    ]
    selected = [(kind, str(value)) for kind, value in values if value]
    if len(selected) != 1:
        raise InputContractError("destination must contain exactly one of workbook_id, collection_id or path")
    kind, value = selected[0]
    try:
        return getattr(datalens_sdk.EntryLocation, kind)(value)
    except (ValueError, TypeError) as exc:
        raise InputContractError(safe_error_text(exc)) from exc


def _draft_name(draft: dict[str, Any]) -> str:
    name = str(draft.get("name") or "")
    if not name:
        contract = draft.get("visual_contract") or draft.get("config") or {}
        name = str(((contract.get("object_name") or {}).get("value")) or "") if isinstance(contract, dict) else ""
    if not name:
        raise InputContractError("draft.name or visual_contract.object_name.value is required")
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
        raise InputContractError(f"unsupported editor variant: {variant}")
    return mapping[variant]


def _result_id(value: Any) -> str:
    direct = getattr(value, "id", None)
    if direct:
        return str(direct)
    raw = _json_object(value)
    return str(raw.get("id") or raw.get("entryId") or raw.get("entry_id") or "")


def _validate_editor_changes(snapshot: dict[str, Any], latest: dict[str, Any]) -> None:
    """Raw SDK replacement preserves unknown state but does not validate tabs."""
    from datalens_sdk._generated import dto
    from pydantic import TypeAdapter, ValidationError

    from datalens_dev_mcp.editor.validation import allowed_editor_fields

    carriers = {
        "table_node": "TableNodeNodeUpdateDataDTO",
        "d3_node": "D3NodeNodeUpdateDataDTO",
        "markdown_node": "MarkdownNodeNodeUpdateDataDTO",
        "advanced-chart_node": "AdvancedChartNodeNodeUpdateDataDTO",
        "control_node": "ControlNodeNodeUpdateDataDTO",
    }
    carrier = getattr(dto, carriers.get(str(snapshot.get("type")), ""), None)
    if carrier is None:
        raise InputContractError("Unsupported Editor renderer in SDK 3.2.0 installation contract")
    allowed = {field.alias or name: field for name, field in carrier.model_fields.items()}
    documented = allowed_editor_fields(str(snapshot.get("type")))
    data, previous = snapshot.get("data") or {}, latest.get("data") or {}
    changed_source = {}
    for key, value in data.items():
        if key in previous and previous[key] == value:
            continue
        if key not in documented or (key not in allowed and key != "activities"):
            raise InputContractError(f"Unsupported Editor tab or UI-managed field: {key}; no public SDK setter")
        changed_source[key] = value
        try:
            # Activities is absent from the generated DTO, but the existing raw
            # replacement carrier preserves data verbatim (SDK transport checked).
            TypeAdapter(allowed[key].rebuild_annotation() if key in allowed else str).validate_python(value)
        except ValidationError as exc:
            raise InputContractError(f"Editor tab {key} has an invalid value type for its SDK carrier") from exc

    from datalens_dev_mcp.editor.validation import validate_editor_source

    issues = validate_editor_source(changed_source)
    if issues:
        raise InputContractError(f"{issues[0]['path']}: {issues[0]['message']}")


def _validate_dashboard_snapshot(snapshot: dict[str, Any], *, from_artifact: bool = False) -> None:
    entry = snapshot.get("entry") if isinstance(snapshot.get("entry"), dict) else snapshot
    version = entry.get("version")
    if (version is not None and version != 2) or (from_artifact and version != 2):
        raise InputContractError(
            "Dashboard snapshot requires document version 2 (36-column layout). "
            "Re-export through API v3 or explicitly migrate the legacy artifact; coordinates are never guessed or scaled."
        )
    from datalens_dev_mcp.dashboard.composition import manual_input_field_types

    for _, path in manual_input_field_types(snapshot):
        raise InputContractError(
            f"{path}: fieldType is not supported for sourceType=manual, elementType=input by SDK 3.2.0; "
            'omit fieldType, e.g. source={"elementType":"input","fieldName":"rate","defaultValue":"50"}'
        )
    data = entry.get("data") or {}
    tabs = data.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        raise InputContractError("Dashboard requires at least one tab")
    for tab in tabs:
        for item in tab.get("layout", []):
            x, width = item.get("x"), item.get("w")
            if type(x) not in (int, float) or type(width) not in (int, float) or x < 0 or width < 1 or x + width > 36:
                raise InputContractError("Dashboard V2 layout must fit its existing 36-column grid")


def _validate_wizard_snapshot(snapshot: dict[str, Any]) -> None:
    data = snapshot.get("data") or {}
    if snapshot.get("version", 1) != 1 or "datasetsPartialFields" in data or "datasetsIds" in data:
        raise InputContractError(
            "Legacy Wizard V2 artifact is incompatible with SDK 3.2.0 document V1. "
            "Re-export through API v3 or rebuild with the typed Wizard recipe using exact Dataset GUIDs."
        )
