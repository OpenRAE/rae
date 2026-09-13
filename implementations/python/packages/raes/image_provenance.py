"""Observed container/image build-provenance models for the SDL ``Source``.

These models express the observable build recipe, layer chain, image
default configuration, source-input mapping, and attestation status of a
custom container image. They attach to the artifact-reference boundary as
``Source.build`` (see ADR-023): ``Source.name`` / ``Source.version`` remain
provider-neutral artifact identity, while the optional ``build`` block carries
facts about how that artifact was produced or inspected.

Image *default* configuration (default entrypoint, command, working directory,
labels, exposed ports, default environment) is an image-artifact fact and lives
here. Runtime-*effective* container facts stay under ``Node.runtime`` and are
not duplicated into this surface, even though some values may legitimately
appear in both with different meanings.
"""

from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from ._base import SDLModel, parse_int_or_var
from .runtime_configuration import RuntimeEnvironmentValueClassification
from .runtime_values import (
    absolute_path_or_var,
    coerce_string_list,
    enforce_observed_value_redaction,
    parse_optional_bool_or_var,
    parse_runtime_enum_or_var,
)
from .runtime_vocabulary import GovernedVocabulary

__all__ = [
    "ContainerImageBuildProvenance",
    "DockerfileInstruction",
    "DockerfileInstructionKind",
    "ImageAttestation",
    "ImageAttestationStatus",
    "ImageAttestationType",
    "ImageBuildArg",
    "ImageConfig",
    "ImageCopiedSource",
    "ImageEnvironmentDefault",
    "ImageLayer",
    "ImageSourceInput",
    "ImageVerificationStatus",
]

_IMAGE_ENV_REDACTED_CLASSIFICATIONS = (
    RuntimeEnvironmentValueClassification.REDACTED,
    RuntimeEnvironmentValueClassification.OPERATOR_SECRET,
)


class DockerfileInstructionKind(str, Enum):
    """Observed kind of a structured container build-recipe instruction."""

    FROM = "from"
    ARG = "arg"
    ENV = "env"
    RUN = "run"
    COPY = "copy"
    ADD = "add"
    WORKDIR = "workdir"
    ENTRYPOINT = "entrypoint"
    CMD = "cmd"
    HEALTHCHECK = "healthcheck"
    LABEL = "label"
    EXPOSE = "expose"
    USER = "user"
    VOLUME = "volume"
    SHELL = "shell"
    STOPSIGNAL = "stopsignal"
    ONBUILD = "onbuild"
    MAINTAINER = "maintainer"
    OTHER = "other"


class ImageAttestationStatus(str, Enum):
    """Availability of a registry-visible build attestation for an image."""

    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class ImageVerificationStatus(str, Enum):
    """Result of verifying an image's build attestation."""

    VERIFIED = "verified"
    FAILED = "failed"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class ImageAttestationType(str, Enum):
    """Format of an observed image build attestation."""

    OCI = "oci"
    IN_TOTO = "in_toto"
    SLSA = "slsa"
    OTHER = "other"
    NONE = "none"
    UNKNOWN = "unknown"


class DockerfileInstruction(SDLModel):
    """A structured record of one container build-recipe instruction.

    The instruction is kept as a typed kind plus tokenized ``arguments``
    rather than raw recipe text: raw Dockerfile/shell syntax can contain
    ``${...}`` strings that collide with RAES variable substitution.
    """

    instruction: GovernedVocabulary[DockerfileInstructionKind]
    arguments: list[str] = Field(default_factory=list)
    description: str = ""

    @field_validator("instruction", mode="before")
    @classmethod
    def normalize_instruction(
        cls, v: GovernedVocabulary[DockerfileInstructionKind]
    ) -> GovernedVocabulary[DockerfileInstructionKind]:
        return parse_runtime_enum_or_var(v, DockerfileInstructionKind, field_name="instruction")

    @field_validator("arguments", mode="before")
    @classmethod
    def normalize_arguments(cls, v: Any) -> list[str]:
        return coerce_string_list(v)


class ImageLayer(SDLModel):
    """An observed layer in the image layer chain.

    Empty/metadata-only layers (e.g. ``ENV`` instructions) legitimately carry
    no ``digest``; the layer is still recorded for build-history correlation.
    """

    digest: str = ""
    created_by: str = ""
    size: int | str | None = None
    empty: bool | str | None = None
    description: str = ""

    @field_validator("size", mode="before")
    @classmethod
    def parse_size(cls, v: int | str | None) -> int | str | None:
        return parse_int_or_var(v, minimum=0, field_name="size") if v is not None else v

    @field_validator("empty", mode="before")
    @classmethod
    def parse_empty(cls, v: bool | str | None) -> bool | str | None:
        return parse_optional_bool_or_var(v, field_name="empty")


class ImageBuildArg(SDLModel):
    """An observed build argument with value-sensitivity classification."""

    name: str
    value: str = ""
    value_classification: GovernedVocabulary[RuntimeEnvironmentValueClassification] = (
        RuntimeEnvironmentValueClassification.UNKNOWN
    )
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("build argument name must be a non-empty string")
        if "=" in v:
            raise ValueError("build argument name must not contain '='")
        return v

    @field_validator("value_classification", mode="before")
    @classmethod
    def normalize_value_classification(
        cls,
        v: GovernedVocabulary[RuntimeEnvironmentValueClassification],
    ) -> GovernedVocabulary[RuntimeEnvironmentValueClassification]:
        return parse_runtime_enum_or_var(
            v,
            RuntimeEnvironmentValueClassification,
            field_name="value_classification",
        )

    @model_validator(mode="after")
    def validate_redacted_value(self) -> "ImageBuildArg":
        enforce_observed_value_redaction(
            owner_label=f"build argument '{self.name}'",
            value=self.value,
            classification=self.value_classification,
            redacted_classifications=_IMAGE_ENV_REDACTED_CLASSIFICATIONS,
            raw_value_label="value",
            redacted_raw_message="redacted build arguments must omit value"
            if self.value_classification == RuntimeEnvironmentValueClassification.REDACTED
            else None,
        )
        return self


class ImageEnvironmentDefault(SDLModel):
    """An image-default environment variable with sensitivity classification."""

    name: str
    value: str = ""
    value_classification: GovernedVocabulary[RuntimeEnvironmentValueClassification] = (
        RuntimeEnvironmentValueClassification.UNKNOWN
    )
    description: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("image environment variable name must be a non-empty string")
        if "=" in v:
            raise ValueError("image environment variable name must not contain '='")
        return v

    @field_validator("value_classification", mode="before")
    @classmethod
    def normalize_value_classification(
        cls,
        v: GovernedVocabulary[RuntimeEnvironmentValueClassification],
    ) -> GovernedVocabulary[RuntimeEnvironmentValueClassification]:
        return parse_runtime_enum_or_var(
            v,
            RuntimeEnvironmentValueClassification,
            field_name="value_classification",
        )

    @model_validator(mode="after")
    def validate_redacted_value(self) -> "ImageEnvironmentDefault":
        enforce_observed_value_redaction(
            owner_label=f"image environment variable '{self.name}'",
            value=self.value,
            classification=self.value_classification,
            redacted_classifications=_IMAGE_ENV_REDACTED_CLASSIFICATIONS,
            raw_value_label="value",
            redacted_raw_message="redacted image environment variables must omit value"
            if self.value_classification == RuntimeEnvironmentValueClassification.REDACTED
            else None,
        )
        return self


class ImageCopiedSource(SDLModel):
    """A source path copied into the image and its in-image destination."""

    source_path: str
    destination_path: str
    from_stage: str = ""
    description: str = ""

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("source_path must be a non-empty string")
        return v

    @field_validator("destination_path")
    @classmethod
    def validate_destination_path(cls, v: str) -> str:
        return absolute_path_or_var(v, field_name="destination_path")


class ImageConfig(SDLModel):
    """Observed image-default configuration baked into the image artifact.

    These are image defaults, distinct from runtime-effective container facts
    recorded under ``Node.runtime.container``.
    """

    entrypoint: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    working_directory: str = ""
    exposed_ports: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    default_environment: list[ImageEnvironmentDefault] = Field(default_factory=list)
    description: str = ""

    @field_validator("entrypoint", "command", "exposed_ports", mode="before")
    @classmethod
    def normalize_string_lists(cls, v: Any) -> list[str]:
        return coerce_string_list(v)

    @field_validator("working_directory")
    @classmethod
    def validate_working_directory(cls, v: str) -> str:
        return absolute_path_or_var(v, field_name="working_directory") if v else v

    @model_validator(mode="after")
    def validate_unique_default_environment(self) -> "ImageConfig":
        seen: set[str] = set()
        for variable in self.default_environment:
            if variable.name in seen:
                raise ValueError(f"Duplicate image environment variable '{variable.name}'")
            seen.add(variable.name)
        return self


class ImageSourceInput(SDLModel):
    """A source-package input and its source-to-runtime destination mapping.

    ``source_path`` uses the same source-path dialect as
    ``RuntimeFilesystemEntry.source_path`` so the build-time input and the
    realized runtime entry can be correlated.
    """

    identifier: str
    source_path: str = ""
    destination_path: str = ""
    checksum: str = ""
    checksum_algorithm: str = ""
    description: str = ""

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("source input identifier must be a non-empty string")
        return v

    @field_validator("destination_path")
    @classmethod
    def validate_destination_path(cls, v: str) -> str:
        return absolute_path_or_var(v, field_name="destination_path") if v else v

    @model_validator(mode="after")
    def validate_checksum_pair(self) -> "ImageSourceInput":
        if self.checksum and not self.checksum_algorithm:
            raise ValueError("checksum requires checksum_algorithm")
        if self.checksum_algorithm and not self.checksum:
            raise ValueError("checksum_algorithm requires checksum")
        return self


class ImageAttestation(SDLModel):
    """Observed build-attestation availability and verification result.

    Attestation *availability* (``status``) and *verification result*
    (``verification``) are deliberately separate facts: a mutable local image
    tag with no registry-visible OCI/in-toto/SLSA attestation is not the same
    state as a failed verification (ADR-023 §5).
    """

    status: GovernedVocabulary[ImageAttestationStatus] = ImageAttestationStatus.UNKNOWN
    verification: GovernedVocabulary[ImageVerificationStatus] = ImageVerificationStatus.UNKNOWN
    attestation_type: GovernedVocabulary[ImageAttestationType] = ImageAttestationType.UNKNOWN
    predicate_type: str = ""
    evidence_reference: str = ""
    description: str = ""

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(
        cls, v: GovernedVocabulary[ImageAttestationStatus]
    ) -> GovernedVocabulary[ImageAttestationStatus]:
        return parse_runtime_enum_or_var(v, ImageAttestationStatus, field_name="status")

    @field_validator("verification", mode="before")
    @classmethod
    def normalize_verification(
        cls, v: GovernedVocabulary[ImageVerificationStatus]
    ) -> GovernedVocabulary[ImageVerificationStatus]:
        return parse_runtime_enum_or_var(v, ImageVerificationStatus, field_name="verification")

    @field_validator("attestation_type", mode="before")
    @classmethod
    def normalize_attestation_type(cls, v: ImageAttestationType | str) -> ImageAttestationType | str:
        return parse_runtime_enum_or_var(v, ImageAttestationType, field_name="attestation_type")

    @model_validator(mode="after")
    def validate_status_verification(self) -> "ImageAttestation":
        if self.status == ImageAttestationStatus.ABSENT and self.verification == ImageVerificationStatus.VERIFIED:
            raise ValueError("an absent attestation cannot have a verified verification result")
        return self


class ContainerImageBuildProvenance(SDLModel):
    """Observed build/provenance facts for a custom container image artifact."""

    base_image: str = ""
    base_image_digest: str = ""
    dockerfile_path: str = ""
    instructions: list[DockerfileInstruction] = Field(default_factory=list)
    layers: list[ImageLayer] = Field(default_factory=list)
    build_args: list[ImageBuildArg] = Field(default_factory=list)
    copied_sources: list[ImageCopiedSource] = Field(default_factory=list)
    config: ImageConfig | None = None
    source_inputs: list[ImageSourceInput] = Field(default_factory=list)
    attestation: ImageAttestation | None = None
    description: str = ""

    @model_validator(mode="after")
    def validate_unique_entries(self) -> "ContainerImageBuildProvenance":
        seen_build_args: set[str] = set()
        for build_arg in self.build_args:
            if build_arg.name in seen_build_args:
                raise ValueError(f"Duplicate build argument '{build_arg.name}'")
            seen_build_args.add(build_arg.name)

        seen_inputs: set[str] = set()
        for source_input in self.source_inputs:
            if source_input.identifier in seen_inputs:
                raise ValueError(f"Duplicate source input identifier '{source_input.identifier}'")
            seen_inputs.add(source_input.identifier)
        return self
