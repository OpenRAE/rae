"""EXP-718 versioned random-stream contracts: profile shape, control binding, and draw provenance.

Builds strictly within ``raes_contracts`` (ADR-036's portable DTO/profile-shape
bucket): selection/compilation (``raes_processor``) and live execution
(``raes_runtime``) are out of scope here (#787-#791). See
``docs/decisions/issue-274-exp-718-controlled-randomness-preflight.md`` and
ADR-084 Section 5 / ``specs/formal/scenario-variation-trial-realization``
SVR-012 through SVR-017 for the governing invariants:

* a seed alone, without generator/derivation/transform identity, is not
  executable stochastic control (``RandomStreamControlBindingModel`` requires
  an admitted ``profile_ref``);
* the stream address is a closed typed DTO derived only from the randomness
  namespace, logical trial coordinate, policy id, variation-point id, draw
  purpose, and a stable local draw coordinate -- never worker/process/thread,
  wall time, retry count, or the aggregate experiment digest
  (``StreamAddressModel``, ``extra="forbid"``);
* sensitive root entropy and sensitive draw outcomes are closed two-kind
  unions where the governed variant carries only an immutable reference id and
  version, never raw bytes or a resolved value (``GovernedEntropyRefModel``,
  ``GovernedRandomOutcomeRefModel``).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from raes.identifiers import PortableIdentifier

from ..versions import RANDOM_STREAM_PROFILE_SCHEMA_VERSION, RANDOM_STREAM_VECTOR_SCHEMA_VERSION
from .base import ContractModel, NonEmptyString, NonNegativeInteger, PositiveInteger, SemanticProfileId
from .experiment_references import ExperimentReferenceModel
from .schema_invariants import _add_raes_invariant
from .validators import _validate_controlled_vocabulary_terms

RANDOM_STREAM_DRAW_PURPOSE_SCOPE = "random_streams.draw_purpose"

#: BLAKE3 key size (32 bytes), encoded as fixed-width lowercase hex.
PUBLIC_SEED_HEX_LENGTH = 64

_PUBLIC_SEED_HEX_PATTERN = rf"^[0-9a-f]{{{PUBLIC_SEED_HEX_LENGTH}}}$"


class PublicSeedModel(ContractModel):
    """Inline public root-entropy seed: fixed-width canonical hex bytes.

    Fixed-width lowercase hex removes leading-zero, integer-width, sign, and
    Unicode ambiguity from the executable entropy encoding (per the EXP-718
    preflight's "Canonical Inputs" section).
    """

    kind: Literal["public-seed"]
    encoding: Literal["hex-fixed-width"]
    value: NonEmptyString = Field(pattern=_PUBLIC_SEED_HEX_PATTERN)


class GovernedEntropyRefModel(ContractModel):
    """Governed reference to sensitive root entropy; never carries raw bytes.

    Raw entropy is resolved only at an authorized in-process boundary (out of
    scope here) and is never serialized back into this model, a diagnostic, a
    fixture, argv, or telemetry (SVR-028).
    """

    kind: Literal["governed-reference"]
    reference_id: NonEmptyString
    reference_version: NonEmptyString


RootEntropyModel = Annotated[
    PublicSeedModel | GovernedEntropyRefModel,
    Field(discriminator="kind"),
]


class PublicRandomOutcomeModel(ContractModel):
    """Public drawn value, recorded as canonical text."""

    kind: Literal["public-value"]
    value: NonEmptyString


class GovernedRandomOutcomeRefModel(ContractModel):
    """Governed reference to a sensitive drawn outcome; never carries the raw value."""

    kind: Literal["governed-reference"]
    reference_id: NonEmptyString
    reference_version: NonEmptyString


RandomDrawOutcomeModel = Annotated[
    PublicRandomOutcomeModel | GovernedRandomOutcomeRefModel,
    Field(discriminator="kind"),
]


class RandomStreamProfileReferenceModel(ExperimentReferenceModel):
    """Reference constrained to an accepted random-stream profile."""

    ref_kind: Literal["profile"]


class TrialCoordinateModel(ContractModel):
    """Logical trial coordinate dimensions usable in a random-stream address.

    Every field is an optional portable identifier: an experiment declares
    only the dimensions it actually varies (SVR-013's "logical trial
    coordinate").
    """

    condition_id: PortableIdentifier | None = None
    block_id: PortableIdentifier | None = None
    replicate_id: PortableIdentifier | None = None


class StreamAddressModel(ContractModel):
    """Closed semantic random-draw address (SVR-013).

    A pure canonical function of the randomness namespace, logical trial
    coordinate, selection-policy id, variation-point id, draw purpose, and a
    stable local draw coordinate. It is not a concatenated string, arbitrary
    mapping, JSON Pointer, or scheduler/compiled-runtime address, and it
    admits no worker/process/thread/host, wall-time, retry, or aggregate
    experiment-digest field (``extra="forbid"`` closes the shape).
    """

    namespace: PortableIdentifier
    trial_coordinate: TrialCoordinateModel
    selection_policy_id: PortableIdentifier
    variation_point_id: PortableIdentifier
    draw_purpose: PortableIdentifier
    local_coordinate: NonNegativeInteger

    @model_validator(mode="after")
    def _validate_draw_purpose(self) -> StreamAddressModel:
        _validate_controlled_vocabulary_terms(RANDOM_STREAM_DRAW_PURPOSE_SCOPE, [self.draw_purpose])
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "random-stream-address-draw-purpose-governed",
            "draw_purpose must be a term from the random_streams.draw_purpose controlled vocabulary.",
            inputs=[{"contract_id": "controlled-vocabularies-v1", "instance_path": "#"}],
        )
        return json_schema


class ParticipantStreamAddressModel(ContractModel):
    """Closed within-run address for one participant-policy draw."""

    namespace: PortableIdentifier
    policy_address: NonEmptyString
    participant_address: NonEmptyString
    time_segment: NonNegativeInteger
    occurrence_ordinal: NonNegativeInteger
    draw_purpose: PortableIdentifier
    local_coordinate: NonNegativeInteger

    @model_validator(mode="after")
    def _validate_address(self) -> ParticipantStreamAddressModel:
        _validate_controlled_vocabulary_terms(RANDOM_STREAM_DRAW_PURPOSE_SCOPE, [self.draw_purpose])
        if not self.policy_address.startswith("participant.autonomous-execution."):
            raise ValueError("participant stream policy_address must be a compiled autonomous-execution address")
        if not self.participant_address.startswith("participant.behavior."):
            raise ValueError("participant stream participant_address must be a compiled participant address")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "participant-random-stream-address-governed",
            (
                "draw_purpose must be governed and policy_address/participant_address must be compiled "
                "autonomous participant addresses."
            ),
            inputs=[{"contract_id": "controlled-vocabularies-v1", "instance_path": "#"}],
        )
        return json_schema


class RandomStreamControlBindingModel(ContractModel):
    """Executable binding: profile identity, namespace, and root entropy.

    A seed alone, without generator/derivation/transform identity, is not a
    reproducibility claim (SVR-012). ``profile_ref`` is required and
    structurally constrained to ``ref_kind="profile"``.
    """

    profile_ref: RandomStreamProfileReferenceModel
    namespace: PortableIdentifier
    root_entropy: RootEntropyModel


class RandomStreamGeneratorModel(ContractModel):
    """Generator family, exact version, and mode fixed by an accepted profile."""

    family: NonEmptyString
    version: NonEmptyString
    mode: NonEmptyString


class RandomStreamRootEntropySpecModel(ContractModel):
    """Root-entropy type, length, and canonical byte encoding fixed by an accepted profile."""

    encoding: NonEmptyString
    byte_length: PositiveInteger


class RandomStreamAddressEncodingSpecModel(ContractModel):
    """Canonical semantic-address byte encoding fixed by an accepted profile."""

    canonicalization: NonEmptyString


class RandomStreamDerivationSpecModel(ContractModel):
    """Key/child-stream derivation function and domain-separation context fixed by an accepted profile."""

    key_derivation_function: NonEmptyString
    context_template: NonEmptyString


class RandomStreamBlockEncodingSpecModel(ContractModel):
    """Raw-block byte length and byte order fixed by an accepted profile."""

    block_bytes: PositiveInteger
    byte_order: Literal["big-endian", "little-endian"]


class RandomStreamTransformSpecModel(ContractModel):
    """One admitted bounded transform, its version, and its rejection/exhaustion budget."""

    transform_id: NonEmptyString
    version: NonEmptyString
    kind: NonEmptyString
    max_rejection_attempts: PositiveInteger


class RandomStreamProfileModel(ContractModel):
    """Published random-stream profile: one closed, immutable compatibility unit.

    Changing any field mints a new ``profile_id`` (the EXP-718 preflight's "One
    Profile And One Stateless API" section). This model's JSON Schema is
    generated via ``schema_bundle()``, never hand-authored.
    """

    schema_version: Literal[RANDOM_STREAM_PROFILE_SCHEMA_VERSION]
    profile_id: SemanticProfileId
    title: NonEmptyString
    description: NonEmptyString
    generator: RandomStreamGeneratorModel
    root_entropy: RandomStreamRootEntropySpecModel
    address_encoding: RandomStreamAddressEncodingSpecModel
    derivation: RandomStreamDerivationSpecModel
    block_encoding: RandomStreamBlockEncodingSpecModel
    transforms: dict[NonEmptyString, RandomStreamTransformSpecModel] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_transform_keys(self) -> RandomStreamProfileModel:
        mismatched = sorted(key for key, transform in self.transforms.items() if transform.transform_id != key)
        if mismatched:
            joined = ", ".join(mismatched)
            raise ValueError(f"random stream profile transforms keys must match embedded transform_id: {joined}")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "random-stream-profile-transform-keys-match",
            "transforms dict keys must match each entry's embedded transform_id.",
            inputs=[{"contract_id": "random-stream-profile-v1", "instance_path": "#/transforms"}],
        )
        return json_schema


class RandomStreamDrawRecordModel(ContractModel):
    """Archival draw provenance: address, transform identity, outcome, and rejection facts.

    References its control rather than duplicating the root seed for every
    draw, and never exposes raw generator blocks outside the conformance
    vector corpus.
    """

    control_id: NonEmptyString
    address: StreamAddressModel
    transform_id: NonEmptyString
    transform_version: NonEmptyString
    local_coordinate: NonNegativeInteger
    outcome: RandomDrawOutcomeModel | None = None
    rejection_attempts: NonNegativeInteger = 0
    rejection_exhausted: bool = False

    @model_validator(mode="after")
    def _validate_local_coordinate_matches_address(self) -> RandomStreamDrawRecordModel:
        if self.local_coordinate != self.address.local_coordinate:
            raise ValueError("stochastic draw record local_coordinate must match address.local_coordinate")
        return self

    @model_validator(mode="after")
    def _validate_outcome_matches_exhaustion(self) -> RandomStreamDrawRecordModel:
        if self.rejection_exhausted and self.outcome is not None:
            raise ValueError("stochastic draw record must omit outcome when rejection_exhausted is true")
        if not self.rejection_exhausted and self.outcome is None:
            raise ValueError("stochastic draw record must include outcome when rejection_exhausted is false")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema)
        json_schema = handler.resolve_ref_schema(json_schema)
        _add_raes_invariant(
            json_schema,
            "random-stream-draw-record-local-coordinate-matches-address",
            "local_coordinate must match address.local_coordinate.",
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#/stochastic_draws"}],
        )
        _add_raes_invariant(
            json_schema,
            "random-stream-draw-record-outcome-matches-exhaustion",
            "outcome must be present exactly when rejection_exhausted is false, and absent when true.",
            inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#/stochastic_draws"}],
        )
        return json_schema


class RandomStreamBoundedIntegerVectorCaseModel(ContractModel):
    """One bounded-integer transform vector case nested inside a vector file."""

    transform_id: NonEmptyString
    transform_version: NonEmptyString
    minimum: int
    maximum: int
    max_rejection_attempts: PositiveInteger
    expected_rejection_attempts: NonNegativeInteger
    expected_rejection_exhausted: bool
    outcome: RandomDrawOutcomeModel | None = None

    @model_validator(mode="after")
    def _validate_bounds_and_outcome(self) -> RandomStreamBoundedIntegerVectorCaseModel:
        if self.maximum < self.minimum:
            raise ValueError("random stream vector bounded-integer case requires maximum >= minimum")
        if self.expected_rejection_exhausted and self.outcome is not None:
            raise ValueError("random stream vector bounded-integer exhaustion case must not include an outcome")
        if not self.expected_rejection_exhausted and self.outcome is None:
            raise ValueError("random stream vector bounded-integer non-exhausted case must include an outcome")
        return self


class RandomStreamVectorModel(ContractModel):
    """One canonical cross-language conformance vector case.

    Computed independently of the reference engine (a throwaway script that
    calls the ``blake3`` library directly), so the vector tests do not just
    test the engine against itself.
    """

    schema_version: Literal[RANDOM_STREAM_VECTOR_SCHEMA_VERSION]
    vector_id: NonEmptyString
    description: NonEmptyString
    profile_id: SemanticProfileId
    root_entropy: PublicSeedModel
    stream_key_hex: NonEmptyString = Field(pattern=_PUBLIC_SEED_HEX_PATTERN)
    address: StreamAddressModel | ParticipantStreamAddressModel
    address_canonical_bytes_hex: NonEmptyString
    raw_block_hex: NonEmptyString
    transform: RandomStreamBoundedIntegerVectorCaseModel | None = None
