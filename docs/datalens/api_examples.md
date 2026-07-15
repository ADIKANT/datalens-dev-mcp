# DataLens API Examples

Source trace: `examples/datalens_api/rpc_examples.json` and `config/datalens_api_methods.json`.

Examples use placeholders only. They are payload-shape examples, not live requests.

## Dataset Update

```json
{
  "method": "updateDataset",
  "payload": {
    "datasetId": "<DATASET_ID>",
    "data": {
      "dataset": {}
    }
  }
}
```

## Dataset Validate

```json
{
  "method": "validateDataset",
  "payload": {
    "datasetId": "<DATASET_ID>",
    "workbookId": "<WORKBOOK_ID>",
    "data": {
      "dataset": {}
    }
  }
}
```

