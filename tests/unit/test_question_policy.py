from __future__ import annotations

import unittest


class QuestionPolicyTests(unittest.TestCase):
    def test_discoverable_missing_facts_trigger_reads_not_questions(self):
        from datalens_dev_mcp.pipeline.question_policy import resolve_question_policy

        decision = resolve_question_policy(
            required_discoverable_facts=["technology", "field_guids", "layout"],
            discovered_facts={"layout": {"widgets": ["synthetic_widget"]}},
        )

        self.assertIsNone(decision.question)
        self.assertEqual(decision.discovery_required, ("technology", "field_guids"))

    def test_each_allowed_business_ambiguity_produces_one_concrete_question(self):
        from datalens_dev_mcp.pipeline.question_policy import QUESTION_PRIORITY, resolve_question_policy

        for category in QUESTION_PRIORITY:
            with self.subTest(category=category):
                decision = resolve_question_policy(unresolved_facts={category: True})
                self.assertIsNotNone(decision.question)
                self.assertEqual(decision.question.category, category)
                self.assertTrue(decision.question.question.endswith(("?", ".")))
                self.assertTrue(decision.question.why_not_discoverable)
                self.assertEqual(decision.question.max_answers, 1)

    def test_priority_is_deterministic_and_never_emits_two_questions(self):
        from datalens_dev_mcp.pipeline.question_policy import resolve_question_policy

        decision = resolve_question_policy(
            unresolved_facts={
                "metric_semantics": True,
                "empty_data_semantics": True,
                "business_key": True,
            }
        )

        self.assertEqual(decision.question.category, "business_key")
        self.assertEqual(decision.to_dict()["question"]["max_answers"], 1)

    def test_unknown_ambiguity_is_ignored_not_asked(self):
        from datalens_dev_mcp.pipeline.question_policy import resolve_question_policy

        decision = resolve_question_policy(unresolved_facts={"historical_preference": "stale"})

        self.assertIsNone(decision.question)
        self.assertEqual(decision.ignored_ambiguities, ("historical_preference",))


if __name__ == "__main__":
    unittest.main()
