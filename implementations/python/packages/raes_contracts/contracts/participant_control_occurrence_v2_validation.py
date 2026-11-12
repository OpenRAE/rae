"""API-409 v2 contextual joins: the per-episode fold behind the single owner entry point.

``validate_participant_control_occurrence_context`` dispatches every batch that is
not purely v1 here. Each participant history must be a complete contiguous
prefix; each episode goes to its own lineage reader and pinned policy in archive
order. ``fold_participant_control_episode_v2`` is the one v2 state machine:
runtime code computes live state by calling it rather than writing another.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from raes_contracts.participant_mixed_control_vocabulary import (
    MixedControlTransitionKind,
    ParticipantControlTargetKind,
)

from .participant_control import ParticipantControlDeclarationModel, ParticipantControlTargetContextModel
from .participant_control_history_verifiability import (
    PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE,
    participant_control_history_verifiability,
    participant_control_occurrence_lineage,
    policy_pin_key,
)
from .participant_control_occurrence_v2 import (
    ParticipantAcceptedOccurrenceV2Model,
    ParticipantApprovalOccurrenceV2Model,
    ParticipantCancellationOccurrenceV2Model,
    ParticipantControlOccurrenceV2Model,
    ParticipantDenialOccurrenceV2Model,
    ParticipantHandoffOccurrenceV2Model,
    ParticipantOverrideOccurrenceV2Model,
    ParticipantProposalOccurrenceV2Model,
    ParticipantRejectedOccurrenceV2Model,
)
from .participant_control_occurrence_v2_policy import (
    ParticipantControlOccurrencePolicyModel,
    ParticipantControlOccurrenceTarget,
    participant_control_validity_bounds,
)
from .participant_control_occurrence_v2_state import (
    ParticipantControlEpisodeFoldV2,
    ParticipantControlEpisodeStateV2,
    ParticipantControlProducedTargetV2,
    ParticipantControlRecordLifecycleV2,
    cited_participant_control_target,
    participant_control_target_authorization,
    participant_control_target_reference,
)

Kind = MixedControlTransitionKind
TargetKind = ParticipantControlTargetKind
PARTICIPANT_CONTROL_VALIDITY_BOUNDS_MISMATCH = (
    "accepted participant control occurrence validity bounds must equal the pinned policy's evaluated window"
)
_ORDER_STRATEGY = "total-effective-order"
_OUTSIDE_EPISODE = "participant control occurrence lies outside its pinned episode policy"
_PIN_NOT_CONSTANT = "participant control policy pin must be constant within an episode"


def _first_broken(rules: Sequence[tuple[bool, str]]) -> str | None:
    """Return the message of the first broken rule, in order."""

    return next((message for broken, message in rules if broken), None)


def _first_violation(*checks: Callable[[], str | None]) -> str | None:
    """Evaluate checks lazily in order and return the first violation."""

    return next((result for result in (check() for check in checks) if result is not None), None)


@dataclass
class _EpisodeFold:
    policy: ParticipantControlOccurrencePolicyModel
    available_targets: Sequence[ParticipantControlOccurrenceTarget]
    state: ParticipantControlEpisodeStateV2 = field(init=False)
    records: dict[str, ParticipantControlOccurrenceV2Model] = field(default_factory=dict)
    rejection_code: str | None = None

    def __post_init__(self) -> None:
        self.state = ParticipantControlEpisodeStateV2(
            participant_address=self.policy.participant_address,
            episode_id=self.policy.episode_id,
            state_ref=self.policy.initial_state_ref,
        )

    def apply(self, record: ParticipantControlOccurrenceV2Model) -> str | None:
        occurrence = record.occurrence
        violation = self._envelope_violation(record)
        if violation is None and isinstance(occurrence, ParticipantRejectedOccurrenceV2Model):
            violation = self._rejected(occurrence)
        elif violation is None:
            violation = self._structure(occurrence) or self._accepted_rejection(record, occurrence)
            if violation is None:
                self._advance(record, occurrence)
        return violation

    def _envelope_violation(self, record: ParticipantControlOccurrenceV2Model) -> str | None:
        scope = (self.policy.participant_address, self.policy.episode_id)
        pinned = (self.policy.semantics, policy_pin_key(self.policy.pin))
        rules = (
            ((record.participant_address, record.episode_id) != scope, _OUTSIDE_EPISODE),
            ((record.semantics, policy_pin_key(record.policy)) != pinned, _PIN_NOT_CONSTANT),
        )
        return _first_broken(rules)

    def _rejected(self, occurrence: ParticipantRejectedOccurrenceV2Model) -> str | None:
        observed = occurrence.observed
        live = self.state
        expected = (live.state_ref, live.state_revision, live.last_order, occurrence.occurrence_revision - 1)
        if (
            observed.state_ref,
            observed.state_revision,
            observed.last_accepted_order,
            observed.history_head,
        ) != expected:
            return "rejected participant control occurrence must record the true observed state"
        known = self.policy.transition(occurrence.attempted.permitted_transition_ref) is not None
        if not known and occurrence.reason_code.value != "unknown-transition":
            return "rejected attempt naming no permitted transition must record unknown-transition"
        return None

    def _structure(self, occurrence: ParticipantAcceptedOccurrenceV2Model) -> str | None:
        transition = self.policy.transition(occurrence.permitted_transition_ref)
        if transition is not None and occurrence.resulting_state_ref != transition.to_state_ref:
            return "accepted participant control occurrence must result in its permitted transition's destination"
        if self.policy.pin.form == "reusable-policy" and occurrence.script_step_ref is not None:
            return "accepted participant control occurrence names a script step outside a finite-script policy"
        return None

    def _accepted_rejection(
        self, record: ParticipantControlOccurrenceV2Model, occurrence: ParticipantAcceptedOccurrenceV2Model
    ) -> str | None:
        code = _first_violation(
            lambda: self._state_rejection(occurrence),
            lambda: self._authority_rejection(occurrence),
            lambda: self._order_rejection(occurrence),
            lambda: self._kind_rejection(occurrence),
        )
        if code is not None:
            self.rejection_code = code
            return f"accepted participant control occurrence fails {code}"
        return _first_violation(
            lambda: self._transformation_violation(record, occurrence),
            lambda: self._bounds_violation(occurrence),
        )

    def _bounds_violation(self, occurrence: ParticipantAcceptedOccurrenceV2Model) -> str | None:
        bounds = participant_control_validity_bounds(
            self.policy, occurrence.permitted_transition_ref, occurrence.script_step_ref
        )
        matches = bounds == (occurrence.valid_from_order, occurrence.valid_until_order)
        return None if matches else PARTICIPANT_CONTROL_VALIDITY_BOUNDS_MISMATCH

    def _state_rejection(self, occurrence: ParticipantAcceptedOccurrenceV2Model) -> str | None:
        transition = self.policy.transition(occurrence.permitted_transition_ref)
        live = self.state
        observed = (live.state_ref, live.state_revision)
        rules = (
            (lambda: self.policy.order_strategy != _ORDER_STRATEGY, "unsupported-order-strategy"),
            (lambda: transition is None, "unknown-transition"),
            (lambda: transition.kind != occurrence.kind, "transition-kind-mismatch"),
            (
                lambda: (
                    (occurrence.prior_state_ref, occurrence.expected_state_revision) != observed
                    or transition.from_state_ref != live.state_ref
                ),
                "stale-state",
            ),
        )
        code = next((code for broken, code in rules if broken()), None)
        return code or self._script_rejection(occurrence)

    def _script_rejection(self, occurrence: ParticipantAcceptedOccurrenceV2Model) -> str | None:
        if self.policy.pin.form != "finite-script":
            return None
        cursor = self.state.script_cursor
        step = self.policy.script_steps[cursor] if cursor < len(self.policy.script_steps) else None
        if step is None:
            return "script-exhausted"
        expected_revision = step.expected_state_revision
        mismatch = (
            occurrence.script_step_ref != step.step_ref
            or occurrence.permitted_transition_ref != step.transition_ref
            or (expected_revision is not None and expected_revision != occurrence.expected_state_revision)
        )
        return "script-step-mismatch" if mismatch else None

    def _authority_rejection(self, occurrence: ParticipantAcceptedOccurrenceV2Model) -> str | None:
        transition = self.policy.transition(occurrence.permitted_transition_ref)
        source = self.policy.state(transition.from_state_ref)
        destination = self.policy.state(transition.to_state_ref)
        acting = (occurrence.controller_ref, occurrence.authority_basis_refs)
        granted = set(source.scope_refs) & set(self.policy.behavior_scope_refs)
        rules = (
            (acting != (source.controller_ref, source.authority_basis_refs), "controller-not-source"),
            (not set(occurrence.controlled_scope_refs) <= granted, "scope-widened"),
            ("revoked" in (source.authority_status, destination.authority_status), "revoked-authority"),
        )
        return _first_broken(rules)

    def _order_rejection(self, occurrence: ParticipantAcceptedOccurrenceV2Model) -> str | None:
        order = occurrence.effective_order
        if self.state.last_order is not None and order <= self.state.last_order:
            return "non-increasing-order"
        # Inside every evaluated window (edge, step, source and destination state) means inside their intersection.
        bounds = participant_control_validity_bounds(
            self.policy, occurrence.permitted_transition_ref, occurrence.script_step_ref
        )
        return None if bounds is not None and bounds[0] <= order <= bounds[1] else "late-authority"

    def _kind_rejection(self, occurrence: ParticipantAcceptedOccurrenceV2Model) -> str | None:
        cited = cited_participant_control_target(occurrence)
        return _first_violation(
            lambda: self._identity_rejection(occurrence),
            lambda: None if cited is None else self._target_rejection(occurrence, *cited),
        )

    def _target_rejection(
        self,
        occurrence: ParticipantAcceptedOccurrenceV2Model,
        target_kind: TargetKind,
        target_ref: str,
        target_revision: int,
    ) -> str | None:
        source_link = isinstance(occurrence, ParticipantProposalOccurrenceV2Model)
        if not source_link and not self._target_kind_permitted(occurrence, target_kind, target_ref):
            return "invalid-target"
        reference = participant_control_target_reference(
            self.state,
            self.available_targets,
            target_kind=target_kind,
            target_ref=target_ref,
            target_revision=target_revision,
            position=occurrence.occurrence_revision,
        )
        if reference is not None or source_link:
            return reference
        return participant_control_target_authorization(
            self.state, citing_kind=Kind(occurrence.kind), target_kind=target_kind, target_ref=target_ref
        )

    def _target_kind_permitted(
        self, occurrence: ParticipantAcceptedOccurrenceV2Model, target_kind: TargetKind, target_ref: str
    ) -> bool:
        transition = self.policy.transition(occurrence.permitted_transition_ref)
        step = self.policy.step(occurrence.script_step_ref)
        if target_kind not in transition.target_kinds or (
            step is not None and step.target_kind is not None and step.target_kind is not target_kind
        ):
            return False
        if step is None or step.target_step_ref is None:
            return True
        producer = dict(self.state.step_records).get(step.target_step_ref)
        produced = self.state.produced(target_kind, target_ref)
        return producer is not None and produced is not None and produced.record_event_id == producer

    def _identity_rejection(self, occurrence: ParticipantAcceptedOccurrenceV2Model) -> str | None:
        taken = (
            self.state.proposal_ids
            | self.state.decision_ids
            | {item.transition_ref for item in self.policy.transitions}
        )
        clash, code = False, None
        if isinstance(occurrence, ParticipantProposalOccurrenceV2Model):
            clash, code = occurrence.proposal_id in taken, "proposal-identity-reused"
        elif isinstance(occurrence, (ParticipantApprovalOccurrenceV2Model, ParticipantDenialOccurrenceV2Model)):
            clash, code = occurrence.decision_ref in taken, "decision-identity-reused"
        elif isinstance(occurrence, ParticipantHandoffOccurrenceV2Model):
            clash = occurrence.completion_evidence_ref in self.state.completion_evidence_refs
            code = "completion-evidence-reused"
        return code if clash else None

    def _transformation_violation(
        self, record: ParticipantControlOccurrenceV2Model, occurrence: ParticipantAcceptedOccurrenceV2Model
    ) -> str | None:
        produced = None
        if isinstance(occurrence, ParticipantProposalOccurrenceV2Model) and occurrence.source_proposal_ref is not None:
            produced = self.state.produced(TargetKind.PROPOSAL, occurrence.source_proposal_ref)
        if produced is None:
            return None
        source = self.records[produced.record_event_id]
        rules = (
            (
                not {source.event_id, occurrence.transformation_ref} <= set(record.provenance_refs),
                "transformed proposal provenance must bind its source and transformation",
            ),
            (
                not set(source.object_marking_refs) <= set(record.object_marking_refs),
                "transformed proposal must inherit source markings",
            ),
        )
        return _first_broken(rules)

    def _advance(
        self, record: ParticipantControlOccurrenceV2Model, occurrence: ParticipantAcceptedOccurrenceV2Model
    ) -> None:
        live = self.state
        position = occurrence.occurrence_revision
        produced = [
            ParticipantControlProducedTargetV2(TargetKind.CONTROL, record.event_id, position, position, record.event_id)
        ]
        lifecycles = {item.event_id: item for item in live.lifecycles}
        lifecycles[record.event_id] = ParticipantControlRecordLifecycleV2(record.event_id)
        proposal_ids, decision_ids, completions = live.proposal_ids, live.decision_ids, live.completion_evidence_refs
        if isinstance(occurrence, ParticipantProposalOccurrenceV2Model):
            produced.append(
                ParticipantControlProducedTargetV2(
                    TargetKind.PROPOSAL, occurrence.proposal_id, 1, position, record.event_id
                )
            )
            proposal_ids |= {occurrence.proposal_id}
        elif isinstance(occurrence, (ParticipantApprovalOccurrenceV2Model, ParticipantDenialOccurrenceV2Model)):
            produced.append(
                ParticipantControlProducedTargetV2(
                    TargetKind.DECISION, occurrence.decision_ref, 1, position, record.event_id
                )
            )
            decision_ids |= {occurrence.decision_ref}
        elif isinstance(occurrence, ParticipantHandoffOccurrenceV2Model):
            completions |= {occurrence.completion_evidence_ref}
        cited = cited_participant_control_target(occurrence)
        if cited is not None:
            cited_record = live.produced(cited[0], cited[1])
            if cited_record is not None:
                event_id = cited_record.record_event_id
                lifecycles[event_id] = _cited_lifecycle(lifecycles[event_id], occurrence, cited[0])
        steps = live.step_records
        if occurrence.script_step_ref is not None:
            steps = (*steps, (occurrence.script_step_ref, record.event_id))
        self.records[record.event_id] = record
        self.state = replace(
            live,
            state_ref=occurrence.resulting_state_ref,
            state_revision=occurrence.resulting_state_revision,
            last_order=occurrence.effective_order,
            script_cursor=live.script_cursor + int(self.policy.pin.form == "finite-script"),
            targets=(*live.targets, *produced),
            lifecycles=tuple(lifecycles.values()),
            proposal_ids=proposal_ids,
            decision_ids=decision_ids,
            completion_evidence_refs=completions,
            step_records=steps,
        )


def _cited_lifecycle(
    lifecycle: ParticipantControlRecordLifecycleV2,
    occurrence: ParticipantAcceptedOccurrenceV2Model,
    target_kind: TargetKind,
) -> ParticipantControlRecordLifecycleV2:
    """Apply one accepted record's effect to the lifecycle of the record it cites."""

    supersedes = isinstance(occurrence, ParticipantOverrideOccurrenceV2Model) or (
        isinstance(occurrence, ParticipantCancellationOccurrenceV2Model)
        and target_kind in {TargetKind.PROPOSAL, TargetKind.DECISION}
    )
    return ParticipantControlRecordLifecycleV2(
        event_id=lifecycle.event_id,
        superseded=lifecycle.superseded or supersedes,
        decided=lifecycle.decided
        or isinstance(occurrence, (ParticipantApprovalOccurrenceV2Model, ParticipantDenialOccurrenceV2Model)),
        replaced=lifecycle.replaced or isinstance(occurrence, ParticipantProposalOccurrenceV2Model),
    )


def fold_participant_control_episode_v2(
    records: Sequence[ParticipantControlOccurrenceV2Model],
    *,
    policy: ParticipantControlOccurrencePolicyModel,
    available_targets: Sequence[ParticipantControlOccurrenceTarget] = (),
) -> ParticipantControlEpisodeFoldV2:
    """Fold one episode's v2 records in archive order under its pinned policy."""

    fold = _EpisodeFold(policy, available_targets)
    for record in records:
        violation = fold.apply(record)
        if violation is not None:
            return ParticipantControlEpisodeFoldV2(fold.state, violation, fold.rejection_code)
    return ParticipantControlEpisodeFoldV2(fold.state)


def validate_participant_control_history_v2(
    records: Sequence[object],
    *,
    declarations: Sequence[ParticipantControlDeclarationModel],
    known_targets: Sequence[ParticipantControlTargetContextModel],
    policies: Sequence[ParticipantControlOccurrencePolicyModel],
    available_targets: Sequence[ParticipantControlOccurrenceTarget],
    validate_v1: Callable[..., None],
) -> None:
    """Validate a batch containing any non-v1 record; raise ``ValueError`` when unverifiable or invalid."""

    if not participant_control_history_verifiability(records, declarations=declarations, policies=policies).verifiable:
        raise ValueError(PARTICIPANT_CONTROL_HISTORY_UNVERIFIABLE)
    v1_records = []
    completions: set[str] = set()
    for (participant, episode), episode_records in _contiguous_episodes(records).items():
        lineages = {participant_control_occurrence_lineage(record) for record in episode_records}
        if len(lineages) != 1:
            raise ValueError("participant control episode must not mix occurrence lineages")
        if lineages == {"v1"}:
            v1_records.extend(episode_records)
            continue
        policy = resolve_participant_control_episode_policy(policies, participant, episode, episode_records[0])
        completions = _fold_episode(episode_records, policy, available_targets, completions)
    if v1_records:
        validate_v1(v1_records, declarations=declarations, known_targets=known_targets)


def _contiguous_episodes(records: Sequence[object]) -> dict[tuple[str, str], list[object]]:
    """Group a complete, contiguous, uniquely identified participant prefix by episode, in archive order."""

    episodes: dict[tuple[str, str], list[object]] = {}
    positions: dict[str, int] = {}
    event_ids: set[str] = set()
    for record in records:
        position = record.occurrence.occurrence_revision
        if position != positions.get(record.participant_address, 0) + 1 or record.event_id in event_ids:
            raise ValueError("participant control history must be a complete, contiguous, uniquely identified prefix")
        positions[record.participant_address] = position
        event_ids.add(record.event_id)
        episodes.setdefault((record.participant_address, record.episode_id), []).append(record)
    return episodes


def _fold_episode(
    records: list[object],
    policy: ParticipantControlOccurrencePolicyModel,
    available_targets: Sequence[ParticipantControlOccurrenceTarget],
    completions: set[str],
) -> set[str]:
    result = fold_participant_control_episode_v2(records, policy=policy, available_targets=available_targets)
    if result.violation is not None:
        raise ValueError(result.violation)
    if completions & result.state.completion_evidence_refs:
        raise ValueError("handoff completion evidence must not be reused")
    return completions | result.state.completion_evidence_refs


def resolve_participant_control_episode_policy(
    policies: Sequence[ParticipantControlOccurrencePolicyModel],
    participant: str,
    episode: str,
    record: ParticipantControlOccurrenceV2Model,
) -> ParticipantControlOccurrencePolicyModel:
    matches = [
        policy
        for policy in policies
        if (policy.participant_address, policy.episode_id, policy.semantics, policy_pin_key(policy.pin))
        == (participant, episode, record.semantics, policy_pin_key(record.policy))
    ]
    if any(policy != matches[0] for policy in matches[1:]):
        raise ValueError("participant control policy identity was reused with different semantics")
    return matches[0]


__all__ = [
    "PARTICIPANT_CONTROL_VALIDITY_BOUNDS_MISMATCH",
    "fold_participant_control_episode_v2",
    "validate_participant_control_history_v2",
]
