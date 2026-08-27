from __future__ import annotations

import unittest

from datalens_dev_mcp.pipeline.retry_controller import retry_decision
from tests.regression.policy_matrix._corpus import load_cases


REQUIRED_FAILURES = {
    "AUTH_401_TOKEN_INVALID_OR_EXPIRED", "AUTH_403_PERMISSION_DENIED", "REVISION_CONFLICT",
    "RATE_LIMIT_429", "NETWORK_TIMEOUT", "TRANSIENT_5XX", "TOOL_OR_CAPABILITY_UNAVAILABLE",
    "AMBIGUOUS_WRITE", "NO_PROGRESS", "STYLE_BINDING_STALE", "PATCH_ANCHOR_STALE",
}


class FailureRecoveryRegressionTests(unittest.TestCase):
    def test_failure_and_resume_families_are_covered(self):
        families = {case["expected_failure_family"] for case in load_cases() if case["expected_failure_family"]}
        self.assertEqual(REQUIRED_FAILURES - families, set())

    def test_401_and_403_refresh_rules_are_locked(self):
        probe_success = retry_decision(
            "AUTH_401_TOKEN_INVALID_OR_EXPIRED", readonly=True, auth_probe="success"
        )
        probe_401 = retry_decision(
            "AUTH_401_TOKEN_INVALID_OR_EXPIRED", readonly=True, auth_probe="auth_401"
        )
        forbidden = retry_decision("AUTH_403_PERMISSION_DENIED", readonly=True)
        self.assertFalse(probe_success.refresh_token)
        self.assertTrue(probe_401.refresh_token)
        self.assertTrue(probe_401.retry)
        self.assertFalse(forbidden.refresh_token)

    def test_ambiguous_write_is_reconciled_without_replay(self):
        decision = retry_decision("AMBIGUOUS_WRITE", readonly=False)
        self.assertTrue(decision.reconcile)
        self.assertFalse(decision.retry)
        cases = [case for case in load_cases() if case["scenario"] == "ambiguous_write"]
        self.assertTrue(all(case["expected_recovery"] == "readback_reconciliation_no_replay" for case in cases))
