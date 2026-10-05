from datalens_dev_mcp.api.runtime import DataLensRuntime
from datalens_dev_mcp.config import DataLensConfig


class HealthyTransport:
    def call(self, method, payload, headers):
        return {"entries": []}


def test_fresh_process_loads_standard_user_credential_file_without_manifest_env(tmp_path):
    path = tmp_path / "datalens-dev-mcp/credentials.env"
    path.parent.mkdir()
    path.write_text(
        "DATALENS_ORG_ID=synthetic-org\nDATALENS_IAM_TOKEN=synthetic-token\n"
        "DATALENS_ENABLE_TOKEN_REFRESH_ON_401=true\nDATALENS_YC_BINARY=/synthetic/yc\n"
    )

    config = DataLensConfig.from_env({"XDG_CONFIG_HOME": str(tmp_path)})

    assert config.org_id == "synthetic-org"
    assert config.iam_token == "synthetic-token"
    assert config.credential_source == "env_file"
    assert config.refresh_available is True
    assert config.yc_binary == "/synthetic/yc"


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


def test_field_provenance_and_profile_isolate_refresh(tmp_path):
    path = tmp_path / "env"
    path.write_text("DATALENS_ORG_ID=synthetic-org\nDATALENS_YC_PROFILE=profile B\n")
    env = {"DATALENS_IAM_TOKEN": "original-synthetic"}
    config = DataLensConfig.from_env(env, env_file=path)
    assert config.credential_source == "process_env"
    assert config.yc_profile == "profile B"
    config.remember_refreshed_token("refreshed-synthetic")
    assert DataLensConfig.from_env(env, env_file=path).iam_token == "refreshed-synthetic"
    path.write_text("DATALENS_ORG_ID=synthetic-org\nDATALENS_YC_PROFILE=profile C\n")
    assert DataLensConfig.from_env(env, env_file=path).iam_token == "original-synthetic"


def test_explicit_profile_passed_as_one_argument(monkeypatch):
    from types import SimpleNamespace

    from datalens_dev_mcp.api.auth import refresh_iam_token_with_yc
    commands = []
    monkeypatch.setattr("subprocess.run", lambda command, **kwargs:
                        commands.append(command) or SimpleNamespace(returncode=0, stdout="synthetic", stderr=""))
    assert refresh_iam_token_with_yc(yc_profile="profile B") == "synthetic"
    assert commands[0][commands[0].index("--profile") + 1] == "profile B"
    assert "--no-browser" in commands[0]


def test_explicit_profile_failure_has_no_default_fallback(monkeypatch):
    import subprocess
    from types import SimpleNamespace

    import pytest

    from datalens_dev_mcp.api.auth import refresh_iam_token_with_yc
    from datalens_dev_mcp.api.errors import CredentialRefreshError, error_response
    calls = []
    def missing_profile(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="secret-token", stderr="unknown profile; secret-detail")
    monkeypatch.setattr(subprocess, "run", missing_profile)
    with pytest.raises(CredentialRefreshError) as caught:
        refresh_iam_token_with_yc(yc_profile="unavailable profile")
    assert len(calls) == 1
    assert calls[0][calls[0].index("--profile") + 1] == "unavailable profile"
    assert "secret" not in repr(error_response(caught.value))


def test_impersonation_and_installation_do_not_share_runtime_token(tmp_path):
    path = tmp_path / "env"
    path.write_text("")
    base = {"DATALENS_ORG_ID": "synthetic-org", "DATALENS_IAM_TOKEN": "scope-original",
            "DATALENS_YC_PROFILE": "authorized", "DATALENS_YC_IMPERSONATE_SERVICE_ACCOUNT_ID": "principal-a"}
    config = DataLensConfig.from_env(base, env_file=path)
    config.remember_refreshed_token("scope-refreshed")
    assert DataLensConfig.from_env(base, env_file=path).iam_token == "scope-refreshed"
    changed = {**base, "DATALENS_YC_IMPERSONATE_SERVICE_ACCOUNT_ID": "principal-b"}
    assert DataLensConfig.from_env(changed, env_file=path).iam_token == "scope-original"
    changed = {**base, "DATALENS_API_BASE_URL": "https://synthetic.invalid"}
    assert DataLensConfig.from_env(changed, env_file=path).iam_token == "scope-original"
