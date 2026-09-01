import json
import unittest
from io import BytesIO
from urllib.error import HTTPError

from datalens_dev_mcp.api.client import DataLensApiClient
from datalens_dev_mcp.api.errors import DataLensApiError
from datalens_dev_mcp.api.request_compiler import validate_method_request
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.mcp.object_registry import object_read_contract
from datalens_dev_mcp.mcp.response_projection import audit_entries_summary, workbook_entries_summary
from datalens_dev_mcp.api.methods import compiled_api_version


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post_json(self, url, body, headers):
        self.requests.append((url, json.loads(body.decode("utf-8")), dict(headers)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response).encode("utf-8")


def contract_error():
    return HTTPError(
        url="https://api.datalens.tech/rpc/getEntries",
        code=400,
        msg="error",
        hdrs={},
        fp=BytesIO(b'{"message":"unsupported api version"}'),
    )


def create_payload(method, location):
    if method == "createDashboard":
        return {"entry": {"data": {}, "meta": {}, **location}}
    if method == "createEditorChart":
        return {"entry": {"type": "advanced-chart_node", "data": {}, **location}}
    if method == "createReport":
        return {
            "data": {
                "counter": 1,
                "salt": "salt",
                "version": 1,
                "slides": [],
                "slideGroups": [],
                "slidesOrder": [],
                "visualSettings": {},
                "slideSettings": {},
            },
            "meta": {},
            **location,
        }
    if method == "createQLChart":
        return {"template": "ql", "data": {}, **location}
    return {"template": "datalens", "data": {}, **location}


class CurrentApiCorpusHardeningTests(unittest.TestCase):
    def test_create_entry_location_accepts_only_documented_forms(self):
        methods = (
            "createDashboard",
            "createEditorChart",
            "createWizardChart",
            "createReport",
            "createQLChart",
        )
        valid_locations = (
            {"key": "folder/object"},
            {"workbookId": "workbook_1", "name": "Object name"},
        )
        invalid_locations = (
            {},
            {"key": "folder/object", "workbookId": "workbook_1", "name": "Object name"},
            {"workbookId": "workbook_1"},
            {"workbookId": "workbook_1", "name": "Object name", "key": ""},
        )
        for method in methods:
            for location in valid_locations:
                with self.subTest(method=method, location=location):
                    result = validate_method_request(method, create_payload(method, location))
                    self.assertTrue(result["ok"], result["issues"])
            for location in invalid_locations:
                with self.subTest(method=method, location=location):
                    result = validate_method_request(method, create_payload(method, location))
                    self.assertFalse(result["ok"])
                    self.assertTrue(any("invalid create location" in issue for issue in result["issues"]))

    def test_get_entries_current_shapes_and_removed_page_are_validated(self):
        valid = validate_method_request(
            "getEntries",
            {
                "ids": ["entry_1"],
                "createdBy": ["user_1"],
                "pageToken": "next",
                "pageSize": 200,
                "ignoreSharedEntries": True,
            },
        )
        self.assertTrue(valid["ok"], valid["issues"])

        for payload in (
            {"ids": "entry_1"},
            {"createdBy": "user_1"},
            {"page": 1},
            {"pageSize": 201},
        ):
            with self.subTest(payload=payload):
                result = validate_method_request("getEntries", payload)
                self.assertFalse(result["ok"], result)

    def test_readonly_rpc_validation_blocks_before_transport(self):
        transport = FakeTransport([])
        client = DataLensApiClient(
            DataLensConfig(iam_token="token", org_id="org", request_interval_sec=0),
            transport=transport,
        )

        with self.assertRaises(DataLensApiError) as raised:
            client.rpc_readonly("getEntries", {"ids": "entry_1"})

        self.assertIn("blocked before HTTP", str(raised.exception))
        self.assertEqual(transport.requests, [])

    def test_read_and_write_use_the_same_compiled_api_contract(self):
        read_transport = FakeTransport([{"entries": []}])
        read_client = DataLensApiClient(
            DataLensConfig(iam_token="token", org_id="org", request_interval_sec=0),
            transport=read_transport,
        )
        read_client.rpc_readonly("getEntries", {"ids": ["entry_1"]})
        write_transport = FakeTransport([{"workbooks": []}, {"ok": True}])
        write_client = DataLensApiClient(
            DataLensConfig(iam_token="token", org_id="org", request_interval_sec=0),
            transport=write_transport,
        )
        write_client.rpc("updateDashboard", {"dashboardId": "dash_1"})

        expected = compiled_api_version()
        self.assertEqual(read_transport.requests[0][2]["x-dl-api-version"], expected)
        self.assertEqual(write_transport.requests[0][2]["x-dl-api-version"], expected)

    def test_get_entries_does_not_retry_under_another_api_contract(self):
        transport = FakeTransport([contract_error()])
        client = DataLensApiClient(
            DataLensConfig(iam_token="token", org_id="org", request_interval_sec=0),
            transport=transport,
        )

        with self.assertRaises(DataLensApiError):
            client.rpc_readonly("getEntries", {"ids": ["entry_1"]})

        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(transport.requests[0][2]["x-dl-api-version"], "2")

    def test_compute_is_inventory_only_and_artifact_is_audit_only(self):
        compute = object_read_contract("compute")
        self.assertIsNotNone(compute)
        self.assertIsNone(compute.read_method)
        self.assertEqual(compute.branch_semantics, "inventory_only")
        self.assertIsNone(object_read_contract("artifact"))

        inventory = workbook_entries_summary(
            {"entries": [{"entryId": "compute_1", "scope": "compute", "workbookId": "workbook_1"}]}
        )
        self.assertEqual(inventory["type_counts"], {"compute": 1})

        audit = audit_entries_summary(
            {
                "entries": [
                    {"entryId": "compute_1", "scope": "compute", "isDeleted": False},
                    {"entryId": "artifact_1", "scope": "artifact", "isDeleted": True},
                ]
            }
        )
        self.assertEqual(audit["scope_counts"], {"artifact": 1, "compute": 1})
        self.assertEqual(audit["entries"][1]["scope_policy"], "audit_only")
        self.assertEqual(audit["scope_policy"]["artifact"], "audit_only_not_generic_object")


if __name__ == "__main__":
    unittest.main()
