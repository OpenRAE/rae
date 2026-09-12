"""Generic backend callback and lifecycle tests; scenario values are fixture data."""

from dataclasses import replace

import pytest
from raes_backend_stubs.stubs import create_stub_target
from raes_contracts.contracts.realization_descriptions import TypedRealizationDescriptionModel
from raes_contracts.observation_demand import (
    AchievedObservationValue,
    ObservationBasis,
    ObservationLifecycleStage,
    ObservationSelector,
)
from raes_contracts.planning import ProvisioningPlan
from raes_runtime.control_plane import RuntimeControlPlane
from raes_runtime.control_plane_store import InMemoryControlPlaneStore
from test_issue_1209_descriptions import description_payload
from test_issue_1212_runtime_boundaries import _demands, _runtime


@pytest.mark.parametrize("retention", ["disable", "forbid", "require"])
def test_typed_description_uses_existing_retention_and_recovery(retention):
    selector = ObservationSelector(semantic_scope="/nodes/a", data_kind="field", names=("family",))
    demands = _demands(
        selector,
        purpose="realization-description",
        collection="require" if retention == "require" else "disable",
        retention=retention,
        export="forbid",
        required=True,
    )
    calls = []
    supplied = TypedRealizationDescriptionModel.model_validate(description_payload())

    def describe(requested, *_):
        calls.append(requested)
        return AchievedObservationValue(supplied, ObservationBasis.BACKEND_SELECTED)

    runtime = _runtime(selector, stages=frozenset({ObservationLifecycleStage.RETENTION}), describer=describe)
    target = replace(create_stub_target(), observation_runtime=runtime)
    store = InMemoryControlPlaneStore()
    control = RuntimeControlPlane(target, store=store)
    receipt = control.submit_provisioning(ProvisioningPlan(observation_demands=demands))
    assert receipt.accepted
    assert control.get_operation(receipt.operation_id).state.value == "succeeded"
    assert calls == [selector]
    recovered = RuntimeControlPlane(target, store=store).observation_execution(receipt.operation_id)
    payload = store.load_records()[receipt.operation_id].result_payload
    assert ("linux" in _stored_scalar_values(payload)) == (retention == "require")
    if retention == "require":
        description = recovered.realized_form_disclosures[0].typed_description
        assert [fact.fact_id for fact in description.facts] == ["family"]
        assert description.facts[0].value.value == "linux"
        assert description.provenance.basis is ObservationBasis.BACKEND_SELECTED
    else:
        assert recovered.realized_form_disclosures == ()
    assert calls == [selector]  # Recovery does not reacquire nonretained data.


def test_five_selected_components_are_typed_fixture_data_without_collection():
    selector = ObservationSelector(semantic_scope="/nodes", data_kind="field", names=("family",))
    demands = _demands(
        selector,
        purpose="realization-description",
        collection="require",
        retention="require",
        export="forbid",
        required=True,
    )
    payload = description_payload()
    payload["coverage"] = []
    payload["facts"] = [
        {
            "fact_id": f"choice-{i}",
            "subject": f"/nodes/n{i}/family",
            "state": "known",
            "value": {"kind": "literal", "origin": "backend", "value": choice},
        }
        for i, choice in enumerate(("linux", "kali", "abstract", "private-system", "linux"))
    ]
    selected = TypedRealizationDescriptionModel.model_validate(payload)
    runtime = _runtime(
        selector,
        stages=frozenset({ObservationLifecycleStage.RETENTION}),
        describer=lambda *_: AchievedObservationValue(selected, ObservationBasis.BACKEND_SELECTED),
    )
    target = replace(create_stub_target(), observation_runtime=runtime)
    control = RuntimeControlPlane(target, store=InMemoryControlPlaneStore())
    receipt = control.submit_provisioning(ProvisioningPlan(observation_demands=demands))
    assert control.get_operation(receipt.operation_id).state.value == "succeeded"
    execution = control.observation_execution(receipt.operation_id)
    assert not execution.lifecycle.collected
    assert not execution.lifecycle.exported
    description = execution.realized_form_disclosures[0].typed_description
    assert len(description.facts) == 5
    assert [fact.value.value for fact in description.facts] == ["linux", "kali", "abstract", "private-system", "linux"]
    assert all(fact.provenance is None for fact in description.facts)
    assert description.provenance.evidence_refs == ()


def test_protection_applies_to_typed_values_before_the_retention_transaction():
    selector = ObservationSelector(semantic_scope="/nodes/a", data_kind="field", names=("family",))
    demands = tuple(
        demand.model_copy(update={"redaction": "scrub"})
        for demand in _demands(
            selector,
            purpose="realization-description",
            collection="require",
            retention="require",
            export="forbid",
            required=True,
        )
    )
    source = description_payload()
    source["facts"][0]["value"]["value"] = "private-sentinel"
    supplied = TypedRealizationDescriptionModel.model_validate(source)

    def redact(values):
        payload = values[0].model_dump(mode="json")
        payload["facts"][0].update(state="withheld", value=None, limitations=["Selected policy withheld this value."])
        return (TypedRealizationDescriptionModel.model_validate(payload),)

    runtime = _runtime(
        selector,
        stages=frozenset({ObservationLifecycleStage.RETENTION}),
        describer=lambda *_: AchievedObservationValue(supplied, ObservationBasis.BACKEND_SELECTED),
        redactors={"scrub": redact},
    )
    target = replace(create_stub_target(), observation_runtime=runtime)
    store = InMemoryControlPlaneStore()
    control = RuntimeControlPlane(target, store=store)
    receipt = control.submit_provisioning(ProvisioningPlan(observation_demands=demands))
    assert control.get_operation(receipt.operation_id).state.value == "succeeded"
    assert all(
        "private-sentinel" not in _stored_scalar_values(record.result_payload)
        for record in store.load_records().values()
    )
    recovered = control.observation_execution(receipt.operation_id).realized_form_disclosures[0].typed_description
    assert recovered.facts[0].state == "withheld"
    assert recovered.facts[0].value is None
    assert supplied.facts[0].value.value == "private-sentinel"


def test_typed_evidence_does_not_replace_required_emitted_bytes():
    from raes_contracts.contracts import ExperimentEvidenceRecordModel
    from raes_contracts.evidence_satisfaction import validate_experiment_run_evidence
    from test_issue_1112_capture_admission import _evidence_bundle

    task, run, spec, record, _payload = _evidence_bundle()
    payload = record.model_dump(mode="json")
    payload["typed_description"] = description_payload()
    typed_record = ExperimentEvidenceRecordModel.model_validate(payload)
    with pytest.raises(ValueError, match="concrete byte reader"):
        validate_experiment_run_evidence(
            task,
            run,
            capture_specs={spec.capture_spec_id: spec},
            evidence_records={typed_record.evidence_record_id: typed_record},
            artifact_readers={},
        )


def test_protection_cannot_restore_unrequested_fact_depth():
    from raes_contracts.observation_demand import ObservationDemandResolution, realization_description_report

    selector = ObservationSelector(semantic_scope="/nodes/a", data_kind="field", names=("family",))
    demands = _demands(selector, purpose="realization-description", required=True)
    source = description_payload()
    source["facts"][1].update(
        state="known", value={"kind": "literal", "origin": "backend", "value": "unrequested-private-detail"}
    )
    supplied = TypedRealizationDescriptionModel.model_validate(source)
    value = AchievedObservationValue(supplied, ObservationBasis.BACKEND_SELECTED)
    report = realization_description_report(
        ObservationDemandResolution(demands), {selector.key: value}, protector=lambda *_: value
    )
    assert [fact.fact_id for fact in report[0].value.facts] == ["family"]
    assert "unrequested-private-detail" not in report[0].value.model_dump_json()


def test_requested_window_excludes_other_time_scope():
    from raes_contracts.description_reporting import project_description

    selector = ObservationSelector(
        semantic_scope="/nodes/a", data_kind="field", names=("family",), window_refs=("another-window",)
    )
    source = TypedRealizationDescriptionModel.model_validate(description_payload())
    assert project_description(source, selector, ObservationBasis.BACKEND_SELECTED).facts == ()


def _stored_scalar_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _stored_scalar_values(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _stored_scalar_values(child)
    else:
        yield value


@pytest.mark.parametrize("allow_opaque", [False, True])
def test_runtime_description_profiles_preserve_explicit_host_policy(allow_opaque):
    from raes_contracts.description_reporting import DescriptionProfileAdmission
    from raes_contracts.domain_profiles import (
        DomainProfileAdmissionPolicyModel,
        DomainProfileNamespaceAdmissionModel,
        DomainProfileResolutionContextModel,
    )
    from raes_runtime.observation_execution import ConfiguredObservationRuntime
    from test_issue_1209_description_profiles import profiled_payload

    selector = ObservationSelector(semantic_scope="/nodes/a", data_kind="field", names=("family",))
    demands = _demands(
        selector, purpose="realization-description", collection="require", retention="require", required=True
    )
    supplied = TypedRealizationDescriptionModel.model_validate(profiled_payload("experiment-run-v1"))
    capabilities = _runtime(
        selector, stages=frozenset({ObservationLifecycleStage.RETENTION}), describer=lambda *_: None
    ).capabilities
    runtime = ConfiguredObservationRuntime(
        capabilities=capabilities,
        describers={
            "test-observation": lambda *_: AchievedObservationValue(supplied, ObservationBasis.BACKEND_SELECTED)
        },
        description_profiles=DescriptionProfileAdmission(
            context=DomainProfileResolutionContextModel(
                namespace_admissions=(
                    DomainProfileNamespaceAdmissionModel(
                        namespace="com.example.private",
                        authority="urn:example:authority",
                        trust_decision_id="local-admission",
                    ),
                ),
                definitions=(),
            ),
            policy=DomainProfileAdmissionPolicyModel(allow_opaque_exchange=allow_opaque),
        ),
    )
    target = replace(create_stub_target(), observation_runtime=runtime)
    store = InMemoryControlPlaneStore()
    control = RuntimeControlPlane(target, store=store)
    receipt = control.submit_provisioning(ProvisioningPlan(observation_demands=demands))
    assert receipt.accepted
    assert control.get_operation(receipt.operation_id).state.value == ("succeeded" if allow_opaque else "failed")
    if allow_opaque:
        recovered = RuntimeControlPlane(target, store=store).observation_execution(receipt.operation_id)
        assert (
            recovered.realized_form_disclosures[0].typed_description.facts[0].profile_bindings
            == supplied.facts[0].profile_bindings
        )
