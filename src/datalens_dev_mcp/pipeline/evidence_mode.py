from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


EvidenceMode = Literal["api_only", "targeted_data_evidence", "source_matrix", "full_dashboard_audit"]


@dataclass(frozen=True)
class EvidenceModeDecision:
    evidence_mode: EvidenceMode
    why_this_mode: str
    metadata_fetch_required: bool
    metadata_fetch_artifacts: list[str] = field(default_factory=list)
    gates: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    schema_version: str = "datalens.evidence-mode-decision.v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SOURCE_MATRIX_KEYWORDS = (
    "availability",
    "no table",
    "no data",
    "source tables",
    "data health",
    "environment",
    "env matrix",
    "source matrix",
    "selector availability",
)
TARGETED_DATA_KEYWORDS = (
    "source error",
    "schema mismatch",
    "unknown table",
    "unknown identifier",
    "502",
    "504",
    "timeout",
    "high fanout",
    "high-fanout",
    "metric",
    "field",
    "sql",
)
FULL_AUDIT_KEYWORDS = (
    "all chart",
    "all-chart",
    "all environment",
    "all-environment",
    "every tab",
    "every chart",
    "full dashboard audit",
    "full audit",
)


def choose_evidence_mode(
    request_text: str = "",
    *,
    changed_surfaces: list[str] | None = None,
    source_keys: list[str] | None = None,
    metadata_fetch_artifacts: list[str] | None = None,
    explicit_full_audit: bool = False,
) -> EvidenceModeDecision:
    text = " ".join([request_text, " ".join(changed_surfaces or []), " ".join(source_keys or [])]).lower()
    artifacts = [str(path) for path in metadata_fetch_artifacts or [] if str(path)]
    if explicit_full_audit or any(token in text for token in FULL_AUDIT_KEYWORDS):
        return EvidenceModeDecision(
            evidence_mode="full_dashboard_audit",
            why_this_mode="request asks for every tab/chart/environment or an explicit full audit",
            metadata_fetch_required=True,
            metadata_fetch_artifacts=artifacts,
            gates=["active_graph_hydration", "all_chart_validation", "source_budget_validation"],
        )
    if any(token in text for token in SOURCE_MATRIX_KEYWORDS):
        return EvidenceModeDecision(
            evidence_mode="source_matrix",
            why_this_mode="request involves source availability, NO TABLE/NO DATA, environment selectors, or Data Health consistency",
            metadata_fetch_required=True,
            metadata_fetch_artifacts=artifacts,
            gates=["source_availability_matrix", "selector_state_guard", "readback"],
        )
    if source_keys or any(token in text for token in TARGETED_DATA_KEYWORDS):
        return EvidenceModeDecision(
            evidence_mode="targeted_data_evidence",
            why_this_mode="request touches a specific source, SQL/source error, field, metric, or performance issue",
            metadata_fetch_required=True,
            metadata_fetch_artifacts=artifacts,
            gates=["targeted_source_evidence", "source_budget_validation", "readback"],
        )
    return EvidenceModeDecision(
        evidence_mode="api_only",
        why_this_mode="DataLens API readback and payload validation are sufficient for this scoped change",
        metadata_fetch_required=False,
        metadata_fetch_artifacts=artifacts,
        gates=["payload_validation", "safe_apply", "saved_readback"],
    )

