from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from datalens_dev_mcp.pipeline.failure_classifier import classify_failure
from datalens_dev_mcp.validators.redaction import sanitize_value


ARCHITECTURE_REVIEW_STATE = "FAILED_ARCHITECTURE_REVIEW_REQUIRED"


@dataclass
class InvestigationRecord:
    family: str
    exact_failure: str = ""
    boundary_evidence: list[str] = field(default_factory=list)
    active_hypothesis: str = ""
    discriminating_probe: str = ""
    corrective_attempts: int = 0
    verification: str = ""
    state: str = "INVESTIGATING"
    schema_id: str = "datalens_investigation_record"

    def record_attempt(
        self,
        *,
        hypothesis: str,
        probe: str,
        evidence: str = "",
        verification: str = "failed",
    ) -> InvestigationRecord:
        self.active_hypothesis = hypothesis
        self.discriminating_probe = probe
        if evidence and evidence not in self.boundary_evidence:
            self.boundary_evidence.append(evidence)
        self.verification = verification
        if verification not in {"passed", "success"}:
            self.corrective_attempts += 1
        if self.corrective_attempts >= 3:
            self.state = ARCHITECTURE_REVIEW_STATE
        return self

    @property
    def can_attempt_fix(self) -> bool:
        return self.corrective_attempts < 3 and self.state != ARCHITECTURE_REVIEW_STATE

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["boundary_evidence"] = value["boundary_evidence"][-10:]
        value["next_action"] = (
            "review route and architecture before another correction"
            if self.state == ARCHITECTURE_REVIEW_STATE
            else "run one minimal discriminating probe"
        )
        return sanitize_value(value)


def start_investigation(failure: BaseException | dict[str, Any] | str, *, operation: str = "") -> InvestigationRecord:
    classified = classify_failure(failure, operation=operation)
    return InvestigationRecord(family=classified.family, exact_failure=classified.evidence)
