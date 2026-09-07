from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

# Process-local credentials only. The configured credential is part of the key:
# changing account, endpoint, or the token on disk invalidates the override.
_RUNTIME_TOKENS: dict[tuple[str, str, str], str] = {}


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"").strip("'")
    return values


@dataclass(frozen=True)
class DataLensConfig:
    base_url: str = "https://api.datalens.tech"
    org_id: str = ""
    iam_token: str = field(default="", repr=False)
    request_timeout_sec: float = 30.0
    read_retries: int = 2
    credential_source: str = "explicit"
    refresh_available: bool = False
    _configured_token: str | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        env_file: str | Path | None = None,
    ) -> DataLensConfig:
        process = dict(os.environ if env is None else env)
        configured_file = env_file or process.get("DATALENS_ENV_FILE")
        file_values = _read_env_file(Path(configured_file).expanduser()) if configured_file else {}
        values = {**process, **file_values}
        token = values.get("DATALENS_IAM_TOKEN") or values.get("YC_IAM_TOKEN") or ""
        source = "env_file" if token and file_values else "process_env" if token else "none"
        refresh = values.get("DATALENS_ENABLE_TOKEN_REFRESH_ON_401", "").strip().lower() in {"1", "true", "yes"}
        base_url = (values.get("DATALENS_API_BASE_URL") or "https://api.datalens.tech").rstrip("/")
        org_id = values.get("DATALENS_ORG_ID", "").strip()
        configured_token = token.strip()
        active_token = _RUNTIME_TOKENS.get((base_url, org_id, configured_token), configured_token)
        return cls(
            base_url=base_url,
            org_id=org_id,
            iam_token=active_token,
            request_timeout_sec=float(values.get("DATALENS_REQUEST_TIMEOUT_SEC", "30")),
            read_retries=int(values.get("DATALENS_READ_RETRIES", "2")),
            credential_source="runtime_refresh" if active_token != configured_token else source,
            refresh_available=refresh,
            _configured_token=configured_token,
        )

    def remember_refreshed_token(self, token: str) -> None:
        if not token or any(character.isspace() for character in token):
            raise ValueError("refresh returned an invalid credential")
        original = self._configured_token if self._configured_token is not None else self.iam_token
        _RUNTIME_TOKENS[(self.base_url, self.org_id, original)] = token

    def require_auth(self) -> None:
        if not self.iam_token or not self.org_id:
            from datalens_dev_mcp.api.errors import DataLensApiError

            raise DataLensApiError("DataLens credentials are incomplete; configure token and organization id")

    def credential_report(self) -> dict[str, object]:
        return {
            "base_url": self.base_url,
            "org_id_set": bool(self.org_id),
            "credential_source": self.credential_source,
            "token_present": bool(self.iam_token),
            "refresh_available": self.refresh_available,
        }
