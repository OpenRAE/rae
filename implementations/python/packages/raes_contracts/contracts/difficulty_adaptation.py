"""Closed adaptive-difficulty declarations and archival provenance."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, model_validator

from raes_contracts.identifiers import PortableIdentifier

from ..canonical import canonical_json_digest
from .base import (
    ContractModel,
    NonEmptyString,
    NonNegativeInteger,
    PositiveInteger,
    PrefixedDigestString,
    Rfc3339DateTimeString,
)
from .difficulty_governance import (
    validate_difficulty_evaluator_identity,
    validate_difficulty_registry_carriers,
)
from .difficulty_observations import (
    DifficultyObservationInputModel,
    DifficultyObservationReferenceModel,
    DifficultySourceDefinitionReferenceModel,
    DifficultyStateCutModel,
    DifficultyThresholdValue,
    _validate_difficulty_evidence_reference,
)
from .experiment_references import ExperimentReferenceModel

DifficultyCondition = Literal["fixed", "adaptive", "scaffolded"]


class DifficultyDimensionModel(ContractModel):
    """One policy-local ordering over named, already declared variants."""

    dimension_id: PortableIdentifier
    ordered_variant_ids: list[PortableIdentifier] = Field(min_length=2, max_length=128)
    ordering_rationale: NonEmptyString

    @model_validator(mode="after")
    def _validate_dimension(self) -> DifficultyDimensionModel:
        if len(self.ordered_variant_ids) != len(set(self.ordered_variant_ids)):
            raise ValueError("difficulty dimension ordered_variant_ids must be unique")
        return self


class DifficultyVariantModel(ContractModel):
    """Named references to incumbent selection, scaffold, and action carriers."""

    variant_id: PortableIdentifier
    selection_policy_refs: list[PortableIdentifier] = Field(default_factory=list, max_length=64)
    scaffold_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)
    action_refs: list[NonEmptyString] = Field(default_factory=list, max_length=64)
    description: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate_variant(self) -> DifficultyVariantModel:
        carriers = [*self.selection_policy_refs, *self.scaffold_refs, *self.action_refs]
        if not carriers:
            raise ValueError("difficulty variants must reference at least one declared carrier")
        if len(carriers) != len(set(carriers)):
            raise ValueError("difficulty variant carrier refs must be unique")
        return self


class DifficultyObservationSourceModel(ContractModel):
    """One evidence-bearing source role admitted as policy input."""

    source_id: PortableIdentifier
    source_kind: Literal[
        "evidence-record",
        "derived-measure",
        "participant-observation",
        "run-event",
        "result-summary",
    ]
    source_ref: DifficultySourceDefinitionReferenceModel
    visibility: Literal["participant-visible", "operator-only", "assurance-only"]
    maximum_age: NonNegativeInteger


class DifficultyAffectedReferenceModel(ContractModel):
    """Semantic reference kind an adaptive action is permitted to affect."""

    ref_kind: Literal[
        "scaffold",
        "participant-inject",
        "participant-control",
        "workflow-action",
        "scenario-variant",
    ]
    ref_id: NonEmptyString


class DifficultyActionModel(ContractModel):
    """One closed action request; the policy never performs the effect."""

    action_id: PortableIdentifier
    action_kind: Literal[
        "scaffold",
        "participant-inject",
        "participant-control",
        "workflow-action",
        "follow-up-trial",
    ]
    carrier_ref: NonEmptyString | None = None
    target_variant_id: PortableIdentifier | None = None
    affected_refs: list[DifficultyAffectedReferenceModel] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_action(self) -> DifficultyActionModel:
        affected_keys = [(reference.ref_kind, reference.ref_id) for reference in self.affected_refs]
        if len(affected_keys) != len(set(affected_keys)):
            raise ValueError("difficulty action affected_refs must be unique")
        expected_ref_kind = {
            "scaffold": "scaffold",
            "participant-inject": "participant-inject",
            "participant-control": "participant-control",
            "workflow-action": "workflow-action",
            "follow-up-trial": "scenario-variant",
        }[self.action_kind]
        if any(reference.ref_kind != expected_ref_kind for reference in self.affected_refs):
            raise ValueError("difficulty action affected_refs must match the closed action carrier kind")
        if self.action_kind == "follow-up-trial":
            if self.carrier_ref is not None or self.target_variant_id is None:
                raise ValueError("follow-up-trial actions require target_variant_id and forbid carrier_ref")
        elif self.carrier_ref is None:
            raise ValueError("in-run difficulty actions require a declared carrier_ref")
        return self


class DifficultyThresholdRuleModel(ContractModel):
    """One ordered typed-threshold rule in the reference evaluator profile."""

    rule_id: PortableIdentifier
    observation_source_id: PortableIdentifier
    operator: Literal["lt", "lte", "eq", "ne", "gte", "gt"]
    threshold: DifficultyThresholdValue
    action_id: PortableIdentifier
    priority: PositiveInteger

    @model_validator(mode="after")
    def _validate_threshold(self) -> DifficultyThresholdRuleModel:
        if self.operator in {"lt", "lte", "gte", "gt"} and (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, (int, float))
            or not math.isfinite(self.threshold)
        ):
            raise ValueError("ordered difficulty thresholds must be finite numbers")
        if isinstance(self.threshold, float) and not math.isfinite(self.threshold):
            raise ValueError("difficulty thresholds must be finite")
        return self


class DifficultyPolicyBoundsModel(ContractModel):
    """Finite intervention and cadence bounds."""

    maximum_interventions: NonNegativeInteger
    minimum_decision_interval: NonNegativeInteger
    cooldown: NonNegativeInteger
    terminal_disposition: Literal["fixed", "no-change", "deny", "unsupported"]


class DifficultyPolicyModel(ContractModel):
    """One immutable fixed, adaptive, or scaffolded policy declaration."""

    policy_id: PortableIdentifier
    policy_version: NonEmptyString
    policy_digest: PrefixedDigestString
    condition: DifficultyCondition
    baseline_variant_id: PortableIdentifier
    evaluator_ref: ExperimentReferenceModel | None = None
    observation_sources: dict[PortableIdentifier, DifficultyObservationSourceModel] = Field(
        default_factory=dict,
        max_length=64,
    )
    threshold_rules: dict[PortableIdentifier, DifficultyThresholdRuleModel] = Field(
        default_factory=dict,
        max_length=128,
    )
    actions: dict[PortableIdentifier, DifficultyActionModel] = Field(default_factory=dict, max_length=64)
    bounds: DifficultyPolicyBoundsModel
    guardrails: list[NonEmptyString] = Field(min_length=1, max_length=64)
    validity_effect: NonEmptyString

    @model_validator(mode="after")
    def _validate_policy(self) -> DifficultyPolicyModel:
        self._validate_keyed_children()
        if self.condition == "fixed":
            self._validate_fixed_authority()
        else:
            self._validate_adaptive_authority()
        self._validate_policy_digest()
        return self

    def _validate_fixed_authority(self) -> None:
        authority = (self.evaluator_ref, self.observation_sources, self.threshold_rules, self.actions)
        if any(authority):
            raise ValueError("fixed difficulty policies must not declare evaluator or intervention authority")
        if self.bounds.maximum_interventions != 0:
            raise ValueError("fixed difficulty policies must set maximum_interventions to zero")

    def _validate_adaptive_authority(self) -> None:
        missing_authority = (
            self.evaluator_ref is None
            or not self.observation_sources
            or not self.threshold_rules
            or not self.actions
            or self.bounds.maximum_interventions == 0
        )
        if missing_authority:
            raise ValueError(
                "adaptive and scaffolded difficulty policies require evaluator, observations, rules, actions, "
                "and a positive intervention bound"
            )
        self._validate_evaluator_reference()
        if self.condition == "scaffolded" and not any(
            action.action_kind == "scaffold" for action in self.actions.values()
        ):
            raise ValueError("scaffolded difficulty policies require a scaffold action")

    def _validate_policy_digest(self) -> None:
        expected_digest = difficulty_policy_digest(self)
        if self.policy_digest != expected_digest:
            raise ValueError("difficulty policy_digest must match the complete immutable declaration")

    def _validate_keyed_children(self) -> None:
        keyed = (
            ("observation source", self.observation_sources, "source_id"),
            ("threshold rule", self.threshold_rules, "rule_id"),
            ("action", self.actions, "action_id"),
        )
        for label, values, id_field in keyed:
            mismatched = sorted(key for key, value in values.items() if key != getattr(value, id_field))
            if mismatched:
                raise ValueError(f"difficulty {label} map keys must match embedded ids")
        priorities = [rule.priority for rule in self.threshold_rules.values()]
        if len(priorities) != len(set(priorities)):
            raise ValueError("difficulty threshold rule priorities must be unique")
        missing_sources = sorted(
            rule.observation_source_id
            for rule in self.threshold_rules.values()
            if rule.observation_source_id not in self.observation_sources
        )
        if missing_sources:
            raise ValueError("difficulty threshold rules must reference declared observation sources")
        missing_actions = sorted(
            rule.action_id for rule in self.threshold_rules.values() if rule.action_id not in self.actions
        )
        if missing_actions:
            raise ValueError("difficulty threshold rules must reference declared actions")

    def _validate_evaluator_reference(self) -> None:
        assert self.evaluator_ref is not None
        evaluator = self.evaluator_ref
        if (
            evaluator.ref_kind != "profile"
            or evaluator.ref_version is None
            or evaluator.ref_digest is None
            or evaluator.ref_path is not None
        ):
            raise ValueError("difficulty evaluator_ref must be a versioned digest-bound profile reference")
        validate_difficulty_evaluator_identity(evaluator)


class DifficultyPolicyRegistryModel(ContractModel):
    """Bounded named variants, dimensions, and policies for one experiment."""

    dimensions: dict[PortableIdentifier, DifficultyDimensionModel] = Field(min_length=1, max_length=32)
    variants: dict[PortableIdentifier, DifficultyVariantModel] = Field(min_length=1, max_length=128)
    policies: dict[PortableIdentifier, DifficultyPolicyModel] = Field(min_length=1, max_length=64)
    default_policy_id: PortableIdentifier

    @model_validator(mode="after")
    def _validate_registry(self) -> DifficultyPolicyRegistryModel:
        self._validate_map_keys()
        default_policy = self.policies.get(self.default_policy_id)
        if default_policy is None:
            raise ValueError("default difficulty policy must resolve to the policy registry")
        if default_policy.condition != "fixed":
            raise ValueError("default difficulty policy must be fixed")
        variant_ids = set(self.variants)
        for dimension in self.dimensions.values():
            if not set(dimension.ordered_variant_ids) <= variant_ids:
                raise ValueError("difficulty dimensions must reference declared difficulty variants")
        for policy in self.policies.values():
            if policy.baseline_variant_id not in variant_ids:
                raise ValueError("difficulty policy baseline must reference a declared difficulty variant")
            for action in policy.actions.values():
                if action.target_variant_id is not None and action.target_variant_id not in variant_ids:
                    raise ValueError("difficulty action target must reference a declared difficulty variant")
        validate_difficulty_registry_carriers(self)
        return self

    def _validate_map_keys(self) -> None:
        keyed = (
            ("dimension", self.dimensions, "dimension_id"),
            ("variant", self.variants, "variant_id"),
            ("policy", self.policies, "policy_id"),
        )
        for label, values, id_field in keyed:
            if any(key != getattr(value, id_field) for key, value in values.items()):
                raise ValueError(f"difficulty {label} map keys must match embedded ids")


class DifficultyDecisionRequestModel(ContractModel):
    """One deterministic request against a named policy and expected history head."""

    policy_id: PortableIdentifier
    policy_version: NonEmptyString
    policy_digest: PrefixedDigestString
    run_id: NonEmptyString
    state_cut: DifficultyStateCutModel
    observation_inputs: list[DifficultyObservationInputModel] = Field(default_factory=list, max_length=64)
    intervention_count: NonNegativeInteger
    expected_history_head: PrefixedDigestString | None = None
    idempotency_key: NonEmptyString
    requested_at: Rfc3339DateTimeString

    @model_validator(mode="after")
    def _validate_inputs(self) -> DifficultyDecisionRequestModel:
        source_ids = [item.source_id for item in self.observation_inputs]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("difficulty decision observation source ids must be unique")
        return self


class DifficultyDecisionRecordModel(ContractModel):
    """Append-only exact-cut policy decision; raw observation values are intentionally absent."""

    decision_id: NonEmptyString
    idempotency_key: NonEmptyString
    request_fingerprint: PrefixedDigestString
    prior_history_head: PrefixedDigestString | None = None
    history_head: PrefixedDigestString
    policy_id: PortableIdentifier
    policy_version: NonEmptyString
    policy_digest: PrefixedDigestString
    run_id: NonEmptyString
    state_cut: DifficultyStateCutModel
    observation_refs: list[DifficultyObservationReferenceModel] = Field(default_factory=list, max_length=64)
    trigger_rule_id: PortableIdentifier | None = None
    selected_action_id: PortableIdentifier | None = None
    affected_refs: list[DifficultyAffectedReferenceModel] = Field(default_factory=list, max_length=64)
    disposition: Literal["fixed", "selected", "no-change", "terminal", "denied", "unsupported"]
    decided_at: Rfc3339DateTimeString
    validity_effect: NonEmptyString

    @model_validator(mode="after")
    def _validate_history_head(self) -> DifficultyDecisionRecordModel:
        self._validate_observation_refs()
        self._validate_selection_shape()
        if self.history_head != difficulty_decision_history_head(self):
            raise ValueError("difficulty decision history_head must match the canonical decision content")
        return self

    def _validate_observation_refs(self) -> None:
        source_ids = [observation.source_id for observation in self.observation_refs]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("difficulty decision observation source ids must be unique")
        if not all(self._observation_precedes_decision(observation) for observation in self.observation_refs):
            raise ValueError("difficulty decision observations must precede the decision in one run scope")

    def _observation_precedes_decision(self, observation: DifficultyObservationReferenceModel) -> bool:
        return (
            observation.run_id == self.run_id
            and observation.observed_cut.order_domain == self.state_cut.order_domain
            and observation.observed_cut.episode_id == self.state_cut.episode_id
            and observation.observed_cut.coordinate <= self.state_cut.coordinate
        )

    def _validate_selection_shape(self) -> None:
        has_selected_action = (
            self.trigger_rule_id is not None or self.selected_action_id is not None or bool(self.affected_refs)
        )
        selected_shape_incomplete = self.disposition == "selected" and (
            self.trigger_rule_id is None
            or self.selected_action_id is None
            or not self.affected_refs
            or not self.observation_refs
        )
        if selected_shape_incomplete:
            raise ValueError("selected difficulty decisions require trigger, action, affected, and observation refs")
        if self.disposition != "selected" and has_selected_action:
            raise ValueError("selected actions require selected disposition")


class DifficultyInterventionRecordModel(ContractModel):
    """Separately evidenced realization or denial of one selected decision action."""

    intervention_id: NonEmptyString
    decision_id: NonEmptyString
    run_id: NonEmptyString
    action_id: PortableIdentifier
    occurred_at: Rfc3339DateTimeString
    disposition: Literal["attempted", "realized", "denied", "unsupported", "failed"]
    affected_refs: list[DifficultyAffectedReferenceModel] = Field(min_length=1, max_length=64)
    occurrence_refs: list[ExperimentReferenceModel] = Field(default_factory=list, max_length=64)
    evidence_refs: list[ExperimentReferenceModel] = Field(default_factory=list, max_length=64)
    follow_up_run_ref: ExperimentReferenceModel | None = None

    @model_validator(mode="after")
    def _validate_intervention(self) -> DifficultyInterventionRecordModel:
        for evidence_ref in self.evidence_refs:
            _validate_difficulty_evidence_reference(evidence_ref)
        if self.disposition in {"attempted", "realized", "failed"} and not (
            self.occurrence_refs or self.evidence_refs or self.follow_up_run_ref is not None
        ):
            raise ValueError("effect-capable difficulty interventions require occurrence or evidence provenance")
        if self.follow_up_run_ref is not None and self.follow_up_run_ref.ref_kind != "run":
            raise ValueError("difficulty follow_up_run_ref must reference a run")
        return self


def difficulty_policy_digest(policy: DifficultyPolicyModel | dict) -> str:
    """Return the canonical digest over a policy declaration, excluding its digest field."""

    if isinstance(policy, DifficultyPolicyModel):
        payload = policy.model_dump(mode="json", exclude={"policy_digest"})
    else:
        evaluator_ref = policy.get("evaluator_ref")
        payload = {
            "policy_id": policy["policy_id"],
            "policy_version": policy["policy_version"],
            "condition": policy["condition"],
            "baseline_variant_id": policy["baseline_variant_id"],
            "evaluator_ref": (
                ExperimentReferenceModel.model_validate(evaluator_ref).model_dump(mode="json")
                if evaluator_ref is not None
                else None
            ),
            "observation_sources": {
                key: DifficultyObservationSourceModel.model_validate(value).model_dump(mode="json")
                for key, value in policy.get("observation_sources", {}).items()
            },
            "threshold_rules": {
                key: DifficultyThresholdRuleModel.model_validate(value).model_dump(mode="json")
                for key, value in policy.get("threshold_rules", {}).items()
            },
            "actions": {
                key: DifficultyActionModel.model_validate(value).model_dump(mode="json")
                for key, value in policy.get("actions", {}).items()
            },
            "bounds": DifficultyPolicyBoundsModel.model_validate(policy["bounds"]).model_dump(mode="json"),
            "guardrails": policy["guardrails"],
            "validity_effect": policy["validity_effect"],
        }
    return canonical_json_digest(payload)


def difficulty_decision_history_head(decision: DifficultyDecisionRecordModel | dict) -> str:
    """Return the append-only history head for one decision record."""

    payload = (
        decision.model_dump(mode="json", exclude={"history_head"})
        if isinstance(decision, DifficultyDecisionRecordModel)
        else {key: value for key, value in decision.items() if key != "history_head"}
    )
    return canonical_json_digest(payload)


__all__ = [
    "DifficultyAffectedReferenceModel",
    "DifficultyActionModel",
    "DifficultyCondition",
    "DifficultyDecisionRecordModel",
    "DifficultyDecisionRequestModel",
    "DifficultyDimensionModel",
    "DifficultyInterventionRecordModel",
    "DifficultyObservationInputModel",
    "DifficultyObservationReferenceModel",
    "DifficultyObservationSourceModel",
    "DifficultySourceDefinitionReferenceModel",
    "DifficultyPolicyBoundsModel",
    "DifficultyPolicyModel",
    "DifficultyPolicyRegistryModel",
    "DifficultyStateCutModel",
    "DifficultyThresholdRuleModel",
    "DifficultyThresholdValue",
    "DifficultyVariantModel",
    "difficulty_decision_history_head",
    "difficulty_policy_digest",
]
