from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from datalens_dev_mcp.api.methods import get_method_schema


REGISTRY_SCHEMA_VERSION = "2026-06-25.object_read_registry.v1"


@dataclass(frozen=True)
class ObjectReadContract:
    object_type: str
    aliases: tuple[str, ...]
    scope_aliases: tuple[str, ...]
    read_method: str | None
    identity_field: str
    branch_semantics: str
    revision_fields: tuple[str, ...]
    compact_summary_schema: str
    structure_schema: str
    artifact_schema: str
    dependency_extractors: tuple[str, ...]
    redaction_policy: str
    error_categories: tuple[str, ...]
    evidence_status: str
    evidence_sources: tuple[str, ...]
    unsupported_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema_version"] = REGISTRY_SCHEMA_VERSION
        if self.read_method:
            payload["method_schema"] = get_method_schema(self.read_method)
        return payload


OBJECT_READ_CONTRACTS: dict[str, ObjectReadContract] = {
    "dashboard": ObjectReadContract(
        object_type="dashboard",
        aliases=("dash", "dashboard_node"),
        scope_aliases=("dash", "dashboard"),
        read_method="getDashboard",
        identity_field="dashboardId",
        branch_semantics="saved_or_published",
        revision_fields=("revId", "savedId", "entry.revId", "entry.savedId"),
        compact_summary_schema="dashboard.identity.tabs.counts.selector_impact.hashes.v1",
        structure_schema="dashboard.tabs.items.links.parameters.v1",
        artifact_schema="sanitized_rpc_envelope.dashboard.v1",
        dependency_extractors=("dashboard_items", "selector_links", "entry_relations"),
        redaction_policy="sanitize secret-like keys and never inline full data by default",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=(
            "config/datalens_api_methods.json#getDashboard",
            "demo workbook dashboard snapshots",
        ),
    ),
    "editor_chart": ObjectReadContract(
        object_type="editor_chart",
        aliases=("chart", "editor", "advanced_editor_chart", "advanced-chart_node", "advanced_chart_node"),
        scope_aliases=("advanced-chart_node", "editor_chart", "chart"),
        read_method="getEditorChart",
        identity_field="chartId",
        branch_semantics="saved_or_published",
        revision_fields=("revId", "savedId", "entry.revId", "entry.savedId"),
        compact_summary_schema="editor_chart.identity.sections.links.hashes.v1",
        structure_schema="editor_chart.tabs.sources.prepare.controls.config.v1",
        artifact_schema="sanitized_rpc_envelope.editor_chart.v1",
        dependency_extractors=("editor_sources", "dataset_ids", "connection_ids", "links"),
        redaction_policy="hash SQL/JS/HTML sections in summaries and spill full payloads to artifacts",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getEditorChart", "demo editor-chart objects"),
    ),
    "wizard_chart": ObjectReadContract(
        object_type="wizard_chart",
        aliases=(
            "wizard",
            "metric_wizard_node",
            "graph_wizard_node",
            "ymap_wizard_node",
            "table_wizard_node",
            "markup_wizard_node",
        ),
        scope_aliases=(
            "metric_wizard_node",
            "graph_wizard_node",
            "ymap_wizard_node",
            "table_wizard_node",
            "markup_wizard_node",
        ),
        read_method="getWizardChart",
        identity_field="chartId",
        branch_semantics="saved_or_published",
        revision_fields=("revId", "savedId", "entry.revId", "entry.savedId"),
        compact_summary_schema="wizard_chart.identity.visualization.fields.hashes.v1",
        structure_schema="wizard_chart.visualization.fields.datasets.params.v1",
        artifact_schema="sanitized_rpc_envelope.wizard_chart.v1",
        dependency_extractors=("wizard_dataset_ids", "wizard_connection_ids", "links"),
        redaction_policy="hash formula/query fragments in summaries and spill full payloads to artifacts",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getWizardChart", "demo wizard-chart objects"),
    ),
    "table_node": ObjectReadContract(
        object_type="table_node",
        aliases=("table", "editor_table", "widget table_node"),
        scope_aliases=("table_node", "widget table_node"),
        read_method="getEditorChart",
        identity_field="chartId",
        branch_semantics="saved_or_published",
        revision_fields=("revId", "savedId", "entry.revId", "entry.savedId"),
        compact_summary_schema="editor_table.identity.sections.table_contract.hashes.v1",
        structure_schema="table_node.input.output.sorting.formatting.groups.bars.totals.cross_filter.v1",
        artifact_schema="sanitized_rpc_envelope.table_node.v1",
        dependency_extractors=("editor_sources", "dataset_ids", "table_cross_filter_params"),
        redaction_policy="do not inline source code or full data rows by default",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getEditorChart", "demo table_node entries"),
    ),
    "d3_node": ObjectReadContract(
        object_type="d3_node",
        aliases=("d3", "gravity", "gravity_chart", "gravity_node", "d3_gravity_node", "widget d3_node"),
        scope_aliases=("d3_node", "widget d3_node"),
        read_method="getEditorChart",
        identity_field="chartId",
        branch_semantics="saved_or_published",
        revision_fields=("revId", "savedId", "entry.revId", "entry.savedId"),
        compact_summary_schema="d3_node.identity.runtime.sections.hashes.v1",
        structure_schema="d3_gravity.configuration.data_contract.runtime.v1",
        artifact_schema="sanitized_rpc_envelope.d3_node.v1",
        dependency_extractors=("editor_sources", "gravity_config", "dataset_ids"),
        redaction_policy="hash runtime code and data contracts in summaries",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getEditorChart", "demo d3/gravity node entries"),
    ),
    "control_node": ObjectReadContract(
        object_type="control_node",
        aliases=("control", "selector", "js_control", "editor_js_control", "widget control_node"),
        scope_aliases=("control_node", "widget control_node"),
        read_method="getEditorChart",
        identity_field="chartId",
        branch_semantics="saved_or_published",
        revision_fields=("revId", "savedId", "entry.revId", "entry.savedId"),
        compact_summary_schema="control_node.identity.params.dependencies.hashes.v1",
        structure_schema="control_node.static.dynamic.dependent_selector_contract.v1",
        artifact_schema="sanitized_rpc_envelope.control_node.v1",
        dependency_extractors=("control_params", "selector_dependencies", "dataset_ids"),
        redaction_policy="do not inline full JS or option payloads by default",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getEditorChart", "demo control_node entries"),
    ),
    "markdown_node": ObjectReadContract(
        object_type="markdown_node",
        aliases=("markdown", "md", "editor_markdown", "widget markdown_node"),
        scope_aliases=("markdown_node", "widget markdown_node"),
        read_method="getEditorChart",
        identity_field="chartId",
        branch_semantics="saved_or_published",
        revision_fields=("revId", "savedId", "entry.revId", "entry.savedId"),
        compact_summary_schema="markdown_node.identity.params.mermaid.cross_filter.hashes.v1",
        structure_schema="markdown_node.params.mermaid.cross_filter_values.v1",
        artifact_schema="sanitized_rpc_envelope.markdown_node.v1",
        dependency_extractors=("markdown_params", "mermaid_blocks", "cross_filter_values"),
        redaction_policy="hash markdown bodies in summaries and spill full content to artifacts",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getEditorChart", "demo markdown_node entries"),
    ),
    "dataset": ObjectReadContract(
        object_type="dataset",
        aliases=("dataset_node",),
        scope_aliases=("dataset",),
        read_method="getDataset",
        identity_field="datasetId",
        branch_semantics="unbranched_revisioned",
        revision_fields=("revId", "rev_id", "metadata.revId"),
        compact_summary_schema="dataset.identity.fields.sources.hashes.v1",
        structure_schema="dataset.fields.sources.avatars.connection_refs.v1",
        artifact_schema="sanitized_rpc_envelope.dataset.v1",
        dependency_extractors=("dataset_connection_ids", "field_formula_refs"),
        redaction_policy="redact connection secrets and hash SQL fragments",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getDataset", "demo dataset objects"),
    ),
    "connection": ObjectReadContract(
        object_type="connection",
        aliases=("connector", "conn"),
        scope_aliases=("connection", "connector"),
        read_method="getConnection",
        identity_field="connectionId",
        branch_semantics="unbranched_revisioned",
        revision_fields=("revId", "rev_id", "metadata.revId"),
        compact_summary_schema="connection.identity.type.options.hashes.v1",
        structure_schema="connection.type.params.safe_options.v1",
        artifact_schema="sanitized_rpc_envelope.connection.v1",
        dependency_extractors=("connection_type",),
        redaction_policy="redact secret-like keys recursively",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getConnection", "demo connection object"),
    ),
    "ql_chart": ObjectReadContract(
        object_type="ql_chart",
        aliases=("ql", "sql_chart", "ql-chart_node", "graph_ql_node"),
        scope_aliases=("ql_chart", "ql-chart_node", "graph_ql_node"),
        read_method="getQLChart",
        identity_field="chartId",
        branch_semantics="saved_or_published",
        revision_fields=("revId", "savedId", "entry.revId", "entry.savedId"),
        compact_summary_schema="ql_chart.identity.query.dataset_dependency.hashes.v1",
        structure_schema="ql_chart.query.dataset_dependency.behavior.v1",
        artifact_schema="sanitized_rpc_envelope.ql_chart.v1",
        dependency_extractors=("ql_dataset_ids", "query_fragments"),
        redaction_policy="hash query text in summaries and spill full payloads to artifacts",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getQLChart", "demo QL chart object"),
    ),
    "report": ObjectReadContract(
        object_type="report",
        aliases=("report_node", "datalens_report"),
        scope_aliases=("report",),
        read_method="getReport",
        identity_field="entryId",
        branch_semantics="revisioned_entry",
        revision_fields=("revId", "entry.revId"),
        compact_summary_schema="report.identity.pages.widgets.hashes.v1",
        structure_schema="report.pages.widgets.selectors.settings.v1",
        artifact_schema="sanitized_rpc_envelope.report.v1",
        dependency_extractors=("report_widgets", "report_selectors"),
        redaction_policy="hash page/widget bodies in summaries and spill full payloads to artifacts",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="live_read_verified",
        evidence_sources=("config/datalens_api_methods.json#getReport", "official reports OpenAPI"),
    ),
    "workbook": ObjectReadContract(
        object_type="workbook",
        aliases=("workbook_object",),
        scope_aliases=("workbook",),
        read_method="getWorkbook",
        identity_field="workbookId",
        branch_semantics="unbranched_revisioned",
        revision_fields=("updatedAt", "createdAt"),
        compact_summary_schema="workbook.identity.collections.permissions.hashes.v1",
        structure_schema="workbook.metadata.collection.refs.v1",
        artifact_schema="sanitized_rpc_envelope.workbook.v1",
        dependency_extractors=("workbook_entries", "collection_refs"),
        redaction_policy="redact permission subjects only when secret-like",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="official_indexed",
        evidence_sources=("config/datalens_api_methods.json#getWorkbook",),
    ),
    "collection": ObjectReadContract(
        object_type="collection",
        aliases=("location", "folder_location"),
        scope_aliases=("collection", "location"),
        read_method="getCollection",
        identity_field="collectionId",
        branch_semantics="unbranched_revisioned",
        revision_fields=("updatedAt", "createdAt"),
        compact_summary_schema="collection.identity.permissions.hashes.v1",
        structure_schema="collection.metadata.parent.refs.v1",
        artifact_schema="sanitized_rpc_envelope.collection.v1",
        dependency_extractors=("collection_parent",),
        redaction_policy="redact secret-like keys recursively",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="official_indexed",
        evidence_sources=("config/datalens_api_methods.json#getCollection",),
    ),
    "permission": ObjectReadContract(
        object_type="permission",
        aliases=("entry_permission", "permissions"),
        scope_aliases=("permission",),
        read_method="getPermissions",
        identity_field="entryId",
        branch_semantics="unbranched",
        revision_fields=(),
        compact_summary_schema="permission.identity.bindings.counts.v1",
        structure_schema="permission.bindings.subjects.roles.v1",
        artifact_schema="sanitized_rpc_envelope.permission.v1",
        dependency_extractors=("permission_subjects",),
        redaction_policy="redact secret-like keys recursively",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="official_indexed",
        evidence_sources=("config/datalens_api_methods.json#getPermissions",),
    ),
    "workbook_permission": ObjectReadContract(
        object_type="workbook_permission",
        aliases=("workbook_access_bindings",),
        scope_aliases=("workbook_permission",),
        read_method="listWorkbookAccessBindings",
        identity_field="workbookId",
        branch_semantics="paginated_unbranched",
        revision_fields=(),
        compact_summary_schema="workbook_permission.bindings.counts.v1",
        structure_schema="workbook_permission.bindings.subjects.roles.v1",
        artifact_schema="sanitized_rpc_envelope.workbook_permission.v1",
        dependency_extractors=("permission_subjects",),
        redaction_policy="redact secret-like keys recursively",
        error_categories=("missing_input", "auth_failure", "datalens_validation_error", "unavailable_api_method"),
        evidence_status="official_indexed",
        evidence_sources=("config/datalens_api_methods.json#listWorkbookAccessBindings",),
    ),
    "workbook_entry": ObjectReadContract(
        object_type="workbook_entry",
        aliases=("entry", "inventory_entry"),
        scope_aliases=("workbook_entry",),
        read_method=None,
        identity_field="entryId",
        branch_semantics="inventory_only",
        revision_fields=("revId", "savedId"),
        compact_summary_schema="workbook_entry.inventory_row.v1",
        structure_schema="workbook_entry.available_only_through_getWorkbookEntries.v1",
        artifact_schema="sanitized_workbook_inventory.v1",
        dependency_extractors=(),
        redaction_policy="redact secret-like keys recursively",
        error_categories=("unavailable_api_method", "missing_input"),
        evidence_status="documented_but_not_implemented",
        evidence_sources=("config/datalens_api_methods.json#getWorkbookEntries",),
        unsupported_reason="No single-entry read method is listed; use getWorkbookEntries inventory or the resolved concrete object type.",
    ),
    "folder": ObjectReadContract(
        object_type="folder",
        aliases=("folder_entry",),
        scope_aliases=("folder",),
        read_method=None,
        identity_field="entryId",
        branch_semantics="inventory_only",
        revision_fields=(),
        compact_summary_schema="folder.inventory_row.v1",
        structure_schema="folder.available_only_through_inventory_or_collection.v1",
        artifact_schema="sanitized_workbook_inventory.v1",
        dependency_extractors=(),
        redaction_policy="redact secret-like keys recursively",
        error_categories=("unavailable_api_method", "missing_input"),
        evidence_status="documented_but_not_implemented",
        evidence_sources=("config/datalens_api_methods.json#getWorkbookEntries", "config/datalens_api_methods.json#getCollection"),
        unsupported_reason="Folder workbook entries have no validated direct read method; collection reads are separate location objects.",
    ),
    "compute": ObjectReadContract(
        object_type="compute",
        aliases=("compute_entry",),
        scope_aliases=("compute",),
        read_method=None,
        identity_field="entryId",
        branch_semantics="inventory_only",
        revision_fields=("revId", "savedId"),
        compact_summary_schema="compute.inventory_row.v1",
        structure_schema="compute.available_only_through_workbook_inventory_and_relations.v1",
        artifact_schema="sanitized_workbook_inventory.v1",
        dependency_extractors=(),
        redaction_policy="preserve scope and identifiers; redact secret-like keys recursively",
        error_categories=("unavailable_api_method", "missing_input"),
        evidence_status="official_inventory_enum_only",
        evidence_sources=(
            "schemas/datalens-api/closed-schema-bundle.json#EntryScope",
            "config/datalens_api_methods.json#getWorkbookEntries",
            "config/datalens_api_methods.json#getEntriesRelations",
        ),
        unsupported_reason=(
            "Compute is an inventory/relationship scope with no validated direct read method; "
            "preserve it in workbook inventories and relation graphs without hydration."
        ),
    ),
    "dataset_field": ObjectReadContract(
        object_type="dataset_field",
        aliases=("field",),
        scope_aliases=("dataset_field",),
        read_method=None,
        identity_field="fieldGuid",
        branch_semantics="embedded_in_dataset",
        revision_fields=(),
        compact_summary_schema="dataset_field.embedded_in_dataset.v1",
        structure_schema="dataset.fields.items.v1",
        artifact_schema="sanitized_dataset_payload.v1",
        dependency_extractors=(),
        redaction_policy="read via dataset summary/artifact",
        error_categories=("unavailable_api_method", "missing_input"),
        evidence_status="blocked_by_explicit_policy",
        evidence_sources=("config/datalens_api_methods.json#getDataset",),
        unsupported_reason="Dataset fields are embedded inside getDataset; no standalone field read method is available.",
    ),
    "calculated_field": ObjectReadContract(
        object_type="calculated_field",
        aliases=("calc_field",),
        scope_aliases=("calculated_field",),
        read_method=None,
        identity_field="fieldGuid",
        branch_semantics="embedded_in_dataset",
        revision_fields=(),
        compact_summary_schema="calculated_field.embedded_in_dataset.v1",
        structure_schema="dataset.fields.formulas.v1",
        artifact_schema="sanitized_dataset_payload.v1",
        dependency_extractors=(),
        redaction_policy="read via dataset summary/artifact",
        error_categories=("unavailable_api_method", "missing_input"),
        evidence_status="blocked_by_explicit_policy",
        evidence_sources=("config/datalens_api_methods.json#getDataset",),
        unsupported_reason="Calculated fields are embedded inside getDataset; no standalone calculated-field read method is available.",
    ),
}


ALIASES: dict[str, str] = {}
for contract in OBJECT_READ_CONTRACTS.values():
    ALIASES[contract.object_type] = contract.object_type
    for alias in (*contract.aliases, *contract.scope_aliases):
        ALIASES[alias.strip().lower().replace("-", "_")] = contract.object_type


def normalize_object_type(object_type: str) -> str:
    normalized = str(object_type or "").strip().lower().replace("-", "_")
    return ALIASES.get(normalized, normalized)


def object_read_contract(object_type: str) -> ObjectReadContract | None:
    return OBJECT_READ_CONTRACTS.get(normalize_object_type(object_type))


def supported_object_type_names() -> list[str]:
    return sorted(OBJECT_READ_CONTRACTS)


def object_type_registry() -> dict[str, Any]:
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "object_types": {name: contract.to_dict() for name, contract in sorted(OBJECT_READ_CONTRACTS.items())},
        "aliases": dict(sorted(ALIASES.items())),
    }
