"""Generated-artifact output consumed as a node environment value / env_file (issue #1074).

Covers the DSL-435 extension that lets a node's runtime environment source a
value from a generated-artifact output instead of a raw literal, across the SDL
model, semantic admission, compilation, and provisioner-capability layers.
"""

from __future__ import annotations

import textwrap
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from raes import SDLParseError, SDLValidationError, parse_sdl, parse_sdl_file
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.apparatus import RealizationObservationCapability
from raes_contracts.vocabulary import (
    GeneratedArtifactDeliveryMode,
    ObservationStrength,
    RealizationVerificationScope,
)
from raes_processor.compiler import compile_runtime_model
from raes_processor.planner import plan
from raes_processor.semantics.realization import project_realization_concern
from raes_schemas import schema_bundle

_DEFAULT_ARTIFACTS = """
cortex-api-key:
  generator: rendered_config
  lifecycle: reuse_valid
  provenance: bootstrap/cortex-api-key.yml
  outputs:
    - {name: api-key, path: api-key.env, sensitivity: secret}
"""


def _block(body: str, indent: int) -> str:
    return textwrap.indent(textwrap.dedent(body).strip("\n"), " " * indent)


def _scenario(*, environment: str = "", environment_files: str = "", artifacts: str = "") -> str:
    runtime = ""
    if environment:
        runtime += "      environment:\n" + _block(environment, 8) + "\n"
    if environment_files:
        runtime += "      environment_files:\n" + _block(environment_files, 8) + "\n"
    runtime_section = "    runtime:\n" + runtime if runtime else ""
    return (
        "name: env-consumer\n"
        "nodes:\n"
        "  cortex: {type: compute}\n"
        "  thehive:\n"
        "    type: compute\n"
        + runtime_section
        + "generated_artifacts:\n"
        + _block(artifacts or _DEFAULT_ARTIFACTS, 2)
        + "\n"
    )


_ENV_SCALAR = """
- name: CORTEX_API_KEY
  value_from: {generated_artifact: cortex-api-key, output: api-key}
  value_classification: redacted
  provenance: runtime
"""


def _environment_capable_manifest():
    manifest = create_stub_manifest()
    declaration = manifest.realization_support[0]
    return replace(
        manifest,
        realization_support=(
            replace(
                declaration,
                supported_exact_requirement_kinds=(
                    declaration.supported_exact_requirement_kinds | {"runtime-environment"}
                ),
                observation_capabilities={
                    **declaration.observation_capabilities,
                    "runtime-environment": RealizationObservationCapability(
                        verification_scope=RealizationVerificationScope.CONFIGURATION,
                        observation_strength=ObservationStrength.GUEST_OBSERVED,
                    ),
                },
            ),
        ),
    )


# --- model / parse layer -----------------------------------------------------


def test_env_var_sources_generated_artifact_output_parses():
    scenario = parse_sdl(_scenario(environment=_ENV_SCALAR))
    env = scenario.nodes["thehive"].runtime.environment[0]
    assert env.name == "CORTEX_API_KEY"
    assert env.value == ""
    assert env.value_from is not None
    assert env.value_from.generated_artifact == "cortex-api-key"
    assert env.value_from.output == "api-key"


def test_env_var_rejects_literal_value_with_value_from():
    conflicting = """
    - name: CORTEX_API_KEY
      value: leaked-literal
      value_from: {generated_artifact: cortex-api-key, output: api-key}
    """
    document = _scenario(environment=conflicting)
    with pytest.raises(SDLParseError, match="value_from"):
        parse_sdl(document)


def test_env_var_value_from_rejects_operator_secret_classification():
    reserved = """
    - name: CORTEX_API_KEY
      value_from: {generated_artifact: cortex-api-key, output: api-key}
      value_classification: operator_secret
    """
    document = _scenario(environment=reserved)
    with pytest.raises(SDLParseError, match="operator_secret"):
        parse_sdl(document)


@pytest.mark.parametrize("classification", ["plain", "unknown", "other", "secret_fixture"])
def test_secret_generated_output_requires_redacted_environment_classification(classification: str):
    downgraded = f"""
    - name: CORTEX_API_KEY
      value_from: {{generated_artifact: cortex-api-key, output: api-key}}
      value_classification: {classification}
    """
    document = _scenario(environment=downgraded)
    with pytest.raises(SDLValidationError, match="redacted"):
        parse_sdl(document)


def test_environment_file_sources_generated_artifact_output_parses():
    artifacts = """
    thehive-keystore:
      generator: rendered_config
      lifecycle: reuse_valid
      provenance: bootstrap/thehive-keystore.yml
      outputs:
        - {name: env, path: keystore.env, sensitivity: secret}
    """
    env_files = """
    - name: thehive-keystore
      value_from: {generated_artifact: thehive-keystore, output: env}
    """
    scenario = parse_sdl(_scenario(environment_files=env_files, artifacts=artifacts))
    env_file = scenario.nodes["thehive"].runtime.environment_files[0]
    assert env_file.name == "thehive-keystore"
    assert env_file.value_from.generated_artifact == "thehive-keystore"
    assert env_file.value_from.output == "env"


def test_generated_artifact_consumed_only_via_environment_needs_no_file_consumer():
    # cortex-api-key declares no `consumers` block; the env var is its only consumer.
    scenario = parse_sdl(_scenario(environment=_ENV_SCALAR))
    assert scenario.generated_artifacts["cortex-api-key"].consumers == []


# --- semantic admission ------------------------------------------------------


def test_env_value_from_unknown_artifact_is_rejected():
    unknown = """
    - name: CORTEX_API_KEY
      value_from: {generated_artifact: does-not-exist, output: api-key}
    """
    document = _scenario(environment=unknown)
    with pytest.raises(SDLValidationError, match="does-not-exist"):
        parse_sdl(document)


def test_env_value_from_unknown_output_is_rejected():
    unknown_output = """
    - name: CORTEX_API_KEY
      value_from: {generated_artifact: cortex-api-key, output: missing-output}
    """
    document = _scenario(environment=unknown_output)
    with pytest.raises(SDLValidationError, match="missing-output"):
        parse_sdl(document)


def test_env_value_from_producer_private_output_is_rejected():
    artifacts = """
    cortex-api-key:
      generator: rendered_config
      lifecycle: reuse_valid
      provenance: bootstrap/cortex-api-key.yml
      outputs:
        - {name: api-key, path: api-key.env, sensitivity: secret, disposition: producer_private}
    """
    document = _scenario(environment=_ENV_SCALAR, artifacts=artifacts)
    with pytest.raises(SDLValidationError, match="producer_private|producer-private"):
        parse_sdl(document)


def test_generated_artifact_with_no_consumer_at_all_is_rejected():
    orphan = """
    orphan-config:
      generator: rendered_config
      lifecycle: reuse_valid
      provenance: bootstrap/orphan.yml
      outputs:
        - {name: conf, path: orphan.conf, sensitivity: restricted}
    """
    document = _scenario(artifacts=orphan)
    with pytest.raises(SDLValidationError, match="orphan-config"):
        parse_sdl(document)


# --- compilation -------------------------------------------------------------


def test_env_value_from_compiles_derived_environment_consumer_projection():
    model = compile_runtime_model(parse_sdl(_scenario(environment=_ENV_SCALAR)))
    artifact = model.generated_artifacts["provision.generated-artifact.cortex-api-key"]
    projections = artifact.spec["environment_consumers"]
    assert len(projections) == 1
    projection = projections[0]
    assert projection["delivery_mode"] == GeneratedArtifactDeliveryMode.ENVIRONMENT.value
    assert projection["output"] == "api-key"
    assert projection["environment_variable"] == "CORTEX_API_KEY"
    assert projection["target_address"] == "provision.node.thehive"


def test_environment_file_compiles_derived_env_file_consumer_projection():
    artifacts = """
    thehive-keystore:
      generator: rendered_config
      lifecycle: reuse_valid
      provenance: bootstrap/thehive-keystore.yml
      outputs:
        - {name: env, path: keystore.env, sensitivity: secret}
    """
    env_files = """
    - name: thehive-keystore
      value_from: {generated_artifact: thehive-keystore, output: env}
    """
    model = compile_runtime_model(parse_sdl(_scenario(environment_files=env_files, artifacts=artifacts)))
    artifact = model.generated_artifacts["provision.generated-artifact.thehive-keystore"]
    projection = artifact.spec["environment_consumers"][0]
    assert projection["delivery_mode"] == GeneratedArtifactDeliveryMode.ENV_FILE.value
    assert projection["output"] == "env"
    assert projection["environment_file"] == "thehive-keystore"
    assert projection["target_address"] == "provision.node.thehive"


def test_composed_environment_consumer_admits_namespaced_node(tmp_path: Path):
    module = tmp_path / "generated-env.yaml"
    module.write_text(
        textwrap.dedent(
            """
            name: generated-env
            version: 1.0.0
            module:
              id: acme/generated-env
              version: 1.0.0
              exports:
                nodes: [consumer]
                generated_artifacts: [api-key]
            nodes:
              consumer:
                type: compute
                runtime:
                  environment:
                    - name: API_KEY
                      value_from: {generated_artifact: api-key, output: key}
                      value_classification: redacted
            generated_artifacts:
              api-key:
                generator: rendered_config
                lifecycle: reuse_valid
                provenance: bootstrap/api-key.yml
                outputs: [{name: key, path: key.env, sensitivity: secret}]
            """
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root.yaml"
    root.write_text(
        textwrap.dedent(
            """
            name: root
            imports:
              - source: local:generated-env.yaml
                namespace: shared
                version: 1.0.0
            """
        ),
        encoding="utf-8",
    )

    execution = plan(compile_runtime_model(parse_sdl_file(root)), _environment_capable_manifest())

    assert execution.is_valid, [diagnostic.message for diagnostic in execution.diagnostics]
    artifact = execution.model.generated_artifacts["provision.generated-artifact.shared.api-key"]
    assert artifact.spec["environment_consumers"][0]["target_address"] == "provision.node.shared.consumer"


# --- capability gating -------------------------------------------------------


def test_backend_without_environment_delivery_mode_rejects_binding():
    scenario = parse_sdl(_scenario(environment=_ENV_SCALAR))
    manifest = _environment_capable_manifest()
    mount_only = replace(
        manifest,
        capabilities=replace(
            manifest.capabilities,
            provisioner=replace(
                manifest.provisioner,
                supported_generated_artifact_delivery_modes=frozenset({GeneratedArtifactDeliveryMode.MOUNT}),
            ),
        ),
    )
    execution = plan(compile_runtime_model(scenario), mount_only)
    assert "provisioner.unsupported-generated-artifact-delivery-mode" in {
        diagnostic.code for diagnostic in execution.diagnostics
    }


def test_backend_with_environment_delivery_mode_admits_binding():
    scenario = parse_sdl(_scenario(environment=_ENV_SCALAR))
    execution = plan(compile_runtime_model(scenario), _environment_capable_manifest())
    assert execution.is_valid, [d.code for d in execution.diagnostics]


# --- published schema --------------------------------------------------------


def test_runtime_environment_projection_pins_value_from_without_raw_bytes():
    projected = project_realization_concern(
        "runtime-environment",
        [
            {
                "name": "CORTEX_API_KEY",
                "value_classification": "redacted",
                "provenance": "runtime",
                "value_from": {"generated_artifact": "cortex-api-key", "output": "api-key"},
            }
        ],
    )
    entry = projected[0]
    assert entry["value_from"] == {"generated_artifact": "cortex-api-key", "output": "api-key"}
    # A generated secret is known to be present, but the comparison surface
    # carries neither raw material nor a commitment derived from raw material.
    assert entry["value_present"] is True
    assert "value" not in entry
    assert "value_commitment" not in entry


def test_observed_value_from_rejects_and_does_not_echo_unknown_fields():
    leaked_value = "generated-secret-material"
    with pytest.raises(ValueError, match="runtime environment observation violates its closed contract") as exc_info:
        project_realization_concern(
            "runtime-environment",
            [
                {
                    "name": "CORTEX_API_KEY",
                    "value_classification": "redacted",
                    "value_from": {
                        "generated_artifact": "cortex-api-key",
                        "output": "api-key",
                        "raw_value": leaked_value,
                    },
                }
            ],
            observed=True,
        )
    assert leaked_value not in str(exc_info.value)


# --- published schema --------------------------------------------------------


def _env_var_schema_validator() -> Draft202012Validator:
    schema = schema_bundle()["sdl-authoring-input-v1"]
    assert "GeneratedArtifactValueSource" in schema["$defs"]
    assert "environment_files" in schema["$defs"]["RuntimeConfiguration"]["properties"]
    return Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/RuntimeEnvironmentVariable"})


def test_published_schema_accepts_env_value_from():
    validator = _env_var_schema_validator()
    validator.validate(
        {"name": "CORTEX_API_KEY", "value_from": {"generated_artifact": "cortex-api-key", "output": "api-key"}}
    )


def test_published_schema_rejects_value_and_value_from_together():
    # The published contract, not just the Python model, must reject the conflict.
    validator = _env_var_schema_validator()
    assert not validator.is_valid(
        {
            "name": "CORTEX_API_KEY",
            "value": "leaked-literal",
            "value_from": {"generated_artifact": "cortex-api-key", "output": "api-key"},
        }
    )


def test_published_schema_rejects_value_from_with_operator_secret():
    validator = _env_var_schema_validator()
    assert not validator.is_valid(
        {
            "name": "CORTEX_API_KEY",
            "value_from": {"generated_artifact": "cortex-api-key", "output": "api-key"},
            "value_classification": "operator_secret",
        }
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "LITERAL", "value": "literal", "value_from": None},
        {"name": "OPERATOR", "value_classification": "operator_secret", "value_from": None},
    ],
)
def test_published_schema_accepts_explicit_null_value_from(payload: dict[str, object]):
    _env_var_schema_validator().validate(payload)


# --- admission hardening -----------------------------------------------------


def test_admission_rejects_malformed_environment_consumers():
    from raes_processor.planner.stateful_admission import generated_artifact_payload_diagnostic

    provisioner = create_stub_manifest().provisioner
    base_spec = {
        "generator": "rendered_config",
        "lifecycle": "reuse_valid",
        "provenance": "bootstrap/x.yml",
        "outputs": [{"name": "api-key", "path": "api-key.env", "sensitivity": "secret"}],
        "consumers": [],
    }
    # Non-list environment_consumers must be rejected, not silently ignored.
    non_list = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={**base_spec, "environment_consumers": {"delivery_mode": "environment"}},
        provisioner=provisioner,
    )
    assert non_list is not None
    assert non_list.code == "provisioner.generated-artifact-invalid"
    # A projection missing its mode-specific target must be rejected.
    missing_target = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={
            **base_spec,
            "environment_consumers": [
                {
                    "node": "thehive",
                    "target_address": "provision.node.thehive",
                    "delivery_mode": "environment",
                    "output": "api-key",
                }
            ],
        },
        provisioner=provisioner,
    )
    assert missing_target is not None
    assert missing_target.code == "provisioner.generated-artifact-invalid"
    # Compiler-derived projections are a closed contract: the opposite mode's
    # target (or any other undeclared key) must not cross the backend boundary.
    unexpected_target = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={
            **base_spec,
            "environment_consumers": [
                {
                    "node": "thehive",
                    "target_address": "provision.node.thehive",
                    "delivery_mode": "environment",
                    "output": "api-key",
                    "environment_variable": "CORTEX_API_KEY",
                    "environment_file": "smuggled-env-file",
                }
            ],
        },
        provisioner=provisioner,
    )
    assert unexpected_target is not None
    assert unexpected_target.code == "provisioner.generated-artifact-invalid"
    null_address = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={
            **base_spec,
            "environment_consumers": [
                {
                    "node": "thehive",
                    "target_address": None,
                    "delivery_mode": "environment",
                    "output": "api-key",
                    "environment_variable": "CORTEX_API_KEY",
                }
            ],
        },
        provisioner=provisioner,
    )
    assert null_address is not None
    assert null_address.code == "provisioner.generated-artifact-invalid"
    assignment_target = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={
            **base_spec,
            "environment_consumers": [
                {
                    "node": "thehive",
                    "target_address": "provision.node.thehive",
                    "delivery_mode": "environment",
                    "output": "api-key",
                    "environment_variable": "CORTEX_API_KEY=smuggled",
                }
            ],
        },
        provisioner=provisioner,
    )
    assert assignment_target is not None
    assert assignment_target.code == "provisioner.generated-artifact-invalid"
    mount_projection = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={
            **base_spec,
            "environment_consumers": [
                {
                    "node": "thehive",
                    "target_address": "provision.node.thehive",
                    "delivery_mode": "mount",
                    "output": "api-key",
                    "environment_variable": "CORTEX_API_KEY",
                }
            ],
        },
        provisioner=provisioner,
    )
    assert mount_projection is not None
    assert mount_projection.code == "provisioner.generated-artifact-invalid"


def test_admission_rejects_contradictory_mount_delivery_mode():
    from raes_processor.planner.stateful_admission import generated_artifact_payload_diagnostic

    diagnostic = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={
            "generator": "rendered_config",
            "lifecycle": "reuse_valid",
            "provenance": "bootstrap/x.yml",
            "outputs": [{"name": "api-key", "path": "api-key.env", "sensitivity": "secret"}],
            "consumers": [
                {
                    "node": "thehive",
                    "target_address": "provision.node.thehive",
                    "delivery_mode": "environment",
                    "mount_destination": "/run/raes/api-key.env",
                    "access_mode": "read_only",
                    "selected_outputs": ["api-key"],
                }
            ],
        },
        provisioner=create_stub_manifest().provisioner,
    )
    assert diagnostic is not None
    assert diagnostic.code == "provisioner.generated-artifact-invalid"


@pytest.mark.parametrize(
    "output",
    [
        "missing-output",
        "producer-only",
    ],
)
def test_direct_admission_authorizes_environment_consumer_output(output: str):
    from raes_processor.planner.stateful_admission import generated_artifact_payload_diagnostic

    diagnostic = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={
            "generator": "rendered_config",
            "lifecycle": "reuse_valid",
            "provenance": "bootstrap/x.yml",
            "outputs": [
                {"name": "api-key", "path": "api-key.env", "sensitivity": "secret"},
                {
                    "name": "producer-only",
                    "path": "producer.env",
                    "sensitivity": "secret",
                    "disposition": "producer_private",
                },
            ],
            "consumers": [],
            "environment_consumers": [
                {
                    "node": "thehive",
                    "target_address": "provision.node.thehive",
                    "delivery_mode": "environment",
                    "output": output,
                    "environment_variable": "CORTEX_API_KEY",
                }
            ],
        },
        provisioner=create_stub_manifest().provisioner,
    )
    assert diagnostic is not None
    assert diagnostic.code == "provisioner.generated-artifact-invalid"


def test_direct_admission_requires_a_consumer():
    from raes_processor.planner.stateful_admission import generated_artifact_payload_diagnostic

    diagnostic = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={
            "generator": "rendered_config",
            "lifecycle": "reuse_valid",
            "provenance": "bootstrap/x.yml",
            "outputs": [{"name": "api-key", "path": "api-key.env", "sensitivity": "secret"}],
            "consumers": [],
        },
        provisioner=create_stub_manifest().provisioner,
    )
    assert diagnostic is not None
    assert diagnostic.code == "provisioner.generated-artifact-invalid"


@pytest.mark.parametrize("classification", [None, "plain", "unknown"])
def test_direct_admission_requires_matching_redacted_node_binding(classification: str | None):
    from raes_processor.planner.stateful_admission import generated_artifact_payload_diagnostic

    node_specs: dict[str, object] = {}
    if classification is not None:
        node_specs["provision.node.thehive"] = {
            "node": {
                "runtime": {
                    "environment": [
                        {
                            "name": "CORTEX_API_KEY",
                            "value_from": {"generated_artifact": "x", "output": "api-key"},
                            "value_classification": classification,
                        }
                    ]
                }
            }
        }
    diagnostic = generated_artifact_payload_diagnostic(
        address="provision.generated-artifact.x",
        spec={
            "generator": "rendered_config",
            "lifecycle": "reuse_valid",
            "provenance": "bootstrap/x.yml",
            "outputs": [{"name": "api-key", "path": "api-key.env", "sensitivity": "secret"}],
            "consumers": [],
            "environment_consumers": [
                {
                    "node": "thehive",
                    "target_address": "provision.node.thehive",
                    "delivery_mode": "environment",
                    "output": "api-key",
                    "environment_variable": "CORTEX_API_KEY",
                }
            ],
        },
        provisioner=create_stub_manifest().provisioner,
        node_specs=node_specs,
    )
    assert diagnostic is not None
    assert diagnostic.code == "provisioner.generated-artifact-invalid"


# --- env-file target hardening ----------------------------------------------


@pytest.mark.parametrize("bad_name", ["../evil", "/etc/passwd", "name with spaces", "line\nbreak", "UPPER"])
def test_environment_file_name_rejects_path_like_targets(bad_name: str):
    artifacts = """
    thehive-keystore:
      generator: rendered_config
      lifecycle: reuse_valid
      provenance: bootstrap/thehive-keystore.yml
      outputs:
        - {name: env, path: keystore.env, sensitivity: secret}
    """
    env_files = f"""
    - name: {bad_name!r}
      value_from: {{generated_artifact: thehive-keystore, output: env}}
    """
    document = _scenario(environment_files=env_files, artifacts=artifacts)
    with pytest.raises(SDLParseError):
        parse_sdl(document)
