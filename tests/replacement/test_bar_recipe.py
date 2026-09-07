from datalens_sdk import DataLensClientYC, Dataset, EntryLocation
from datalens_sdk.converter.wizard import WizardChartConverter

from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.wizard.authoring import wizard_builder


def test_categorical_bar_uses_horizontal_roles_and_compiles_display_settings(tmp_path):
    draft = compile_recipe("categorical_bar", {
        "dataset_id": "synthetic-dataset",
        "category": {"field_guid": "category", "label": "Category"},
        "metric": {"field_guid": "amount", "label": "Synthetic amount"},
    }, user_config_path=tmp_path / "absent.json")["draft"]
    fields = (
        {"guid": "category", "title": "Category", "type": "DIMENSION", "data_type": "string", "calc_mode": "direct"},
        {"guid": "amount", "title": "Amount", "type": "MEASURE", "data_type": "float", "calc_mode": "direct", "aggregation": "sum"},
    )
    with DataLensClientYC(auth=None) as client:
        builder = wizard_builder(client, Dataset(id="synthetic-dataset", result_schema=fields), draft["wizard"],
                                 name=draft["name"], location=EntryLocation.workbook("synthetic"))
        data = WizardChartConverter.from_domain_create(builder.to_spec()).to_payload()["data"]
    placeholders = {p["id"]: p for p in data["visualization"]["placeholders"]}
    assert placeholders["x"]["items"][0]["guid"] == "amount"
    assert placeholders["y"]["items"][0]["guid"] == "category"
    assert data["labels"][0]["guid"] == "amount"
    assert data["extraSettings"]["legendMode"] == "hide"
