"""Digest-bound apparatus admission for deterministic trial compilation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import (
    AdmittedApparatusBindingModel,
    BackendManifestV2Model,
    ExperimentApparatusConstraintModel,
    ExperimentManifestReferenceModel,
    ParticipantImplementationManifestModel,
    ProcessorManifestV2Model,
)
from raes_contracts.contracts.mixed_composition import MixedCompositionComponentModel
from raes_contracts.experiment_bindings import (
    ApparatusManifest,
    ApparatusManifestKey,
    ParticipantManifestKey,
)
from raes_contracts.realization_envelope import BackendRealizationEnvelopeModel

from .models import CompilationFailure, TrialCompilationRequest

_CAPABILITY_CONTRACT_ALIASES = {
    "evaluation-results": "evaluation-result-envelope-v1",
    "workflow-results": "workflow-result-envelope-v1",
}
_MANIFEST_REFS_ADDRESS = "/apparatus/manifest_refs"
_PARTICIPANT_MANIFEST_REFS_ADDRESS = "/apparatus/participant_manifest_refs"
_CAPABILITY_REFS_ADDRESS = "/apparatus/capability_refs"
_REALIZATION_ENVELOPE_ADDRESS = "/apparatus/realization_envelope"


def _fail(code: str, address: str, message: str) -> CompilationFailure:
    return CompilationFailure(code, address, message)


def apparatus_manifest_key(reference: ExperimentManifestReferenceModel) -> ApparatusManifestKey:
    subject = reference.subject_ref
    if (
        subject is None
        or subject.ref_kind not in {"processor", "backend"}
        or subject.ref_version is None
        or reference.ref_version is None
    ):
        raise _fail(
            "apparatus-manifest-reference-invalid",
            _MANIFEST_REFS_ADDRESS,
            "selected apparatus manifest references require an exact processor or backend subject identity",
        )
    return (
        subject.ref_kind,
        subject.ref_id,
        subject.ref_version,
        reference.ref_version,
    )


def _manifest_kind(manifest: ApparatusManifest) -> str:
    return "processor" if isinstance(manifest, ProcessorManifestV2Model) else "backend"


def _validate_reference_payload(
    reference: ExperimentManifestReferenceModel,
    manifest: ApparatusManifest,
) -> None:
    subject = reference.subject_ref
    manifest_kind = _manifest_kind(manifest)
    if (
        subject is None
        or subject.ref_kind != manifest_kind
        or reference.ref_id != manifest.identity.name
        or reference.ref_version != manifest.schema_version
        or subject.ref_id != manifest.identity.name
        or subject.ref_version != manifest.identity.version
    ):
        raise _fail(
            "apparatus-manifest-identity-mismatch",
            _MANIFEST_REFS_ADDRESS,
            "selected apparatus manifest identity does not match its concrete payload",
        )
    digest = canonical_json_digest(manifest.model_dump(mode="json"))
    if reference.ref_digest != digest:
        raise _fail(
            "apparatus-manifest-digest-mismatch",
            _MANIFEST_REFS_ADDRESS,
            "selected apparatus manifest digest does not match its concrete payload",
        )


def _manifest_capability_ids(manifest: ApparatusManifest) -> set[str]:
    contracts = set(manifest.supported_contract_versions)
    capabilities = set(contracts)
    if isinstance(manifest, ProcessorManifestV2Model):
        capabilities.update(manifest.capabilities.supported_sdl_versions)
        capabilities.update(
            feature.value if hasattr(feature, "value") else str(feature)
            for feature in manifest.capabilities.supported_features
        )
    else:
        capabilities.update(
            capability
            for capability, required_contract in _CAPABILITY_CONTRACT_ALIASES.items()
            if required_contract in contracts
        )
    return capabilities


def _identity_allowed(
    manifest: ApparatusManifest,
    allowed_refs: Iterable[object],
) -> bool:
    manifest_kind = _manifest_kind(manifest)
    return any(
        getattr(reference, "ref_kind", None) == manifest_kind
        and getattr(reference, "ref_id", None) == manifest.identity.name
        and getattr(reference, "ref_version", None) == manifest.identity.version
        for reference in allowed_refs
    )


def _reference_satisfies_requirement(
    selected: ExperimentManifestReferenceModel,
    required: ExperimentManifestReferenceModel,
) -> bool:
    reference_matches = True
    for field_name in ("ref_kind", "ref_id", "ref_version", "ref_digest"):
        required_value = getattr(required, field_name)
        if required_value is not None and getattr(selected, field_name) != required_value:
            reference_matches = False
            break
    required_subject = required.subject_ref
    selected_subject = selected.subject_ref
    if not reference_matches or required_subject is None:
        subject_matches = reference_matches
    elif selected_subject is None:
        subject_matches = False
    else:
        subject_matches = all(
            getattr(required_subject, field_name) is None
            or getattr(selected_subject, field_name) == getattr(required_subject, field_name)
            for field_name in ("ref_kind", "ref_id", "ref_version")
        )
    return subject_matches


def _load_apparatus_manifests(
    apparatus: AdmittedApparatusBindingModel,
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest],
) -> tuple[
    dict[ApparatusManifestKey, ApparatusManifest],
    dict[ApparatusManifestKey, ExperimentManifestReferenceModel],
]:
    selected: dict[ApparatusManifestKey, ApparatusManifest] = {}
    references_by_key: dict[ApparatusManifestKey, ExperimentManifestReferenceModel] = {}
    for reference in apparatus.manifest_refs:
        key = apparatus_manifest_key(reference)
        if key in selected:
            raise _fail(
                "apparatus-manifest-duplicate",
                _MANIFEST_REFS_ADDRESS,
                "selected apparatus contains duplicate concrete manifest identities",
            )
        manifest = apparatus_manifests.get(key)
        if manifest is None:
            raise _fail(
                "apparatus-manifest-payload-missing",
                _MANIFEST_REFS_ADDRESS,
                "selected apparatus manifest reference has no exact concrete payload",
            )
        _validate_reference_payload(reference, manifest)
        selected[key] = manifest
        references_by_key[key] = reference
    return selected, references_by_key


def _validate_apparatus_envelope_and_capabilities(
    apparatus: AdmittedApparatusBindingModel,
    realization_envelope: BackendRealizationEnvelopeModel,
    selected: dict[ApparatusManifestKey, ApparatusManifest],
) -> set[str]:
    backends = [manifest for manifest in selected.values() if isinstance(manifest, BackendManifestV2Model)]
    if not backends or any(
        manifest.realization_envelope != getattr(realization_envelope, "identity", None) for manifest in backends
    ):
        raise _fail(
            "apparatus-envelope-unsupported",
            _REALIZATION_ENVELOPE_ADDRESS,
            "selected backend manifests do not bind the admitted realization envelope",
        )
    available_capabilities = set().union(*(_manifest_capability_ids(manifest) for manifest in selected.values()))
    if apparatus.realization_envelope != getattr(realization_envelope, "identity", None):
        raise _fail(
            "apparatus-envelope-identity-mismatch",
            _REALIZATION_ENVELOPE_ADDRESS,
            "admitted apparatus realization envelope does not match the concrete payload",
        )
    declared_capabilities = set(apparatus.capability_refs)
    if not declared_capabilities.issubset(available_capabilities):
        raise _fail(
            "apparatus-capability-unproven",
            _CAPABILITY_REFS_ADDRESS,
            "selected apparatus capability claims are not proven by concrete manifests",
        )
    return declared_capabilities


def _validate_apparatus_allowlists(
    selected: dict[ApparatusManifestKey, ApparatusManifest],
    intent: ExperimentApparatusConstraintModel,
) -> None:
    for manifest_kind, allowed_refs in (
        ("processor", intent.allowed_processor_refs),
        ("backend", intent.allowed_backend_refs),
    ):
        matching_kind = [manifest for manifest in selected.values() if _manifest_kind(manifest) == manifest_kind]
        if allowed_refs and (
            not matching_kind or any(not _identity_allowed(manifest, allowed_refs) for manifest in matching_kind)
        ):
            raise _fail(
                "apparatus-identity-not-allowed",
                _MANIFEST_REFS_ADDRESS,
                "selected apparatus identity is outside its admitted kind-specific allowlist",
            )


def _validate_apparatus_intent(
    request: TrialCompilationRequest,
    selected: dict[ApparatusManifestKey, ApparatusManifest],
    references_by_key: dict[ApparatusManifestKey, ExperimentManifestReferenceModel],
    declared_capabilities: set[str],
) -> None:
    intent = request.experiment.apparatus_intent
    if intent is None:
        return
    if not set(intent.required_capabilities).issubset(declared_capabilities):
        raise _fail(
            "apparatus-capability-missing",
            _CAPABILITY_REFS_ADDRESS,
            "selected apparatus does not satisfy every required capability",
        )
    _validate_apparatus_allowlists(selected, intent)
    selected_references = tuple(references_by_key.values())
    if any(
        not any(_reference_satisfies_requirement(selected_ref, required) for selected_ref in selected_references)
        for required in intent.required_manifest_refs
    ):
        raise _fail(
            "apparatus-manifest-missing",
            _MANIFEST_REFS_ADDRESS,
            "selected apparatus does not include every exact required manifest",
        )


def validate_selected_apparatus(
    request: TrialCompilationRequest,
) -> dict[ApparatusManifestKey, ApparatusManifest]:
    """Resolve and validate every sealed apparatus reference against concrete content."""

    selected, references_by_key = _load_apparatus_manifests(request.apparatus, request.apparatus_manifests)
    declared_capabilities = _validate_apparatus_envelope_and_capabilities(
        request.apparatus,
        request.realization_envelope,
        selected,
    )
    _validate_apparatus_intent(request, selected, references_by_key, declared_capabilities)
    return selected


def validate_admitted_apparatus(
    apparatus: AdmittedApparatusBindingModel,
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest],
    realization_envelope: BackendRealizationEnvelopeModel,
    *,
    intent: ExperimentApparatusConstraintModel | None = None,
) -> dict[ApparatusManifestKey, ApparatusManifest]:
    """Revalidate sealed apparatus refs against exact execution-time payloads."""

    selected, references_by_key = _load_apparatus_manifests(apparatus, apparatus_manifests)
    declared_capabilities = _validate_apparatus_envelope_and_capabilities(
        apparatus,
        realization_envelope,
        selected,
    )
    if intent is not None:
        if not set(intent.required_capabilities).issubset(declared_capabilities):
            raise _fail(
                "apparatus-capability-missing",
                _CAPABILITY_REFS_ADDRESS,
                "selected apparatus does not satisfy every required capability",
            )
        _validate_apparatus_allowlists(selected, intent)
        selected_references = tuple(references_by_key.values())
        if any(
            not any(_reference_satisfies_requirement(selected_ref, required) for selected_ref in selected_references)
            for required in intent.required_manifest_refs
        ):
            raise _fail(
                "apparatus-manifest-missing",
                _MANIFEST_REFS_ADDRESS,
                "selected apparatus does not include every exact required manifest",
            )
    return selected


def validate_selected_participant_manifests(
    request: TrialCompilationRequest,
) -> dict[ParticipantManifestKey, ParticipantImplementationManifestModel]:
    """Resolve every participant admission authority from its sealed digest reference."""

    selected: dict[ParticipantManifestKey, ParticipantImplementationManifestModel] = {}
    for reference in request.apparatus.participant_manifest_refs:
        key = (
            reference.participant_address,
            reference.implementation_name,
            reference.implementation_version,
            reference.manifest_version,
        )
        manifest = request.participant_manifests.get(key)
        if manifest is None:
            raise _fail(
                "participant-manifest-payload-missing",
                _PARTICIPANT_MANIFEST_REFS_ADDRESS,
                "selected participant manifest reference has no exact concrete payload",
            )
        if (
            manifest.identity.name != reference.implementation_name
            or manifest.identity.version != reference.implementation_version
            or manifest.schema_version != reference.manifest_version
        ):
            raise _fail(
                "participant-manifest-identity-mismatch",
                _PARTICIPANT_MANIFEST_REFS_ADDRESS,
                "selected participant manifest identity does not match its concrete payload",
            )
        if canonical_json_digest(manifest.model_dump(mode="json")) != reference.manifest_digest:
            raise _fail(
                "participant-manifest-digest-mismatch",
                _PARTICIPANT_MANIFEST_REFS_ADDRESS,
                "selected participant manifest digest does not match its concrete payload",
            )
        selected[key] = manifest
    return selected


def _resolve_composition_components(
    components: Mapping[str, MixedCompositionComponentModel],
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest],
    realization_envelopes: Mapping[str, BackendRealizationEnvelopeModel],
) -> tuple[
    dict[str, ApparatusManifest],
    dict[ApparatusManifestKey, ApparatusManifest],
    dict[ApparatusManifestKey, ExperimentManifestReferenceModel],
]:
    selected: dict[str, ApparatusManifest] = {}
    selected_by_key: dict[ApparatusManifestKey, ApparatusManifest] = {}
    references_by_key: dict[ApparatusManifestKey, ExperimentManifestReferenceModel] = {}
    for component_id, component in sorted(components.items()):
        key = apparatus_manifest_key(component.manifest_ref)
        manifest = apparatus_manifests.get(key)
        if manifest is None:
            raise _fail(
                "apparatus-manifest-payload-missing",
                _MANIFEST_REFS_ADDRESS,
                "composition component manifest reference has no exact concrete payload",
            )
        _validate_reference_payload(component.manifest_ref, manifest)
        envelope = realization_envelopes.get(component.realization_envelope.envelope_id)
        if envelope is None or envelope.identity != component.realization_envelope:
            raise _fail(
                "apparatus-envelope-identity-mismatch",
                _REALIZATION_ENVELOPE_ADDRESS,
                "composition component realization envelope is unresolved or stale",
            )
        if isinstance(manifest, BackendManifestV2Model) and manifest.realization_envelope != envelope.identity:
            raise _fail(
                "apparatus-envelope-unsupported",
                _REALIZATION_ENVELOPE_ADDRESS,
                "composition backend manifest does not bind its selected realization envelope",
            )
        selected[component_id] = manifest
        selected_by_key[key] = manifest
        references_by_key[key] = component.manifest_ref
    return selected, selected_by_key, references_by_key


def _validate_composition_compatibility(selected: Mapping[str, ApparatusManifest]) -> None:
    processors = [manifest for manifest in selected.values() if isinstance(manifest, ProcessorManifestV2Model)]
    backends = [manifest for manifest in selected.values() if isinstance(manifest, BackendManifestV2Model)]
    for processor in processors:
        if backends and not any(
            backend.identity.name in processor.compatibility.backends
            and processor.identity.name in backend.compatibility.processors
            for backend in backends
        ):
            raise _fail(
                "apparatus-compatibility-rejected",
                _MANIFEST_REFS_ADDRESS,
                "composition processor has no mutually compatible selected backend",
            )


def _validate_composition_intent(
    selected: Mapping[str, ApparatusManifest],
    selected_by_key: dict[ApparatusManifestKey, ApparatusManifest],
    references_by_key: Mapping[ApparatusManifestKey, ExperimentManifestReferenceModel],
    intent: ExperimentApparatusConstraintModel,
) -> None:
    available_capabilities = set().union(*(_manifest_capability_ids(manifest) for manifest in selected.values()))
    if not set(intent.required_capabilities).issubset(available_capabilities):
        raise _fail(
            "apparatus-capability-missing",
            _CAPABILITY_REFS_ADDRESS,
            "composition apparatus does not satisfy every required capability",
        )
    _validate_apparatus_allowlists(selected_by_key, intent)
    selected_references = tuple(references_by_key.values())
    if any(
        not any(_reference_satisfies_requirement(selected_ref, required) for selected_ref in selected_references)
        for required in intent.required_manifest_refs
    ):
        raise _fail(
            "apparatus-manifest-missing",
            _MANIFEST_REFS_ADDRESS,
            "composition apparatus omits a required manifest",
        )


def validate_composition_components(
    components: Mapping[str, MixedCompositionComponentModel],
    apparatus_manifests: Mapping[ApparatusManifestKey, ApparatusManifest],
    realization_envelopes: Mapping[str, BackendRealizationEnvelopeModel],
    *,
    intent: ExperimentApparatusConstraintModel | None,
) -> dict[str, ApparatusManifest]:
    """Resolve exact component manifests/envelopes and their joint compatibility."""

    selected, selected_by_key, references_by_key = _resolve_composition_components(
        components,
        apparatus_manifests,
        realization_envelopes,
    )
    _validate_composition_compatibility(selected)
    if intent is not None:
        _validate_composition_intent(selected, selected_by_key, references_by_key, intent)
    return selected


__all__ = [
    "apparatus_manifest_key",
    "validate_admitted_apparatus",
    "validate_composition_components",
    "validate_selected_apparatus",
    "validate_selected_participant_manifests",
]
