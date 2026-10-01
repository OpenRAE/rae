"""Closed-shape policy for the dev-container entry point.

`devcontainer.json` is what a contributor's client executes on their behalf, so
it admits only the reviewed keys and fixed values that make the container ready
to use: the reviewed image definition, the non-root account, one named cache
volume, the one repository setup command, the tool path, editor customizations,
while native host sizing stays with the client. Host-side commands, extra environment, build inputs, host
mounts, and container capabilities are refused rather than reviewed ad hoc.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.policy.common import PolicyFailure, load_bounded_json_object
from tools.tooling_artifact_policy_common import (
    as_list,
    as_mapping,
    failure,
    is_regular_repo_file,
)

DEVCONTAINER_CONFIG_PATH = ".devcontainer/devcontainer.json"
MAX_CONFIG_BYTES = 64 * 1024

RULE_SHAPE = "tooling-container-config-shape"
RULE_USER = "tooling-container-user"
RULE_RUNTIME = "tooling-container-unsafe-runtime"

SETUP_COMMAND = "/usr/bin/python3 -m tools.devcontainer_setup"
REMOTE_PATH = "${containerWorkspaceFolder}/implementations/tooling/python/.venv/bin:${containerEnv:PATH}"

_KEYS = frozenset(
    {
        "name",
        "build",
        "remoteUser",
        "containerUser",
        "updateRemoteUserUID",
        "mounts",
        "updateContentCommand",
        "remoteEnv",
        "hostRequirements",
        "customizations",
    }
)
_REQUIRED_KEYS = frozenset({"build", "remoteUser", "containerUser", "updateContentCommand", "remoteEnv"})
# Keys that would run on the host, widen container privileges, or expose host state.
_UNSAFE_RUNTIME_KEYS = frozenset(
    {
        "initializeCommand",
        "privileged",
        "runArgs",
        "capAdd",
        "securityOpt",
        "init",
        "overrideCommand",
        "workspaceMount",
    }
)
_VOLUME_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*(?:\$\{devcontainerId\}[a-z0-9_.-]*)?$")
_EXTENSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*\.[A-Za-z0-9][A-Za-z0-9-]*$")
# Editor settings that inject terminal environment, shells, or commands.
_UNSAFE_SETTING_RE = re.compile(
    r"^terminal\.integrated\.|(?:^|\.)env(?:File)?(?:\.|$)|command|shell|args$|automationProfile",
    re.IGNORECASE,
)
_SCALARS = (str, int, float, bool)


def load_devcontainer_config(
    repo_root: Path,
) -> tuple[dict[str, Any] | None, PolicyFailure | None]:
    if not is_regular_repo_file(repo_root, DEVCONTAINER_CONFIG_PATH):
        return None, failure(
            RULE_SHAPE,
            "dev-container configuration could not be read safely",
            DEVCONTAINER_CONFIG_PATH,
        )
    try:
        return load_bounded_json_object(repo_root, DEVCONTAINER_CONFIG_PATH, max_bytes=MAX_CONFIG_BYTES), None
    except (OSError, ValueError, RecursionError):
        return None, failure(
            RULE_SHAPE,
            "dev-container configuration could not be parsed safely",
            DEVCONTAINER_CONFIG_PATH,
        )


def _build_admitted(build: object) -> bool:
    return (
        isinstance(build, Mapping)
        and set(build) <= {"dockerfile", "context"}
        and build.get("dockerfile") == "Dockerfile"
        and build.get("context", ".") == "."
    )


def _mount_admitted(mount: object, cache_root: str) -> bool:
    if not isinstance(mount, str):
        return False
    parts = {key: value for key, _, value in (part.partition("=") for part in mount.split(","))}
    return (
        set(parts) == {"source", "target", "type"}
        and parts["type"] == "volume"
        and _VOLUME_SOURCE_RE.fullmatch(parts["source"]) is not None
        and (parts["target"] == cache_root or parts["target"].startswith(f"{cache_root}/"))
    )


def _setting_value_admitted(value: object, *, nested: bool = False) -> bool:
    if isinstance(value, _SCALARS):
        return True
    if isinstance(value, list):
        return all(isinstance(item, _SCALARS) for item in value)
    return (
        not nested
        and isinstance(value, Mapping)
        and all(
            not _UNSAFE_SETTING_RE.search(key) and _setting_value_admitted(item, nested=True)
            for key, item in value.items()
        )
    )


def _customizations_admitted(value: object) -> bool:
    customizations = as_mapping(value)
    vscode = as_mapping(customizations.get("vscode"))
    extensions = vscode.get("extensions", [])
    settings = vscode.get("settings", {})
    return (
        isinstance(value, Mapping)
        and set(customizations) == {"vscode"}
        and isinstance(customizations.get("vscode"), Mapping)
        and set(vscode) <= {"extensions", "settings"}
        and isinstance(extensions, list)
        and all(isinstance(item, str) and _EXTENSION_ID_RE.fullmatch(item) for item in extensions)
        and isinstance(settings, Mapping)
        and all(not _UNSAFE_SETTING_RE.search(key) and _setting_value_admitted(item) for key, item in settings.items())
    )


def devcontainer_failures(document: Mapping[str, Any], user: str) -> list[PolicyFailure]:
    """Return every way the entry point departs from its closed reviewed shape."""

    keys = set(document)
    mounts = document.get("mounts", [])
    checks = (
        (
            not keys & _UNSAFE_RUNTIME_KEYS,
            RULE_RUNTIME,
            "dev-container requests host execution, extra capabilities, or a host mount",
        ),
        (
            _KEYS >= keys >= _REQUIRED_KEYS,
            RULE_SHAPE,
            "dev-container configuration departs from its reviewed key set",
        ),
        (
            _build_admitted(document.get("build")),
            RULE_SHAPE,
            "dev-container build must select the reviewed image definition without extra inputs",
        ),
        (
            document.get("updateContentCommand") == SETUP_COMMAND,
            RULE_SHAPE,
            "dev-container setup must run only the reviewed repository setup command",
        ),
        (
            document.get("remoteEnv") == {"PATH": REMOTE_PATH},
            RULE_SHAPE,
            "dev-container environment may only put the locked tool environment on PATH",
        ),
        (
            document.get("updateRemoteUserUID", True) is True,
            RULE_SHAPE,
            "dev-container must keep the development user aligned with the checkout owner",
        ),
        (
            "customizations" not in document or _customizations_admitted(document["customizations"]),
            RULE_SHAPE,
            "dev-container editor customizations may not configure commands, shells, or environment",
        ),
        (isinstance(mounts, list), RULE_SHAPE, "dev-container mounts must be a list"),
        (
            all(_mount_admitted(mount, f"/home/{user}/.cache") for mount in as_list(mounts)),
            RULE_RUNTIME,
            "dev-container mounts anything other than a named development cache volume",
        ),
        (
            all(document.get(key) == user for key in ("remoteUser", "containerUser")),
            RULE_USER,
            "dev-container must run as the reviewed non-root development user",
        ),
    )
    return [failure(rule, message, DEVCONTAINER_CONFIG_PATH) for admitted, rule, message in checks if not admitted]
