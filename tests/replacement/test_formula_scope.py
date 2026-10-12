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


def test_formula_literals_comments_and_field_names_are_not_lod_operators():
    for formula in ("IF([kind] = 'FIXED', 1, 0)", "SUM([FIXED])", "'escaped \\' FIXED'",
                    "'it''s FIXED'", '"FIXED"', "SUM([amount]) /* FIXED */", "1 -- FIXED\n"):
        fields = [{"guid": "literal", "title": "Literal", "formula": formula}, FIELDS[1]]
        assert validate_visualization_fields(fields, ["literal", "ago"])["ok"], formula
