"""Associated-artifact manifest contracts and URI-safety validation."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ..uri_safety import validate_safe_absolute_uri
from ..versions import ASSOCIATED_ARTIFACT_MANIFEST_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString
from .experiment_artifacts import ExperimentArtifactRefModel
from .experiment_references import AssociatedArtifactParentReferenceModel
from .schema_invariants import _add_raes_invariant

AssociatedArtifactSetDigestString = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]


def _validate_associated_artifact_uri(artifact_id: str, uri: str) -> None:
    validate_safe_absolute_uri(uri, field_name=f"associated artifact {artifact_id!r} uri")


class AssociatedArtifactManifestModel(ContractModel):
    """One exact non-semantic artifact-reference set attached to one parent."""

    schema_version: Literal[ASSOCIATED_ARTIFACT_MANIFEST_SCHEMA_VERSION]
    manifest_id: NonEmptyString
    manifest_version: NonEmptyString
    canonicalization_profile: Literal["associated-artifact-set/v1"]
    scope: Literal["scenario", "experiment"]
    parent_ref: AssociatedArtifactParentReferenceModel
    artifacts: dict[NonEmptyString, ExperimentArtifactRefModel] = Field(min_length=1)
    set_digest: AssociatedArtifactSetDigestString

    @model_validator(mode="after")
    def _validate_associated_artifact_manifest(self) -> AssociatedArtifactManifestModel:
        scenario_kinds = {"scenario", "scenario-snapshot", "materialization-attestation"}
        parent_is_scenario = self.parent_ref.ref_kind in scenario_kinds
        if (self.scope == "scenario") != parent_is_scenario:
            raise ValueError("associated-artifact scope and parent kind must agree")

        descriptor_owners: dict[tuple[Any, ...], str] = {}
        locator_claims: dict[str, tuple[Any, ...]] = {}
        for artifact_key, artifact in self.artifacts.items():
            if artifact_key != artifact.artifact_id:
                raise ValueError(
                    f"associated artifact map key {artifact_key!r} must equal embedded artifact_id "
                    f"{artifact.artifact_id!r}"
                )
            _validate_associated_artifact_uri(artifact.artifact_id, artifact.uri)
            descriptor_key = (
                artifact.role,
                artifact.media_type,
                artifact.uri,
                artifact.checksum.algorithm,
                artifact.checksum.value.casefold(),
                artifact.size_bytes,
                artifact.created_at,
                artifact.source,
                tuple(ref.model_dump_json() for ref in artifact.satisfies_refs),
                artifact.sensitivity,
                artifact.description,
            )
            prior_descriptor_owner = descriptor_owners.get(descriptor_key)
            if prior_descriptor_owner is not None:
                raise ValueError(
                    f"associated artifacts {prior_descriptor_owner!r} and {artifact.artifact_id!r} are exact "
                    "descriptor aliases; duplicate descriptors require one stable artifact id"
                )
            descriptor_owners[descriptor_key] = artifact.artifact_id

            locator_claim = (
                artifact.media_type,
                artifact.checksum.algorithm,
                artifact.checksum.value.casefold(),
                artifact.size_bytes,
            )
            prior_locator_claim = locator_claims.get(artifact.uri)
            if prior_locator_claim is not None and prior_locator_claim != locator_claim:
                raise ValueError("one associated-artifact locator must not carry conflicting payload claims")
            locator_claims[artifact.uri] = locator_claim
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {"properties": {"scope": {"const": "scenario"}}, "required": ["scope"]},
                    "then": {
                        "properties": {
                            "parent_ref": {
                                "properties": {
                                    "ref_kind": {
                                        "enum": ["scenario", "scenario-snapshot", "materialization-attestation"]
                                    },
                                }
                            }
                        }
                    },
                },
                {
                    "if": {"properties": {"scope": {"const": "experiment"}}, "required": ["scope"]},
                    "then": {
                        "properties": {
                            "parent_ref": {
                                "properties": {
                                    "ref_kind": {
                                        "enum": ["task", "authoring-input", "apparatus-context", "run", "study"]
                                    },
                                }
                            }
                        }
                    },
                },
            ]
        )
        _add_raes_invariant(
            json_schema,
            "associated-artifact-parent-set-and-byte-binding",
            "Full conformance requires matching the concrete parent, recomputing the canonical set digest, "
            "and binding every checksum and size to an explicitly supplied bounded byte stream.",
            validator="raes_contracts.associated_artifacts.validate_associated_artifact_manifest",
            inputs=[{"contract_id": "associated-artifact-manifest-v1", "instance_path": "#"}],
        )
        return json_schema
