from datalens_dev_mcp.dataset.contracts import validate_dataset_fields, validate_visualization_fields


FIELDS = [
    {"guid": "lod", "title": "LOD", "formula": "SUM([amount] FIXED [region])"},
    {"guid": "ago", "title": "Prior", "formula": "AGO([amount], 'year')"},
    {"guid": "derived", "title": "Derived", "formula": "[LOD] + 1"},
]


def test_unused_time_field_does_not_invalidate_lod_chart_or_dataset():
    assert validate_dataset_fields(FIELDS)["ok"]
    assert validate_visualization_fields(FIELDS, ["lod"])["ok"]
    assert validate_visualization_fields(FIELDS, ["ago"])["ok"]


def test_used_transitive_lod_dependency_conflicts_with_time_series():
    result = validate_visualization_fields(FIELDS, ["derived", "ago"])
    assert not result["ok"]
    assert "lod" in result["field_guids"]
