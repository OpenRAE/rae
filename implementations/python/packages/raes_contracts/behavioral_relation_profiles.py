"""Closed, corpus-backed parameter profiles for behavioral relations and their bounded loaders."""

from __future__ import annotations

import os
import stat
from functools import cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, GetJsonSchemaHandler, ValidationError, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from raes_contracts._base import ContractModel, NonEmptyString, PrefixedDigestString
from raes_contracts.behavioral_claims import BehavioralTaxonomyRevision
from raes_contracts.identifiers import is_portable_identifier

from ._participant_crossing_multi_profile import (
    MultiParticipantCrossingParametersModel,
    multi_crossing_profile_schema_join,
    validate_multi_crossing_profile_join,
)
from ._participant_crossing_profile import (
    HIDDEN,
    INPUT_CLASSES,
    VISIBLE,
    ParticipantCrossingParametersModel,
    crossing_profile_schema_join,
    validate_crossing_profile_join,
)
from .behavioral_authority_errors import BehavioralAuthorityArtifactError, BehavioralAuthorityUnsupportedError
from .canonical import canonical_json_digest
from .corpus import PROFILES, corpus_family_root
from .json_ingress import StrictJsonIngressError, parse_bounded_json_object
from .operational_logging import get_logger
from .versions import BEHAVIORAL_RELATION_PROFILE_SCHEMA_VERSION

ProfileId = Annotated[
    str,
    Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64),
]
SafeRef = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9._:/-]*$", max_length=256),
]
Revision = Annotated[
    str,
    Field(pattern=r"^[a-z0-9][a-z0-9._/-]*$", max_length=128),
]


def _require_sorted_unique(values: tuple[str, ...], label: str) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be unique and use canonical sorted order")


def _carrier_kind_condition(kind: str, *, nested: bool = False) -> dict[str, object]:
    carrier: dict[str, object] = {
        "properties": {"kind": {"const": kind}},
        "required": ["kind"],
    }
    if not nested:
        return {"properties": {"carrier": carrier}, "required": ["carrier"]}
    parameters = {"properties": {"carrier": carrier}, "required": ["carrier"]}
    return {"properties": {"parameters": parameters}, "required": ["parameters"]}


class BehavioralProfileSourceModel(ContractModel):
    """Immutable source identity used to reproduce one profile revision."""

    source_ref: SafeRef
    source_digest: PrefixedDigestString


class IndividualOpacityObserverModel(ContractModel):
    """One participant or audience observes the selected information cell."""

    kind: Literal["individual"]
    participant_ref: SafeRef
    audience_ref: SafeRef


class CoalitionOpacityObserverModel(ContractModel):
    """A declared coalition observes one explicitly fused information cell."""

    kind: Literal["coalition"]
    member_refs: tuple[SafeRef, ...] = Field(min_length=2, max_length=32)
    audience_ref: SafeRef
    fusion_rule_ref: SafeRef
    fusion_rule_revision: Revision

    @model_validator(mode="after")
    def _validate_members(self) -> CoalitionOpacityObserverModel:
        _require_sorted_unique(self.member_refs, "coalition member refs")
        return self


OpacityObserverModel = Annotated[
    IndividualOpacityObserverModel | CoalitionOpacityObserverModel,
    Field(discriminator="kind"),
]


class OpacitySecretPredicateModel(ContractModel):
    predicate_ref: SafeRef
    predicate_revision: Revision
    truth_polarity: Literal["one-sided-true"]


class FiniteOpacityCarrierModel(ContractModel):
    kind: Literal["finite-possible-points"]
    reachability_ref: SafeRef
    reachability_revision: Revision


class AbstractOpacityCarrierModel(ContractModel):
    """An abstract carrier whose proof obligations are discharged by a theorem session."""

    kind: Literal["abstract-possible-points"]
    reachability_ref: SafeRef
    reachability_revision: Revision
    eligibility_ref: SafeRef
    eligibility_revision: Revision
    correspondence_ref: SafeRef
    correspondence_revision: Revision


OpacityCarrierModel = Annotated[
    FiniteOpacityCarrierModel | AbstractOpacityCarrierModel,
    Field(discriminator="kind"),
]


class OpacityInitialInformationModel(ContractModel):
    projection_ref: SafeRef
    projection_revision: Revision


class OpacityObservationModel(ContractModel):
    projection_ref: SafeRef
    projection_revision: Revision
    observable_channels: tuple[
        Literal[
            "participant-state",
            "payload",
            "decision",
            "action-availability",
            "delivery",
            "retry",
            "latency",
            "order",
            "policy-release",
        ],
        ...,
    ] = Field(min_length=1, max_length=16)
    supervisor_decisions: Literal[
        "fully-known",
        "public-contract-hidden-realization",
        "online-learned",
        "selectively-disclosed",
    ]

    @model_validator(mode="after")
    def _validate_channels(self) -> OpacityObservationModel:
        _require_sorted_unique(self.observable_channels, "observable channels")
        return self


class OpacityHorizonModel(ContractModel):
    scope: Literal["current", "initial", "historical-k", "language"]
    cut_ref: SafeRef
    cut_revision: Revision
    steps: int | None = Field(default=None, ge=1, le=1024)

    @model_validator(mode="after")
    def _validate_steps(self) -> OpacityHorizonModel:
        if (self.scope == "historical-k") != (self.steps is not None):
            raise ValueError("historical-k horizon alone requires a positive steps bound")
        return self


class OpacityMemoryModel(ContractModel):
    retention: Literal["perfect", "cross-episode", "episode-local", "cut-local"]
    memory_ref: SafeRef
    memory_revision: Revision
    reset_rule_ref: SafeRef | None = None
    reset_rule_revision: Revision | None = None

    @model_validator(mode="after")
    def _validate_reset_rule(self) -> OpacityMemoryModel:
        if (self.reset_rule_ref is None) != (self.reset_rule_revision is None):
            raise ValueError("memory reset rule ref and revision must be supplied together")
        return self


class PassiveOpacityStrategyModel(ContractModel):
    kind: Literal["passive"]


class ActiveOpacityStrategyModel(ContractModel):
    kind: Literal["active"]
    strategy_refs: tuple[SafeRef, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_strategies(self) -> ActiveOpacityStrategyModel:
        _require_sorted_unique(self.strategy_refs, "active strategy refs")
        return self


OpacityStrategyModel = Annotated[
    PassiveOpacityStrategyModel | ActiveOpacityStrategyModel,
    Field(discriminator="kind"),
]


class OpacityReleaseModel(ContractModel):
    schedule_ref: SafeRef
    schedule_revision: Revision
    exact_cut: bool
    concealment_erases_retained_knowledge: Literal[False]


class OpacityOrderModel(ContractModel):
    treatment: Literal[
        "total-order",
        "named-linearization",
        "all-linearizations",
        "partial-order",
        "causal-frontier",
    ]
    order_refs: tuple[SafeRef, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_order_refs(self) -> OpacityOrderModel:
        _require_sorted_unique(self.order_refs, "order refs")
        return self


class OpacityTimeModel(ContractModel):
    model: Literal["untimed"]
    progress: Literal["progress-insensitive"]
    absence_observable: bool
    opportunity_basis_ref: SafeRef | None = None
    opportunity_basis_revision: Revision | None = None

    @model_validator(mode="after")
    def _validate_absence_basis(self) -> OpacityTimeModel:
        paired = (self.opportunity_basis_ref is None) == (self.opportunity_basis_revision is None)
        if not paired:
            raise ValueError("opportunity basis ref and revision must be supplied together")
        if self.absence_observable and self.opportunity_basis_ref is None:
            raise ValueError("observable absence requires a declared opportunity basis")
        if not self.absence_observable and self.opportunity_basis_ref is not None:
            raise ValueError("an opportunity basis is valid only when absence is observable")
        return self


class OpacityFiniteBoundsModel(ContractModel):
    max_points: int = Field(ge=1, le=100_000)
    max_runs: int = Field(ge=1, le=10_000)
    max_cuts: int = Field(ge=1, le=10_000)
    max_strategies: int = Field(ge=1, le=1_000)
    max_scheduler_environment_pairs: int = Field(ge=1, le=10_000)
    max_order_variants: int = Field(ge=1, le=1_000)


class ParticipantPredicateOpacityParametersModel(ContractModel):
    """Closed parameters for the SEM-231 one-sided possibilistic kernel."""

    kind: Literal["participant-predicate-opacity/v1"]
    observer: OpacityObserverModel
    secret: OpacitySecretPredicateModel
    carrier: OpacityCarrierModel
    initial_information: OpacityInitialInformationModel
    observation: OpacityObservationModel
    horizon: OpacityHorizonModel
    memory: OpacityMemoryModel
    strategy: OpacityStrategyModel
    release: OpacityReleaseModel
    scheduler_refs: tuple[SafeRef, ...] = Field(min_length=1, max_length=64)
    environment_refs: tuple[SafeRef, ...] = Field(min_length=1, max_length=64)
    nondeterminism: Literal["possibilistic-support"]
    order: OpacityOrderModel
    time: OpacityTimeModel
    probability: Literal["outside-baseline"]
    bounds: OpacityFiniteBoundsModel | None = None

    @model_validator(mode="after")
    def _validate_domains(
        self,
    ) -> ParticipantPredicateOpacityParametersModel:
        _require_sorted_unique(self.scheduler_refs, "scheduler refs")
        _require_sorted_unique(self.environment_refs, "environment refs")
        if isinstance(self.carrier, FiniteOpacityCarrierModel) and self.bounds is None:
            raise ValueError("finite opacity carriers require declared finite bounds")
        if isinstance(self.carrier, AbstractOpacityCarrierModel) and self.bounds is not None:
            raise ValueError("abstract theorem carriers must not declare finite bounds")
        strategy_count = (
            len(self.strategy.strategy_refs) if isinstance(self.strategy, ActiveOpacityStrategyModel) else 1
        )
        if self.bounds is None:
            return self
        if strategy_count > self.bounds.max_strategies:
            raise ValueError("declared strategies exceed the finite profile bound")
        if len(self.order.order_refs) > self.bounds.max_order_variants:
            raise ValueError("declared order variants exceed the finite profile bound")
        if len(self.scheduler_refs) * len(self.environment_refs) > self.bounds.max_scheduler_environment_pairs:
            raise ValueError("declared scheduler/environment pairs exceed the finite profile bound")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": _carrier_kind_condition("finite-possible-points"),
                    "then": {
                        "properties": {"bounds": {"type": "object"}},
                        "required": ["bounds"],
                    },
                },
                {
                    "if": _carrier_kind_condition("abstract-possible-points"),
                    "then": {"properties": {"bounds": {"type": "null"}}},
                },
            ]
        )
        return json_schema


class BehavioralRelationProfileModel(ContractModel):
    """One resolved relation profile with a closed parameter variant."""

    schema_version: Literal[BEHAVIORAL_RELATION_PROFILE_SCHEMA_VERSION] = BEHAVIORAL_RELATION_PROFILE_SCHEMA_VERSION
    profile_id: ProfileId
    profile_revision: Revision
    taxonomy_id: Literal["raes-behavioral-relations"]
    taxonomy_revision: BehavioralTaxonomyRevision
    relation_id: Literal["participant-predicate-opacity", "divergence-preserving-branching-bisimulation"]
    left_carrier_ref: SafeRef
    observation_projection_ref: SafeRef
    observation_projection_revision: Revision
    finite_analysis_scope: Literal[
        "declared-complete-finite-carrier",
        "abstract-parameterized-theorem-carrier",
    ]
    parameters: Annotated[
        ParticipantPredicateOpacityParametersModel
        | ParticipantCrossingParametersModel
        | MultiParticipantCrossingParametersModel,
        Field(discriminator="kind"),
    ]
    source_refs: tuple[BehavioralProfileSourceModel, ...] = Field(
        min_length=1,
        max_length=16,
    )
    limitations: tuple[NonEmptyString, ...] = Field(min_length=1, max_length=32)
    explicit_non_claims: tuple[NonEmptyString, ...] = Field(
        min_length=1,
        max_length=32,
    )

    @model_validator(mode="after")
    def _validate_profile_join(self) -> BehavioralRelationProfileModel:
        source_ids = tuple(item.source_ref for item in self.source_refs)
        _require_sorted_unique(source_ids, "profile source refs")
        if isinstance(self.parameters, ParticipantCrossingParametersModel):
            validate_crossing_profile_join(self)
            return self
        if isinstance(self.parameters, MultiParticipantCrossingParametersModel):
            validate_multi_crossing_profile_join(self)
            return self
        if self.relation_id != "participant-predicate-opacity":
            raise ValueError("opacity parameters require the opacity relation")
        if (
            self.parameters.observation.projection_ref != self.observation_projection_ref
            or self.parameters.observation.projection_revision != self.observation_projection_revision
        ):
            raise ValueError("profile observation projection must match the parameter projection")
        finite_variant = isinstance(self.parameters.carrier, FiniteOpacityCarrierModel)
        if finite_variant != (self.finite_analysis_scope == "declared-complete-finite-carrier"):
            raise ValueError("profile assurance scope must match its carrier variant")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler.resolve_ref_schema(handler(core_schema))
        json_schema.setdefault("allOf", []).append(crossing_profile_schema_join())
        json_schema["allOf"].append(multi_crossing_profile_schema_join())
        json_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": _carrier_kind_condition("finite-possible-points", nested=True),
                    "then": {"properties": {"finite_analysis_scope": {"const": "declared-complete-finite-carrier"}}},
                },
                {
                    "if": _carrier_kind_condition("abstract-possible-points", nested=True),
                    "then": {
                        "properties": {"finite_analysis_scope": {"const": "abstract-parameterized-theorem-carrier"}}
                    },
                },
            ]
        )
        return json_schema

    @property
    def canonical_digest(self) -> str:
        """Return the RFC 8785 digest of this exact profile revision."""

        return canonical_json_digest(self.model_dump(mode="json"))


_LOGGER = get_logger(__name__)
_MAX_PROFILE_BYTES = 256 * 1024
_PROFILE_INVALID = "behavioral relation profile JSON or contract is invalid"
SUPPORTED_BEHAVIORAL_RELATION_PROFILE_IDS = frozenset(
    {
        "participant-opacity-baseline-v1",
        "participant-opacity-runtime-reference-v1",
        "participant-opacity-theorem-v1",
        "participant-crossing-dpbb-finite-v1",
        "participant-crossing-multi-operation-dpbb-finite-v1",
    }
)


def behavioral_relation_profiles_root() -> Path:
    return corpus_family_root(PROFILES) / "behavioral-relation"


def _validate_profile_id(profile_id: str) -> None:
    if not is_portable_identifier(profile_id):
        raise BehavioralAuthorityUnsupportedError(
            "requested behavioral relation profile id must be a portable identifier"
        )
    if profile_id not in SUPPORTED_BEHAVIORAL_RELATION_PROFILE_IDS:
        raise BehavioralAuthorityUnsupportedError("requested behavioral relation profile is unsupported")


def behavioral_relation_profile_path(profile_id: str) -> Path:
    _validate_profile_id(profile_id)
    return behavioral_relation_profiles_root() / f"{profile_id}.json"


def load_behavioral_relation_profile_from_path(
    profile_id: str,
    path: Path,
) -> BehavioralRelationProfileModel:
    """Load one trusted profile path after strict bounded JSON ingress."""

    _validate_profile_id(profile_id)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise BehavioralAuthorityArtifactError(_PROFILE_INVALID)
            content = stream.read(_MAX_PROFILE_BYTES + 1)
        payload = parse_bounded_json_object(
            content,
            max_bytes=_MAX_PROFILE_BYTES,
        )
        profile = BehavioralRelationProfileModel.model_validate(payload)
    except OSError, StrictJsonIngressError, ValidationError:
        # A trusted profile path fails here only when the artifact or installation is damaged.
        _LOGGER.exception("behavioral relation profile %s failed bounded ingress", profile_id)
        raise BehavioralAuthorityArtifactError(_PROFILE_INVALID) from None
    if profile.profile_id != profile_id:
        raise BehavioralAuthorityArtifactError(
            "behavioral relation profile artifact identity does not match the requested profile"
        )
    return profile


@cache
def load_behavioral_relation_profile(
    profile_id: str,
) -> BehavioralRelationProfileModel:
    return load_behavioral_relation_profile_from_path(
        profile_id,
        behavioral_relation_profile_path(profile_id),
    )


_HISTORICAL_PROFILE_PATHS = {
    (
        "participant-opacity-baseline-v1",
        "sem-231/rev2",
    ): behavioral_relation_profiles_root() / "history" / "participant-opacity-baseline-v1-sem-231-rev2.json",
    (
        "participant-opacity-runtime-reference-v1",
        "sem-231/runtime-rev1",
    ): behavioral_relation_profiles_root()
    / "history"
    / "participant-opacity-runtime-reference-v1-sem-231-runtime-rev1.json",
}


@cache
def load_behavioral_relation_profile_revision(
    profile_id: str,
    profile_revision: str,
) -> BehavioralRelationProfileModel:
    """Resolve an exact immutable profile revision for evidence replay."""

    _validate_profile_id(profile_id)
    historical_path = _HISTORICAL_PROFILE_PATHS.get((profile_id, profile_revision))
    if historical_path is not None:
        profile = load_behavioral_relation_profile_from_path(profile_id, historical_path)
        if profile.profile_revision != profile_revision:
            raise BehavioralAuthorityArtifactError(
                "historical behavioral relation profile revision does not match its registry entry"
            )
        return profile
    current = load_behavioral_relation_profile(profile_id)
    if current.profile_revision == profile_revision:
        return current
    raise BehavioralAuthorityUnsupportedError("requested behavioral relation profile revision is unsupported")


__all__ = [
    "AbstractOpacityCarrierModel",
    "ActiveOpacityStrategyModel",
    "BehavioralRelationProfileModel",
    "CoalitionOpacityObserverModel",
    "FiniteOpacityCarrierModel",
    "HIDDEN",
    "INPUT_CLASSES",
    "MultiParticipantCrossingParametersModel",
    "OpacityFiniteBoundsModel",
    "ParticipantCrossingParametersModel",
    "ParticipantPredicateOpacityParametersModel",
    "SUPPORTED_BEHAVIORAL_RELATION_PROFILE_IDS",
    "VISIBLE",
    "behavioral_relation_profile_path",
    "behavioral_relation_profiles_root",
    "load_behavioral_relation_profile",
    "load_behavioral_relation_profile_from_path",
    "load_behavioral_relation_profile_revision",
]
