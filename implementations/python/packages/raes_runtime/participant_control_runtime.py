"""Installed rev1 policy context and retained episode admissions.

The existing operation ledger owns admissions; accepted control state remains
derived exclusively from API-409 history. No metadata dictionary is a policy
authority and a restart never substitutes today's policy for an archived one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from raes_processor.models import ParticipantBehaviorSpecificationRuntime

    from .control_plane import RuntimeControlPlane
    from .control_plane_store import ControlPlaneOperationRecord


from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from pydantic import ConfigDict, Field, ValidationError
from pydantic_core import PydanticSerializationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.base import ContractModel
from raes_contracts.contracts.participant_control import ParticipantControlDeclarationModel
from raes_contracts.contracts.participant_control_coordinates import ControlCount, ControlRef
from raes_contracts.contracts.participant_control_occurrence_v2 import ControlRefList
from raes_contracts.contracts.participant_control_occurrence_v2_policy import ParticipantControlOccurrencePolicyModel
from raes_contracts.errors import (
    AuthorizationError,
    ConflictError,
    EvidenceIntegrityError,
    InvalidInputError,
)
from raes_contracts.operational_logging import foreign_failure_record
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model, project_control_episode_policy
from raes_processor.models import RuntimeModel

from .errors import RuntimeBudgetExhaustedError
from .participant_control_intents import ParticipantControlIntent

_ADMISSIONS = "mixed_control_episode_admissions"
_OWNER_REFUSED = "mixed-control owner refused the live cut"
_INVALID_OWNER_CUT = "mixed-control owner returned an invalid live cut"
_UNVERIFIABLE_ADMISSION = "retained mixed-control admission evidence is unverifiable"
# Refusals of a live control cut: governed-state, owner, evidence and budget failures.
# Adapters and asyncio still raise the built-in TimeoutError for an exhausted budget.
CONTROL_CUT_REFUSALS = (
    AuthorizationError,
    ConflictError,
    EvidenceIntegrityError,
    InvalidInputError,
    RuntimeBudgetExhaustedError,
    TimeoutError,
)


class ParticipantControlLiveCut(ContractModel):
    """Owner-established order, live grants and resolved occurrence evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    request_ref: ControlRef
    effective_order: ControlCount
    active_authority_basis_refs: list[ControlRef] = Field(max_length=256)
    authorized_scope_refs: list[ControlRef] = Field(max_length=256)
    evidence_refs: ControlRefList


class ParticipantControlCutResolver(Protocol):
    """Trusted apparatus owner, independent of the submitting principal."""

    def resolve_cut(
        self,
        policy: ParticipantControlOccurrencePolicyModel,
        intent: ParticipantControlIntent | None,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantControlLiveCut: ...


@dataclass(frozen=True, kw_only=True)
class MixedControlRuntimeBinding:
    """Explicit installation of compiled context and its admitted live-cut owner."""

    model: RuntimeModel
    resolver: ParticipantControlCutResolver
    legacy_declarations: tuple[ParticipantControlDeclarationModel, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.model, RuntimeModel) or self.model.realization_instance is None:
            raise TypeError("mixed control requires retained instantiated compiler context")
        if not callable(getattr(self.resolver, "resolve_cut", None)):
            raise TypeError("mixed control requires a typed live-cut resolver")
        try:
            canonical = compile_runtime_model(self.model.realization_instance)
        except InvalidInputError as exc:
            raise ValueError("mixed-control policies must match retained compiler context") from exc
        if canonical.behavior_specifications != self.model.behavior_specifications:
            raise ValueError("mixed-control policies must match retained compiler context")
        if not all(isinstance(item, ParticipantControlDeclarationModel) for item in self.legacy_declarations):
            raise TypeError("legacy declarations require typed historical context")
        object.__setattr__(
            self,
            "legacy_declarations",
            tuple(
                ParticipantControlDeclarationModel.model_validate(item.model_dump(mode="json"))
                for item in self.legacy_declarations
            ),
        )
        object.__setattr__(self, "model", deepcopy(self.model))

    def policy(self, specification_ref: str, episode_id: str) -> ParticipantControlOccurrencePolicyModel:
        """Resolve policy through the compiler's canonical identity projection."""

        try:
            return project_control_episode_policy(self.model, specification_ref, episode_id=episode_id)
        # The episode identity comes from the request; the projection validates it.
        except ValueError as exc:
            raise InvalidInputError("mixed-control episode policy cannot be projected for this episode") from exc


def resolve_live_cut(
    plane: RuntimeControlPlane, policy: ParticipantControlOccurrencePolicyModel, intent: ParticipantControlIntent | None
) -> ParticipantControlLiveCut:
    """Run the installed owner outside state authority and fence its evaluated cut."""

    return resolve_owner_cut(plane, policy, intent, plane._mixed_control.resolver.resolve_cut)


def resolve_owner_cut(
    plane: RuntimeControlPlane,
    policy: ParticipantControlOccurrencePolicyModel,
    request: object,
    method: Callable[..., ParticipantControlLiveCut],
) -> ParticipantControlLiveCut:
    """Use one bounded, detached callback boundary for all live policy cuts."""

    revision = plane._snapshot_state.revision
    try:
        with plane._mutation_authority.external_call():
            cut = plane._execution_adapter.call(
                "control",
                method,
                deepcopy(policy),
                deepcopy(request),
                deepcopy(plane._snapshot),
                timeout_ms=plane._supervision.admission_ms,
            )
    # The installed owner refuses a cut with PermissionError or ValueError. The owner is foreign
    # code, so the refusal chains the foreign record and no record shows the owner's frames.
    except PermissionError as exc:
        raise AuthorizationError(_OWNER_REFUSED) from foreign_failure_record(exc)
    except ValueError as exc:
        raise ConflictError(_OWNER_REFUSED) from foreign_failure_record(exc)
    if not isinstance(cut, ParticipantControlLiveCut):
        raise InvalidInputError(_INVALID_OWNER_CUT)
    try:
        cut = ParticipantControlLiveCut.model_validate(cut.model_dump(mode="json"))
    # An owner-built cut can hold a value that does not serialize or does not revalidate.
    except (ValidationError, PydanticSerializationError) as exc:
        raise InvalidInputError(_INVALID_OWNER_CUT) from exc
    plane._reload_derived_state()
    if plane._snapshot_state.revision != revision:
        raise ConflictError("mixed-control evaluation cut changed")
    return cut


def _initial_authority_valid(policy: ParticipantControlOccurrencePolicyModel, cut: ParticipantControlLiveCut) -> bool:
    initial = policy.state(policy.initial_state_ref)
    return (
        initial.authority_status == "active"
        and set(initial.authority_basis_refs) <= set(cut.active_authority_basis_refs)
        and set(initial.scope_refs) <= set(cut.authorized_scope_refs)
        and initial.valid_from_order <= cut.effective_order <= initial.valid_until_order
    )


def require_initial_authority(
    policy: ParticipantControlOccurrencePolicyModel, cut: ParticipantControlLiveCut, message: str
) -> None:
    """Validate the initial state at a newly admitted live cut."""
    if not _initial_authority_valid(policy, cut):
        raise ConflictError(message)


def participant_policy_specifications(
    plane: RuntimeControlPlane, participant: str
) -> list[ParticipantBehaviorSpecificationRuntime]:
    return [
        spec
        for spec in plane._behavior_specifications.values()
        if spec.mixed_control_policy is not None and spec.mixed_control_participant_address == participant
    ]


def episode_policy_admissions(
    plane: RuntimeControlPlane, previous: RuntimeSnapshot, snapshot: RuntimeSnapshot
) -> dict[str, object] | None:
    """Attach initial authority/policy evidence to the lifecycle's atomic operation."""
    if plane._mixed_control is None:
        return None
    admissions = []
    for participant, state in snapshot.participant_episode_results.items():
        old = previous.participant_episode_results.get(participant, {})
        if old.get("episode_id") == state.get("episode_id"):
            continue
        admission = _episode_policy_admission(plane, participant, state)
        if admission is not None:
            admissions.append(admission)
    return {_ADMISSIONS: admissions} if admissions else None


def _episode_policy_admission(
    plane: RuntimeControlPlane, participant: str, state: dict[str, object]
) -> dict[str, object] | None:
    specifications = participant_policy_specifications(plane, participant)
    if not specifications:
        return None
    if len(specifications) != 1 or state.get("status") != "running":
        raise ConflictError("mixed-control episode must have one running admitted policy")
    policy = plane._mixed_control.policy(specifications[0].address, state["episode_id"])
    if any(item.episode_id == policy.episode_id for item in archived_policies(plane, participant)):
        raise ConflictError("mixed-control episode identity cannot be reused")
    cut = resolve_live_cut(plane, policy, None)
    require_initial_authority(policy, cut, "initial mixed-control authority is not valid")
    return {"policy": policy.model_dump(mode="json"), "cut": cut.model_dump(mode="json")}


def _archived_policy(
    record: ControlPlaneOperationRecord, admission: dict[str, object]
) -> ParticipantControlOccurrencePolicyModel:
    # A restored store can retain opaque data; refuse a malformed record before a field reader runs.
    if not isinstance(admission, Mapping) or admission.keys() != {"policy", "cut"}:
        raise EvidenceIntegrityError(_UNVERIFIABLE_ADMISSION)
    try:
        policy = ParticipantControlOccurrencePolicyModel.model_validate(admission["policy"])
        cut = ParticipantControlLiveCut.model_validate(admission["cut"])
    except ValidationError as exc:
        raise EvidenceIntegrityError(_UNVERIFIABLE_ADMISSION) from exc
    if record.receipt.context.operation_kind.value != "participant-action" or not _initial_authority_valid(policy, cut):
        raise EvidenceIntegrityError(_UNVERIFIABLE_ADMISSION)
    return policy


def archived_policies(
    plane: RuntimeControlPlane, participant: str
) -> tuple[ParticipantControlOccurrencePolicyModel, ...]:
    """Read the original scoped successful lifecycle records, never current grants."""
    policies = {}
    from .participant_control_operation_index import operation_index

    for record in operation_index(plane).policy_records.values():
        if record.status.state is not OperationState.SUCCEEDED:
            continue
        admissions = (record.result_payload or {}).get(_ADMISSIONS, ())
        if not isinstance(admissions, list | tuple):
            raise EvidenceIntegrityError(_UNVERIFIABLE_ADMISSION)
        for admission in admissions:
            policy = _archived_policy(record, admission)
            if policy.participant_address != participant:
                continue
            digest = canonical_json_digest(policy.model_dump(mode="json"))
            key = policy.episode_id
            if key in policies and policies[key][0] != digest:
                raise EvidenceIntegrityError("mixed-control episode has conflicting admitted policies")
            policies[key] = (digest, policy)
    return tuple(item[1] for item in policies.values())


def admitted_policy(
    plane: RuntimeControlPlane, participant: str, episode: str
) -> ParticipantControlOccurrencePolicyModel:
    """Resolve exactly one retained admission for this participant episode."""

    matches = [policy for policy in archived_policies(plane, participant) if policy.episode_id == episode]
    if len(matches) != 1:
        raise ConflictError("mixed-control episode policy is unavailable or unverifiable")
    return matches[0]
