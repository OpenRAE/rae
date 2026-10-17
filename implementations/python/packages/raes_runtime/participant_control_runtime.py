"""Installed rev1 policy context and retained episode admissions.

The existing operation ledger owns admissions; accepted control state remains
derived exclusively from API-409 history. No metadata dictionary is a policy
authority and a restart never substitutes today's policy for an archived one.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from pydantic import ConfigDict, Field
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.base import ContractModel
from raes_contracts.contracts.participant_control import ParticipantControlDeclarationModel
from raes_contracts.contracts.participant_control_coordinates import ControlCount, ControlRef
from raes_contracts.contracts.participant_control_occurrence_v2 import ControlRefList
from raes_contracts.contracts.participant_control_occurrence_v2_policy import ParticipantControlOccurrencePolicyModel
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model, project_control_episode_policy
from raes_processor.models import RuntimeModel

from .participant_control_intents import ParticipantControlIntent

_ADMISSIONS = "mixed_control_episode_admissions"


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
        canonical = compile_runtime_model(self.model.realization_instance)
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

        return project_control_episode_policy(self.model, specification_ref, episode_id=episode_id)


def resolve_live_cut(plane, policy, intent):
    """Run the installed owner outside state authority and fence its evaluated cut."""

    return resolve_owner_cut(plane, policy, intent, plane._mixed_control.resolver.resolve_cut)


def resolve_owner_cut(plane, policy, request, method):
    """Use one bounded, detached callback boundary for all live policy cuts."""

    revision = plane._snapshot_state.revision
    with plane._mutation_authority.external_call():
        cut = plane._execution_adapter.call(
            "control",
            method,
            deepcopy(policy),
            deepcopy(request),
            deepcopy(plane._snapshot),
            timeout_ms=plane._supervision.admission_ms,
        )
    if not isinstance(cut, ParticipantControlLiveCut):
        raise ValueError("mixed-control owner returned an invalid live cut")
    cut = ParticipantControlLiveCut.model_validate(cut.model_dump(mode="json"))
    plane._reload_derived_state()
    if plane._snapshot_state.revision != revision:
        raise ValueError("mixed-control evaluation cut changed")
    return cut


def episode_policy_admissions(plane, previous, snapshot):
    """Attach initial authority/policy evidence to the lifecycle's atomic operation."""

    if plane._mixed_control is None:
        return None
    admissions = []
    for participant, state in snapshot.participant_episode_results.items():
        old = previous.participant_episode_results.get(participant, {})
        if old.get("episode_id") == state.get("episode_id"):
            continue
        specifications = [
            spec
            for spec in plane._behavior_specifications.values()
            if spec.mixed_control_policy is not None and spec.mixed_control_participant_address == participant
        ]
        if not specifications:
            continue
        if len(specifications) != 1 or state.get("status") != "running":
            raise ValueError("mixed-control episode must have one running admitted policy")
        policy = plane._mixed_control.policy(specifications[0].address, state["episode_id"])
        if any(item.episode_id == policy.episode_id for item in archived_policies(plane, participant)):
            raise ValueError("mixed-control episode identity cannot be reused")
        cut = resolve_live_cut(plane, policy, None)
        initial = policy.state(policy.initial_state_ref)
        if (
            initial.authority_status != "active"
            or not set(initial.authority_basis_refs) <= set(cut.active_authority_basis_refs)
            or not set(initial.scope_refs) <= set(cut.authorized_scope_refs)
            or not initial.valid_from_order <= cut.effective_order <= initial.valid_until_order
        ):
            raise ValueError("initial mixed-control authority is not valid")
        admissions.append({"policy": policy.model_dump(mode="json"), "cut": cut.model_dump(mode="json")})
    return {_ADMISSIONS: admissions} if admissions else None


def archived_policies(plane, participant):
    """Read the original scoped successful lifecycle records, never current grants."""

    policies = {}
    for record in plane._operations.values():
        if record.status.state is not OperationState.SUCCEEDED:
            continue
        for admission in (record.result_payload or {}).get(_ADMISSIONS, ()):
            policy = ParticipantControlOccurrencePolicyModel.model_validate(admission["policy"])
            cut = ParticipantControlLiveCut.model_validate(admission["cut"])
            initial = policy.state(policy.initial_state_ref)
            if (
                record.receipt.context.operation_kind.value != "participant-action"
                or initial.authority_status != "active"
                or not set(initial.authority_basis_refs) <= set(cut.active_authority_basis_refs)
                or not set(initial.scope_refs) <= set(cut.authorized_scope_refs)
                or not initial.valid_from_order <= cut.effective_order <= initial.valid_until_order
            ):
                raise ValueError("retained mixed-control admission evidence is unverifiable")
            if policy.participant_address != participant:
                continue
            digest = canonical_json_digest(policy.model_dump(mode="json"))
            key = policy.episode_id
            if key in policies and policies[key][0] != digest:
                raise ValueError("mixed-control episode has conflicting admitted policies")
            policies[key] = (digest, policy)
    return tuple(item[1] for item in policies.values())


def admitted_policy(plane, participant, episode):
    """Resolve exactly one retained admission for this participant episode."""

    matches = [policy for policy in archived_policies(plane, participant) if policy.episode_id == episode]
    if len(matches) != 1:
        raise ValueError("mixed-control episode policy is unavailable or unverifiable")
    return matches[0]
