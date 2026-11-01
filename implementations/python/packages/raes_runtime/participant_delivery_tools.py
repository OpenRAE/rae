"""Runtime-owned tool port of one admitted delivery invocation."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from threading import Lock
from types import SimpleNamespace
from typing import TYPE_CHECKING

from pydantic import TypeAdapter
from raes_contracts.contracts.participant_action_admission import ParticipantActionAdmissionRequest
from raes_contracts.contracts.participant_runtime import ParticipantActionResultModel
from raes_contracts.contracts.participant_temporal import ParticipantTemporalEvidenceModel
from raes_contracts.contracts.participant_temporal_assessment import coordinate_key
from raes_contracts.contracts.participant_temporal_history import assess_temporal_guarantee
from raes_contracts.errors import RaesError
from raes_contracts.operational_logging import foreign_failure_record, get_logger
from raes_contracts.participant_tool_actions import (
    ParticipantToolActionDecision,
    ParticipantToolActionReceipt,
    ParticipantToolActionRefusal,
    ParticipantToolActionRequest,
    ParticipantToolActionSettlement,
    tool_action_instance_id,
)
from raes_contracts.timestamps import isoformat_z
from raes_processor.compiler import compile_participant_invocation_tools

from .participant_delivery_tool_admission import action_admission, execution_offers, prepare_tool_crossing, tool_binding
from .participant_delivery_tool_recovery import reconcile_delivery_tool
from .participant_delivery_tool_settlement import settle_delivery_tool
from .participant_invocation_tool_actions import HostedActionRegistry, InvocationToolEntry, detached_tool_outcome

if TYPE_CHECKING:
    from raes_contracts.contracts.participant_crossing_evidence import ParticipantCrossingEvidence
    from raes_contracts.contracts.participant_delivery_invocation import ParticipantDeliveryInvocationContextModel

    from .control_plane import RuntimeControlPlane
    from .control_plane_mutation import InvocationChildScope
    from .control_plane_security import ControlPlaneIdentity
    from .control_plane_store import ControlPlaneOperationRecord

_LOGGER = get_logger(__name__)
_R = ParticipantToolActionRefusal
_S = ParticipantToolActionSettlement


class ParticipantDeliveryInvocationTools:
    def __init__(
        self,
        plane: RuntimeControlPlane,
        invocation: ParticipantDeliveryInvocationContextModel,
        scope: InvocationChildScope,
        record: ControlPlaneOperationRecord,
        identity: ControlPlaneIdentity,
    ):
        self._plane = plane
        self._invocation = invocation.model_copy(deep=True)
        self._scope = scope
        self._record = record
        self._identity = identity
        self._current_request = None
        self._closed = False
        self.has_unresolved_effects = False
        self.ledger_failures = 0
        self._lock, self._busy = Lock(), False
        self._entries, self._by_action = {}, {}
        self._decisions, self._offers = {}, {}
        self._registry = HostedActionRegistry()
        self._capability = plane.delivery_target.manifest.participant_runtime
        self._limits = self._capability.invocation_tool_actions
        delivery = plane.delivery_inject_delivery.model.participant_inject_deliveries[
            invocation.delivery.application.delivery_address
        ]
        self._bindings, self._temporal = compile_participant_invocation_tools(
            plane.delivery_inject_delivery.model,
            delivery.behavior_specification_address,
            participant_implementation_ref=self.participant_implementation_ref,
            max_actions=self._limits.max_tool_actions_per_invocation,
            max_in_flight=self._limits.max_concurrent_tool_actions_per_invocation,
        )
        self._ledger = plane.delivery_create_tool_ledger(record)

    def delivery_tools_context(self):
        """Give runtime handlers internal state only while they own the writer."""
        self._plane.delivery_require_state_writer()
        return SimpleNamespace(
            plane=self._plane,
            bindings=self._bindings,
            temporal=self._temporal,
            capability=self._capability,
            current_request=self._current_request,
            identity=self._identity,
            scope=self._scope,
            ledger=self._ledger,
            registry=self._registry,
        )

    @classmethod
    def recovery_port(cls, plane, invocation, parent):
        """Construct a settlement-only port; recovery never issues grants."""
        plane.delivery_require_state_writer()
        value = object.__new__(cls)
        cls.initialize_recovery_port(value, plane, invocation, parent)
        return value

    def initialize_recovery_port(self, plane, invocation, parent):
        plane.delivery_require_state_writer()
        self._plane, self._invocation = plane, invocation
        self._bindings, self._temporal = (), ()
        self._capability = self._current_request = self._identity = self._scope = None
        self._registry, self.has_unresolved_effects = HostedActionRegistry(), False
        self._ledger = plane.delivery_create_tool_ledger(parent)

    def settle_interrupted_tool(self, entry, settlement, failure_class):
        self._plane.delivery_require_state_writer()
        return self._settle_unknown(entry, settlement, failure_class)

    @property
    def invocation(self) -> ParticipantDeliveryInvocationContextModel:
        return self._invocation.model_copy(deep=True)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def invocation_action_instance_id(self) -> str:
        return self.invocation.invocation_id

    @property
    def participant_address(self) -> str:
        return self.invocation.participant_address

    @property
    def episode_id(self) -> str:
        return self.invocation.episode_id

    @property
    def participant_implementation_ref(self) -> str:
        return self.invocation.implementation_selection.manifest_ref

    @property
    def execution_scope_ref(self) -> str:
        return self.invocation.execution_scope_ref

    @property
    def execution_generation(self) -> int:
        return self.invocation.execution_generation

    @property
    def observation_point(self) -> str:
        return "invocation:" + self.invocation.invocation_id

    def finish(self) -> None:
        with self._lock:
            self._closed = True
        self._scope.close()
        for entry in tuple(self._entries.values()):
            if entry.state == "settled":
                continue
            settlement = _S.WITHHELD if entry.state == "admitted" else _S.INDETERMINATE
            try:
                self._settle_unknown(entry, settlement, "interrupted")
            except Exception as exc:
                self.ledger_failures += 1
                self.has_unresolved_effects = True
                _LOGGER.exception(
                    "delivery tool closure could not retain settlement", exc_info=foreign_failure_record(exc)
                )

        # A claim may have committed before its acknowledgement was lost.
        # Close any retained child that never reached the in-memory port map.
        try:
            self._plane.delivery_reload_derived_state()
            for retained in tuple(self._plane.delivery_operations.values()):
                if (
                    retained.status.context.parent_operation_id == self.invocation_action_instance_id
                    and retained.receipt.operation_id not in self._by_action
                    and retained.status.state.value in {"accepted", "running"}
                ):
                    reconcile_delivery_tool(self._plane, retained, port_type=type(self))
        except Exception as exc:
            self.ledger_failures += 1
            self.has_unresolved_effects = True
            _LOGGER.exception(
                "delivery tool closure could not reconcile retained claims", exc_info=foreign_failure_record(exc)
            )

    def _call[T](self, handler: Callable[[], T], refused: Callable[[ParticipantToolActionRefusal], T]) -> T:
        with self._lock:
            if self._closed:
                return refused(_R.INVOCATION_CLOSED)
            if self._busy:
                return refused(_R.STATE_CONFLICT)
            self._busy = True
        try:
            return self._scope.run(handler)
        except RaesError:
            return refused(_R.AUTHORITY_DENIED)
        except TypeError, ValueError:
            return refused(_R.OUTCOME_INVALID)
        except Exception as exc:
            self.has_unresolved_effects = True
            self.ledger_failures += 1
            _LOGGER.exception("delivery tool operation did not complete", exc_info=foreign_failure_record(exc))
            return refused(_R.LEDGER_UNAVAILABLE)
        finally:
            with self._lock:
                self._busy = False

    def admit(
        self, request: ParticipantToolActionRequest, *, crossing_evidence: ParticipantCrossingEvidence | None = None
    ) -> ParticipantToolActionDecision:
        if not isinstance(request, ParticipantToolActionRequest):
            raise TypeError("request must be a ParticipantToolActionRequest")
        request = replace(request)

        def refusal(reason):
            return ParticipantToolActionDecision(request.tool_call_id, False, refusal=reason)

        return self._call(lambda: self._admit(request, crossing_evidence), refusal)

    def _admit(self, request, evidence):
        prior = self._entries.get(request.tool_call_id)
        if prior is not None:
            if prior.request != request or prior.crossing_evidence != evidence:
                return ParticipantToolActionDecision(request.tool_call_id, False, refusal=_R.REQUEST_CONFLICT)
            return deepcopy(self._decisions[request.tool_call_id])
        binding, reason = tool_binding(self, request)
        if reason is None and len(self._entries) >= self._limits.max_tool_actions_per_invocation:
            reason = _R.ADMISSION_LIMIT_EXHAUSTED
        if reason is None and self.has_unresolved_effects:
            reason = _R.UNRESOLVED_EFFECTS
        if reason is not None:
            return ParticipantToolActionDecision(request.tool_call_id, False, refusal=reason)
        action_id = tool_action_instance_id(
            self.invocation_action_instance_id,
            episode_id=self.episode_id,
            execution_generation=self.execution_generation,
            tool_call_id=request.tool_call_id,
        )
        admission = action_admission(self, request, binding, action_id)
        self._current_request = request
        crossing, governed = prepare_tool_crossing(self, admission, evidence, stage="admit")
        if crossing is None:
            return ParticipantToolActionDecision(request.tool_call_id, False, refusal=_R.AUTHORITY_DENIED)
        self._plane.delivery_commit_prepared_crossing(crossing)
        self._plane.delivery_reload_derived_state()
        self._scope.require_live()
        now = isoformat_z(self._plane.wall_clock())
        actual = replace(
            request,
            action_contract_address=governed.action_contract_address,
            observation_boundary_address=governed.observation_boundary_address,
            target_addresses=governed.target_addresses,
        )
        binding, refusal = tool_binding(self, actual)
        if refusal is not None:
            return ParticipantToolActionDecision(request.tool_call_id, False, refusal=refusal)
        (offer,) = execution_offers(self, governed)
        if (
            sum(self._offers[item.action_instance_id].binding_id == offer.binding_id for item in self._entries.values())
            >= offer.max_action_attempts
        ):
            return ParticipantToolActionDecision(request.tool_call_id, False, refusal=_R.ADMISSION_LIMIT_EXHAUSTED)
        record = self._ledger.admission_record(
            action_id,
            request,
            now,
            delivery_tool={
                "admission_ordinal": len(self._entries),
                "admission": TypeAdapter(ParticipantActionAdmissionRequest).dump_python(governed, mode="json"),
            },
        )
        try:
            claimed = self._plane.delivery_claim_record(record)
        except Exception:
            self._plane.delivery_reload_derived_state()
            if self._plane.delivery_operations.get(action_id) != record:
                self.ledger_failures += 1
                self.has_unresolved_effects = True
                raise
            claimed = self._plane.delivery_operations[action_id]
        if claimed != record:
            self.has_unresolved_effects = True
            raise ValueError("delivery tool claim conflicts with its original binding")
        entry = InvocationToolEntry(
            request,
            action_id,
            len(self._entries),
            now,
            record,
            interaction=binding.interaction,
            admission=governed,
            crossing_evidence=deepcopy(evidence),
        )
        self._entries[request.tool_call_id], self._by_action[action_id] = entry, entry
        self._offers[action_id] = offer
        decision = self._decision(entry)
        self._decisions[request.tool_call_id] = deepcopy(decision)
        return decision

    def _decision(self, entry):
        return ParticipantToolActionDecision(
            entry.request.tool_call_id, True, entry.action_instance_id, binding=deepcopy(entry.admission)
        )

    def _receipt(self, entry):
        return ParticipantToolActionReceipt(
            entry.action_instance_id, True, settlement=entry.settlement, binding=deepcopy(entry.admission)
        )

    def dispatch(
        self, action_instance_id: str, *, temporal_evidence: tuple[ParticipantTemporalEvidenceModel, ...] = ()
    ) -> ParticipantToolActionReceipt:
        return self._call(
            lambda: self._dispatch(action_instance_id, temporal_evidence),
            lambda reason: ParticipantToolActionReceipt(action_instance_id, False, refusal=reason),
        )

    def _dispatch(self, action_id, temporal_evidence):
        entry = self._by_action.get(action_id)
        if entry is None:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.ACTION_UNKNOWN)
        if entry.state != "admitted":
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.STATE_CONFLICT)
        if self.has_unresolved_effects:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.UNRESOLVED_EFFECTS)
        if (
            sum(item.state == "dispatched" for item in self._entries.values())
            >= self._limits.max_concurrent_tool_actions_per_invocation
        ):
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.CONCURRENCY_LIMIT_EXHAUSTED)
        offer = self._offers[action_id]
        if (
            sum(
                item.state == "dispatched" and self._offers[item.action_instance_id].binding_id == offer.binding_id
                for item in self._entries.values()
            )
            >= offer.max_in_flight
        ):
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.CONCURRENCY_LIMIT_EXHAUSTED)
        if not isinstance(temporal_evidence, tuple) or any(
            not isinstance(item, ParticipantTemporalEvidenceModel) for item in temporal_evidence
        ):
            raise TypeError("tool temporal evidence must be a tuple of typed proofs")
        proofs = tuple(
            ParticipantTemporalEvidenceModel.model_validate(item.model_dump(mode="json")) for item in temporal_evidence
        )
        admitted = replace(entry.admission, temporal_evidence=proofs)
        self._current_request = entry.request
        crossing, governed = prepare_tool_crossing(self, admitted, entry.crossing_evidence, stage="dispatch")
        if crossing is None:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.AUTHORITY_DENIED)
        if governed != admitted:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.STATE_CONFLICT)
        for temporal in governed.temporal_contexts:
            context = temporal.shared_time
            if context is None:
                continue
            clock = self._plane.delivery_snapshot.time_model_state.clocks[context.binding.clock_address]
            invalid = clock.coordinate.segment != context.submitted_at.segment
            if context.binding.temporal_kind == "deadline":
                invalid |= coordinate_key(clock.coordinate) > coordinate_key(context.bound_end)
            else:
                invalid |= (
                    assess_temporal_guarantee(
                        context,
                        proofs,
                        governed.observation_boundary_address,
                        clock,
                        native_execution="not_dispatched",
                    ).status
                    != "met"
                )
            if invalid:
                return ParticipantToolActionReceipt(action_id, False, refusal=_R.TEMPORAL_GUARANTEE_UNSATISFIED)
        if not self._registry.reserve(self.invocation_action_instance_id, action_id, entry.interaction):
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.SEMANTIC_CONFLICT)
        entry.state, entry.admission = "dispatched", governed
        try:
            record = self._ledger.dispatched_record(entry.record)
            record = replace(
                record,
                result_payload={
                    **record.result_payload,
                    "delivery_tool": {
                        **record.result_payload["delivery_tool"],
                        "admission": TypeAdapter(ParticipantActionAdmissionRequest).dump_python(governed, mode="json"),
                    },
                },
            )
            self._commit_crossing(entry, crossing, record, "dispatch_participant_tool_action")
        except BaseException:
            self.has_unresolved_effects = True
            self._registry.mark_unresolved()
            raise
        return self._receipt(entry)

    def _commit_crossing(self, entry, crossing, record, action):
        record = replace(
            record,
            decision_history_heads=crossing.expected_history_heads,
            result_history_heads=crossing.record.result_history_heads,
        )
        try:
            self._plane.delivery_commit_participant_transition(
                expected_history_heads=crossing.expected_history_heads,
                snapshot=crossing.next_snapshot,
                record=record,
                audit_event=self._plane.delivery_combined_crossing_audit(
                    replace(
                        crossing.audit_event,
                        operation_id=record.receipt.operation_id,
                        timestamp=record.status.updated_at,
                    ),
                    crossing,
                    action=action,
                    allowed=True,
                ),
            )
        except BaseException:
            # Retain the exact read-back proof binding, but never reissue a grant.
            if self._plane.delivery_operations.get(entry.action_instance_id) == record:
                entry.record = record
            raise
        entry.record = record

    def complete(self, action_instance_id: str, outcome: ParticipantActionResultModel) -> ParticipantToolActionReceipt:
        return self._call(
            lambda: self._complete(action_instance_id, outcome),
            lambda reason: ParticipantToolActionReceipt(action_instance_id, False, refusal=reason),
        )

    def _complete(self, action_id, outcome):
        entry = self._by_action.get(action_id)
        if entry is None:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.ACTION_UNKNOWN)
        detached = detached_tool_outcome(outcome)
        if entry.state == "settled":
            return (
                self._receipt(entry)
                if entry.settlement is _S.COMPLETED and entry.action_result == detached
                else ParticipantToolActionReceipt(action_id, False, refusal=_R.OUTCOME_CONFLICT)
            )
        if entry.state != "dispatched":
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.STATE_CONFLICT)
        if detached is None or detached.status not in {
            "succeeded",
            "failed",
            "partial_success",
            "rejected",
            "withheld",
        }:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.OUTCOME_INVALID)
        if detached.episode_id != self.episode_id or detached.resource_measurements:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.OUTCOME_INVALID)
        expected_point = (
            entry.admission.temporal_contexts[0].observation_point
            if entry.admission.temporal_contexts
            else self.observation_point
        )
        if detached.observation_point != expected_point:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.OUTCOME_INVALID)
        replace(entry.admission, action_result=detached)
        settle_delivery_tool(self, entry, _S.COMPLETED, detached)
        return self._receipt(entry)

    def cancel(self, action_instance_id: str) -> ParticipantToolActionReceipt:
        return self._call(
            lambda: self._cancel(action_instance_id),
            lambda reason: ParticipantToolActionReceipt(action_instance_id, False, refusal=reason),
        )

    def _cancel(self, action_id):
        entry = self._by_action.get(action_id)
        if entry is None:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.ACTION_UNKNOWN)
        if entry.state == "admitted":
            self._settle_unknown(entry, _S.WITHHELD, "interrupted")
        return (
            self._receipt(entry)
            if entry.settlement is _S.WITHHELD
            else ParticipantToolActionReceipt(action_id, False, refusal=_R.STATE_CONFLICT)
        )

    def report_unknown(self, action_instance_id: str, failure_class: str) -> ParticipantToolActionReceipt:
        return self._call(
            lambda: self._unknown(action_instance_id, failure_class),
            lambda reason: ParticipantToolActionReceipt(action_instance_id, False, refusal=reason),
        )

    def _unknown(self, action_id, failure_class):
        entry = self._by_action.get(action_id)
        if entry is None:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.ACTION_UNKNOWN)
        if failure_class not in {"timeout", "interrupted", "backend_error", "unknown"}:
            return ParticipantToolActionReceipt(action_id, False, refusal=_R.OUTCOME_INVALID)
        if entry.state == "dispatched":
            self._settle_unknown(entry, _S.INDETERMINATE, failure_class)
        if entry.settlement is _S.INDETERMINATE and entry.action_result.failure_class == failure_class:
            return self._receipt(entry)
        return ParticipantToolActionReceipt(action_id, False, refusal=_R.STATE_CONFLICT)

    def _settle_unknown(self, entry, settlement, failure_class):
        outcome = ParticipantActionResultModel(
            status="withheld" if settlement is _S.WITHHELD else "unknown",
            participant_address=self.participant_address,
            episode_id=self.episode_id,
            action_instance_id=entry.action_instance_id,
            action_contract_address=entry.admission.action_contract_address,
            observation_point=entry.admission.temporal_contexts[0].observation_point
            if entry.admission.temporal_contexts
            else self.observation_point,
            failure_class=failure_class,
        )
        settle_delivery_tool(self, entry, settlement, outcome)
