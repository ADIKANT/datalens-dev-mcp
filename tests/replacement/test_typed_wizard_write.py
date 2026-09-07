from types import SimpleNamespace

import pytest
from datalens_sdk import DataLensClientYC, Dataset

from datalens_dev_mcp.api.sdk_adapter import SdkAdapter
from test_l04_dataset_wizard import FIELDS


def test_wizard_create_uses_official_typed_factory_and_live_field_lookup():
    dataset = Dataset(id="synthetic-dataset", result_schema=tuple(FIELDS))
    reads, specs = [], []
    with DataLensClientYC(auth=None) as official:
        def factory(**kwargs):
            builder = official.create.wizard_chart.flat_table(**kwargs)
            def build():
                specs.append(builder.to_spec())
                return {"id": "synthetic-chart", "revId": "synthetic-r1"}
            builder.build = build
            return builder

        def get_dataset(**kwargs):
            reads.append(kwargs)
            return dataset

        client = SimpleNamespace(
            get=SimpleNamespace(dataset=get_dataset),
            create=SimpleNamespace(wizard_chart=SimpleNamespace(flat_table=factory)),
        )
        draft = {"object_type": "wizard_chart", "name": "Synthetic table", "wizard": {
            "dataset_id": dataset.id, "visualization": "flat_table",
            "roles": {"columns": ["date-guid", "revenue-guid"]}}}
        result = SdkAdapter(client=client).create(draft, {"workbook_id": "synthetic-workbook"})
    assert result["object_id"] == "synthetic-chart"
    assert reads == [{"by_id": "synthetic-dataset"}]
    assert len(specs) == 1
    assert result["expected_readback"]["data"]["datasetsIds"] == ["synthetic-dataset"]


def test_wizard_role_cannot_invoke_build_during_configuration():
    from datalens_dev_mcp.wizard.authoring import wizard_builder
    from datalens_sdk import EntryLocation
    with DataLensClientYC(auth=None) as client:
        with pytest.raises(ValueError, match="unsupported Wizard field role"):
            wizard_builder(client, Dataset(id="synthetic", result_schema=tuple(FIELDS)), {
                "visualization": "flat_table", "roles": {"build": ["date-guid"]}},
                name="Synthetic", location=EntryLocation.workbook("synthetic-workbook"))


def test_typed_expected_content_is_checked_and_persisted(tmp_path):
    from test_l06_object_lifecycle import FakeReader, FakeBackend, rb, service
    expected = {"data": {"datasetsIds": ["synthetic-dataset"]}}
    reader = FakeReader({("wizard_chart", "synthetic-chart", "saved"): [
        rb("wizard_chart", "synthetic-chart", "r1", {"data": {"datasetsIds": ["wrong-dataset"]}})]})
    backend = FakeBackend([{"object_id": "synthetic-chart", "expected_readback": expected}])
    writer = service(tmp_path, reader, backend)
    result = writer.create_objects([{"client_ref": "table", "object_type": "wizard_chart", "name": "Synthetic", "wizard": {
        "dataset_id": "synthetic-dataset", "visualization": "flat_table",
        "roles": {"columns": ["date-guid"]}}}], {"workbook_id": "synthetic-workbook"}, operation_id="typed-create")
    assert result["results"][0]["status"] == "uncertain"
    assert result["results"][0]["desired"] == expected
    assert result["results"][0]["code"] == "readback_mismatch"
