"""Participant action contracts, observation boundaries, outcome-interpretation rules."""

from collections.abc import Callable

from raes.scenario import InstantiatedScenario
from raes_contracts.canonical import canonical_json_bytes
from raes_contracts.digests import sha256_hex
from raes_contracts.participant_outcome_semantics import (
    OutcomeInterpretationSourceLayer,
    OutcomeInterpretationTargetLayer,
)

from ..models import (
    ParticipantActionContractRuntime,
    ParticipantObservationBoundaryRuntime,
    ParticipantOutcomeInterpretationRuleRuntime,
)
from .addresses import (
    _action_contract_address,
    _evaluation_address,
    _objective_address,
    _observation_boundary_address,
    _outcome_interpretation_rule_address,
    _workflow_address,
)
from .alias_index import _runtime_visibility_reference_index
from .support import _dedupe, _dump
from .view_relations import (
    _boundary_reference_aliases,
    _compile_view_relation_timeline,
    _initial_view_relation,
    _normalize_visibility_references,
    _ordered_view_transitions,
    _view_relation_refs,
    _visibility_aliases_by_address,
)


def _dedupe_field(items: list[object], key: str) -> tuple[str, ...]:
    return _dedupe([str(item.get(key, "")) for item in items if isinstance(item, dict) and item.get(key)])


def _shared_state_refs(interactions: list[object]) -> tuple[str, ...]:
    return _dedupe(
        [
            str(ref)
            for interaction in interactions
            if isinstance(interaction, dict)
            for ref in interaction.get("shared_state_refs", [])
        ]
    )


def _backend_failure_mappings(contract_spec: dict[str, object]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "backend_error_code": str(mapping.get("backend_error_code", "")),
            "failure_class": str(mapping.get("failure_class", "")),
            "diagnostic": str(mapping.get("diagnostic", "")),
        }
        for mapping in contract_spec.get("backend_failure_mappings", [])
        if isinstance(mapping, dict)
    )


def _backend_timing_disclosures(contract_spec: dict[str, object]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "disclosure_id": str(disclosure.get("disclosure_id", "")),
            "disclosure_kind": str(disclosure.get("disclosure_kind", "")),
            "support_mode": str(disclosure.get("support_mode", "")),
            "description": str(disclosure.get("description", "")),
            "affected_temporal_ids": [str(temporal_id) for temporal_id in disclosure.get("affected_temporal_ids", [])],
            "limitations": [str(limitation) for limitation in disclosure.get("limitations", [])],
        }
        for disclosure in contract_spec.get("backend_timing_disclosures", [])
        if isinstance(disclosure, dict)
    )


def _compiled_argument_shape(
    address: str,
    contract_spec: dict[str, object],
) -> tuple[str, tuple[dict[str, object], ...]]:
    raw_arguments = contract_spec.get("arguments", {})
    arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
    digest = sha256_hex(canonical_json_bytes(arguments))
    definitions = tuple(
        {"name": str(name), **definition}
        for name, definition in sorted(arguments.items())
        if isinstance(definition, dict)
    )
    return f"{address}.argument-shape.sha256-{digest}", definitions


def _compile_action_contracts(scenario: InstantiatedScenario) -> dict[str, ParticipantActionContractRuntime]:
    action_contracts: dict[str, ParticipantActionContractRuntime] = {}
    for name, contract in scenario.action_contracts.items():
        contract_spec = _dump(contract)
        interactions = contract_spec.get("interactions", [])
        temporal_contracts = contract_spec.get("temporal_contracts", [])
        address = _action_contract_address(name)
        argument_shape_ref, argument_definitions = _compiled_argument_shape(address, contract_spec)
        action_contracts[address] = ParticipantActionContractRuntime(
            address=address,
            name=name,
            action_name=name,
            argument_shape_ref=argument_shape_ref,
            argument_definitions=argument_definitions,
            semantic_version=str(contract_spec.get("semantic_version", "")),
            lifecycle_state=str(contract_spec.get("lifecycle_state", "")),
            behavioral_granularity=str(contract_spec.get("behavioral_granularity", "")),
            precondition_classes=_dedupe_field(contract_spec.get("preconditions", []), "precondition_class"),
            effect_classes=_dedupe_field(contract_spec.get("effects", []), "effect_class"),
            failure_classes=_dedupe(str(failure_class) for failure_class in contract_spec.get("failure_classes", [])),
            backend_failure_mappings=_backend_failure_mappings(contract_spec),
            interaction_classes=_dedupe_field(interactions, "interaction_class"),
            shared_state_refs=_shared_state_refs(interactions),
            commutative_interaction_targets=_dedupe(
                str(interaction.get("target", ""))
                for interaction in interactions
                if interaction.get("commutative") is True
            ),
            merge_rule_refs=_dedupe(
                str(interaction["merge_rule_ref"])
                for interaction in interactions
                if interaction.get("merge_rule_ref") is not None
            ),
            temporal_contract_ids=_dedupe_field(temporal_contracts, "temporal_id"),
            temporal_kinds=_dedupe_field(temporal_contracts, "temporal_kind"),
            time_domains=_dedupe_field(temporal_contracts, "time_domain"),
            clock_authorities=_dedupe_field(temporal_contracts, "clock_authority"),
            backend_timing_disclosures=_backend_timing_disclosures(contract_spec),
            spec=contract_spec,
        )
    return action_contracts


def _compile_observation_boundaries(scenario: InstantiatedScenario) -> dict[str, ParticipantObservationBoundaryRuntime]:
    observation_boundaries: dict[str, ParticipantObservationBoundaryRuntime] = {}
    address_index = _runtime_visibility_reference_index(scenario)
    aliases_by_address = _visibility_aliases_by_address(address_index)
    for name, boundary in scenario.observation_boundaries.items():
        boundary_spec = _dump(boundary)
        compiled_spec = _normalize_visibility_references(boundary_spec, address_index)
        view_rules = compiled_spec.get("view_rules", [])
        view_transitions = compiled_spec.get("view_transitions", [])
        initial_view_relation = _initial_view_relation(view_rules=view_rules)
        disclosed_refs = _view_relation_refs(initial_view_relation, {"disclosed"})
        evidence_only_refs = _view_relation_refs(initial_view_relation, {"evidence_only"})
        discovered_refs = _view_relation_refs(initial_view_relation, {"discovered"})
        inferred_refs = _view_relation_refs(initial_view_relation, {"inferred"})
        concealed_refs = _view_relation_refs(initial_view_relation, {"concealed"})
        deceptive_refs = _view_relation_refs(initial_view_relation, {"deceptive"})
        view_relation_timeline = _compile_view_relation_timeline(
            view_rules=view_rules,
            view_transitions=view_transitions,
        )
        ordered_view_transitions = _ordered_view_transitions(view_transitions)
        observation_boundaries[_observation_boundary_address(name)] = ParticipantObservationBoundaryRuntime(
            address=_observation_boundary_address(name),
            name=name,
            boundary_name=name,
            projection_basis=str(boundary_spec.get("projection_basis", "")),
            hidden_refs=tuple(str(ref) for ref in compiled_spec.get("hidden_refs", [])),
            observable_refs=tuple(str(ref) for ref in compiled_spec.get("observable_refs", [])),
            evidence_refs=tuple(str(ref) for ref in compiled_spec.get("evidence_refs", [])),
            disclosed_refs=disclosed_refs,
            evidence_only_refs=evidence_only_refs,
            discovered_refs=discovered_refs,
            inferred_refs=inferred_refs,
            concealed_refs=concealed_refs,
            deceptive_refs=deceptive_refs,
            view_transitions=ordered_view_transitions,
            view_relation_timeline=view_relation_timeline,
            realized_view_disclosure=str(boundary_spec.get("realized_view_disclosure") or ""),
            reference_aliases=_boundary_reference_aliases(compiled_spec, aliases_by_address),
            spec=boundary_spec,
        )
    return observation_boundaries


_OUTCOME_SOURCE_LAYER_ADDRESS: dict[str, Callable[[str], str]] = {
    OutcomeInterpretationSourceLayer.PARTICIPANT_ACTION_OUTCOME.value: _action_contract_address,
    OutcomeInterpretationSourceLayer.OBJECTIVE_RESULT.value: _objective_address,
    OutcomeInterpretationSourceLayer.WORKFLOW_RESULT.value: _workflow_address,
    OutcomeInterpretationSourceLayer.EVALUATION_RESULT.value: _evaluation_address,
}

_OUTCOME_TARGET_LAYER_ADDRESS: dict[str, Callable[[str], str]] = {
    OutcomeInterpretationTargetLayer.OBJECTIVE_RESULT.value: _objective_address,
    OutcomeInterpretationTargetLayer.WORKFLOW_RESULT.value: _workflow_address,
    OutcomeInterpretationTargetLayer.EVALUATION_RESULT.value: _evaluation_address,
}


def _outcome_source_ref_address(source_layer: str, ref: str) -> str:
    builder = _OUTCOME_SOURCE_LAYER_ADDRESS.get(source_layer)
    return builder(ref) if builder is not None else ref


def _outcome_target_ref_address(target_layer: str, ref: str) -> str:
    builder = _OUTCOME_TARGET_LAYER_ADDRESS.get(target_layer)
    return builder(ref) if builder is not None else ref


def _compile_outcome_interpretation_rules(
    scenario: InstantiatedScenario,
) -> dict[str, ParticipantOutcomeInterpretationRuleRuntime]:
    rules: dict[str, ParticipantOutcomeInterpretationRuleRuntime] = {}
    for name, rule in scenario.outcome_interpretation_rules.items():
        rule_spec = _dump(rule)
        sources = tuple(source for source in rule_spec.get("source_bindings", ()) if isinstance(source, dict))
        targets = tuple(target for target in rule_spec.get("target_bindings", ()) if isinstance(target, dict))
        source_layers = tuple(str(source.get("source_layer", "")) for source in sources)
        target_layers = tuple(str(target.get("target_layer", "")) for target in targets)
        source_refs = tuple(
            _outcome_source_ref_address(str(source.get("source_layer", "")), str(source.get("ref", "")))
            for source in sources
        )
        target_refs = tuple(
            _outcome_target_ref_address(str(target.get("target_layer", "")), str(target.get("ref", "")))
            for target in targets
        )
        address = _outcome_interpretation_rule_address(name)
        rules[address] = ParticipantOutcomeInterpretationRuleRuntime(
            address=address,
            name=name,
            rule_name=name,
            semantic_version=str(rule_spec.get("semantic_version", "")),
            participant_scope=str(rule_spec.get("participant_scope", "")),
            observation_point_basis=str(rule_spec.get("observation_point_basis", "")),
            interpretation_basis=str(rule_spec.get("interpretation_basis", "")),
            source_layers=source_layers,
            source_refs=source_refs,
            target_layers=target_layers,
            target_refs=target_refs,
            evidence_refs=tuple(str(ref) for ref in rule_spec.get("evidence_refs", ())),
            limitations=tuple(str(item) for item in rule_spec.get("limitations", ())),
            spec=rule_spec,
        )
    return rules
