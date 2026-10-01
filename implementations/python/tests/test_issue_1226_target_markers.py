"""Reviewed closure targets must bind their own PEP 508 marker environment.

The projection generator resolves locks for targets it is not running on, so a
marker field inherited from the generator host makes the reviewed projection
depend on who ran it. These cases pin every field to the reviewed target.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from packaging.markers import Marker, default_environment
from tools.generate_python_closures import TARGETS
from tools.generate_python_closures_locks import locked_closure, target_environment

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_LOCK = REPO_ROOT / "implementations" / "tooling" / "artifacts.lock.json"

# Every field PEP 508 defines. A reviewed projection must bind all of them.
_MARKER_FIELDS = frozenset(default_environment())

_LINUX_X86 = "x86_64-unknown-linux-gnu"
_LINUX_ARM = "aarch64-unknown-linux-gnu"
_MACOS_ARM = "aarch64-apple-darwin"


def _reviewed_full_version(python_version: str) -> str:
    lock = json.loads(ARTIFACT_LOCK.read_text(encoding="utf-8"))
    (artifact,) = [item for item in lock["artifacts"] if item["artifact_id"] == f"cpython-{python_version}"]
    return str(artifact["version"])


def test_reviewed_target_binds_every_marker_field() -> None:
    environment = target_environment("3.14", _MACOS_ARM, full_version="3.14.7")
    assert set(environment) == _MARKER_FIELDS


@pytest.mark.parametrize(
    ("platform", "expected_system", "expected_sys_platform", "expected_machine"),
    [
        (_LINUX_X86, "Linux", "linux", "x86_64"),
        (_LINUX_ARM, "Linux", "linux", "aarch64"),
        (_MACOS_ARM, "Darwin", "darwin", "arm64"),
    ],
)
def test_target_operating_system_fields_follow_the_target_not_the_host(
    platform: str,
    expected_system: str,
    expected_sys_platform: str,
    expected_machine: str,
) -> None:
    environment = target_environment("3.14", platform, full_version="3.14.7")
    assert environment["platform_system"] == expected_system
    assert environment["sys_platform"] == expected_sys_platform
    assert environment["platform_machine"] == expected_machine


def test_darwin_target_is_not_internally_contradictory() -> None:
    """`sys_platform` and `platform_system` must describe the same operating system."""

    environment = target_environment("3.14", _MACOS_ARM, full_version="3.14.7")
    assert Marker('platform_system == "Darwin"').evaluate(environment=environment)
    assert not Marker('platform_system == "Linux"').evaluate(environment=environment)
    assert Marker('sys_platform == "darwin"').evaluate(environment=environment)


def test_patch_sensitive_markers_use_the_reviewed_full_version() -> None:
    environment = target_environment("3.12", _LINUX_X86, full_version="3.12.14")
    assert environment["python_full_version"] == "3.12.14"
    assert environment["implementation_version"] == "3.12.14"
    assert Marker('python_full_version >= "3.12.1"').evaluate(environment=environment)


def test_environment_is_independent_of_the_generator_host() -> None:
    """Every field is a reviewed constant, so the projection cannot vary by host.

    `os_name` is deliberately not asserted to differ from the host: every
    reviewed target is POSIX, so matching the host there is correct rather than
    inherited. Pinning the whole mapping is what proves independence.
    """

    assert target_environment("3.12", _MACOS_ARM, full_version="3.12.14") == {
        "implementation_name": "cpython",
        "implementation_version": "3.12.14",
        "os_name": "posix",
        "platform_machine": "arm64",
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_system": "Darwin",
        "platform_version": "",
        "python_full_version": "3.12.14",
        "python_version": "3.12",
        "sys_platform": "darwin",
    }


def test_kernel_fields_are_not_taken_from_the_generator_host() -> None:
    """A target has no reviewed running kernel, so these stay empty."""

    host = default_environment()
    environment = target_environment("3.14", _LINUX_X86, full_version="3.14.7")
    for field in ("platform_release", "platform_version"):
        assert environment[field] == ""
        assert environment[field] != host[field]


def test_unsupported_target_platform_is_refused() -> None:
    with pytest.raises(ValueError):
        target_environment("3.14", "riscv64-unknown-linux-gnu", full_version="3.14.7")


def test_full_version_must_belong_to_the_declared_minor_series() -> None:
    with pytest.raises(ValueError):
        target_environment("3.12", _LINUX_X86, full_version="3.13.15")


def test_patch_sensitive_selection_reaches_the_locked_closure() -> None:
    """The defect this fixes changed a shipped projection, so pin that outcome.

    `coverage` requires `tomli` under `python_full_version <= '3.11'`. Synthesizing
    the cp311 target as `3.11.0` satisfied that marker and pinned a `tomli` wheel
    into the reviewed offline wheelhouse, even though the reviewed 3.11.16 payload
    reports `3.11.16`, never selects it, and has `tomllib` in the standard library.
    """

    lock = tomllib.loads((REPO_ROOT / "implementations" / "python" / "uv.lock").read_text(encoding="utf-8"))
    selected = {
        str(package["name"])
        for package in locked_closure(
            lock,
            target_environment("3.11", _LINUX_X86, full_version=_reviewed_full_version("3.11")),
            root_name="raes",
            include_root_optional=True,
        )
    }
    assert "coverage" in selected, "guard: this case is meaningless if coverage stops being projected"
    assert "tomli" not in selected

    synthesized = {
        str(package["name"])
        for package in locked_closure(
            lock,
            target_environment("3.11", _LINUX_X86, full_version="3.11.0"),
            root_name="raes",
            include_root_optional=True,
        )
    }
    assert "tomli" in synthesized, "guard: the marker must still be patch-sensitive for this case to bite"


def test_every_reviewed_target_resolves_a_locked_full_version() -> None:
    """Each projected target names an interpreter the artifact lock actually pins."""

    for _profile_id, python_version, _abi, platform in TARGETS:
        full_version = _reviewed_full_version(python_version)
        assert full_version.startswith(f"{python_version}.")
        environment = target_environment(python_version, platform, full_version=full_version)
        assert environment["python_full_version"] == full_version
