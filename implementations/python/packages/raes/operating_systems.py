"""Governed portable operating-system identity vocabulary (issue #1077)."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated

from pydantic import WithJsonSchema
from raes_contracts.operating_systems import OS_VERSION_PATTERN, OS_VERSION_RE
from raes_contracts.variable_references import VARIABLE_TOKEN_PATTERN, is_variable_ref


class OSDistribution(str, Enum):
    """Canonical portable distribution or product-line identifiers."""

    UBUNTU = "ubuntu"
    DEBIAN = "debian"
    ROCKY_LINUX = "rocky-linux"
    RED_HAT_ENTERPRISE_LINUX = "red-hat-enterprise-linux"
    WINDOWS_SERVER = "windows-server"
    WINDOWS_CLIENT = "windows-client"
    SOLARIS = "solaris"


OS_DISTRIBUTION_EXTENSION_PATTERN = r"^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*$"
_OS_DISTRIBUTION_EXTENSION_RE = re.compile(OS_DISTRIBUTION_EXTENSION_PATTERN)
_OS_DISTRIBUTION_EXTENSION_BODY = r"x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*"

AuthoredOSDistributionString = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "pattern": f"^(?:{_OS_DISTRIBUTION_EXTENSION_BODY}|{VARIABLE_TOKEN_PATTERN})$",
        }
    ),
]

AuthoredOSVersionString = Annotated[
    str,
    WithJsonSchema(
        {
            "type": "string",
            "pattern": f"^(?:{OS_VERSION_PATTERN[1:-1]}|{VARIABLE_TOKEN_PATTERN})?$",
        }
    ),
]


def normalize_os_distribution(value: object) -> object:
    """Normalize one authored distribution token and reject ungoverned values."""

    if isinstance(value, OSDistribution) or is_variable_ref(value):
        return value
    if not isinstance(value, str):
        raise ValueError("OS distribution must be a string")
    lowered = value.lower()
    if _OS_DISTRIBUTION_EXTENSION_RE.fullmatch(lowered):
        return lowered
    try:
        return OSDistribution(lowered)
    except ValueError as exc:
        raise ValueError(
            "OS distribution must be a governed portable term, a governed "
            "x-<owner>:<term> extension, or a ${var} placeholder"
        ) from exc


def normalize_os_version(value: object) -> object:
    """Validate a bounded release-only opaque token; empty means not authored."""

    if is_variable_ref(value):
        return value
    if value == "":
        return ""
    if not isinstance(value, str) or OS_VERSION_RE.fullmatch(value) is None:
        raise ValueError("OS version must be a bounded printable release token")
    return value


__all__ = [
    "AuthoredOSDistributionString",
    "AuthoredOSVersionString",
    "OSDistribution",
    "OS_DISTRIBUTION_EXTENSION_PATTERN",
    "normalize_os_distribution",
    "normalize_os_version",
]
