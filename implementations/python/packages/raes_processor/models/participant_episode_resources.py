"""Compiled participant episode policy records (DSL-120).

The compiled policy is participant metadata at
``participant.episode-policy.<behavior-specification>``. It carries authored
intent and the canonical addresses that intent resolves to. Realized episode
identity, state, history and terminal reasons remain the ADR-013 participant
episode contracts keyed by the same ``participant.behavior.<agent>`` addresses.
"""

from dataclasses import dataclass

from raes_contracts.participant_episode import ParticipantEpisodeTerminalReason

from .resources import ResolvedResource

# Authored conditions may map only to these ADR-013 terminal reasons. An
# ``interrupted`` episode is externally induced and is never an authored condition.
AUTHORED_EPISODE_TERMINAL_REASONS = frozenset(
    {
        ParticipantEpisodeTerminalReason.COMPLETED.value,
        ParticipantEpisodeTerminalReason.TIMED_OUT.value,
        ParticipantEpisodeTerminalReason.TRUNCATED.value,
    }
)


@dataclass(frozen=True)
class ParticipantEpisodeConditionRuntime:
    """One compiled terminal or truncation condition and its explicit terminal reason."""

    condition_id: str
    terminal_reason: str
    evidence_requirement_addresses: tuple[str, ...]
    assertion_addresses: tuple[str, ...] = ()
    temporal_constraint_address: str = ""

    def __post_init__(self) -> None:
        if self.terminal_reason not in AUTHORED_EPISODE_TERMINAL_REASONS:
            raise ValueError(f"compiled episode condition cannot map to terminal reason {self.terminal_reason!r}")
        if not self.evidence_requirement_addresses:
            raise ValueError("compiled episode conditions must name the evidence that backs the transition")
        timed_out = self.terminal_reason == ParticipantEpisodeTerminalReason.TIMED_OUT.value
        if timed_out != bool(self.temporal_constraint_address) or timed_out == bool(self.assertion_addresses):
            raise ValueError("timed_out conditions use one temporal constraint; other conditions use assertions")


@dataclass(frozen=True)
class ParticipantEpisodePolicyRuntime(ResolvedResource):
    """Compiled authored episode intent for one behavior specification."""

    behavior_specification_address: str = ""
    participant_addresses: tuple[str, ...] = ()
    profile: str = ""
    initialization_assertion_addresses: tuple[str, ...] = ()
    turn_order_basis: str = ""
    turn_action_contract_addresses: tuple[str, ...] = ()
    conditions: tuple[ParticipantEpisodeConditionRuntime, ...] = ()
    reset_control_actions: tuple[str, ...] = ()
    participant_memory_scope: str = ""
    memory_reset_authority_ref: str = ""
    reset_evidence_requirement_addresses: tuple[str, ...] = ()
