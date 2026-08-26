from __future__ import annotations

import unittest

from datalens_dev_mcp.pipeline.condition_wait import wait_for_condition
from datalens_dev_mcp.pipeline.result_dedup import ResultLedger, classify_result, semantic_result_hash


class ResultDedupTests(unittest.TestCase):
    def test_result_classifications_and_active_context(self):
        ledger = ResultLedger()
        first = ledger.add("revision", {"revision": 1, "polled_at": "a"}, poll=True)
        second = ledger.add("revision", {"revision": 1, "polled_at": "b"}, poll=True)
        noop = ledger.add("plan", {"ok": True})
        noop2 = ledger.add("plan", {"ok": True})
        self.assertEqual(first["classification"], "material")
        self.assertEqual(second["classification"], "unchanged_poll")
        self.assertEqual(noop2["classification"], "no_op")
        self.assertEqual(len(ledger.records), 4)
        self.assertEqual([row["classification"] for row in ledger.active_context()], ["material", "material"])
        self.assertEqual(semantic_result_hash({"updated_at": "a", "x": 1}), semantic_result_hash({"updated_at": "b", "x": 1}))

    def test_empty_semantics_are_explicit(self):
        self.assertEqual(classify_result([], expected_empty=True), "empty_expected")
        self.assertEqual(classify_result([], expected_empty=False), "empty_useless")

    def test_condition_wait_suppresses_identical_polls(self):
        values = iter([{"revision": 1}, {"revision": 1}, {"revision": 2}])
        now = [0.0]
        result = wait_for_condition(
            lambda: next(values),
            lambda value: value["revision"] == 2,
            timeout_sec=10,
            clock=lambda: now[0],
            sleeper=lambda delay: now.__setitem__(0, now[0] + delay),
        )
        self.assertEqual(result["status"], "satisfied")
        self.assertEqual(result["suppressed_unchanged_polls"], 1)
        self.assertEqual(result["state_changes"], [{"revision": 1}, {"revision": 2}])
