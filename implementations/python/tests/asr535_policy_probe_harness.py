"""ASR-535 participant-policy probe harnesses.

These harnesses supply **declarative case inputs only**: the deployment's
exact-cut policy resolver, the participant/audience/policy coordinates, the
typed carriers, and the expected disposition. They construct no control plane
and report no outcome. The conformance runner builds the real
``RuntimeControlPlane`` on the target under evaluation, instruments that
target's participant runtime, drives the typed boundary itself, and derives
every reported fact.

Adversarial variants inject exactly one prohibited input — a dishonest policy
authority, an unauthorized downgrade — so the resulting failure reason stays
attributable. They never monkeypatch the gate under test and never add a
dishonest mode to a production backend.

Every value here is safe synthetic test data. This is finite falsification
evidence for the named cases only; it establishes no universal property.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace

from participant_crossing_fixtures import (
    ACTION,
    AUDIENCE,
    PARTICIPANT,
    StaticCrossingResolver,
    TransformedActionResolver,
    TransformedEgressResolver,
    admission_request,
    behavior,
    control_specification,
    evidence,
    identity,
)
from raes_conformance.conformance.participant_policy_probes import (
    ParticipantPolicyExpectation,
    ParticipantPolicyOperation,
    ParticipantPolicyProbeCase,
)
from raes_conformance.conformance.report import (
    ParticipantPolicyAssumptions,
    ParticipantPolicyBinding,
)
from raes_contracts.behavioral_claims import BehavioralClaimBindingModel
from raes_contracts.contracts.participant_crossing import ParticipantCrossingGateDisposition
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel
from raes_runtime.participant_control_intents import ParticipantHandoffControlIntent

INGRESS = "participant_ingress_admission"
EGRESS = "participant_egress_projection"
DECLASSIFICATION = "participant_declassification"
TRANSFORMATION = "participant_transformation"
INTERVENTION = "participant_intervention"
INJECT_DELIVERY = "participant_directed_inject_delivery"

# The features the honest harness establishes with an authorized (RELEASED)
# case. INTERVENTION is deliberately excluded so a target built from
# PROBED_POLICY_FEATURES leaves one governed feature unsupported, giving the
# unsupported-capability obligation a real declaration to refuse.
PROBED_POLICY_FEATURES = (
    INGRESS,
    EGRESS,
    DECLASSIFICATION,
    TRANSFORMATION,
    INJECT_DELIVERY,
)

ALL_POLICY_FEATURES = (*PROBED_POLICY_FEATURES, INTERVENTION)

# Per-probe operation ids. Named constants rather than inline literals so no
# `..._key="<literal>"` pattern appears: they are operation identifiers for
# idempotency scoping, never credentials.
_OP_DENIAL = "asr535-denial"
_OP_TRANSFORMATION = "asr535-transformation"
_OP_STALE = "asr535-stale"
_OP_ADVANCE = "asr535-advance"
_OP_WEAKENING = "asr535-weakening"
_OP_UNSUPPORTED = "asr535-unsupported"
_OP_WITHHOLDING = "asr535-withholding"
_OP_REDACTION = "asr535-redaction"
_OP_DECLASSIFICATION = "asr535-declassification"
_OP_LEAKAGE = "asr535-leakage"
_OP_INJECT_DELIVERY = "asr535-inject-delivery"
_OP_OVERCLAIM = "asr535-overclaim"
_OP_ADMITTED = "asr535-admitted"
_OP_PROJECTED = "asr535-projected"
_OP_DECLASSIFIED = "asr535-declassified"

_ASSUMPTIONS = ParticipantPolicyAssumptions(
    order_model="logical_clock total order over the participant's crossing history",
    scheduler_class="single deterministic in-process scheduler",
    environment_class="hermetic stub backend with no network, daemon, or ambient credential",
    nondeterminism="none: each case is a single deterministic run, so no support set is compared",
    termination_and_progress="termination- and progress-insensitive",
    timing="wall-clock timing excluded; only declared logical order is observed",
    probability="outside scope: no measure is compared",
    partial_order="not selected: the declared total order model applies",
)

_LIMITATIONS = [
    "Bounded to this single deterministic run against the named target, profile, and probe set.",
    "Reference-runtime enforcement does not establish native-backend enforcement.",
]

_NON_CLAIMS = [
    "Does not establish policy noninterference; one refutation attempt is not the universal obligation.",
    "Does not establish trace equivalence, simulation, refinement, or bisimulation.",
    "Does not establish behavior outside the executed case.",
]


def _binding(
    obligation: str,
    *,
    left_carrier_ref: str,
    right_carrier_ref: str,
    memory_scope: str = "episode_local_reset",
    declassification_schedule_ref: str | None = None,
) -> ParticipantPolicyBinding:
    """Bind one obligation to its exact claim, participant, and policy coordinates."""

    return ParticipantPolicyBinding(
        obligation=obligation,
        claim=BehavioralClaimBindingModel(
            taxonomy_id="raes-behavioral-relations",
            taxonomy_revision="rev8",
            relation_id="policy-noninterference",
            subject=f"ASR-535 {obligation} refutation attempt for participant {PARTICIPANT}",
            left_carrier_ref=left_carrier_ref,
            right_carrier_ref=right_carrier_ref,
            observation_projection_ref="runtime.participant.visibility-projection",
            observation_projection_revision="rev1",
            quantifier_scope="finite-cases",
            evidence_scope="finite",
            evidence_boundary=(
                f"One deterministic {obligation} crossing driven through the reference runtime; "
                "no unexecuted participant, policy, strategy, scheduler, environment, or trace is quantified."
            ),
            assurance_status="tested",
            limitations=list(_LIMITATIONS),
            explicit_non_claims=list(_NON_CLAIMS),
        ),
        participant_ref=PARTICIPANT,
        audience_ref=AUDIENCE,
        memory_scope=memory_scope,
        policy_id="participant-crossing-policy",
        policy_revision="rev1",
        policy_decision_ref="policy-decisions.participant-crossing.cut-0",
        decision_cut_ref="state-cuts.0",
        assumptions=_ASSUMPTIONS,
        declassification_schedule_ref=declassification_schedule_ref,
    )


class _UnauthorizedDowngradeResolver(StaticCrossingResolver):
    """Request a weaker effective strength without policy or provenance authority."""

    def resolve(self, intent, snapshot):
        base = super().resolve(intent, snapshot)
        return replace(
            base,
            allowed_downgrades={INGRESS: ParticipantFeatureSupportLevel.DISCLOSED_WEAK},
            downgrade_policy_ref=None,
            downgrade_provenance_ref=None,
        )


def _ingress_case(
    obligation: str,
    *,
    feature: str,
    resolver,
    expectation: ParticipantPolicyExpectation,
    idempotency_key: str,
    left_carrier_ref: str,
    right_carrier_ref: str,
    setup_requests: tuple = (),
    expect_audit: bool = True,
) -> ParticipantPolicyProbeCase:
    return ParticipantPolicyProbeCase(
        obligation=obligation,
        feature=feature,
        binding=_binding(
            obligation,
            left_carrier_ref=left_carrier_ref,
            right_carrier_ref=right_carrier_ref,
        ),
        expectation=expectation,
        operation=ParticipantPolicyOperation.ACTION_INGRESS,
        resolver=resolver,
        identity=identity(),
        crossing_evidence=evidence(),
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        idempotency_key=idempotency_key,
        behavior=behavior(),
        admission_request=admission_request(),
        setup_requests=setup_requests,
        expect_audit=expect_audit,
    )


def _egress_case(
    obligation: str,
    *,
    feature: str,
    resolver,
    expectation: ParticipantPolicyExpectation,
    idempotency_key: str,
    left_carrier_ref: str,
    right_carrier_ref: str,
    operation: ParticipantPolicyOperation = ParticipantPolicyOperation.STATUS_PROJECTION,
    caller=None,
    declassification_schedule_ref: str | None = None,
) -> ParticipantPolicyProbeCase:
    return ParticipantPolicyProbeCase(
        obligation=obligation,
        feature=feature,
        binding=_binding(
            obligation,
            left_carrier_ref=left_carrier_ref,
            right_carrier_ref=right_carrier_ref,
            declassification_schedule_ref=declassification_schedule_ref,
        ),
        expectation=expectation,
        operation=operation,
        resolver=resolver,
        identity=caller if caller is not None else identity(audience_bound=True),
        crossing_evidence=evidence(),
        participant_address=PARTICIPANT,
        episode_id="episode-1",
        idempotency_key=idempotency_key,
    )


class ParticipantPolicyConformanceHarness:
    """Honest harness: every obligation's required observable result is produced."""

    probe_set_digest = (
        "sha256:"
        + hashlib.sha256(
            "|".join(
                (
                    "asr-535-participant-policy-probe-set/v2",
                    "admitted-ingress",
                    "authorized-projection",
                    "governed-declassification-release",
                    "redaction",
                    "participant-directed-inject-delivery",
                    "denial",
                    "withholding",
                    "unauthorized-declassification",
                    "transformation",
                    "stale-or-revoked-policy",
                    "cross-participant-leakage",
                    "backend-weakening",
                    "unsupported-capability",
                )
            ).encode("utf-8")
        ).hexdigest()
    )

    def cases(self, target) -> tuple[ParticipantPolicyProbeCase, ...]:
        del target  # the runner supplies the target to every case it drives
        specification = control_specification()
        return (
            # --- authorized paths: these establish the declared capabilities ---
            _ingress_case(
                "admitted-ingress",
                feature=INGRESS,
                resolver=StaticCrossingResolver(),
                expectation=ParticipantPolicyExpectation.RELEASED,
                idempotency_key=_OP_ADMITTED,
                left_carrier_ref=f"participant-action-admission:{ACTION}",
                right_carrier_ref="participant-crossing-decision:permit",
            ),
            _egress_case(
                "authorized-projection",
                feature=EGRESS,
                resolver=StaticCrossingResolver(),
                expectation=ParticipantPolicyExpectation.RELEASED,
                idempotency_key=_OP_PROJECTED,
                left_carrier_ref="participant-status-view:source",
                right_carrier_ref="participant-status-view:projected",
            ),
            _egress_case(
                "governed-declassification-release",
                feature=DECLASSIFICATION,
                resolver=StaticCrossingResolver(
                    gate_overrides={"declassification": ParticipantCrossingGateDisposition.PERMIT}
                ),
                expectation=ParticipantPolicyExpectation.RELEASED,
                idempotency_key=_OP_DECLASSIFIED,
                left_carrier_ref="participant-status-view:classified",
                right_carrier_ref="participant-status-view:declassified",
                declassification_schedule_ref="declassification-schedule:cut-0",
            ),
            _egress_case(
                "redaction",
                feature=TRANSFORMATION,
                resolver=TransformedEgressResolver(),
                expectation=ParticipantPolicyExpectation.RELEASED,
                idempotency_key=_OP_REDACTION,
                left_carrier_ref="participant-status-view:source",
                right_carrier_ref="participant-status-view:redacted",
            ),
            _egress_case(
                "participant-directed-inject-delivery",
                feature=INJECT_DELIVERY,
                resolver=StaticCrossingResolver(),
                expectation=ParticipantPolicyExpectation.RELEASED,
                idempotency_key=_OP_INJECT_DELIVERY,
                left_carrier_ref="participant-inject-delivery:requested",
                right_carrier_ref="participant-crossing-decision:delivery",
                operation=ParticipantPolicyOperation.INJECT_DELIVERY,
            ),
            # --- refusal obligations ---
            _ingress_case(
                "denial",
                feature=INGRESS,
                resolver=StaticCrossingResolver(
                    gate_overrides={"participant_authority": ParticipantCrossingGateDisposition.DENY}
                ),
                expectation=ParticipantPolicyExpectation.DENIED,
                idempotency_key=_OP_DENIAL,
                left_carrier_ref=f"participant-action-admission:{ACTION}",
                right_carrier_ref="participant-crossing-decision:deny",
            ),
            _egress_case(
                "withholding",
                feature=EGRESS,
                resolver=StaticCrossingResolver(gate_overrides={"visibility": ParticipantCrossingGateDisposition.DENY}),
                expectation=ParticipantPolicyExpectation.WITHHELD,
                idempotency_key=_OP_WITHHOLDING,
                left_carrier_ref="participant-status-view:requested",
                right_carrier_ref="participant-crossing-decision:withheld",
            ),
            _egress_case(
                "unauthorized-declassification",
                feature=DECLASSIFICATION,
                resolver=StaticCrossingResolver(
                    gate_overrides={"declassification": ParticipantCrossingGateDisposition.DENY}
                ),
                expectation=ParticipantPolicyExpectation.DENIED,
                idempotency_key=_OP_DECLASSIFICATION,
                left_carrier_ref="participant-status-view:classified",
                right_carrier_ref="participant-crossing-decision:unauthorized-declassification",
                declassification_schedule_ref="declassification-schedule:absent",
            ),
            _ingress_case(
                "transformation",
                feature=INGRESS,
                resolver=TransformedActionResolver(deny_fresh=True),
                expectation=ParticipantPolicyExpectation.DENIED,
                idempotency_key=_OP_TRANSFORMATION,
                left_carrier_ref=f"participant-action-admission:{ACTION}",
                right_carrier_ref="participant-action-admission:transformed",
            ),
            _ingress_case(
                "stale-or-revoked-policy",
                feature=INGRESS,
                resolver=StaticCrossingResolver(),
                expectation=ParticipantPolicyExpectation.DENIED,
                idempotency_key=_OP_STALE,
                left_carrier_ref="participant-crossing-decision:state-cut-0",
                right_carrier_ref="participant-crossing-decision:state-cut-advanced",
                setup_requests=(
                    (admission_request(), _OP_STALE),
                    (admission_request(action_instance_id="action-2"), _OP_ADVANCE),
                ),
                # The replay is rejected structurally, before policy evaluation
                # and therefore before the audit boundary.
                expect_audit=False,
            ),
            _egress_case(
                "cross-participant-leakage",
                feature=EGRESS,
                resolver=StaticCrossingResolver(),
                expectation=ParticipantPolicyExpectation.DENIED,
                idempotency_key=_OP_LEAKAGE,
                left_carrier_ref="participant-status-view:sibling-request",
                right_carrier_ref="participant-crossing-decision:audience-forbidden",
                caller=identity(audience_bound=True, audience_scope_ref="audience:blue-operator"),
            ),
            _ingress_case(
                "backend-weakening",
                feature=INGRESS,
                resolver=_UnauthorizedDowngradeResolver(),
                expectation=ParticipantPolicyExpectation.DENIED,
                idempotency_key=_OP_WEAKENING,
                left_carrier_ref="capability-declaration:exact",
                right_carrier_ref="participant-crossing-decision:unauthorized-downgrade",
            ),
            ParticipantPolicyProbeCase(
                obligation="unsupported-capability",
                feature=INTERVENTION,
                binding=_binding(
                    "unsupported-capability",
                    left_carrier_ref="capability-declaration:unsupported",
                    right_carrier_ref="participant-crossing-decision:unsupported",
                ),
                expectation=ParticipantPolicyExpectation.DENIED,
                operation=ParticipantPolicyOperation.SUPERVISORY_CONTROL,
                resolver=StaticCrossingResolver(),
                identity=identity(),
                crossing_evidence=evidence(),
                participant_address=PARTICIPANT,
                episode_id="episode-1",
                idempotency_key=_OP_UNSUPPORTED,
                behavior_specifications={specification.address: specification},
                control_intent=ParticipantHandoffControlIntent(
                    declaration_ref=specification.control_transitions[0].address,
                    episode_id="episode-1",
                    client_correlation_id=_OP_UNSUPPORTED,
                    policy_revision="1.0.0",
                    expected_state_revision=0,
                    provenance_refs=["provenance:crossing-1"],
                    evidence_refs=["evidence:crossing-1"],
                    object_marking_refs=["marking:participant-control"],
                    limitation_refs=["limitation:bounded-reference-runtime"],
                    completion_evidence_ref="evidence:handoff",
                ),
            ),
        )


class OverclaimingPolicyProbeHarness(ParticipantPolicyConformanceHarness):
    """Adversarial harness: declares exact support and permits a required denial.

    The single injected fault is a dishonest deployment policy authority that
    permits a crossing the denial obligation requires to be refused. The shipped
    runtime is unchanged, so a passing result here would mean the probe family
    accepts an overclaim.
    """

    probe_set_digest = "sha256:" + hashlib.sha256(b"asr-535-overclaiming-probe-set/v2").hexdigest()

    def cases(self, target) -> tuple[ParticipantPolicyProbeCase, ...]:
        del target
        return (
            _ingress_case(
                "denial",
                feature=INGRESS,
                resolver=StaticCrossingResolver(),
                expectation=ParticipantPolicyExpectation.DENIED,
                idempotency_key=_OP_OVERCLAIM,
                left_carrier_ref=f"participant-action-admission:{ACTION}",
                right_carrier_ref="participant-crossing-decision:permit",
            ),
        )


class RefusalOnlyPolicyProbeHarness(ParticipantPolicyConformanceHarness):
    """Adversarial harness that only ever fails closed.

    An implementation that refuses everything satisfies every refusal obligation
    while realizing none of the declared capabilities, so refusal-only coverage
    must not establish a declared feature.
    """

    probe_set_digest = "sha256:" + hashlib.sha256(b"asr-535-refusal-only-probe-set/v1").hexdigest()

    def cases(self, target) -> tuple[ParticipantPolicyProbeCase, ...]:
        del target
        return (
            _ingress_case(
                "denial",
                feature=INGRESS,
                resolver=StaticCrossingResolver(
                    gate_overrides={"participant_authority": ParticipantCrossingGateDisposition.DENY}
                ),
                expectation=ParticipantPolicyExpectation.DENIED,
                idempotency_key=_OP_DENIAL,
                left_carrier_ref=f"participant-action-admission:{ACTION}",
                right_carrier_ref="participant-crossing-decision:deny",
            ),
        )


__all__ = (
    "ALL_POLICY_FEATURES",
    "PROBED_POLICY_FEATURES",
    "OverclaimingPolicyProbeHarness",
    "ParticipantPolicyConformanceHarness",
    "RefusalOnlyPolicyProbeHarness",
)
