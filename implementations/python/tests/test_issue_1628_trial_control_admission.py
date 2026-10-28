"""Trial controls must be supported before the compiler exposes any plan."""

from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from paths import REPO_ROOT
from pydantic import ValidationError
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import BackendManifestV2Model
from raes_contracts.versions import BACKEND_OPERATION_CONTRACT_IDS
from raes_processor.trial_compiler import compile_admitted_trial_plan
from test_sce_002_trial_compiler import _request


def _with_backend(request, change):
    key, manifest = next(iter(request.apparatus_manifests.items()))
    payload = manifest.model_dump(mode="json")
    change(payload)
    manifest = BackendManifestV2Model.model_validate(payload)
    reference = request.apparatus.manifest_refs[0].model_copy(
        update={"ref_digest": canonical_json_digest(manifest.model_dump(mode="json"))}
    )
    return replace(
        request,
        apparatus=request.apparatus.model_copy(update={"manifest_refs": [reference]}),
        apparatus_manifests={key: manifest},
    )


def _assert_refused(request):
    result = compile_admitted_trial_plan(request)
    assert result.plan is None
    assert [(d.code, d.address, d.message) for d in result.diagnostics] == [
        (
            "trial-compiler.execution-authority-unsupported",
            "/execution_authority",
            "a selected backend cannot honour the admitted execution authority",
        )
    ]


def test_timeout_cancellation_requires_explicit_backend_support():
    request = _request()
    request = replace(
        request, execution_authority=request.execution_authority.model_copy(update={"on_timeout": "cancel"})
    )
    _assert_refused(request)


@pytest.mark.parametrize("missing", ["declaration", "action", "probe", "residual-disclosure"])
def test_required_cleanup_must_be_supported(missing):
    def change(payload):
        cleanup = payload["capabilities"]["cleanup"]
        if missing == "declaration":
            payload["capabilities"]["cleanup"] = None
            payload["supported_contract_versions"] = [
                c for c in payload["supported_contract_versions"] if not c.startswith("trial-cleanup-")
            ]
        elif missing == "action":
            cleanup["supported_action_kinds"] = ["reset"]
        elif missing == "probe":
            cleanup["supported_verification_methods"] = ["unsupported"]
        else:
            cleanup["supports_reusable_state"] = False
            cleanup["supports_residual_state_disclosure"] = False

    _assert_refused(_with_backend(_request(), change))


def test_non_cancelling_single_attempt_keeps_supported_plan():
    assert compile_admitted_trial_plan(_request()).plan is not None


def test_retry_requires_cessation_and_effect_observation():
    request = _request()
    cleanup = request.execution_authority.cleanup
    retry = cleanup.retry_policy.model_copy(update={"max_attempts": 2})
    authority = request.execution_authority.model_copy(
        update={"cleanup": cleanup.model_copy(update={"retry_policy": retry})}
    )
    _assert_refused(replace(request, execution_authority=authority))


def _declare(payload, guarantees):
    payload["capabilities"]["operation_supervision"] = {"name": "trial-controls", "guarantees": guarantees}
    payload["supported_contract_versions"] = sorted(
        set(payload["supported_contract_versions"]) | set(BACKEND_OPERATION_CONTRACT_IDS)
    )


def test_declared_cancellation_round_trips_and_admits():
    from raes_backend_protocols.manifest import backend_manifest_from_v2_model_with_envelope, backend_manifest_v2_model

    request = _with_backend(_request(), lambda payload: _declare(payload, ["cancellation"]))
    request = replace(
        request, execution_authority=request.execution_authority.model_copy(update={"on_timeout": "cancel"})
    )
    model = next(iter(request.apparatus_manifests.values()))
    internal = backend_manifest_from_v2_model_with_envelope(model, request.realization_envelope)
    rendered = backend_manifest_v2_model(internal)
    assert rendered.capabilities.operation_supervision == model.capabilities.operation_supervision
    assert backend_manifest_from_v2_model_with_envelope(rendered, request.realization_envelope) == internal
    assert compile_admitted_trial_plan(request).plan is not None


@pytest.mark.parametrize("guarantees", [["cancellation", "cancellation"], ["invented"], [True], ["cancellation"] * 6])
def test_manifest_rejects_invalid_guarantee_collections(guarantees):
    request = _request()
    payload = next(iter(request.apparatus_manifests.values())).model_dump(mode="json")
    _declare(payload, guarantees)
    with pytest.raises(ValidationError):
        BackendManifestV2Model.model_validate(payload)


def test_manifest_requires_operation_contract_family():
    request = _request()
    payload = next(iter(request.apparatus_manifests.values())).model_dump(mode="json")
    _declare(payload, ["cancellation"])
    payload["supported_contract_versions"].remove(BACKEND_OPERATION_CONTRACT_IDS[0])
    with pytest.raises(ValidationError, match="operation supervision requires"):
        BackendManifestV2Model.model_validate(payload)


def test_unchanged_manifest_omits_declaration_and_retains_digest():
    import json

    payload = json.loads(
        (REPO_ROOT / "contracts/fixtures/backend-manifest/backend-manifest-v2/valid/stub.json").read_text()
    )
    model = BackendManifestV2Model.model_validate(payload)
    assert "operation_supervision" not in model.model_dump(mode="json")["capabilities"]
    assert (
        canonical_json_digest(model.model_dump(mode="json"))
        == "sha256:5f2a0c0f27812a431da8e1ec02ed42f0125a857f312dcc37f4899440827d145c"
    )


def test_published_schema_accepts_support_and_rejects_duplicates():
    import json

    schema = json.loads((REPO_ROOT / "contracts/schemas/backend-manifest/backend-manifest-v2.json").read_text())
    model = next(iter(_with_backend(_request(), lambda p: _declare(p, ["cancellation"])).apparatus_manifests.values()))
    payload = model.model_dump(mode="json")
    validator = Draft202012Validator(schema)
    validator.validate(payload)
    payload["capabilities"]["operation_supervision"]["guarantees"] *= 2
    assert list(validator.iter_errors(payload))


@pytest.mark.parametrize("missing_contract", BACKEND_OPERATION_CONTRACT_IDS)
def test_published_schema_requires_each_operation_contract(missing_contract):
    import json

    from raes_contracts.contracts import schema_bundle

    model = next(iter(_with_backend(_request(), lambda p: _declare(p, ["cancellation"])).apparatus_manifests.values()))
    payload = model.model_dump(mode="json")
    payload["supported_contract_versions"].remove(missing_contract)
    published = json.loads((REPO_ROOT / "contracts/schemas/backend-manifest/backend-manifest-v2.json").read_text())
    for schema in (published, schema_bundle()["backend-manifest-v2"]):
        assert list(Draft202012Validator(schema).iter_errors(payload))


@pytest.mark.parametrize(
    "guarantees,admitted",
    [([], False), (["cessation-evidence"], False), (["cessation-evidence", "effect-observation"], True)],
)
def test_retry_checks_all_required_guarantees(guarantees, admitted):
    request = _with_backend(_request(), lambda payload: _declare(payload, guarantees))
    cleanup = request.execution_authority.cleanup
    retry = cleanup.retry_policy.model_copy(update={"max_attempts": 2})
    authority = request.execution_authority.model_copy(
        update={"cleanup": cleanup.model_copy(update={"retry_policy": retry})}
    )
    result = compile_admitted_trial_plan(replace(request, execution_authority=authority))
    assert (result.plan is not None) is admitted


def _mixed_with_unsupported_backend(*, selected):
    from raes_contracts.contracts import seal_mixed_composition_profile
    from test_issue_1015_mixed_staged_trial_admission import _mixed_request, _profile_context, _replace_root_profile

    request = _mixed_request()
    # The original ordinary backend remains in caller maps but is not selected by mixed entries.
    key = next(iter(request.apparatus_manifests))
    profile = list(request.mixed_profiles.values())[-1]
    if selected:
        reference = next(iter(profile.components.values())).manifest_ref
        key = ("backend", reference.subject_ref.ref_id, reference.subject_ref.ref_version, reference.ref_version)
    payload = request.apparatus_manifests[key].model_dump(mode="json")
    payload["capabilities"]["cleanup"]["supported_action_kinds"] = ["reset"]
    manifest = BackendManifestV2Model.model_validate(payload)
    request = replace(request, apparatus_manifests={**request.apparatus_manifests, key: manifest})
    if selected:
        fields = profile.model_dump(mode="python", exclude={"profile_digest"})
        component = next(iter(fields["components"].values()))
        component["manifest_ref"]["ref_digest"] = canonical_json_digest(manifest.model_dump(mode="json"))
        profile = seal_mixed_composition_profile(**fields)
        request = _replace_root_profile(request, profile, _profile_context(profile))
    return request


def test_unsupported_later_mixed_entry_refuses_complete_plan_deterministically():
    request = _mixed_with_unsupported_backend(selected=True)
    _assert_refused(request)
    reversed_request = replace(request, apparatus_manifests=dict(reversed(list(request.apparatus_manifests.items()))))
    first = compile_admitted_trial_plan(request, coordinate_partitions=((0,), (1,)))
    second = compile_admitted_trial_plan(reversed_request, coordinate_partitions=((1,), (0,)))
    assert first == second


def test_unselected_backend_cannot_refuse_a_mixed_plan():
    assert compile_admitted_trial_plan(_mixed_with_unsupported_backend(selected=False)).plan is not None


def test_empty_selected_backend_set_is_refused(monkeypatch):
    import raes_processor.trial_compiler.compiler as compiler

    monkeypatch.setattr(compiler, "validate_selected_apparatus", lambda request: {})
    _assert_refused(_request())


def test_best_effort_cleanup_does_not_require_its_action_support():
    request = _request()
    cleanup = request.execution_authority.cleanup
    obligation = cleanup.cleanup_obligations["destroy"].model_copy(
        update={"action_kind": "reset", "requirement": "best-effort", "verification_probe_refs": ["optional:reset"]}
    )
    authority = request.execution_authority.model_copy(
        update={"cleanup": cleanup.model_copy(update={"cleanup_obligations": {"destroy": obligation}})}
    )
    assert compile_admitted_trial_plan(replace(request, execution_authority=authority)).plan is not None


def test_reusable_state_requires_declared_support():
    request = _request()
    cleanup = request.execution_authority.cleanup
    clean_state = cleanup.clean_state.model_copy(
        update={"mode": "declared-reusable", "reusable_state_claim_ref": "claim:reusable"}
    )
    authority = request.execution_authority.model_copy(
        update={"cleanup": cleanup.model_copy(update={"clean_state": clean_state})}
    )
    request = replace(request, execution_authority=authority)
    request = _with_backend(
        request, lambda payload: payload["capabilities"]["cleanup"].update(supports_reusable_state=False)
    )
    _assert_refused(request)


def test_internal_manifest_cannot_bypass_operation_contract_requirement():
    from raes_backend_protocols.backend_manifest import BackendManifest
    from raes_backend_protocols.manifest import backend_manifest_from_v2_model_with_envelope

    request = _with_backend(_request(), lambda payload: _declare(payload, ["cancellation"]))
    model = next(iter(request.apparatus_manifests.values()))
    internal = backend_manifest_from_v2_model_with_envelope(model, request.realization_envelope)
    unsupported_contracts = internal.supported_contract_versions.difference(BACKEND_OPERATION_CONTRACT_IDS)
    with pytest.raises(ValueError, match="operation supervision requires"):
        BackendManifest(
            identity=internal.identity,
            compatibility=internal.compatibility,
            capabilities=internal.capabilities,
            supported_contract_versions=unsupported_contracts,
        )
