"""Authored safe-state intent and resolved proof, independent of effect permission."""

from typing import Annotated, Literal, Self

from pydantic import BeforeValidator, ConfigDict, Field, model_validator

from ._base import ContractModel
from .evidence_requirements import EvidenceRequirement
from .execution_policy import PolicyNamespace
from .observation_demand import SemanticScope
from .propositions import Assertion, AssertionPolarity, AssertionRole, Proposition, PropositionBasis, SubjectQuantifier
from .realization_structure import semantic_address_contains, validate_realization_value
from .runtime_value_limits import PLAN_VALUE_LIMITS
from .safe_state_schema import safe_state_schema

SafeStateReference = Annotated[str, Field(min_length=1, max_length=2048, pattern=r"^\S+$")]


class SafeState(ContractModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", json_schema_extra=safe_state_schema
    )
    schema_version: Literal["safe-state/v1"] = "safe-state/v1"
    kind: Literal["safe-hold", "controlled-stop", "continue"]
    continuing_mode: SafeStateReference | None = None
    assertion_refs: tuple[SafeStateReference, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _complete_state(self) -> Self:
        if (self.kind == "continue") != (self.continuing_mode is not None):
            raise ValueError("continuing mode is required only for a continuing safe state")
        if len(set(self.assertion_refs)) != len(self.assertion_refs):
            raise ValueError("safe-state assertions must be unique")
        return self


class SafeStateScope(ContractModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", json_schema_extra=safe_state_schema
    )
    namespace: tuple[PolicyNamespace, ...] = Field(default=(), max_length=31)
    scope: SemanticScope = ""
    state: SafeState


class SafeStateDocument(ContractModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", json_schema_extra=safe_state_schema
    )
    default: SafeState | None = None
    scopes: tuple[SafeStateScope, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def _unique_scopes(self) -> Self:
        identities = [(rule.namespace, rule.scope) for rule in self.scopes]
        if len(set(identities)) != len(identities) or (self.default is not None and ((), "") in identities):
            raise ValueError("safe-state scopes must be unique")
        return self


class SafeStateProof(ContractModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", json_schema_extra=safe_state_schema
    )
    assertion: Assertion
    proposition: Proposition
    evidence_requirements: dict[SafeStateReference, EvidenceRequirement] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _observed_postcondition(self) -> Self:
        if (
            self.assertion.role is not AssertionRole.POSTCONDITION
            or self.assertion.polarity is not AssertionPolarity.POSITIVE
        ):
            raise ValueError("safe-state proof requires positive postconditions")
        if (
            self.proposition.basis is not PropositionBasis.OBSERVED_STATE
            or self.proposition.quantifier is not SubjectQuantifier.ALL
        ):
            raise ValueError("safe-state proof must observe every subject")
        if set(self.evidence_requirements) != set(self.proposition.evidence_requirements):
            raise ValueError("safe-state evidence must resolve exactly")
        return self


class ResolvedSafeState(ContractModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", json_schema_extra=safe_state_schema
    )
    target_ref: SafeStateReference
    scope: SemanticScope
    governing_scope: Annotated[str, Field(min_length=1, max_length=8192)]
    namespace: tuple[PolicyNamespace, ...] = Field(default=(), max_length=31)
    state: SafeState
    proofs: dict[SafeStateReference, SafeStateProof] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _resolved_proof(self) -> Self:
        if set(self.proofs) != set(self.state.assertion_refs):
            raise ValueError("safe-state assertions must resolve exactly")
        namespace, separator, defining = self.governing_scope.partition("#")
        defining = "" if defining == "/" else defining
        if not separator or namespace != ".".join(self.namespace):
            raise ValueError("safe-state lexical provenance is inconsistent")
        SafeStateScope(scope=defining, namespace=self.namespace, state=self.state)
        if not semantic_address_contains(defining, self.scope):
            raise ValueError("safe-state defining scope must contain its target")
        for proof in self.proofs.values():
            if self.target_ref not in proof.proposition.subjects:
                raise ValueError("safe-state proof must observe its exact target")
            for requirement in proof.evidence_requirements.values():
                if self.target_ref not in (*requirement.source_refs, *requirement.scope_refs):
                    raise ValueError("safe-state evidence must cover its exact target")
        return self


def _bounded_safe_state_input(value: object) -> object:
    if not validate_realization_value(value, limits=PLAN_VALUE_LIMITS, python_carriers=True).conformant:
        raise ValueError("safe-state collection exceeds aggregate plan limits")
    return value


SafeStates = Annotated[
    tuple[ResolvedSafeState, ...],
    Field(default=(), max_length=4096, exclude_if=lambda value: not value),
    BeforeValidator(_bounded_safe_state_input),
]


def validate_safe_states(states: tuple[ResolvedSafeState, ...]) -> None:
    if not isinstance(states, tuple) or len(states) > 4096:
        raise ValueError("safe-state collection must be a bounded tuple")
    if any(not isinstance(state, ResolvedSafeState) for state in states):
        raise TypeError("safe-state collection requires typed resolved declarations")
    _bounded_safe_state_input(states)
    validated = [ResolvedSafeState.model_validate(state.model_dump(mode="json")) for state in states]
    if len({state.target_ref for state in validated}) != len(validated):
        raise ValueError("safe-state targets must be unique")
