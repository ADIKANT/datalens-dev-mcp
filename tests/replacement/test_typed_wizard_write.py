from types import SimpleNamespace

import pytest
from datalens_sdk import DataLensClientYC, Dataset
from test_l04_dataset_wizard import FIELDS

from datalens_dev_mcp.api.sdk_adapter import SdkAdapter


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
        draft = {
            "object_type": "wizard_chart",
            "name": "Synthetic table",
            "wizard": {
                "dataset_id": dataset.id,
                "visualization": "flat_table",
                "roles": {"columns": ["date-guid", "revenue-guid"]},
            },
        }
        result = SdkAdapter(client=client).create(draft, {"workbook_id": "synthetic-workbook"})
    assert result["object_id"] == "synthetic-chart"
    assert reads == [{"by_id": "synthetic-dataset", "branch": "saved"}]
    assert len(specs) == 1
    assert result["expected_readback"]["data"]["sources"]["datasetsIds"] == ["synthetic-dataset"]


def test_wizard_role_cannot_invoke_build_during_configuration():
    from datalens_sdk import EntryLocation

    from datalens_dev_mcp.wizard.authoring import wizard_builder

    with DataLensClientYC(auth=None) as client, pytest.raises(ValueError, match="unsupported Wizard field role"):
        wizard_builder(
            client,
            Dataset(id="synthetic", result_schema=tuple(FIELDS)),
            {"visualization": "flat_table", "roles": {"build": ["date-guid"]}},
            name="Synthetic",
            location=EntryLocation.workbook("synthetic-workbook"),
        )


def test_typed_expected_content_is_checked_and_persisted(tmp_path):
    from test_l06_object_lifecycle import FakeBackend, FakeReader, rb, service

    expected = {"data": {"datasetsIds": ["synthetic-dataset"]}}
    reader = FakeReader(
        {
            ("wizard_chart", "synthetic-chart", "saved"): [
                rb("wizard_chart", "synthetic-chart", "r1", {"data": {"datasetsIds": ["wrong-dataset"]}})
            ]
        }
    )
    backend = FakeBackend([{"object_id": "synthetic-chart", "expected_readback": expected}])
    writer = service(tmp_path, reader, backend)
    result = writer.create_objects(
        [
            {
                "client_ref": "table",
                "object_type": "wizard_chart",
                "name": "Synthetic",
                "wizard": {
                    "dataset_id": "synthetic-dataset",
                    "visualization": "flat_table",
                    "roles": {"columns": ["date-guid"]},
                },
            }
        ],
        {"workbook_id": "synthetic-workbook"},
        operation_id="typed-create",
    )
    assert result["results"][0]["status"] == "uncertain"
    assert result["results"][0]["desired"] == expected
    assert result["results"][0]["code"] == "readback_mismatch"
def test_multimeasure_defaults_resolve_collisions_and_accept_explicit_grid():
    from datalens_dev_mcp.wizard.authoring import resolve_wizard_presentation

    for count in (2, 9):
        spec = {"visualization": "line", "roles": {"x": ["date"], "y": [f"measure-{i:03}" for i in range(count)]},
                "grid": {"x": True, "y": True}}
        result, profile = resolve_wizard_presentation(spec)
        assert len(result["measure_colors"]) == count
        assert result["grid"]["x"] and result["grid"]["y"]
        if count == 2:
            assert len(set(result["measure_colors"].values())) == 2
        else:
            assert profile["advisories"]
        explicit = {"measure-000": "#abcdef"}
        result, _ = resolve_wizard_presentation({**spec, "measure_colors": explicit})
        assert result["measure_colors"] == explicit
