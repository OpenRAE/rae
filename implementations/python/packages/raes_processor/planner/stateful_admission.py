"""Shared admission for generated-artifact plan payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import TypeAdapter
from raes.identifiers import PortableIdentifier
from raes.runtime_configuration import RuntimeConfiguration
from raes.runtime_generated_value import GeneratedArtifactValueSource, resolve_consumable_generated_artifact_output
from raes.stateful_resources import GeneratedArtifact
from raes_backend_protocols.capabilities import ProvisionerCapabilities
from raes_contracts.addressing import render_compiled_address
from raes_contracts.vocabulary import GeneratedArtifactDeliveryMode, GeneratedArtifactKind

from ..models import Diagnostic


def _node_target_matches(canonical: Mapping[str, Any]) -> bool:
    target_address = canonical.get("target_address")
    return target_address is None or target_address == render_compiled_address(
        "provision",
        "node",
        str(canonical.get("node", "")),
    )


_DELIVERY_MODE_REQUIRED_FIELD = {
    GeneratedArtifactDeliveryMode.ENVIRONMENT: "environment_variable",
    GeneratedArtifactDeliveryMode.ENV_FILE: "environment_file",
}
_PORTABLE_IDENTIFIER = TypeAdapter(PortableIdentifier)
_ENVIRONMENT_PROJECTION_COMMON_FIELDS = frozenset({"node", "target_address", "delivery_mode", "output"})


def _environment_projection_shape(
    projection: object,
) -> tuple[Mapping[str, Any], GeneratedArtifactDeliveryMode, str]:
    if not isinstance(projection, Mapping):
        raise ValueError("generated artifact environment consumer projection is invalid")
    mode = GeneratedArtifactDeliveryMode(str(projection.get("delivery_mode", "")))
    required_field = _DELIVERY_MODE_REQUIRED_FIELD.get(mode)
    if required_field is None:
        # mount is never a derived environment consumer; it is authored as a consumer.
        raise ValueError("generated artifact environment consumer must declare an environment delivery mode")
    if set(projection) != _ENVIRONMENT_PROJECTION_COMMON_FIELDS | {required_field}:
        raise ValueError("generated artifact environment consumer projection contains invalid fields")
    return projection, mode, required_field


def _validate_environment_projection_source(
    projection: Mapping[str, Any],
) -> None:
    node = projection.get("node")
    if not isinstance(node, str) or not node:
        raise ValueError("generated artifact environment consumer requires a node")
    output = projection.get("output")
    _PORTABLE_IDENTIFIER.validate_python(output)
    if not isinstance(output, str) or not output:
        raise ValueError("generated artifact environment consumer must select an output")
    if not isinstance(projection.get("target_address"), str) or not _node_target_matches(projection):
        raise ValueError("generated artifact environment consumer target_address does not match node")


def _validate_environment_projection_target(
    projection: Mapping[str, Any],
    *,
    mode: GeneratedArtifactDeliveryMode,
    required_field: str,
) -> None:
    target = projection.get(required_field)
    if not isinstance(target, str) or not target:
        raise ValueError(f"generated artifact environment consumer must declare {required_field}")
    if mode is GeneratedArtifactDeliveryMode.ENV_FILE:
        _PORTABLE_IDENTIFIER.validate_python(target)
    elif "=" in target or not target.strip():
        raise ValueError("generated artifact environment consumer has an invalid environment variable")


def _validate_environment_projection(projection: object) -> GeneratedArtifactDeliveryMode:
    """Validate one derived environment-consumer projection with a closed mode-specific shape."""

    canonical, mode, required_field = _environment_projection_shape(projection)
    _validate_environment_projection_source(canonical)
    _validate_environment_projection_target(canonical, mode=mode, required_field=required_field)
    return mode


def _artifact_name_from_address(address: str) -> str:
    prefix = "provision.generated-artifact."
    if not address.startswith(prefix) or not address.removeprefix(prefix):
        raise ValueError("generated artifact address is invalid")
    return address.removeprefix(prefix)


def _source_matches_artifact(
    source: GeneratedArtifactValueSource,
    *,
    artifact_name: str,
    output_name: str,
) -> bool:
    source_artifact = source.generated_artifact.removeprefix("generated_artifacts.")
    return source_artifact == artifact_name and source.output == output_name


def _projection_runtime(
    projection: Mapping[str, Any],
    *,
    node_specs: Mapping[str, object] | None,
) -> RuntimeConfiguration:
    target_address = str(projection["target_address"])
    if node_specs is None or target_address not in node_specs:
        raise ValueError("generated artifact environment consumer target node is absent")
    node_spec = node_specs[target_address]
    if not isinstance(node_spec, Mapping):
        raise ValueError("generated artifact environment consumer target node is invalid")
    node = node_spec.get("node")
    runtime_payload = node.get("runtime") if isinstance(node, Mapping) else None
    if not isinstance(runtime_payload, Mapping):
        raise ValueError("generated artifact environment consumer target runtime is absent")
    return RuntimeConfiguration.model_validate(runtime_payload)


def _environment_variable_projection_classification(
    runtime: RuntimeConfiguration,
    projection: Mapping[str, Any],
    *,
    artifact_name: str,
) -> object:
    output_name = str(projection["output"])
    target_name = projection["environment_variable"]
    matches = [
        variable
        for variable in runtime.environment
        if variable.name == target_name
        and variable.value_from is not None
        and _source_matches_artifact(
            variable.value_from,
            artifact_name=artifact_name,
            output_name=output_name,
        )
    ]
    if len(matches) != 1:
        raise ValueError("generated artifact environment consumer has no exact node binding")
    return matches[0].value_classification


def _validate_environment_file_projection(
    runtime: RuntimeConfiguration,
    projection: Mapping[str, Any],
    *,
    artifact_name: str,
) -> None:
    output_name = str(projection["output"])
    target_name = projection["environment_file"]
    matches = [
        env_file
        for env_file in runtime.environment_files
        if env_file.name == target_name
        and _source_matches_artifact(
            env_file.value_from,
            artifact_name=artifact_name,
            output_name=output_name,
        )
    ]
    if len(matches) != 1:
        raise ValueError("generated artifact env-file consumer has no exact node binding")


def _environment_projection_classification(
    projection: Mapping[str, Any],
    *,
    artifact_name: str,
    node_specs: Mapping[str, object] | None,
) -> object | None:
    """Resolve a derived projection against its canonical target-node binding."""

    runtime = _projection_runtime(projection, node_specs=node_specs)
    mode = GeneratedArtifactDeliveryMode(str(projection["delivery_mode"]))
    if mode is GeneratedArtifactDeliveryMode.ENVIRONMENT:
        return _environment_variable_projection_classification(
            runtime,
            projection,
            artifact_name=artifact_name,
        )
    _validate_environment_file_projection(runtime, projection, artifact_name=artifact_name)
    return None


_CONTENT_PROJECTION_FIELDS = frozenset({"content", "target_address", "delivery_mode", "output"})


def _validate_content_projection(projection: object) -> GeneratedArtifactDeliveryMode:
    if not isinstance(projection, Mapping):
        raise ValueError("generated artifact content_consumers entry must be an object")
    if set(projection) != _CONTENT_PROJECTION_FIELDS:
        raise ValueError("generated artifact content_consumers projection contains invalid fields")
    if projection.get("delivery_mode") != GeneratedArtifactDeliveryMode.CONTENT_TEXT.value:
        raise ValueError("generated artifact content_consumers delivery_mode must be content_text")
    content = projection.get("content")
    if not isinstance(content, str) or not content:
        raise ValueError("generated artifact content_consumers entry must name a content placement")
    output = projection.get("output")
    _PORTABLE_IDENTIFIER.validate_python(output)
    if not isinstance(output, str) or not output:
        raise ValueError("generated artifact content_consumers entry must name an output")
    target = projection.get("target_address")
    if not isinstance(target, str) or target != render_compiled_address("provision", "content", content):
        raise ValueError("generated artifact content_consumers target_address does not match its content placement")
    return GeneratedArtifactDeliveryMode.CONTENT_TEXT


def _delivery_modes_in_use(
    consumers: object,
    environment_consumers: object,
    content_consumers: object = None,
) -> set[GeneratedArtifactDeliveryMode]:
    """Delivery modes the payload requires; a malformed shape raises for bounded rejection."""

    modes: set[GeneratedArtifactDeliveryMode] = set()
    if isinstance(consumers, list) and consumers:
        modes.add(GeneratedArtifactDeliveryMode.MOUNT)
    if environment_consumers is not None:
        if not isinstance(environment_consumers, list):
            raise ValueError("generated artifact environment_consumers must be a list")
        for projection in environment_consumers:
            modes.add(_validate_environment_projection(projection))
    if content_consumers is not None:
        if not isinstance(content_consumers, list):
            raise ValueError("generated artifact content_consumers must be a list")
        for projection in content_consumers:
            modes.add(_validate_content_projection(projection))
    return modes


def _canonical_consumer(consumer: object) -> object:
    if not isinstance(consumer, Mapping):
        return consumer
    canonical = dict(consumer)
    if "delivery_mode" in canonical and canonical["delivery_mode"] != "mount":
        raise ValueError("generated artifact consumer delivery_mode must be mount")
    canonical.pop("delivery_mode", None)
    if "target_address" in canonical and (
        not isinstance(canonical["target_address"], str) or not _node_target_matches(canonical)
    ):
        raise ValueError("generated artifact consumer target_address does not match node")
    canonical.pop("target_address", None)
    return canonical


def _canonical_consumers(consumers: object) -> object:
    if not isinstance(consumers, list):
        return consumers
    return [_canonical_consumer(consumer) for consumer in consumers]


def _rejoin_content_projection(
    projection: Mapping[str, Any],
    *,
    artifact_name: str,
    content_specs: Mapping[str, object] | None,
) -> None:
    """Rejoin a derived content projection to its declared content placement.

    A directly submitted plan must not name an absent placement or one whose
    ``text_from`` binding does not match this artifact/output (issue #1276), the
    way the environment path rejoins to the target-node runtime declaration.
    """

    target_address = str(projection["target_address"])
    placement = content_specs.get(target_address) if content_specs is not None else None
    spec = placement.get("spec") if isinstance(placement, Mapping) else None
    if not isinstance(spec, Mapping):
        raise ValueError("generated artifact content consumer has no declared content placement")
    source = spec.get("text_from")
    if not isinstance(source, Mapping) or not _source_matches_artifact(
        GeneratedArtifactValueSource.model_validate(source),
        artifact_name=artifact_name,
        output_name=str(projection["output"]),
    ):
        raise ValueError("generated artifact content consumer does not match the content placement text_from binding")
    if spec.get("type") != "file":
        raise ValueError("generated artifact content consumer target is not file content")


def _validated_generated_artifact_payload(
    *,
    address: str,
    spec: object,
    node_specs: Mapping[str, object] | None = None,
    content_specs: Mapping[str, object] | None = None,
) -> tuple[GeneratedArtifact, set[GeneratedArtifactDeliveryMode]]:
    if not isinstance(spec, Mapping):
        raise ValueError("generated artifact spec must be an object")
    canonical_spec: dict[str, Any] = dict(spec)
    # Compiler-derived provisioning keys are not part of the authored model;
    # strip them before the closed-model round-trip and validate separately.
    environment_consumers = canonical_spec.pop("environment_consumers", None)
    content_consumers = canonical_spec.pop("content_consumers", None)
    consumers = canonical_spec.get("consumers")
    canonical_spec["consumers"] = _canonical_consumers(consumers)
    delivery_modes = _delivery_modes_in_use(consumers, environment_consumers, content_consumers)
    if not delivery_modes:
        raise ValueError("generated artifact must declare at least one consumer")
    artifact = GeneratedArtifact.model_validate(canonical_spec)
    artifact_name = _artifact_name_from_address(address)
    for projection in environment_consumers or []:
        classification = _environment_projection_classification(
            projection,
            artifact_name=artifact_name,
            node_specs=node_specs,
        )
        resolve_consumable_generated_artifact_output(
            artifact,
            projection["output"],
            environment_classification=classification,
        )
    for projection in content_consumers or []:
        # Rejoin the derived content projection to the canonical output contract and
        # its declared content placement so a directly submitted plan cannot bind an
        # unknown/producer_private output or a phantom content target (issue #1276).
        resolve_consumable_generated_artifact_output(artifact, projection["output"])
        _rejoin_content_projection(projection, artifact_name=artifact_name, content_specs=content_specs)
    return artifact, delivery_modes


def _artifact_capability_diagnostic(
    *,
    address: str,
    artifact: GeneratedArtifact,
    delivery_modes: set[GeneratedArtifactDeliveryMode],
    provisioner: ProvisionerCapabilities,
) -> Diagnostic | None:
    from raes_contracts.domain_profiles import DomainProfileBindingModel

    kind = (
        artifact.generator.coordinate
        if isinstance(artifact.generator, DomainProfileBindingModel)
        else artifact.generator
    )
    unsupported_modes = delivery_modes - provisioner.supported_generated_artifact_delivery_modes
    scope = artifact.regeneration_scope
    checks = (
        (
            kind not in provisioner.supported_generated_artifact_kinds,
            "provisioner.unsupported-generated-artifact-kind",
            "Provisioner does not support the selected generated artifact kind.",
        ),
        (
            bool(unsupported_modes),
            "provisioner.unsupported-generated-artifact-delivery-mode",
            f"Provisioner does not support generated artifact delivery mode "
            f"'{min((mode.value for mode in unsupported_modes), default='')}'.",
        ),
        (
            kind is GeneratedArtifactKind.RANDOM_VALUE
            and scope is not None
            and scope not in provisioner.supported_regeneration_scopes,
            "provisioner.unsupported-regeneration-scope",
            f"Provisioner does not support regeneration scope '{getattr(scope, 'value', '')}'.",
        ),
    )
    return next(
        (
            Diagnostic(code=code, domain="provisioning", address=address, message=message)
            for failed, code, message in checks
            if failed
        ),
        None,
    )


def generated_artifact_payload_diagnostic(
    *,
    address: str,
    spec: object,
    provisioner: ProvisionerCapabilities,
    node_specs: Mapping[str, object] | None = None,
    content_specs: Mapping[str, object] | None = None,
) -> Diagnostic | None:
    """Validate one compiled or directly submitted generated-artifact spec."""

    try:
        artifact, delivery_modes = _validated_generated_artifact_payload(
            address=address,
            spec=spec,
            node_specs=node_specs,
            content_specs=content_specs,
        )
    except (TypeError, ValueError):
        return Diagnostic(
            code="provisioner.generated-artifact-invalid",
            domain="provisioning",
            address=address,
            message="Submitted generated artifact payload is invalid.",
        )
    return _artifact_capability_diagnostic(
        address=address,
        artifact=artifact,
        delivery_modes=delivery_modes,
        provisioner=provisioner,
    )


__all__ = ["generated_artifact_payload_diagnostic"]
