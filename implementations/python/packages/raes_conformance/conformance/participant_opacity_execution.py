"""Runner-owned execution and measurement for participant-opacity probes.

This half of the probe family builds the real control plane for each possible
point, drives the governed crossing, replay, and delivery-opportunity
operations itself, and reads back what the runtime committed. The harness
contributes case inputs and a backend state commitment; it never contributes a
transcript, an operation outcome, or a side-effect fact measured here. Each
point runs in its own control plane so retained state from one point cannot
shape the other. The configuration and tool digests are derived here from what
was actually executed, never from harness labels.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

from pydantic import ValidationError
from pydantic_core import to_jsonable_python
from raes_contracts.canonical import canonical_json_digest, jsonable_fallback
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingOccurrenceModel,
    ParticipantOpacityRuntimeSupportModel,
)
from raes_contracts.contracts.participant_crossing_validation import validate_participant_crossing_occurrence_context
from raes_contracts.errors import AuthorizationError, EvidenceIntegrityError, InvalidInputError, RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.participant_opacity_runtime import validate_participant_opacity_runtime_enforcement
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.registry import RuntimeTarget

from raes_conformance.conformance.diagnostics import sanitized_failure_message
from raes_conformance.conformance.participant_opacity_types import (
    ParticipantOpacityBackendReadback,
    ParticipantOpacityProbeCase,
    ParticipantOpacityProbeHarness,
    ParticipantOpacityProbePoint,
    ParticipantOpacityReadbackRequest,
)
from raes_conformance.conformance.participant_policy_execution import _CallCounter, _instrumented_target

_LOGGER = get_logger(__name__)
_TOOL_REVISION = "participant-opacity-observed/rev2"


@dataclass(frozen=True)
class _OperationFacts:
    """What the runner read back for one governed operation."""

    records: tuple[Mapping[str, object], ...]
    backend_calls: tuple[str, ...]
    receipt_accepted: bool | None = None
    operation_id: str | None = None
    terminal_state: str | None = None
    diagnostic_codes: tuple[str, ...] = ()
    result: str | None = None


@dataclass(frozen=True)
class _PointMeasurement:
    """Every fact the runner measured for one possible point."""

    point_ref: str
    ingress: _OperationFacts | None
    replay: _OperationFacts | None
    egress: _OperationFacts | None
    readback_before: str | None
    readback_after: str | None
    history_valid: bool
    opacity_supports: tuple[ParticipantOpacityRuntimeSupportModel, ...]
    failures: tuple[str, ...]


def _history(plane: RuntimeControlPlane, participant_address: str) -> tuple[Mapping[str, object], ...]:
    return tuple(plane.snapshot.participant_crossing_history.get(participant_address, ()))


def _status_facts(plane: RuntimeControlPlane, receipt: object) -> dict[str, object]:
    """Read the terminal status of an operation; an accepted receipt is not an outcome."""

    operation_id = getattr(receipt, "operation_id", None)
    status = plane.get_operation(operation_id) if isinstance(operation_id, str) else None
    return {
        "receipt_accepted": bool(getattr(receipt, "accepted", False)),
        "operation_id": operation_id,
        "terminal_state": None if status is None else status.state.value,
        "diagnostic_codes": () if status is None else tuple(item.code for item in status.diagnostics),
    }


class _Governed:
    """Run one governed operation and attribute appended records and backend calls to it."""

    def __init__(
        self,
        plane: RuntimeControlPlane,
        counter: _CallCounter | None,
        participant_address: str,
        failures: list[str],
    ) -> None:
        self._plane = plane
        self._counter = counter
        self._participant_address = participant_address
        self._failures = failures

    def run(self, label: str, call: Callable[[], dict[str, object]]) -> _OperationFacts | None:
        records_before = len(_history(self._plane, self._participant_address))
        calls_before = len(self._counter.called_methods) if self._counter is not None else 0
        try:
            observed = call()
        except Exception as exc:
            if not isinstance(exc, RaesError):
                # Isolation of the backend runtime: a refusal category of the runtime needs no record.
                _LOGGER.exception("participant opacity governed operation failed", exc_info=foreign_failure_record(exc))
            self._failures.append(f"{label}: {sanitized_failure_message(exc)}")
            return None
        calls = tuple(self._counter.called_methods[calls_before:]) if self._counter is not None else ()
        return _OperationFacts(
            records=_history(self._plane, self._participant_address)[records_before:],
            backend_calls=calls,
            **observed,  # type: ignore[arg-type]
        )


def _admit(plane: RuntimeControlPlane, case: ParticipantOpacityProbeCase) -> dict[str, object]:
    receipt = plane.admit_participant_action(
        case.behavior,  # type: ignore[arg-type]
        case.admission_request,  # type: ignore[arg-type]
        identity=case.identity,  # type: ignore[arg-type]
        crossing_evidence=case.crossing_evidence,  # type: ignore[arg-type]
        idempotency_key=case.idempotency_key,
    )
    return _status_facts(plane, receipt)


def _egress(plane: RuntimeControlPlane, case: ParticipantOpacityProbeCase) -> dict[str, object]:
    """Request the participant view at a governed delivery opportunity.

    ``AuthorizationError`` is the runtime's refusal signal for this route. It is
    recorded only as a refusal here; the judging half accepts it as withholding
    only when the runtime also committed the withheld delivery attempt.
    """

    try:
        plane.get_participant_status_view(
            case.participant_address,
            identity=case.identity,  # type: ignore[arg-type]
            crossing_evidence=case.crossing_evidence,  # type: ignore[arg-type]
            idempotency_key=f"{case.idempotency_key}-egress",
        )
    except AuthorizationError:
        return {"result": "refused"}
    return {"result": "view"}


def _readback(
    harness: ParticipantOpacityProbeHarness,
    target: RuntimeTarget,
    case: ParticipantOpacityProbeCase,
    point_ref: str,
    phase: str,
    failures: list[str],
) -> ParticipantOpacityBackendReadback | None:
    """Collect one execution-bound backend readback; anything unbound stays unobserved."""

    request = ParticipantOpacityReadbackRequest(
        collection_id=secrets.token_hex(16),
        case_name=case.name,
        point_ref=point_ref,
        phase=phase,
    )
    try:
        readback = harness.backend_readback(target, case, request)
        if not isinstance(readback, ParticipantOpacityBackendReadback):
            raise InvalidInputError("backend readback must be a ParticipantOpacityBackendReadback")
        if readback.request != request:
            raise InvalidInputError("backend readback does not answer this collection request")
    except Exception as exc:
        if not isinstance(exc, RaesError):
            # Isolation of the harness: a refusal category needs no record.
            _LOGGER.exception("participant opacity backend readback failed", exc_info=foreign_failure_record(exc))
        failures.append(f"backend readback: {sanitized_failure_message(exc)}")
        return None
    return readback


def _readback_digests(
    before: ParticipantOpacityBackendReadback | None,
    after: ParticipantOpacityBackendReadback | None,
    failures: list[str],
) -> tuple[str | None, str | None]:
    """Compare only two readbacks of the same backend state source."""

    if before is None or after is None:
        return None, None
    if before.source_ref != after.source_ref:
        failures.append("backend readback: before and after collections name different state sources")
        return None, None
    return before.state_digest, after.state_digest


def _rejoin_opacity_bindings(
    records: list[ParticipantCrossingOccurrenceModel],
    supports: tuple[ParticipantOpacityRuntimeSupportModel, ...],
) -> None:
    """Rejoin each committed opacity binding to trusted support through the published validator."""

    for record in records:
        binding = getattr(record.occurrence, "opacity_enforcement", None)
        if binding is None:
            continue
        support = next((item for item in supports if item.binding == binding), None)
        if support is None:
            raise EvidenceIntegrityError("committed opacity binding has no trusted runtime support")
        validate_participant_opacity_runtime_enforcement(
            binding,
            support=support,
            participant_address=record.participant_address,
            audience_scope_ref=record.occurrence.audience_scope_ref,
        )


def _validated_history(
    plane: RuntimeControlPlane,
    point: ParticipantOpacityProbePoint,
    participant_address: str,
    failures: list[str],
) -> tuple[bool, tuple[ParticipantOpacityRuntimeSupportModel, ...]]:
    """Validate committed records against the published contracts and trusted context.

    The runner re-validates independently from the published API-423 model,
    cross-record joins, and SEM-231 support validator rather than trusting the
    runtime's own acceptance of what it committed.
    """

    try:
        context = point.resolver.validation_context(plane.snapshot, participant_address)  # type: ignore[attr-defined]
    except Exception as exc:
        if not isinstance(exc, TypeError | ValueError | RaesError):
            # Isolation of the host-installed crossing resolver. The resolver protocol refuses with
            # TypeError or ValueError (rule E4), and a refusal needs no record.
            _LOGGER.exception("participant opacity validation context failed", exc_info=foreign_failure_record(exc))
        failures.append(f"committed history: {sanitized_failure_message(exc)}")
        return False, ()
    try:
        records = [
            ParticipantCrossingOccurrenceModel.model_validate(entry) for entry in _history(plane, participant_address)
        ]
        validate_participant_crossing_occurrence_context(
            records,
            known_subjects=context.known_subjects,
            policies=context.policies,
            known_evidence_refs=context.known_evidence_refs,
            known_authority_basis_refs=context.known_authority_basis_refs,
        )
        supports = tuple(context.opacity_enforcement_supports)
        _rejoin_opacity_bindings(records, supports)
    except (ValidationError, ValueError, RaesError) as exc:
        # The published contract validators refuse with ValueError (rule E3), and a damaged
        # packaged authority or an unsupported binding raises a RaesError category.
        failures.append(f"committed history: {sanitized_failure_message(exc)}")
        return False, ()
    return True, supports


def measure_point(
    target: RuntimeTarget,
    harness: ParticipantOpacityProbeHarness,
    case: ParticipantOpacityProbeCase,
    point: ParticipantOpacityProbePoint,
) -> _PointMeasurement:
    """Drive the governed operations for one point and read back what happened."""

    instrumented, counter = _instrumented_target(target)
    plane = RuntimeControlPlane(
        instrumented,
        crossing_policy_resolver=point.resolver,  # type: ignore[arg-type]
        behavior_specifications=case.behavior_specifications,  # type: ignore[arg-type]
        enforce_final_sink_flow_control=case.enforce_final_sink_flow_control,
    )
    failures: list[str] = []
    with plane:
        plane.initialize_participant_episode(case.participant_address, episode_id=case.episode_id)
        if counter is not None:
            # Episode setup is not a governed operation of the case.
            counter.calls = 0
            counter.called_methods.clear()
        governed = _Governed(plane, counter, case.participant_address, failures)
        before = _readback(harness, target, case, point.point_ref, "before", failures)
        ingress = governed.run("ingress", lambda: _admit(plane, case))
        replay = governed.run("replay", lambda: _admit(plane, case))
        egress = governed.run("egress", lambda: _egress(plane, case))
        after = _readback(harness, target, case, point.point_ref, "after", failures)
        history_valid, supports = _validated_history(plane, point, case.participant_address, failures)
    readback_before, readback_after = _readback_digests(before, after, failures)
    return _PointMeasurement(
        point_ref=point.point_ref,
        ingress=ingress,
        replay=replay,
        egress=egress,
        readback_before=readback_before,
        readback_after=readback_after,
        history_valid=history_valid,
        opacity_supports=supports,
        failures=tuple(failures),
    )


def _raes_version() -> str:
    try:
        return distribution_version("raes")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def configuration_digest(
    target: RuntimeTarget,
    case: ParticipantOpacityProbeCase,
    manifest_digest: str,
    measurements: list[_PointMeasurement],
) -> str:
    """Digest the runtime, backend, profile, resolver, and option configuration actually executed."""

    return canonical_json_digest(
        {
            "runtime": {
                "implementation": _qualified_name_of(RuntimeControlPlane),
                "raes_version": _raes_version(),
            },
            "backend": {
                "manifest_digest": manifest_digest,
                "participant_runtime": _qualified_name_of(type(target.participant_runtime)),
            },
            "profile": [case.profile_id, case.profile_revision, case.profile_digest],
            "points": [
                {
                    "point_ref": point.point_ref,
                    "resolver": _qualified_name_of(type(point.resolver)),
                    "opacity_supports": sorted(
                        canonical_json_digest(support.model_dump(mode="json"))
                        for support in measurement.opacity_supports
                    ),
                }
                for point, measurement in zip(case.points, measurements, strict=True)
            ],
            "enforce_final_sink_flow_control": case.enforce_final_sink_flow_control,
            "behavior_specifications": {
                address: canonical_json_digest(to_jsonable_python(specification, fallback=jsonable_fallback))
                for address, specification in sorted((case.behavior_specifications or {}).items())
            },
        }
    )


def _qualified_name_of(kind: type) -> str:
    return f"{kind.__module__}.{kind.__qualname__}"


def tool_digest() -> str:
    """Digest the probe-family revision and the RAES distribution that ran it."""

    return canonical_json_digest({"tool": _TOOL_REVISION, "raes_version": _raes_version()})


__all__ = ("_OperationFacts", "_PointMeasurement", "configuration_digest", "measure_point", "tool_digest")
