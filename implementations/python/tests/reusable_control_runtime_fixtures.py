"""Installed policy and live-cut owners for reusable runtime tests."""

from dataclasses import dataclass, field

from mixed_control_rev1_scenarios import edge, parse, rev1_scenario
from raes_backend_stubs.stubs import create_stub_target
from raes_processor.compiler import compile_runtime_model
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_security import (
    ControlPlaneIdentity,
    ControlPlaneRole,
    ParticipantControlSubjectBinding,
)

PARTICIPANT = "participant.behavior.red-agent"
SPEC = "participant.behavior-specification.controlled-red"


@dataclass
class CutOwner:
    orders: dict[str, int] = field(default_factory=dict)
    revoked: set[str] = field(default_factory=set)

    def resolve_cut(self, policy, intent, snapshot):
        from raes_runtime.participant_control_runtime import ParticipantControlLiveCut

        return ParticipantControlLiveCut(
            request_ref="episode-admission" if intent is None else intent.client_correlation_id,
            effective_order=0 if intent is None else self.orders[intent.client_correlation_id],
            active_authority_basis_refs=sorted(
                {basis for state in policy.states for basis in state.authority_basis_refs} - self.revoked
            ),
            authorized_scope_refs=sorted({ref for state in policy.states for ref in state.scope_refs}),
            evidence_refs=["evidence:episode-admission"] if intent is None else intent.evidence_refs,
        )


def configured_plane(*, owner=None, store=None, form="reusable-policy", target=None, **options):
    from raes_runtime.participant_control_runtime import MixedControlRuntimeBinding

    payload = rev1_scenario(form=form)
    payload["behavior_specifications"]["controlled-red"]["mixed_control"]["permitted_transitions"]["cancel"] = edge(
        "cancellation", "autonomous", "autonomous", "red-team"
    )
    model = compile_runtime_model(parse(payload))
    owner = owner or CutOwner()
    plane = RuntimeControlPlane(
        target or create_stub_target(),
        store=store,
        behavior_specifications=model.behavior_specifications,
        mixed_control=MixedControlRuntimeBinding(model=model, resolver=owner),
        **options,
    )
    return plane, owner


def identity():
    return ControlPlaneIdentity(
        identity="operator",
        roles=frozenset({ControlPlaneRole.OPERATOR}),
        target_name="stub",
        participant_control_subjects=(
            ParticipantControlSubjectBinding(PARTICIPANT, PARTICIPANT),
            ParticipantControlSubjectBinding(PARTICIPANT, "participant.behavior.supervisor-agent"),
        ),
    )


def handoff(plane, owner, edge, *, revision, head, order, key, episode="episode-1", step=None):
    from raes_runtime.participant_control_intents import ParticipantHandoffControlIntent

    policy = plane._behavior_specifications[SPEC].mixed_control_policy
    transition = next(item for item in policy.permitted_transitions if item.transition_id == edge)
    owner.orders[key] = order
    return ParticipantHandoffControlIntent(
        declaration_ref=transition.address,
        episode_id=episode,
        client_correlation_id=key,
        policy_revision=policy.policy_revision,
        expected_state_revision=revision,
        provenance_refs=["provenance:test"],
        evidence_refs=[f"completion:{key}"],
        object_marking_refs=["marking:test"],
        limitation_refs=["limitation:none"],
        completion_evidence_ref=f"completion:{key}",
        application={
            "semantics": policy.semantics,
            "policy_ref": policy.address,
            "prior_state_ref": transition.from_state_address,
            "expected_history_head": head,
            "effective_order": order,
            "script_step_ref": step,
        },
    )
