"""Projection of measured participant-opacity facts into the closed transcript.

Each transcript field is derived from one named measured basis. A field whose
basis was not measured stays ``None`` so the judging half can refuse it as
missing evidence instead of defaulting it to the expected value. The runner
also owns the expected normal form for each admitted profile revision and the
derivation of the realization owner from committed runtime bindings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.participant_crossing import ParticipantOpacityRuntimeEnforcementBindingModel
from raes_contracts.runtime_state import OperationState

from raes_conformance.conformance.participant_opacity_execution import _OperationFacts, _PointMeasurement
from raes_conformance.conformance.participant_opacity_types import (
    OBSERVATION_FIELDS,
    ParticipantOpacityProbeCase,
    ParticipantOpacityProbeObservation,
    ParticipantOpacityRealizationOwner,
)

MeasuredObservation = dict[str, object | None]

_UNIFORM_DENIAL = ParticipantOpacityProbeObservation(
    decision="deny",
    failure="uniform-refusal",
    action_availability="denied",
    delivery="withheld",
    omission="recorded-at-governed-opportunity",
    retry="stable-replay",
    logical_timing="logical-bucket:contained",
    logical_order="stable-causal-order",
    policy_release_effect="contained",
    external_effect="none",
    payload_released=False,
)

# The runner, not the harness, owns the expected projection of each admitted
# profile revision. ``sem-231/runtime-rev2`` admits uniform denial only.
NORMAL_FORMS: Mapping[tuple[str, str], ParticipantOpacityProbeObservation] = {
    ("participant-opacity-runtime-reference-v1", "sem-231/runtime-rev2"): _UNIFORM_DENIAL,
}

# Logical stages a contained governed operation commits under the untimed,
# total-order profile: ingress decides, an exact replay commits nothing, and an
# egress opportunity records its withheld delivery attempt.
_CONTAINED_STAGES = (
    ("requested", "decided"),
    (),
    ("requested", "decided", "delivery-attempted"),
)
_RELEASE_STAGES = frozenset({"transformed", "disclosed", "delivered", "observed"})


def _occurrence(record: Mapping[str, object]) -> Mapping[str, object]:
    occurrence = record.get("occurrence")
    return cast("Mapping[str, object]", occurrence) if isinstance(occurrence, Mapping) else {}


def _stages(facts: _OperationFacts) -> tuple[str, ...]:
    return tuple(str(_occurrence(record).get("stage")) for record in facts.records)


def _by_terminal_state(ingress: _OperationFacts | None, *, failed: str, succeeded: str) -> str | None:
    """Map the terminal action state; a running or indeterminate operation is not a refusal."""

    if ingress is None or ingress.terminal_state is None:
        return None
    if ingress.terminal_state == OperationState.FAILED.value:
        return failed
    return succeeded if ingress.terminal_state == OperationState.SUCCEEDED.value else "indeterminate"


def _decision(ingress: _OperationFacts | None) -> str | None:
    return _by_terminal_state(ingress, failed="deny", succeeded="allow")


def _failure(ingress: _OperationFacts | None) -> str | None:
    return _by_terminal_state(ingress, failed="uniform-refusal", succeeded="none")


def _availability(ingress: _OperationFacts | None) -> str | None:
    return _by_terminal_state(ingress, failed="denied", succeeded="available")


def _withheld_attempt(egress: _OperationFacts) -> Mapping[str, object] | None:
    for record in egress.records:
        occurrence = _occurrence(record)
        if occurrence.get("stage") == "delivery-attempted" and occurrence.get("disposition") == "withheld":
            return occurrence
    return None


def _delivery(egress: _OperationFacts | None) -> str | None:
    if egress is None:
        return None
    if egress.result == "view":
        return "delivered"
    # A refusal that never reached the governed opportunity is not withholding.
    return "withheld" if _withheld_attempt(egress) is not None else None


def _omission(egress: _OperationFacts | None) -> str | None:
    if egress is None:
        return None
    if egress.result == "view":
        return "not-recorded"
    attempt = _withheld_attempt(egress)
    recorded = attempt is not None and bool(attempt.get("owning_occurrence_ref"))
    return "recorded-at-governed-opportunity" if recorded else None


def _retry(ingress: _OperationFacts | None, replay: _OperationFacts | None) -> str | None:
    if ingress is None or replay is None or ingress.operation_id is None:
        return None
    stable = replay.operation_id == ingress.operation_id and not replay.records and not replay.backend_calls
    return "stable-replay" if stable else "divergent-replay"


def _timing(operations: Sequence[_OperationFacts]) -> str:
    steps = tuple(len(facts.records) for facts in operations)
    if steps == tuple(len(stages) for stages in _CONTAINED_STAGES):
        return "logical-bucket:contained"
    return "logical-bucket:" + "-".join(str(step) for step in steps)


def _causal_chain_holds(records: Sequence[Mapping[str, object]]) -> bool:
    """Require one total logical order whose predecessors are earlier committed facts."""

    seen: set[object] = set()
    previous_order: int | None = None
    for record in records:
        order = _occurrence(record).get("effective_order")
        if not isinstance(order, int) or (previous_order is not None and order != previous_order + 1):
            return False
        predecessors = record.get("predecessor_event_refs") or ()
        if not isinstance(predecessors, Sequence) or any(ref not in seen for ref in predecessors):
            return False
        seen.add(record.get("event_id"))
        previous_order = order
    return True


def _order(operations: Sequence[_OperationFacts]) -> str:
    stages = tuple(_stages(facts) for facts in operations)
    records = [record for facts in operations for record in facts.records]
    if stages == _CONTAINED_STAGES and _causal_chain_holds(records):
        return "stable-causal-order"
    return "order:" + canonical_json_digest([list(item) for item in stages]).removeprefix("sha256:")[:16]


def _release(operations: Sequence[_OperationFacts]) -> str:
    occurrences = [_occurrence(record) for facts in operations for record in facts.records]
    policies = {canonical_json_digest(cast("dict", occurrence.get("policy") or {})) for occurrence in occurrences}
    released = any(occurrence.get("stage") in _RELEASE_STAGES for occurrence in occurrences)
    return "released" if released or len(policies) > 1 else "contained"


def _external_effect(measurement: _PointMeasurement) -> str | None:
    if measurement.readback_before is None or measurement.readback_after is None:
        return None
    return "none" if measurement.readback_before == measurement.readback_after else "observed"


def _payload(egress: _OperationFacts | None) -> bool | None:
    if egress is None or egress.result is None:
        return None
    return egress.result == "view"


def project_observation(measurement: _PointMeasurement) -> MeasuredObservation:
    """Derive the closed transcript from measured facts; unmeasured fields stay ``None``."""

    ingress, replay, egress = measurement.ingress, measurement.replay, measurement.egress
    operations = (ingress, replay, egress)
    complete_sequence = all(facts is not None for facts in operations)
    sequence = cast("tuple[_OperationFacts, ...]", operations)
    return {
        "decision": _decision(ingress),
        "failure": _failure(ingress),
        "action_availability": _availability(ingress),
        "delivery": _delivery(egress),
        "omission": _omission(egress),
        "retry": _retry(ingress, replay),
        "logical_timing": _timing(sequence) if complete_sequence else None,
        "logical_order": _order(sequence) if complete_sequence else None,
        "policy_release_effect": _release(sequence) if complete_sequence else None,
        "external_effect": _external_effect(measurement),
        "payload_released": _payload(egress),
    }


def visible_projection(measurement: _PointMeasurement) -> list[object]:
    """Participant-visible facts compared across points; identifiers and times are excluded."""

    projected: list[object] = []
    for facts in (measurement.ingress, measurement.replay, measurement.egress):
        if facts is None:
            projected.append(None)
            continue
        projected.append(
            {
                "receipt_accepted": facts.receipt_accepted,
                "terminal_state": facts.terminal_state,
                "diagnostic_codes": list(facts.diagnostic_codes),
                "result": facts.result,
                "records": [
                    {
                        key: _occurrence(record).get(key)
                        for key in ("stage", "interaction_kind", "direction", "disposition", "reason_code", "gates")
                    }
                    for record in facts.records
                ],
            }
        )
    return projected


def missing_fields(observations: Sequence[MeasuredObservation]) -> tuple[str, ...]:
    return tuple(name for name in OBSERVATION_FIELDS if any(item[name] is None for item in observations))


def disagreeing_fields(
    measured: MeasuredObservation,
    reported: ParticipantOpacityProbeObservation,
) -> tuple[str, ...]:
    """Fields where the backend's reported transcript differs from a measured value."""

    return tuple(
        name for name in OBSERVATION_FIELDS if measured[name] is not None and measured[name] != getattr(reported, name)
    )


def _decided_bindings(measurement: _PointMeasurement) -> list[object] | None:
    decided = [
        _occurrence(record)
        for facts in (measurement.ingress, measurement.replay, measurement.egress)
        if facts is not None
        for record in facts.records
        if _occurrence(record).get("stage") == "decided"
    ]
    return [occurrence.get("opacity_enforcement") for occurrence in decided] if decided else None


def _case_profile_binding(
    case: ParticipantOpacityProbeCase,
    payload: object,
) -> ParticipantOpacityRuntimeEnforcementBindingModel | None:
    """Parse a committed binding and keep it only for the exact case profile."""

    binding = None
    if isinstance(payload, Mapping):
        try:
            binding = ParticipantOpacityRuntimeEnforcementBindingModel.model_validate(payload)
        except ValueError:
            binding = None
    expected = (case.profile_id, case.profile_revision, case.profile_digest)
    if (
        binding is None
        or binding.assurance_axis != "runtime-enforcement"
        or (binding.profile_id, binding.profile_revision, binding.profile_digest) != expected
    ):
        return None
    return binding


def _runtime_binding_rejoins(
    case: ParticipantOpacityProbeCase,
    measurement: _PointMeasurement,
    payload: object,
) -> bool:
    """Require an exact case-profile binding that rejoins to the point's trusted support."""

    binding = _case_profile_binding(case, payload)
    if binding is None:
        return False
    support = next((item for item in measurement.opacity_supports if item.binding == binding), None)
    return support is not None and (support.predicate_positive_case_ref, support.predicate_negative_case_ref) == (
        case.protected_point.point_ref,
        case.complement_point.point_ref,
    )


def derive_realization_owner(
    case: ParticipantOpacityProbeCase,
    measurements: Sequence[_PointMeasurement],
) -> ParticipantOpacityRealizationOwner:
    """Derive ownership from committed bindings, never from a harness label.

    Under the published runtime profile RUN-319 produces the normal form before
    any protected backend effect, so the runtime shields the backend and the
    strongest derivable owner is runtime mediation.
    """

    for measurement in measurements:
        bindings = _decided_bindings(measurement)
        if not measurement.history_valid or bindings is None:
            return ParticipantOpacityRealizationOwner.DECLARATION_ONLY
        if not all(_runtime_binding_rejoins(case, measurement, payload) for payload in bindings):
            return ParticipantOpacityRealizationOwner.DECLARATION_ONLY
    return ParticipantOpacityRealizationOwner.RUNTIME_MEDIATED


__all__ = (
    "NORMAL_FORMS",
    "MeasuredObservation",
    "derive_realization_owner",
    "disagreeing_fields",
    "missing_fields",
    "project_observation",
    "visible_projection",
)
