from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_BASE_URL = "https://api.datalens.tech"
EXECUTION_SWITCH_ENV_NAMES = frozenset(
    {
        "DATALENS_MCP_ENABLE_WRITES",
        "DATALENS_MCP_LIVE_ALLOW_SAVE",
        "DATALENS_MCP_LIVE_ALLOW_PUBLISH",
    }
)


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_env_file(
    path: str | Path | None,
    *,
    override: bool = False,
    skip_keys: frozenset[str] = frozenset(),
) -> None:
    if not path:
        return
    env_path = Path(path).expanduser()
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in skip_keys or (key in os.environ and not override):
            continue
        os.environ[key] = value.strip().strip("'\"")


def read_env_file(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}
    env_path = Path(path).expanduser()
    if not env_path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip("'\"")
    return values


@dataclass(frozen=True)
class DataLensConfig:
    iam_token: str = ""
    org_id: str = ""
    base_url: str = DEFAULT_BASE_URL
    api_version: str = "auto"
    write_enabled: bool = True
    save_enabled: bool = True
    publish_enabled: bool = True
    delete_requires_confirmation: bool = True
    expert_rpc_enabled: bool = False
    request_interval_sec: float = 0.15
    request_timeout_sec: float = 30.0
    rate_limit_retries: int = 6
    request_debug: bool = False
    token_refresh_enabled: bool = False
    token_refresh_timeout_sec: float = 15.0
    yc_binary: str = "yc"
    expert_unsafe_internal_name_override: bool = False
    env_file_path: str = ""
    env_file_loaded: bool = False
    credential_source: str = "none"
    org_id_source: str = "none"
    env_file_reload_state: str = "not_reloaded"

    @classmethod
    def from_env(
        cls,
        env_file: str | Path | None = None,
        *,
        reload_state: str = "not_reloaded",
    ) -> "DataLensConfig":
        env_file_path = str(env_file or os.getenv("DATALENS_ENV_FILE") or "").strip()
        file_values = read_env_file(env_file_path)
        process_values = os.environ
        iam_token, credential_source = _first_config_value(
            ("DATALENS_IAM_TOKEN", "YC_IAM_TOKEN"),
            file_values=file_values,
            process_values=process_values,
            prefer_file=bool(env_file_path),
        )
        org_id, org_source = _first_config_value(
            ("DATALENS_ORG_ID",),
            file_values=file_values,
            process_values=process_values,
            prefer_file=bool(env_file_path),
        )
        base_url, _ = _first_config_value(
            ("DATALENS_BASE_URL", "DATALENS_API_BASE_URL"),
            file_values=file_values,
            process_values=process_values,
            prefer_file=bool(env_file_path),
            default=DEFAULT_BASE_URL,
        )
        return cls(
            iam_token=iam_token,
            org_id=org_id,
            base_url=base_url.rstrip("/"),
            api_version=_config_value(
                "DATALENS_API_VERSION",
                file_values=file_values,
                process_values=process_values,
                prefer_file=bool(env_file_path),
                default="auto",
            )
            or "auto",
            write_enabled=_execution_flag(
                "DATALENS_MCP_ENABLE_WRITES",
                file_values=file_values,
                process_values=process_values,
                prefer_file=bool(env_file_path),
                default=True,
            ),
            save_enabled=_execution_flag(
                "DATALENS_MCP_LIVE_ALLOW_SAVE",
                file_values=file_values,
                process_values=process_values,
                prefer_file=bool(env_file_path),
                default=True,
            ),
            publish_enabled=_execution_flag(
                "DATALENS_MCP_LIVE_ALLOW_PUBLISH",
                file_values=file_values,
                process_values=process_values,
                prefer_file=bool(env_file_path),
                default=True,
            ),
            delete_requires_confirmation=True,
            expert_rpc_enabled=_config_flag(
                "DATALENS_MCP_ENABLE_EXPERT_RPC",
                file_values=file_values,
                process_values=process_values,
                prefer_file=bool(env_file_path),
                default=False,
            ),
            request_interval_sec=float(
                _config_value(
                    "DATALENS_REQUEST_INTERVAL_SEC",
                    file_values=file_values,
                    process_values=process_values,
                    prefer_file=bool(env_file_path),
                    default="0.15",
                )
                or "0.15"
            ),
            request_timeout_sec=float(
                _config_value(
                    "DATALENS_REQUEST_TIMEOUT_SEC",
                    file_values=file_values,
                    process_values=process_values,
                    prefer_file=bool(env_file_path),
                    default="30",
                )
                or "30"
            ),
            rate_limit_retries=int(
                _config_value(
                    "DATALENS_RATE_LIMIT_RETRIES",
                    file_values=file_values,
                    process_values=process_values,
                    prefer_file=bool(env_file_path),
                    default="6",
                )
                or "6"
            ),
            request_debug=_config_flag(
                "DATALENS_REQUEST_DEBUG",
                file_values=file_values,
                process_values=process_values,
                prefer_file=bool(env_file_path),
                default=False,
            ),
            token_refresh_enabled=_config_flag(
                "DATALENS_ENABLE_TOKEN_REFRESH_ON_401",
                file_values=file_values,
                process_values=process_values,
                prefer_file=bool(env_file_path),
                default=False,
            ),
            token_refresh_timeout_sec=float(
                _config_value(
                    "DATALENS_TOKEN_REFRESH_TIMEOUT_SEC",
                    file_values=file_values,
                    process_values=process_values,
                    prefer_file=bool(env_file_path),
                    default="15",
                )
                or "15"
            ),
            yc_binary=_config_value(
                "DATALENS_YC_BINARY",
                file_values=file_values,
                process_values=process_values,
                prefer_file=bool(env_file_path),
                default="yc",
            )
            or "yc",
            expert_unsafe_internal_name_override=_config_flag(
                "DATALENS_MCP_EXPERT_ALLOW_UNSAFE_INTERNAL_NAMES",
                file_values=file_values,
                process_values=process_values,
                prefer_file=bool(env_file_path),
                default=False,
            ),
            env_file_path=str(Path(env_file_path).expanduser()) if env_file_path else "",
            env_file_loaded=bool(env_file_path and file_values),
            credential_source=credential_source,
            org_id_source=org_source,
            env_file_reload_state=reload_state,
        )

    def reload_canonical_env(self, *, reload_state: str = "reloaded_from_canonical_env") -> "DataLensConfig":
        """Reload the configured canonical env file without changing explicit in-memory configs."""

        if not self.env_file_path:
            return self
        return type(self).from_env(self.env_file_path, reload_state=reload_state)

    def require_auth(self) -> None:
        from datalens_dev_mcp.api.errors import DataLensApiError

        if not self.iam_token:
            raise DataLensApiError(
                "BLOCKED_LIVE_CREDENTIALS: Missing DATALENS_IAM_TOKEN or YC_IAM_TOKEN in environment or env file."
            )
        if not self.org_id:
            raise DataLensApiError("BLOCKED_LIVE_CREDENTIALS: Missing DATALENS_ORG_ID in environment or env file.")

    def credential_report(self) -> dict[str, object]:
        return {
            "credential_source": self.credential_source,
            "org_id_source": self.org_id_source,
            "env_file": {
                "configured": bool(self.env_file_path),
                "loaded": self.env_file_loaded,
                "reload_state": self.env_file_reload_state,
            },
            "token_present": bool(self.iam_token),
            "org_id_set": bool(self.org_id),
            "token_refresh_on_401": self.token_refresh_enabled,
            "yc_binary_configured": bool(self.yc_binary),
            "token_refresh_timeout_sec": self.token_refresh_timeout_sec,
        }


def _first_config_value(
    keys: tuple[str, ...],
    *,
    file_values: Mapping[str, str],
    process_values: Mapping[str, str],
    prefer_file: bool,
    default: str = "",
) -> tuple[str, str]:
    sources = ((file_values, "env_file"), (process_values, "process_env"))
    if not prefer_file:
        sources = tuple(reversed(sources))
    for source, label in sources:
        for key in keys:
            value = str(source.get(key, "")).strip()
            if value:
                return value, label
    return default, "default" if default else "none"


def _config_value(
    key: str,
    *,
    file_values: Mapping[str, str],
    process_values: Mapping[str, str],
    prefer_file: bool,
    default: str = "",
) -> str:
    value, _ = _first_config_value((key,), file_values=file_values, process_values=process_values, prefer_file=prefer_file)
    return value or default


def _config_flag(
    key: str,
    *,
    file_values: Mapping[str, str],
    process_values: Mapping[str, str],
    prefer_file: bool,
    default: bool,
) -> bool:
    raw = _config_value(key, file_values=file_values, process_values=process_values, prefer_file=prefer_file)
    if not raw:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _execution_flag(
    key: str,
    *,
    file_values: Mapping[str, str],
    process_values: Mapping[str, str],
    prefer_file: bool,
    default: bool,
) -> bool:
    """Resolve an execution switch while making every explicit off value authoritative."""

    false_values = {"0", "false", "no", "off"}
    explicit_values = (
        str(file_values.get(key, "")).strip().lower(),
        str(process_values.get(key, "")).strip().lower(),
    )
    if any(value in false_values for value in explicit_values):
        return False
    return _config_flag(
        key,
        file_values=file_values,
        process_values=process_values,
        prefer_file=prefer_file,
        default=default,
    )
