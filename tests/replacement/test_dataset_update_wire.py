import copy
import json
from io import BytesIO
from unittest.mock import patch

import datalens_sdk
import httpx
import pytest

from datalens_dev_mcp.api.sdk_adapter import SdkAdapter
from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.server import dl_method_schema


def snapshot():
    return {'id': 'synthetic-dataset', 'revId': 'outer-r1', 'dataset': {
        'revision_id': 'inner-r7', 'description': 'before',
        'sources': [{'id': 'source-guid', 'parameters': {'sql': 'SELECT 1'}}],
        'source_avatars': [{'id': 'avatar-guid', 'source_id': 'source-guid'}],
        'avatar_relations': [], 'result_schema': [{'guid': 'field-guid', 'formula': '1'}],
        'obligatory_filters': [], 'rls2': {}}}


def run_update(desired, current=None):
    current = current or snapshot()
    writes = []
    def handle(request):
        if request.url.path.endswith('updateDataset'):
            writes.append((json.loads(request.content), request.headers.get('x-dl-api-version')))
        return httpx.Response(200, json=current)
    client = datalens_sdk.DataLensClientYC(
        auth=datalens_sdk.StaticYCIAMAuthProvider(org_id='synthetic', token='synthetic'),
        base_url='https://synthetic.invalid', transport=httpx.MockTransport(handle))
    def direct(request, **kwargs):
        assert request.full_url.endswith('/rpc/updateDataset')
        writes.append((json.loads(request.data), request.get_header('X-dl-api-version')))
        return BytesIO(json.dumps(current).encode())
    config = DataLensConfig(base_url='https://synthetic.invalid', org_id='synthetic', iam_token='synthetic')
    with patch('datalens_dev_mcp.api.client.request.urlopen', direct):
        SdkAdapter(config, client=client).update('dataset', 'synthetic-dataset', desired)
    return writes


def test_dataset_wire_preserves_inner_revision_and_content():
    desired = snapshot()
    desired['dataset']['description'] = 'after'
    original = copy.deepcopy(desired)
    writes = run_update(desired)
    assert writes == [({'datasetId': 'synthetic-dataset', 'data': {'dataset': desired['dataset']}}, '2')]
    assert desired == original


@pytest.mark.parametrize('field', ['outer', 'inner'])
def test_dataset_stale_revision_is_rejected(field):
    current = snapshot()
    if field == 'outer':
        current['revId'] = 'outer-r2'
    else:
        current['dataset']['revision_id'] = 'inner-r8'
    with pytest.raises(ValueError, match='revision'):
        run_update(snapshot(), current)


def test_dataset_missing_revision_is_not_invented():
    desired = snapshot()
    del desired['dataset']['revision_id']
    with pytest.raises(ValueError, match='revision'):
        run_update(desired)


def test_schema_lookup_example_reaches_dataset_adapter():
    result = dl_method_schema('updateDataset')
    operation = result['operation']
    assert operation['contract_kind'] == 'reference_contract'
    example = operation['example']
    desired = snapshot()
    desired['dataset'].update(example['data']['dataset'])
    desired['dataset']['revision_id'] = 'inner-r7'
    assert run_update(desired)[0][0]['data']['dataset'] == desired['dataset']


def test_unknown_method_returns_alternatives():
    result = dl_method_schema('doesNotExist')
    assert result['ok'] is False
    assert result['status'] == 'not_found'
    assert 'updateDataset' in result['available_methods']
