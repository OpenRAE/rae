"""Test-local finite model for the SEM-233 revision-1 algebra.

This module is bounded falsification evidence. It is not a portable contract,
runtime policy implementation, model checker, or proof.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum

from raes_contracts.errors import InvalidInputError


class UnsupportedFlow(InvalidInputError):
    """The bounded model cannot resolve the requested flow operation."""


class FlowOperation(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    ADMISSION = "admission"
    APPROVAL = "approval"
    DECLASSIFICATION = "declassification"
    ENDORSEMENT = "endorsement"
    REDACTION = "redaction"
    TRANSFORMATION = "transformation"


@dataclass(frozen=True)
class FlowLabel:
    profile_id: str
    profile_revision: str
    confidentiality: frozenset[str]
    integrity: frozenset[str]


@dataclass(frozen=True)
class FlowProfile:
    profile_id: str
    profile_revision: str
    authority_revision: str
    confidentiality_universe: frozenset[str]
    integrity_universe: frozenset[str]

    def __post_init__(self) -> None:
        if not self.profile_id or not self.profile_revision or not self.authority_revision:
            raise UnsupportedFlow("profile coordinates must be non-empty")
        if "conf:deny-unresolved" not in self.confidentiality_universe:
            raise UnsupportedFlow("confidentiality universe must contain its deny-unresolved obligation")
        if "int:deny-unresolved" not in self.integrity_universe:
            raise UnsupportedFlow("integrity universe must contain its deny-unresolved obligation")

    def label(
        self,
        *,
        confidentiality: Iterable[str] = (),
        integrity: Iterable[str] = (),
    ) -> FlowLabel:
        confidentiality_set = frozenset(confidentiality)
        integrity_set = frozenset(integrity)
        unknown_confidentiality = confidentiality_set - self.confidentiality_universe
        if unknown_confidentiality:
            raise UnsupportedFlow(
                f"obligations outside the closed confidentiality universe: {sorted(unknown_confidentiality)}"
            )
        unknown_integrity = integrity_set - self.integrity_universe
        if unknown_integrity:
            raise UnsupportedFlow(f"obligations outside the closed integrity universe: {sorted(unknown_integrity)}")
        return FlowLabel(
            profile_id=self.profile_id,
            profile_revision=self.profile_revision,
            confidentiality=confidentiality_set,
            integrity=integrity_set,
        )

    @property
    def bottom(self) -> FlowLabel:
        return self.label()

    @property
    def top(self) -> FlowLabel:
        return self.label(
            confidentiality=self.confidentiality_universe,
            integrity=self.integrity_universe,
        )

    @property
    def unknown_label(self) -> FlowLabel:
        return self.top


def _require_profile(profile: FlowProfile, label: FlowLabel) -> None:
    if (label.profile_id, label.profile_revision) != (profile.profile_id, profile.profile_revision):
        raise UnsupportedFlow("label and profile coordinates do not match")
    if not label.confidentiality <= profile.confidentiality_universe:
        raise UnsupportedFlow("label is outside the closed confidentiality universe")
    if not label.integrity <= profile.integrity_universe:
        raise UnsupportedFlow("label is outside the closed integrity universe")


def join_labels(profile: FlowProfile, labels: Iterable[FlowLabel]) -> FlowLabel:
    confidentiality: set[str] = set()
    integrity: set[str] = set()
    for label in labels:
        _require_profile(profile, label)
        confidentiality.update(label.confidentiality)
        integrity.update(label.integrity)
    return profile.label(confidentiality=confidentiality, integrity=integrity)


def label_leq(left: FlowLabel, right: FlowLabel) -> bool:
    if (left.profile_id, left.profile_revision) != (right.profile_id, right.profile_revision):
        raise UnsupportedFlow("label profile coordinates do not match")
    return left.confidentiality <= right.confidentiality and left.integrity <= right.integrity


@dataclass(frozen=True)
class CoordinateRewrite:
    operation: FlowOperation
    source_ref: str
    result_ref: str
    profile_id: str
    profile_revision: str
    policy_ref: str
    policy_revision: str
    removed_confidentiality: frozenset[str]
    removed_integrity: frozenset[str]
    authority_ref: str
    sink_ref: str
    state_cut_ref: str


@dataclass(frozen=True)
class FlowValue:
    value_ref: str
    label: FlowLabel | None
    provenance_refs: frozenset[str]
    influence_refs: frozenset[str]
    participant_ref: str
    episode_ref: str
    policy_ref: str
    policy_revision: str
    state_cut_ref: str
    supported: bool = True
    rewrites: tuple[CoordinateRewrite, ...] = ()

    def without_label(self) -> FlowValue:
        return replace(self, label=None, supported=False)

    @property
    def semantic_state(self) -> tuple[FlowLabel | None, frozenset[str], frozenset[str]]:
        return (self.label, self.provenance_refs, self.influence_refs)


def derive(
    profile: FlowProfile,
    *,
    result_ref: str,
    inputs: Iterable[FlowValue],
    participant_ref: str,
    episode_ref: str,
    policy_ref: str,
    policy_revision: str,
    state_cut_ref: str,
) -> FlowValue:
    materialized_inputs = tuple(inputs)
    supported = bool(materialized_inputs) and all(
        value.supported and value.label is not None for value in materialized_inputs
    )
    labels = tuple(value.label for value in materialized_inputs if value.label is not None)
    label = join_labels(profile, labels) if supported else profile.unknown_label
    provenance_refs = frozenset(
        ref for value in materialized_inputs for ref in (*value.provenance_refs, f"derived-from:{value.value_ref}")
    )
    influence_refs = frozenset(
        ref for value in materialized_inputs for ref in (*value.influence_refs, f"possible-influence:{value.value_ref}")
    )
    if not supported:
        provenance_refs |= {"provenance:unresolved-label"}
        influence_refs |= {"influence:unresolved-label"}
    rewrites = tuple(
        sorted(
            {rewrite for value in materialized_inputs for rewrite in value.rewrites},
            key=lambda rewrite: (
                rewrite.state_cut_ref,
                rewrite.result_ref,
                rewrite.operation.value,
                rewrite.authority_ref,
            ),
        )
    )
    return FlowValue(
        value_ref=result_ref,
        label=label,
        provenance_refs=provenance_refs,
        influence_refs=influence_refs,
        participant_ref=participant_ref,
        episode_ref=episode_ref,
        policy_ref=policy_ref,
        policy_revision=policy_revision,
        state_cut_ref=state_cut_ref,
        supported=supported,
        rewrites=rewrites,
    )


def carry(
    profile: FlowProfile,
    source: FlowValue,
    *,
    result_ref: str,
    participant_ref: str,
    episode_ref: str,
    policy_ref: str,
    policy_revision: str,
    state_cut_ref: str,
) -> FlowValue:
    return derive(
        profile,
        result_ref=result_ref,
        inputs=(source,),
        participant_ref=participant_ref,
        episode_ref=episode_ref,
        policy_ref=policy_ref,
        policy_revision=policy_revision,
        state_cut_ref=state_cut_ref,
    )


def rewrite_coordinate(
    profile: FlowProfile,
    source: FlowValue,
    *,
    result_ref: str,
    operation: FlowOperation,
    remove_confidentiality: frozenset[str],
    remove_integrity: frozenset[str],
    authority_ref: str,
    sink_ref: str,
    state_cut_ref: str,
) -> FlowValue:
    if source.label is None or not source.supported:
        raise UnsupportedFlow("an unresolved source label cannot be rewritten")
    _require_profile(profile, source.label)
    if not result_ref or result_ref == source.value_ref:
        raise UnsupportedFlow("a coordinate rewrite requires a fresh result identity")
    if not authority_ref or not sink_ref or not state_cut_ref:
        raise UnsupportedFlow("a coordinate rewrite requires exact authority, sink, and cut refs")

    confidentiality = source.label.confidentiality
    integrity = source.label.integrity
    if operation is FlowOperation.DECLASSIFICATION:
        if remove_integrity:
            raise UnsupportedFlow("declassification cannot rewrite the integrity coordinate")
        if not remove_confidentiality <= confidentiality:
            raise UnsupportedFlow("declassification names absent confidentiality obligations")
        confidentiality -= remove_confidentiality
    elif operation is FlowOperation.ENDORSEMENT:
        if remove_confidentiality:
            raise UnsupportedFlow("endorsement cannot rewrite the confidentiality coordinate")
        if not remove_integrity <= integrity:
            raise UnsupportedFlow("endorsement names absent integrity obligations")
        integrity -= remove_integrity
    else:
        raise UnsupportedFlow(f"{operation.value} cannot rewrite flow coordinates")

    rewrite = CoordinateRewrite(
        operation=operation,
        source_ref=source.value_ref,
        result_ref=result_ref,
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        policy_ref=source.policy_ref,
        policy_revision=source.policy_revision,
        removed_confidentiality=remove_confidentiality,
        removed_integrity=remove_integrity,
        authority_ref=authority_ref,
        sink_ref=sink_ref,
        state_cut_ref=state_cut_ref,
    )
    return FlowValue(
        value_ref=result_ref,
        label=profile.label(confidentiality=confidentiality, integrity=integrity),
        provenance_refs=source.provenance_refs | {source.value_ref, f"rewrite:{operation.value}:{authority_ref}"},
        influence_refs=source.influence_refs,
        participant_ref=source.participant_ref,
        episode_ref=source.episode_ref,
        policy_ref=source.policy_ref,
        policy_revision=source.policy_revision,
        state_cut_ref=state_cut_ref,
        supported=True,
        rewrites=(*source.rewrites, rewrite),
    )


@dataclass(frozen=True)
class SinkPolicy:
    sink_ref: str
    destination_ref: str
    profile_id: str
    profile_revision: str
    policy_ref: str
    policy_revision: str
    state_cut_ref: str
    satisfied_confidentiality: frozenset[str]
    satisfied_integrity: frozenset[str]


@dataclass(frozen=True)
class FlowGateState:
    authenticated: bool
    authorized: bool
    admitted: bool
    effective_capability: bool
    crossing_valid: bool
    fresh_history_heads: bool

    @classmethod
    def allowing(cls) -> FlowGateState:
        return cls(
            authenticated=True,
            authorized=True,
            admitted=True,
            effective_capability=True,
            crossing_valid=True,
            fresh_history_heads=True,
        )

    @classmethod
    def gate_names(cls) -> tuple[str, ...]:
        return (
            "authenticated",
            "authorized",
            "admitted",
            "effective_capability",
            "crossing_valid",
            "fresh_history_heads",
        )

    def deny(self, gate_name: str) -> FlowGateState:
        if gate_name not in self.gate_names():
            raise UnsupportedFlow(f"unknown final-sink gate {gate_name!r}")
        return replace(self, **{gate_name: False})

    @property
    def all_allow(self) -> bool:
        return all(getattr(self, gate_name) for gate_name in self.gate_names())


def may_flow_at_sink(
    profile: FlowProfile,
    value: FlowValue,
    sink: SinkPolicy,
    gates: FlowGateState,
) -> bool:
    if value.label is None or not value.supported:
        return False
    if not value.provenance_refs or not value.influence_refs:
        return False
    try:
        _require_profile(profile, value.label)
    except UnsupportedFlow:
        return False
    if (sink.profile_id, sink.profile_revision) != (profile.profile_id, profile.profile_revision):
        return False
    if (value.policy_ref, value.policy_revision, value.state_cut_ref) != (
        sink.policy_ref,
        sink.policy_revision,
        sink.state_cut_ref,
    ):
        return False
    if not sink.satisfied_confidentiality <= profile.confidentiality_universe:
        return False
    if not sink.satisfied_integrity <= profile.integrity_universe:
        return False
    if any(
        (
            rewrite.profile_id,
            rewrite.profile_revision,
            rewrite.policy_ref,
            rewrite.policy_revision,
            rewrite.sink_ref,
            rewrite.state_cut_ref,
        )
        != (
            sink.profile_id,
            sink.profile_revision,
            sink.policy_ref,
            sink.policy_revision,
            sink.sink_ref,
            sink.state_cut_ref,
        )
        for rewrite in value.rewrites
    ):
        return False
    return (
        value.label.confidentiality <= sink.satisfied_confidentiality
        and value.label.integrity <= sink.satisfied_integrity
        and gates.all_allow
    )
