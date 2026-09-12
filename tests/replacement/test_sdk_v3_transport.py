"""Public handlers using the installed SDK; only HTTP and configuration are synthetic."""

import json
from copy import deepcopy
from io import BytesIO

import datalens_sdk
import httpx
import pytest

from datalens_dev_mcp.api.runtime import DataLensRuntime
from datalens_dev_mcp.api.sdk_adapter import SDK_VERSION, SdkAdapter
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.server import call_tool as _call_tool


def test_installed_sdk_v3_contract_is_admitted():
    assert datalens_sdk.__version__ == "3.0.0"
    assert SDK_VERSION == "3.0.0"
    SdkAdapter()


def call_tool(name, arguments):
    return _call_tool(name, arguments)["structuredContent"]


def dataset_state():
    return {
        "id": "synthetic-dataset",
        "revId": "A1",
        "dataset": {
            "revision_id": "I1",
            "description": "before",
            "sources": [],
            "source_avatars": [],
            "avatar_relations": [],
            "result_schema": [
                {"guid": "one", "title": "Duplicate", "cast": "string", "type": "DIMENSION", "calc_mode": "direct"},
                {
                    "guid": "two",
                    "title": "Duplicate",
                    "cast": "float",
                    "type": "MEASURE",
                    "calc_mode": "direct",
                    "aggregation": "sum",
                },
            ],
            "obligatory_filters": [],
            "rls2": {},
            "future": {"revision": "business-value", "empty": [], "text": "", "null": None},
        },
    }


class Provider:
    def __init__(self, state):
        self.state = deepcopy(state)
        self.requests = []
        self.writes = []
        self.after_write = None
        self.before_read = None
        self.reads = 0

    def handle(self, request):
        payload = json.loads(request.content)
        method = request.url.path.rsplit("/", 1)[-1]
        self.requests.append((method, payload, dict(request.headers)))
        if method.startswith("get"):
            self.reads += 1
            if self.before_read:
                self.before_read(self, self.reads)
        elif method.startswith(("create", "update")):
            self.writes.append((method, payload))
            if method == "updateDataset":
                self.state["dataset"] = deepcopy(payload["data"]["dataset"])
                self.state["revId"] = "A2"
                self.state["dataset"]["revision_id"] = "I2"
            elif method == "createWizardChart":
                self.state = wizard_state(payload["data"])
            elif method == "updateWizardChart":
                self.state["data"] = deepcopy(payload["data"])
                self.state["revId"] = payload.get("revId", "S3")
                if payload.get("mode") == "publish":
                    self.state["publishedId"] = self.state["revId"]
            elif method == "updateEditorChart":
                self.state["data"] = deepcopy(payload["entry"]["data"])
                self.state["revId"] = "S3"
            elif method == "updateDashboard":
                self.state["entry"]["data"] = deepcopy(payload["entry"]["data"])
                if "annotation" in payload["entry"]:
                    self.state["entry"]["annotation"] = deepcopy(payload["entry"]["annotation"])
                if payload.get("mode") == "publish":
                    self.state["entry"]["publishedId"] = payload["entry"].get("revId", "S3")
                self.state["entry"]["revId"] = payload["entry"].get("revId", "S3")
            if self.after_write:
                self.after_write(self)
        value = deepcopy(self.state)
        if method.endswith(("WizardChart", "EditorChart")) and "entry" not in value:
            value = {"entry": value}
        return httpx.Response(200, json=value)


@pytest.fixture
def install_runtime(monkeypatch, tmp_path):
    runtimes = []

    def install(provider, installation="yacloud"):
        # Runtime injection is configuration only. Both transports execute the
        # real public handler, services, SDK conversion, and error normalization.
        config = DataLensConfig(
            installation=installation,
            base_url="https://synthetic.invalid",
            org_id="synthetic-org",
            iam_token="synthetic-token",
        )
        cls = datalens_sdk.DataLensClientYC if installation == "yacloud" else datalens_sdk.DataLensClientEnterprise
        client = cls(auth=None, base_url=config.base_url, transport=httpx.MockTransport(provider.handle))
        runtime = DataLensRuntime(config, sdk_client=client)
        runtimes.append(runtime)
        monkeypatch.setattr("datalens_dev_mcp.api.runtime.get_runtime", lambda *args: runtime)
        monkeypatch.setattr("datalens_dev_mcp.server.get_runtime", lambda *args: runtime)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

        def direct(request, **kwargs):
            response = provider.handle(
                httpx.Request("POST", request.full_url, content=request.data, headers=dict(request.header_items()))
            )
            return BytesIO(response.content)

        monkeypatch.setattr("datalens_dev_mcp.api.client.request.urlopen", direct)
        return runtime

    yield install
    for runtime in runtimes:
        runtime.close()


def update(object_type, object_id, patch, operation="sdk-v3-update", **extra):
    return call_tool(
        "dl_object_update",
        {
            "changes": [{"object_type": object_type, "object_id": object_id, "patch": patch, **extra}],
            "operation_id": operation,
        },
    )


@pytest.mark.parametrize("installation", ["yacloud", "enterprise"])
def test_public_dataset_full_state_and_reconcile(install_runtime, installation):
    initial = dataset_state()
    provider = Provider(initial)
    install_runtime(provider, installation)
    desired = deepcopy(initial["dataset"])
    desired["description"] = "after"
    result = update("dataset", "synthetic-dataset", {"dataset": desired})
    assert result["results"][0]["status"] == "completed", json.dumps(result, indent=2)
    assert provider.writes == [("updateDataset", {"datasetId": "synthetic-dataset", "data": {"dataset": desired}})]
    assert provider.state["dataset"]["future"] == initial["dataset"]["future"]
    assert all(headers["x-dl-api-version"] == "3" for _, _, headers in provider.requests)
    call_tool("dl_operation_reconcile", {"operation_id": "sdk-v3-update"})
    assert len(provider.writes) == 1


def test_public_dataset_wrong_business_revision_is_mismatch(install_runtime):
    provider = Provider(dataset_state())
    install_runtime(provider)
    provider.after_write = lambda p: p.state["dataset"]["future"].update(revision="wrong")
    result = update("dataset", "synthetic-dataset", {"dataset": {"future": {"revision": "requested"}}})
    assert result["results"][0]["code"] == "readback_mismatch", json.dumps(result, indent=2)


def test_public_dataset_stale_then_fresh_patch_preserves_manual_filter(install_runtime):
    provider = Provider(dataset_state())
    install_runtime(provider)

    def drift(p, count):
        if count == 2:
            p.state["revId"] = "A-manual"
            p.state["dataset"]["revision_id"] = "I-manual"
            p.state["dataset"]["obligatory_filters"] = [{"field": "one", "value": "manual"}]

    provider.before_read = drift
    stale = update("dataset", "synthetic-dataset", {"dataset": {"description": "after"}}, expected_revision="A1")
    assert stale["results"][0]["code"] == "revision_conflict", stale
    assert not provider.writes
    fresh = update(
        "dataset",
        "synthetic-dataset",
        {"dataset": {"description": "after"}},
        operation="fresh",
        expected_revision="A-manual",
    )
    assert fresh["results"][0]["status"] == "completed", fresh
    assert provider.writes[0][1]["data"]["dataset"]["obligatory_filters"][0]["value"] == "manual"


def test_enterprise_configuration_uses_own_client_and_no_cloud_org_header(monkeypatch, tmp_path):
    config = DataLensConfig.from_env(
        {
            "XDG_CONFIG_HOME": str(tmp_path),
            "DATALENS_INSTALLATION": "enterprise",
            "DATALENS_API_BASE_URL": "https://enterprise.invalid",
            "DATALENS_TOKEN": "synthetic-enterprise",
        }
    )
    adapter = SdkAdapter(config)
    client = adapter._sdk_client()
    assert isinstance(client, datalens_sdk.DataLensClientEnterprise)
    from datalens_dev_mcp.api.client import DataLensApiClient

    headers = DataLensApiClient(config)._headers("getWorkbooksList")
    assert headers["authorization"] == "Bearer synthetic-enterprise"
    assert headers["x-dl-api-version"] == "3"
    assert "x-dl-org-id" not in headers
    adapter.close()


@pytest.mark.parametrize(
    "env",
    [
        {"DATALENS_INSTALLATION": "enterprise"},
        {"DATALENS_INSTALLATION": "unknown"},
        {"DATALENS_INSTALLATION": "enterprise", "DATALENS_API_BASE_URL": "https://api.datalens.tech"},
    ],
)
def test_invalid_installation_has_no_cloud_fallback(env, tmp_path):
    with pytest.raises(ValueError):
        DataLensConfig.from_env({"XDG_CONFIG_HOME": str(tmp_path), **env})


def test_public_wizard_guid_payload_v1_and_unsupported_setter(install_runtime):
    provider = Provider(dataset_state())
    install_runtime(provider)
    draft = {
        "client_ref": "table",
        "object_type": "wizard_chart",
        "name": "Synthetic",
        "wizard": {
            "dataset_id": "synthetic-dataset",
            "visualization": "flat_table",
            "roles": {"columns": ["two", "one"]},
        },
    }
    result = call_tool(
        "dl_object_create",
        {"drafts": [draft], "destination": {"workbook_id": "synthetic-workbook"}, "operation_id": "wizard-create"},
    )
    assert result["results"][0]["status"] == "completed", json.dumps(result, indent=2)
    data = provider.writes[0][1]["data"]
    assert provider.state["version"] == 1
    assert [field["guid"] for field in data["visualization"]["columns"]["items"]] == ["two", "one"]
    assert data["sources"]["datasetsIds"] == ["synthetic-dataset"]
    assert "template" not in data and "placeholders" not in data
    assert "two" in json.dumps(data) and "one" in json.dumps(data)
    provider.state = dataset_state()
    draft["wizard"]["legend"] = "show"
    result = call_tool(
        "dl_object_create",
        {"drafts": [draft], "destination": {"workbook_id": "synthetic-workbook"}, "operation_id": "unsupported-setter"},
    )
    assert result["results"][0]["code"] == "input_error", json.dumps(result, indent=2)
    assert len(provider.writes) == 1


def editor_state():
    return {
        "entryId": "synthetic-editor",
        "type": "table_node",
        "revId": "S2",
        "data": {
            "meta": '{"alias":"synthetic-dataset"}',
            "params": "",
            "sources": "module.exports={};",
            "prepare": "module.exports=[];",
            "config": "module.exports={};",
            "secrets": {"password": "NEVER-TRANSMIT-SYNTHETIC"},
        },
        "links": {"alias": "synthetic-dataset"},
    }


def test_public_editor_one_tab_preserves_others_and_strips_secrets(install_runtime):
    provider = Provider(editor_state())
    install_runtime(provider)
    result = update("editor_chart", "synthetic-editor", {"data": {"prepare": "module.exports=[1];"}})
    assert result["results"][0]["status"] == "completed", json.dumps(result, indent=2)
    data = provider.writes[0][1]["entry"]["data"]
    assert data["meta"] == editor_state()["data"]["meta"]
    assert data["sources"] == editor_state()["data"]["sources"]
    assert data["params"] == ""
    assert "secrets" not in data
    assert "NEVER-TRANSMIT" not in json.dumps(result)


def test_public_editor_activities_rejected_before_network_write(install_runtime):
    provider = Provider(editor_state())
    install_runtime(provider)
    result = update("editor_chart", "synthetic-editor", {"data": {"activities": "module.exports={};"}})
    assert result["results"][0]["code"] == "input_error", json.dumps(result, indent=2)
    assert not provider.writes


def test_preview_malformed_response_is_not_empty_success(install_runtime):
    from datalens_dev_mcp.dataset.preview import DatasetPreviewService

    provider = Provider({"notRows": []})
    runtime = install_runtime(provider)
    with pytest.raises(Exception, match="rows|schema|response"):
        DatasetPreviewService(runtime.api).preview(
            dataset_id="synthetic", fields=dataset_state()["dataset"]["result_schema"], columns=["one"]
        )


def wizard_state(data):
    return {
        "entryId": "synthetic-chart",
        "type": "table_wizard_node",
        "data": data,
        "revId": "S2",
        "createdAt": "2026-01-01",
        "createdBy": "synthetic",
        "hidden": False,
        "key": "Synthetic",
        "meta": {},
        "public": False,
        "publishedId": "P1",
        "savedId": "S2",
        "scope": "widget",
        "tenantId": "synthetic",
        "updatedAt": "2026-01-01",
        "updatedBy": "synthetic",
        "version": 1,
        "workbookId": "synthetic-workbook",
    }


def dashboard_state(version=2):
    from datalens_sdk import DashboardTab, EntryLocation
    from datalens_sdk.converter.dashboard import DashboardConverter

    with datalens_sdk.DataLensClientYC(auth=None) as client:
        tab = DashboardTab("First", tab_id="first")
        tab.add_selector(chart="synthetic-selector", title="Selector", item_id="selector", at=(0, 0, 9, 2))
        tab.add_text("Manual", item_id="manual", at=(0, 2, 18, 6))
        other = DashboardTab("Second", tab_id="second", hidden=True)
        other.add_text("Other", item_id="other", at=(0, 0, 36, 2))
        builder = (
            client.create.dashboard(name="Synthetic", location=EntryLocation.workbook("synthetic-workbook"))
            .add_tab(tab)
            .add_tab(other)
        )
        entry = DashboardConverter.from_domain_create(builder.to_spec()).to_payload()["entry"]
    entry.update(entryId="synthetic-dashboard", revId="S2", savedId="S2", publishedId="P1", version=version)
    return {"entry": entry}


def test_public_dashboard_v2_geometry_unchanged(install_runtime):
    initial = dashboard_state()
    provider = Provider(initial)
    install_runtime(provider)
    result = update("dashboard", "synthetic-dashboard", {"entry": {"annotation": {"description": "after"}}})
    assert result["results"][0]["status"] == "completed", json.dumps(result, indent=2)
    assert provider.writes[0][1]["entry"]["data"] == initial["entry"]["data"]
    assert [tab["id"] for tab in provider.state["entry"]["data"]["tabs"]] == ["first", "second"]


def test_public_dashboard_legacy_layout_requires_explicit_migration(install_runtime):
    provider = Provider(dashboard_state(version=1))
    install_runtime(provider)
    result = update("dashboard", "synthetic-dashboard", {"entry": {"annotation": {"description": "after"}}})
    assert result["results"][0]["code"] == "input_error", json.dumps(result, indent=2)
    assert not provider.writes


def test_public_raw_dashboard_create_requires_tab_and_known_schema(install_runtime):
    initial = dashboard_state()
    initial["entry"]["data"]["tabs"] = []
    provider = Provider(initial)
    install_runtime(provider)
    result = call_tool(
        "dl_object_create",
        {
            "drafts": [
                {"client_ref": "dashboard", "object_type": "dashboard", "name": "Synthetic", "snapshot": initial}
            ],
            "destination": {"workbook_id": "synthetic-workbook"},
            "operation_id": "empty-dashboard",
        },
    )
    assert result["results"][0]["code"] == "input_error", json.dumps(result, indent=2)
    assert not provider.writes


@pytest.mark.parametrize("kind", ["dashboard", "wizard_chart"])
def test_public_publish_uses_exact_saved_revision(install_runtime, kind):
    initial = (
        dashboard_state()
        if kind == "dashboard"
        else wizard_state(
            {
                "sources": {"datasetsIds": ["synthetic-dataset"]},
                "visualization": {
                    "type": "flatTable",
                    "columns": {"items": []},
                    "colors": {"items": [], "settings": {}},
                    "sort": {"items": []},
                },
            }
        )
    )
    provider = Provider(initial)
    install_runtime(provider)
    target = "synthetic-dashboard" if kind == "dashboard" else "synthetic-chart"
    result = call_tool(
        "dl_object_publish",
        {
            "targets": [{"object_type": kind, "object_id": target, "expected_saved_revision": "S2"}],
            "operation_id": "publish-exact",
        },
    )
    payload = provider.writes[0][1]
    assert (payload.get("entry") or payload).get("revId") == "S2"
    assert result["results"][0]["status"] == "completed", json.dumps(result, indent=2)
    assert payload["mode"] == "publish"


def test_public_publish_third_revision_is_not_success(install_runtime):
    provider = Provider(dashboard_state())
    install_runtime(provider)

    def drift(p, count):
        if count == 3:
            p.state["entry"]["revId"] = "S-unrequested"
            p.state["entry"]["publishedId"] = "S-unrequested"

    provider.before_read = drift
    result = call_tool(
        "dl_object_publish",
        {
            "targets": [
                {"object_type": "dashboard", "object_id": "synthetic-dashboard", "expected_saved_revision": "S2"}
            ],
            "operation_id": "publish-drift",
        },
    )
    assert result["results"][0]["code"] == "readback_mismatch", json.dumps(result, indent=2)


@pytest.mark.parametrize("kind", ["zero", "denied", "unavailable", "malformed", "transport", "over_limit"])
def test_public_preview_real_sdk_bounded_and_distinct(install_runtime, kind):
    class PreviewProvider(Provider):
        def handle(self, request):
            self.requests.append(
                (request.url.path.rsplit("/", 1)[-1], json.loads(request.content), dict(request.headers))
            )
            if kind == "transport":
                raise httpx.ReadTimeout("synthetic read failure", request=request)
            if kind in {"denied", "unavailable"}:
                return httpx.Response(
                    403 if kind == "denied" else 503,
                    json={"code": "SOURCE_UNAVAILABLE" if kind == "unavailable" else "DENIED", "message": kind},
                )
            body = {"schema": [{"guid": "one", "name": "Duplicate", "type": "string"}], "rows": []}
            if kind == "malformed":
                body = {"notRows": []}
            if kind == "over_limit":
                body["rows"] = [["x"]] * 3
            return httpx.Response(200, json=body)

    provider = PreviewProvider({})
    install_runtime(provider)
    result = call_tool(
        "dl_dataset_preview",
        {
            "dataset_id": "synthetic-dataset",
            "columns": ["one"],
            "fields": dataset_state()["dataset"]["result_schema"],
            "limit": 2,
        },
    )
    if kind == "zero":
        assert result["ok"] is True and result["rows"] == []
        assert result["evidence"] == "dataset_query_only"
    else:
        assert result["ok"] is False, result
        assert "rows" not in result
        if kind == "denied":
            assert result["http_status"] == 403
        if kind == "unavailable":
            assert result["http_status"] == 503
    assert provider.requests[0][0] == "getDatasetData"
    assert provider.requests[0][1]["columns"] == ["one"]
    assert provider.requests[0][1]["limit"] == 2
    assert provider.requests[0][2]["x-dl-api-version"] == "3"


def test_server_info_keeps_loaded_sdk_identity_when_disk_distribution_changes(monkeypatch):
    import datalens_dev_mcp.runtime_identity as identity
    from datalens_dev_mcp.server import dl_server_info

    before = dl_server_info()
    monkeypatch.setattr(
        identity.metadata, "version", lambda name: "future-installed" if name == "datalens-sdk" else "other-package"
    )
    after = dl_server_info()
    assert before["runtime"]["sdk_version"] == "3.0.0"
    assert after["runtime"]["sdk_version"] == before["runtime"]["sdk_version"]
    assert after["installed_sdk_version"] == "future-installed"
    assert after["active_sdk_matches_installed"] is False


def test_raw_editor_create_cannot_bypass_activities_contract(install_runtime):
    provider = Provider(editor_state())
    runtime = install_runtime(provider)
    snapshot = editor_state()
    snapshot["data"].pop("secrets", None)
    snapshot["data"]["activities"] = "module.exports={};"
    from datalens_dev_mcp.api.errors import InputContractError

    with pytest.raises(InputContractError, match="activities"):
        runtime.sdk.create(
            {"object_type": "editor_chart", "name": "Synthetic", "snapshot": snapshot},
            {"workbook_id": "synthetic-workbook"},
        )
    assert not provider.writes


def test_wizard_legacy_v2_artifact_rejected_locally(install_runtime):
    provider = Provider(dataset_state())
    runtime = install_runtime(provider)
    snapshot = wizard_state(
        {
            "datasetsIds": ["synthetic-dataset"],
            "datasetsPartialFields": [],
            "visualization": {"type": "flatTable", "placeholders": []},
        }
    )
    snapshot["version"] = 2
    from datalens_dev_mcp.api.errors import InputContractError

    with pytest.raises(InputContractError, match="V1|v1|legacy|version|V2"):
        runtime.sdk.create(
            {"object_type": "wizard_chart", "name": "Synthetic", "snapshot": snapshot},
            {"workbook_id": "synthetic-workbook"},
        )
    assert not provider.writes


@pytest.mark.parametrize("effect", ["create", "update"])
def test_html_page_content_authoring_stops_before_dispatch_without_readback_contract(install_runtime, effect):
    provider = Provider(
        {
            "entryId": "synthetic-html",
            "revId": "S2",
            "savedId": "S2",
            "data": {},
            "meta": {"objectId": "synthetic-storage"},
        }
    )
    install_runtime(provider)
    if effect == "create":
        result = call_tool(
            "dl_object_create",
            {
                "drafts": [
                    {
                        "client_ref": "page",
                        "object_type": "html_page",
                        "name": "Synthetic",
                        "content": "<html><body>Local artifact</body></html>",
                    }
                ],
                "destination": {"workbook_id": "synthetic-workbook"},
                "operation_id": "html-create",
            },
        )
    else:
        result = update("html_page", "synthetic-html", {"content": "<html><body>Local artifact</body></html>"})
    assert result["results"][0]["code"] == "input_error", json.dumps(result, indent=2)
    assert "content readback" in result["results"][0]["error"]
    assert not provider.writes


@pytest.mark.parametrize("stale", [False, True])
def test_html_page_metadata_and_exact_revision_publish(install_runtime, stale):
    provider = Provider(
        {
            "entryId": "synthetic-html",
            "revId": "S2",
            "savedId": "S2",
            "data": {},
            "meta": {"objectId": "synthetic-storage"},
        }
    )
    install_runtime(provider)

    def drift(p, count):
        if stale and count == 3:
            p.state["revId"] = "S-other"

    provider.before_read = drift
    metadata = call_tool("dl_object_get", {"object_type": "html_page", "object_id": "synthetic-html"})
    assert metadata["object"]["meta"]["objectId"] == "synthetic-storage"
    assert "content" not in metadata["object"]
    result = call_tool(
        "dl_object_publish",
        {
            "targets": [{"object_type": "html_page", "object_id": "synthetic-html", "expected_saved_revision": "S2"}],
            "operation_id": "html-publish",
        },
    )
    if stale:
        assert result["results"][0]["code"] == "revision_conflict", result
        assert not provider.writes
    else:
        assert result["results"][0]["status"] == "completed", json.dumps(result, indent=2)
        assert provider.writes == [("updateHtmlPage", {"entryId": "synthetic-html", "mode": "publish", "revId": "S2"})]


def test_public_relations_preserve_unknown_scope_and_page_cursor(install_runtime):
    class RelationsProvider(Provider):
        def handle(self, request):
            payload = json.loads(request.content)
            self.requests.append((request.url.path.rsplit("/", 1)[-1], payload, dict(request.headers)))
            return httpx.Response(
                200,
                json={
                    "entries": [
                        {"entryId": "known", "scope": "dataset"},
                        {"entryId": "future", "scope": "future_scope"},
                    ],
                    "nextPageToken": "next",
                },
            )

    provider = RelationsProvider({})
    install_runtime(provider)
    result = call_tool("dl_object_relations", {"object_id": "synthetic-dashboard", "max_pages": 1})
    assert result["complete"] is False and result["next_page_token"] == "next"
    assert {entry["type"] for entry in result["relations"]} == {"dataset", "future_scope"}
    assert provider.requests[0][2]["x-dl-api-version"] == "3"


def test_sdk_navigation_unknown_request_scope_rejected_before_transport(install_runtime):
    provider = Provider({})
    runtime = install_runtime(provider)
    with pytest.raises(datalens_sdk.DataLensValidationError, match="scope"):
        runtime.sdk._sdk_client().navigation.get_entries(scope="future_scope")
    assert not provider.requests


@pytest.mark.parametrize("drift", ["identity", "branch"])
def test_second_sdk_fetch_rejects_wrong_target_or_branch_before_write(install_runtime, drift):
    provider = Provider(editor_state())
    install_runtime(provider)

    def changed(p, count):
        if count == 2:
            p.state["entryId" if drift == "identity" else "branch"] = (
                "wrong-target" if drift == "identity" else "published"
            )

    provider.before_read = changed
    result = update("editor_chart", "synthetic-editor", {"data": {"prepare": "module.exports=[1];"}})
    assert result["results"][0]["status"] != "completed"
    assert not provider.writes


def test_preview_refresh_uses_runtime_owner_once(monkeypatch):
    calls, refreshes = [], []

    def network(transport, request):
        calls.append(request.headers.get("authorization"))
        if len(calls) == 1:
            return httpx.Response(401, json={"code": "UNAUTHORIZED", "message": "expired"})
        return httpx.Response(200, json={"schema": [{"guid": "one", "name": "One", "type": "string"}], "rows": []})

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", network)
    config = DataLensConfig(
        base_url="https://synthetic.invalid", org_id="synthetic", iam_token="synthetic-expired", refresh_available=True
    )
    runtime = DataLensRuntime(config, credential_refresher=lambda: refreshes.append(1) or "synthetic-fresh")
    monkeypatch.setattr("datalens_dev_mcp.server.get_runtime", lambda: runtime)
    result = call_tool(
        "dl_dataset_preview",
        {"dataset_id": "synthetic", "columns": ["one"], "fields": dataset_state()["dataset"]["result_schema"]},
    )
    assert result["ok"], result
    assert refreshes == [1]
    assert calls == ["Bearer synthetic-expired", "Bearer synthetic-fresh"]
    runtime.close()
