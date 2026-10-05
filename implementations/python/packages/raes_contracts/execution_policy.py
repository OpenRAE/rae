"""Portable author requirements; these values never authorize effects or trial allocation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator
from raes.evidence_requirements import EvidenceRequirement

from ._base import ContractModel
from .execution_policy_schema import execution_policy_schema
from .execution_retry import ExecutionRetryPolicyModel
from .observation_demand import SemanticScope
from .realization_structure import semantic_address_contains

EXECUTION_POLICY_VERSION = "execution-policy/v1"
WORKFLOW_SCOPE_PREFIX = "/workflows/"
WORKFLOW_STEP_SEGMENT = "/steps/"
PolicyIdentifier = Annotated[str, Field(min_length=1, max_length=256)]
PolicyLimit = Annotated[int, Field(strict=True, ge=1, le=9007199254740991)]
PolicyNamespace = Annotated[str, Field(pattern=r"^(?:[a-z0-9][a-z0-9_-]{0,63}|__private)$", max_length=64)]
FailureClass = Literal[
    "delivery", "backend-refusal", "operation", "intentional-fault", "continuity", "invalid-evidence"
]
RecoveryResponse = Literal["terminate", "hold", "reconcile", "continue", "retry", "resume", "new-trial"]


class ExecutionPolicy(ContractModel):
    """A complete local choice; omitted fields never inherit from another policy."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", json_schema_extra=execution_policy_schema
    )
    schema_version: Literal[EXECUTION_POLICY_VERSION] = EXECUTION_POLICY_VERSION
    policy_id: PolicyIdentifier
    revision: PolicyIdentifier = "1"
    response: RecoveryResponse
    failure_classes: tuple[FailureClass, ...] = Field(default=("operation",), min_length=1, max_length=6)
    validity: Literal["preserve", "qualify", "invalidate"] = "preserve"
    retry: ExecutionRetryPolicyModel = Field(
        default_factory=lambda: ExecutionRetryPolicyModel(max_attempts=1, after_effect_policy="disallow")
    )
    effect_classes: tuple[Literal["absent", "applied", "partial"], ...] = Field(default=(), max_length=3)
    budget_ms: PolicyLimit | None = None
    delay_ms: Annotated[int, Field(strict=True, ge=0, le=9007199254740991)] = 0
    clock_basis: Literal["apparatus", "semantic"] = "apparatus"
    clock_ref: PolicyIdentifier | None = None
    evidence_refs: tuple[PolicyIdentifier, ...] = Field(default=(), max_length=64)
    on_exhausted: Literal["terminate", "new-trial"] = "terminate"
    fresh_trial_limit: PolicyLimit | None = None

    @field_validator("retry", mode="before")
    @classmethod
    def _bounded_retry(cls, value: object) -> object:
        if not isinstance(value, (Mapping, ExecutionRetryPolicyModel)):
            raise ValueError("operation retry requires a typed retry policy")
        attempts = value.get("max_attempts") if isinstance(value, Mapping) else getattr(value, "max_attempts", None)
        if type(attempts) is not int or not 1 <= attempts <= 9007199254740991:
            raise ValueError("operation retry attempts must be a strict bounded integer")
        collections = (
            (value.get("reset_obligation_refs", ()), value.get("compensation_refs", ()))
            if isinstance(value, Mapping)
            else (value.reset_obligation_refs, value.compensation_refs)
        )
        if any(not isinstance(refs, (list, tuple)) for refs in collections):
            raise ValueError("operation retry obligation references must be bounded collections")
        refs = [ref for collection in collections for ref in collection]
        if len(refs) > 64 or any(not isinstance(ref, str) or not 1 <= len(ref) <= 256 for ref in refs):
            raise ValueError("operation retry obligation references exceed their bounds")
        return value

    @model_validator(mode="after")
    def _consistent_choices(self) -> Self:
        for values in (self.failure_classes, self.effect_classes, self.evidence_refs):
            if len(values) != len(set(values)):
                raise ValueError("execution policy references and classes must be unique")
        repeats = self.retry.max_attempts > 1
        self._validate_retry_budget(repeats)
        self._validate_repetition_conditions(repeats)
        self._validate_recovery_choices(repeats)
        return self

    def _validate_retry_budget(self, repeats: bool) -> None:
        if (self.response == "retry") != repeats:
            raise ValueError("retry response requires multiple attempts; other responses permit one invocation")
        if repeats and (self.budget_ms is None or not self.effect_classes or not self.evidence_refs):
            raise ValueError("bounded retry requires budget, effect classes and evidence requirements")
        if repeats and self.delay_ms >= self.budget_ms:
            raise ValueError("retry delay must fit within the total budget")

    def _validate_repetition_conditions(self, repeats: bool) -> None:
        if any(item != "absent" for item in self.effect_classes) and self.retry.after_effect_policy == "disallow":
            raise ValueError("after-effect repetition requires an explicit admitted posture")
        if not repeats and (self.effect_classes or self.delay_ms or self.retry.after_effect_policy != "disallow"):
            raise ValueError("non-repeating policy cannot declare repetition conditions")

    def _validate_recovery_choices(self, repeats: bool) -> None:
        if (self.clock_basis == "semantic") != (self.clock_ref is not None):
            raise ValueError("semantic budget requires an authored clock reference")
        fresh = self.response == "new-trial" or self.on_exhausted == "new-trial"
        if fresh != (self.fresh_trial_limit is not None):
            raise ValueError("fresh-trial choice requires its own allocation limit")
        if self.on_exhausted != "terminate" and not repeats:
            raise ValueError("exhaustion disposition requires bounded retry")
        if self.response in {"resume", "continue", "hold", "reconcile", "new-trial"} and not self.evidence_refs:
            raise ValueError("selected recovery response requires explicit evidence requirements")


class ExecutionPolicyScope(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    namespace: tuple[PolicyNamespace, ...] = Field(default=(), max_length=31)
    scope: SemanticScope = ""
    policy: ExecutionPolicy


class ExecutionPolicyDocument(ContractModel):
    """Convenience defaults with complete lexical overrides, independent of realization closure."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", json_schema_extra=execution_policy_schema
    )
    default: ExecutionPolicy | None = None
    scopes: tuple[ExecutionPolicyScope, ...] = Field(default=(), max_length=256)

    @model_validator(mode="after")
    def _unique_scopes(self) -> Self:
        identities = [(rule.namespace, rule.scope) for rule in self.scopes]
        if len(identities) != len(set(identities)):
            raise ValueError("execution policies must have unique lexical scope identities")
        if self.default is not None and ((), "") in identities:
            raise ValueError("execution policy default duplicates the root scope")
        return self


class EffectiveExecutionPolicy(ContractModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", json_schema_extra=execution_policy_schema
    )
    scope: SemanticScope
    retry_unit: Literal["native-operation", "workflow-step"] = "native-operation"
    governing_scope: Annotated[str, Field(min_length=1, max_length=8192)]
    namespace: tuple[PolicyNamespace, ...] = Field(default=(), max_length=31)
    policy: ExecutionPolicy
    evidence_requirements: dict[PolicyIdentifier, EvidenceRequirement] = Field(default_factory=dict, max_length=64)

    @model_validator(mode="after")
    def _resolved_evidence(self) -> Self:
        if set(self.evidence_requirements) != set(self.policy.evidence_refs):
            raise ValueError("effective execution policy must resolve every evidence requirement exactly")
        namespace, separator, pointer = self.governing_scope.partition("#")
        if not separator or namespace != ".".join(self.namespace):
            raise ValueError("effective execution policy governing namespace is inconsistent")
        pointer = "" if pointer == "/" else pointer
        # Validate the defining pointer through the same closed scope carrier.
        ExecutionPolicyScope(scope=pointer, namespace=self.namespace, policy=self.policy)
        if not semantic_address_contains(pointer, self.scope):
            raise ValueError("effective execution policy governing scope must contain its application scope")
        expected_unit = _retry_unit(self.scope)
        if self.retry_unit != expected_unit:
            raise ValueError("effective execution policy retry unit must match its native scope owner")
        return self


def validate_effective_execution_policies(
    primary: EffectiveExecutionPolicy | None, scopes: tuple[EffectiveExecutionPolicy, ...]
) -> None:
    if primary is not None and not isinstance(primary, EffectiveExecutionPolicy):
        raise TypeError("execution policy must be a validated effective policy")
    if (
        not isinstance(scopes, tuple)
        or len(scopes) > 256
        or any(not isinstance(policy, EffectiveExecutionPolicy) for policy in scopes)
    ):
        raise TypeError("execution policy scopes must contain bounded validated effective policies")
    policies = [value for value in (primary, *scopes) if value is not None]
    if len({policy.scope for policy in policies}) != len(policies):
        raise ValueError("native execution policy application scopes must be unique")
    for policy in policies:
        EffectiveExecutionPolicy.model_validate(policy.model_dump())


def resolve_execution_policy(
    document: ExecutionPolicyDocument | None,
    scope: str,
    *,
    namespace: tuple[str, ...] = (),
    evidence_requirements: Mapping[str, EvidenceRequirement] | None = None,
) -> EffectiveExecutionPolicy | None:
    """Select the nearest complete value; no scope grants permission by omission."""

    if document is None:
        return None
    rule = _selected_rule(document, scope, namespace)
    if rule is None:
        return None
    evidence_requirements = evidence_requirements or {}
    if not set(rule.policy.evidence_refs) <= set(evidence_requirements):
        raise ValueError("execution policy evidence requirements do not resolve")
    return EffectiveExecutionPolicy(
        scope=scope,
        retry_unit=_retry_unit(scope),
        namespace=rule.namespace,
        governing_scope=".".join(rule.namespace) + "#" + (rule.scope or "/"),
        policy=rule.policy.model_dump(),
        evidence_requirements={ref: evidence_requirements[ref].model_dump() for ref in rule.policy.evidence_refs},
    )


def _retry_unit(scope: str) -> Literal["workflow-step", "native-operation"]:
    return (
        "workflow-step"
        if scope.startswith(WORKFLOW_SCOPE_PREFIX) and WORKFLOW_STEP_SEGMENT in scope
        else "native-operation"
    )


def _selected_rule(
    document: ExecutionPolicyDocument, scope: str, namespace: tuple[str, ...]
) -> ExecutionPolicyScope | None:
    matches = [
        rule
        for rule in document.scopes
        if namespace[: len(rule.namespace)] == rule.namespace and semantic_address_contains(rule.scope, scope)
    ]
    if matches:
        return max(matches, key=lambda item: (len(item.namespace), len(item.scope.split("/"))))
    return ExecutionPolicyScope(policy=document.default) if document.default is not None else None


class ExecutionPolicyCapabilities(ContractModel):
    """Installed support declaration; each invocation still needs contextual willingness."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", json_schema_extra=execution_policy_schema
    )
    schema_version: Literal[EXECUTION_POLICY_VERSION] = EXECUTION_POLICY_VERSION
    responses: tuple[RecoveryResponse, ...] = Field(min_length=1, max_length=7)
    max_attempts: PolicyLimit = 1
    after_effect_policies: tuple[Literal["disallow", "idempotent", "reset", "compensate"], ...] = Field(
        default=("disallow",), min_length=1, max_length=4
    )

    # No published checkpoint/continuation carrier exists in #1360's v1 family.
    @model_validator(mode="after")
    def _supported_claims(self) -> Self:
        if "resume" in self.responses:
            raise ValueError("general continuation needs a governed continuation contract")
        if len(self.responses) != len(set(self.responses)) or len(self.after_effect_policies) != len(
            set(self.after_effect_policies)
        ):
            raise ValueError("execution policy capabilities must be unique")
        return self


def execution_policy_capability_gaps(
    policy: ExecutionPolicy, support: ExecutionPolicyCapabilities | None
) -> tuple[str, ...]:
    """Closed failure codes shared by planning and exact contextual admission."""

    policy = ExecutionPolicy.model_validate(policy.model_dump())
    code = _required_authority_gap(policy)
    if code is None:
        code = _installed_support_gap(policy, support)
    return tuple([code] if code is not None else [])


def _required_authority_gap(policy: ExecutionPolicy) -> str | None:
    if policy.response == "resume":
        code = "continuation-unsupported"
    elif policy.response == "new-trial" or policy.on_exhausted == "new-trial":
        code = "trial-allocation-authority-required"
    elif policy.retry.after_effect_policy in {"reset", "compensate"}:
        code = "cleanup-authority-required"
    else:
        code = None
    return code


def _installed_support_gap(policy: ExecutionPolicy, support: ExecutionPolicyCapabilities | None) -> str | None:
    if support is None or policy.response not in support.responses:
        return "response-unsupported"
    support = ExecutionPolicyCapabilities.model_validate(support.model_dump())
    if (
        policy.retry.max_attempts > support.max_attempts
        or policy.retry.after_effect_policy not in support.after_effect_policies
    ):
        return "retry-unsupported"
    return None


OptionalExecutionPolicy = Annotated[
    ExecutionPolicyDocument | None,
    Field(exclude_if=lambda value: value is None, json_schema_extra={"x-raes-realization-dimension": False}),
]
