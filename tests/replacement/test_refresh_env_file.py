from datalens_dev_mcp.config import DataLensConfig
from datalens_dev_mcp.server import dl_auth_refresh


def test_explicit_refresh_survives_next_config_read_without_rewriting_file(tmp_path, monkeypatch):
    path = tmp_path / "env"
    original = "DATALENS_ORG_ID=synthetic-org\nDATALENS_IAM_TOKEN=expired-synthetic\n"
    path.write_text(original)
    monkeypatch.setenv("DATALENS_ENV_FILE", str(path))
    monkeypatch.setattr("datalens_dev_mcp.server.refresh_iam_token_with_yc", lambda: "fresh-synthetic")
    report = dl_auth_refresh()
    assert DataLensConfig.from_env().iam_token == "fresh-synthetic"
    assert path.read_text() == original
    assert "fresh-synthetic" not in str(report)
    monkeypatch.setattr("datalens_dev_mcp.server.refresh_iam_token_with_yc", lambda: "newer-synthetic")
    dl_auth_refresh()
    assert DataLensConfig.from_env().iam_token == "newer-synthetic"
    path.write_text(original.replace("synthetic-org", "another-synthetic-org"))
    assert DataLensConfig.from_env().iam_token == "expired-synthetic"
    path.write_text(original.replace("expired-synthetic", "manually-changed-synthetic"))
    assert DataLensConfig.from_env().iam_token == "manually-changed-synthetic"
