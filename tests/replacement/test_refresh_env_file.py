from datalens_dev_mcp.api.runtime import DataLensRuntime
from datalens_dev_mcp.config import DataLensConfig


class HealthyTransport:
    def call(self, method, payload, headers):
        return {"entries": []}


def test_fresh_process_loads_standard_user_credential_file_without_manifest_env(tmp_path):
    path = tmp_path / "datalens-dev-mcp/credentials.env"
    path.parent.mkdir()
    path.write_text(
        "DATALENS_ORG_ID=synthetic-org\nDATALENS_IAM_TOKEN=synthetic-token\nDATALENS_ENABLE_TOKEN_REFRESH_ON_401=true\n"
    )

    config = DataLensConfig.from_env({"XDG_CONFIG_HOME": str(tmp_path)})

    assert config.org_id == "synthetic-org"
    assert config.iam_token == "synthetic-token"
    assert config.credential_source == "env_file"
    assert config.refresh_available is True


def test_explicit_refresh_survives_next_config_read_without_rewriting_file(tmp_path, monkeypatch):
    path = tmp_path / "env"
    original = "DATALENS_ORG_ID=synthetic-org\nDATALENS_IAM_TOKEN=expired-synthetic\n"
    path.write_text(original)
    monkeypatch.setenv("DATALENS_ENV_FILE", str(path))
    runtime = DataLensRuntime(
        DataLensConfig.from_env(),
        api_transport=HealthyTransport(),
        credential_refresher=lambda: "fresh-synthetic",
    )
    runtime.refresh_and_probe()
    assert DataLensConfig.from_env().iam_token == "fresh-synthetic"
    assert path.read_text() == original
    runtime = DataLensRuntime(
        DataLensConfig.from_env(),
        api_transport=HealthyTransport(),
        credential_refresher=lambda: "newer-synthetic",
    )
    runtime.refresh_and_probe()
    assert DataLensConfig.from_env().iam_token == "newer-synthetic"
    path.write_text(original.replace("synthetic-org", "another-synthetic-org"))
    assert DataLensConfig.from_env().iam_token == "expired-synthetic"
    path.write_text(original.replace("expired-synthetic", "manually-changed-synthetic"))
    assert DataLensConfig.from_env().iam_token == "manually-changed-synthetic"
