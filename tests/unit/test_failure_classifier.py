from __future__ import annotations

import unittest

from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.pipeline.failure_classifier import FAILURE_FAMILIES, classify_failure


class FailureClassifierTests(unittest.TestCase):
    def test_http_and_write_families_are_stable(self):
        cases = {
            401: "AUTH_401_TOKEN_INVALID_OR_EXPIRED",
            403: "AUTH_403_PERMISSION_DENIED",
            404: "NOT_FOUND_404",
            429: "RATE_LIMIT_429",
            503: "TRANSIENT_5XX",
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                result = classify_failure(DataLensApiError("failure", http_status=status), readonly=True)
                self.assertEqual(result.family, expected)
                self.assertIn(result.family, FAILURE_FAMILIES)
        self.assertEqual(classify_failure("lost response", write_ambiguous=True).family, "AMBIGUOUS_WRITE")

    def test_secret_values_are_not_retained(self):
        result = classify_failure(
            "Authorization: Bearer secret-token-value DATALENS_IAM_TOKEN=another-secret",
            operation="getDashboard",
        ).to_dict()
        rendered = str(result)
        self.assertNotIn("secret-token-value", rendered)
        self.assertNotIn("another-secret", rendered)

    def test_semantic_failure_messages_are_classified(self):
        self.assertEqual(classify_failure("patch anchor stale").family, "PATCH_ANCHOR_STALE")
        self.assertEqual(classify_failure("unexpected empty result").family, "DATA_EMPTY_UNEXPECTED")
        self.assertEqual(classify_failure("browser evidence missing").family, "BROWSER_REQUIRED_MISSING")
