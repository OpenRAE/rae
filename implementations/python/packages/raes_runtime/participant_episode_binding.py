"""Explicit ACT-623 implementation admission under retained compiler context."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from raes_contracts.canonical import canonical_contract_digest
from raes_contracts.contracts.participant_action_admission import implementation_selection_violations
from raes_contracts.contracts.participant_manifests import (
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.errors import ConflictError, InvalidInputError
from raes_contracts.participant_episode import (
    ParticipantEpisodeResetRequest,
    ParticipantEpisodeRestartRequest,
    ParticipantEpisodeTerminalReason,
    ParticipantEpisodeTerminateRequest,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_processor.compiler import compile_runtime_model
from raes_processor.models import ParticipantEpisodePolicyRuntime, RuntimeModel
from raes_processor.models.participant_episode_validation import participant_episode_history_policy_violations

if TYPE_CHECKING:
    from .registry import RuntimeTarget

EPISODE_CONTRACTS = frozenset({"participant-episode-state-envelope-v1", "participant-episode-history-event-stream-v1"})


@dataclass(frozen=True, kw_only=True)
class ParticipantEpisodeImplementationBinding:
    """One existing implementation manifest and its exact participant selection."""

    manifest: ParticipantImplementationManifestModel
    selection: ParticipantImplementationSelectionModel

    def __post_init__(self) -> None:
        manifest = ParticipantImplementationManifestModel.model_validate(self.manifest.model_dump(mode="json"))
        selection = ParticipantImplementationSelectionModel.model_validate(self.selection.model_dump(mode="json"))
        violations = implementation_selection_violations(selection.participant_address, manifest, selection)
        if violations or selection.manifest_digest != canonical_contract_digest(manifest):
            raise ValueError("episode implementation selection must match its manifest and digest")
        if not set(selection.participant_contract_versions) >= EPISODE_CONTRACTS:
            raise ValueError("episode implementation selection must support episode state and history")
        object.__setattr__(self, "manifest", manifest)
        object.__setattr__(self, "selection", selection)


@dataclass(frozen=True, kw_only=True, init=False)
class ParticipantEpisodeRuntimeBinding:
    """Install one implementation per governed participant without a deployment graph."""

    _model: RuntimeModel
    _implementations: tuple[ParticipantEpisodeImplementationBinding, ...]

    def __init__(
        self, *, model: RuntimeModel, implementations: tuple[ParticipantEpisodeImplementationBinding, ...]
    ) -> None:
        if not isinstance(model, RuntimeModel) or model.realization_instance is None:
            raise TypeError("episode binding requires retained compiler context")
        try:
            canonical = compile_runtime_model(model.realization_instance)
        except InvalidInputError as exc:
            raise ValueError("episode binding must match its original compiler context") from exc
        if canonical != model:
            raise ValueError("episode binding must match its original compiler context")
        participants = _admitted_implementations(implementations)
        _require_policy_owners(canonical, participants)
        object.__setattr__(self, "_model", deepcopy(canonical))
        object.__setattr__(self, "_implementations", tuple(participants.values()))

    @property
    def model(self) -> RuntimeModel:
        """Return a detached view of the admitted compiler context."""
        return deepcopy(self._model)

    @property
    def implementations(self) -> tuple[ParticipantEpisodeImplementationBinding, ...]:
        """Return detached implementation declarations."""
        return deepcopy(self._implementations)

    def require_target(self, target: RuntimeTarget) -> None:
        """Require the target's existing episode contract and runtime declarations."""

        capability = target.manifest.participant_runtime
        if target.participant_runtime is None or capability is None:
            raise ValueError("episode binding requires an installed participant runtime")
        if not set(target.manifest.supported_contract_versions) >= EPISODE_CONTRACTS:
            raise ValueError("episode target must declare episode state and history contracts")
        for binding in self._implementations:
            compatibility = binding.manifest.compatibility
            if compatibility.participant_runtimes and capability.name not in compatibility.participant_runtimes:
                raise ValueError("episode implementation does not support the selected participant runtime")
            if compatibility.backends and target.manifest.name not in compatibility.backends:
                raise ValueError("episode implementation does not support the selected backend")

    def policy(self, participant_address: str) -> ParticipantEpisodePolicyRuntime | None:
        return next(
            (
                deepcopy(policy)
                for policy in self._model.participant_episode_policies.values()
                if participant_address in policy.participant_addresses
            ),
            None,
        )

    def require_request(self, request: object) -> None:
        """Check authored action and reason bounds before an existing lifecycle effect."""

        policy = self.policy(getattr(request, "participant_address", ""))
        if policy is None:
            return
        action = None
        if isinstance(request, ParticipantEpisodeResetRequest):
            action = "reset"
        elif isinstance(request, ParticipantEpisodeRestartRequest):
            action = "restart"
        if action is not None and policy.reset_control_actions and action not in policy.reset_control_actions:
            raise ConflictError("participant episode control action is not admitted by its authored policy")
        if isinstance(request, ParticipantEpisodeTerminateRequest):
            reasons = {condition.terminal_reason for condition in policy.conditions}
            if request.terminal_reason is not ParticipantEpisodeTerminalReason.INTERRUPTED and (
                request.terminal_reason.value not in reasons
            ):
                raise ConflictError("participant episode terminal reason is not admitted by its authored policy")

    def require_snapshot(self, snapshot: RuntimeSnapshot) -> None:
        """Refuse recorded history that contradicts the installed policy."""

        if any(
            next(
                participant_episode_history_policy_violations(
                    policy, snapshot.participant_episode_history.get(address)
                ),
                None,
            )
            is not None
            for policy in self._model.participant_episode_policies.values()
            for address in policy.participant_addresses
        ):
            raise ConflictError("recorded participant episodes contradict the installed authored policy")


def _admitted_implementations(
    implementations: tuple[ParticipantEpisodeImplementationBinding, ...],
) -> dict[str, ParticipantEpisodeImplementationBinding]:
    participants: dict[str, ParticipantEpisodeImplementationBinding] = {}
    for binding in deepcopy(implementations):
        if not isinstance(binding, ParticipantEpisodeImplementationBinding):
            raise TypeError("episode implementations require typed manifest selections")
        binding = ParticipantEpisodeImplementationBinding(manifest=binding.manifest, selection=binding.selection)
        address = binding.selection.participant_address
        if address in participants:
            raise ValueError("episode participant must resolve exactly one implementation")
        participants[address] = binding
    return participants


def _require_policy_owners(
    model: RuntimeModel,
    participants: dict[str, ParticipantEpisodeImplementationBinding],
) -> None:
    governed: set[str] = set()
    for policy in model.participant_episode_policies.values():
        specification = model.behavior_specifications[policy.behavior_specification_address]
        if specification.episode_policy_address != policy.address:
            raise ValueError("episode aggregate and policy attachment must agree")
        for address in policy.participant_addresses:
            if address in governed or address not in participants:
                raise ValueError("episode participant must resolve one policy and one implementation")
            governed.add(address)
            mode = participants[address].selection.selected_decision_surface_mode
            if specification.behavior_mode and specification.behavior_mode != mode:
                raise ValueError("episode implementation decision mode must match its behavior specification")
    if set(participants) != governed:
        raise ValueError("episode implementation selections must name exactly the governed participants")
