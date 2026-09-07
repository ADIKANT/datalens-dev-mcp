from datalens_sdk import DataLensClientYC, Dataset, EntryLocation
from datalens_sdk.converter.wizard import WizardChartConverter

from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.wizard.authoring import wizard_builder


def test_pivot_recipe_compiles_dimension_subtotals_and_measure_role(tmp_path):
    draft = compile_recipe("cross_tab_totals", {
        "dataset_id": "synthetic", "object_name": "Synthetic cross-tab",
        "rows": [{"field_guid": "region"}], "columns": [{"field_guid": "category"}],
        "measures": [{"field_guid": "amount"}],
    }, user_config_path=tmp_path / "absent.json")["draft"]
    fields = tuple({"guid": g, "title": g, "calc_mode": "direct",
                    "type": "MEASURE" if g == "amount" else "DIMENSION",
                    "data_type": "float" if g == "amount" else "string"}
                   for g in ("region", "category", "amount"))
    with DataLensClientYC(auth=None) as client:
        builder = wizard_builder(client, Dataset(id="synthetic", result_schema=fields), draft["wizard"],
                                 name=draft["name"], location=EntryLocation.workbook("synthetic"))
        data = WizardChartConverter.from_domain_create(builder.to_spec()).to_payload()["data"]
    assert draft["wizard"]["roles"]["y"] == ["amount"]
    assert draft["wizard"]["subtotals"] == ["region", "category"]
    assert data["extraSettings"]["pagination"] == "on"
    items = [item for p in data["visualization"]["placeholders"] for item in p["items"]]
    by_guid = {item["guid"]: item for item in items}
    assert by_guid["region"]["subTotalsSettings"]["enabled"] is True
    assert by_guid["category"]["subTotalsSettings"]["enabled"] is True
