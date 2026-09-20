"""The legacy security profile retains its owning SEM-233 relation and joins."""

from dataclasses import replace

import pytest
from participant_control_contract_fixtures import evaluation_payload, ref
from raes_contracts._canonical import canonical_json_digest
from raes_contracts.contracts import ParticipantControlEvaluationModel, ParticipantFlowControlRelationModel
from raes_contracts.contracts.participant_control_composition import control_digest
from raes_contracts.contracts.participant_control_coordinates import ControlArtifactReferenceModel
from raes_contracts.contracts.participant_control_resolution import (
    control_references,
    validate_participant_control_context,
)
from test_api_424_composition_boundaries import refresh
from test_api_424_control_resolution import record_and_context
from test_sem_233_flow_control_contracts import _context_relation_payload, _validation_context


def security_record_and_context():
    relation = ParticipantFlowControlRelationModel.model_validate(_context_relation_payload())
    owner = _validation_context()
    crossing = owner.crossing_records[-1]
    sink = relation.sink_decisions[0]
    payload = evaluation_payload()
    selection = payload["request"]["selection"]
    profile = ref("participant-boundary-flow-policy-v1", "profile")
    profile["digest"] = relation.profile.profile_digest
    selection["required_profiles"] = [profile["ref"]]
    selection["bindings"][0]["profiles"] = [profile]
    selection["slots"] = selection["slots"][:1]
    context = payload["request"]["context"]
    context.update(
        participant_address=crossing.participant_address,
        episode_id=crossing.episode_id,
        subject=crossing.occurrence.subject.model_dump(mode="json"),
        policy=crossing.occurrence.policy.model_dump(mode="json"),
        crossing={
            **ref(crossing.event_id, "crossing"),
            "digest": canonical_json_digest(crossing.model_dump(mode="json", exclude_unset=True)),
        },
        sink_ref=sink.sink.sink_ref,
        audience_ref=sink.sink.audience_scope_ref,
        destination_ref=sink.sink.destination_ref,
        controller_ref=crossing.occurrence.controller_ref,
        authority=ref(crossing.occurrence.authority_basis_refs[0], "authority"),
        order=11,
        expected_history_heads=[ref(head, "history") for head in sink.expected_history_head_refs],
    )
    context["state_cut"].update(cut_ref=context["policy"]["decision_cut_ref"], anchor_order=8, history_prefix_length=9)
    selection["bindings"][0]["applicability"][0].update(
        participant_address=context["participant_address"],
        sink_ref=context["sink_ref"],
        subject_kind=context["subject"]["subject_kind"],
    )
    payload["results"] = payload["results"][:1]
    payload["results"][0]["payload"] = {
        "kind": "ifc-fact",
        "domain": "sem-233/rev1",
        "label_ref": sink.label_ref,
        "relation": {
            **ref(relation.document_id, "flow-relation"),
            "revision": relation.document_revision,
            "digest": control_digest(relation),
        },
    }
    payload["composition"]["contributing_result_ids"] = ["result-fact"]
    refresh(payload)
    record = ParticipantControlEvaluationModel.model_validate(payload)
    _, trusted = record_and_context()
    safe = set(control_references(record))
    safe.update(ControlArtifactReferenceModel.model_validate(ref(item)) for item in owner.known_evidence_refs)
    safe.update(
        ControlArtifactReferenceModel.model_validate(ref(item, "authority")) for item in owner.known_authority_refs
    )
    return record, replace(
        trusted,
        admitted_request=record.request,
        safe_references=frozenset(safe),
        installed_bindings={"influence": record.request.selection.bindings[0]},
        effective_support={"influence": record.support[0]},
        resolved_results={"result-fact": record.results[0]},
        authorized_effects={},
        crossing_records=tuple(owner.crossing_records),
        crossing_subjects=tuple(owner.crossing_subjects),
        crossing_policies=tuple(owner.crossing_policies),
        flow_relations={relation.document_id: relation},
        flow_contexts={relation.document_id: owner},
    )


def test_security_fact_uses_incumbent_label_and_crossing_binding():
    record, context = security_record_and_context()
    validate_participant_control_context(record, context)


def test_security_fact_cannot_self_certify_owning_flow_relation():
    record, context = security_record_and_context()
    with pytest.raises(ValueError):
        validate_participant_control_context(record, replace(context, flow_contexts={}))


def test_incumbent_profile_file_read_is_bounded_before_decode(monkeypatch, tmp_path):
    from io import BytesIO
    from pathlib import Path

    from raes_contracts.participant_flow_policy_profiles import load_participant_boundary_flow_policy_profile_from_path

    class BoundedStream(BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 256 * 1024 + 1, "profile read must have a finite bound"
            return super().read(size)

    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: BoundedStream(b" " * (256 * 1024 + 1)))
    with pytest.raises(ValueError, match="profile JSON or contract is invalid"):
        load_participant_boundary_flow_policy_profile_from_path(
            "participant-boundary-flow-policy-v1", tmp_path / "profile.json"
        )
