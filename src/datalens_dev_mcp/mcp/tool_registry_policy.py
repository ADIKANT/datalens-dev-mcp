from __future__ import annotations

from collections.abc import Mapping


HIDDEN_TOOL_CALLS_ENV = "DATALENS_MCP_ALLOW_HIDDEN_TOOL_CALLS"
TEST_ONLY_REGISTRY_ENV = "DATALENS_MCP_TEST_ONLY_REGISTRY"
LEGACY_TOOL_PROFILE_ENV = "DATALENS_MCP_TOOL_PROFILE"
LEGACY_TOOL_SURFACE_ENV = "DATALENS_MCP_TOOL_SURFACE"

TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
INTERNAL_PROFILE_ENV_VARS = (LEGACY_TOOL_PROFILE_ENV, LEGACY_TOOL_SURFACE_ENV)


def env_truthy(name: str, env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else _os_environ()
    return str(source.get(name, "")).strip().lower() in TRUE_ENV_VALUES


def test_only_registry_enabled(env: Mapping[str, str] | None = None) -> bool:
    return env_truthy(TEST_ONLY_REGISTRY_ENV, env)


def hidden_tool_calls_enabled(env: Mapping[str, str] | None = None) -> bool:
    return env_truthy(HIDDEN_TOOL_CALLS_ENV, env) and test_only_registry_enabled(env)


def tool_registry_env_status(env: Mapping[str, str] | None = None) -> dict[str, object]:
    source = env if env is not None else _os_environ()
    hidden_env_present = bool(str(source.get(HIDDEN_TOOL_CALLS_ENV, "")).strip())
    hidden_env_enabled = env_truthy(HIDDEN_TOOL_CALLS_ENV, source)
    test_marker_enabled = test_only_registry_enabled(source)
    internal_profile_env = [
        name for name in INTERNAL_PROFILE_ENV_VARS if str(source.get(name, "")).strip()
    ]
    return {
        "standard_surface": "standard",
        "hidden_tool_calls_env": HIDDEN_TOOL_CALLS_ENV,
        "test_only_registry_env": TEST_ONLY_REGISTRY_ENV,
        "hidden_tool_calls_env_present": hidden_env_present,
        "hidden_tool_calls_env_enabled": hidden_env_enabled,
        "test_only_registry_enabled": test_marker_enabled,
        "hidden_tool_calls_enabled": hidden_env_enabled and test_marker_enabled,
        "hidden_tool_calls_env_ignored": hidden_env_enabled and not test_marker_enabled,
        "internal_profile_env_vars_present": internal_profile_env,
    }


def _os_environ() -> Mapping[str, str]:
    import os

    return os.environ
