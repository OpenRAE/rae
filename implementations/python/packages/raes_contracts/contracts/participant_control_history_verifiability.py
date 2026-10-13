"""Typed completeness check for mixed API-409 control archives (MC-08).

Unverifiable is distinct from invalid: a missing historical policy, missing
v1 declarations or an unknown lineage reader yields an explicit unverifiable
episode, and the archive bytes are preserved. The check never evaluates an
occurrence; the contextual owner remains the single evaluator.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .participant_control import ParticipantControlDeclarationModel
from .participant_control_occurrence_v2 import PARTICIPANT_CONTROL_OCCURRENCE_SCHEMA_NAME
from .participant_control_occurrence_v2_policy import ParticipantControlOccurrencePolicyModel

PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE = (
    "participant control history is unverifiable: an episode lacks its pinned policy, declarations or lineage reader"
)
_V1 = (PARTICIPANT_CONTROL_OCCURRENCE_SCHEMA_NAME, "1.0.0")
_V2 = (PARTICIPANT_CONTROL_OCCURRENCE_SCHEMA_NAME, "2.0.0")
MissingContext = Literal["missing-policy", "unsupported-lineage"]


@dataclass(frozen=True)
class ParticipantControlEpisodeVerifiability:
    """Completeness of one participant episode's reconstruction context."""

    participant_address: str
    episode_id: str
    status: Literal["verifiable", "unverifiable"]
    missing: tuple[MissingContext, ...] = ()


@dataclass(frozen=True)
class ParticipantControlHistoryVerifiability:
    """Per-episode completeness, in archive order of first appearance."""

    entries: tuple[ParticipantControlEpisodeVerifiability, ...]

    @property
    def verifiable(self) -> bool:
        """Return whether every episode has its complete reconstruction context."""

        return all(entry.status == "verifiable" for entry in self.entries)


def participant_control_occurrence_lineage(record: object) -> Literal["v1", "v2", "unknown"]:
    """Dispatch on (``schema_name``, ``schema_version``); never infer a lineage from other fields."""

    pair = (getattr(record, "schema_name", None), getattr(record, "schema_version", None))
    return "v1" if pair == _V1 else "v2" if pair == _V2 else "unknown"


def policy_pin_key(pin: object) -> tuple[object, ...]:
    """Return the hashable (specification, policy, revision, form) identity of one policy pin."""

    return tuple(
        getattr(pin, name, None) for name in ("behavior_specification_ref", "policy_ref", "policy_revision", "form")
    )


def _context_supplied(
    lineage: str,
    record: object,
    key: tuple[str, str],
    declared: set[tuple[str, str]],
    pinned: set[tuple[object, ...]],
) -> bool:
    if lineage == "v1":
        return key in declared
    return (*key, getattr(record, "semantics", None), policy_pin_key(getattr(record, "policy", None))) in pinned


def participant_control_history_verifiability(
    records: Sequence[object],
    *,
    declarations: Sequence[ParticipantControlDeclarationModel] = (),
    policies: Sequence[ParticipantControlOccurrencePolicyModel] = (),
) -> ParticipantControlHistoryVerifiability:
    """Report each episode as verifiable or unverifiable without evaluating any occurrence."""

    declared = {(item.participant_address, item.episode_id) for item in declarations}
    pinned = {
        (item.participant_address, item.episode_id, item.semantics, policy_pin_key(item.pin)) for item in policies
    }
    missing: dict[tuple[str, str], set[MissingContext]] = {}
    for record in records:
        key = (str(getattr(record, "participant_address", "")), str(getattr(record, "episode_id", "")))
        gaps = missing.setdefault(key, set())
        lineage = participant_control_occurrence_lineage(record)
        if lineage == "unknown":
            gaps.add("unsupported-lineage")
        elif not _context_supplied(lineage, record, key, declared, pinned):
            gaps.add("missing-policy")
    return ParticipantControlHistoryVerifiability(
        tuple(
            ParticipantControlEpisodeVerifiability(
                participant_address=participant,
                episode_id=episode,
                status="unverifiable" if gaps else "verifiable",
                missing=tuple(sorted(gaps)),
            )
            for (participant, episode), gaps in missing.items()
        )
    )


__all__ = [
    "PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE",
    "ParticipantControlEpisodeVerifiability",
    "ParticipantControlHistoryVerifiability",
    "participant_control_history_verifiability",
    "participant_control_occurrence_lineage",
    "policy_pin_key",
]
