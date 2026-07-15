"""Synthetic fixture for adapter quarantine coverage."""


def run(client):
    client.call("updateDashboard", {})
    client.call("updateEditorChart", {})
    client.call("publishWorkbookEntry", {})
