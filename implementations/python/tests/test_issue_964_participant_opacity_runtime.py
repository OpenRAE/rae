"""SEM-231/RUN-319 bounded participant-opacity runtime enforcement."""

from __future__ import annotations

from dataclasses import replace

import pytest
from participant_crossing_fixtures import (
    PARTICIPANT as CROSSING_PARTICIPANT,
)
from participant_crossing_fixtures import (
    StaticCrossingResolver,
    action_plane,
    admit,
    evidence,
    identity,
    policy_capable_target,
)
from raes_contracts.behavioral_relation_profiles import (
    load_behavioral_relation_profile,
)
from raes_contracts.behavioral_relations import (
    load_behavioral_relation_catalog,
    load_behavioral_relation_catalog_revision,
)
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts.base import BehavioralClaimBindingModel
from raes_contracts.contracts.participant_crossing import (
    ParticipantCrossingGateDisposition,
    ParticipantOpacityObservationInventoryModel,
    ParticipantOpacityObservationSurfaceModel,
    ParticipantOpacityRuntimeEnforcementBindingModel,
    ParticipantOpacityRuntimeSupportModel,
)
from raes_contracts.participant_opacity_runtime import (
    validate_participant_opacity_runtime_enforcement,
)
from raes_contracts.runtime_state import OperationState
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import LocalControlPlaneStore
from raes_runtime.participant_crossing_mediation import (
    ParticipantCrossingIntent,
    ParticipantCrossingPolicyResolution,
)

PROFILE_ID = "participant-opacity-runtime-reference-v1"
PARTICIPANT = "participant.behavior.red-agent"
AUDIENCE = "audience:red-operator"


def _surface(
    channel: str,
    suffix: str,
    owner: str,
    *,
    opportunity: bool = False,
    timing: bool = False,
    unreachable: bool = False,
) -> ParticipantOpacityObservationSurfaceModel:
    return ParticipantOpacityObservationSurfaceModel.model_validate(
        {
            "surface_ref": f"participant-opacity-surface:{suffix}",
            "profile_channel": channel,
            "owner_ref": owner,
            "disposition": "unreachable" if unreachable else "mediated",
            "occurrence_treatment": "not-applicable" if unreachable else "observable",
            "content_treatment": "not-applicable" if unreachable else "projected",
            "projection_ref": "participant-opacity-observation:runtime-reference-v1",
            "projection_revision": "rev1",
            "order_basis_ref": "participant-opacity-order:logical-crossing-v1",
            "order_basis_revision": "rev1",
            **(
                {
                    "opportunity_basis_ref": "participant-opacity-opportunity:crossing-v1",
                    "opportunity_basis_revision": "rev1",
                }
                if opportunity
                else {}
            ),
            **(
                {
                    "timing_bucket_ref": "participant-opacity-timing:logical-bucket-v1",
                    "timing_bucket_revision": "rev1",
                }
                if timing
                else {}
            ),
        }
    )


def _inventory() -> ParticipantOpacityObservationInventoryModel:
    surfaces = (
        _surface("action-availability", "action-ingress", "runtime.participant-control:admit-action"),
        _surface(
            "decision",
            "action-decision-selection",
            "runtime.participant-crossing:decision-surface-selection",
        ),
        _surface(
            "action-availability",
            "autonomous-scheduler-action",
            "runtime.participant-scheduler:autonomous-action",
        ),
        _surface("decision", "supervisor-control", "runtime.participant-control:supervisor-occurrence"),
        _surface(
            "participant-state",
            "episode-lifecycle",
            "runtime.participant-episode:lifecycle",
            unreachable=True,
        ),
        _surface(
            "participant-state",
            "execution-lifecycle-readback",
            "runtime.participant-execution-service:lifecycle-readback",
            unreachable=True,
        ),
        _surface(
            "participant-state",
            "status-view",
            "runtime.participant-retrieval:status-view",
            unreachable=True,
        ),
        _surface(
            "participant-state",
            "history-view",
            "runtime.participant-retrieval:history-view",
            unreachable=True,
        ),
        _surface(
            "participant-state",
            "context-view",
            "runtime.participant-retrieval:context-view",
            unreachable=True,
        ),
        _surface(
            "payload",
            "projected-payload",
            "runtime.participant-retrieval:projection-serialization",
            unreachable=True,
        ),
        _surface(
            "delivery",
            "directed-inject",
            "runtime.participant-retrieval:directed-inject",
            unreachable=True,
        ),
        _surface(
            "delivery",
            "delivery-failure-omission",
            "runtime.participant-crossing:delivery-status-opportunity",
            opportunity=True,
        ),
        _surface("decision", "operation-status-error", "runtime.control-plane:operation-status-error"),
        _surface("retry", "retry-replay", "runtime.participant-crossing:idempotency-replay"),
        _surface(
            "latency",
            "logical-timing-bucket",
            "runtime.time-model:logical-bucket",
            timing=True,
        ),
        _surface("order", "logical-causal-order", "runtime.participant-crossing:logical-causal-order"),
        _surface(
            "policy-release",
            "policy-release-effects",
            "runtime.participant-crossing:policy-release-effects",
        ),
        _surface(
            "participant-state",
            "authorized-evidence-audit-read",
            "runtime.control-plane:administrative-evidence-audit-read",
            unreachable=True,
        ),
        _surface(
            "action-availability",
            "native-backend-direct-use",
            "runtime.backend-calls:direct-native-adapter",
            unreachable=True,
        ),
    )
    draft = ParticipantOpacityObservationInventoryModel(
        inventory_ref="participant-opacity-inventory:runtime-reference-v1",
        inventory_revision="rev1",
        observer_ref=PARTICIPANT,
        audience_ref=AUDIENCE,
        surfaces=surfaces,
    )
    return draft


def _binding() -> ParticipantOpacityRuntimeEnforcementBindingModel:
    profile = load_behavioral_relation_profile(PROFILE_ID)
    inventory = _inventory()
    initial_information_digest = canonical_json_digest(
        {"initial_information": "participant-opacity-runtime-reference-v1"}
    )
    normalized_observation_digest = canonical_json_digest(
        {
            "action_availability": "denied",
            "decision_content": "participant-opacity-contained",
            "delivery": "withheld",
            "latency": "logical-bucket:contained",
            "observation": "uniform-denial",
            "payload": "not-released",
        }
    )
    claim = BehavioralClaimBindingModel(
        taxonomy_id=profile.taxonomy_id,
        taxonomy_revision=profile.taxonomy_revision,
        relation_id=profile.relation_id,
        subject=PARTICIPANT,
        left_carrier_ref=profile.left_carrier_ref,
        observation_projection_ref=profile.observation_projection_ref,
        observation_projection_revision=profile.observation_projection_revision,
        relation_parameter_profile_ref=profile.profile_id,
        relation_parameter_profile_revision=profile.profile_revision,
        quantifier_scope="finite-cases",
        evidence_scope="finite",
        assurance_axis="runtime-enforcement",
        assurance_status="enforced",
        evidence_boundary="One exact finite reference-runtime profile and complete mediated surface inventory.",
        evidence_refs=["evidence:participant-opacity-runtime-reference-v1"],
        limitations=["limitation:bounded-reference-runtime"],
        explicit_non_claims=["No backend realization or general opacity is established."],
    )
    return ParticipantOpacityRuntimeEnforcementBindingModel(
        taxonomy_id=profile.taxonomy_id,
        taxonomy_revision=profile.taxonomy_revision,
        relation_id=profile.relation_id,
        profile_id=profile.profile_id,
        profile_revision=profile.profile_revision,
        profile_digest=profile.canonical_digest,
        predicate_ref=profile.parameters.secret.predicate_ref,
        predicate_revision=profile.parameters.secret.predicate_revision,
        carrier_ref=profile.left_carrier_ref,
        carrier_digest=canonical_json_digest(
            {
                "carrier_ref": profile.left_carrier_ref,
                "initial_information_digest": initial_information_digest,
                "points": [
                    "possible-point:runtime-reference-protected",
                    "possible-point:runtime-reference-complement",
                ],
                "normalized_observation_digest": normalized_observation_digest,
            }
        ),
        materializer_ref="participant-opacity-materializer:runtime-reference-v1",
        materializer_revision="rev1",
        materializer_digest=canonical_json_digest({"materializer": "runtime-reference-v1"}),
        observation_inventory_ref=inventory.inventory_ref,
        observation_inventory_revision=inventory.inventory_revision,
        observation_inventory_digest=inventory.canonical_digest,
        enforcement_rule_ref="participant-opacity-enforcement:crossing-containment-v1",
        enforcement_rule_revision="rev1",
        enforcement_rule_digest=canonical_json_digest({"rule": "crossing-containment-v1"}),
        state_cut_ref=profile.parameters.horizon.cut_ref,
        state_cut_revision=profile.parameters.horizon.cut_revision,
        memory_ref=profile.parameters.memory.memory_ref,
        memory_revision=profile.parameters.memory.memory_revision,
        release_ref=profile.parameters.release.schedule_ref,
        release_revision=profile.parameters.release.schedule_revision,
        assurance_axis="runtime-enforcement",
        claim=claim,
        evidence_refs=["evidence:participant-opacity-runtime-reference-v1"],
        limitations=["limitation:bounded-reference-runtime"],
        explicit_non_claims=["No backend realization or general opacity is established."],
    )


def _support(
    binding: ParticipantOpacityRuntimeEnforcementBindingModel | None = None,
    *,
    inventory: ParticipantOpacityObservationInventoryModel | None = None,
) -> ParticipantOpacityRuntimeSupportModel:
    binding = _binding() if binding is None else binding
    inventory = _inventory() if inventory is None else inventory
    return ParticipantOpacityRuntimeSupportModel(
        binding=binding,
        observation_inventory=inventory,
        predicate_positive_case_ref="possible-point:runtime-reference-protected",
        predicate_negative_case_ref="possible-point:runtime-reference-complement",
        initial_information_digest=canonical_json_digest(
            {"initial_information": "participant-opacity-runtime-reference-v1"}
        ),
        normalized_observation_digest=canonical_json_digest(
            {
                "action_availability": "denied",
                "decision_content": "participant-opacity-contained",
                "delivery": "withheld",
                "latency": "logical-bucket:contained",
                "observation": "uniform-denial",
                "payload": "not-released",
            }
        ),
    )


def test_exact_runtime_profile_and_complete_inventory_are_admitted() -> None:
    binding = _binding()

    admitted = validate_participant_opacity_runtime_enforcement(
        binding,
        support=_support(binding),
        participant_address=PARTICIPANT,
        audience_scope_ref=AUDIENCE,
    )

    assert admitted.assurance_axis == "runtime-enforcement"
    assert admitted.claim.assurance_status == "enforced"
    assert admitted.observation_inventory_digest == _inventory().canonical_digest


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("profile_digest", "profile digest"),
        ("inventory_digest", "inventory digest"),
        ("participant", "observer"),
    ],
)
def test_stale_or_cross_observer_runtime_binding_fails_closed(
    mutation: str,
    message: str,
) -> None:
    binding = _binding()
    support = _support(binding)
    participant = PARTICIPANT
    if mutation == "profile_digest":
        binding = binding.model_copy(update={"profile_digest": canonical_json_digest({"stale": True})})
        support = support.model_copy(update={"binding": binding})
    elif mutation == "inventory_digest":
        binding = binding.model_copy(update={"observation_inventory_digest": canonical_json_digest({"stale": True})})
        support = support.model_copy(update={"binding": binding})
    else:
        participant = "participant.behavior.other"

    with pytest.raises(ValueError, match=message):
        validate_participant_opacity_runtime_enforcement(
            binding,
            support=support,
            participant_address=participant,
            audience_scope_ref=AUDIENCE,
        )


def test_missing_claimed_channel_and_active_probe_bypass_fail_closed() -> None:
    binding = _binding()
    inventory = _inventory()
    without_delivery = inventory.model_copy(
        update={"surfaces": tuple(surface for surface in inventory.surfaces if surface.profile_channel != "delivery")}
    )
    missing_delivery = binding.model_copy(
        update={
            "observation_inventory_digest": without_delivery.canonical_digest,
        }
    )
    missing_support = _support(missing_delivery, inventory=without_delivery)

    with pytest.raises(ValueError, match="delivery"):
        validate_participant_opacity_runtime_enforcement(
            missing_delivery,
            support=missing_support,
            participant_address=PARTICIPANT,
            audience_scope_ref=AUDIENCE,
        )

    active_probe = next(surface for surface in inventory.surfaces if surface.profile_channel == "action-availability")
    bypassed = active_probe.model_copy(
        update={
            "disposition": "unsupported",
            "limitation_ref": "limitation:unmediated-active-probe",
        }
    )
    bypass_inventory = inventory.model_copy(
        update={"surfaces": tuple(bypassed if surface is active_probe else surface for surface in inventory.surfaces)}
    )
    bypass_binding = binding.model_copy(
        update={
            "observation_inventory_digest": bypass_inventory.canonical_digest,
        }
    )
    bypass_support = _support(bypass_binding, inventory=bypass_inventory)

    with pytest.raises(ValueError, match="unsupported"):
        validate_participant_opacity_runtime_enforcement(
            bypass_binding,
            support=bypass_support,
            participant_address=PARTICIPANT,
            audience_scope_ref=AUDIENCE,
        )


def test_coarse_channel_coverage_without_every_concrete_surface_fails_closed() -> None:
    binding = _binding()
    inventory = _inventory()
    incomplete = inventory.model_copy(
        update={
            "surfaces": tuple(
                surface
                for surface in inventory.surfaces
                if surface.surface_ref != "participant-opacity-surface:history-view"
            )
        }
    )
    changed = binding.model_copy(
        update={
            "observation_inventory_digest": incomplete.canonical_digest,
        }
    )
    changed_support = _support(changed, inventory=incomplete)

    with pytest.raises(ValueError, match="missing concrete surfaces"):
        validate_participant_opacity_runtime_enforcement(
            changed,
            support=changed_support,
            participant_address=PARTICIPANT,
            audience_scope_ref=AUDIENCE,
        )


def test_omission_and_logical_timing_require_declared_bases() -> None:
    binding = _binding()
    inventory = _inventory()
    delivery = next(surface for surface in inventory.surfaces if surface.opportunity_basis_ref is not None)
    no_opportunity = delivery.model_copy(update={"opportunity_basis_ref": None, "opportunity_basis_revision": None})
    latency = next(surface for surface in inventory.surfaces if surface.profile_channel == "latency")
    no_bucket = latency.model_copy(update={"timing_bucket_ref": None, "timing_bucket_revision": None})

    for changed, message in ((no_opportunity, "opportunity"), (no_bucket, "timing bucket")):
        changed_inventory = inventory.model_copy(
            update={
                "surfaces": tuple(
                    changed if surface.surface_ref == changed.surface_ref else surface for surface in inventory.surfaces
                )
            }
        )
        changed_binding = binding.model_copy(
            update={
                "observation_inventory_digest": changed_inventory.canonical_digest,
            }
        )
        changed_support = _support(changed_binding, inventory=changed_inventory)
        with pytest.raises(ValueError, match=message):
            validate_participant_opacity_runtime_enforcement(
                changed_binding,
                support=changed_support,
                participant_address=PARTICIPANT,
                audience_scope_ref=AUDIENCE,
            )


def test_catalog_preserves_runtime_assurance_while_extending_backend_axes() -> None:
    catalog = load_behavioral_relation_catalog()
    relation = catalog.relations["participant-predicate-opacity"]
    historical = load_behavioral_relation_catalog_revision("rev10").relations["participant-predicate-opacity"]

    assert catalog.taxonomy_revision == "rev12"
    assert relation.assurance.runtime_enforcement_status == "partial"
    assert relation.assurance.backend_declaration_status == "declared"
    assert relation.assurance.backend_realization_status == "partial"
    assert relation.assurance.backend_conformance_status == "bounded"
    assert historical.assurance.backend_realization_status == "not-realized"


class _OpacityResolver(StaticCrossingResolver):
    def __init__(
        self,
        *,
        gate_overrides: dict[str, ParticipantCrossingGateDisposition] | None = None,
        include_claim: bool = True,
        omit_route_binding: bool = False,
    ) -> None:
        super().__init__(gate_overrides=gate_overrides)
        self.include_claim = include_claim
        self.omit_route_binding = omit_route_binding
        self.binding = _binding()
        self.support = _support(self.binding)

    def resolve(
        self,
        intent: ParticipantCrossingIntent,
        snapshot: object,
    ) -> ParticipantCrossingPolicyResolution:
        resolution = super().resolve(intent, snapshot)
        return replace(
            resolution,
            opacity_enforcement=(self.binding if self.include_claim and not self.omit_route_binding else None),
        )

    def validation_context(self, snapshot: object, participant_address: str):
        context = super().validation_context(snapshot, participant_address)
        return replace(
            context,
            opacity_enforcement_supports=(self.support,) if self.include_claim else (),
        )


def _opacity_plane(resolver: _OpacityResolver):
    return action_plane(
        resolver,
        target=policy_capable_target(
            "participant_ingress_admission",
            "participant_egress_projection",
            "participant_transformation",
        ),
    )


def test_runtime_decision_durably_owns_safe_opacity_binding() -> None:
    resolver = _OpacityResolver()
    plane = _opacity_plane(resolver)

    receipt = admit(plane, idempotency_key="opacity-action")

    assert receipt.accepted is True
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    decision = plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT][1]["occurrence"]
    binding = decision["opacity_enforcement"]
    assert binding["assurance_axis"] == "runtime-enforcement"
    assert binding["claim"]["evidence_scope"] == "finite"
    assert "observation_inventory" not in binding
    assert binding["observation_inventory_ref"] == "participant-opacity-inventory:runtime-reference-v1"
    encoded = str(binding).lower()
    assert "secret_holds" not in encoded
    assert "possible_world" not in encoded
    assert "information_cell" not in encoded
    assert "belief_state" not in encoded


def test_exact_retry_reuses_opacity_decision_and_changed_binding_conflicts() -> None:
    resolver = _OpacityResolver()
    plane = _opacity_plane(resolver)

    first = admit(plane, idempotency_key="opacity-retry")
    retry = admit(plane, idempotency_key="opacity-retry")
    assert retry.operation_id == first.operation_id
    assert len(plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT]) == 2

    resolver.binding = resolver.binding.model_copy(
        update={
            "enforcement_rule_digest": canonical_json_digest({"rule": "changed"}),
        }
    )
    with pytest.raises(ValueError, match="different semantics"):
        admit(plane, idempotency_key="opacity-retry")


def test_governed_egress_normalizes_to_withheld_opportunity_before_return() -> None:
    plane = _opacity_plane(_OpacityResolver())
    bound_identity = identity(audience_bound=True)
    crossing_evidence = evidence()

    with pytest.raises(PermissionError, match="not permitted"):
        plane.get_participant_status_view(
            CROSSING_PARTICIPANT,
            identity=bound_identity,
            crossing_evidence=crossing_evidence,
            idempotency_key="opacity-egress",
        )

    stages = [item["occurrence"]["stage"] for item in plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT]]
    assert stages == [
        "requested",
        "decided",
        "delivery-attempted",
    ]
    assert plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT][-1]["occurrence"]["disposition"] == (
        "withheld"
    )
    assert all(
        "opacity_enforcement" not in item["occurrence"]
        or item["occurrence"]["opacity_enforcement"]["assurance_axis"] == "runtime-enforcement"
        for item in plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT]
    )


def test_denied_egress_records_observable_denial_without_returning_a_view() -> None:
    resolver = _OpacityResolver(gate_overrides={"visibility": ParticipantCrossingGateDisposition.DENY})
    plane = _opacity_plane(resolver)
    bound_identity = identity(audience_bound=True)
    crossing_evidence = evidence()

    with pytest.raises(PermissionError, match="not permitted"):
        plane.get_participant_status_view(
            CROSSING_PARTICIPANT,
            identity=bound_identity,
            crossing_evidence=crossing_evidence,
            idempotency_key="opacity-withheld",
        )

    history = plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT]
    assert [item["occurrence"]["stage"] for item in history] == [
        "requested",
        "decided",
        "delivery-attempted",
    ]
    assert history[1]["occurrence"]["disposition"] == "deny"
    assert history[1]["occurrence"]["opacity_enforcement"]["assurance_axis"] == ("runtime-enforcement")
    assert history[2]["occurrence"]["disposition"] == "withheld"


def test_secret_dependent_policy_outcomes_are_normalized_to_the_same_observation() -> None:
    allowed = _opacity_plane(_OpacityResolver())
    denied = _opacity_plane(
        _OpacityResolver(gate_overrides={"action_admission": ParticipantCrossingGateDisposition.DENY})
    )

    allowed_receipt = admit(allowed, idempotency_key="opacity-secret-true")
    denied_receipt = admit(denied, idempotency_key="opacity-secret-false")

    assert allowed_receipt.accepted is denied_receipt.accepted is True
    assert allowed.get_operation(allowed_receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    assert denied.get_operation(denied_receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    allowed_decision = allowed.snapshot.participant_crossing_history[CROSSING_PARTICIPANT][1]["occurrence"]
    denied_decision = denied.snapshot.participant_crossing_history[CROSSING_PARTICIPANT][1]["occurrence"]
    for decision in (allowed_decision, denied_decision):
        assert decision["disposition"] == "deny"
    assert allowed_decision["gates"] == denied_decision["gates"]


def test_route_local_binding_omission_cannot_bypass_active_runtime_support() -> None:
    plane = _opacity_plane(_OpacityResolver(omit_route_binding=True))

    receipt = admit(plane, idempotency_key="opacity-route-bypass")

    assert receipt.accepted is True
    assert plane.get_operation(receipt.operation_id).state is OperationState.FAILED  # type: ignore[union-attr]
    decision = plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT][1]["occurrence"]
    assert decision["opacity_enforcement"]["assurance_axis"] == "runtime-enforcement"


def test_disclosed_weakening_removes_positive_opacity_claim() -> None:
    plane = _opacity_plane(_OpacityResolver(include_claim=False))

    receipt = admit(plane, idempotency_key="opacity-weakened")

    assert receipt.accepted is True
    decision = plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT][1]["occurrence"]
    assert "opacity_enforcement" not in decision


def test_restart_requires_the_exact_persisted_opacity_context(tmp_path) -> None:
    store = LocalControlPlaneStore(tmp_path / "opacity-control-plane")
    first_resolver = _OpacityResolver()
    first = action_plane(
        first_resolver,
        target=policy_capable_target("participant_ingress_admission"),
        store=store,
    )
    admit(first, idempotency_key="opacity-restart")
    first.close()

    restarted_resolver = _OpacityResolver()
    restarted_resolver.subjects = list(first_resolver.subjects)
    restarted_resolver.evidence_refs = set(first_resolver.evidence_refs)
    restarted = RuntimeControlPlane(
        policy_capable_target("participant_ingress_admission"),
        store=LocalControlPlaneStore(tmp_path / "opacity-control-plane"),
        crossing_policy_resolver=restarted_resolver,
        enforce_final_sink_flow_control=False,
    )
    assert restarted.snapshot.participant_crossing_history[CROSSING_PARTICIPANT]
    restarted.close()

    stale = _OpacityResolver()
    stale.subjects = list(first_resolver.subjects)
    stale.evidence_refs = set(first_resolver.evidence_refs)
    stale.binding = stale.binding.model_copy(
        update={"enforcement_rule_digest": canonical_json_digest({"rule": "stale"})}
    )
    stale.support = _support(stale.binding)
    restart_target = policy_capable_target("participant_ingress_admission")
    restart_store = LocalControlPlaneStore(tmp_path / "opacity-control-plane")
    with pytest.raises(ValueError, match="restart context"):
        RuntimeControlPlane(
            restart_target,
            store=restart_store,
            crossing_policy_resolver=stale,
            enforce_final_sink_flow_control=False,
        )


def test_runtime_reset_does_not_erase_retained_opacity_history() -> None:
    plane = _opacity_plane(_OpacityResolver())
    admit(plane, idempotency_key="opacity-before-reset")
    before = tuple(plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT])

    receipt = plane.reset_participant_episode(
        CROSSING_PARTICIPANT,
        episode_id="episode-1",
        reason="bounded test reset",
        idempotency_key="opacity-reset",
    )

    assert receipt.accepted is True
    assert tuple(plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT]) == before
    admit(plane, idempotency_key="opacity-after-reset")
    assert len(plane.snapshot.participant_crossing_history[CROSSING_PARTICIPANT]) > len(before)
