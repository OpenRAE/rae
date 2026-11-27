"""ASR-535 participant-policy probe vocabulary.

The declarative half of the probe family: the closed operation and expectation
vocabularies, the case record a harness fills in, the harness protocol, and the
claim binding used when a declaration was never established. The runner that
executes these cases and judges their outcome lives in
``participant_policy_probes``; keeping the vocabulary separate makes it obvious
that a harness contributes inputs and expectations, never a verdict.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from raes_contracts.behavioral_claims import BehavioralClaimBindingModel
from raes_runtime.registry import RuntimeTarget

from raes_conformance.conformance.report import (
    ParticipantPolicyAssumptions,
    ParticipantPolicyBinding,
)

_STANDING_LIMITATIONS = (
    "Results are bounded by the named target, profile, harness case policy, and execution environment.",
    "Manifest validity and method presence do not establish participant-policy realization.",
)

_STANDING_NON_CLAIMS = (
    "Does not establish policy noninterference; finite refutation attempts are not the universal obligation.",
    "Does not establish trace equivalence, simulation, refinement, or bisimulation.",
    "Does not establish native-backend enforcement or behavior outside the executed cases.",
)


class ParticipantPolicyOperation(str, Enum):
    """The typed runtime boundary the runner drives for a case.

    A closed set the runner knows how to invoke itself. These are operation
    kinds, not backend identities, so adding a backend never adds a branch here.
    """

    ACTION_INGRESS = "action-ingress"
    STATUS_PROJECTION = "status-projection"
    INJECT_DELIVERY = "inject-delivery"
    SUPERVISORY_CONTROL = "supervisory-control"


class ParticipantPolicyExpectation(str, Enum):
    """The obligation's required observable result.

    ``DENIED`` and ``WITHHELD`` are deliberately distinct. SEM-230 keeps refusal
    and intentional non-release as separate transition facts, so a single
    "refused" boolean would let a runtime that always denies egress satisfy a
    claimed withholding obligation.
    """

    DENIED = "denied"
    WITHHELD = "withheld"
    RELEASED = "released"


_REFUSAL_EXPECTATIONS = frozenset({ParticipantPolicyExpectation.DENIED, ParticipantPolicyExpectation.WITHHELD})

_EXPECTED_DISPOSITIONS = {
    ParticipantPolicyExpectation.DENIED: frozenset({"deny", "unsupported"}),
    ParticipantPolicyExpectation.WITHHELD: frozenset({"withhold", "deny"}),
    ParticipantPolicyExpectation.RELEASED: frozenset({"permit", "transform"}),
}


@dataclass(frozen=True)
class ParticipantPolicyProbeCase:
    """One finite, single-fault participant-policy obligation, declared as data.

    Every field is an input or an expectation. There is deliberately no callable
    that returns a control plane or an outcome: the runner builds the plane on
    the target under evaluation and derives the result itself.
    """

    obligation: str
    feature: str
    binding: ParticipantPolicyBinding
    expectation: ParticipantPolicyExpectation
    operation: ParticipantPolicyOperation
    resolver: object
    identity: object
    crossing_evidence: object
    participant_address: str
    episode_id: str
    idempotency_key: str
    behavior: object | None = None
    admission_request: object | None = None
    control_intent: object | None = None
    behavior_specifications: Mapping[str, object] | None = None
    projection_ref: str = "runtime.participant.visibility-projection"
    setup_requests: tuple[tuple[object, str], ...] = ()
    """``(admission_request, idempotency_key)`` pairs the runner admits before the
    case's own operation, for obligations that need an advanced state cut."""

    expect_audit: bool = True
    """Whether the obligation requires safe audit evidence for its refusal.

    A policy denial must leave auditable evidence. A few obligations fail closed
    at an earlier structural boundary — a replay rejected because the state cut
    advanced never reaches policy evaluation — and demanding an audit event
    there would assert one that was never produced.
    """


@runtime_checkable
class ParticipantPolicyProbeHarness(Protocol):
    """Backend-neutral supplier of declarative participant-policy cases.

    The harness owns the deployment-specific *inputs* the conformance engine
    cannot invent: a validated exact-cut policy resolver, deterministic
    participant/audience/policy/projection coordinates, typed carriers, and its
    own declared case policy and digest. It owns none of the verdict.
    """

    probe_set_digest: str

    def cases(self, target: RuntimeTarget) -> tuple[ParticipantPolicyProbeCase, ...]:
        """Return the finite case set to drive against ``target``."""


def _unprobed_binding(feature: str) -> ParticipantPolicyBinding:
    """Bind an unestablished declaration to the catalog's declaration relation.

    ``capability-declaration`` is the governed relation for exactly this state:
    the backend has declared support and nothing has established it. Recording
    it through the same claim model keeps the catalog authoritative for a
    non-result as well as a result.
    """

    unknown = "unknown: no authorized probe outcome was established"
    return ParticipantPolicyBinding(
        obligation="unsupported-capability",
        claim=BehavioralClaimBindingModel(
            taxonomy_id="raes-behavioral-relations",
            taxonomy_revision="rev8",
            relation_id="capability-declaration",
            subject=f"Unestablished participant-policy declaration for feature {feature}",
            quantifier_scope="single-artifact",
            evidence_scope="structural",
            evidence_boundary=(
                "A static manifest declaration only; no authorized participant-policy behavior was "
                "observed, so no case, trace, participant, or backend behavior is quantified."
            ),
            assurance_status="defined",
            limitations=list(_STANDING_LIMITATIONS),
            explicit_non_claims=list(_STANDING_NON_CLAIMS),
        ),
        participant_ref=unknown,
        audience_ref=unknown,
        memory_scope=unknown,
        policy_id=unknown,
        policy_revision=unknown,
        policy_decision_ref=unknown,
        decision_cut_ref=unknown,
        assumptions=ParticipantPolicyAssumptions(
            order_model=unknown,
            scheduler_class=unknown,
            environment_class=unknown,
            nondeterminism=unknown,
            termination_and_progress=unknown,
            timing=unknown,
            probability=unknown,
            partial_order=unknown,
        ),
    )


def _declared_level(target: RuntimeTarget, feature: str) -> str | None:
    """Return the support level ``target`` declares for ``feature``, if any."""

    capabilities = target.manifest.participant_runtime
    if capabilities is None:
        return None
    for entry in capabilities.feature_support:
        if entry.feature == feature:
            return entry.support_level.value
    return None


__all__ = (
    "ParticipantPolicyExpectation",
    "ParticipantPolicyOperation",
    "ParticipantPolicyProbeCase",
    "ParticipantPolicyProbeHarness",
    "_EXPECTED_DISPOSITIONS",
    "_REFUSAL_EXPECTATIONS",
    "_STANDING_LIMITATIONS",
    "_STANDING_NON_CLAIMS",
    "_declared_level",
    "_unprobed_binding",
)
