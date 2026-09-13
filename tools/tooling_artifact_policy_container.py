"""Development container image definition policy.

The image configuration is a consumer of the reviewed development artifact
policy, never a second authority. Every base digest, package snapshot, package
selection, platform, and account below is joined from the container host
profile and the artifact lock; a literal in the Dockerfile that disagrees with
that join fails closed here, before any build or acquisition. The dev-container
entry point is checked by `tools.tooling_artifact_policy_devcontainer`.

The Dockerfile is a closed shape: only the reviewed instructions, environment
names, and builder-stage mounts are admitted, so an unanticipated build
argument, copied input, or host exposure is refused rather than overlooked.
This module owns the small fixed mapping from policy identifiers to container
directives; it never evaluates policy data as shell input and never acquires.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.policy.common import PolicyFailure
from tools.tooling_artifact_policy_common import (
    ARTIFACT_LOCK_PATH,
    PROFILES_PATH,
    as_list,
    as_mapping,
    failure,
    normalize_platform_id,
    safe_text,
    string_set,
)
from tools.tooling_artifact_policy_devcontainer import (
    DEVCONTAINER_CONFIG_PATH,
    devcontainer_failures,
    load_devcontainer_config,
)

CONTAINER_DOCKERFILE_PATH = ".devcontainer/Dockerfile"

RULE_PROFILE = "tooling-container-profile"
RULE_BASE = "tooling-container-base-drift"
RULE_SNAPSHOT = "tooling-container-snapshot-drift"
RULE_PACKAGES = "tooling-container-package-drift"
RULE_USER = "tooling-container-user"
RULE_BUILD = "tooling-container-unsafe-build"
RULE_PLATFORM = "tooling-container-platform"

# Transport trust a non-final stage may take from the base image's own signed
# archive. It only authenticates TLS to the snapshot; the final stage installs
# every package, including these, from the reviewed snapshot.
TRANSPORT_TRUST_PACKAGES = frozenset({"ca-certificates"})
_INSTRUCTIONS = frozenset({"FROM", "RUN", "ENV", "USER"})
_ENVIRONMENT_NAMES = frozenset(
    {
        "UV_CACHE_DIR",
        "XDG_CACHE_HOME",
        "UV_LINK_MODE",
        "UV_PYTHON_DOWNLOADS",
        "UV_PYTHON",
        "PATH",
        "EDITOR",
        "LANG",
        "LC_ALL",
    }
)
# uv must never download an interpreter the lock did not admit.
_REQUIRED_ENVIRONMENT = {"UV_PYTHON_DOWNLOADS": "never"}
# Canonical platform to the OCI platform every stage must pin. Linux x86_64 is the
# only platform with an immutable Ubuntu package snapshot to build from.
_OCI_PLATFORMS = {"linux-x86_64": "linux/amd64"}

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
# A RUN body is a `;`-separated list of plain commands. Any quoting, escaping,
# expansion, substitution, redirection, grouping, globbing, pipeline, or
# background job could hide an unreviewed command from this parser, so such
# syntax is refused outright rather than interpreted.
_SHELL_SYNTAX_RE = re.compile(r"[\\`'\"$<>(){}|&*?\[\]~#!]")
_APT_OPTION_RE = re.compile(r"^(?:APT::Snapshot=[0-9]{8}T[0-9]{6}Z|Acquire::https::CAInfo=/run/[a-z0-9.-]+)$")
_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]*$")
_SNAPSHOT_OPTION_RE = re.compile(r"^APT::Snapshot=(?P<snapshot>\S+)$")
_NAME_RE = r"[a-z_][a-z0-9_-]{0,31}"
_GROUPADD_RE = re.compile(rf"^--gid [0-9]+ {_NAME_RE}$")
_USERADD_RE = re.compile(rf"^--uid [0-9]+ --gid [0-9]+ --create-home --shell /bin/bash {_NAME_RE}$")
_INSTALL_RE = re.compile(rf"^-d -o (?P<owner>{_NAME_RE}) -g (?P=owner)(?: /home/(?P=owner)(?:/[a-z0-9._-]+)*)+$")


@dataclass
class _Stage:
    reference: str
    platform: str | None
    alias: str | None
    runs: list[tuple[list[str], str]] = field(default_factory=list)
    users: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Expected:
    reference: str
    snapshot: str
    packages: frozenset[str]
    user: str
    uid: int
    gid: int
    platform: str


def _image_failure(rule: str, message: str) -> PolicyFailure:
    return failure(rule, message, CONTAINER_DOCKERFILE_PATH)


def _instructions(text: str) -> list[tuple[str, str]]:
    """Return (keyword, arguments) pairs with comments dropped and continuations joined."""

    logical = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    logical = re.sub(r"\\\n\s*", " ", logical)
    parsed: list[tuple[str, str]] = []
    for line in logical.splitlines():
        keyword, _, arguments = line.strip().partition(" ")
        if keyword:
            parsed.append((keyword.upper(), arguments.strip()))
    return parsed


def _stages(instructions: Sequence[tuple[str, str]]) -> tuple[list[_Stage], list[PolicyFailure]]:
    stages: list[_Stage] = []
    failures: list[PolicyFailure] = []
    for keyword, arguments in instructions:
        if keyword not in _INSTRUCTIONS:
            failures.append(_image_failure(RULE_BUILD, f"image uses unreviewed instruction {keyword}"))
            continue
        if keyword == "FROM":
            tokens = arguments.split()
            platform = (
                tokens.pop(0).removeprefix("--platform=") if tokens and tokens[0].startswith("--platform=") else None
            )
            alias = tokens[2] if len(tokens) == 3 and tokens[1].upper() == "AS" else None
            stages.append(_Stage(tokens[0] if len(tokens) in {1, 3} else arguments, platform, alias))
        elif not stages:
            failures.append(_image_failure(RULE_BUILD, "image instruction precedes its base image"))
        elif keyword == "RUN":
            stages[-1].runs.append(_run_flags(arguments))
        elif keyword == "USER":
            stages[-1].users.append(arguments)
    return stages, failures


def _run_flags(arguments: str) -> tuple[list[str], str]:
    tokens = arguments.split(" ")
    flags = []
    while tokens and tokens[0].startswith("--"):
        flags.append(tokens.pop(0))
    return flags, " ".join(tokens).strip()


def _environment_failures(instructions: Sequence[tuple[str, str]]) -> list[PolicyFailure]:
    environment: dict[str, str] = {}
    well_formed = True
    for keyword, arguments in instructions:
        if keyword != "ENV":
            continue
        tokens = arguments.split()
        well_formed = well_formed and bool(tokens) and all("=" in token for token in tokens)
        environment.update(token.split("=", maxsplit=1) for token in tokens if "=" in token)
    failures = []
    if not well_formed or not set(environment) <= _ENVIRONMENT_NAMES:
        failures.append(_image_failure(RULE_BUILD, "image declares an unreviewed environment input"))
    if any(environment.get(name) != value for name, value in _REQUIRED_ENVIRONMENT.items()):
        failures.append(_image_failure(RULE_BUILD, "image must forbid uv from downloading unreviewed interpreters"))
    return failures


def _plain_commands(body: str) -> list[list[str]] | None:
    """Return a RUN body's commands as argv tokens, or None if it uses any other shell syntax."""

    text = " ".join(body.split())
    if _SHELL_SYNTAX_RE.search(text):
        return None
    return [segment.split() for segment in text.split(";") if segment.split()]


def _apt_arguments_admitted(arguments: Sequence[str]) -> bool:
    operation = ""
    iterator = iter(arguments)
    for argument in iterator:
        if argument == "-o":
            if _APT_OPTION_RE.fullmatch(next(iterator, "")) is None:
                return False
        elif argument in {"-y", "--no-install-recommends"}:
            continue
        elif not operation:
            if argument not in {"update", "install", "clean"}:
                return False
            operation = argument
        elif operation != "install" or _PACKAGE_RE.fullmatch(argument) is None:
            return False
    return bool(operation)


def _command_admitted(tokens: Sequence[str]) -> bool:
    """Admit only the reviewed command forms; everything else, including any acquisition, is refused."""

    executable, arguments = tokens[0], list(tokens[1:])
    joined = " ".join(arguments)
    forms = {
        "set": lambda: arguments == ["-eu"],
        "export": lambda: arguments == ["DEBIAN_FRONTEND=noninteractive"],
        "apt-get": lambda: _apt_arguments_admitted(arguments),
        "find": lambda: arguments == ["/var/lib/apt/lists", "-mindepth", "1", "-delete"],
        # The pinned base ships a stock account at the development uid.
        "userdel": lambda: arguments == ["--remove", "ubuntu"],
        "groupadd": lambda: _GROUPADD_RE.fullmatch(joined) is not None,
        "useradd": lambda: _USERADD_RE.fullmatch(joined) is not None,
        "install": lambda: _INSTALL_RE.fullmatch(joined) is not None,
    }
    form = forms.get(executable)
    return form is not None and form()


def _apt_options(tokens: Sequence[str]) -> tuple[str | None, str, set[str]]:
    """Return an apt command's snapshot option, its operation, and its package operands."""

    snapshot: str | None = None
    operation = ""
    packages: set[str] = set()
    iterator = iter(tokens[1:])
    for argument in iterator:
        if argument == "-o":
            option = next(iterator, "")
            if (match := _SNAPSHOT_OPTION_RE.fullmatch(option)) is not None:
                snapshot = match.group("snapshot")
        elif argument.startswith("-"):
            continue
        elif not operation:
            operation = argument
        else:
            packages.add(argument)
    return snapshot, operation, packages


def _stage_package_failures(stage: _Stage, expected: _Expected, *, final: bool) -> tuple[set[str], list[PolicyFailure]]:
    installed: set[str] = set()
    failures: list[PolicyFailure] = []
    for _flags, body in stage.runs:
        for tokens in _plain_commands(body) or []:
            if tokens[0] != "apt-get":
                continue
            snapshot, operation, packages = _apt_options(tokens)
            if operation == "clean":
                continue
            transport_bootstrap = not final and snapshot is None and packages <= TRANSPORT_TRUST_PACKAGES
            if snapshot != expected.snapshot and not transport_bootstrap:
                message = (
                    "image package source differs from the reviewed repository snapshot"
                    if snapshot is not None
                    else "image installs packages without the reviewed repository snapshot"
                )
                failures.append(_image_failure(RULE_SNAPSHOT, message))
            if not final and not packages <= TRANSPORT_TRUST_PACKAGES:
                failures.append(_image_failure(RULE_PACKAGES, "image builder stage installs an unreviewed package"))
            installed |= packages
    return installed, failures


def _base_failures(stages: Sequence[_Stage], expected: _Expected) -> list[PolicyFailure]:
    if not stages:
        return [_image_failure(RULE_BASE, "image definition declares no base image")]
    failures = [
        _image_failure(RULE_BASE, "image base reference is not the reviewed digest-pinned platform manifest")
        for stage in stages
        if stage.reference != expected.reference
    ]
    failures.extend(
        _image_failure(RULE_PLATFORM, "every image stage must pin the qualified container platform")
        for stage in stages
        if stage.platform != expected.platform
    )
    return failures


def _mount_failures(stages: Sequence[_Stage]) -> list[PolicyFailure]:
    """Admit only read-only bind mounts from an earlier builder stage."""

    failures: list[PolicyFailure] = []
    for index, stage in enumerate(stages):
        builders = {earlier.alias for earlier in stages[:index] if earlier.alias}
        for flags, _body in stage.runs:
            for flag in flags:
                name, _, value = flag.partition("=")
                options = dict(part.partition("=")[::2] for part in value.split(","))
                admitted = (
                    name == "--mount"
                    and options.get("type") == "bind"
                    and options.get("from") in builders
                    and options.get("target", "").startswith("/run/")
                    and set(options) <= {"type", "from", "source", "target"}
                )
                if not admitted:
                    failures.append(_image_failure(RULE_BUILD, "image build step requests an unreviewed capability"))
    return failures


def _command_failures(stages: Sequence[_Stage]) -> list[PolicyFailure]:
    failures: list[PolicyFailure] = []
    for stage in stages:
        for _flags, body in stage.runs:
            commands = _plain_commands(body)
            if commands is None or not commands or not all(_command_admitted(tokens) for tokens in commands):
                failures.append(
                    _image_failure(RULE_BUILD, "image build step runs a command outside the reviewed forms")
                )
    return failures


def _account_failures(stage: _Stage, expected: _Expected) -> list[PolicyFailure]:
    accounts: set[tuple[str, str, str]] = set()
    for _flags, body in stage.runs:
        for tokens in _plain_commands(body) or []:
            if tokens[0] not in {"useradd", "groupadd"}:
                continue
            # Each option is read from the token that follows it; the account
            # name is the final operand.
            options = dict(zip(tokens[1:-1], tokens[2:], strict=True))
            accounts.add((tokens[0], options.get("--uid", ""), f"{options.get('--gid', '')}:{tokens[-1]}"))
    expected_accounts = {
        ("groupadd", "", f"{expected.gid}:{expected.user}"),
        ("useradd", str(expected.uid), f"{expected.gid}:{expected.user}"),
    }
    if not stage.users or stage.users[-1] != expected.user or accounts != expected_accounts:
        return [_image_failure(RULE_USER, "image must end as the reviewed non-root development user")]
    return []


def _dockerfile_failures(text: str, expected: _Expected) -> list[PolicyFailure]:
    instructions = _instructions(text)
    stages, failures = _stages(instructions)
    failures.extend(_environment_failures(instructions))
    failures.extend(_base_failures(stages, expected))
    if not stages:
        return failures
    installed: set[str] = set()
    for index, stage in enumerate(stages):
        final = index == len(stages) - 1
        packages, package_failures = _stage_package_failures(stage, expected, final=final)
        failures.extend(package_failures)
        if final:
            installed = packages
    if installed != expected.packages:
        failures.append(
            _image_failure(RULE_PACKAGES, "image native package selection differs from the reviewed container profiles")
        )
    failures.extend(_mount_failures(stages))
    failures.extend(_command_failures(stages))
    failures.extend(_account_failures(stages[-1], expected))
    return failures


def _container_host_profiles(documents: Mapping[str, dict[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        host
        for host in as_list((documents.get(PROFILES_PATH) or {}).get("host_profiles"))
        if isinstance(host, Mapping) and isinstance(host.get("base_image_artifact_ref"), str)
    ]


def _expected(documents: Mapping[str, dict[str, Any]], host: Mapping[str, Any]) -> _Expected | None:
    """Join the container host profile to its locked platform manifest, or return None."""

    platform_id = normalize_platform_id(str(host.get("platform_id", "")))
    user = as_mapping(host.get("development_user"))
    for artifact_value in as_list((documents.get(ARTIFACT_LOCK_PATH) or {}).get("artifacts")):
        artifact = as_mapping(artifact_value)
        if (
            artifact.get("artifact_id") != host["base_image_artifact_ref"]
            or artifact.get("artifact_class") != "oci-image"
        ):
            continue
        repository = as_mapping(artifact.get("source")).get("asset")
        manifests = [
            as_mapping(entry)
            for value in as_list(artifact.get("platforms"))
            if normalize_platform_id(str((platform := as_mapping(value)).get("platform_id", ""))) == platform_id
            for entry in as_list(platform.get("raw_manifest"))
        ]
        digest = manifests[0].get("sha256") if len(manifests) == 1 else None
        admitted = (
            isinstance(repository, str)
            and isinstance(digest, str)
            and _DIGEST_RE.fullmatch(digest) is not None
            # The human-readable identity must name the same locked repository.
            and str(host.get("base_image_identity", "")).startswith(f"{repository}:")
            and isinstance(host.get("native_repository_snapshot"), str)
            and isinstance(user.get("name"), str)
            and all(isinstance(user.get(key), int) for key in ("uid", "gid"))
            and platform_id in _OCI_PLATFORMS
        )
        if admitted:
            packages = string_set(as_mapping(host.get("offline_kit")).get("host_prerequisite_package_ids")) | (
                string_set(host.get("development_package_ids"))
            )
            return _Expected(
                reference=f"{repository}@sha256:{digest}",
                snapshot=str(host["native_repository_snapshot"]),
                packages=frozenset(packages),
                user=str(user["name"]),
                uid=int(user["uid"]),
                gid=int(user["gid"]),
                platform=_OCI_PLATFORMS[platform_id],
            )
    return None


def container_failures(
    repo_root: Path,
    documents: Mapping[str, dict[str, Any]],
    tracked_paths: Sequence[str] | None = None,
) -> list[PolicyFailure]:
    """Return deterministic container-configuration failures without building."""

    del tracked_paths  # The container artifacts are at fixed reviewed paths.
    hosts = _container_host_profiles(documents)
    dockerfile = safe_text(repo_root, CONTAINER_DOCKERFILE_PATH)
    present = dockerfile is not None or (repo_root / DEVCONTAINER_CONFIG_PATH).exists()
    if not hosts:
        return [_image_failure(RULE_PROFILE, "container configuration has no reviewed host profile")] if present else []
    expected = _expected(documents, hosts[0]) if len(hosts) == 1 else None
    if expected is None:
        return [
            failure(
                RULE_PROFILE,
                "exactly one container host profile must bind a qualified platform manifest in the lock, "
                "a package snapshot, and a development user",
                PROFILES_PATH,
            )
        ]
    if dockerfile is None:
        return [_image_failure(RULE_PROFILE, "the reviewed container host profile has no image definition")]
    failures = _dockerfile_failures(dockerfile, expected)
    document, config_failure = load_devcontainer_config(repo_root)
    if document is None:
        failures.append(config_failure or failure(RULE_PROFILE, "dev-container configuration is unavailable"))
        return failures
    failures.extend(devcontainer_failures(document, expected.user))
    return failures
