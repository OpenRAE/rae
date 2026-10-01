"""EXP-731 relation-aware trial realization regression coverage."""

from __future__ import annotations

import copy
from dataclasses import replace

from raes.scenario import ExpandedScenario
from raes.validator import SemanticValidator
from raes_contracts.canonical import canonical_json_digest
from raes_contracts.contracts import ExperimentTaskModel
from raes_processor.trial_compiler import compile_admitted_trial_plan
from test_exp_731_evidence_requirement_refinement import (
    _authority_ref,
    _relation,
    _scenario_ref,
)


def _family_with_supported_authored_requirement(family: ExpandedScenario) -> ExpandedScenario:
    payload = family.model_dump(
        mode="python",
        by_alias=True,
        exclude_unset=True,
        exclude={"expansion_provenance"},
    )
    payload["evidence_requirements"] = {
        "event-log": {
            "description": "Retain the admitted participant behavior field.",
            "source_class": "processor_backend",
            "scope": "network",
            "window": "run",
            "channel": "trace",
            "artifact_role": "observation",
            "media_types": ["application/json"],
            "sensitivity": "plain",
            "redaction": "none",
            "integrity": "checksum",
            "retention": "run_lifetime",
            "loss_disclosure": "required",
            "output_contract": "participant-behavior-history-event-stream-v1",
            "field_selectors": ["/0/action_contract_address"],
        }
    }
    updated = ExpandedScenario.model_validate(payload)
    SemanticValidator(updated).validate()
    updated._set_semantic_validated(True)
    return updated


def _request_with_valid_task_extension():
    from test_sce_002_trial_compiler import _request
    from test_sce_002_trial_realization import _request_with_processor

    base_request = _request(run_count=2)
    request = base_request.with_family(_family_with_supported_authored_requirement(base_request.family))
    capture_spec = next(iter(request.capture_specs.values()))
    task_payload = request.task.model_dump(mode="json")
    task_payload["scenario_ref"] = _scenario_ref(request.family)
    authority_ref = _authority_ref("task", task_payload)
    relation = _relation(request.family, authority_ref, relation_kind="extend")
    relation["capture_spec_ref"] = {
        "ref_kind": "capture-spec",
        "ref_id": capture_spec.capture_spec_id,
        "ref_version": capture_spec.spec_version,
    }
    relation["capture_requirement_ref"] = "auth-log-evidence"
    task_payload["evidence_requirement_relations"] = [relation]
    task = ExperimentTaskModel.model_validate(task_payload)

    backend_key = next(key for key in request.apparatus_manifests if key[0] == "backend")
    backend = request.apparatus_manifests[backend_key]
    backend_payload = backend.model_dump(mode="json")
    offers = backend_payload["capabilities"]["observation"]["capture_offers"]
    base_offer = copy.deepcopy(offers[0])
    base_offer.update(
        {
            "offer_id": "compiler-fixture-authored-event-log",
            "source_classes": ["processor_backend"],
            "channel_kinds": ["backend-log"],
            "channel_refs": [],
            "integrity_modes": ["checksum"],
            "sensitivity": "plain",
            "retention_policy_refs": ["run_lifetime"],
        }
    )
    offers.append(base_offer)
    admitted_backend = type(backend).model_validate(backend_payload)
    backend_ref = request.apparatus.manifest_refs[0].model_copy(
        update={"ref_digest": canonical_json_digest(admitted_backend.model_dump(mode="json"))}
    )

    processor_request = _request_with_processor()
    processor_manifests = {
        key: manifest for key, manifest in processor_request.apparatus_manifests.items() if key[0] == "processor"
    }
    processor_refs = [
        reference
        for reference in processor_request.apparatus.manifest_refs
        if reference.subject_ref.ref_kind == "processor"
    ]
    apparatus = request.apparatus.model_copy(update={"manifest_refs": [backend_ref, *processor_refs]})
    input_refs = request.input_refs.model_copy(
        update={"task_digest": canonical_json_digest(task.model_dump(mode="json"))}
    )
    return replace(
        request,
        task=task,
        input_refs=input_refs,
        apparatus=apparatus,
        apparatus_manifests={backend_key: admitted_backend, **processor_manifests},
    )


def test_trial_realization_revalidates_relations_against_the_authoring_scenario(monkeypatch) -> None:
    import raes_processor.trial_realization as realization_module
    from test_sce_002_trial_realization import _realization_inputs

    request = _request_with_valid_task_extension()
    result = compile_admitted_trial_plan(request)
    assert result.plan is not None
    plan = result.plan
    entry = next(iter(plan.entries.values()))
    calls = []
    original = realization_module.compile_scoped_evidence_requirement_demands

    def guarded(scenario, capture_specs, relations, *, relation_scenario=None):
        calls.append((scenario, capture_specs, relations, relation_scenario))
        return original(
            scenario,
            capture_specs,
            relations,
            relation_scenario=relation_scenario,
        )

    monkeypatch.setattr(realization_module, "compile_scoped_evidence_requirement_demands", guarded)
    realized = realization_module.realize_admitted_trial_entry(
        inputs=_realization_inputs(request, plan, request.task),
        plan_entry_id=entry.plan_entry_id,
    )

    assert len(calls) == 1
    assert calls[0][2] == tuple(request.task.evidence_requirement_relations)
    assert calls[0][3] is request.family
    assert [demand.address for demand in realized.execution_plan.model.capture_demands] == [
        "evidence_requirements.event-log",
        "capture_specs.capture-techvault-evidence-v1.capture_requirements.auth-log-evidence",
    ]
