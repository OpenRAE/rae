"""Closed experiment-owned scenario-family selection policy contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, model_validator
from raes.identifiers import PortableIdentifier

from ..graphs import has_cycle
from .base import ContractModel, NonEmptyString, PositiveInteger, SemanticProfileId
from .experiment_bindings import LiteralBindingValueModel

if TYPE_CHECKING:
    from .experiment_spec import ExperimentRunPlanModel, ExperimentSpecModel
    from .experiment_study import ExperimentRunAllocationPlanModel

MAX_SELECTION_POLICIES = 128
MAX_SELECTION_POLICY_REFS = 64
MAX_SELECTION_OUTCOMES = 1_024
MAX_SELECTION_OUTPUT_BOUND = 1_000_000

SelectionOutputBound = Annotated[PositiveInteger, Field(le=MAX_SELECTION_OUTPUT_BOUND)]
_BINDING_REFS_UNIQUE_ERROR = "selection binding_descriptor_refs must be unique"


class ExperimentSelectionReferenceOutcomeModel(ContractModel):
    """One governed-reference outcome named by its declared reference id."""

    kind: Literal["reference"]
    reference_id: NonEmptyString


class ExperimentSelectionMemberOutcomeModel(ContractModel):
    """One named alternative/member outcome."""

    kind: Literal["member"]
    member_id: PortableIdentifier


class ExperimentSelectionSubsetOutcomeModel(ContractModel):
    """One canonical subset of declared structural member ids."""

    kind: Literal["subset"]
    member_ids: list[PortableIdentifier] = Field(max_length=MAX_SELECTION_OUTCOMES)

    @model_validator(mode="after")
    def _validate_unique_members(self) -> ExperimentSelectionSubsetOutcomeModel:
        if len(self.member_ids) != len(set(self.member_ids)):
            raise ValueError("selection subset member_ids must be unique")
        return self


class ExperimentSelectionOrderOutcomeModel(ContractModel):
    """One complete canonical order of declared structural member ids."""

    kind: Literal["order"]
    member_ids: list[PortableIdentifier] = Field(min_length=1, max_length=MAX_SELECTION_OUTCOMES)

    @model_validator(mode="after")
    def _validate_unique_members(self) -> ExperimentSelectionOrderOutcomeModel:
        if len(self.member_ids) != len(set(self.member_ids)):
            raise ValueError("selection order member_ids must be unique")
        return self


ExperimentSelectionOutcomeModel = Annotated[
    LiteralBindingValueModel
    | ExperimentSelectionReferenceOutcomeModel
    | ExperimentSelectionMemberOutcomeModel
    | ExperimentSelectionSubsetOutcomeModel
    | ExperimentSelectionOrderOutcomeModel,
    Field(discriminator="kind"),
]


class ExperimentFixedSelectionPolicyModel(ContractModel):
    """Deterministic leaf selecting one admitted outcome."""

    kind: Literal["fixed"]
    policy_id: PortableIdentifier
    purpose: Literal["nuisance-variation", "fixed-configuration"]
    point_ref: NonEmptyString
    outcome: ExperimentSelectionOutcomeModel
    output_bound: SelectionOutputBound
    binding_descriptor_refs: list[NonEmptyString] = Field(
        default_factory=list,
        max_length=MAX_SELECTION_POLICY_REFS,
    )

    @model_validator(mode="after")
    def _validate_fixed(self) -> ExperimentFixedSelectionPolicyModel:
        if self.output_bound != 1:
            raise ValueError("fixed selection policy output_bound must equal one")
        if len(self.binding_descriptor_refs) != len(set(self.binding_descriptor_refs)):
            raise ValueError(_BINDING_REFS_UNIQUE_ERROR)
        return self


class ExperimentEnumerateSelectionPolicyModel(ContractModel):
    """Deterministic exhaustive enumeration of one finite point domain."""

    kind: Literal["enumerate"]
    policy_id: PortableIdentifier
    purpose: Literal["nuisance-variation"]
    point_ref: NonEmptyString
    output_bound: SelectionOutputBound
    binding_descriptor_refs: list[NonEmptyString] = Field(
        default_factory=list,
        max_length=MAX_SELECTION_POLICY_REFS,
    )

    @model_validator(mode="after")
    def _validate_binding_refs(self) -> ExperimentEnumerateSelectionPolicyModel:
        if len(self.binding_descriptor_refs) != len(set(self.binding_descriptor_refs)):
            raise ValueError(_BINDING_REFS_UNIQUE_ERROR)
        return self


class ExperimentProductSelectionPolicyModel(ContractModel):
    """Deterministic Cartesian product over named policy dimensions."""

    kind: Literal["product"]
    policy_id: PortableIdentifier
    purpose: Literal["controlled-factor", "nuisance-variation"]
    policy_refs: list[PortableIdentifier] = Field(
        min_length=2,
        max_length=MAX_SELECTION_POLICY_REFS,
    )
    output_bound: SelectionOutputBound

    @model_validator(mode="after")
    def _validate_unique_policy_refs(self) -> ExperimentProductSelectionPolicyModel:
        if len(self.policy_refs) != len(set(self.policy_refs)):
            raise ValueError("product policy_refs must be unique")
        return self


class ExperimentSelectionStratumModel(ContractModel):
    """One exact allocation stratum joined to an existing condition."""

    stratum_id: PortableIdentifier
    outcome_ref: PortableIdentifier
    factor_id: NonEmptyString
    factor_level_id: NonEmptyString
    condition_id: NonEmptyString
    output_count: SelectionOutputBound


class ExperimentStratifiedSelectionPolicyModel(ContractModel):
    """Exact balanced/stratified allocation over declared policy outcomes."""

    kind: Literal["stratified"]
    policy_id: PortableIdentifier
    purpose: Literal["controlled-factor", "nuisance-variation"]
    point_ref: NonEmptyString
    balance: Literal["equal"]
    outcomes: dict[PortableIdentifier, ExperimentSelectionOutcomeModel] = Field(
        min_length=1,
        max_length=MAX_SELECTION_OUTCOMES,
    )
    strata: dict[PortableIdentifier, ExperimentSelectionStratumModel] = Field(
        min_length=1,
        max_length=MAX_SELECTION_OUTCOMES,
    )
    output_bound: SelectionOutputBound

    @model_validator(mode="after")
    def _validate_strata(self) -> ExperimentStratifiedSelectionPolicyModel:
        mismatched = sorted(key for key, stratum in self.strata.items() if key != stratum.stratum_id)
        if mismatched:
            raise ValueError("selection strata keys must match embedded stratum_id")
        mismatched_conditions = sorted(key for key, stratum in self.strata.items() if key != stratum.condition_id)
        if mismatched_conditions:
            raise ValueError("selection stratum condition_id must match its keyed allocation condition")
        missing_outcomes = sorted(
            stratum.outcome_ref for stratum in self.strata.values() if stratum.outcome_ref not in self.outcomes
        )
        if missing_outcomes:
            raise ValueError("selection strata must reference declared outcomes")
        counts = [stratum.output_count for stratum in self.strata.values()]
        if len(set(counts)) != 1:
            raise ValueError("equal balanced strata must have identical output_count values")
        if sum(counts) != self.output_bound:
            raise ValueError("stratified policy output_bound must equal the sum of stratum output counts")
        return self


class ExperimentSampleSelectionPolicyModel(ContractModel):
    """Bounded uniform sampling with replacement using one governed stream."""

    kind: Literal["sample"]
    policy_id: PortableIdentifier
    purpose: Literal["nuisance-variation"]
    point_ref: NonEmptyString
    algorithm_profile: Literal["uniform-index-v1"]
    distribution: Literal["uniform"]
    replacement: Literal["with-replacement"]
    sample_count: SelectionOutputBound
    output_bound: SelectionOutputBound
    stochastic_control_ref: NonEmptyString
    logical_coordinate_profile: SemanticProfileId = "selection-coordinate-v1"
    binding_descriptor_refs: list[NonEmptyString] = Field(
        default_factory=list,
        max_length=MAX_SELECTION_POLICY_REFS,
    )

    @model_validator(mode="after")
    def _validate_sample(self) -> ExperimentSampleSelectionPolicyModel:
        if self.sample_count != self.output_bound:
            raise ValueError("sample_count must equal sample policy output_bound")
        if len(self.binding_descriptor_refs) != len(set(self.binding_descriptor_refs)):
            raise ValueError(_BINDING_REFS_UNIQUE_ERROR)
        return self


ExperimentSelectionPolicyModel = Annotated[
    ExperimentFixedSelectionPolicyModel
    | ExperimentEnumerateSelectionPolicyModel
    | ExperimentProductSelectionPolicyModel
    | ExperimentStratifiedSelectionPolicyModel
    | ExperimentSampleSelectionPolicyModel,
    Field(discriminator="kind"),
]


def _validate_selection_policy_registry(run_plan: ExperimentRunPlanModel) -> None:
    mismatched = sorted(key for key, policy in run_plan.selection_policies.items() if key != policy.policy_id)
    if mismatched:
        raise ValueError("selection policy map keys must match embedded policy_id")
    control_ids = [control.control_id for control in run_plan.stochastic_controls]
    if len(control_ids) != len(set(control_ids)):
        raise ValueError("run_plan stochastic control ids must be unique")
    total_runs = (
        len(run_plan.allocation.compared_conditions) * run_plan.allocation.target_runs_per_condition
        if run_plan.allocation is not None
        else run_plan.target_run_count
    )
    if total_runs is None:
        raise ValueError("run plan must declare a run allocation before validating selection policies")
    for policy in run_plan.selection_policies.values():
        if policy.output_bound > total_runs:
            raise ValueError("selection policy output_bound must not exceed the declared run allocation")
        if isinstance(policy, ExperimentSampleSelectionPolicyModel):
            if policy.sample_count != total_runs:
                raise ValueError("sample_count must equal the declared run allocation")
            _validate_sample_control(run_plan, policy)
    _validate_product_graph(run_plan.selection_policies)


def _validate_sample_control(
    run_plan: ExperimentRunPlanModel,
    policy: ExperimentSampleSelectionPolicyModel,
) -> None:
    controls = [
        control for control in run_plan.stochastic_controls if control.control_id == policy.stochastic_control_ref
    ]
    if len(controls) != 1:
        raise ValueError("stochastic selection policy must resolve exactly one stochastic control")
    control = controls[0]
    if control.role not in {"sampling", "randomization"}:
        raise ValueError("stochastic selection policy control must have sampling or randomization role")
    if control.executable_binding is None:
        raise ValueError("stochastic selection policy control must carry an executable binding")
    from ..random_stream_profiles import load_random_stream_profile

    profile = load_random_stream_profile(control.executable_binding.profile_ref.ref_id)
    transform = profile.transforms.get("bounded-integer")
    if transform is None or transform.version != "1":
        raise ValueError("uniform-index-v1 requires the bounded-integer transform version 1")


def _validate_product_graph(policies: dict[str, ExperimentSelectionPolicyModel]) -> None:
    products = {
        policy_id: policy
        for policy_id, policy in policies.items()
        if isinstance(policy, ExperimentProductSelectionPolicyModel)
    }
    for product in products.values():
        _validate_product_policy(product, policies)
    _validate_product_cycles(products)


def _validate_product_policy(
    product: ExperimentProductSelectionPolicyModel,
    policies: dict[str, ExperimentSelectionPolicyModel],
) -> None:
    if any(ref not in policies for ref in product.policy_refs):
        raise ValueError("product policy_refs must reference declared selection policies")
    expected = _product_output_bound(product, policies)
    if expected != product.output_bound:
        raise ValueError("product policy output_bound must equal the product of referenced bounds")
    has_controlled_dimension = any(policies[ref].purpose == "controlled-factor" for ref in product.policy_refs)
    if (product.purpose == "controlled-factor") != has_controlled_dimension:
        raise ValueError("product controlled-factor purpose must match its authoritative controlled-factor dimensions")


def _product_output_bound(
    product: ExperimentProductSelectionPolicyModel,
    policies: dict[str, ExperimentSelectionPolicyModel],
) -> int:
    expected = 1
    for ref in product.policy_refs:
        expected *= policies[ref].output_bound
        if expected > MAX_SELECTION_OUTPUT_BOUND:
            raise ValueError("product policy output_bound exceeds the admission bound")
    return expected


def _validate_product_cycles(products: dict[str, ExperimentProductSelectionPolicyModel]) -> None:
    if has_cycle({policy_id: product.policy_refs for policy_id, product in products.items()}):
        raise ValueError("selection policy reference graph must be acyclic")


def _validate_selection_factor_joins(spec: ExperimentSpecModel) -> None:
    allocation = spec.run_plan.allocation
    for policy in spec.run_plan.selection_policies.values():
        _validate_binding_descriptor_refs(spec, policy)
        if isinstance(policy, ExperimentStratifiedSelectionPolicyModel):
            _validate_stratified_factor_join(spec, policy, allocation)


def _validate_binding_descriptor_refs(
    spec: ExperimentSpecModel,
    policy: ExperimentSelectionPolicyModel,
) -> None:
    refs = getattr(policy, "binding_descriptor_refs", [])
    if not refs:
        return
    if spec.binding_descriptors is None:
        raise ValueError("selection binding_descriptor_refs require binding_descriptors")
    descriptors = {descriptor.binding_id: descriptor for descriptor in spec.binding_descriptors.descriptors}
    if any(ref not in descriptors for ref in refs):
        raise ValueError("selection binding_descriptor_refs must reference declared bindings")
    point_ref = getattr(policy, "point_ref", None)
    for ref in refs:
        if getattr(descriptors[ref].target, "variation_point_id", None) != point_ref:
            raise ValueError("selection binding descriptor must target the policy variation point")


def _validate_stratified_factor_join(
    spec: ExperimentSpecModel,
    policy: ExperimentStratifiedSelectionPolicyModel,
    allocation: ExperimentRunAllocationPlanModel | None,
) -> None:
    if allocation is None:
        raise ValueError("stratified selection requires condition-based run allocation")
    if set(policy.strata) != set(allocation.compared_conditions):
        raise ValueError("stratified selection conditions must match compared_conditions")
    for stratum in policy.strata.values():
        _validate_stratum_factor_join(spec, stratum, allocation)


def _validate_stratum_factor_join(
    spec: ExperimentSpecModel,
    stratum: ExperimentSelectionStratumModel,
    allocation: ExperimentRunAllocationPlanModel,
) -> None:
    factor = spec.factors.get(stratum.factor_id)
    if factor is None or stratum.factor_level_id not in factor.levels:
        raise ValueError("selection stratum factor and level must be declared")
    assignment = allocation.condition_assignments.get(stratum.condition_id)
    if assignment is None:
        raise ValueError("selection stratum condition_id must reference an allocation condition")
    if assignment.factor_levels.get(stratum.factor_id) != stratum.factor_level_id:
        raise ValueError("selection stratum factor level must match its condition assignment")
    if stratum.output_count != allocation.target_runs_per_condition:
        raise ValueError("selection stratum output_count must match target_runs_per_condition")


__all__ = [
    "ExperimentEnumerateSelectionPolicyModel",
    "ExperimentFixedSelectionPolicyModel",
    "ExperimentProductSelectionPolicyModel",
    "ExperimentSampleSelectionPolicyModel",
    "ExperimentSelectionMemberOutcomeModel",
    "ExperimentSelectionOrderOutcomeModel",
    "ExperimentSelectionReferenceOutcomeModel",
    "ExperimentSelectionStratumModel",
    "ExperimentSelectionSubsetOutcomeModel",
    "ExperimentStratifiedSelectionPolicyModel",
]
