"""Bindings cannot escape their carrier, selected fact or verified evidence basis."""

from copy import deepcopy

import pytest
from pydantic import ValidationError
from raes_contracts.contracts import ExperimentEvidenceRecordModel, ExperimentRealizedFormDisclosureModel
from raes_contracts.contracts.realization_descriptions import TypedRealizationDescriptionModel
from raes_contracts.domain_profiles import DomainProfileBindingBasis, DomainProfileBindingUse
from raes_contracts.observation_demand import (
    AchievedObservationValue,
    ObservationBasis,
    ObservationDemandResolution,
    ObservationSelector,
    realization_description_report,
)
from test_issue_1202_domain_profiles import _binding, _definition
from test_issue_1209_descriptions import description_payload, evidence_payload
from test_issue_1212_runtime_boundaries import _demands


def profiled_payload(host="experiment-evidence-record-v1"):
    definition = _definition(namespace="com.example.private", authority="urn:example:authority", profile_id="detail")
    binding = _binding(
        definition,
        value={"name": "profile-private-sentinel"},
        use=DomainProfileBindingUse.OPAQUE_EXCHANGE,
        basis=DomainProfileBindingBasis.BACKEND_SELECTED,
    ).model_dump(mode="json")
    binding["owner"].update(
        owning_contract_id=host,
        canonical_address="#/nodes/a/family",
        lifecycle_phase="capture" if host == "experiment-evidence-record-v1" else "realization-description",
    )
    payload = description_payload()
    payload["facts"][0]["profile_bindings"] = [binding]
    return payload


def carrier_payload(description, host):
    if host == "experiment-evidence-record-v1":
        return ExperimentEvidenceRecordModel, {**evidence_payload(), "typed_description": description}
    return ExperimentRealizedFormDisclosureModel, {
        "concern_id": "selection",
        "concern_kind": "backend-selection",
        "basis": "backend-realized",
        "realized_by_ref": description["provenance"]["observer_ref"],
        "realized_value_summary": "Requested detail",
        "disclosure": "Selected detail",
        "typed_description": description,
    }


@pytest.mark.parametrize("host", ["experiment-evidence-record-v1", "experiment-run-v1"])
@pytest.mark.parametrize("change", ["address", "nested-address", "carrier", "phase", "nested-carrier", "nested-phase"])
def test_profile_owners_are_bound_to_fact_and_lifecycle_carrier(host, change):
    payload = profiled_payload(host)
    binding = payload["facts"][0]["profile_bindings"][0]
    if change.startswith("nested"):
        binding["children"] = [deepcopy(binding)]
        binding = binding["children"][0]
        binding["binding_id"] = "child"
    if change.endswith("address"):
        binding["owner"]["canonical_address"] = "#/nodes/a/private"
    elif change.endswith("carrier"):
        binding["owner"]["owning_contract_id"] = (
            "experiment-run-v1" if host == "experiment-evidence-record-v1" else "experiment-evidence-record-v1"
        )
    else:
        binding["owner"]["lifecycle_phase"] = "authoring"
    model, carrier = carrier_payload(payload, host)
    with pytest.raises(ValidationError, match="profile.*owner"):
        model.model_validate(carrier)


@pytest.mark.parametrize("host", ["experiment-evidence-record-v1", "experiment-run-v1"])
def test_valid_profile_owner_round_trips_in_its_carrier(host):
    payload = profiled_payload(host)
    model, carrier = carrier_payload(payload, host)
    value = model.model_validate(carrier)
    assert model.model_validate_json(value.model_dump_json()).typed_description == value.typed_description


@pytest.mark.parametrize("nested", [False, True])
def test_backend_selected_fact_cannot_forge_observed_profile_basis(nested):
    payload = profiled_payload()
    binding = payload["facts"][0]["profile_bindings"][0]
    if nested:
        binding["children"] = [deepcopy(binding)]
        binding = binding["children"][0]
        binding["binding_id"] = "child"
    binding["provenance"].update(basis="observed", evidence_refs=["forged-evidence"])
    with pytest.raises(ValidationError, match="profile.*basis"):
        TypedRealizationDescriptionModel.model_validate(payload)


@pytest.mark.parametrize("basis", [ObservationBasis.OBSERVED, ObservationBasis.INDEPENDENTLY_VERIFIED])
def test_profile_evidence_must_join_the_externally_verified_reference(basis):
    from raes_contracts.domain_profiles import (
        DomainProfileAdmissionPolicyModel,
        DomainProfileNamespaceAdmissionModel,
        DomainProfileResolutionContextModel,
    )

    payload = profiled_payload("experiment-run-v1")
    payload["facts"] = payload["facts"][:1]
    payload["coverage"] = []
    payload["provenance"].update(
        basis=basis.value, evidence_refs=[{"ref_kind": "evidence-record", "ref_id": "verified-evidence"}]
    )
    binding = payload["facts"][0]["profile_bindings"][0]
    binding["provenance"].update(basis="observed", evidence_refs=["unverified-evidence"])
    # Parser rejects a profile claim that does not join its descriptive provenance.
    with pytest.raises(ValidationError, match="profile.*evidence"):
        TypedRealizationDescriptionModel.model_validate(payload)
    binding["provenance"]["evidence_refs"] = ["verified-evidence"]
    value = TypedRealizationDescriptionModel.model_validate(payload)
    selector = ObservationSelector(semantic_scope="/nodes/a", data_kind="field", names=("family",))
    demands = _demands(selector, purpose="realization-description", required=True)
    context = DomainProfileResolutionContextModel(
        namespace_admissions=(
            DomainProfileNamespaceAdmissionModel(
                namespace="com.example.private", authority="urn:example:authority", trust_decision_id="admitted"
            ),
        ),
        definitions=(),
    )

    def report(reference, validator):
        return realization_description_report(
            ObservationDemandResolution(demands),
            {selector.key: AchievedObservationValue(value, basis, evidence_ref=reference)},
            evidence_validator=validator,
            profile_context=context,
            profile_policy=DomainProfileAdmissionPolicyModel(allow_opaque_exchange=True),
        )

    with pytest.raises(ValueError, match="evidence"):
        report("different-verified-reference", lambda *_: True)
    with pytest.raises(ValueError, match="unsatisfied"):
        report("verified-evidence", lambda *_: False)
    assert report("verified-evidence", lambda *_: True)[0].value.facts[0].profile_bindings[
        0
    ].provenance.evidence_refs == ("verified-evidence",)
