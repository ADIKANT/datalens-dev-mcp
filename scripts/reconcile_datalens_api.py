#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datalens_dev_mcp.knowledge.corpus import (  # noqa: E402
    DEFAULT_CORPUS_ROOT,
    normalize_corpus_root,
    resolve_corpus_root as resolve_shared_corpus_root,
)

CONFIG_PATH = ROOT / "config" / "datalens_api_methods.json"
SCHEMA_DIR = ROOT / "schemas" / "datalens-api"
DOCS_DIR = ROOT / "docs" / "datalens"
EXAMPLES_DIR = ROOT / "examples" / "datalens_api"
PACKAGE_CONFIG_DIR = ROOT / "src" / "datalens_dev_mcp" / "assets" / "config"
PACKAGE_SCHEMA_DIR = ROOT / "src" / "datalens_dev_mcp" / "assets" / "schemas" / "datalens-api"

SOURCE = "https://api.datalens.tech/json/"
LEGACY_API_HEADER_VERSION = "1"
SCHEMA_VERSION = "2026-06-25.datalens_api_methods.v3"
EXPECTED_OPERATION_COUNT = 88
EXPECTED_PATH_COUNT = 88

GUARDED_WRITE_METHODS = {
    "createConnection",
    "updateConnection",
    "createDashboard",
    "updateDashboard",
    "createDataset",
    "updateDataset",
    "createEditorChart",
    "updateEditorChart",
    "createWizardChart",
    "updateWizardChart",
    "createQLChart",
    "updateQLChart",
    "createWorkbook",
    "updateWorkbook",
    "startWorkbookExport",
    "startWorkbookImport",
    "updateCollectionAccessBindings",
    "updateWorkbookAccessBindings",
}

UNSUPPORTED_METHODS = {
    "assignLicenses",
    "cancelWorkbookExport",
    "createCollection",
    "createEmbed",
    "createEmbeddingSecret",
    "createFolder",
    "createReport",
    "updateCollection",
    "updateEmbed",
    "updateReport",
}

FORBIDDEN_PREFIXES = ("delete", "move")
FORBIDDEN_METHODS = {
    "renameEntry",
    "setLicenseLimit",
    "deleteQLChart",
    "modifyPermissions",
}

ROUTE_BY_METHOD = {
    "createConnection": "connector_operation",
    "updateConnection": "connector_operation",
    "createDashboard": "dashboard_relation_operation",
    "updateDashboard": "dashboard_relation_operation",
    "createDataset": "dataset_operation",
    "updateDataset": "dataset_operation",
    "validateDataset": "dataset_operation",
    "createEditorChart": "editor_advanced",
    "updateEditorChart": "editor_advanced",
    "createWizardChart": "wizard_native",
    "updateWizardChart": "wizard_native",
    "createQLChart": "ql_explicit",
    "updateQLChart": "ql_explicit",
    "createWorkbook": "guarded_write",
    "updateWorkbook": "guarded_write",
    "startWorkbookExport": "guarded_write",
    "startWorkbookImport": "guarded_write",
    "updateCollectionAccessBindings": "guarded_write",
    "updateWorkbookAccessBindings": "guarded_write",
}

DIRECT_TOOL_BY_METHOD = {
    "getDashboard": "dl_get_dashboard / dl_read_object",
    "getEditorChart": "dl_get_editor_chart / dl_read_object",
    "getWizardChart": "dl_get_wizard_chart / dl_read_object",
    "getDataset": "dl_get_dataset / dl_read_object",
    "getConnection": "dl_get_connection / dl_read_object",
    "getEntriesRelations": "dl_get_entries_relations / dl_list_related_objects",
    "getWorkbook": "dl_get_workbook_entries / dl_rpc_readonly",
    "getWorkbookEntries": "dl_get_workbook_entries",
    "getWorkbooksList": "dl_list_workbooks",
    "createConnection": "dl_create_connector_plan",
    "updateConnection": "dl_update_connector_plan",
    "createDashboard": "dl_create_dashboard_plan",
    "updateDashboard": "dl_update_dashboard_plan / dl_save_object_plan / dl_publish_object_plan",
    "createDataset": "dl_create_dataset_plan",
    "updateDataset": "dl_update_dataset_plan",
    "createEditorChart": "dl_create_editor_chart_plan",
    "updateEditorChart": "dl_update_editor_chart_plan",
    "createWizardChart": "dl_create_wizard_chart_plan",
    "updateWizardChart": "dl_update_wizard_chart_plan",
    "getQLChart": "dl_read_object",
    "createQLChart": "dl_plan_object_create",
    "updateQLChart": "dl_plan_object_update",
}


def timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(stable_json(value).encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def corpus_input_paths(corpus_root: Path) -> tuple[Path, Path, Path, Path]:
    return (
        corpus_root / "raw" / "api" / "openapi.json",
        corpus_root / "api_inventory.json",
        corpus_root / "reports" / "content_hashes.json",
        corpus_root / "reports" / "validation.md",
    )


def clean_summary(text: str) -> str:
    return text.replace("🚧 ", "").strip()


UPSTREAM_SCHEMA_ANNOTATION_KEYS = {
    "description",
    "title",
    "summary",
    "example",
    "examples",
    "externalDocs",
}


def strip_upstream_schema_annotations(value: Any) -> Any:
    """Retain validation structure while removing upstream prose annotations."""
    if isinstance(value, dict):
        return {
            key: strip_upstream_schema_annotations(nested)
            for key, nested in value.items()
            if key not in UPSTREAM_SCHEMA_ANNOTATION_KEYS
        }
    if isinstance(value, list):
        return [strip_upstream_schema_annotations(item) for item in value]
    return value


def project_method_summary(method: str) -> str:
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", method)
    return words[:1].upper() + words[1:]


def method_name_from_path(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def pascal_method_name(method: str) -> str:
    return method[:1].upper() + method[1:]


def inline_schema_name(method: str, direction: str) -> str:
    return f"{pascal_method_name(method)}{direction}"


def schema_ref_name(schema: dict[str, Any] | None, *, method: str, direction: str) -> str:
    if not schema:
        return ""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return ref.rsplit("/", 1)[-1]
    if "oneOf" in schema:
        return inline_schema_name(method, direction)
    if "anyOf" in schema:
        return inline_schema_name(method, direction)
    if schema.get("type") in {"object", "array"} or schema.get("properties"):
        return inline_schema_name(method, direction)
    return str(schema.get("type") or inline_schema_name(method, direction))


def json_media_schema(operation: dict[str, Any], direction: str) -> dict[str, Any]:
    if direction == "Request":
        content = (operation.get("requestBody") or {}).get("content") or {}
    else:
        responses = operation.get("responses") or {}
        response = responses.get("200") or responses.get("201") or responses.get("default") or {}
        content = response.get("content") or {}
    media = content.get("application/json") or next(iter(content.values()), {})
    schema = media.get("schema") or {}
    return copy.deepcopy(schema) if isinstance(schema, dict) else {}


def required_api_header_version(spec: dict[str, Any]) -> str:
    parameter = ((spec.get("components") or {}).get("parameters") or {}).get("ApiVersionHeader") or {}
    schema = parameter.get("schema") or {}
    value = schema.get("const") or schema.get("default") or schema.get("example")
    return str(value or LEGACY_API_HEADER_VERSION)


def infer_mode(method: str, tag: str) -> str:
    if method in FORBIDDEN_METHODS or method.startswith(FORBIDDEN_PREFIXES):
        return "forbidden"
    if method in GUARDED_WRITE_METHODS:
        return "guarded_write"
    if method in UNSUPPORTED_METHODS:
        return "unsupported"
    if method.startswith(("get", "list", "batchList", "dlsSuggest")) or method == "validateDataset":
        return "readonly"
    if tag in {"Audit", "Access"}:
        return "readonly"
    return "unsupported"


def support_status(method: str, tag: str, mode: str) -> str:
    if mode == "guarded_write":
        return "PLAN_ONLY_SUPPORTED"
    if mode == "readonly":
        return "EXECUTABLE_TOOL_SUPPORTED"
    if mode == "forbidden":
        return "READ_ONLY_REFERENCE"
    return "UNSUPPORTED_NO_VALIDATED_METHOD"


def support_reason(method: str, tag: str, mode: str) -> str:
    if tag == "QL" and mode == "guarded_write":
        return "QL create/update is guarded and requires route=ql_explicit plus direct-user-request provenance."
    if tag == "QL" and mode == "readonly":
        return "QL read is available; QL is never selected automatically for authoring."
    if tag == "QL" and mode == "forbidden":
        return "QL delete remains closed by route policy."
    if mode == "guarded_write":
        return "Official method exists, but MCP exposes plan/safe-apply behavior by default."
    if mode == "readonly":
        return "Curated read-only RPC can be called without enabling writes."
    if mode == "forbidden":
        return "Official method is documented but blocked by destructive/move/license/permission policy."
    return "No validated MCP workflow or payload contract is implemented."


def doc_url(method: str, inventory_by_method: dict[str, dict[str, Any]]) -> str:
    inventory_item = inventory_by_method.get(method) or {}
    return str(inventory_item.get("markdown_source_url") or f"https://yandex.cloud/ru/docs/datalens/openapi-ref/{method}")


def build_support_overlay() -> dict[str, Any]:
    return {
        "schema_version": "2026-06-25.datalens_api_support_policy.v1",
        "guarded_write_methods": sorted(GUARDED_WRITE_METHODS),
        "unsupported_methods": sorted(UNSUPPORTED_METHODS),
        "forbidden_methods": sorted(FORBIDDEN_METHODS),
        "forbidden_prefixes": sorted(FORBIDDEN_PREFIXES),
        "route_by_method": dict(sorted(ROUTE_BY_METHOD.items())),
        "direct_tool_by_method": dict(sorted(DIRECT_TOOL_BY_METHOD.items())),
        "ql_policy": "read_create_update_explicit_user_request_only; delete_closed; never_automatic",
        "source_inventory_policy": "OpenAPI inventory is source evidence; support policy is MCP-local overlay.",
    }


def build_catalog(
    spec: dict[str, Any],
    inventory: dict[str, Any],
    operation_schema_index: dict[str, dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    inventory_by_method = {
        str(item.get("operation_name") or item.get("method") or ""): item
        for item in inventory.get("operations", [])
        if isinstance(item, dict)
    }
    api_version = required_api_header_version(spec)
    methods: list[dict[str, Any]] = []
    for path, operations in sorted(spec.get("paths", {}).items()):
        if not path.startswith("/rpc/") or not isinstance(operations, dict):
            continue
        for http_method, operation in operations.items():
            if http_method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            method = method_name_from_path(path)
            tag = (operation.get("tags") or [""])[0]
            mode = infer_mode(method, tag)
            schema_refs = operation_schema_index[method]
            methods.append(
                {
                    "method": method,
                    "path": path,
                    "http_method": http_method.upper(),
                    "tag": tag,
                    "summary": project_method_summary(method),
                    "description": f"DataLens RPC method `{method}`.",
                    "experimental": "Experimental" in (operation.get("summary") or ""),
                    "mode": mode,
                    "support_status": support_status(method, tag, mode),
                    "support_reason": support_reason(method, tag, mode),
                    "mcp_route": ROUTE_BY_METHOD.get(method, "read_only" if mode == "readonly" else mode),
                    "mcp_tool": DIRECT_TOOL_BY_METHOD.get(
                        method,
                        "dl_rpc_readonly" if mode == "readonly" else "",
                    ),
                    "request_schema_ref": schema_refs.get("request_schema_ref", ""),
                    "response_schema_ref": schema_refs.get("response_schema_ref", ""),
                    "source": inventory.get("source_url") or SOURCE,
                    "doc_url": doc_url(method, inventory_by_method),
                    "markdown_ref": (inventory_by_method.get(method) or {}).get("markdown_ref", ""),
                    "auth": ["IAM token", "Organization ID", f"x-dl-api-version: {api_version}"],
                }
            )
    methods.sort(key=lambda item: item["method"])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source": inventory.get("source_url") or SOURCE,
        "openapi_version": spec.get("openapi"),
        "required_api_header_version": api_version,
        "operation_count": len(methods),
        "tag_counts": dict(Counter(item["tag"] for item in methods)),
        "support_status_counts": dict(Counter(item["support_status"] for item in methods)),
        "methods": methods,
    }


def collect_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            refs.add(ref.rsplit("/", 1)[-1])
        for item in value.values():
            refs.update(collect_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(collect_refs(item))
    return refs


def build_operation_schema_index(spec: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    synthetic_schemas: dict[str, Any] = {}
    index: dict[str, dict[str, Any]] = {}
    for path, operations in sorted(spec.get("paths", {}).items()):
        if not path.startswith("/rpc/") or not isinstance(operations, dict):
            continue
        method = method_name_from_path(path)
        operation = operations.get("post") or next(iter(operations.values()))
        request_schema = json_media_schema(operation, "Request")
        response_schema = json_media_schema(operation, "Response")
        request_ref = schema_ref_name(request_schema, method=method, direction="Request")
        response_ref = schema_ref_name(response_schema, method=method, direction="Response")
        if request_schema and "$ref" not in request_schema and request_ref:
            synthetic_schemas[request_ref] = request_schema
        if response_schema and "$ref" not in response_schema and response_ref:
            synthetic_schemas[response_ref] = response_schema
        index[method] = {
            "request_schema_ref": request_ref,
            "response_schema_ref": response_ref,
            "request_schema_kind": "inline" if request_ref in synthetic_schemas else ("ref" if request_ref else "none"),
            "response_schema_kind": "inline" if response_ref in synthetic_schemas else ("ref" if response_ref else "none"),
        }
    return index, synthetic_schemas


def validate_operation_inventory(*, spec: dict[str, Any], inventory: dict[str, Any], openapi_sha256: str) -> None:
    spec_paths: set[str] = set()
    spec_methods: set[str] = set()
    spec_operation_count = 0
    for path, operations in sorted(spec.get("paths", {}).items()):
        if not path.startswith("/rpc/") or not isinstance(operations, dict):
            continue
        http_methods = [
            name
            for name in operations
            if str(name).lower() in {"get", "post", "put", "patch", "delete"}
        ]
        if not http_methods:
            continue
        spec_paths.add(path)
        spec_methods.add(method_name_from_path(path))
        spec_operation_count += len(http_methods)

    inventory_operations = [item for item in inventory.get("operations", []) if isinstance(item, dict)]
    inventory_paths = {str(item.get("path") or "") for item in inventory_operations if item.get("path")}
    inventory_methods = {
        str(item.get("operation_name") or item.get("method") or "")
        for item in inventory_operations
        if item.get("operation_name") or item.get("method")
    }
    stats = inventory.get("stats") if isinstance(inventory.get("stats"), dict) else {}
    issues: list[str] = []
    if spec_operation_count != EXPECTED_OPERATION_COUNT:
        issues.append(f"OpenAPI operations={spec_operation_count} expected {EXPECTED_OPERATION_COUNT}")
    if len(spec_paths) != EXPECTED_PATH_COUNT:
        issues.append(f"OpenAPI paths={len(spec_paths)} expected {EXPECTED_PATH_COUNT}")
    if len(inventory_operations) != EXPECTED_OPERATION_COUNT:
        issues.append(f"inventory operations={len(inventory_operations)} expected {EXPECTED_OPERATION_COUNT}")
    if len(inventory_paths) != EXPECTED_PATH_COUNT:
        issues.append(f"inventory paths={len(inventory_paths)} expected {EXPECTED_PATH_COUNT}")
    if stats.get("operations") != EXPECTED_OPERATION_COUNT:
        issues.append(f"inventory stats.operations={stats.get('operations')!r} expected {EXPECTED_OPERATION_COUNT}")
    if stats.get("paths") != EXPECTED_PATH_COUNT:
        issues.append(f"inventory stats.paths={stats.get('paths')!r} expected {EXPECTED_PATH_COUNT}")
    if inventory.get("openapi_sha256") and inventory.get("openapi_sha256") != openapi_sha256:
        issues.append("inventory openapi_sha256 does not match raw/api/openapi.json")
    if spec_paths != inventory_paths:
        missing = sorted(spec_paths - inventory_paths)[:5]
        extra = sorted(inventory_paths - spec_paths)[:5]
        issues.append(f"inventory paths differ from OpenAPI paths; missing={missing} extra={extra}")
    if spec_methods != inventory_methods:
        missing = sorted(spec_methods - inventory_methods)[:5]
        extra = sorted(inventory_methods - spec_methods)[:5]
        issues.append(f"inventory methods differ from OpenAPI paths; missing={missing} extra={extra}")
    if issues:
        raise ValueError("OpenAPI operation inventory blocker: " + "; ".join(issues))


def build_closed_schema_bundle(spec: dict[str, Any], synthetic_schemas: dict[str, Any]) -> dict[str, Any]:
    components = copy.deepcopy(((spec.get("components") or {}).get("schemas") or {}))
    schemas = {**components, **copy.deepcopy(synthetic_schemas)}
    needed = deque(sorted(synthetic_schemas))
    needed.extend(sorted(collect_refs({"schemas": synthetic_schemas})))
    closed_names: set[str] = set()
    while needed:
        name = needed.popleft()
        if name in closed_names or name not in schemas:
            continue
        closed_names.add(name)
        for ref in sorted(collect_refs(schemas[name])):
            if ref not in closed_names:
                needed.append(ref)
    for name in sorted(components):
        if name in closed_names:
            continue
    # Keep the bundle complete for deterministic offline validation and to avoid
    # losing discriminator branches that are not reachable from current plans yet.
    closed_names.update(schemas)
    return {name: schemas[name] for name in sorted(closed_names)}


def missing_refs(schema_bundle: dict[str, Any]) -> list[str]:
    refs = set()
    for schema in schema_bundle.values():
        refs.update(collect_refs(schema))
    return sorted(ref for ref in refs if ref not in schema_bundle)


def extract_cut_list(text: str, title_fragment: str) -> list[str]:
    start = text.find(title_fragment)
    if start < 0:
        return []
    end = text.find("{% endcut %}", start)
    section = text[start:end if end >= 0 else len(text)]
    return sorted(set(re.findall(r"\* `([^`]+)`", section)))


def build_editor_allowlist(corpus_root: Path) -> dict[str, Any]:
    methods_path = corpus_root / "raw" / "md" / "datalens" / "charts" / "editor" / "methods.md"
    advanced_path = corpus_root / "raw" / "md" / "datalens" / "charts" / "editor" / "widgets" / "advanced.md"
    methods_text = methods_path.read_text(encoding="utf-8")
    methods = sorted(set(re.findall(r"\[Editor\.([A-Za-z_][A-Za-z0-9_]*)\(", methods_text)))
    tags = extract_cut_list(methods_text, "Поддерживаемые HTML-теги")
    attributes = extract_cut_list(methods_text, "Поддерживаемые атрибуты тегов")
    return {
        "schema_version": "2026-06-25.editor_runtime_allowlist.v1",
        "source_refs": [
            "raw/md/datalens/charts/editor/methods.md",
            "raw/md/datalens/charts/editor/widgets/advanced.md",
        ],
        "methods": methods,
        "html_tags": tags,
        "html_attributes": attributes,
        "advanced_widget_doc_sha256": sha256_bytes(advanced_path.read_bytes()) if advanced_path.is_file() else "",
    }


def build_openapi_lock(
    *,
    corpus_root: Path,
    spec: dict[str, Any],
    inventory: dict[str, Any],
    content_hashes: dict[str, Any],
    openapi_sha256: str,
    schema_bundle: dict[str, Any],
    catalog: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "2026-06-25.openapi_lock.v1",
        "generated_at": generated_at,
        "source_path_category": "external_corpus",
        "corpus_root_hint": "<DATALENS_DOCS_CORPUS_ROOT>",
        "openapi_path": "raw/api/openapi.json",
        "source_url": inventory.get("source_url") or SOURCE,
        "openapi_version": spec.get("openapi"),
        "openapi_sha256": openapi_sha256,
        "inventory_openapi_sha256": inventory.get("openapi_sha256"),
        "content_hashes": {
            key: content_hashes.get(key)
            for key in (
                "api_content_hash",
                "pages_content_hash",
                "assets_content_hash",
                "manifest_stable_hash",
            )
        },
        "operation_count": catalog["operation_count"],
        "inventory_operation_count": len(inventory.get("operations", [])),
        "path_count": len({item["path"] for item in catalog["methods"]}),
        "inventory_path_count": len(
            {
                str(item.get("path") or "")
                for item in inventory.get("operations", [])
                if isinstance(item, dict) and item.get("path")
            }
        ),
        "component_schema_count": len(((spec.get("components") or {}).get("schemas") or {})),
        "closed_schema_count": len(schema_bundle),
        "closed_schema_sha256": sha256_json(schema_bundle),
        "required_api_header_version": required_api_header_version(spec),
    }


def build_docs() -> dict[Path, str]:
    api_contract = """# Контракт DataLens API

Официальный источник:
[DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/).
Сведения о компиляции схем: [`docs/sources.md`](../sources.md).

## Транспорт

- Методы вызываются через `POST https://api.datalens.tech/rpc/<method>`.
- Запрос содержит `Authorization: Bearer <IAM_TOKEN>`, `x-dl-org-id`,
  `x-dl-api-version`, `content-type: application/json` и
  `accept: application/json`.
- `DATALENS_API_VERSION=auto` выбирает версию, закреплённую в скомпилированном контракте.
- Диагностика очищается от токенов, заголовков авторизации, паролей и закрытых ключей.

## Статус метода

Каталог разделяет методы чтения, методы записи через Safe Apply и справочные
операции. Текущий статус можно получить через `dl_list_api_methods`, точную
схему — через `dl_get_api_method_schema`.

## Запись

Перед write выполняются target lock, актуальное чтение, сохранение ревизии и
неизвестных полей, валидация payload и проверка write/save/publish. Save
сопровождается saved readback. Publish строится из saved readback и
сопровождается published readback.

Команда пользователя на create/fix/update/enhance/redesign запускает этот цикл
без отдельного подтверждения save/publish. Произвольное удаление целого
объекта недоступно; manifest action `retire_legacy_objects` использует
отдельный `confirm_delete` flow. Перемещение, изменение прав и credential
mutations не поддерживаются.

Повтор записи под другой API-версией не выполняется.
"""

    catalog_doc = """# Каталог методов DataLens API

Полный актуальный каталог поставляется в `config/datalens_api_methods.json` и
доступен через `dl_list_api_methods`. Для одного метода используйте
`dl_get_api_method_schema`.

## Основные методы

| Объект | Методы чтения | Методы создания/обновления |
| --- | --- | --- |
| Workbook | `getWorkbooksList`, `getWorkbookEntries` | Обрабатываются проектным workflow при наличии manifest |
| Dashboard | `getDashboard` | `createDashboard`, `updateDashboard` |
| Wizard chart | `getWizardChart` | `createWizardChart`, `updateWizardChart` |
| Editor chart | `getEditorChart` | `createEditorChart`, `updateEditorChart` |
| QL chart | `getQLChart` | `createQLChart`, `updateQLChart` по прямому QL-запросу |
| Dataset | `getDataset` | `validateDataset`, `createDataset`, `updateDataset` |
| Connection | `getConnection` | `createConnection`, `updateConnection` |
| Relations | `getEntriesRelations` | — |

## Статусы

- `read_only` — метод используется для чтения или проверки;
- `guarded_write` — метод выполняется через target lock, fresh read, Safe Apply и readback;
- `reference_only` — контракт доступен для справки;
- `unsupported` — операция не входит в публичный workflow сервера.

Только объявленное в project manifest действие `retire_legacy_objects` может
удалять целые объекты и требует отдельного `confirm_delete`. Произвольное
whole-object deletion, перемещение и изменение permissions не поддерживаются.

Официальные схемы и описания: [DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/).
"""

    mapping_doc = """# Связь инструментов с DataLens API

| Инструменты MCP | Официальные методы | Использование |
| --- | --- | --- |
| `dl_list_workbooks`, `dl_get_workbook_entries` | `getWorkbooksList`, `getWorkbookEntries` | Поиск воркбуков и объектов |
| `dl_get_entries_relations` | `getEntriesRelations` | Связи объектов |
| `dl_read_object` | `getDashboard`, `get*Chart`, `getDataset`, `getConnection` | Унифицированное чтение |
| `dl_plan_object_create` | create-метод выбранного object type | План создания |
| `dl_plan_object_update` | update-метод выбранного object type | План обновления |
| `dl_plan_guarded_dataset_update` | `getDataset`, `validateDataset`, `updateDataset` | Проверка и обновление датасета |
| `dl_create_safe_apply_plan`, `dl_execute_safe_apply` | Методы записи из проверенного плана | Save-first применение |
| `dl_create_publish_from_saved_plan` | Update-метод в publish mode | Публикация из saved readback |
| `dl_list_api_methods`, `dl_get_api_method_schema` | OpenAPI catalog | Справка по контрактам |

Точный метод и request schema возвращаются plan-инструментом до выполнения
записи. Официальный источник:
[DataLens API Reference](https://yandex.cloud/ru/docs/datalens/openapi-ref/).
"""

    examples_doc = [
        "# DataLens API Examples",
        "",
        "Source trace: `examples/datalens_api/rpc_examples.json` and `config/datalens_api_methods.json`.",
        "",
        "Examples use placeholders only. They are payload-shape examples, not live requests.",
        "",
        "## Dataset Update",
        "",
        "```json",
        json.dumps(
            {"method": "updateDataset", "payload": {"datasetId": "<DATASET_ID>", "data": {"dataset": {}}}},
            indent=2,
        ),
        "```",
        "",
        "## Dataset Validate",
        "",
        "```json",
        json.dumps(
            {
                "method": "validateDataset",
                "payload": {"datasetId": "<DATASET_ID>", "workbookId": "<WORKBOOK_ID>", "data": {"dataset": {}}},
            },
            indent=2,
        ),
        "```",
        "",
    ]

    return {
        DOCS_DIR / "api_contract.md": api_contract,
        DOCS_DIR / "api_methods_catalog.md": catalog_doc,
        DOCS_DIR / "api_tool_mapping.md": mapping_doc,
        DOCS_DIR / "api_examples.md": "\n".join(examples_doc) + "\n",
    }


def build_examples(api_version: str) -> dict[str, Any]:
    return {
        "auth_headers": {
            "Authorization": "Bearer <IAM_TOKEN>",
            "x-dl-org-id": "<ORG_ID>",
            "x-dl-api-version": api_version,
            "content-type": "application/json",
            "accept": "application/json",
        },
        "readonly": {
            "getDashboard": {"dashboardId": "<DASHBOARD_ID>", "branch": "saved"},
            "getEntriesRelations": {"entryIds": ["<ENTRY_ID>"]},
            "getWorkbookEntries": {"workbookId": "<WORKBOOK_ID>"},
        },
        "plan_only": {
            "updateDataset": {"datasetId": "<DATASET_ID>", "data": {"dataset": {}}},
            "validateDataset": {"datasetId": "<DATASET_ID>", "workbookId": "<WORKBOOK_ID>", "data": {"dataset": {}}},
            "updateConnection": {"connectionId": "<CONNECTION_ID>", "data": {"type": "clickhouse"}},
            "updateDashboard_save": {"mode": "save", "entry": {"entryId": "<DASHBOARD_ID>", "revId": "<REV_ID>"}},
        },
    }


def build_source_trace(corpus_root: Path, lock: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "2026-06-25.datalens_source_trace.v1",
        "source_class": "official_documentation",
        "source_path_category": "external_compiler_input",
        "corpus_root_hint": "<DATALENS_DOCS_CORPUS_ROOT>",
        "source_repository": "https://github.com/yandex-cloud/docs",
        "source_repository_paths": [
            "en/datalens/openapi-ref/",
            "md-docs/datalens/openapi-ref/",
        ],
        "generation_input": SOURCE,
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "modified": True,
        "transformations": [
            "selected interoperability contracts",
            "normalized schema structure",
            "removed upstream prose annotations",
            "compiled deterministic validation bundles",
        ],
        "inputs": [
            "raw/api/openapi.json",
            "api_inventory.json",
            "reports/content_hashes.json",
            "reports/validation.md",
            "raw/md/datalens/charts/editor/methods.md",
            "raw/md/datalens/charts/editor/widgets/advanced.md",
        ],
        "openapi_sha256": lock["openapi_sha256"],
        "generated_artifacts": [
            "schemas/datalens-api/openapi.lock.json",
            "config/datalens_api_methods.json",
            "schemas/datalens-api/operation-schema-index.json",
            "schemas/datalens-api/selected-openapi-schema-refs.json",
            "schemas/datalens-api/closed-schema-bundle.json",
            "schemas/datalens-api/support-policy-overlay.json",
            "schemas/datalens-api/editor-runtime-allowlist.json",
        ],
    }


def render_outputs(corpus_root: Path) -> dict[Path, str]:
    corpus_root = normalize_corpus_root(corpus_root)
    openapi_path, inventory_path, content_hashes_path, validation_path = corpus_input_paths(corpus_root)
    missing_inputs = [path for path in (openapi_path, inventory_path, content_hashes_path, validation_path) if not path.is_file()]
    if missing_inputs:
        raise FileNotFoundError("missing corpus inputs: " + ", ".join(str(path) for path in missing_inputs))

    openapi_bytes = openapi_path.read_bytes()
    spec = json.loads(openapi_bytes.decode("utf-8"))
    inventory = read_json(inventory_path)
    content_hashes = read_json(content_hashes_path)
    generated_at = str(inventory.get("fetched_at") or content_hashes.get("generated_at") or "")
    openapi_sha = sha256_bytes(openapi_bytes)
    validate_operation_inventory(spec=spec, inventory=inventory, openapi_sha256=openapi_sha)
    operation_index, synthetic = build_operation_schema_index(spec)
    schema_bundle = strip_upstream_schema_annotations(build_closed_schema_bundle(spec, synthetic))
    missing = missing_refs(schema_bundle)
    catalog = build_catalog(spec, inventory, operation_index, generated_at=generated_at)
    lock = build_openapi_lock(
        corpus_root=corpus_root,
        spec=spec,
        inventory=inventory,
        content_hashes=content_hashes,
        openapi_sha256=openapi_sha,
        schema_bundle=schema_bundle,
        catalog=catalog,
        generated_at=generated_at,
    )
    overlay = build_support_overlay()
    editor_allowlist = build_editor_allowlist(corpus_root)
    source_trace = build_source_trace(corpus_root, lock)
    tool_support = {
        "schema_version": "2026-06-25.api_tool_support_matrix.v2",
        "source": SOURCE,
        "support_policy_overlay": "schemas/datalens-api/support-policy-overlay.json",
        "methods": [
            {
                "method": method["method"],
                "mode": method["mode"],
                "support_status": method["support_status"],
                "mcp_route": method["mcp_route"],
                "mcp_tool": method["mcp_tool"],
                "support_reason": method["support_reason"],
            }
            for method in catalog["methods"]
        ],
    }
    json_outputs: dict[Path, Any] = {
        SCHEMA_DIR / "openapi.lock.json": lock,
        CONFIG_PATH: catalog,
        SCHEMA_DIR / "operation-schema-index.json": operation_index,
        SCHEMA_DIR / "selected-openapi-schema-refs.json": schema_bundle,
        SCHEMA_DIR / "closed-schema-bundle.json": {
            "schema_version": "2026-06-25.closed_openapi_schema_bundle.v1",
            "openapi_lock_sha256": openapi_sha,
            "schema_count": len(schema_bundle),
            "missing_refs": missing,
            "schemas": schema_bundle,
        },
        SCHEMA_DIR / "method-schema-refs.json": {
            method: {
                **refs,
                "support_status": next(item["support_status"] for item in catalog["methods"] if item["method"] == method),
            }
            for method, refs in sorted(operation_index.items())
        },
        SCHEMA_DIR / "tool-support-matrix.json": tool_support,
        SCHEMA_DIR / "support-policy-overlay.json": overlay,
        SCHEMA_DIR / "editor-runtime-allowlist.json": editor_allowlist,
        SCHEMA_DIR / "source-trace.json": source_trace,
        EXAMPLES_DIR / "rpc_examples.json": build_examples(lock["required_api_header_version"]),
    }
    outputs = {
        path: json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        for path, value in json_outputs.items()
    }
    outputs.update(build_docs())
    packaged_sources = {
        CONFIG_PATH: PACKAGE_CONFIG_DIR / CONFIG_PATH.name,
        **{
            source_path: PACKAGE_SCHEMA_DIR / source_path.name
            for source_path in json_outputs
            if source_path.parent == SCHEMA_DIR
        },
    }
    for source_path, packaged_path in packaged_sources.items():
        outputs[packaged_path] = outputs[source_path]
    return outputs


def resolve_corpus_root(cli_value: str) -> Path:
    # An explicitly supplied corpus is authoritative, including for drift and
    # malformed-corpus diagnostics. Never silently replace it with the default
    # fresh mirror when it is incomplete.
    if cli_value:
        return normalize_corpus_root(cli_value)
    return resolve_shared_corpus_root()


def write_outputs(outputs: dict[Path, str]) -> None:
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def check_outputs(outputs: dict[Path, str]) -> list[str]:
    drift: list[str] = []
    for path, expected in sorted(outputs.items(), key=lambda item: str(item[0])):
        if not path.is_file():
            drift.append(f"missing {path.relative_to(ROOT)}")
            continue
        current = path.read_text(encoding="utf-8")
        if current != expected:
            drift.append(f"changed {path.relative_to(ROOT)}")
    return drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile DataLens API contracts from the external docs corpus.")
    parser.add_argument("--corpus-root", default="", help="Path to datalens-docs-corpus.")
    parser.add_argument("--check", action="store_true", help="Fail if generated artifacts differ from committed outputs.")
    args = parser.parse_args(argv)

    try:
        corpus_root = resolve_corpus_root(args.corpus_root)
        outputs = render_outputs(corpus_root)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.check:
        drift = check_outputs(outputs)
        if drift:
            print(json.dumps({"ok": False, "drift": drift}, indent=2, sort_keys=True))
            return 1
        print(json.dumps({"ok": True, "checked": len(outputs)}, sort_keys=True))
        return 0

    write_outputs(outputs)
    catalog = json.loads(outputs[CONFIG_PATH])
    lock = json.loads(outputs[SCHEMA_DIR / "openapi.lock.json"])
    print(
        json.dumps(
            {
                "operation_count": catalog["operation_count"],
                "path_count": lock["path_count"],
                "required_api_header_version": lock["required_api_header_version"],
                "openapi_sha256": lock["openapi_sha256"],
                "outputs": len(outputs),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
