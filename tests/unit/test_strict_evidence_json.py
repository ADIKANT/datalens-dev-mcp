from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from datalens_dev_mcp.pipeline.artifacts import (
    EvidenceArtifactInvalidError,
    loads_strict_json,
    read_json,
)


def test_generated_evidence_duplicate_key_is_a_hard_failure() -> None:
    exact_invalid_artifact = """{
      "schema_id": "coverage_matrix",
      "screening": {
        "result_classes": {"BLOCKED": 274},
        "provider_reads": 57,
        "provider_reads": 3
      }
    }"""

    with pytest.raises(EvidenceArtifactInvalidError, match="EVIDENCE_ARTIFACT_INVALID.*provider_reads"):
        loads_strict_json(exact_invalid_artifact, source="coverage-matrix.json")


def test_nested_duplicate_key_is_rejected_when_read_from_disk() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "evidence.json"
        path.write_text('{"outer":{"receipt_hash":"a","receipt_hash":"b"}}', encoding="utf-8")

        with pytest.raises(EvidenceArtifactInvalidError, match="receipt_hash"):
            read_json(path, {})


def test_distinct_keys_remain_typed_and_unchanged() -> None:
    parsed = loads_strict_json('{"provider_reads":3,"provider_writes":0}')

    assert parsed == {"provider_reads": 3, "provider_writes": 0}
