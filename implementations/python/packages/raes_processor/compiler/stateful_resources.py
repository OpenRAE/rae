"""Compilation of generated artifacts and persistent volumes."""

from typing import Any

from raes.scenario import InstantiatedScenario, ScenarioContent
from raes_contracts.vocabulary import GeneratedArtifactDeliveryMode

from ..models import GeneratedArtifactRuntime, PersistentVolumeRuntime
from .addresses import (
    _generated_artifact_address,
    _node_address,
    _persistent_volume_address,
    _section_ref_name,
)
from .support import _dump

_GENERATED_ARTIFACTS_PREFIX = "generated_artifacts."


def _generated_artifact_ref_matches(reference: str, artifact_name: str) -> bool:
    resolved = (
        reference.removeprefix(_GENERATED_ARTIFACTS_PREFIX)
        if reference.startswith(_GENERATED_ARTIFACTS_PREFIX)
        else reference
    )
    return resolved == artifact_name


def _environment_consumer_projections(
    scenario: ScenarioContent,
    artifact_name: str,
) -> list[dict[str, Any]]:
    """Derive generated-artifact consumer projections from node env bindings.

    The projection reads only the shared ``nodes`` content, so both the
    instantiated scenario compiled here and the expanded scenario rebuilt for
    prepared-node admission satisfy it.

    Authors declare the binding once on ``nodes.<node>.runtime.environment[]`` /
    ``environment_files[]``; the provisioning resource needs the matching
    consumer projection so a backend can inject the referenced output. No raw
    generated value is carried - only the output name and env target.
    """

    projections: list[dict[str, Any]] = []
    for node_name, node in scenario.nodes.items():
        runtime = node.runtime
        if runtime is None:
            continue
        target_address = _node_address(node_name)
        for variable in runtime.environment:
            source = variable.value_from
            if source is not None and _generated_artifact_ref_matches(source.generated_artifact, artifact_name):
                projections.append(
                    {
                        "node": node_name,
                        "target_address": target_address,
                        "delivery_mode": GeneratedArtifactDeliveryMode.ENVIRONMENT.value,
                        "output": source.output,
                        "environment_variable": variable.name,
                    }
                )
        for env_file in runtime.environment_files:
            source = env_file.value_from
            if _generated_artifact_ref_matches(source.generated_artifact, artifact_name):
                projections.append(
                    {
                        "node": node_name,
                        "target_address": target_address,
                        "delivery_mode": GeneratedArtifactDeliveryMode.ENV_FILE.value,
                        "output": source.output,
                        "environment_file": env_file.name,
                    }
                )
    return projections


def _stateful_dependency_address(
    scenario: InstantiatedScenario,
    reference: str,
) -> str:
    if reference.startswith(_GENERATED_ARTIFACTS_PREFIX):
        name = reference.removeprefix(_GENERATED_ARTIFACTS_PREFIX)
        if name in scenario.generated_artifacts:
            return _generated_artifact_address(name)
    if reference.startswith("persistent_volumes."):
        name = reference.removeprefix("persistent_volumes.")
        if name in scenario.persistent_volumes:
            return _persistent_volume_address(name)
    in_artifacts = reference in scenario.generated_artifacts
    in_volumes = reference in scenario.persistent_volumes
    if in_artifacts != in_volumes:
        return _generated_artifact_address(reference) if in_artifacts else _persistent_volume_address(reference)
    raise ValueError("validated stateful dependency reference must resolve unambiguously")


def _stateful_spec(
    scenario: InstantiatedScenario,
    resource: object,
) -> dict[str, Any]:
    spec = _dump(resource)
    consumers: list[dict[str, Any]] = []
    for raw_consumer in spec.get("consumers", []):
        consumer = dict(raw_consumer)
        node_name = _section_ref_name(
            str(consumer.get("node", "")),
            "nodes",
            scenario.nodes,
        )
        consumer["node"] = node_name
        consumer["target_address"] = _node_address(node_name)
        consumers.append(consumer)
    spec["consumers"] = consumers
    return spec


def _compile_generated_artifacts(
    scenario: InstantiatedScenario,
) -> dict[str, GeneratedArtifactRuntime]:
    resources: dict[str, GeneratedArtifactRuntime] = {}
    for name, artifact in scenario.generated_artifacts.items():
        address = _generated_artifact_address(name)
        spec = _stateful_spec(scenario, artifact)
        for consumer in spec["consumers"]:
            consumer["delivery_mode"] = GeneratedArtifactDeliveryMode.MOUNT.value
        spec["environment_consumers"] = _environment_consumer_projections(scenario, name)
        resources[address] = GeneratedArtifactRuntime(
            address=address,
            name=name,
            spec=spec,
            ordering_dependencies=tuple(
                _stateful_dependency_address(scenario, ref) for ref in artifact.ordering_dependencies
            ),
            refresh_dependencies=tuple(
                _stateful_dependency_address(scenario, ref) for ref in artifact.refresh_dependencies
            ),
        )
    return resources


def _compile_persistent_volumes(
    scenario: InstantiatedScenario,
) -> dict[str, PersistentVolumeRuntime]:
    resources: dict[str, PersistentVolumeRuntime] = {}
    for name, volume in scenario.persistent_volumes.items():
        address = _persistent_volume_address(name)
        resources[address] = PersistentVolumeRuntime(
            address=address,
            name=name,
            spec=_stateful_spec(scenario, volume),
            ordering_dependencies=tuple(
                _stateful_dependency_address(scenario, ref) for ref in volume.ordering_dependencies
            ),
            refresh_dependencies=tuple(
                _stateful_dependency_address(scenario, ref) for ref in volume.refresh_dependencies
            ),
        )
    return resources
