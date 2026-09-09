"""Authored participant action-contract models (ACT-602, SEM-208, SEM-211).

Action-argument domains, the interaction declaration, and the governed
:class:`ParticipantActionContract`. Typed preconditions/effects/failure mappings
remain owned by :mod:`raes.participant_action_semantics`; temporal payloads by
:mod:`raes.participant_temporal_semantics`.
"""

from enum import Enum
from math import isfinite

from pydantic import Field, field_validator, model_validator
from typing_extensions import TypeAliasType

from .._base import SDLModel
from .._classification_guard import LegacyClassificationGuard
from .._identifiers import PortableIdentifier
from ..participant_action_semantics import (
    ParticipantActionEffect,
    ParticipantActionPrecondition,
    ParticipantBackendFailureMapping,
    ParticipantFailureClass,
)
from ..participant_temporal_semantics import (
    ParticipantBackendTimingDisclosure,
    ParticipantTemporalContract,
    validate_action_contract_temporal_payload,
)


class ParticipantActionLifecycle(str, Enum):
    """Governance lifecycle for participant action contracts."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class ParticipantActionGranularity(str, Enum):
    """Behavioral granularity of a participant action contract."""

    ATOMIC = "atomic"
    PROCEDURE = "procedure"
    AGGREGATE = "aggregate"


class ParticipantActionArgumentValueType(str, Enum):
    """Portable JSON value families admitted by an action argument."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    REFERENCE = "reference"


class ParticipantActionArgumentCardinality(str, Enum):
    """Whether an action argument carries one value or a bounded collection."""

    ONE = "one"
    MANY = "many"


class ParticipantActionArgumentNormalization(str, Enum):
    """Portable normalization operations with explicit disclosure."""

    IDENTITY = "identity"
    TRIM = "trim"


class ParticipantActionArgumentOmission(str, Enum):
    """Portable handling for an omitted action argument."""

    REJECT = "reject"
    USE_DEFAULT = "use_default"
    OMIT = "omit"


ParticipantActionArgumentScalar = TypeAliasType(
    "ParticipantActionArgumentScalar",
    str | int | float | bool,
)
ParticipantActionArgumentAuthoredValue = TypeAliasType(
    "ParticipantActionArgumentAuthoredValue",
    ParticipantActionArgumentScalar | list[ParticipantActionArgumentScalar],
)


def _participant_argument_scalar_matches(
    value: object,
    value_type: ParticipantActionArgumentValueType,
) -> bool:
    if value_type in {
        ParticipantActionArgumentValueType.STRING,
        ParticipantActionArgumentValueType.REFERENCE,
    }:
        matches = isinstance(value, str)
    elif value_type == ParticipantActionArgumentValueType.INTEGER:
        matches = isinstance(value, int) and not isinstance(value, bool)
    elif value_type == ParticipantActionArgumentValueType.NUMBER:
        matches = isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
    else:
        matches = isinstance(value, bool)
    return matches


def _participant_argument_values_equal(
    left: ParticipantActionArgumentScalar,
    right: ParticipantActionArgumentScalar,
) -> bool:
    return type(left) is type(right) and left == right


class ParticipantActionArgumentDefinition(SDLModel):
    """Closed authored domain for one non-secret portable action argument."""

    value_type: ParticipantActionArgumentValueType
    cardinality: ParticipantActionArgumentCardinality = ParticipantActionArgumentCardinality.ONE
    default: str | int | float | bool | list[str | int | float | bool] | None = None
    allowed_values: list[str | int | float | bool] = Field(default_factory=list)
    minimum: int | float | None = None
    maximum: int | float | None = None
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=0)
    min_items: int | None = Field(default=None, ge=0)
    max_items: int | None = Field(default=None, ge=0)
    unique_items: bool = True
    normalization: ParticipantActionArgumentNormalization
    normalization_disclosure_ref: str
    omission: ParticipantActionArgumentOmission
    omission_disclosure_ref: str
    default_disclosure_ref: str | None = None
    loss_disclosure_ref: str

    @field_validator(
        "normalization_disclosure_ref",
        "omission_disclosure_ref",
        "default_disclosure_ref",
        "loss_disclosure_ref",
    )
    @classmethod
    def _require_non_empty_disclosures(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("participant action argument disclosure refs must be non-empty")
        return value

    @model_validator(mode="after")
    def _validate_argument_domain(self) -> "ParticipantActionArgumentDefinition":
        self._normalize_domain_literals()
        self._validate_cardinality()
        self._validate_type_specific_constraints()
        self._validate_allowed_values()
        self._validate_omission()
        return self

    def _normalize_domain_literals(self) -> None:
        if self.normalization != ParticipantActionArgumentNormalization.TRIM:
            return
        self.allowed_values = [value.strip() if isinstance(value, str) else value for value in self.allowed_values]
        if isinstance(self.default, list):
            self.default = [value.strip() if isinstance(value, str) else value for value in self.default]
        elif isinstance(self.default, str):
            self.default = self.default.strip()

    def _validate_cardinality(self) -> None:
        if self.cardinality == ParticipantActionArgumentCardinality.ONE:
            self._validate_single_cardinality()
            return
        self._validate_many_cardinality()

    def _validate_single_cardinality(self) -> None:
        if self.min_items is not None or self.max_items is not None:
            raise ValueError("min_items and max_items require cardinality many")
        if isinstance(self.default, list):
            raise ValueError("single-valued argument default must be a scalar")

    def _validate_many_cardinality(self) -> None:
        if self.min_items is not None and self.max_items is not None and self.min_items > self.max_items:
            raise ValueError("min_items must not exceed max_items")
        if self.default is not None and not isinstance(self.default, list):
            raise ValueError("many-valued argument default must be a list")
        if isinstance(self.default, list):
            self._validate_collection(self.default, field_name="default")

    def _validate_type_specific_constraints(self) -> None:
        self._validate_numeric_constraints()
        self._validate_text_constraints()
        self._validate_reference_normalization()

    def _validate_numeric_constraints(self) -> None:
        numeric = self.value_type in {
            ParticipantActionArgumentValueType.INTEGER,
            ParticipantActionArgumentValueType.NUMBER,
        }
        if not numeric and (self.minimum is not None or self.maximum is not None):
            raise ValueError("minimum and maximum require an integer or number argument")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")

    def _validate_text_constraints(self) -> None:
        textual = self.value_type in {
            ParticipantActionArgumentValueType.STRING,
            ParticipantActionArgumentValueType.REFERENCE,
        }
        if not textual and (self.min_length is not None or self.max_length is not None):
            raise ValueError("min_length and max_length require a string or reference argument")
        if self.min_length is not None and self.max_length is not None and self.min_length > self.max_length:
            raise ValueError("min_length must not exceed max_length")

    def _validate_reference_normalization(self) -> None:
        if self.value_type == ParticipantActionArgumentValueType.REFERENCE and (
            self.normalization != ParticipantActionArgumentNormalization.IDENTITY
        ):
            raise ValueError("reference arguments require identity normalization")

    def _validate_allowed_values(self) -> None:
        for index, value in enumerate(self.allowed_values):
            self._validate_scalar(value, field_name="allowed_values")
            if any(_participant_argument_values_equal(value, prior) for prior in self.allowed_values[:index]):
                raise ValueError("allowed_values must not contain duplicates")
        if self.default is None:
            return
        values = self.default if isinstance(self.default, list) else [self.default]
        for value in values:
            self._validate_scalar(value, field_name="default")
            if self.allowed_values and not any(
                _participant_argument_values_equal(value, allowed) for allowed in self.allowed_values
            ):
                raise ValueError("default must satisfy allowed_values")

    def _validate_omission(self) -> None:
        if self.omission == ParticipantActionArgumentOmission.USE_DEFAULT:
            if self.default is None or self.default_disclosure_ref is None:
                raise ValueError("use_default omission requires a default and default_disclosure_ref")
        elif self.default is not None or self.default_disclosure_ref is not None:
            raise ValueError("defaults require use_default omission")

    def _validate_collection(
        self,
        values: list[ParticipantActionArgumentScalar],
        *,
        field_name: str,
    ) -> None:
        if self.min_items is not None and len(values) < self.min_items:
            raise ValueError(f"{field_name} must satisfy min_items")
        if self.max_items is not None and len(values) > self.max_items:
            raise ValueError(f"{field_name} must satisfy max_items")
        if self.unique_items:
            for index, value in enumerate(values):
                if any(_participant_argument_values_equal(value, prior) for prior in values[:index]):
                    raise ValueError(f"{field_name} entries must be unique")
        for value in values:
            self._validate_scalar(value, field_name=field_name)

    def _validate_scalar(
        self,
        value: ParticipantActionArgumentScalar,
        *,
        field_name: str,
    ) -> None:
        if not _participant_argument_scalar_matches(value, self.value_type):
            raise ValueError(f"{field_name} must match argument value_type {self.value_type.value}")
        self._validate_scalar_length(value, field_name)
        self._validate_scalar_range(value, field_name)

    def _validate_scalar_length(
        self,
        value: ParticipantActionArgumentScalar,
        field_name: str,
    ) -> None:
        if not isinstance(value, str):
            return
        if self.min_length is not None and len(value) < self.min_length:
            raise ValueError(f"{field_name} must satisfy min_length")
        if self.max_length is not None and len(value) > self.max_length:
            raise ValueError(f"{field_name} must satisfy max_length")

    def _validate_scalar_range(
        self,
        value: ParticipantActionArgumentScalar,
        field_name: str,
    ) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{field_name} must satisfy minimum")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{field_name} must satisfy maximum")


class ParticipantInteractionClass(str, Enum):
    """SEM-209 interaction classes for multi-participant behavior."""

    COORDINATION = "coordination"
    CONTENTION = "contention"
    INTERFERENCE = "interference"
    SHARED_STATE_CHANGE = "shared_state_change"


class ExternalMappingLoss(SDLModel):
    """Historical mapping syntax, retained solely for explicit migration."""

    system: str
    identifier: str
    loss_label: str
    rationale: str

    @field_validator("system", "identifier", "loss_label", "rationale")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("external mapping fields must be non-empty")
        return value


class ParticipantInteractionDeclaration(SDLModel):
    """Declared interaction semantics for a participant action contract."""

    interaction_class: ParticipantInteractionClass
    target: str
    rationale: str
    related_actions: list[str] = Field(default_factory=list)
    shared_state_refs: list[str] = Field(default_factory=list)
    commutative: bool = False
    merge_rule_ref: str | None = None

    @field_validator("target", "rationale")
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant interaction fields must be non-empty")
        return value

    @field_validator("merge_rule_ref")
    @classmethod
    def _require_non_empty_merge_rule(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("participant interaction merge_rule_ref must be non-empty")
        return value

    @field_validator("related_actions", "shared_state_refs")
    @classmethod
    def _require_non_empty_items(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("participant interaction references must be non-empty")
        return values

    @model_validator(mode="after")
    def _validate_sem209_class_payload(self) -> "ParticipantInteractionDeclaration":
        if self.commutative and self.merge_rule_ref is not None:
            raise ValueError("participant interaction must declare commutativity or a merge rule, not both")
        if (
            self.interaction_class
            in {
                ParticipantInteractionClass.COORDINATION,
                ParticipantInteractionClass.INTERFERENCE,
            }
            and not self.related_actions
        ):
            raise ValueError(f"{self.interaction_class.value} interactions require related_actions")
        if (
            self.interaction_class
            in {
                ParticipantInteractionClass.CONTENTION,
                ParticipantInteractionClass.SHARED_STATE_CHANGE,
            }
            and not self.shared_state_refs
        ):
            raise ValueError(f"{self.interaction_class.value} interactions require shared_state_refs")
        return self


class ParticipantActionContract(LegacyClassificationGuard):
    """Governed semantic contract for one participant action name."""

    legacy_classification_fields = ("external_mappings",)

    semantic_version: str
    lifecycle_state: ParticipantActionLifecycle = ParticipantActionLifecycle.ACTIVE
    behavioral_granularity: ParticipantActionGranularity
    procedure_basis: str
    realization_profile: str
    fidelity_claim: str
    arguments: dict[PortableIdentifier, ParticipantActionArgumentDefinition] = Field(default_factory=dict)
    preconditions: list[ParticipantActionPrecondition] = Field(default_factory=list)
    effects: list[ParticipantActionEffect] = Field(default_factory=list)
    state_transition_effects: list[str] = Field(default_factory=list)
    observation_expectations: list[str] = Field(default_factory=list)
    evidence_expectations: list[str] = Field(default_factory=list)
    failure_classes: list[ParticipantFailureClass] = Field(default_factory=list)
    backend_failure_mappings: list[ParticipantBackendFailureMapping] = Field(default_factory=list)
    interactions: list[ParticipantInteractionDeclaration] = Field(default_factory=list)
    temporal_contracts: list[ParticipantTemporalContract] = Field(default_factory=list)
    backend_timing_disclosures: list[ParticipantBackendTimingDisclosure] = Field(default_factory=list)

    @field_validator(
        "semantic_version",
        "procedure_basis",
        "realization_profile",
        "fidelity_claim",
    )
    @classmethod
    def _require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("participant action contract fields must be non-empty")
        return value

    @field_validator(
        "state_transition_effects",
        "observation_expectations",
        "evidence_expectations",
    )
    @classmethod
    def _require_non_empty_items(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value.strip():
                raise ValueError("participant action contract list entries must be non-empty")
        if len(set(values)) != len(values):
            raise ValueError("participant action contract list entries must be unique")
        return values

    @model_validator(mode="after")
    def _validate_sem211_payload(self) -> "ParticipantActionContract":
        if not self.preconditions:
            raise ValueError("participant action contracts require typed preconditions")
        if not self.effects:
            raise ValueError("participant action contracts require typed effects")
        if not self.failure_classes:
            raise ValueError("participant action contracts require controlled failure_classes")
        precondition_ids = [item.precondition_id for item in self.preconditions]
        if len(set(precondition_ids)) != len(precondition_ids):
            raise ValueError("participant action precondition_id values must be unique")
        effect_ids = [item.effect_id for item in self.effects]
        if len(set(effect_ids)) != len(effect_ids):
            raise ValueError("participant action effect_id values must be unique")
        if len(set(self.failure_classes)) != len(self.failure_classes):
            raise ValueError("participant action failure_classes must be unique")
        mapped_codes = [mapping.backend_error_code for mapping in self.backend_failure_mappings]
        if len(set(mapped_codes)) != len(mapped_codes):
            raise ValueError("participant backend_failure_mappings backend_error_code values must be unique")
        declared_failures = set(self.failure_classes)
        for mapping in self.backend_failure_mappings:
            if mapping.failure_class not in declared_failures:
                raise ValueError(
                    f"backend failure mapping {mapping.backend_error_code!r} "
                    f"uses undeclared failure_class {mapping.failure_class.value!r}"
                )
        validate_action_contract_temporal_payload(
            preconditions=self.preconditions,
            temporal_contracts=self.temporal_contracts,
            backend_timing_disclosures=self.backend_timing_disclosures,
        )
        return self
