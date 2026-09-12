"""Effective evidence claims must match the identity admitted by reporting."""

from copy import deepcopy

import pytest
from raes_contracts.contracts.realization_descriptions import TypedRealizationDescriptionModel
from raes_contracts.domain_profiles import (
    DomainProfileAdmissionPolicyModel,
    DomainProfileNamespaceAdmissionModel,
    DomainProfileResolutionContextModel,
)
from raes_contracts.observation_demand import (
    AchievedObservationValue,
    ObservationBasis,
    ObservationDemandResolution,
    ObservationSelector,
    realization_description_report,
)
from test_issue_1209_description_profiles import profiled_payload
from test_issue_1209_descriptions import description_payload
from test_issue_1212_runtime_boundaries import _demands


def observed_payload(*, profiled=False):
    payload = profiled_payload("experiment-run-v1") if profiled else description_payload()
    payload["provenance"].update(
        basis="observed", evidence_refs=[{"ref_kind": "evidence-record", "ref_id": "verified-evidence"}]
    )
    if profiled:
        binding = payload["facts"][0]["profile_bindings"][0]
        binding["provenance"].update(basis="observed", evidence_refs=["verified-evidence"])
        binding["children"] = [deepcopy(binding)]
        binding["children"][0]["binding_id"] = "nested-profile"
    return payload


def report(payload, *, protector=None):
    selector = ObservationSelector(
        semantic_scope="/nodes/a",
        data_kind="field",
        names=("family",),
        coverage_profile="example-state/v1",
        max_items=8,
    )
    return realization_description_report(
        ObservationDemandResolution(_demands(selector, purpose="realization-description", required=True)),
        {
            selector.key: AchievedObservationValue(
                TypedRealizationDescriptionModel.model_validate(payload),
                ObservationBasis.OBSERVED,
                evidence_ref="verified-evidence",
            )
        },
        evidence_validator=lambda _key, value: value.evidence_ref == "verified-evidence",
        protector=protector,
        profile_context=DomainProfileResolutionContextModel(
            namespace_admissions=(
                DomainProfileNamespaceAdmissionModel(
                    namespace="com.example.private", authority="urn:example:authority", trust_decision_id="admitted"
                ),
            ),
            definitions=(),
        ),
        profile_policy=DomainProfileAdmissionPolicyModel(allow_opaque_exchange=True),
    )


@pytest.mark.parametrize("retain_coverage", [False, True])
def test_projection_checks_effective_evidence_provenance(retain_coverage):
    payload = observed_payload()
    payload["facts"][0]["provenance"] = deepcopy(payload["provenance"])
    if retain_coverage:
        payload["coverage"][0]["provenance"] = deepcopy(payload["provenance"])
    else:
        payload["coverage"] = []
    # This default applies only to facts that the requested projection removes.
    payload["provenance"]["evidence_refs"][0]["ref_id"] = "unselected-evidence"
    result = report(payload)[0].value
    assert [fact.fact_id for fact in result.facts] == ["family"]
    assert result.facts[0].provenance.evidence_refs[0].ref_id == "verified-evidence"
    assert bool(result.coverage) is retain_coverage
    if retain_coverage:
        assert result.coverage[0].provenance.evidence_refs[0].ref_id == "verified-evidence"


@pytest.mark.parametrize("inherited_claim", ["fact", "coverage"])
def test_inherited_provenance_still_requires_verified_reference(inherited_claim):
    payload = observed_payload()
    payload["facts"][0]["provenance"] = deepcopy(payload["provenance"])
    payload["coverage"][0]["provenance"] = deepcopy(payload["provenance"])
    claim = payload["facts"][0] if inherited_claim == "fact" else payload["coverage"][0]
    del claim["provenance"]
    payload["provenance"]["evidence_refs"][0]["ref_id"] = "unverified-evidence"
    with pytest.raises(ValueError, match="evidence"):
        report(payload)


@pytest.mark.parametrize("source", ["default", "fact", "coverage", "profiled-fact", "protection"])
@pytest.mark.parametrize("qualifier", ["ref_kind", "ref_version", "ref_digest", "ref_path", "duplicate"])
def test_reporting_rejects_unverified_reference_qualifiers(source, qualifier):
    payload = observed_payload(profiled=source == "profiled-fact")

    def forge(value):
        provenance = value["provenance"]
        if source in {"fact", "profiled-fact"}:
            value["facts"][0]["provenance"] = deepcopy(provenance)
            provenance = value["facts"][0]["provenance"]
        elif source == "coverage":
            value["coverage"][0]["provenance"] = deepcopy(provenance)
            provenance = value["coverage"][0]["provenance"]
        reference = provenance["evidence_refs"][0]
        if qualifier == "duplicate":
            provenance["evidence_refs"].append({**reference, "ref_version": "forged-version"})
        else:
            reference[qualifier] = {
                "ref_kind": "other",
                "ref_version": "forged-version",
                "ref_digest": "sha256:" + "a" * 64,
                "ref_path": "/unverified-evidence",
            }[qualifier]

    def protect(_key, achieved, _demand):
        value = achieved.value.model_dump(mode="json")
        forge(value)
        return AchievedObservationValue(
            TypedRealizationDescriptionModel.model_validate(value), achieved.basis, achieved.evidence_ref
        )

    # Pin the accepted identity, including the nested profile path, before forgery.
    assert report(payload)[0].value.facts[0].fact_id == "family"
    if source != "protection":
        forge(payload)
    with pytest.raises(ValueError, match="evidence"):
        report(payload, protector=protect if source == "protection" else None)


@pytest.mark.parametrize("after_protection", [False, True])
def test_nested_profile_reference_cannot_escape_verified_fact(after_protection):
    payload = observed_payload(profiled=True)
    assert report(payload)[0].value.facts[0].profile_bindings[0].children

    def forge(value):
        value["facts"][0]["profile_bindings"][0]["children"][0]["provenance"]["evidence_refs"] = ["unverified"]

    def protect(_key, achieved, _demand):
        # Mutate the nested admitted model to exercise reporting's re-admission,
        # without touching the fact or coverage reference that the verifier accepts.
        nested = achieved.value.facts[0].profile_bindings[0].children[0]
        object.__setattr__(nested.provenance, "evidence_refs", ("unverified",))
        return achieved

    if not after_protection:
        forge(payload)
    with pytest.raises(ValueError, match="description profile evidence must join its fact provenance"):
        report(payload, protector=protect if after_protection else None)


def test_nested_profile_evidence_is_checked_independently_by_report_join():
    from raes_contracts.description_reporting import validate_description_evidence

    value = TypedRealizationDescriptionModel.model_validate(observed_payload(profiled=True))
    validate_description_evidence(value, ObservationBasis.OBSERVED, "verified-evidence")
    nested = value.facts[0].profile_bindings[0].children[0]
    object.__setattr__(nested.provenance, "evidence_refs", ("unverified",))
    with pytest.raises(ValueError, match="typed description evidence must join the externally verified reference"):
        validate_description_evidence(value, ObservationBasis.OBSERVED, "verified-evidence")
