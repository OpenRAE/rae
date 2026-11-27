"""Admission for bounded participant-opacity runtime-enforcement bindings."""

from __future__ import annotations

from .behavioral_authority_errors import unsupported_authority_as_value_error
from .behavioral_relation_profiles import (
    ActiveOpacityStrategyModel,
    BehavioralRelationProfileModel,
    IndividualOpacityObserverModel,
    load_behavioral_relation_profile_revision,
)
from .behavioral_relations import (
    BehavioralRelationCatalogModel,
    load_behavioral_relation_catalog_revision,
    validate_behavioral_claim_binding,
)
from .canonical import canonical_json_digest
from .contracts.participant_crossing import (
    ParticipantOpacityObservationInventoryModel,
    ParticipantOpacityObservationSurfaceModel,
    ParticipantOpacityRuntimeEnforcementBindingModel,
    ParticipantOpacityRuntimeSupportModel,
)

_INVENTORY_REF = "participant-opacity-inventory:runtime-reference-v1"
_INVENTORY_REVISION = "rev1"
_PROJECTION_REF = "participant-opacity-observation:runtime-reference-v1"
_PROJECTION_REVISION = "rev1"
_ORDER_BASIS_REF = "participant-opacity-order:logical-crossing-v1"
_ORDER_BASIS_REVISION = "rev1"
_OPPORTUNITY_BASIS_REF = "participant-opacity-opportunity:crossing-v1"
_OPPORTUNITY_BASIS_REVISION = "rev1"
_TIMING_BUCKET_REF = "participant-opacity-timing:logical-bucket-v1"
_TIMING_BUCKET_REVISION = "rev1"
_POSITIVE_CASE_REF = "possible-point:runtime-reference-protected"
_NEGATIVE_CASE_REF = "possible-point:runtime-reference-complement"
_INITIAL_INFORMATION_DIGEST = canonical_json_digest({"initial_information": "participant-opacity-runtime-reference-v1"})
_NORMALIZED_OBSERVATION = {
    "action_availability": "denied",
    "decision_content": "participant-opacity-contained",
    "delivery": "withheld",
    "latency": "logical-bucket:contained",
    "observation": "uniform-denial",
    "payload": "not-released",
}
_NORMALIZED_OBSERVATION_DIGEST = canonical_json_digest(_NORMALIZED_OBSERVATION)
_CARRIER_DIGEST = canonical_json_digest(
    {
        "carrier_ref": "possible-point-carrier:runtime-reference-v1",
        "initial_information_digest": _INITIAL_INFORMATION_DIGEST,
        "points": [_POSITIVE_CASE_REF, _NEGATIVE_CASE_REF],
        "normalized_observation_digest": _NORMALIZED_OBSERVATION_DIGEST,
    }
)
_MATERIALIZER_REF = "participant-opacity-materializer:runtime-reference-v1"
_MATERIALIZER_REVISION = "rev1"
_MATERIALIZER_DIGEST = canonical_json_digest({"materializer": "runtime-reference-v1"})
_ENFORCEMENT_RULE_REF = "participant-opacity-enforcement:crossing-containment-v1"
_ENFORCEMENT_RULE_REVISION = "rev1"
_ENFORCEMENT_RULE_DIGEST = canonical_json_digest({"rule": "crossing-containment-v1"})

# This is the complete supported concrete surface set for the one reference
# profile. A broad semantic channel without every corresponding runtime route
# is deliberately insufficient for a positive enforcement claim.
_RUNTIME_SURFACE_SUPPORT: dict[str, tuple[str, str, str, str, str, bool, bool]] = {
    "participant-opacity-surface:action-ingress": (
        "action-availability",
        "runtime.participant-control:admit-action",
        "mediated",
        "observable",
        "projected",
        False,
        False,
    ),
    "participant-opacity-surface:action-decision-selection": (
        "decision",
        "runtime.participant-crossing:decision-surface-selection",
        "mediated",
        "observable",
        "projected",
        False,
        False,
    ),
    "participant-opacity-surface:autonomous-scheduler-action": (
        "action-availability",
        "runtime.participant-scheduler:autonomous-action",
        "mediated",
        "observable",
        "projected",
        False,
        False,
    ),
    "participant-opacity-surface:supervisor-control": (
        "decision",
        "runtime.participant-control:supervisor-occurrence",
        "mediated",
        "observable",
        "projected",
        False,
        False,
    ),
    "participant-opacity-surface:episode-lifecycle": (
        "participant-state",
        "runtime.participant-episode:lifecycle",
        "unreachable",
        "not-applicable",
        "not-applicable",
        False,
        False,
    ),
    "participant-opacity-surface:execution-lifecycle-readback": (
        "participant-state",
        "runtime.participant-execution-service:lifecycle-readback",
        "unreachable",
        "not-applicable",
        "not-applicable",
        False,
        False,
    ),
    "participant-opacity-surface:status-view": (
        "participant-state",
        "runtime.participant-retrieval:status-view",
        "unreachable",
        "not-applicable",
        "not-applicable",
        False,
        False,
    ),
    "participant-opacity-surface:history-view": (
        "participant-state",
        "runtime.participant-retrieval:history-view",
        "unreachable",
        "not-applicable",
        "not-applicable",
        False,
        False,
    ),
    "participant-opacity-surface:context-view": (
        "participant-state",
        "runtime.participant-retrieval:context-view",
        "unreachable",
        "not-applicable",
        "not-applicable",
        False,
        False,
    ),
    "participant-opacity-surface:projected-payload": (
        "payload",
        "runtime.participant-retrieval:projection-serialization",
        "unreachable",
        "not-applicable",
        "not-applicable",
        False,
        False,
    ),
    "participant-opacity-surface:directed-inject": (
        "delivery",
        "runtime.participant-retrieval:directed-inject",
        "unreachable",
        "not-applicable",
        "not-applicable",
        False,
        False,
    ),
    "participant-opacity-surface:delivery-failure-omission": (
        "delivery",
        "runtime.participant-crossing:delivery-status-opportunity",
        "mediated",
        "observable",
        "projected",
        True,
        False,
    ),
    "participant-opacity-surface:operation-status-error": (
        "decision",
        "runtime.control-plane:operation-status-error",
        "mediated",
        "observable",
        "projected",
        False,
        False,
    ),
    "participant-opacity-surface:retry-replay": (
        "retry",
        "runtime.participant-crossing:idempotency-replay",
        "mediated",
        "observable",
        "projected",
        False,
        False,
    ),
    "participant-opacity-surface:logical-timing-bucket": (
        "latency",
        "runtime.time-model:logical-bucket",
        "mediated",
        "observable",
        "projected",
        False,
        True,
    ),
    "participant-opacity-surface:logical-causal-order": (
        "order",
        "runtime.participant-crossing:logical-causal-order",
        "mediated",
        "observable",
        "projected",
        False,
        False,
    ),
    "participant-opacity-surface:policy-release-effects": (
        "policy-release",
        "runtime.participant-crossing:policy-release-effects",
        "mediated",
        "observable",
        "projected",
        False,
        False,
    ),
    "participant-opacity-surface:authorized-evidence-audit-read": (
        "participant-state",
        "runtime.control-plane:administrative-evidence-audit-read",
        "unreachable",
        "not-applicable",
        "not-applicable",
        False,
        False,
    ),
    "participant-opacity-surface:native-backend-direct-use": (
        "action-availability",
        "runtime.backend-calls:direct-native-adapter",
        "unreachable",
        "not-applicable",
        "not-applicable",
        False,
        False,
    ),
}


def validate_participant_opacity_runtime_enforcement(
    binding: ParticipantOpacityRuntimeEnforcementBindingModel,
    *,
    support: ParticipantOpacityRuntimeSupportModel,
    participant_address: str,
    audience_scope_ref: str,
    catalog: BehavioralRelationCatalogModel | None = None,
    profile: BehavioralRelationProfileModel | None = None,
) -> ParticipantOpacityRuntimeEnforcementBindingModel:
    """Resolve an exact finite profile and reject incomplete runtime coverage.

    A binding that names an unpackaged revision fails with ``ValueError`` (E3).
    A damaged packaged authority raises ``BehavioralAuthorityArtifactError``.
    """

    with unsupported_authority_as_value_error("participant opacity runtime binding names an unsupported authority"):
        if catalog is None:
            catalog = load_behavioral_relation_catalog_revision(binding.taxonomy_revision)
        if profile is None:
            profile = load_behavioral_relation_profile_revision(binding.profile_id, binding.profile_revision)
    validate_behavioral_claim_binding(binding.claim, catalog=catalog, profile=profile)
    if support.binding != binding:
        raise ValueError("participant opacity runtime support does not match the durable binding")
    _validate_binding_coordinates(binding, support, profile)
    _validate_observer(binding, support, profile, participant_address, audience_scope_ref)
    _validate_inventory(support, profile)
    return binding


def _validate_binding_coordinates(
    binding: ParticipantOpacityRuntimeEnforcementBindingModel,
    support: ParticipantOpacityRuntimeSupportModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    parameters = profile.parameters
    expected = (
        (binding.taxonomy_id, profile.taxonomy_id, "taxonomy id"),
        (binding.taxonomy_revision, profile.taxonomy_revision, "taxonomy revision"),
        (binding.relation_id, profile.relation_id, "relation"),
        (binding.profile_id, profile.profile_id, "profile id"),
        (binding.profile_revision, profile.profile_revision, "profile revision"),
        (binding.profile_digest, profile.canonical_digest, "profile digest"),
        (binding.predicate_ref, parameters.secret.predicate_ref, "predicate ref"),
        (binding.predicate_revision, parameters.secret.predicate_revision, "predicate revision"),
        (binding.carrier_ref, profile.left_carrier_ref, "carrier ref"),
        (binding.carrier_digest, _CARRIER_DIGEST, "carrier digest"),
        (binding.materializer_ref, _MATERIALIZER_REF, "materializer ref"),
        (binding.materializer_revision, _MATERIALIZER_REVISION, "materializer revision"),
        (binding.materializer_digest, _MATERIALIZER_DIGEST, "materializer digest"),
        (binding.enforcement_rule_ref, _ENFORCEMENT_RULE_REF, "enforcement rule ref"),
        (binding.enforcement_rule_revision, _ENFORCEMENT_RULE_REVISION, "enforcement rule revision"),
        (binding.enforcement_rule_digest, _ENFORCEMENT_RULE_DIGEST, "enforcement rule digest"),
        (binding.observation_inventory_ref, _INVENTORY_REF, "inventory ref"),
        (binding.observation_inventory_revision, _INVENTORY_REVISION, "inventory revision"),
        (
            binding.observation_inventory_digest,
            support.observation_inventory.canonical_digest,
            "inventory digest",
        ),
        (binding.state_cut_ref, parameters.horizon.cut_ref, "state cut ref"),
        (binding.state_cut_revision, parameters.horizon.cut_revision, "state cut revision"),
        (binding.memory_ref, parameters.memory.memory_ref, "memory ref"),
        (binding.memory_revision, parameters.memory.memory_revision, "memory revision"),
        (binding.release_ref, parameters.release.schedule_ref, "release ref"),
        (binding.release_revision, parameters.release.schedule_revision, "release revision"),
    )
    for actual, wanted, label in expected:
        if actual != wanted:
            raise ValueError(f"participant opacity runtime {label} does not match the exact profile")
    if binding.claim.assurance_axis != "runtime-enforcement":
        raise ValueError("participant opacity runtime claim must use the runtime-enforcement axis")
    support_coordinates = (
        (support.predicate_positive_case_ref, _POSITIVE_CASE_REF, "predicate-positive case"),
        (support.predicate_negative_case_ref, _NEGATIVE_CASE_REF, "predicate-negative case"),
        (support.initial_information_digest, _INITIAL_INFORMATION_DIGEST, "initial information"),
        (
            support.normalized_observation_digest,
            _NORMALIZED_OBSERVATION_DIGEST,
            "normalized observation",
        ),
    )
    for actual, wanted, label in support_coordinates:
        if actual != wanted:
            raise ValueError(f"participant opacity runtime {label} does not match the enforced normal form")


def _validate_observer(
    binding: ParticipantOpacityRuntimeEnforcementBindingModel,
    support: ParticipantOpacityRuntimeSupportModel,
    profile: BehavioralRelationProfileModel,
    participant_address: str,
    audience_scope_ref: str,
) -> None:
    observer = profile.parameters.observer
    if not isinstance(observer, IndividualOpacityObserverModel):
        raise ValueError("participant opacity runtime profile does not support coalition observers")
    expected = (
        (participant_address, observer.participant_ref, "observer participant"),
        (audience_scope_ref, observer.audience_ref, "observer audience"),
        (support.observation_inventory.observer_ref, observer.participant_ref, "inventory observer"),
        (support.observation_inventory.audience_ref, observer.audience_ref, "inventory audience"),
        (binding.claim.subject, observer.participant_ref, "claim observer"),
    )
    for actual, wanted, label in expected:
        if actual != wanted:
            raise ValueError(f"participant opacity runtime {label} does not match the profile observer")


def _validate_inventory(
    support: ParticipantOpacityRuntimeSupportModel,
    profile: BehavioralRelationProfileModel,
) -> None:
    parameters = profile.parameters
    inventory = support.observation_inventory
    surfaces = inventory.surfaces
    _validate_inventory_identity(inventory)
    declared_channels = _validate_inventory_channels(
        surfaces,
        tuple(parameters.observation.observable_channels),
    )
    _validate_inventory_time_semantics(inventory, profile, declared_channels)
    actual_by_ref = _validate_inventory_surface_set(surfaces)
    _validate_inventory_surface_coordinates(actual_by_ref)
    if isinstance(parameters.strategy, ActiveOpacityStrategyModel) and not any(
        surface.profile_channel == "action-availability" and surface.disposition == "mediated" for surface in surfaces
    ):
        raise ValueError("participant opacity active strategy has an unmediated probe surface")


def _validate_inventory_identity(inventory: ParticipantOpacityObservationInventoryModel) -> None:
    if (
        inventory.inventory_ref,
        inventory.inventory_revision,
    ) != (_INVENTORY_REF, _INVENTORY_REVISION):
        raise ValueError("participant opacity runtime inventory identity does not match the supported declaration")
    unsupported = sorted(surface.surface_ref for surface in inventory.surfaces if surface.disposition == "unsupported")
    if unsupported:
        raise ValueError("participant opacity runtime inventory contains unsupported observation surfaces")


def _validate_inventory_channels(
    surfaces: tuple[ParticipantOpacityObservationSurfaceModel, ...],
    observable_channels: tuple[str, ...],
) -> set[str]:
    declared_channels = set(observable_channels)
    present_channels = {surface.profile_channel for surface in surfaces}
    missing = sorted(declared_channels - present_channels)
    extra = sorted(present_channels - declared_channels)
    if missing:
        raise ValueError("participant opacity runtime inventory is missing claimed channels: " + ", ".join(missing))
    if extra:
        raise ValueError("participant opacity runtime inventory contains undeclared channels: " + ", ".join(extra))
    return declared_channels


def _validate_inventory_time_semantics(
    inventory: ParticipantOpacityObservationInventoryModel,
    profile: BehavioralRelationProfileModel,
    declared_channels: set[str],
) -> None:
    parameters = profile.parameters
    surfaces = inventory.surfaces
    if parameters.time.absence_observable:
        opportunities = [
            surface
            for surface in surfaces
            if surface.profile_channel == "delivery" and surface.disposition == "mediated"
        ]
        if not any(
            (
                surface.opportunity_basis_ref,
                surface.opportunity_basis_revision,
            )
            == (
                parameters.time.opportunity_basis_ref,
                parameters.time.opportunity_basis_revision,
            )
            for surface in opportunities
        ):
            raise ValueError("participant opacity observable omission requires the exact opportunity basis")
    if "latency" in declared_channels:
        latency_surfaces = [surface for surface in surfaces if surface.profile_channel == "latency"]
        if any(surface.timing_bucket_ref is None for surface in latency_surfaces):
            raise ValueError("participant opacity logical latency requires a governed timing bucket")


def _validate_inventory_surface_set(
    surfaces: tuple[ParticipantOpacityObservationSurfaceModel, ...],
) -> dict[str, ParticipantOpacityObservationSurfaceModel]:
    actual_by_ref = {surface.surface_ref: surface for surface in surfaces}
    expected_refs = set(_RUNTIME_SURFACE_SUPPORT)
    actual_refs = set(actual_by_ref)
    missing_surfaces = sorted(expected_refs - actual_refs)
    extra_surfaces = sorted(actual_refs - expected_refs)
    if missing_surfaces:
        raise ValueError(
            "participant opacity runtime inventory is missing concrete surfaces: " + ", ".join(missing_surfaces)
        )
    if extra_surfaces:
        raise ValueError(
            "participant opacity runtime inventory contains unadmitted concrete surfaces: " + ", ".join(extra_surfaces)
        )
    return actual_by_ref


def _validate_inventory_surface_coordinates(
    actual_by_ref: dict[str, ParticipantOpacityObservationSurfaceModel],
) -> None:
    for surface_ref, expected in _RUNTIME_SURFACE_SUPPORT.items():
        channel, owner, disposition, occurrence, content, opportunity, timing = expected
        surface = actual_by_ref[surface_ref]
        coordinates = (
            surface.profile_channel,
            surface.owner_ref,
            surface.disposition,
            surface.occurrence_treatment,
            surface.content_treatment,
            surface.projection_ref,
            surface.projection_revision,
            surface.order_basis_ref,
            surface.order_basis_revision,
            surface.opportunity_basis_ref,
            surface.opportunity_basis_revision,
            surface.timing_bucket_ref,
            surface.timing_bucket_revision,
            surface.limitation_ref,
        )
        wanted = (
            channel,
            owner,
            disposition,
            occurrence,
            content,
            _PROJECTION_REF,
            _PROJECTION_REVISION,
            _ORDER_BASIS_REF,
            _ORDER_BASIS_REVISION,
            _OPPORTUNITY_BASIS_REF if opportunity else None,
            _OPPORTUNITY_BASIS_REVISION if opportunity else None,
            _TIMING_BUCKET_REF if timing else None,
            _TIMING_BUCKET_REVISION if timing else None,
            None,
        )
        if coordinates != wanted:
            raise ValueError(
                f"participant opacity runtime surface {surface_ref} does not match the supported declaration"
            )


__all__ = ["validate_participant_opacity_runtime_enforcement"]
