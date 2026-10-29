"""Bounded public execution cases. This driver never imports model decisions."""

from dataclasses import replace

from crossing_runtime_observer import capture_call, crossing_binding
from participant_crossing_fixtures import (
    PARTICIPANT,
    StaticCrossingResolver,
    TransformedActionResolver,
    action_plane,
    admission_request,
    admit,
    evidence,
    identity,
    policy_capable_target,
)
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts.participant_crossing import ParticipantCrossingGateDisposition as Gate
from raes_contracts.contracts.participant_crossing import ParticipantCrossingOperation as Operation


class DeclassificationResolver(TransformedActionResolver):
    def __init__(self, permitted):
        super().__init__()
        self.permitted = permitted

    def resolve_operation(self, *args):
        resolved = super().resolve_operation(*args)
        return replace(
            resolved,
            required_operation=Operation.DECLASSIFICATION,
            gates=replace(resolved.gates, declassification=Gate.PERMIT if self.permitted else Gate.DENY),
            transformation=replace(resolved.transformation, declassification_basis_ref="authority:red-team"),
        )


def advance_policy(resolver, binding):
    old = resolver.policy
    resolver.policy = old.model_copy(
        update={
            "decision_cut_ref": binding.policy_cuts[1],
            "policy_revision": old.policy_revision + ".p1",
            "policy_decision_ref": old.policy_decision_ref + ".p1",
        }
    )
    context = resolver.validation_context
    resolver.validation_context = lambda snapshot, participant: replace(
        context(snapshot, participant), policies=(old, resolver.policy)
    )


def ingress_case(input_class, cut="p0"):
    resolver = (
        TransformedActionResolver()
        if input_class == "transform"
        else DeclassificationResolver(cut == "p1")
        if input_class == "declassify"
        else StaticCrossingResolver(gate_overrides={"action_admission": Gate.DENY})
        if input_class == "forbidden"
        else StaticCrossingResolver()
    )
    target = (
        create_stub_target()
        if input_class == "unsupported"
        else policy_capable_target(
            "participant_ingress_admission", "participant_transformation", "participant_declassification"
        )
    )
    plane = action_plane(resolver, target=target)
    binding = crossing_binding()
    with plane:
        return capture_call(
            plane,
            lambda: admit(plane),
            binding,
            input_class=input_class,
            cut=cut,
            policy_advance=(lambda: advance_policy(resolver, binding)) if cut == "p1" else None,
        )


def replay_case(mode):
    resolver = StaticCrossingResolver(gate_overrides={"action_admission": Gate.DENY})
    plane = action_plane(resolver)
    binding = crossing_binding()
    with plane:
        first = capture_call(plane, lambda: admit(plane), binding, input_class="forbidden")
        request = admission_request(action_instance_id="different") if mode == "changed-input" else admission_request()
        retry = capture_call(
            plane,
            lambda: admit(plane, request=request),
            binding,
            input_class="forbidden",
            policy_advance=(lambda: advance_policy(resolver, binding)) if mode == "later-cut" else None,
            cut="p1" if mode == "later-cut" else "p0",
        )
    return first, retry


def backend_failure_case():
    from raes_contracts.runtime_state import ApplyResult

    target = policy_capable_target()
    target.participant_runtime.admit_action = lambda request, snapshot: ApplyResult(success=False, snapshot=snapshot)
    plane = action_plane(StaticCrossingResolver(), target=target)
    with plane:
        return capture_call(plane, lambda: admit(plane), crossing_binding(), input_class="plain")


def egress_case(permitted, *, store=None):
    from raes_contracts.contracts import ParticipantFlowFinalDisposition
    from sem233_flow_sink_fixtures import FlowSinkToggles, deny_resolver, permit_resolver, sem233_plane

    resolver = (
        permit_resolver()
        if permitted
        else deny_resolver(FlowSinkToggles(capability_disposition=ParticipantFlowFinalDisposition.DENY))
    )
    plane = sem233_plane(
        resolver,
        target=policy_capable_target("participant_egress_projection", "participant_transformation"),
        store=store,
    )
    binding = crossing_binding(controller="runtime.control-plane.participant-retrieval")
    with plane:
        return capture_call(
            plane,
            lambda: plane.get_participant_status_view(
                PARTICIPANT,
                identity=identity(audience_bound=True),
                crossing_evidence=evidence(),
                idempotency_key="mapping-egress",
            ),
            binding,
            input_class="plain",
            entry_point="get_participant_status_view",
        )


def effect_case():
    from governed_effect_runtime_fixtures import EffectResolver, effect_plane

    plane, owner = effect_plane(EffectResolver(decision="deny"))
    caller = identity(audience_bound=True)
    with plane:
        parent = capture_call(
            plane, lambda: admit(plane, control_identity=caller), crossing_binding(), input_class="plain"
        )
        effect = capture_call(
            plane,
            lambda: plane.dispatch_participant_control_effects(PARTICIPANT, identity=caller),
            crossing_binding(),
            input_class="plain",
            entry_point="dispatch_participant_control_effects",
        )
    return parent, effect, owner


def v2_case(context):
    import test_sem_220_participant_decision_surface_v2_runtime as cases

    plane, delivered, selected, delivery = cases._governed_selection_case()
    caller = (
        None
        if context == "missing-identity"
        else identity(participant_address="participant.other" if context == "wrong-participant" else cases.PARTICIPANT)
    )
    selection = cases._selection_for(delivered)
    if context == "stale-epoch":
        selection = selection.model_copy(update={"decision_epoch": selection.decision_epoch + 1})
    with plane:
        return capture_call(
            plane,
            lambda: cases._admit_governed_selection(
                plane,
                delivered,
                selected,
                delivery,
                selection=selection,
                identity=caller,
                crossing_evidence=evidence(),
            ),
            crossing_binding(participant=cases.PARTICIPANT, episode=cases.EPISODE),
            input_class="plain",
            entry_point="admit_participant_decision_surface_selection_v2",
        )


def collect_cases():
    from implementations.formal.participant_crossing.runtime_mapping import assess

    observations = {
        f"ingress/{item}/{cut}": ingress_case(item, cut)
        for item in ("plain", "transform", "declassify", "unsupported", "forbidden")
        for cut in ("p0", "p1")
    }
    for mode in ("same-cut", "later-cut", "changed-input"):
        first, retry = replay_case(mode)
        observations[f"replay/{mode}/initial"] = first
        observations[f"replay/{mode}/retry"] = retry
    observations["ingress/backend-failure"] = backend_failure_case()
    for permitted in (False, True):
        observations[f"egress/{'permit' if permitted else 'deny'}"] = egress_case(permitted)
    parent, effect, _ = effect_case()
    observations.update({"provider/parent": parent, "provider/owner": effect})
    for context in ("valid", "missing-identity", "wrong-participant", "stale-epoch"):
        observations[f"v2/{context}"] = v2_case(context)
    reports = {name: assess(observed) for name, observed in observations.items()}
    if any(report["runtime_safety_issues"] for report in reports.values()):
        raise ValueError("runtime safety checks failed independently of finite-model compatibility")
    return reports


if __name__ == "__main__":
    import argparse

    from crossing_model_fixtures import ROOT
    from implementations.formal.participant_crossing import runtime_mapping_export

    parser = argparse.ArgumentParser(description="Run the bounded public-call mapping cases.")
    parser.add_argument("--write", action="store_true", help="Publish a new mapping bundle; refuse existing drift.")
    options = parser.parse_args()
    reports = collect_cases()
    (runtime_mapping_export.publish if options.write else runtime_mapping_export.check)(ROOT, reports)
    print("Runtime mapping cases verified; no equivalence or complete realization result.")
