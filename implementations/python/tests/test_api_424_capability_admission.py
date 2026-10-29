"""Use real backend manifest admission, never method-presence support guesses."""

from dataclasses import replace

import pytest
from participant_control_contract_fixtures import evaluation_payload
from raes_backend_protocols import participant_control_admission
from raes_backend_protocols.capabilities import BackendManifest, ParticipantFeatureSupport
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_backend_stubs.stubs import create_stub_manifest
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.contracts.participant_control_composition import ParticipantControlEvaluationModel, control_digest
from raes_contracts.errors import ConflictError
from raes_contracts.vocabulary import ParticipantFeatureSupportLevel

_UNRESOLVED = "participant control manifest support is unresolved"


def manifest_with_modular_support():
    base = create_stub_manifest()
    feature = "participant_modular_control"
    runtime = replace(
        base.participant_runtime,
        supported_behavior_features=base.participant_runtime.supported_behavior_features | {feature},
        feature_support=tuple(s for s in base.participant_runtime.feature_support if s.feature != feature)
        + (
            ParticipantFeatureSupport(
                feature=feature, support_level=ParticipantFeatureSupportLevel.EXACT, evidence_refs=("support-evidence",)
            ),
        ),
    )
    return BackendManifest(
        identity=base.identity,
        compatibility=base.compatibility,
        supported_contract_versions=base.supported_contract_versions
        | {"participant-control-selection-v1", "participant-control-evaluation-v1"},
        realization_support=base.realization_support,
        concept_bindings=base.concept_bindings,
        constraints=base.constraints,
        capabilities=replace(base.capabilities, participant_runtime=runtime),
    )


def test_exact_manifest_declaration_resolves_but_does_not_install_provider():
    from raes_backend_protocols.participant_control_admission import resolve_participant_control_support

    manifest = manifest_with_modular_support()
    payload = evaluation_payload()
    payload["support"][0]["declaration_ref"]["digest"] = control_digest(backend_manifest_v2_model(manifest))
    record = ParticipantControlEvaluationModel.model_validate(payload)
    assert resolve_participant_control_support(manifest, record.support[0]) == "exact"


def test_manifest_content_mismatch_rejects_dishonest_claim():
    from raes_backend_protocols.participant_control_admission import resolve_participant_control_support

    record = ParticipantControlEvaluationModel.model_validate(evaluation_payload())
    manifest = manifest_with_modular_support()
    with pytest.raises(ConflictError, match=_UNRESOLVED):
        resolve_participant_control_support(manifest, record.support[0])


def test_unimplemented_stub_does_not_gain_modular_support():
    from raes_backend_protocols.participant_control_admission import resolve_participant_control_support

    manifest = create_stub_manifest()
    payload = evaluation_payload()
    payload["support"][0]["declaration_ref"]["digest"] = control_digest(backend_manifest_v2_model(manifest))
    record = ParticipantControlEvaluationModel.model_validate(payload)
    with pytest.raises(ConflictError, match=_UNRESOLVED) as caught:
        resolve_participant_control_support(manifest, record.support[0])
    # The fixed refusal does not carry the API-407 reason, which names the feature and levels.
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


def test_manifest_without_contract_form_is_an_unresolved_refusal(monkeypatch: pytest.MonkeyPatch):
    def no_contract_form(_manifest: BackendManifest) -> BackendManifestV2Model:
        return BackendManifestV2Model.model_validate({})

    record = ParticipantControlEvaluationModel.model_validate(evaluation_payload())
    monkeypatch.setattr(participant_control_admission, "backend_manifest_v2_model", no_contract_form)

    with pytest.raises(ConflictError, match=_UNRESOLVED):
        participant_control_admission.resolve_participant_control_support(
            manifest_with_modular_support(), record.support[0]
        )


def test_defect_in_support_resolution_is_not_reported_as_a_refusal(monkeypatch: pytest.MonkeyPatch):
    # Regression: a broad handler once turned every exception, defects included, into the refusal.
    def defective(*_args: object, **_kwargs: object) -> None:
        raise KeyError("resolver-defect")

    manifest = manifest_with_modular_support()
    payload = evaluation_payload()
    payload["support"][0]["declaration_ref"]["digest"] = control_digest(backend_manifest_v2_model(manifest))
    record = ParticipantControlEvaluationModel.model_validate(payload)
    monkeypatch.setattr(participant_control_admission, "resolve_participant_feature_support", defective)

    with pytest.raises(KeyError, match="resolver-defect"):
        participant_control_admission.resolve_participant_control_support(manifest, record.support[0])
