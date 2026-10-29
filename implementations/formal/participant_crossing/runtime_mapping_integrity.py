"""Independent preservation and atomic-publication checks for runtime evidence."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingOccurrenceModel,
)
from raes_contracts.contracts.participant_crossing_validation import (
    validate_participant_crossing_occurrence_context,
)
from raes_contracts.participant_control_evaluation_history import (
    iter_participant_control_evaluation_snapshot_violations,
)
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane_store import (
    AuditEvent,
    ControlPlaneOperationRecord,
    _require_operation_audit_binding,
    _require_operation_record_transition,
    _snapshot_payload,
)
from raes_runtime.control_plane_store_records import (
    _record_from_payload,
    _record_payload,
)
from raes_runtime.participant_crossing_state_cut import (
    expected_participant_history_heads,
)
from raes_runtime.participant_result_contracts import (
    participant_runtime_history_transition_diagnostics,
)

if TYPE_CHECKING:
    from .runtime_mapping import Observation


def integrity(observed: Observation) -> list[str]:
    issues = []
    binding = observed.binding
    # The apply-result validator forbids backend-owned changes to evaluations.
    # Here the runtime itself may append them; retain its full shape and prefix
    # checks separately, then verify each append against the expected commit.
    before_evaluations = observed.before.participant_control_evaluation_history
    after_evaluations = observed.after.participant_control_evaluation_history
    if iter_participant_control_evaluation_snapshot_violations(
        after_evaluations
    ) or any(
        after_evaluations.get(key, [])[: len(prior)] != prior
        for key, prior in before_evaluations.items()
    ):
        issues.append("history-integrity-invalid")
    apply_view = replace(
        observed.after, participant_control_evaluation_history=before_evaluations
    )
    if participant_runtime_history_transition_diagnostics(observed.before, apply_view):
        issues.append("history-integrity-invalid")
    old = observed.before.participant_crossing_history.get(binding.participant, [])
    history = observed.after.participant_crossing_history.get(binding.participant, [])
    if history[: len(old)] != old:
        issues.append("history-prefix-changed")
    try:
        records = [
            ParticipantCrossingOccurrenceModel.model_validate(item) for item in history
        ]
        context = observed.context
        validate_participant_crossing_occurrence_context(
            records,
            known_subjects=context.known_subjects,
            policies=context.policies,
            known_evidence_refs=context.known_evidence_refs,
            known_authority_basis_refs=context.known_authority_basis_refs,
        )
    except (TypeError, ValueError):
        issues.append("invalid-occurrence-context")
    for intent in observed.intents:
        if (
            intent.participant_address,
            intent.episode_id,
            intent.audience_scope_ref,
            intent.controller_ref,
        ) != (
            binding.participant,
            binding.episode,
            binding.audience,
            binding.controller,
        ):
            issues.append("identity-context-mismatch")
    changed = {
        key: record
        for key, record in observed.records_after.items()
        if observed.records_before.get(key) != record
    }
    last_commits = {
        commit.record.receipt.operation_id: commit for commit in observed.commits
    }
    retained_records = dict(observed.records_before)
    retained_audit = observed.audit_before
    for commit in observed.commits:
        required = {
            **retained_records,
            commit.expected_record.receipt.operation_id: commit.expected_record,
        }
        if any(commit.records.get(key) != record for key, record in required.items()):
            issues.append("operation-records-not-preserved")
        retained_records = {**commit.records, **required}
        if commit.audit_before[
            : len(retained_audit)
        ] != retained_audit or commit.audit != (
            *commit.audit_before,
            commit.expected_audit,
        ):
            issues.append("audit-prefix-changed")
        retained_audit = commit.audit
    if any(
        observed.records_after.get(key) != record
        for key, record in retained_records.items()
    ):
        issues.append("operation-records-not-preserved")
    if observed.audit[: len(retained_audit)] != retained_audit:
        issues.append("audit-prefix-changed")
    if any(
        observed.records_after.get(key) != commit.record
        for key, commit in last_commits.items()
    ):
        issues.append("partial-publication")
    latest_decision = next(
        (
            item["occurrence"]
            for item in reversed(history[len(old) :])
            if item["occurrence"]["stage"] == "decided"
        ),
        None,
    )
    if latest_decision is not None and latest_decision["disposition"] in {
        "deny",
        "unsupported",
    }:
        if observed.backend_calls:
            issues.append("refusal-effect")
        decision_id = latest_decision["decision_id"]
        owner_ids = {
            event.operation_id
            for event in observed.audit
            if event.details.get(
                "crossing_decision_id", event.details.get("decision_id")
            )
            == decision_id
        }
        if any(
            observed.records_after[key].status.state is OperationState.SUCCEEDED
            for key in owner_ids
            if key in observed.records_after
        ):
            issues.append("refusal-outcome-invalid")
    for record in changed.values():
        context = record.receipt.context
        if context is None or (
            context.actor_id,
            context.target_scope,
            context.run_scope,
        ) != (
            binding.principal,
            "target:" + binding.target,
            binding.run_scope,
        ):
            issues.append("operation-context-mismatch")
        if not _has_audit(record, observed.audit):
            issues.append("partial-publication")
        try:
            _record_from_payload(_record_payload(record))
            previous = observed.records_before.get(record.receipt.operation_id)
            if previous is not None:
                _require_operation_record_transition(previous, record)
        except (TypeError, ValueError):
            issues.append("operation-record-invalid")
    if len(history) > len(old) and not changed:
        issues.append("partial-publication")
    for commit in observed.commits:
        record = commit.record
        if (
            commit.snapshot != commit.expected_snapshot
            or record != commit.expected_record
            or commit.expected_audit not in commit.audit
            or commit.revision != commit.expected_revision + 1
        ):
            issues.append("partial-publication")
        if (
            record.result_history_heads
            and record.result_history_heads
            != expected_participant_history_heads(commit.snapshot, binding.participant)
        ):
            issues.append("commit-history-mismatch")
        if not _has_audit(record, commit.audit):
            issues.append("partial-publication")
    result_id = getattr(observed.result, "operation_id", None)
    if result_id is not None and getattr(observed.result, "accepted", False):
        record = observed.records_after.get(result_id)
        if record is None or record.receipt != observed.result:
            issues.append("receipt-record-mismatch")
    authorized_operations = {
        commit.record.receipt.operation_id
        for commit in observed.commits
        if commit.expected_audit.action == "authorize_participant_action"
        and commit.expected_audit.allowed
        and latest_decision is not None
        and latest_decision["disposition"] in {"permit", "transform"}
        and commit.expected_audit.details.get("crossing_decision_id")
        == latest_decision["decision_id"]
        and commit.record == commit.expected_record
        and commit.expected_audit in commit.audit
    }
    proven_authorized_result = (
        len(changed) == 1
        and not any(
            event.label == "runtime.state-cut.changed" for event in observed.events
        )
        and any(
            record.status.state in {OperationState.SUCCEEDED, OperationState.FAILED}
            and record.receipt.operation_id in authorized_operations
            and last_commits.get(record.receipt.operation_id) is not None
            and last_commits[record.receipt.operation_id].record == record
            for record in changed.values()
        )
    )
    refused = not proven_authorized_result and (
        observed.error_type is not None
        or any(
            record.status.state is OperationState.FAILED for record in changed.values()
        )
    )
    if refused:
        if observed.backend_calls:
            issues.append("backend-executed-during-refusal")
        before, after = (
            _snapshot_payload(observed.before),
            _snapshot_payload(observed.after),
        )
        for allowed in (
            "participant_crossing_history",
            "participant_control_evaluation_history",
        ):
            old_histories, new_histories = (
                before.get(allowed, {}),
                after.get(allowed, {}),
            )
            if any(
                old_histories.get(key) != new_histories.get(key)
                for key in old_histories.keys() | new_histories.keys()
                if key != binding.participant
            ):
                issues.append("unrelated-refusal-state-change")
            if observed.commits and getattr(
                observed.commits[-1].snapshot, allowed
            ) != getattr(observed.after, allowed):
                issues.append("unowned-refusal-history-change")
            before.pop(allowed, None)
            after.pop(allowed, None)
        if before != after or observed.backend_calls:
            issues.append("protected-state-changed-after-refusal")
    return sorted(set(issues))


def _has_audit(
    record: ControlPlaneOperationRecord, events: tuple[AuditEvent, ...]
) -> bool:
    for event in events:
        try:
            _require_operation_audit_binding(record, event)
        except ValueError:
            continue
        return True
    return False
