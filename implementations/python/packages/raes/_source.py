"""Shared Source and portable artifact-requirement reference types.

A Source identifies an artifact (VM image, package, template) by
name and version. Supports shorthand (bare string) and longhand
(name + version dict) forms matching OCR SDL conventions.

The Source is backend-agnostic: it could reference a Docker image,
VM template, OVA, AMI, or any provider-specific artifact. Resolution
is delegated to the deployment backend.

When the artifact is a custom-built container image, the optional
``build`` block records its observable build/provenance facts (see
ADR-023 and ``image_provenance``).
"""

import re
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ._base import SDLModel
from .explicitness import ExplicitnessClass
from .image_provenance import ContainerImageBuildProvenance

_SHA256_DIGEST_PATTERN = r"^sha256:[a-f0-9]{64}$"
_EXTENSION_MECHANISM_PATTERN = re.compile(r"^x-[a-z0-9]+(?:-[a-z0-9]+)*:[a-z0-9]+(?:-[a-z0-9]+)*$")
_PORTABLE_MECHANISMS = frozenset(
    {
        "exact-artifact",
        "backend-owned-artifact",
        "published-candidate",
        "dynamic-composition",
        "materialization-specification",
    }
)
_PORTABLE_IDENTIFIER_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._:/@+-]*$"


def _require_unique(values: list[str], *, field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")


class ArtifactIdentity(SDLModel):
    """Immutable provider-neutral identity for one artifact payload."""

    artifact_id: Annotated[str, Field(min_length=1, max_length=256, pattern=_PORTABLE_IDENTIFIER_PATTERN)]
    version: Annotated[str, Field(min_length=1, max_length=256)]
    digest: Annotated[str, Field(pattern=_SHA256_DIGEST_PATTERN)]
    media_type: Annotated[str, Field(min_length=1, max_length=256)]


class ArtifactMechanismProfile(SDLModel):
    """Versioned portable mechanism profile.

    Portable mechanisms use the governed base names above or a namespaced
    ``x-<authority>:<term>`` extension. The profile digest binds the exact
    mechanism contract without making the mechanism set a closed union.
    """

    mechanism: Annotated[str, Field(min_length=1, max_length=128)]
    profile: Annotated[str, Field(min_length=1, max_length=256, pattern=_PORTABLE_IDENTIFIER_PATTERN)]
    version: Annotated[str, Field(min_length=1, max_length=128)]
    digest: Annotated[str, Field(pattern=_SHA256_DIGEST_PATTERN)]

    @model_validator(mode="after")
    def validate_mechanism(self) -> ArtifactMechanismProfile:
        if (
            self.mechanism not in _PORTABLE_MECHANISMS
            and _EXTENSION_MECHANISM_PATTERN.fullmatch(self.mechanism) is None
        ):
            raise ValueError("mechanism must be a portable base mechanism or a governed x-<authority>:<term> extension")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema["properties"]["mechanism"]["anyOf"] = [
            {"enum": sorted(_PORTABLE_MECHANISMS)},
            {"pattern": _EXTENSION_MECHANISM_PATTERN.pattern},
        ]
        return json_schema


class ArtifactSatisfactionRoute(SDLModel):
    """One permitted mechanism/acquisition/timing combination."""

    mechanism: ArtifactMechanismProfile
    acquisition: Literal["pull", "copy", "import", "local-lookup", "none"]
    timing: Literal["publication", "pack-ingestion", "backend-preparation", "realization"]


class ArtifactConstraint(SDLModel):
    """One typed, named bound on a constrained artifact selection."""

    constraint_id: Annotated[str, Field(min_length=1, max_length=256, pattern=_PORTABLE_IDENTIFIER_PATTERN)]
    kind: Annotated[str, Field(min_length=1, max_length=128, pattern=_PORTABLE_IDENTIFIER_PATTERN)]
    allowed_values: list[Annotated[str, Field(min_length=1, max_length=1024)]] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_values(self) -> ArtifactConstraint:
        _require_unique(self.allowed_values, field_name="artifact constraint allowed_values")
        return self


class ArtifactCandidate(SDLModel):
    """One immutable candidate explicitly admitted by the author."""

    candidate_id: Annotated[str, Field(min_length=1, max_length=256, pattern=_PORTABLE_IDENTIFIER_PATTERN)]
    artifact: ArtifactIdentity


class ArtifactLockedInput(SDLModel):
    """One immutable materialization input joined to existing trust contracts."""

    input_id: Annotated[str, Field(min_length=1, max_length=256, pattern=_PORTABLE_IDENTIFIER_PATTERN)]
    artifact: ArtifactIdentity
    associated_artifact_manifest_ref: Annotated[str, Field(min_length=1, max_length=1024)]
    trust_policy_ref: Annotated[str, Field(min_length=1, max_length=1024)]


class ArtifactMaterializationSpecification(SDLModel):
    """Reference to a closed executable materialization profile.

    This is a digest-bound specification reference, not shell text, a
    Dockerfile, an environment map, or a reinterpretation of ``Source.build``.
    """

    specification_id: Annotated[str, Field(min_length=1, max_length=256, pattern=_PORTABLE_IDENTIFIER_PATTERN)]
    profile: ArtifactMechanismProfile
    digest: Annotated[str, Field(pattern=_SHA256_DIGEST_PATTERN)]
    locked_input_ids: list[
        Annotated[str, Field(min_length=1, max_length=256, pattern=_PORTABLE_IDENTIFIER_PATTERN)]
    ] = Field(default_factory=list, json_schema_extra={"uniqueItems": True})

    @model_validator(mode="after")
    def validate_input_ids(self) -> ArtifactMaterializationSpecification:
        if self.profile.mechanism != "materialization-specification" and not self.profile.mechanism.startswith("x-"):
            raise ValueError(
                "materialization specifications require the materialization-specification "
                "mechanism or a governed extension"
            )
        _require_unique(self.locked_input_ids, field_name="materialization locked_input_ids")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).append(
            {
                "properties": {
                    "profile": {
                        "allOf": [
                            {
                                "properties": {
                                    "mechanism": {
                                        "anyOf": [
                                            {"const": "materialization-specification"},
                                            {"pattern": _EXTENSION_MECHANISM_PATTERN.pattern},
                                        ]
                                    }
                                },
                                "required": ["mechanism"],
                            }
                        ]
                    }
                }
            }
        )
        return json_schema


class ArtifactRequirement(SDLModel):
    """Author-owned artifact requirement attached to a ``Source`` selector."""

    requirement_id: Annotated[str, Field(min_length=1, max_length=256, pattern=_PORTABLE_IDENTIFIER_PATTERN)]
    explicitness: ExplicitnessClass
    exact_artifact: ArtifactIdentity | None = None
    constraints: list[ArtifactConstraint] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    candidates: list[ArtifactCandidate] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    locked_inputs: list[ArtifactLockedInput] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    materialization_specifications: list[ArtifactMaterializationSpecification] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    permitted_routes: list[ArtifactSatisfactionRoute] = Field(
        min_length=1,
        json_schema_extra={"uniqueItems": True},
    )
    trust_policy_refs: list[Annotated[str, Field(min_length=1, max_length=1024)]] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
    )
    associated_artifact_manifest_refs: list[Annotated[str, Field(min_length=1, max_length=1024)]] = Field(
        default_factory=list, json_schema_extra={"uniqueItems": True}
    )

    @model_validator(mode="after")
    def validate_authority(self) -> ArtifactRequirement:
        self._validate_unique_identities()
        if self.explicitness is ExplicitnessClass.EXACT:
            self._validate_exact_authority()
        elif self.explicitness is ExplicitnessClass.CONSTRAINED:
            self._validate_constrained_authority()
        else:
            self._validate_open_authority()
        self._validate_materialization_input_joins()
        return self

    def _validate_exact_authority(self) -> None:
        if self.exact_artifact is None:
            raise ValueError("exact artifact requirements require one immutable exact_artifact identity")
        if self.constraints or self.candidates or self.locked_inputs or self.materialization_specifications:
            raise ValueError(
                "exact artifact requirements must not declare alternative constraints, "
                "candidates, locked inputs, or materialization specifications"
            )
        if any(route.mechanism.mechanism != "exact-artifact" for route in self.permitted_routes):
            raise ValueError("exact artifact requirements permit only the exact-artifact mechanism")

    def _validate_constrained_authority(self) -> None:
        if self.exact_artifact is not None:
            raise ValueError("constrained artifact requirements must not declare exact_artifact")
        if not (self.constraints or self.candidates or self.locked_inputs or self.materialization_specifications):
            raise ValueError("constrained artifact requirements require a non-empty constraint domain")

    def _validate_open_authority(self) -> None:
        if self.exact_artifact is not None:
            raise ValueError("open artifact requirements must not declare exact_artifact")
        if self.constraints or self.candidates or self.materialization_specifications:
            raise ValueError(
                "open artifact requirements must not declare constraints, candidates, or materialization specifications"
            )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        exact_condition = {
            "properties": {"explicitness": {"const": ExplicitnessClass.EXACT.value}},
            "required": ["explicitness"],
        }
        constrained_condition = {
            "properties": {"explicitness": {"const": ExplicitnessClass.CONSTRAINED.value}},
            "required": ["explicitness"],
        }
        open_condition = {
            "properties": {"explicitness": {"const": ExplicitnessClass.OPEN.value}},
            "required": ["explicitness"],
        }
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": exact_condition,
                    "then": {
                        "required": ["exact_artifact"],
                        "properties": {
                            "exact_artifact": {"not": {"type": "null"}},
                            "constraints": {"maxItems": 0},
                            "candidates": {"maxItems": 0},
                            "locked_inputs": {"maxItems": 0},
                            "materialization_specifications": {"maxItems": 0},
                            "permitted_routes": {
                                "items": {
                                    "properties": {
                                        "mechanism": {"properties": {"mechanism": {"const": "exact-artifact"}}}
                                    }
                                }
                            },
                        },
                    },
                },
                {
                    "if": constrained_condition,
                    "then": {
                        "properties": {"exact_artifact": {"type": "null"}},
                        "anyOf": [
                            {"properties": {"constraints": {"minItems": 1}}, "required": ["constraints"]},
                            {"properties": {"candidates": {"minItems": 1}}, "required": ["candidates"]},
                            {"properties": {"locked_inputs": {"minItems": 1}}, "required": ["locked_inputs"]},
                            {
                                "properties": {"materialization_specifications": {"minItems": 1}},
                                "required": ["materialization_specifications"],
                            },
                        ],
                    },
                },
                {
                    "if": open_condition,
                    "then": {
                        "properties": {
                            "exact_artifact": {"type": "null"},
                            "constraints": {"maxItems": 0},
                            "candidates": {"maxItems": 0},
                            "materialization_specifications": {"maxItems": 0},
                        }
                    },
                },
            ]
        )
        return json_schema

    def _validate_unique_identities(self) -> None:
        for field_name, values in (
            ("constraint ids", [item.constraint_id for item in self.constraints]),
            ("candidate ids", [item.candidate_id for item in self.candidates]),
            ("locked input ids", [item.input_id for item in self.locked_inputs]),
            (
                "materialization specification ids",
                [item.specification_id for item in self.materialization_specifications],
            ),
            (
                "permitted routes",
                [
                    (
                        item.mechanism.mechanism,
                        item.mechanism.profile,
                        item.mechanism.version,
                        item.acquisition,
                        item.timing,
                    )
                    for item in self.permitted_routes
                ],
            ),
            ("trust policy refs", self.trust_policy_refs),
            ("associated artifact manifest refs", self.associated_artifact_manifest_refs),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"artifact requirement {field_name} must not contain duplicates")

    def _validate_materialization_input_joins(self) -> None:
        declared = {item.input_id for item in self.locked_inputs}
        referenced = {
            input_id
            for specification in self.materialization_specifications
            for input_id in specification.locked_input_ids
        }
        missing = sorted(referenced - declared)
        if missing:
            raise ValueError("materialization specification references missing locked input ids: " + ", ".join(missing))


class Source(SDLModel):
    """Provider-neutral artifact reference.

    Shorthand: ``source: "package-name"`` (version defaults to ``"*"``).
    Longhand: ``source: {name: "package-name", version: "1.2.3"}``.
    """

    name: str
    version: str = Field(default="*")
    build: ContainerImageBuildProvenance | None = None
    artifact_requirement: ArtifactRequirement | None = None

    @model_validator(mode="after")
    def validate_exact_requirement_selector(self) -> Source:  # NOSONAR - Pydantic requires returning self.
        requirement = self.artifact_requirement
        if requirement is None or requirement.explicitness is not ExplicitnessClass.EXACT:
            return self
        assert requirement.exact_artifact is not None
        if self.name != requirement.exact_artifact.artifact_id or self.version != requirement.exact_artifact.version:
            raise ValueError(
                "exact artifact requirement immutable identity must match the Source selector name and version"
            )
        return self
