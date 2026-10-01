"""Finite abstract model for issue #1348, not a runtime implementation.

Evidence booleans stand for independently established boundary attestations.
They do not implement authentication, external fencing, snapshot validation,
clock continuity, or a transactional store. One instance models one operation
in one conflicting-effect scope; publication is an indivisible abstract cut.
"""

from dataclasses import dataclass, replace

TERMINAL = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "INDETERMINATE"})
EFFECTS = frozenset({"absent", "partial", "complete", "unknown"})


@dataclass(frozen=True)
class Evidence:
    effects: str
    quiescent: bool
    validated: bool = True
    satisfies: bool = False


@dataclass(frozen=True)
class Operation:
    state: str = "ACCEPTED"
    actor: str = "author"
    supervisor: str | None = None
    cancel: str = "none"
    admission_open: bool = True
    invocations: int = 0
    effects: str = "absent"
    quiescent: bool = True
    quarantined: bool = False
    revision: int = 0
    audit: tuple[str, ...] = ()


def admit(
    *,
    required: frozenset[str] = frozenset(),
    supported: frozenset[str] = frozenset(),
    willing: bool = True,
) -> Operation:
    if not required <= supported or not willing:
        raise ValueError("admission refused")
    return Operation()


def start(operation: Operation) -> Operation:
    if not operation.admission_open or operation.quarantined:
        raise ValueError("admission closed")
    if operation.state != "ACCEPTED":
        raise ValueError("not an accepted operation")
    return replace(operation, state="RUNNING", invocations=1, effects="unknown", quiescent=False)


def stop_admission(operation: Operation) -> Operation:
    return replace(operation, admission_open=False)


def supervise(
    operation: Operation,
    *,
    actor: str,
    authorized: bool = True,
    reply: str = "requested",
) -> Operation:
    if not authorized:
        raise ValueError("authorization required")
    if reply not in {"requested", "accepted", "refused", "unsupported"}:
        raise ValueError("invalid supervision disposition")
    if operation.state in TERMINAL:
        return operation
    if operation.state == "ACCEPTED":
        return replace(operation, state="CANCELLED", supervisor=actor, cancel="completed", audit=("CANCELLED",))
    return replace(operation, supervisor=actor, cancel=reply)


def settle(
    operation: Operation,
    evidence: Evidence,
    *,
    cancelled: bool = False,
    expected_revision: int | None = None,
) -> Operation:
    if operation.state in TERMINAL:
        raise ValueError("terminal operation is immutable")
    if operation.state != "RUNNING" or evidence.effects not in EFFECTS:
        raise ValueError("invalid settlement")
    if expected_revision is not None and expected_revision != operation.revision:
        raise ValueError("revision conflict")
    if not evidence.validated or not evidence.quiescent or evidence.effects == "unknown":
        state = "INDETERMINATE"
    elif cancelled and operation.cancel == "accepted":
        state = "CANCELLED"
    elif evidence.satisfies and evidence.effects in {"absent", "complete"}:
        state = "SUCCEEDED"
    else:
        state = "FAILED"
    known = state != "INDETERMINATE"
    return replace(
        operation,
        state=state,
        effects=evidence.effects if known else "unknown",
        quiescent=evidence.quiescent and evidence.validated,
        quarantined=not known,
        revision=operation.revision + int(known and evidence.effects in {"partial", "complete"}),
        audit=(*operation.audit, state),
    )


@dataclass(frozen=True)
class Publication:
    authoritative: Operation
    visible: Operation
    poisoned: bool


def publish(before: Operation, after: Operation, *, persisted: bool, acknowledged: bool) -> Publication:
    if acknowledged and not persisted:
        raise ValueError("acknowledgement cannot assert an absent commit")
    return Publication(after if persisted else before, after if acknowledged else before, not acknowledged)


def deadline_expired(*, started: int, now: int, budget: int) -> bool:
    if any(type(value) is not int for value in (started, now, budget)) or budget <= 0 or now < started:
        raise ValueError("invalid monotonic duration")
    return now - started >= budget


def continuation_allowed(
    action: str,
    *,
    permitted: bool,
    quiescent: bool,
    effects: str,
    durable: bool = False,
    continuity: bool = False,
    allocated: bool = False,
    clean: bool = False,
    posture: str = "disallow",
    safety_proved: bool = False,
    attempts_left: int = 1,
) -> bool:
    # Durability deliberately supplies neither semantic permission nor safety evidence.
    _ = durable
    if action not in {"retry", "resume", "new-trial"} or effects not in EFFECTS:
        raise ValueError("unknown continuation")
    if not permitted or not quiescent or effects == "unknown":
        return False
    if action == "resume":
        return continuity
    if action == "new-trial":
        return allocated and clean
    return attempts_left > 0 and (
        effects == "absent" or (posture in {"idempotent", "reset", "compensate"} and safety_proved)
    )
