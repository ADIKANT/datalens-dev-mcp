import pytest
from datalens_sdk import DataLensClientYC, Dataset, EntryLocation
from datalens_sdk.converter.wizard import WizardChartConverter

from datalens_dev_mcp.authoring.recipes import compile_recipe
from datalens_dev_mcp.wizard.authoring import wizard_builder
from test_l04_dataset_wizard import FIELDS


def bindings():
    return {"dataset_id": "synthetic-dataset", "object_name": "Synthetic comparison",
            "date": {"field_guid": "date-guid"}, "metric": {"field_guid": "revenue-guid"},
            "comparison": {"field_guid": "prior-guid", "method": "previous_period", "alignment": "calendar"}}


def test_time_comparison_compiles_two_explicit_series_without_inventing_formula(tmp_path):
    result = compile_recipe("time_comparison", bindings(), user_config_path=tmp_path / "absent.json")
    draft = result["draft"]
    prior = {**FIELDS[1], "guid": "prior-guid", "title": "Previous revenue"}
    with DataLensClientYC(auth=None) as client:
        builder = wizard_builder(client, Dataset(id="synthetic-dataset", result_schema=tuple(FIELDS + [prior])),
                                 draft["wizard"], name=draft["name"], location=EntryLocation.workbook("synthetic"))
        data = WizardChartConverter.from_domain_create(builder.to_spec()).to_payload()["data"]
    placeholders = {p["id"]: p for p in data["visualization"]["placeholders"]}
    assert [v["guid"] for v in placeholders["y"]["items"]] == ["revenue-guid", "prior-guid"]
    assert data["sort"][0]["guid"] == "date-guid"
    assert data["extraSettings"]["legendMode"] == "show"
    assert draft["visual_contract"]["comparison"]["alignment"] == "calendar"


def test_time_comparison_does_not_treat_period_label_as_field(tmp_path):
    values = bindings()
    del values["comparison"]["field_guid"]
    with pytest.raises(ValueError, match="comparison requires an explicit field_guid"):
        compile_recipe("time_comparison", values, user_config_path=tmp_path / "absent.json")
