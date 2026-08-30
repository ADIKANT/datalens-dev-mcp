from __future__ import annotations

import unittest


class UserRequestContractTests(unittest.TestCase):
    def test_markdown_datalens_target_links_preserve_exact_ids(self) -> None:
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        cases = (
            (
                "[https://datalens.ru/workbooks/u8pn8dlinqumf]"
                "(https://datalens.ru/workbooks/u8pn8dlinqumf)",
                "u8pn8dlinqumf",
                "",
            ),
            (
                "[dashboard](https://datalens.ru/7l21cz8lo954s-data-platform-health)",
                "",
                "7l21cz8lo954s",
            ),
        )
        for text, workbook_id, dashboard_id in cases:
            with self.subTest(text=text):
                request = normalize_user_request(text)
                self.assertEqual(request.target_workbook_id, workbook_id)
                self.assertEqual(request.target_dashboard_id, dashboard_id)
                self.assertNotIn("](", request.target_url)

    def test_multi_url_request_separates_target_reference_and_evidence(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        request = normalize_user_request(
            "Issue: https://example.test/issues/TEST-1\n"
            "Target dashboard: https://datalens.ru/?dashboardId=synthetic_target_123\n"
            "Reference style: https://datalens.ru/?dashboardId=synthetic_reference_456"
        )

        self.assertEqual(request.target_dashboard_id, "synthetic_target_123")
        self.assertEqual(request.reference_url, "https://datalens.ru/?dashboardId=synthetic_reference_456")
        self.assertEqual([item["role"] for item in request.url_inventory], ["evidence", "target", "reference"])

    def test_external_url_before_unlabelled_datalens_url_is_not_the_target(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        request = normalize_user_request(
            "See https://example.test/issues/T-1 and update "
            "https://datalens.ru/?dashboardId=synthetic_target_123"
        )

        self.assertEqual(request.target_dashboard_id, "synthetic_target_123")
        self.assertEqual(request.target_url, "https://datalens.ru/?dashboardId=synthetic_target_123")

    def test_labelled_ids_accept_backticks_but_not_slash_separated_object_nouns(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        request = normalize_user_request(
            "В workbook `synthetic_workbook_123` создать dashboard / chart для отчёта"
        )

        self.assertEqual(request.target_workbook_id, "synthetic_workbook_123")
        self.assertEqual(request.target_dashboard_id, "")
        self.assertEqual(request.target_chart_id, "")

    def test_browser_preference_is_first_class(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        forbidden = normalize_user_request("update chart:synthetic_chart_user; do not use the browser")
        required = normalize_user_request("update chart:synthetic_chart_user and verify in the browser")

        self.assertEqual(forbidden.browser_preference, "forbidden")
        self.assertEqual(required.browser_preference, "required")

    def test_explicit_corrections_are_retained_as_constraints(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        request = normalize_user_request(
            "update chart:synthetic_chart_user\n"
            "do not change layout\n"
            "preserve this JS format"
        )

        self.assertEqual(request.explicit_constraints, ["do not change layout", "preserve this JS format"])

    def test_partial_content_removal_is_update_not_object_delete(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        request = normalize_user_request("remove the legend from chart:synthetic_chart_user")

        self.assertEqual(request.task_intent, "update")
        self.assertEqual(request.destructive_actions, [])

    def test_update_intent_outranks_save_and_publish_delivery_verbs(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        request = normalize_user_request(
            "Update the existing controlled dashboard description, save and publish it."
        )

        self.assertEqual(request.task_intent, "update")

    def test_explicit_javascript_editor_outranks_generic_table_and_map_nouns(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        table = normalize_user_request("Create a JavaScript Editor table widget for the dashboard")
        map_context = normalize_user_request("Build the map comparison as an Advanced Editor JS chart")
        native = normalize_user_request("Use a native table, preferred over Advanced Editor HTML tables")
        forbidden = normalize_user_request("Keep Wizard charts; do not use Advanced Editor JS")
        no_ql = normalize_user_request("Use JavaScript Editor for every widget; Wizard and QL не использовать")
        json_context = normalize_user_request("parse the JSON map and update the table rows")
        chart_handler = normalize_user_request("JSON преобразуй в читаемый вид и на стороне чарта сделай обработчик")

        self.assertEqual(table.route_intent, "js")
        self.assertEqual(map_context.route_intent, "js")
        self.assertEqual(native.route_intent, "native_table")
        self.assertEqual(forbidden.route_intent, "wizard_native")
        self.assertEqual(no_ql.route_intent, "js")
        self.assertNotEqual(json_context.route_intent, "js")
        self.assertEqual(chart_handler.route_intent, "js")

    def test_completed_action_check_is_first_class_existing_effect_verification(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        published = normalize_user_request(
            "Я уже опубликовал dashboard: synthetic_dashboard_verify — проверь."
        )
        applied = normalize_user_request(
            "Посмотри, применились ли правки в dashboard: synthetic_dashboard_verify."
        )

        self.assertEqual(published.operation_kind, "verify_existing_effect")
        self.assertEqual(published.effect_kind, "published")
        self.assertEqual(published.task_intent, "review")
        self.assertEqual(published.destructive_actions, [])
        self.assertEqual(applied.operation_kind, "verify_existing_effect")
        self.assertEqual(applied.effect_kind, "changed")

    def test_adjacent_review_and_future_mutation_are_not_existing_effect_verification(self):
        from datalens_dev_mcp.pipeline.user_request import normalize_user_request

        review = normalize_user_request("Проверь текущий dashboard: synthetic_dashboard_review")
        mutation = normalize_user_request("Опубликуй dashboard: synthetic_dashboard_publish")

        self.assertEqual(review.operation_kind, "inspect")
        self.assertEqual(mutation.operation_kind, "mutate")


if __name__ == "__main__":
    unittest.main()
