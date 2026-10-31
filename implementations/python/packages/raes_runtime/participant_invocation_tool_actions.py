"""Runtime-owned port for tool actions hosted by one autonomous invocation (issue #1740).

The scheduler creates one port for each outer invocation while it holds the
runtime operation. The port uses one leaf lock and in-memory state only; it
never calls the runtime manager or the control plane. A harness can therefore
use it from any thread while the outer ``admit_action`` call waits.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from raes_backend_protocols.participant_capabilities import ParticipantExecutionBinding, ParticipantRuntimeCapabilities
from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.operational_logging import get_logger
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_tool_actions import (
    INVOCATION_TOOL_ACTIONS_SEMANTICS,
    ParticipantToolActionDecision,
    ParticipantToolActionReceipt,
    ParticipantToolActionRecord,
    ParticipantToolActionRefusal,
    ParticipantToolActionRequest,
    ParticipantToolActionSettlement,
    tool_action_instance_id,
)
from raes_contracts.timestamps import WallClock, isoformat_z, utc_now
from raes_processor.models import (
    ParticipantAutonomousExecutionRuntime,
    ParticipantExecutionBindingRuntime,
    ParticipantInvocationToolBindingRuntime,
)

from .participant_interaction_conflicts import bindings_semantically_conflict
from .participant_invocation_tool_claims import TOOL_ADMISSION_UNRESOLVED

if TYPE_CHECKING:
    from .control_plane_store import ControlPlaneOperationRecord
    from .participant_execution_control import InvocationToolActionLedger

_RESOURCE_GOVERNED_PROFILE = "participant-autonomous-execution/v3"
_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "partial_success", "rejected", "withheld"})
_UNKNOWN_EFFECT_CLASSES = frozenset({"timeout", "interrupted", "backend_error", "unknown"})
_INTERRUPTED = "interrupted"
_LOGGER = get_logger(__name__)
_AUTHORITY_CHECK_FAILED = "authority-check-failed"
_AUTHORITY_REFUSALS = {
    TOOL_ADMISSION_UNRESOLVED: ParticipantToolActionRefusal.UNRESOLVED_EFFECTS,
    _AUTHORITY_CHECK_FAILED: ParticipantToolActionRefusal.LEDGER_UNAVAILABLE,
}
_ADMITTED = "admitted"
_DISPATCHED = "dispatched"
_SETTLED = "settled"


class HostedActionRegistry:
    """Pass-wide view of dispatched hosted actions and active outer invocations.

    Every port of one scheduler pass shares this registry. A grant is refused
    when its authored interaction footprint conflicts with an active hosted
    action or with another invocation's outer action. Unknown effects keep
    their reservation and fence every later grant in the pass.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._outer: dict[str, ParticipantExecutionBindingRuntime | None] = {}
        self._active: dict[str, ParticipantExecutionBindingRuntime | None] = {}
        self._unresolved = False

    @property
    def unresolved(self) -> bool:
        with self._lock:
            return self._unresolved

    def register_outer(self, invocation: str, binding: ParticipantExecutionBindingRuntime | None) -> None:
        with self._lock:
            self._outer[invocation] = binding

    def unregister_outer(self, invocation: str) -> None:
        with self._lock:
            self._outer.pop(invocation, None)

    def reserve(
        self,
        invocation: str,
        action_instance_id: str,
        binding: ParticipantExecutionBindingRuntime | None,
    ) -> bool:
        """Record one grant unless it conflicts with active work; return whether it was recorded."""

        with self._lock:
            others = [outer for key, outer in self._outer.items() if key != invocation]
            if any(bindings_semantically_conflict(binding, other) for other in (*others, *self._active.values())):
                return False
            self._active[action_instance_id] = binding
            return True

    def release(self, action_instance_id: str) -> None:
        with self._lock:
            self._active.pop(action_instance_id, None)

    def mark_unresolved(self) -> None:
        with self._lock:
            self._unresolved = True


@dataclass(frozen=True)
class InvocationToolActionConfiguration:
    """Admitted composition limits and the manifest offers that bound tool actions."""

    max_tool_actions: int
    max_concurrent_tool_actions: int
    execution_offers: tuple[ParticipantExecutionBinding, ...]
    ledger: InvocationToolActionLedger
    crossing_installed: bool = False
    registry: HostedActionRegistry = field(default_factory=HostedActionRegistry)

    @classmethod
    def from_manifest(
        cls,
        capability: ParticipantRuntimeCapabilities | None,
        *,
        ledger: InvocationToolActionLedger,
        crossing_installed: bool = False,
    ) -> InvocationToolActionConfiguration | None:
        """Return the configuration only when the backend claims the composition."""

        claim = None if capability is None else capability.invocation_tool_actions
        if claim is None or INVOCATION_TOOL_ACTIONS_SEMANTICS not in claim.semantic_versions:
            return None
        return cls(
            max_tool_actions=claim.max_tool_actions_per_invocation,
            max_concurrent_tool_actions=claim.max_concurrent_tool_actions_per_invocation,
            execution_offers=tuple(capability.execution_bindings),
            ledger=ledger,
            crossing_installed=crossing_installed,
        )


@dataclass
class _ToolEntry:
    request: ParticipantToolActionRequest
    action_instance_id: str
    ordinal: int
    admitted_at: str
    record: ControlPlaneOperationRecord
    boundary_evidence_refs: tuple[str, ...] = ()
    interaction: ParticipantExecutionBindingRuntime | None = None
    state: str = _ADMITTED
    settlement: ParticipantToolActionSettlement | None = None
    action_result: ParticipantActionResultModel | None = None
    settled_at: str | None = None


def _detached_outcome(outcome: object) -> ParticipantActionResultModel | None:
    """Revalidate a consumer outcome as a detached copy; ``None`` when it is not a valid result."""

    if not isinstance(outcome, ParticipantActionResultModel):
        return None
    try:
        return ParticipantActionResultModel.model_validate(outcome.model_dump(mode="json"))
    # The refusal is a fixed code; the validation text can repeat consumer-supplied values.
    except ValueError:
        return None


def _refused(tool_call_id: str, refusal: ParticipantToolActionRefusal) -> ParticipantToolActionDecision:
    return ParticipantToolActionDecision(tool_call_id=tool_call_id, admitted=False, refusal=refusal)


def _rejected(action_instance_id: str, refusal: ParticipantToolActionRefusal) -> ParticipantToolActionReceipt:
    return ParticipantToolActionReceipt(action_instance_id=action_instance_id, accepted=False, refusal=refusal)


def _accepted(entry: _ToolEntry) -> ParticipantToolActionReceipt:
    return ParticipantToolActionReceipt(
        action_instance_id=entry.action_instance_id,
        accepted=True,
        settlement=entry.settlement,
    )


class ParticipantInvocationToolActions:
    """Admission, dispatch and settlement of the tool actions of one outer invocation."""

    def __init__(
        self,
        *,
        outer: ParticipantActionAdmissionRequest,
        episode_id: str,
        policy: ParticipantAutonomousExecutionRuntime,
        configuration: InvocationToolActionConfiguration,
        scheduler_state_key: str,
        prior_history_length: int,
        wall_clock: WallClock = utc_now,
    ) -> None:
        if outer.execution_scope_ref is None or outer.execution_generation is None:
            raise ValueError("invocation tool actions require a generation-bound outer invocation")
        self._outer = outer
        self._episode_id = episode_id
        self._policy = policy
        self._configuration = configuration
        self._wall_clock = wall_clock
        self.scheduler_state_key = scheduler_state_key
        self.prior_history_length = prior_history_length
        self._tool_contexts = tuple(context for context in outer.temporal_contexts if context.shared_time is None)
        self._lock = threading.Lock()
        self._active = False
        self._closed = False
        self._ledger_failures = 0
        self._unresolved_effects = False
        self._entries: dict[str, _ToolEntry] = {}
        self._entries_by_action: dict[str, _ToolEntry] = {}
        self._records: tuple[ParticipantToolActionRecord, ...] = ()

    @property
    def outer(self) -> ParticipantActionAdmissionRequest:
        return self._outer

    @property
    def policy(self) -> ParticipantAutonomousExecutionRuntime:
        return self._policy

    @property
    def invocation_action_instance_id(self) -> str:
        return self._outer.action_instance_id

    @property
    def participant_address(self) -> str:
        return self._outer.participant_address

    @property
    def episode_id(self) -> str:
        return self._episode_id

    @property
    def participant_implementation_ref(self) -> str:
        return self._outer.implementation_selection.manifest_ref

    @property
    def execution_scope_ref(self) -> str:
        assert self._outer.execution_scope_ref is not None
        return self._outer.execution_scope_ref

    @property
    def execution_generation(self) -> int:
        assert self._outer.execution_generation is not None
        return self._outer.execution_generation

    @property
    def observation_point(self) -> str:
        contexts = self._tool_contexts
        return contexts[0].observation_point if contexts else f"invocation:{self._outer.action_instance_id}"

    @property
    def ledger_failures(self) -> int:
        """Return how many closure settlements the store did not retain."""

        with self._lock:
            return self._ledger_failures

    @property
    def has_unresolved_effects(self) -> bool:
        """Return whether a hosted action of this pass has unknown native effects."""

        with self._lock:
            return self._unresolved_effects or self._configuration.registry.unresolved

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def activate(self) -> None:
        """Open admission as the matching outer dispatch begins; the scheduler alone calls this."""

        with self._lock:
            if not self._closed:
                self._active = True
                self._configuration.registry.register_outer(self.invocation_action_instance_id, self._outer_binding())

    def admit(self, request: ParticipantToolActionRequest) -> ParticipantToolActionDecision:
        if not isinstance(request, ParticipantToolActionRequest):
            raise TypeError("request must be a ParticipantToolActionRequest")
        with self._lock:
            refusal = self._lifecycle_refusal()
            entry = self._entries.get(request.tool_call_id) if refusal is None else None
            if entry is not None and entry.request != request:
                refusal = ParticipantToolActionRefusal.REQUEST_CONFLICT
            elif refusal is None and entry is None:
                entry, refusal = self._admit_new(request)
            return _refused(request.tool_call_id, refusal) if refusal is not None else self._admitted(entry)

    def dispatch(self, action_instance_id: str) -> ParticipantToolActionReceipt:
        with self._lock:
            entry, refusal = self._open_entry(action_instance_id)
            if refusal is None and entry.state != _ADMITTED:
                refusal = ParticipantToolActionRefusal.STATE_CONFLICT
            if refusal is None and self._dispatched_count() >= self._configuration.max_concurrent_tool_actions:
                refusal = ParticipantToolActionRefusal.CONCURRENCY_LIMIT_EXHAUSTED
            if refusal is None:
                refusal = self._effect_authority_refusal()
            registry = self._configuration.registry
            if refusal is None and not registry.reserve(
                self.invocation_action_instance_id, action_instance_id, entry.interaction
            ):
                refusal = ParticipantToolActionRefusal.SEMANTIC_CONFLICT
            if refusal is not None:
                return _rejected(action_instance_id, refusal)
            record = self._write(lambda: self._configuration.ledger.record_dispatch(entry.record))
            if record is None:
                registry.release(action_instance_id)
                return _rejected(action_instance_id, ParticipantToolActionRefusal.LEDGER_UNAVAILABLE)
            entry.record = record
            entry.state = _DISPATCHED
            return _accepted(entry)

    def complete(self, action_instance_id: str, outcome: ParticipantActionResultModel) -> ParticipantToolActionReceipt:
        with self._lock:
            entry, refusal = self._open_entry(action_instance_id)
            if refusal is None:
                refusal = self._completion_refusal(entry, outcome)
            return _rejected(action_instance_id, refusal) if refusal is not None else _accepted(entry)

    def cancel(self, action_instance_id: str) -> ParticipantToolActionReceipt:
        with self._lock:
            entry, refusal = self._open_entry(action_instance_id)
            if refusal is None:
                refusal = self._cancel_refusal(entry)
            return _rejected(action_instance_id, refusal) if refusal is not None else _accepted(entry)

    def report_unknown(self, action_instance_id: str, failure_class: str) -> ParticipantToolActionReceipt:
        with self._lock:
            entry, refusal = self._open_entry(action_instance_id)
            if refusal is None:
                refusal = self._unknown_effect_refusal(entry, failure_class)
            return _rejected(action_instance_id, refusal) if refusal is not None else _accepted(entry)

    def close(self) -> tuple[ParticipantToolActionRecord, ...]:
        """Stop admission and settle every open tool action; idempotent."""

        with self._lock:
            if not self._closed:
                self._closed = True
                self._configuration.registry.unregister_outer(self.invocation_action_instance_id)
                for entry in self._entries.values():
                    if entry.state == _ADMITTED:
                        self._settle_synthesized(
                            entry, ParticipantToolActionSettlement.WITHHELD, _INTERRUPTED, required=False
                        )
                    elif entry.state == _DISPATCHED:
                        self._settle_synthesized(
                            entry, ParticipantToolActionSettlement.INDETERMINATE, _INTERRUPTED, required=False
                        )
                self._records = tuple(
                    ParticipantToolActionRecord(
                        request=entry.request,
                        action_instance_id=entry.action_instance_id,
                        admission_ordinal=entry.ordinal,
                        settlement=entry.settlement,
                        action_result=entry.action_result,
                        admitted_at=entry.admitted_at,
                        settled_at=entry.settled_at,
                    )
                    for entry in sorted(self._entries.values(), key=lambda item: item.ordinal)
                )
            return self._records

    @staticmethod
    def _admitted(entry: _ToolEntry) -> ParticipantToolActionDecision:
        return ParticipantToolActionDecision(
            tool_call_id=entry.request.tool_call_id,
            admitted=True,
            action_instance_id=entry.action_instance_id,
        )

    def _admit_new(
        self, request: ParticipantToolActionRequest
    ) -> tuple[_ToolEntry | None, ParticipantToolActionRefusal | None]:
        refusal, binding = self._admission_refusal(request)
        if refusal is None and len(self._entries) >= self._configuration.max_tool_actions:
            refusal = ParticipantToolActionRefusal.ADMISSION_LIMIT_EXHAUSTED
        if refusal is None:
            refusal = self._effect_authority_refusal()
        entry = None
        if refusal is None:
            entry = self._recorded_entry(request, binding)
            refusal = None if entry is not None else ParticipantToolActionRefusal.LEDGER_UNAVAILABLE
        return entry, refusal

    def _recorded_entry(
        self, request: ParticipantToolActionRequest, binding: ParticipantInvocationToolBindingRuntime
    ) -> _ToolEntry | None:
        """Claim the child record, then register the entry; ``None`` when the store refused."""

        action_instance_id = tool_action_instance_id(
            self._outer.action_instance_id,
            episode_id=self._episode_id,
            execution_generation=self.execution_generation,
            tool_call_id=request.tool_call_id,
        )
        admitted_at = isoformat_z(self._wall_clock())
        record = self._write(
            lambda: self._configuration.ledger.record_admission(action_instance_id, request, admitted_at)
        )
        if record is None:
            return None
        entry = _ToolEntry(
            request=request,
            action_instance_id=action_instance_id,
            ordinal=len(self._entries),
            admitted_at=admitted_at,
            record=record,
            boundary_evidence_refs=dict(binding.observation_boundary_evidence_refs).get(
                request.observation_boundary_address, ()
            ),
            interaction=binding.interaction,
        )
        self._entries[request.tool_call_id] = entry
        self._entries_by_action[action_instance_id] = entry
        return entry

    def _completion_refusal(
        self, entry: _ToolEntry, outcome: ParticipantActionResultModel
    ) -> ParticipantToolActionRefusal | None:
        refusal = None
        if entry.state == _SETTLED:
            replay = entry.settlement is ParticipantToolActionSettlement.COMPLETED and entry.action_result == outcome
            refusal = None if replay else ParticipantToolActionRefusal.OUTCOME_CONFLICT
        elif entry.state != _DISPATCHED:
            refusal = ParticipantToolActionRefusal.STATE_CONFLICT
        else:
            detached = self._valid_outcome(entry, outcome)
            if detached is None:
                refusal = ParticipantToolActionRefusal.OUTCOME_INVALID
            elif not self._settle(entry, ParticipantToolActionSettlement.COMPLETED, detached):
                refusal = ParticipantToolActionRefusal.LEDGER_UNAVAILABLE
        return refusal

    def _cancel_refusal(self, entry: _ToolEntry) -> ParticipantToolActionRefusal | None:
        refusal = None
        if entry.state == _ADMITTED:
            if not self._settle_synthesized(entry, ParticipantToolActionSettlement.WITHHELD, _INTERRUPTED):
                refusal = ParticipantToolActionRefusal.LEDGER_UNAVAILABLE
        elif entry.settlement is not ParticipantToolActionSettlement.WITHHELD:
            refusal = ParticipantToolActionRefusal.STATE_CONFLICT
        return refusal

    def _unknown_effect_refusal(self, entry: _ToolEntry, failure_class: str) -> ParticipantToolActionRefusal | None:
        refusal = None
        if not isinstance(failure_class, str) or failure_class not in _UNKNOWN_EFFECT_CLASSES:
            refusal = ParticipantToolActionRefusal.OUTCOME_INVALID
        elif entry.state == _DISPATCHED:
            if not self._settle_synthesized(entry, ParticipantToolActionSettlement.INDETERMINATE, failure_class):
                refusal = ParticipantToolActionRefusal.LEDGER_UNAVAILABLE
        elif entry.state == _ADMITTED:
            refusal = ParticipantToolActionRefusal.STATE_CONFLICT
        elif (
            entry.settlement is not ParticipantToolActionSettlement.INDETERMINATE
            or entry.action_result.failure_class != failure_class
        ):
            refusal = ParticipantToolActionRefusal.OUTCOME_CONFLICT
        return refusal

    def _lifecycle_refusal(self) -> ParticipantToolActionRefusal | None:
        if self._closed:
            return ParticipantToolActionRefusal.INVOCATION_CLOSED
        return None if self._active else ParticipantToolActionRefusal.INVOCATION_INACTIVE

    def _open_entry(self, action_instance_id: str) -> tuple[_ToolEntry | None, ParticipantToolActionRefusal | None]:
        lifecycle_refusal = self._lifecycle_refusal()
        if lifecycle_refusal is not None:
            return None, lifecycle_refusal
        entry = self._entries_by_action.get(action_instance_id)
        return entry, None if entry is not None else ParticipantToolActionRefusal.ACTION_UNKNOWN

    def _dispatched_count(self) -> int:
        return sum(1 for entry in self._entries.values() if entry.state == _DISPATCHED)

    def _admission_refusal(
        self, request: ParticipantToolActionRequest
    ) -> tuple[ParticipantToolActionRefusal | None, ParticipantInvocationToolBindingRuntime | None]:
        refusal = self._composition_refusal(request)
        if refusal is not None:
            return refusal, None
        members = [
            binding
            for binding in self._policy.invocation_tool_bindings
            if binding.tool_affordance_address == request.tool_affordance_address
            and binding.action_contract_address == request.action_contract_address
            and request.participant_address in binding.participant_addresses
        ]
        if len(members) != 1:
            refusal = (
                ParticipantToolActionRefusal.BINDING_UNKNOWN
                if not members
                else ParticipantToolActionRefusal.BINDING_AMBIGUOUS
            )
            return refusal, None
        return self._binding_refusal(request, members[0]), members[0]

    def _composition_refusal(self, request: ParticipantToolActionRequest) -> ParticipantToolActionRefusal | None:
        checks = (
            (not self._matches_invocation(request), ParticipantToolActionRefusal.INVOCATION_MISMATCH),
            (
                self._policy.profile == _RESOURCE_GOVERNED_PROFILE,
                ParticipantToolActionRefusal.RESOURCE_GOVERNANCE_UNSUPPORTED,
            ),
            (self._configuration.crossing_installed, ParticipantToolActionRefusal.CROSSING_MEDIATION_UNSUPPORTED),
        )
        return next((refusal for refused, refusal in checks if refused), None)

    def _matches_invocation(self, request: ParticipantToolActionRequest) -> bool:
        return (
            request.participant_address,
            request.episode_id,
            request.participant_implementation_ref,
            request.invocation_action_instance_id,
            request.execution_scope_ref,
            request.execution_generation,
        ) == (
            self.participant_address,
            self._episode_id,
            self.participant_implementation_ref,
            self.invocation_action_instance_id,
            self.execution_scope_ref,
            self.execution_generation,
        )

    def _binding_refusal(
        self,
        request: ParticipantToolActionRequest,
        binding: ParticipantInvocationToolBindingRuntime,
    ) -> ParticipantToolActionRefusal | None:
        targets = set(request.target_addresses)
        offers = [
            offer
            for offer in self._configuration.execution_offers
            if offer.action_contract_address == request.action_contract_address
            and offer.participant_implementation_ref == self.participant_implementation_ref
            and targets.issubset(offer.target_addresses)
        ]
        checks = (
            (
                request.observation_boundary_address not in binding.observation_boundary_addresses,
                ParticipantToolActionRefusal.OBSERVATION_BOUNDARY_UNBOUND,
            ),
            (not targets.issubset(binding.target_addresses), ParticipantToolActionRefusal.TARGET_UNBOUND),
            (binding.shared_time_bound, ParticipantToolActionRefusal.TEMPORAL_BINDING_UNSUPPORTED),
            (not offers, ParticipantToolActionRefusal.EXECUTION_OFFER_MISSING),
            (len(offers) > 1, ParticipantToolActionRefusal.EXECUTION_OFFER_AMBIGUOUS),
        )
        return next((refusal for refused, refusal in checks if refused), None)

    def _valid_outcome(self, entry: _ToolEntry, outcome: object) -> ParticipantActionResultModel | None:
        detached = _detached_outcome(outcome)
        valid = (
            detached is not None and self._outcome_matches(entry, detached) and self._binds_exposure(entry, detached)
        )
        return detached if valid else None

    def _outcome_matches(self, entry: _ToolEntry, outcome: ParticipantActionResultModel) -> bool:
        expected = (
            entry.request.participant_address,
            self._episode_id,
            entry.action_instance_id,
            entry.request.action_contract_address,
        )
        actual = (
            outcome.participant_address,
            outcome.episode_id,
            outcome.action_instance_id,
            outcome.action_contract_address,
        )
        return (
            actual == expected
            and outcome.status in _TERMINAL_STATUSES
            and not outcome.temporal_evidence
            and not outcome.resource_measurements
        )

    def _binds_exposure(self, entry: _ToolEntry, outcome: ParticipantActionResultModel) -> bool:
        """Run the canonical binding and exposure validation for one tool outcome."""

        request = entry.request
        try:
            ParticipantActionAdmissionRequest(
                participant_address=request.participant_address,
                action_contract_address=request.action_contract_address,
                observation_boundary_address=request.observation_boundary_address,
                action_instance_id=entry.action_instance_id,
                implementation_manifest=self._outer.implementation_manifest,
                implementation_selection=self._outer.implementation_selection,
                observation_boundary_evidence_refs=entry.boundary_evidence_refs,
                temporal_contexts=self._tool_contexts,
                action_result=outcome,
                requires_terminal_outcome=True,
                target_addresses=request.target_addresses,
                execution_scope_ref=request.execution_scope_ref,
                execution_generation=request.execution_generation,
            )
        # The refusal is a fixed code; the validation text can repeat consumer-supplied values.
        except TypeError, ValueError:
            return False
        return True

    def _settle_synthesized(
        self,
        entry: _ToolEntry,
        settlement: ParticipantToolActionSettlement,
        failure_class: str,
        *,
        required: bool = True,
    ) -> bool:
        status = "withheld" if settlement is ParticipantToolActionSettlement.WITHHELD else "unknown"
        return self._settle(
            entry,
            settlement,
            ParticipantActionResultModel(
                status=status,
                participant_address=entry.request.participant_address,
                episode_id=self._episode_id,
                action_instance_id=entry.action_instance_id,
                action_contract_address=entry.request.action_contract_address,
                observation_point=self.observation_point,
                failure_class=failure_class,
            ),
            required=required,
        )

    def _settle(
        self,
        entry: _ToolEntry,
        settlement: ParticipantToolActionSettlement,
        action_result: ParticipantActionResultModel,
        *,
        required: bool = True,
    ) -> bool:
        """Commit the terminal child record, then settle in memory.

        A required write refuses on failure. Closure is not optional, so it settles
        in memory, counts the failure, and leaves the durable record to recovery.
        """

        registry = self._configuration.registry
        if settlement is ParticipantToolActionSettlement.INDETERMINATE:
            # Unknown effects fence every later grant in the pass before any write; a failed write
            # leaves the fence in place, and accepted work may still settle.
            self._unresolved_effects = True
            registry.mark_unresolved()
        record = self._write(
            lambda: self._configuration.ledger.record_settlement(entry.record, settlement, action_result)
        )
        if record is None:
            if required:
                return False
            self._ledger_failures += 1
        else:
            entry.record = record
        entry.state = _SETTLED
        entry.settlement = settlement
        entry.action_result = action_result
        entry.settled_at = isoformat_z(self._wall_clock())
        if settlement is not ParticipantToolActionSettlement.INDETERMINATE:
            # An indeterminate action keeps its interaction reservation; its effects may still run.
            registry.release(entry.action_instance_id)
        return True

    def _outer_binding(self) -> ParticipantExecutionBindingRuntime | None:
        matches = [
            binding
            for binding in self._policy.execution_bindings
            if binding.action_contract_address == self._outer.action_contract_address
        ]
        return matches[0] if len(matches) == 1 else None

    def _effect_authority_refusal(self) -> ParticipantToolActionRefusal | None:
        """Refuse a new claim or grant unless the enclosing authority still admits effects."""

        if self._unresolved_effects or self._configuration.registry.unresolved:
            return ParticipantToolActionRefusal.UNRESOLVED_EFFECTS
        try:
            reason = self._configuration.ledger.effect_admission_refusal()
        # Any store or driver failure refuses with a fixed code; the check never fails open.
        except Exception:  # NOSONAR - a store read failure of any driver must refuse the grant
            _LOGGER.exception("invocation tool-action authority check failed")
            reason = _AUTHORITY_CHECK_FAILED
        return (
            None
            if reason is None
            else _AUTHORITY_REFUSALS.get(reason, ParticipantToolActionRefusal.EFFECT_ADMISSION_CLOSED)
        )

    @staticmethod
    def _write(write: Callable[[], ControlPlaneOperationRecord]) -> ControlPlaneOperationRecord | None:
        try:
            return write()
        # A failed store write refuses the transition with a fixed code; the record stays at its last state.
        # SQLite and PostgreSQL drivers raise their own exception types, so the boundary is not narrowed.
        except Exception:  # NOSONAR - a store write failure of any driver must refuse, not escape closure
            _LOGGER.exception("invocation tool-action ledger write failed")
            return None


__all__ = ("InvocationToolActionConfiguration", "ParticipantInvocationToolActions")
