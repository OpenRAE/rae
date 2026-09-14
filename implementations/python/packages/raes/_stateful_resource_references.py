"""Semantic validation for stateful realization resource references."""

from collections.abc import Iterable, Mapping

from .content import Content
from .nodes import Node, OSFamily
from .propositions import Proposition, PropositionBasis, StringPredicate
from .runtime_generated_value import (
    GeneratedArtifactValueSource,
    resolve_consumable_generated_artifact_output,
)
from .stateful_resources import GeneratedArtifact, PersistentVolume, ResourceSensitivity

_GENERATED_ARTIFACTS_PREFIX = "generated_artifacts."


def _node_name(reference: str, nodes: Mapping[str, Node]) -> str | None:
    name = reference.removeprefix("nodes.") if reference.startswith("nodes.") else reference
    return name if name in nodes else None


def _generated_artifact_ref_name(
    reference: str,
    generated_artifacts: Mapping[str, GeneratedArtifact],
) -> str | None:
    name = (
        reference.removeprefix(_GENERATED_ARTIFACTS_PREFIX)
        if reference.startswith(_GENERATED_ARTIFACTS_PREFIX)
        else reference
    )
    return name if name in generated_artifacts else None


def _node_environment_bindings(node: Node) -> list[tuple[str, GeneratedArtifactValueSource, object | None]]:
    """Return labels, sources, and optional env classifications for node bindings."""

    runtime = node.runtime
    if runtime is None:
        return []
    bindings: list[tuple[str, GeneratedArtifactValueSource, object | None]] = []
    for variable in runtime.environment:
        if variable.value_from is not None:
            bindings.append(
                (
                    f"environment variable {variable.name!r}",
                    variable.value_from,
                    variable.value_classification,
                )
            )
    for env_file in runtime.environment_files:
        bindings.append((f"environment file {env_file.name!r}", env_file.value_from, None))
    return bindings


def _environment_binding_errors(
    *,
    nodes: Mapping[str, Node],
    generated_artifacts: Mapping[str, GeneratedArtifact],
    consumed_artifacts: set[str],
) -> list[str]:
    """Validate node runtime env / env-file generated-artifact references.

    Records every referenced artifact in ``consumed_artifacts`` so an artifact
    consumed only through an environment binding is not flagged as an orphan.
    """

    errors: list[str] = []
    for node_name, node in nodes.items():
        for label, source, environment_classification in _node_environment_bindings(node):
            owner = f"node {node_name!r} {label}"
            artifact_name = _generated_artifact_ref_name(source.generated_artifact, generated_artifacts)
            if artifact_name is None:
                errors.append(f"{owner} references generated artifact {source.generated_artifact!r} which is missing")
                continue
            consumed_artifacts.add(artifact_name)
            try:
                resolve_consumable_generated_artifact_output(
                    generated_artifacts[artifact_name],
                    source.output,
                    environment_classification=environment_classification,
                )
            except ValueError as exc:
                errors.append(f"{owner} {exc} on generated_artifacts.{artifact_name}")
    return errors


def _content_binding_errors(
    *,
    content: Mapping[str, Content],
    generated_artifacts: Mapping[str, GeneratedArtifact],
    consumed_artifacts: set[str],
) -> list[str]:
    """Validate content ``text_from`` generated-artifact references (issue #1276).

    Records each referenced artifact in ``consumed_artifacts`` so an artifact
    consumed only through a content binding is not flagged as an orphan.
    """

    errors: list[str] = []
    for content_name, item in content.items():
        source = item.text_from
        if source is None:
            continue
        owner = f"content {content_name!r} text_from"
        artifact_name = _generated_artifact_ref_name(source.generated_artifact, generated_artifacts)
        if artifact_name is None:
            errors.append(f"{owner} references generated artifact {source.generated_artifact!r} which is missing")
            continue
        consumed_artifacts.add(artifact_name)
        try:
            output = resolve_consumable_generated_artifact_output(generated_artifacts[artifact_name], source.output)
        except ValueError as exc:
            errors.append(f"{owner} {exc} on generated_artifacts.{artifact_name}")
            continue
        if output.sensitivity is ResourceSensitivity.SECRET and item.sensitive is False:
            errors.append(f"{owner} binds a secret generated output; content must be marked sensitive")
    return errors


def _proposition_expected_from_errors(
    *,
    propositions: Mapping[str, Proposition],
    generated_artifacts: Mapping[str, GeneratedArtifact],
    consumed_artifacts: set[str],
) -> list[str]:
    """Validate proposition ``expected_from`` generated-artifact references (issue #1276)."""

    errors: list[str] = []
    for proposition_name, proposition in propositions.items():
        predicate = proposition.predicate
        if not isinstance(predicate, StringPredicate) or predicate.expected_from is None:
            continue
        source = predicate.expected_from
        owner = f"proposition {proposition_name!r} expected_from"
        if proposition.basis is not PropositionBasis.OBSERVED_STATE:
            errors.append(f"{owner} requires an observed_state proposition basis")
        artifact_name = _generated_artifact_ref_name(source.generated_artifact, generated_artifacts)
        if artifact_name is None:
            errors.append(f"{owner} references generated artifact {source.generated_artifact!r} which is missing")
            continue
        consumed_artifacts.add(artifact_name)
        try:
            resolve_consumable_generated_artifact_output(generated_artifacts[artifact_name], source.output)
        except ValueError as exc:
            errors.append(f"{owner} {exc} on generated_artifacts.{artifact_name}")
    return errors


def _orphan_generated_artifact_errors(
    generated_artifacts: Mapping[str, GeneratedArtifact],
    consumed_artifacts: Iterable[str],
) -> list[str]:
    consumed = set(consumed_artifacts)
    return [
        f"generated_artifacts.{name} is declared but no file consumer, environment binding, "
        f"or content binding consumes it"
        for name, artifact in generated_artifacts.items()
        if not artifact.consumers and name not in consumed
    ]


def _dependency_candidates(
    reference: str,
    *,
    generated_artifacts: Mapping[str, GeneratedArtifact],
    persistent_volumes: Mapping[str, PersistentVolume],
) -> list[str]:
    if reference.startswith(_GENERATED_ARTIFACTS_PREFIX):
        name = reference.removeprefix(_GENERATED_ARTIFACTS_PREFIX)
        return [reference] if name in generated_artifacts else []
    if reference.startswith("persistent_volumes."):
        name = reference.removeprefix("persistent_volumes.")
        return [reference] if name in persistent_volumes else []

    candidates: list[str] = []
    if reference in generated_artifacts:
        candidates.append(f"{_GENERATED_ARTIFACTS_PREFIX}{reference}")
    if reference in persistent_volumes:
        candidates.append(f"persistent_volumes.{reference}")
    return candidates


def _consumer_reference_errors(
    *,
    owner: str,
    resource: GeneratedArtifact | PersistentVolume,
    nodes: Mapping[str, Node],
    occupied_destinations: dict[tuple[str, str], str],
) -> list[str]:
    errors: list[str] = []
    for consumer in resource.consumers:
        node_name = _node_name(consumer.node, nodes)
        if node_name is None:
            errors.append(f"{owner} consumer node reference {consumer.node!r} is missing")
            continue
        node = nodes[node_name]
        if node.os is OSFamily.WINDOWS or node.os == OSFamily.WINDOWS.value:
            errors.append(f"{owner} uses a POSIX mount_destination for Windows consumer node {node_name!r}")
        destination = (node_name, consumer.mount_destination)
        previous = occupied_destinations.get(destination)
        if previous is None:
            occupied_destinations[destination] = owner
        else:
            errors.append(
                f"{owner} mount_destination {consumer.mount_destination!r} on node {node_name!r} "
                f"is already consumed by {previous}"
            )
    return errors


def _dependency_reference_errors(
    *,
    owner: str,
    resource: GeneratedArtifact | PersistentVolume,
    generated_artifacts: Mapping[str, GeneratedArtifact],
    persistent_volumes: Mapping[str, PersistentVolume],
) -> list[str]:
    errors: list[str] = []
    for dependency in (*resource.ordering_dependencies, *resource.refresh_dependencies):
        candidates = _dependency_candidates(
            dependency,
            generated_artifacts=generated_artifacts,
            persistent_volumes=persistent_volumes,
        )
        if not candidates:
            errors.append(f"{owner} dependency reference {dependency!r} is missing")
        elif len(candidates) > 1:
            choices = ", ".join(candidates)
            errors.append(f"{owner} dependency reference {dependency!r} is ambiguous; use one of: {choices}")
    return errors


def stateful_resource_reference_errors(
    *,
    nodes: Mapping[str, Node],
    generated_artifacts: Mapping[str, GeneratedArtifact],
    persistent_volumes: Mapping[str, PersistentVolume],
    content: Mapping[str, Content] | None = None,
    propositions: Mapping[str, Proposition] | None = None,
) -> list[str]:
    """Return bounded semantic errors before compilation or dispatch."""

    errors: list[str] = []
    occupied_destinations: dict[tuple[str, str], str] = {}
    consumed_artifacts: set[str] = set()
    for section, resources in (
        ("generated_artifacts", generated_artifacts),
        ("persistent_volumes", persistent_volumes),
    ):
        for name, resource in resources.items():
            owner = f"{section}.{name}"
            if section == "generated_artifacts" and resource.consumers:
                consumed_artifacts.add(name)
            errors.extend(
                _consumer_reference_errors(
                    owner=owner,
                    resource=resource,
                    nodes=nodes,
                    occupied_destinations=occupied_destinations,
                )
            )
            errors.extend(
                _dependency_reference_errors(
                    owner=owner,
                    resource=resource,
                    generated_artifacts=generated_artifacts,
                    persistent_volumes=persistent_volumes,
                )
            )
    errors.extend(
        _environment_binding_errors(
            nodes=nodes,
            generated_artifacts=generated_artifacts,
            consumed_artifacts=consumed_artifacts,
        )
    )
    errors.extend(
        _content_binding_errors(
            content=content or {},
            generated_artifacts=generated_artifacts,
            consumed_artifacts=consumed_artifacts,
        )
    )
    errors.extend(
        _proposition_expected_from_errors(
            propositions=propositions or {},
            generated_artifacts=generated_artifacts,
            consumed_artifacts=consumed_artifacts,
        )
    )
    errors.extend(_orphan_generated_artifact_errors(generated_artifacts, consumed_artifacts))
    for node_name, node in nodes.items():
        runtime = node.runtime
        if runtime is None:
            continue
        for mount in runtime.mounts:
            destination = (node_name, mount.target)
            previous = occupied_destinations.get(destination)
            if previous is not None:
                errors.append(
                    f"runtime mount target {mount.target!r} on node {node_name!r} is already consumed by {previous}"
                )
    return errors


__all__ = ["stateful_resource_reference_errors"]
