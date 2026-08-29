from __future__ import annotations

from datalens_dev_mcp.pipeline.object_locator import (
    build_canonical_direct_url,
    normalize_object_locator,
)


def test_markdown_slugged_url_normalizes_to_typed_dataset_locator() -> None:
    locator = normalize_object_locator(
        "[dataset](https://datalens.ru/datasets/synthetic_dataset_123-slug?tab=source)",
        workbook_id="workbook_fixture",
    )

    assert locator == {
        "object_id": "synthetic_dataset_123",
        "object_type": "dataset",
        "workbook_id": "workbook_fixture",
        "canonical_direct_url": "https://datalens.ru/datasets/synthetic_dataset_123-slug",
        "url_source": "route_builder",
    }


def test_id_only_routes_cover_dashboard_editor_ql_and_workbook() -> None:
    assert build_canonical_direct_url("dashboard", "dashid123456") == "https://datalens.ru/dashid123456"
    assert build_canonical_direct_url("editor_chart", "editorid1234") == "https://datalens.ru/editor/editorid1234"
    assert build_canonical_direct_url("ql_chart", "qlchartid123") == "https://datalens.ru/ql/qlchartid123"
    assert build_canonical_direct_url("workbook", "workbook_fixture_123") == (
        "https://datalens.ru/workbooks/workbook_fixture_123"
    )


def test_provider_url_wins_and_is_normalized_without_query_or_fragment() -> None:
    locator = normalize_object_locator(
        "https://datalens.ru/wizard/chartid12345-slug?tab=main#fragment",
        object_type="wizard_chart",
        object_id="chartid12345",
        url_source="provider_readback",
    )

    assert locator["canonical_direct_url"] == "https://datalens.ru/wizard/chartid12345-slug"
    assert locator["url_source"] == "provider_readback"


def test_relative_direct_object_path_normalizes_without_workbook_search() -> None:
    locator = normalize_object_locator("/ql/qlchartid123-synthetic")

    assert locator["object_id"] == "qlchartid123"
    assert locator["object_type"] == "ql_chart"
    assert locator["canonical_direct_url"] == "https://datalens.ru/ql/qlchartid123-synthetic"
