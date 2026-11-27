"""Issue #847: typed, pinned third-party runtime package repositories."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes import SDLInstantiationError, SDLParseError, instantiate_scenario, parse_sdl
from raes.nodes import RuntimeAptPackageRepository as NodeRuntimeAptPackageRepository
from raes.runtime_configuration import RuntimeAptPackageRepository, RuntimeConfiguration, RuntimePackage
from raes_processor.compiler import compile_runtime_model
from raes_processor.semantics.realization_concerns import project_realization_concern
from raes_schemas import schema_bundle

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "fixtures" / "sdl" / "runtime-package-repository-v1"
SCHEMA_PATHS = (
    REPO_ROOT / "contracts" / "schemas" / "sdl" / "sdl-authoring-input-v1.json",
    REPO_ROOT / "contracts" / "schemas" / "sdl" / "instantiated-scenario-v1.json",
    REPO_ROOT / "contracts" / "schemas" / "sdl" / "instantiated-scenario-snapshot-v1.json",
    REPO_ROOT / "contracts" / "schemas" / "satisfiability" / "scenario-satisfiability-evidence-v1.json",
)
KEY_DIGEST = "sha256:" + "a" * 64


def _repository(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "repository_profile": "apt",
        "profile_version": "1",
        "uri": "https://packages.wazuh.com/4.x/apt/",
        "suite": "stable",
        "components": ["main"],
        "signing_key": {
            "uri": "https://packages.wazuh.com/key/GPG-KEY-WAZUH",
            "format": "openpgp-ascii-armored",
            "digest": KEY_DIGEST,
        },
    }
    value.update(overrides)
    return value


def _package(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "manager": "apt",
        "name": "wazuh-agent",
        "version": "4.12.0-1",
        "repository": _repository(),
    }
    value.update(overrides)
    return value


def test_repository_profile_round_trips_through_parser_compiler_and_projection() -> None:
    source = (FIXTURE_ROOT / "valid" / "wazuh.yaml").read_text(encoding="utf-8")

    scenario = parse_sdl(source)
    package = scenario.nodes["manager"].runtime.packages[0]
    compiled = compile_runtime_model(scenario)
    compiled_package = compiled.node_deployments["provision.node.manager"].spec["node"]["runtime"]["packages"][0]
    projected = project_realization_concern("runtime-packages", [compiled_package])

    assert package.repository.repository_profile == "apt"
    assert package.repository.profile_version == "1"
    assert package.repository.signing_key.digest == KEY_DIGEST
    assert compiled_package["repository"] == package.repository.model_dump(mode="json")
    assert projected[0]["repository"]["components"] == ["main"]
    assert NodeRuntimeAptPackageRepository is RuntimeAptPackageRepository


def test_repository_components_are_canonical_set_like_values() -> None:
    package = RuntimePackage.model_validate(
        _package(repository=_repository(components=["non-free", "main", "contrib"]))
    )

    assert package.repository.components == ["contrib", "main", "non-free"]
    projected = project_realization_concern("runtime-packages", [package.model_dump(mode="json")])
    assert projected[0]["repository"]["components"] == ["contrib", "main", "non-free"]


@pytest.mark.parametrize(
    ("repository", "message"),
    (
        (_repository(uri="http://packages.example.test/apt"), "repository uri must use HTTPS"),
        (_repository(uri="https://user:password@example.test/apt"), "credential userinfo"),
        (_repository(uri="https://example.test/apt#stable"), "must not contain a fragment"),
        (
            _repository(
                signing_key={
                    "uri": "https://example.test/key?access_token=secret",
                    "format": "openpgp-binary",
                    "digest": KEY_DIGEST,
                }
            ),
            "secret-bearing query fields",
        ),
        (
            _repository(
                signing_key={
                    "uri": "http://example.test/key",
                    "format": "openpgp-binary",
                    "digest": KEY_DIGEST,
                }
            ),
            "signing key uri must use HTTPS",
        ),
        (
            _repository(
                signing_key={
                    "uri": "https://example.test/key",
                    "format": "pem",
                    "digest": KEY_DIGEST,
                }
            ),
            "format",
        ),
        (
            _repository(
                signing_key={
                    "uri": "https://example.test/key",
                    "format": "openpgp-binary",
                    "digest": "sha256:" + "A" * 64,
                }
            ),
            "digest",
        ),
        (_repository(suite="stable main"), "suite must be a bounded APT token"),
        (_repository(components=[]), "components must contain at least one APT component"),
        (_repository(components=["main", "main"]), "components must not contain duplicates"),
        (_repository(components=["main;deb"]), "component must be a bounded APT token"),
        (_repository(options={"trusted": "yes"}), "Extra inputs are not permitted"),
    ),
)
def test_repository_profile_rejects_unsafe_or_ambiguous_input(repository: dict[str, object], message: str) -> None:
    package = _package(repository=repository)

    with pytest.raises(ValidationError, match=message):
        RuntimePackage.model_validate(package)


@pytest.mark.parametrize(
    ("package", "message"),
    (
        (_package(manager="dnf"), "manager 'apt'"),
        (_package(name="-oDebug::pkgProblemResolver=yes"), "package name must be a bounded APT token"),
        (_package(version="4.12.0-1\nmalformed"), "package version must be a bounded APT token"),
    ),
)
def test_repository_bearing_package_rejects_manager_mismatch_and_option_like_tokens(
    package: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        RuntimePackage.model_validate(package)


def test_default_repository_packages_keep_backward_compatible_opaque_metadata() -> None:
    package = RuntimePackage(
        manager="vendor manager",
        name="legacy package",
        version="version selected downstream",
        source="opaque provenance; never executable",
        purl="pkg:generic/legacy",
    )

    assert package.repository is None
    assert package.source == "opaque provenance; never executable"
    assert package.purl == "pkg:generic/legacy"


def test_runtime_configuration_rejects_duplicate_package_identity() -> None:
    runtime = {
        "packages": [
            _package(version="4.12.0-1"),
            _package(version="4.13.0-1", repository=_repository(uri="https://packages.example.test/apt")),
        ]
    }

    with pytest.raises(ValidationError, match="Duplicate runtime package identity 'apt:wazuh-agent:'"):
        RuntimeConfiguration.model_validate(runtime)


def test_runtime_configuration_allows_same_package_name_for_distinct_identity_dimensions() -> None:
    runtime = RuntimeConfiguration.model_validate(
        {
            "packages": [
                {"manager": "apt", "name": "agent", "version": "1", "architecture": "amd64"},
                {"manager": "apt", "name": "agent", "version": "1", "architecture": "arm64"},
                {"manager": "apk", "name": "agent", "version": "1", "architecture": "amd64"},
            ]
        }
    )

    assert len(runtime.packages) == 3


def test_instantiation_revalidates_bound_repository_values_without_echoing_them() -> None:
    scenario = parse_sdl(
        f"""
name: variable-repository
variables:
  repository_uri:
    type: string
    default: https://packages.example.test/apt
nodes:
  worker:
    type: compute
    resources: {{ram: 1 gib, cpu: 1}}
    runtime:
      packages:
        - manager: apt
          name: agent
          version: "1"
          repository:
            repository_profile: apt
            profile_version: "1"
            uri: ${{repository_uri}}
            suite: stable
            components: [main]
            signing_key:
              uri: https://packages.example.test/key
              format: openpgp-binary
              digest: {KEY_DIGEST}
"""
    )
    unsafe_value = "http://user:password@example.test/apt"

    with pytest.raises(SDLInstantiationError, match="Bound scenario is invalid") as caught:
        instantiate_scenario(scenario, {"repository_uri": unsafe_value})

    assert unsafe_value not in str(caught.value)


def test_live_and_published_schemas_expose_the_same_closed_repository_contract() -> None:
    live = schema_bundle()["sdl-authoring-input-v1"]
    live_repository = live["$defs"]["RuntimePackage"]["properties"]["repository"]

    assert "RuntimeAptPackageRepository" in json.dumps(live_repository)
    for schema_path in SCHEMA_PATHS:
        published = json.loads(schema_path.read_text(encoding="utf-8"))
        package_schema = published["$defs"]["RuntimePackage"]
        repository_schema = package_schema["properties"]["repository"]
        assert repository_schema == live_repository
        assert package_schema["properties"]["source"]["description"].startswith("Opaque")
        Draft202012Validator(published).check_schema(published)


@pytest.mark.parametrize(
    ("target", "unsafe_uri"),
    (
        ("repository", "http://packages.example.test/apt"),
        ("repository", "https://user:password@example.test/apt"),
        ("repository", "https://packages.example.test/apt#stable"),
        ("signing_key", "https://keys.example.test/vendor?access_token=secret"),
    ),
)
def test_live_schema_rejects_unsafe_repository_uris(target: str, unsafe_uri: str) -> None:
    scenario = parse_sdl((FIXTURE_ROOT / "valid" / "wazuh.yaml").read_text(encoding="utf-8"))
    payload = scenario.model_dump(mode="json", by_alias=True)
    repository = payload["nodes"]["manager"]["runtime"]["packages"][0]["repository"]
    if target == "repository":
        repository["uri"] = unsafe_uri
    else:
        repository["signing_key"]["uri"] = unsafe_uri

    assert not Draft202012Validator(schema_bundle()["sdl-authoring-input-v1"]).is_valid(payload)


def test_invalid_unpinned_key_fixture_fails_at_the_typed_contract_boundary() -> None:
    source = (FIXTURE_ROOT / "invalid" / "unpinned-key.yaml").read_text(encoding="utf-8")

    with pytest.raises(SDLParseError, match="digest"):
        parse_sdl(source)
