"""RUN-308 participant concurrency runtime validators."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from .immutable_history import EventHistory
from .participant_concurrency_time import TIME_CONTEXTS_KEY as _TIME_CONTEXTS_KEY
from .participant_concurrency_time import time_contexts_violations as _time_contexts_violations

Violation = tuple[str, str]

_JOINT_ACTION_RECORDS_KEY = "runtime.snapshot.joint-action-records"


def iter_participant_concurrency_snapshot_violations(
    joint_action_records: object,
    time_management_contexts: object,
    *,
    participant_behavior_history: object = None,
    shared_state_records: object = None,
    shared_state_history: object = None,
) -> Iterator[Violation]:
    """Yield RUN-308 snapshot violations for joint action/time records."""

    known_event_refs = _known_behavior_event_refs(participant_behavior_history)
    known_state_refs = _known_shared_state_refs(shared_state_records, shared_state_history)
    known_time_context_refs = _known_mapping_keys(time_management_contexts)
    known_time_contexts = time_management_contexts if isinstance(time_management_contexts, Mapping) else {}
    violations: list[Violation] = []
    violations.extend(
        _joint_action_records_violations(
            joint_action_records,
            known_event_refs=known_event_refs,
            known_state_refs=known_state_refs,
            known_time_context_refs=known_time_context_refs,
            known_time_contexts=known_time_contexts,
        )
    )
    violations.extend(_time_contexts_violations(time_management_contexts, known_event_refs=known_event_refs))
    return iter(violations)


def iter_participant_concurrency_transition_violations(
    previous_joint_action_records: object,
    next_joint_action_records: object,
    previous_time_management_contexts: object,
    next_time_management_contexts: object,
) -> Iterator[Violation]:
    """Yield append-only violations for RUN-308 concurrency records."""

    yield from _append_only_mapping_violations(
        "joint_action_records",
        _JOINT_ACTION_RECORDS_KEY,
        previous_joint_action_records,
        next_joint_action_records,
    )
    yield from _append_only_mapping_violations(
        "time_management_contexts",
        _TIME_CONTEXTS_KEY,
        previous_time_management_contexts,
        next_time_management_contexts,
    )


def _known_behavior_event_refs(participant_behavior_history: object) -> set[str]:
    if not isinstance(participant_behavior_history, Mapping):
        return set()
    return {ref for history in participant_behavior_history.values() for ref in _behavior_history_refs(history)}


def _behavior_history_refs(history: object) -> Iterator[str]:
    if not isinstance(history, (list, EventHistory)):
        return
    for event in history:
        if isinstance(event, Mapping):
            yield from _behavior_event_refs(event)


def _behavior_event_refs(event: Mapping[object, object]) -> Iterator[str]:
    for field_name in ("event_id", "action_instance_id"):
        ref = event.get(field_name)
        if isinstance(ref, str) and ref:
            yield ref


def _known_shared_state_refs(shared_state_records: object, shared_state_history: object) -> set[str]:
    refs: set[str] = set()
    for candidate in (shared_state_records, shared_state_history):
        if isinstance(candidate, Mapping):
            refs.update(str(key) for key in candidate if isinstance(key, str) and key)
    return refs


def _known_mapping_keys(candidate: object) -> set[str]:
    if not isinstance(candidate, Mapping):
        return set()
    return {str(key) for key in candidate if isinstance(key, str) and key}


def _joint_action_records_violations(
    records: object,
    *,
    known_event_refs: set[str],
    known_state_refs: set[str],
    known_time_context_refs: set[str],
    known_time_contexts: Mapping[object, object],
) -> list[Violation]:
    violations: list[Violation] = []
    if not isinstance(records, Mapping):
        return [(_JOINT_ACTION_RECORDS_KEY, "joint_action_records must be a mapping")]
    for outer_key, record in records.items():
        locator = f"{_JOINT_ACTION_RECORDS_KEY}.{outer_key}"
        if not isinstance(outer_key, str) or not outer_key:
            violations.append((_JOINT_ACTION_RECORDS_KEY, "joint_action_records keys must be non-empty strings"))
        elif not isinstance(record, Mapping):
            violations.append((locator, "joint action record must be a mapping"))
        else:
            violations.extend(
                _joint_action_record_violations(
                    locator,
                    outer_key,
                    record,
                    known_event_refs=known_event_refs,
                    known_state_refs=known_state_refs,
                    known_time_context_refs=known_time_context_refs,
                    known_time_contexts=known_time_contexts,
                )
            )
    return violations


def _joint_action_record_violations(
    locator: str,
    outer_key: str,
    record: Mapping[object, object],
    *,
    known_event_refs: set[str],
    known_state_refs: set[str],
    known_time_context_refs: set[str],
    known_time_contexts: Mapping[object, object],
) -> list[Violation]:
    violations: list[Violation] = []
    violations.extend(_joint_action_identity_violations(locator, outer_key, record.get("joint_action_set_id")))

    member_refs = record.get("member_event_refs")
    access_sets = record.get("access_sets")
    member_ref_set, member_violations = _joint_action_member_ref_violations(
        locator,
        member_refs,
        known_event_refs=known_event_refs,
    )
    violations.extend(member_violations)

    access_event_refs, access_violations = _joint_action_access_violations(
        locator,
        access_sets,
        known_state_refs=known_state_refs,
    )
    violations.extend(access_violations)
    if member_ref_set and not _exact_string_set(access_event_refs, member_ref_set):
        violations.append((locator, "joint action access_sets must cover member_event_refs exactly once"))

    realized_order = record.get("realized_order", [])
    violations.extend(_joint_action_realized_order_violations(locator, realized_order, member_ref_set))

    conflict_policy = record.get("conflict_policy")
    conflict_class = record.get("conflict_class")
    unsupported = record.get("unsupported_disclosure") is True
    exact_claim = record.get("exact_concurrency_claim") is True
    actual_conflict = _actual_conflict(access_sets)
    violations.extend(
        _joint_action_conflict_violations(
            locator,
            _JointActionConflictCheck(
                conflict_class=conflict_class,
                conflict_policy=conflict_policy,
                actual_conflict=actual_conflict,
                realized_order=realized_order,
                unsupported=unsupported,
                exact_claim=exact_claim,
                retry_limit=record.get("retry_limit"),
                rollback_event_refs=record.get("rollback_event_refs", []),
                atomicity_scope=record.get("atomicity_scope"),
                isolation_guarantee=record.get("isolation_guarantee"),
            ),
        )
    )

    violations.extend(
        _joint_action_time_context_violations(
            locator,
            record.get("time_management_context_ref"),
            exact_claim=exact_claim,
            known_time_context_refs=known_time_context_refs,
            known_time_contexts=known_time_contexts,
        )
    )
    return violations


def _joint_action_identity_violations(locator: str, outer_key: str, joint_id: object) -> list[Violation]:
    if not isinstance(joint_id, str) or not joint_id:
        return [(locator, "joint action record requires joint_action_set_id")]
    if joint_id != outer_key:
        return [(locator, f"joint action record key {outer_key!r} does not match joint_action_set_id")]
    return []


def _joint_action_member_ref_violations(
    locator: str,
    member_refs: object,
    *,
    known_event_refs: set[str],
) -> tuple[set[str], list[Violation]]:
    if not isinstance(member_refs, list) or not member_refs:
        return set(), [(locator, "joint action member_event_refs must be a non-empty list")]

    valid_refs = [ref for ref in member_refs if isinstance(ref, str) and ref]
    member_ref_set = set(valid_refs)
    if len(valid_refs) != len(member_refs):
        return member_ref_set, [(locator, "joint action member_event_refs entries must be non-empty strings")]
    if len(member_ref_set) != len(valid_refs):
        return member_ref_set, [(locator, "joint action member_event_refs must be unique")]
    return member_ref_set, [
        (locator, f"joint action member_event_ref {ref!r} does not resolve to behavior history")
        for ref in sorted(member_ref_set - known_event_refs)
    ]


def _joint_action_realized_order_violations(
    locator: str, realized_order: object, member_ref_set: set[str]
) -> list[Violation]:
    if not isinstance(realized_order, list):
        return [(locator, "joint action realized_order must be a list")]
    if member_ref_set and realized_order and not _exact_string_set(realized_order, member_ref_set):
        return [(locator, "joint action realized_order must be an exact permutation of member_event_refs")]
    return []


def _joint_action_time_context_violations(
    locator: str,
    time_context_ref: object,
    *,
    exact_claim: bool,
    known_time_context_refs: set[str],
    known_time_contexts: Mapping[object, object],
) -> list[Violation]:
    if not isinstance(time_context_ref, str) or not time_context_ref:
        if exact_claim:
            return [(locator, "exact concurrency claims require time_management_context_ref")]
        return []

    if time_context_ref not in known_time_context_refs:
        return [(locator, f"time_management_context_ref {time_context_ref!r} does not resolve")]
    time_context = known_time_contexts.get(time_context_ref)
    if exact_claim and isinstance(time_context, Mapping) and time_context.get("claim_strength") != "exact":
        return [(locator, "exact concurrency claims require exact time-management context")]
    return []


def _joint_action_access_violations(
    locator: str,
    access_sets: object,
    *,
    known_state_refs: set[str],
) -> tuple[list[str], list[Violation]]:
    event_refs: list[str] = []
    violations: list[Violation] = []
    if not isinstance(access_sets, list) or not access_sets:
        return event_refs, [(locator, "joint action access_sets must be a non-empty list")]
    for index, access in enumerate(access_sets):
        access_locator = f"{locator}.access_sets[{index}]"
        access_event_refs, access_violations = _single_access_set_violations(
            access_locator,
            access,
            known_state_refs=known_state_refs,
        )
        event_refs.extend(access_event_refs)
        violations.extend(access_violations)
    return event_refs, violations


def _single_access_set_violations(
    access_locator: str,
    access: object,
    *,
    known_state_refs: set[str],
) -> tuple[list[str], list[Violation]]:
    if not isinstance(access, Mapping):
        return [], [(access_locator, "joint action access set must be a mapping")]

    event_ref = access.get("member_event_ref")
    event_refs: list[str] = []
    violations: list[Violation] = []
    if not isinstance(event_ref, str) or not event_ref:
        violations.append((access_locator, "joint action access set requires member_event_ref"))
    else:
        event_refs.append(event_ref)

    for field_name in ("shared_state_read_refs", "shared_state_write_refs"):
        violations.extend(
            _access_state_ref_violations(
                access_locator,
                field_name,
                access.get(field_name, []),
                known_state_refs=known_state_refs,
            )
        )
    return event_refs, violations


def _access_state_ref_violations(
    access_locator: str,
    field_name: str,
    values: object,
    *,
    known_state_refs: set[str],
) -> list[Violation]:
    if not isinstance(values, list):
        return [(access_locator, f"{field_name} must be a list")]
    return [
        violation
        for state_ref in values
        for violation in _access_state_ref_violation(access_locator, field_name, state_ref, known_state_refs)
    ]


def _access_state_ref_violation(
    access_locator: str,
    field_name: str,
    state_ref: object,
    known_state_refs: set[str],
) -> list[Violation]:
    if not isinstance(state_ref, str) or not state_ref:
        return [(access_locator, f"{field_name} entries must be non-empty strings")]
    if state_ref not in known_state_refs:
        return [(access_locator, f"{field_name} entry {state_ref!r} does not resolve")]
    return []


@dataclass(frozen=True)
class _JointActionConflictCheck:
    conflict_class: object
    conflict_policy: object
    actual_conflict: str
    realized_order: object
    unsupported: bool
    exact_claim: bool
    retry_limit: object
    rollback_event_refs: object
    atomicity_scope: object
    isolation_guarantee: object


def _joint_action_conflict_violations(locator: str, check: _JointActionConflictCheck) -> list[Violation]:
    violations: list[Violation] = []
    if check.unsupported and check.exact_claim:
        violations.append((locator, "unsupported concurrency disclosure cannot carry an exact concurrency claim"))
    if check.conflict_policy == "unsupported":
        violations.extend(_unsupported_conflict_policy_violations(locator, check))
        return violations

    violations.extend(_conflict_class_violations(locator, check))
    violations.extend(_conflict_policy_violations(locator, check))
    violations.extend(_conflict_atomicity_violations(locator, check))
    return violations


def _unsupported_conflict_policy_violations(locator: str, check: _JointActionConflictCheck) -> list[Violation]:
    if not check.unsupported or check.exact_claim:
        return [(locator, "unsupported conflict_policy requires unsupported_disclosure and no exact claim")]
    return []


def _conflict_class_violations(locator: str, check: _JointActionConflictCheck) -> list[Violation]:
    violations: list[Violation] = []
    if not check.unsupported and check.conflict_class != check.actual_conflict:
        violations.append((locator, "joint action conflict_class must match declared access-set conflicts"))
    if check.conflict_class == "none" and check.actual_conflict != "none":
        violations.append((locator, "joint action conflict_class cannot be none when access sets conflict"))
    return violations


def _conflict_policy_violations(locator: str, check: _JointActionConflictCheck) -> list[Violation]:
    violations: list[Violation] = []
    has_realized_order = _has_realized_order(check.realized_order)
    if check.isolation_guarantee == "serializable" and not has_realized_order:
        violations.append((locator, "serializable joint action isolation requires realized_order"))
    if check.conflict_policy == "serialize" and not has_realized_order:
        violations.append((locator, "serialize conflict_policy requires realized_order"))
    if check.conflict_policy == "retry" and (not isinstance(check.retry_limit, int) or not check.rollback_event_refs):
        violations.append((locator, "retry conflict_policy requires retry_limit and rollback_event_refs"))
    if check.conflict_policy == "none" and check.actual_conflict != "none":
        violations.append((locator, "none conflict_policy is only valid when access sets do not conflict"))
    return violations


def _conflict_atomicity_violations(locator: str, check: _JointActionConflictCheck) -> list[Violation]:
    has_recovery_evidence = _has_realized_order(check.realized_order) or bool(check.rollback_event_refs)
    if check.atomicity_scope == "multi_object" and check.actual_conflict != "none" and not has_recovery_evidence:
        return [(locator, "multi_object conflicting joint actions require realized_order or rollback_event_refs")]
    return []


def _has_realized_order(realized_order: object) -> bool:
    return isinstance(realized_order, list) and bool(realized_order)


def _actual_conflict(access_sets: object) -> str:
    if not isinstance(access_sets, list):
        return "none"
    return _classify_access_conflict(access for access in access_sets if isinstance(access, Mapping))


def _classify_access_conflict(access_sets: Iterator[Mapping[object, object]]) -> str:
    mapped_access_sets = list(access_sets)
    read_write_conflict = False
    for left_index, left in enumerate(mapped_access_sets):
        for right in mapped_access_sets[left_index + 1 :]:
            conflict = _access_pair_conflict(left, right)
            if conflict == "write_write":
                return "write_write"
            if conflict == "read_write":
                read_write_conflict = True
    return "read_write" if read_write_conflict else "none"


def _access_pair_conflict(left: Mapping[object, object], right: Mapping[object, object]) -> str:
    left_reads = _string_set(left.get("shared_state_read_refs", []))
    left_writes = _write_refs(left)
    right_reads = _string_set(right.get("shared_state_read_refs", []))
    right_writes = _write_refs(right)
    if left_writes & right_writes:
        return "write_write"
    if (left_writes & right_reads) or (left_reads & right_writes):
        return "read_write"
    return "none"


def _write_refs(access: Mapping[object, object]) -> set[str]:
    refs = _string_set(access.get("shared_state_write_refs", []))
    refs.update(f"resource:{ref}" for ref in _string_set(access.get("exclusive_resource_refs", [])))
    return refs


def _string_set(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {value for value in values if isinstance(value, str) and value}


def _exact_string_set(values: object, expected: set[str]) -> bool:
    return isinstance(values, list) and len(values) == len(expected) and set(values) == expected


def _append_only_mapping_violations(
    field_name: str,
    address_prefix: str,
    previous_records: object,
    next_records: object,
) -> Iterator[Violation]:
    if not isinstance(previous_records, Mapping) or not isinstance(next_records, Mapping):
        return
    for record_id, previous_record in previous_records.items():
        if not isinstance(record_id, str) or not record_id:
            continue
        locator = f"{address_prefix}.{record_id}"
        if record_id not in next_records:
            yield (locator, f"{field_name} must be append-only; record {record_id!r} was removed")
        elif next_records[record_id] != previous_record:
            yield (locator, f"{field_name} must be append-only; record {record_id!r} changed")


__all__ = ("iter_participant_concurrency_snapshot_violations", "iter_participant_concurrency_transition_violations")
