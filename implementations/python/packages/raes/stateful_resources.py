"""Portable desired-state resources for stateful service prerequisites."""

from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath

from pydantic import Field, field_validator, model_validator
from raes_contracts.domain_profiles import DomainProfileBindingModel
from raes_contracts.vocabulary import GeneratedArtifactKind

from ._base import SDLModel
from ._identifiers import PortableIdentifier


class GeneratedArtifactLifecycle(str, Enum):
    REGENERATE_ON_CHANGE = "regenerate_on_change"
    REUSE_VALID = "reuse_valid"


class ResourceSensitivity(str, Enum):
    PUBLIC = "public"
    RESTRICTED = "restricted"
    # Constructed to avoid credential detectors treating this vocabulary value
    # as a hard-coded credential.
    SECRET = "".join(("sec", "ret"))


class GeneratedArtifactOutputDisposition(str, Enum):
    CONSUMER_SELECTED = "consumer_selected"
    PRODUCER_PRIVATE = "producer_private"


class ConsumerAccessMode(str, Enum):
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class VolumeLifecycle(str, Enum):
    RETAIN = "retain"
    EPHEMERAL = "ephemeral"


class VolumeAccessMode(str, Enum):
    READ_WRITE_ONCE = "read_write_once"
    READ_WRITE_MANY = "read_write_many"
    READ_ONLY_MANY = "read_only_many"


def _validate_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or str(path) != value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("generated output path must be a canonical contained POSIX relative file path")
    return value


def _validate_mount_destination(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or not path.is_absolute()
        or value.startswith("//")
        or ".." in path.parts
        or str(path) == "/"
        or str(path) != value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("mount_destination must be a canonical contained POSIX absolute path below root")
    return value


class GeneratedArtifactOutput(SDLModel):
    """One complete output declared by an artifact generator."""

    name: PortableIdentifier
    path: str
    sensitivity: ResourceSensitivity
    disposition: GeneratedArtifactOutputDisposition = GeneratedArtifactOutputDisposition.CONSUMER_SELECTED

    _contained_path = field_validator("path")(_validate_relative_path)


class StatefulResourceConsumer(SDLModel):
    """A node that consumes a generated artifact or persistent volume."""

    node: str
    mount_destination: str
    access_mode: ConsumerAccessMode

    _contained_mount_destination = field_validator("mount_destination")(_validate_mount_destination)


class GeneratedArtifactConsumer(StatefulResourceConsumer):
    """A read-only artifact projection selected by output name."""

    selected_outputs: list[PortableIdentifier] = Field(
        default_factory=list,
        exclude_if=lambda value: not value,
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )

    @model_validator(mode="after")
    def _unique_selected_outputs(self) -> GeneratedArtifactConsumer:
        if len(self.selected_outputs) != len(set(self.selected_outputs)):
            raise ValueError("generated artifact consumer selected_outputs must be unique")
        return self


def _validate_generated_artifact_identity(artifact: GeneratedArtifact) -> None:
    names = [output.name for output in artifact.outputs]
    paths = [output.path for output in artifact.outputs]
    consumers = [(consumer.node, consumer.mount_destination) for consumer in artifact.consumers]
    if len(names) != len(set(names)):
        raise ValueError("generated artifact output names must be unique")
    if len(paths) != len(set(paths)):
        raise ValueError("generated artifact output paths must be unique")
    if len(consumers) != len(set(consumers)):
        raise ValueError("generated artifact consumers must be unique")
    if any(consumer.access_mode is ConsumerAccessMode.READ_WRITE for consumer in artifact.consumers):
        raise ValueError("generated artifact consumers must be read_only")


def _selected_generated_artifact_outputs(artifact: GeneratedArtifact) -> set[str]:
    outputs_by_name = {output.name: output for output in artifact.outputs}
    selected_output_names: set[str] = set()
    for consumer in artifact.consumers:
        if isinstance(artifact.generator, DomainProfileBindingModel) and not consumer.selected_outputs:
            raise ValueError("Private generated artifact consumers must select at least one output")
        if artifact.generator is GeneratedArtifactKind.SSH_KEY_BUNDLE and not consumer.selected_outputs:
            raise ValueError("SSH generated artifact consumers must select at least one output")
        for selected_output in consumer.selected_outputs:
            output = outputs_by_name.get(selected_output)
            if output is None:
                raise ValueError("generated artifact consumer selects an unknown generated artifact output")
            if output.disposition is GeneratedArtifactOutputDisposition.PRODUCER_PRIVATE:
                raise ValueError(
                    "generated artifact consumer cannot select a producer-private generated artifact output"
                )
            selected_output_names.add(selected_output)
    return selected_output_names


def _validate_ssh_output_selection(artifact: GeneratedArtifact, selected_output_names: set[str]) -> None:
    if artifact.generator is not GeneratedArtifactKind.SSH_KEY_BUNDLE:
        return
    for output in artifact.outputs:
        if (
            output.disposition is GeneratedArtifactOutputDisposition.CONSUMER_SELECTED
            and output.name not in selected_output_names
        ):
            raise ValueError("each consumer-selected SSH output must be selected by at least one consumer")


class GeneratedArtifact(SDLModel):
    """Desired generated configuration or certificate/key material."""

    generator: GeneratedArtifactKind | DomainProfileBindingModel
    lifecycle: GeneratedArtifactLifecycle
    provenance: str = Field(min_length=1)
    outputs: list[GeneratedArtifactOutput] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    # Consumers may be empty when a generated artifact is consumed only as a node
    # runtime environment value / env_file (issue #1074): those bindings are
    # authored on ``nodes.<node>.runtime.environment[]`` and the compiler derives
    # the consumer projection. Semantic admission still rejects an artifact that
    # no file consumer and no environment binding consumes.
    consumers: list[GeneratedArtifactConsumer] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    ordering_dependencies: list[str] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    refresh_dependencies: list[str] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _unique_outputs_and_consumers(self) -> GeneratedArtifact:
        _validate_generated_artifact_identity(self)
        selected_output_names = _selected_generated_artifact_outputs(self)
        _validate_ssh_output_selection(self, selected_output_names)
        if len(self.ordering_dependencies) != len(set(self.ordering_dependencies)):
            raise ValueError("generated artifact ordering_dependencies must be unique")
        if len(self.refresh_dependencies) != len(set(self.refresh_dependencies)):
            raise ValueError("generated artifact refresh_dependencies must be unique")
        return self


class PersistentVolume(SDLModel):
    """Portable desired persistent storage and its mount consumers."""

    lifecycle: VolumeLifecycle
    access_mode: VolumeAccessMode
    consumers: list[StatefulResourceConsumer] = Field(min_length=1, json_schema_extra={"uniqueItems": True})
    ordering_dependencies: list[str] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})
    refresh_dependencies: list[str] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def _unique_consumers(self) -> PersistentVolume:
        consumers = [(consumer.node, consumer.mount_destination) for consumer in self.consumers]
        if len(consumers) != len(set(consumers)):
            raise ValueError("persistent volume consumers must be unique")
        if self.access_mode is VolumeAccessMode.READ_ONLY_MANY and any(
            consumer.access_mode is ConsumerAccessMode.READ_WRITE for consumer in self.consumers
        ):
            raise ValueError("read_only_many volume consumers must be read_only")
        writer_nodes = {
            consumer.node for consumer in self.consumers if consumer.access_mode is ConsumerAccessMode.READ_WRITE
        }
        if self.access_mode is VolumeAccessMode.READ_WRITE_ONCE and len(writer_nodes) > 1:
            raise ValueError("read_write_once volumes admit at most one writer node")
        if len(self.ordering_dependencies) != len(set(self.ordering_dependencies)):
            raise ValueError("persistent volume ordering_dependencies must be unique")
        if len(self.refresh_dependencies) != len(set(self.refresh_dependencies)):
            raise ValueError("persistent volume refresh_dependencies must be unique")
        return self


__all__ = (
    "ConsumerAccessMode",
    "GeneratedArtifact",
    "GeneratedArtifactConsumer",
    "GeneratedArtifactKind",
    "GeneratedArtifactLifecycle",
    "GeneratedArtifactOutput",
    "GeneratedArtifactOutputDisposition",
    "PersistentVolume",
    "ResourceSensitivity",
    "StatefulResourceConsumer",
    "VolumeAccessMode",
    "VolumeLifecycle",
)
