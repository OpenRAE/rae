"""Deterministic policy-graph compilation for trial-compiler-v1."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

from raes import SDLSelectionError
from raes.scenario import ExpandedScenario
from raes.selected_scenario import ExpandedScenarioBindingTargetResolver
from raes_contracts.contracts import (
    AdmittedSelectionRecordModel,
    ExperimentBindingDescriptorModel,
    ExperimentEnumerateSelectionPolicyModel,
    ExperimentFixedSelectionPolicyModel,
    ExperimentProductSelectionPolicyModel,
    ExperimentSampleSelectionPolicyModel,
    ExperimentSpecModel,
    ExperimentStochasticControlModel,
    ExperimentStratifiedSelectionPolicyModel,
    LiteralBindingValueModel,
    PublicRandomOutcomeModel,
    PublicSeedModel,
    RandomStreamControlBindingModel,
    RandomStreamDrawRecordModel,
    StreamAddressModel,
    TrialCompilationLimitsModel,
    TrialCoordinateModel,
)
from raes_contracts.contracts.experiment_treatments import ExperimentScenarioSelectionDescriptorModel
from raes_contracts.contracts.random_stream_engine import (
    BOUNDED_INTEGER_TRANSFORM_ID,
    BOUNDED_INTEGER_TRANSFORM_VERSION,
    BoundedIntegerDrawRequest,
    decode_public_seed,
    derive_stream_key,
    draw_bounded_integer_batch,
)
from raes_contracts.contracts.random_stream_profiles import load_random_stream_profile

from .domains import canonical_domain_outcomes
from .models import CompilationFailure
from .profiles import RANDOM_STREAM_PROFILE_ID, RANDOM_STREAM_PROFILE_VERSION

_SELECTION_POLICIES_ADDRESS = "/run_plan/selection_policies"
_FACTORIAL_DESIGN_ADDRESS = "/factorial_design"


@dataclass(frozen=True)
class ResolvedSelection:
    point_id: str
    policy_id: str
    policy_kind: str
    outcome: object
    treatment: ExperimentScenarioSelectionDescriptorModel | None = None


@dataclass(frozen=True)
class CoordinateSelections:
    selections: tuple[ResolvedSelection, ...]
    draws: tuple[RandomStreamDrawRecordModel, ...] = ()

    def records(self) -> list[AdmittedSelectionRecordModel]:
        """Project the same exact selection records for compilation and readmission."""
        return [
            AdmittedSelectionRecordModel(
                variation_point_id=selection.point_id,
                origin_policy_id=selection.policy_id,
                origin_policy_kind=selection.policy_kind,
                outcome=selection.outcome,
                treatment=selection.treatment,
            )
            for selection in self.selections
        ]


def _merge_rows(
    rows: tuple[ResolvedSelection, ...],
    additions: tuple[ResolvedSelection, ...],
) -> tuple[ResolvedSelection, ...]:
    merged = {selection.point_id: selection for selection in rows}
    for selection in additions:
        if selection.point_id in merged:
            raise CompilationFailure(
                "point-selected-multiple-times",
                _SELECTION_POLICIES_ADDRESS,
                "multiple selection policies resolve the same variation point",
            )
        merged[selection.point_id] = selection
    return tuple(merged[point_id] for point_id in sorted(merged))


def _static_rows(
    policy_id: str,
    *,
    family: ExpandedScenario,
    spec: ExperimentSpecModel,
    limits: TrialCompilationLimitsModel,
) -> list[tuple[ResolvedSelection, ...]]:
    policy = spec.run_plan.selection_policies[policy_id]
    if isinstance(policy, ExperimentFixedSelectionPolicyModel):
        return [(ResolvedSelection(policy.point_ref, policy.policy_id, policy.kind, policy.outcome),)]
    if isinstance(policy, ExperimentEnumerateSelectionPolicyModel):
        point = family.variation_points[policy.point_ref]
        outcomes = canonical_domain_outcomes(point, maximum=limits.max_domain_values_per_point)
        return [(ResolvedSelection(policy.point_ref, policy.policy_id, policy.kind, outcome),) for outcome in outcomes]
    if not isinstance(policy, ExperimentProductSelectionPolicyModel):
        raise CompilationFailure(
            "product-child-unsupported",
            f"/run_plan/selection_policies/{policy_id}",
            "product dimensions admit only fixed, enumerate, or nested product policies in v1",
        )
    child_rows = [
        _static_rows(child_id, family=family, spec=spec, limits=limits) for child_id in sorted(policy.policy_refs)
    ]
    product_cardinality = 1
    for rows in child_rows:
        if len(rows) > limits.max_product_outputs // product_cardinality:
            raise CompilationFailure(
                "product-limit-exceeded",
                f"/run_plan/selection_policies/{policy_id}",
                "selection product exceeds the compilation limit",
            )
        product_cardinality *= len(rows)
    if product_cardinality != policy.output_bound:
        raise CompilationFailure(
            "policy-cardinality-mismatch",
            f"/run_plan/selection_policies/{policy_id}",
            "selection policy output cardinality does not match its declared bound",
        )
    output: list[tuple[ResolvedSelection, ...]] = []
    for combination in product(*child_rows):
        merged: tuple[ResolvedSelection, ...] = ()
        for child in combination:
            merged = _merge_rows(merged, child)
        output.append(merged)
    return output


def _stratified_rows(
    policy: ExperimentStratifiedSelectionPolicyModel,
    coordinates: list[TrialCoordinateModel],
) -> list[CoordinateSelections]:
    output: list[CoordinateSelections] = []
    counts: dict[str, int] = {}
    for coordinate in coordinates:
        condition_id = coordinate.condition_id
        stratum = policy.strata.get(condition_id or "")
        if stratum is None:
            raise CompilationFailure(
                "stratum-coordinate-missing",
                f"/run_plan/selection_policies/{policy.policy_id}",
                "a stratified policy does not cover a logical trial coordinate",
            )
        counts[stratum.stratum_id] = counts.get(stratum.stratum_id, 0) + 1
        output.append(
            CoordinateSelections(
                (
                    ResolvedSelection(
                        policy.point_ref,
                        policy.policy_id,
                        policy.kind,
                        policy.outcomes[stratum.outcome_ref],
                    ),
                )
            )
        )
    if any(counts.get(stratum_id, 0) != stratum.output_count for stratum_id, stratum in policy.strata.items()):
        raise CompilationFailure(
            "stratum-cardinality-mismatch",
            f"/run_plan/selection_policies/{policy.policy_id}",
            "stratified output counts do not match the logical coordinate allocation",
        )
    return output


def _resolve_sample_control(
    policy: ExperimentSampleSelectionPolicyModel,
    spec: ExperimentSpecModel,
) -> tuple[ExperimentStochasticControlModel, RandomStreamControlBindingModel]:
    control = next(
        (item for item in spec.run_plan.stochastic_controls if item.control_id == policy.stochastic_control_ref),
        None,
    )
    if control is None or control.executable_binding is None:
        raise CompilationFailure(
            "sample-control-unresolved",
            f"{_SELECTION_POLICIES_ADDRESS}/{policy.policy_id}",
            "sample policy control is not executable",
        )
    binding = control.executable_binding
    if (
        binding.profile_ref.ref_id != RANDOM_STREAM_PROFILE_ID
        or binding.profile_ref.ref_version != RANDOM_STREAM_PROFILE_VERSION
    ):
        raise CompilationFailure(
            "sample-profile-mismatch",
            f"/run_plan/stochastic_controls/{control.control_id}",
            "sample policy random-stream profile does not match trial-compiler-v1",
        )
    if not isinstance(binding.root_entropy, PublicSeedModel):
        raise CompilationFailure(
            "governed-entropy-resolver-required",
            f"/run_plan/stochastic_controls/{control.control_id}",
            "governed entropy requires an authorized in-process resolver",
        )
    return control, binding


def _sample_rows(
    policy: ExperimentSampleSelectionPolicyModel,
    *,
    family: ExpandedScenario,
    spec: ExperimentSpecModel,
    coordinates: list[TrialCoordinateModel],
    limits: TrialCompilationLimitsModel,
) -> list[CoordinateSelections]:
    control, binding = _resolve_sample_control(policy, spec)
    profile_id = binding.profile_ref.ref_id
    profile = load_random_stream_profile(profile_id)
    transform = profile.transforms[BOUNDED_INTEGER_TRANSFORM_ID]
    outcomes = canonical_domain_outcomes(
        family.variation_points[policy.point_ref],
        maximum=limits.max_domain_values_per_point,
    )
    stream_key = derive_stream_key(profile_id=profile_id, root_entropy=decode_public_seed(binding.root_entropy))
    addresses = [
        StreamAddressModel(
            namespace=binding.namespace,
            trial_coordinate=coordinate,
            selection_policy_id=policy.policy_id,
            variation_point_id=policy.point_ref,
            draw_purpose="sampling-selection",
            local_coordinate=0,
        )
        for coordinate in coordinates
    ]
    batch = draw_bounded_integer_batch(
        profile_id=profile_id,
        stream_key=stream_key,
        requests=[
            BoundedIntegerDrawRequest(
                address=address,
                minimum=0,
                maximum=len(outcomes) - 1,
                max_rejection_attempts=transform.max_rejection_attempts,
            )
            for address in addresses
        ],
    )
    if batch.diagnostic is not None or batch.draws is None:
        raise CompilationFailure(
            "sample-address-collision",
            f"{_SELECTION_POLICIES_ADDRESS}/{policy.policy_id}",
            "sample policy draw addresses are not unique",
        )
    rows: list[CoordinateSelections] = []
    for address, draw in zip(addresses, batch.draws, strict=True):
        if draw.rejection_exhausted or draw.value is None:
            raise CompilationFailure(
                "sample-rejection-exhausted",
                f"{_SELECTION_POLICIES_ADDRESS}/{policy.policy_id}",
                "sample policy exhausted its bounded transform",
            )
        rows.append(
            CoordinateSelections(
                (
                    ResolvedSelection(
                        policy.point_ref,
                        policy.policy_id,
                        policy.kind,
                        outcomes[draw.value],
                    ),
                ),
                (
                    RandomStreamDrawRecordModel(
                        control_id=control.control_id,
                        address=address,
                        transform_id=BOUNDED_INTEGER_TRANSFORM_ID,
                        transform_version=BOUNDED_INTEGER_TRANSFORM_VERSION,
                        local_coordinate=0,
                        outcome=PublicRandomOutcomeModel(kind="public-value", value=str(draw.value)),
                        rejection_attempts=draw.rejection_attempts,
                        rejection_exhausted=False,
                    ),
                ),
            )
        )
    return rows


def compile_coordinate_selections(
    *,
    family: ExpandedScenario,
    spec: ExperimentSpecModel,
    coordinates: list[TrialCoordinateModel],
    limits: TrialCompilationLimitsModel,
) -> list[CoordinateSelections]:
    """Compile the closed policy graph into one complete selection set per coordinate."""

    policies = spec.run_plan.selection_policies
    if spec.factorial_design is not None:
        return _factorial_coordinate_selections(family, spec, coordinates)
    referenced = {
        child
        for policy in policies.values()
        if isinstance(policy, ExperimentProductSelectionPolicyModel)
        for child in policy.policy_refs
    }
    roots = sorted(set(policies) - referenced)
    non_fixed_roots = [root for root in roots if not isinstance(policies[root], ExperimentFixedSelectionPolicyModel)]
    if len(non_fixed_roots) > 1:
        raise CompilationFailure(
            "policy-roots-ambiguous",
            _SELECTION_POLICIES_ADDRESS,
            "multiple non-fixed selection policy roots are ambiguous",
        )
    if not policies:
        rows = [CoordinateSelections(()) for _ in coordinates]
    elif non_fixed_roots:
        root = policies[non_fixed_roots[0]]
        if isinstance(root, ExperimentStratifiedSelectionPolicyModel):
            rows = _stratified_rows(root, coordinates)
        elif isinstance(root, ExperimentSampleSelectionPolicyModel):
            rows = _sample_rows(root, family=family, spec=spec, coordinates=coordinates, limits=limits)
        else:
            static = _static_rows(root.policy_id, family=family, spec=spec, limits=limits)
            if len(static) != len(coordinates):
                raise CompilationFailure(
                    "policy-cardinality-mismatch",
                    f"/run_plan/selection_policies/{root.policy_id}",
                    "selection policy output does not exactly cover the logical coordinates",
                )
            rows = [CoordinateSelections(selections) for selections in static]
    else:
        rows = [CoordinateSelections(()) for _ in coordinates]

    fixed_roots = [root for root in roots if isinstance(policies[root], ExperimentFixedSelectionPolicyModel)]
    additions = tuple(
        ResolvedSelection(
            policies[root].point_ref,
            policies[root].policy_id,
            policies[root].kind,
            policies[root].outcome,
        )
        for root in fixed_roots
    )
    completed = [CoordinateSelections(_merge_rows(row.selections, additions), row.draws) for row in rows]
    expected_points = set(family.variation_points)
    if any({selection.point_id for selection in row.selections} != expected_points for row in completed):
        raise CompilationFailure(
            "variation-points-uncovered",
            _SELECTION_POLICIES_ADDRESS,
            "every family variation point must be selected exactly once",
        )
    return completed


def _factorial_coordinate_selections(
    family: ExpandedScenario,
    spec: ExperimentSpecModel,
    coordinates: list[TrialCoordinateModel],
) -> list[CoordinateSelections]:
    if spec.factorial_design.profile == "factorial-treatments-v1":
        return _treatment_coordinate_selections(family, spec, coordinates)
    if spec.run_plan.selection_policies:
        raise CompilationFailure(
            "factorial-selection-conflict",
            _SELECTION_POLICIES_ADDRESS,
            "factorial binding selection cannot also declare selection policies",
        )
    descriptors_by_condition = {}
    for descriptor in spec.binding_descriptors.descriptors:
        descriptors_by_condition.setdefault(descriptor.source_condition_id, []).append(descriptor)
    return [
        _factorial_row(family, descriptors_by_condition.get(coordinate.condition_id, ())) for coordinate in coordinates
    ]


def _treatment_coordinate_selections(
    family: ExpandedScenario,
    spec: ExperimentSpecModel,
    coordinates: list[TrialCoordinateModel],
) -> list[CoordinateSelections]:
    resolver = ExpandedScenarioBindingTargetResolver(family)
    rows = {}
    fixed = tuple(
        ResolvedSelection(policy.point_ref, policy.policy_id, policy.kind, policy.outcome)
        for _, policy in sorted(spec.run_plan.selection_policies.items())
    )
    for condition_id, assignment in sorted(spec.run_plan.allocation.condition_assignments.items()):
        scalar = tuple(
            ResolvedSelection(binding.target.variation_point_id, "factorial-treatments-v1", "stratified", binding.value)
            for binding in assignment.required_bindings
            if binding.target.plane == "scenario"
        )
        typed = []
        for treatment in assignment.required_selections:
            try:
                resolver.validate_selection(treatment)
            except SDLSelectionError as exc:
                raise CompilationFailure(
                    "selection-treatment-rejected",
                    _FACTORIAL_DESIGN_ADDRESS,
                    "a typed selection failed authoritative scenario-family admission",
                ) from exc
            typed.append(
                ResolvedSelection(
                    treatment.target.variation_point_id,
                    "factorial-treatments-v1",
                    "stratified",
                    treatment.outcome,
                    treatment,
                )
            )
        combined = _merge_rows(_merge_rows(scalar, tuple(typed)), fixed)
        if {selection.point_id for selection in combined} != set(family.variation_points):
            raise CompilationFailure(
                "variation-points-uncovered",
                _FACTORIAL_DESIGN_ADDRESS,
                "factorial effects and fixed policies must cover every family point exactly once",
            )
        rows[condition_id] = CoordinateSelections(combined)
    return [rows[coordinate.condition_id] for coordinate in coordinates]


def _factorial_row(
    family: ExpandedScenario,
    descriptors: Sequence[ExperimentBindingDescriptorModel],
) -> CoordinateSelections:
    selections = tuple(
        ResolvedSelection(descriptor.target.variation_point_id, "factorial-bindings-v1", "stratified", descriptor.value)
        for descriptor in descriptors
        if descriptor.target.plane == "scenario"
    )
    if any(not isinstance(selection.outcome, LiteralBindingValueModel) for selection in selections):
        raise CompilationFailure(
            "factorial-scenario-value-unsupported",
            _FACTORIAL_DESIGN_ADDRESS,
            "factorial scenario bindings require literal scalar outcomes",
        )
    if {selection.point_id for selection in selections} != set(family.variation_points):
        raise CompilationFailure(
            "variation-points-uncovered",
            _FACTORIAL_DESIGN_ADDRESS,
            "factorial bindings must cover every scenario variation point exactly once",
        )
    return CoordinateSelections(tuple(sorted(selections, key=lambda selection: selection.point_id)))


__all__ = ["CoordinateSelections", "ResolvedSelection", "compile_coordinate_selections"]
