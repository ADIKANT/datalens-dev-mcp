import pytest
from datalens_sdk import DataLensClientYC, Dataset, EntryLocation
from datalens_sdk.converter.wizard import WizardChartConverter
from test_l04_dataset_wizard import FIELDS

from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.wizard.authoring import wizard_builder


def test_native_table_recipe_produces_executable_typed_draft(tmp_path):
    result = compile_recipe(
        "native_detail_table",
        {
            "dataset_id": "synthetic-dataset",
            "object_name": "Synthetic details",
            "columns": [{"field_guid": "date-guid", "label": "Date"}, {"field_guid": "revenue-guid"}],
            "sort": [{"field_guid": "date-guid", "direction": "asc"}],
        },
        {"table": {"page_size": 25}},
        user_config_path=tmp_path / "absent.json",
    )
    draft = result["draft"]
    assert draft["name"] == "Synthetic details"
    assert draft["client_ref"]
    assert "snapshot" not in draft
    assert draft["wizard"]["table"]["page_size"] == 25
    assert draft["wizard"]["title_mode"] == "hide"
    with DataLensClientYC(auth=None) as client:
        builder = wizard_builder(
            client,
            Dataset(id="synthetic-dataset", result_schema=tuple(FIELDS)),
            draft["wizard"],
            name=draft["name"],
            location=EntryLocation.workbook("synthetic"),
        )
        payload = WizardChartConverter.from_domain_create(builder.to_spec()).to_payload()
    assert payload["data"]["datasetsIds"] == ["synthetic-dataset"]
    settings = payload["data"]["extraSettings"]
    assert settings["pagination"] == "on"
    assert settings["limit"] == 25
    assert settings["totals"] == "on"
    assert settings["titleMode"] == "hide"
    assert payload["data"]["sort"][0]["guid"] == "date-guid"


def test_native_table_recipe_rejects_unresolved_source(tmp_path):
    with pytest.raises(ValueError, match="dataset_id"):
        compile_recipe(
            "native_detail_table", {"columns": [{"field_guid": "date-guid"}]}, user_config_path=tmp_path / "absent.json"
        )
