"""Synthetic fixture for adapter detection."""


def run(client):
    client.call("validateDataset", {})
    client.call("updateDataset", {})
