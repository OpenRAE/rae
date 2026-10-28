"""Independent finite expectations; runtime reducers never generate the oracle."""

from __future__ import annotations

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.runtime_state import OperationState

from .modular_control_execution import _Measurement
from .modular_control_refusals import negative_condition as _negative_condition
from .modular_control_replay import ledger_digest
from .modular_control_types import ModularControlCase, ModularControlOperation

_NEGATIVE = frozenset({"mandatory-coverage", "strict-denial", "authority", "stale-cut", "conflict", "integrity"})


def case_checks(case: ModularControlCase, measured: _Measurement) -> tuple[str, ...]:
    failures: list[str] = []
    actual = tuple(
        item.composition.disposition
        for item in measured.evaluations
        if item.commit.receipt is not None and item.commit.receipt.ref in measured.parent_operation_ids
    )
    if actual != case.expected_compositions:
        failures.append("composition")
    for identity in measured.parent_operation_ids:
        parent = measured.records.get(identity)
        evaluation = next(
            (
                item
                for item in measured.evaluations
                if item.commit.receipt is not None and item.commit.receipt.ref == identity
            ),
            None,
        )
        if (
            evaluation is not None
            and evaluation.composition.disposition == "eligible"
            and (parent is None or parent.status.state is not OperationState.SUCCEEDED)
        ):
            failures.append("parent-outcome")
    expected_calls = {key: value for key, value in case.expected_calls.items() if value}
    if dict(measured.counts) != expected_calls:
        failures.append("execution-count")
    if measured.outcomes != dict(case.expected_effects):
        failures.append("effect-outcome")
    if not measured.duplicate_stable:
        failures.append("duplicate-changed")
    if measured.residual_state:
        failures.append("cleanup")
    if not case.steps or not any(step.operation is not ModularControlOperation.REOPEN for step in case.steps):
        failures.append("no-operation")
    if case.obligation in _NEGATIVE:
        blocked = measured.refusals or (
            measured.parent_states and all(state is not OperationState.SUCCEEDED for state in measured.parent_states)
        )
        if not blocked or measured.counts or "applied" in measured.outcomes.values():
            failures.append("prohibited-execution")
        if not _negative_condition(case, measured):
            failures.append("unrelated-refusal")
        else:
            measured.refusal_causes.add(case.obligation)
    check = _OBLIGATION_CHECKS.get(case.obligation)
    if check is not None and not check(case, measured):
        failures.append("obligation-evidence")
    if case.obligation.startswith("effect:"):
        failures.extend(_effect_checks(case, measured))
    return tuple(failures)


def _has_subset(case: ModularControlCase, measured: _Measurement) -> bool:
    return any(
        len(item.request.applicability.applicable_slot_ids) < len(item.request.selection.slots)
        and len(item.request.applicability.coverage) == len(item.request.selection.obligations)
        for item in measured.evaluations
    )


def _has_dependency(case: ModularControlCase, measured: _Measurement) -> bool:
    return any(invocation.predecessor_inputs for item in measured.evaluations for invocation in item.invocations)


def _has_optional_failure(case: ModularControlCase, measured: _Measurement) -> bool:
    return (
        bool(measured.parent_states)
        and all(state is OperationState.SUCCEEDED for state in measured.parent_states)
        and any(item.lost_advice and item.composition.disposition == "eligible" for item in measured.evaluations)
    )


def _has_support(case: ModularControlCase, measured: _Measurement) -> bool:
    return any(item.support for item in measured.evaluations)


def _has_influence(case: ModularControlCase, measured: _Measurement) -> bool:
    return (
        any(
            item.composition.disposition == "eligible"
            and any(result.payload is not None and result.payload.kind == "ifc-fact" for result in item.results)
            for item in measured.evaluations
        )
        and OperationState.SUCCEEDED in measured.parent_states
    )


def _has_non_ifc(case: ModularControlCase, measured: _Measurement) -> bool:
    return any(
        item.results
        and all(result.payload is None or result.payload.kind != "ifc-fact" for result in item.results)
        and any(result.payload is not None for result in item.results)
        for item in measured.evaluations
    )


def _has_phase(case: ModularControlCase, measured: _Measurement) -> bool:
    return (
        any(item.effect_plan.effects for item in measured.evaluations)
        and any(state is not OperationState.SUCCEEDED for state in measured.parent_states)
        and measured.counts.get("participant_runtime.admit_action", 0) == 0
    )


def _has_duplicate(case: ModularControlCase, measured: _Measurement) -> bool:
    return measured.exact_replays > 0 and measured.duplicate_stable and bool(measured.evaluations)


def _has_restart(case: ModularControlCase, measured: _Measurement) -> bool:
    return measured.reopened and measured.replayed_after_reopen and _has_duplicate(case, measured)


def _has_trigger_bound(case: ModularControlCase, measured: _Measurement) -> bool:
    return (
        len(measured.evaluations) > 1
        and any(
            item.request.context.effects_consumed > 0 or item.request.context.rule_firings
            for item in measured.evaluations
        )
        and measured.duplicate_stable
    )


def _has_final_sink(case: ModularControlCase, measured: _Measurement) -> bool:
    return bool(measured.refusals) and any(
        event.details.get("flow_final_disposition") in {"deny", "unsupported", "stale", "unresolved"}
        and event.operation_id in measured.records
        and measured.records[event.operation_id].status.state is OperationState.FAILED
        and measured.records[event.operation_id].result_payload is None
        for event in measured.audit
    )


_OBLIGATION_CHECKS = {
    "applicable-subset": _has_subset,
    "dependency": _has_dependency,
    "optional-failure": _has_optional_failure,
    "support-strength": _has_support,
    "permissive-influence": _has_influence,
    "non-ifc": _has_non_ifc,
    "phase-decision": _has_phase,
    "duplicate": _has_duplicate,
    "restart": _has_restart,
    "trigger-bound": _has_trigger_bound,
    "final-sink": _has_final_sink,
}


def _effect_checks(case: ModularControlCase, measured: _Measurement) -> list[str]:
    kind = case.obligation.removeprefix("effect:")
    effects = {effect.effect_id: effect for item in measured.evaluations for effect in item.effect_plan.effects}
    observations = {item.effect_id: item for item in measured.observations}
    if not measured.outcomes or len(observations) != len(measured.observations):
        return ["missing-owner-observation"]
    failures: list[str] = []
    if not any(effects[key].target.kind == kind for key in measured.outcomes if key in effects):
        failures.append("effect-kind")
    for identity, disposition in measured.outcomes.items():
        observed = observations.get(identity)
        claims = [
            record
            for record in measured.records.values()
            if isinstance(record.result_payload, dict) and record.result_payload.get("effect_id") == identity
        ]
        if observed is None or not observed.evidence_refs or observed.disposition != disposition:
            failures.append("owner-readback")
            continue
        owner = measured.records.get(observed.receipt_ref)
        if owner is None or not claims:
            failures.append("owner-receipt")
            continue
        if not any(
            record.result_payload.get("disposition") == disposition
            and record.result_payload.get("receipt", {}).get("ref") == observed.receipt_ref
            and owner.receipt.context.parent_operation_id == record.receipt.operation_id
            for record in claims
        ):
            failures.append("durable-owner-join")
        if disposition == "applied" and owner.status.state is not OperationState.SUCCEEDED:
            failures.append("owner-not-applied")
        if kind == "inject" and disposition == "applied" and owner.inject_occurrence is None:
            failures.append("missing-world-occurrence")
    if kind == "inject" and not measured.counts.get("operation_provider.start_operation", 0):
        failures.append("missing-world-dispatch")
    return failures


def artifact_bindings(case: ModularControlCase, measured: _Measurement) -> dict[str, str]:
    """Pin exact inputs without copying provider payloads into the report."""

    installed = case.options.get("participant_control")
    result: dict[str, str] = {}
    if measured.snapshot_digest is not None:
        result["snapshot"] = measured.snapshot_digest
        result["ledger"] = ledger_digest(measured)
    if measured.invocation_digest is not None:
        result["invocations"] = measured.invocation_digest
    if installed is not None:
        selection = installed.selection.model_dump(mode="json")
        result["selection"] = canonical_json_digest(selection)
        result["apparatus"] = canonical_json_digest(selection["apparatus"])
        for label, field in (
            ("profiles", "profiles"),
            ("mechanisms", "mechanism"),
            ("implementation", "implementation"),
            ("configuration", "configuration_digest"),
            ("authority", "authority"),
            ("memory", "memory_scope"),
        ):
            result[label] = canonical_json_digest([item[field] for item in selection["bindings"]])
    if measured.evaluations:
        contexts = [item.request.context.model_dump(mode="json") for item in measured.evaluations]
        for label, field in (("cut", "state_cut"), ("policy", "policy"), ("run", "run"), ("trigger", "trigger")):
            result[label] = canonical_json_digest([item[field] for item in contexts])
        result["evaluations"] = canonical_json_digest([item.model_dump(mode="json") for item in measured.evaluations])
        result["effects"] = canonical_json_digest(
            [effect.model_dump(mode="json") for item in measured.evaluations for effect in item.effect_plan.effects]
        )
    return result
