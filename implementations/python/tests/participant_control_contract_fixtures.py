"""Small portable API-424 examples; no backend realization is claimed."""

from copy import deepcopy

DIGEST = "sha256:" + "a" * 64


def ref(identity, kind="evidence"):
    if (identity, kind) == ("teaching-influence", "profile"):
        from raes_contracts._canonical import canonical_json_digest
        from raes_contracts.contracts.participant_control_profiles import load_teaching_influence_profile

        return {
            "kind": kind,
            "ref": identity,
            "revision": "rev1",
            "digest": canonical_json_digest(load_teaching_influence_profile().model_dump(mode="json")),
        }
    return {"kind": kind, "ref": identity, "revision": "rev1", "digest": DIGEST}


def selection_payload():
    return {
        "schema_version": "participant-control-selection/v1",
        "selection_id": "selection-1",
        "semantic_revision": "sem-235/rev1",
        "apparatus": ref("apparatus-1", "apparatus"),
        "required_profiles": ["teaching-influence"],
        "bindings": [
            {
                "instance_id": "influence",
                "profiles": [ref("teaching-influence", "profile")],
                "mechanism": ref("propagation", "mechanism"),
                "protocol_revision": "participant-control-provider/v1",
                "implementation": ref("provider-artifact", "implementation"),
                "configuration_digest": DIGEST,
                "authority": ref("teaching-authority", "authority"),
                "memory_scope": ref("retained-memory", "memory"),
                "applicability": [
                    {
                        "participant_address": "participants.student",
                        "episode_id": "episode-1",
                        "direction": "ingress",
                        "sink_ref": "teaching-observation",
                        "phase_ref": "practice",
                        "subject_kind": "participant-observation",
                    }
                ],
                "evidence": [ref("binding-evidence")],
                "limitations": [ref("explicit-flows-only", "limitation")],
            }
        ],
        "slots": [
            {
                "slot_id": "fact",
                "instance_id": "influence",
                "kind": "ifc-fact",
                "role": "mandatory",
                "dependencies": [],
            },
            {
                "slot_id": "rule",
                "instance_id": "influence",
                "kind": "effect-request",
                "role": "mandatory",
                "dependencies": [{"slot_id": "fact", "kind": "ifc-fact"}],
            },
        ],
        "bounds": {
            "max_depth": 2,
            "max_effects": 2,
            "max_fanout": 2,
            "max_firings_per_rule": 1,
            "max_attempts": 3,
            "expires_at_order": 20,
        },
        "evidence": [ref("selection-evidence")],
    }


def context_payload():
    context = {
        "run": ref("run-1", "run"),
        "apparatus": ref("apparatus-1", "apparatus"),
        "participant_address": "participants.student",
        "episode_id": "episode-1",
        "subject": {
            "subject_kind": "participant-observation",
            "contract_id": "participant-observation-envelope-v1",
            "subject_ref": "observation-1",
            "subject_revision": "rev1",
            "subject_digest": DIGEST,
            "participant_address": "participants.student",
            "episode_id": "episode-1",
        },
        "crossing": ref("crossing-1", "crossing"),
        "direction": "ingress",
        "sink_ref": "teaching-observation",
        "audience_ref": "student-audience",
        "destination_ref": "student",
        "controller_ref": "teacher",
        "authority": ref("teaching-authority", "authority"),
        "policy": {
            "policy_id": "teaching-policy",
            "policy_revision": "rev1",
            "policy_digest": DIGEST,
            "policy_decision_ref": "crossing-decision-1",
            "decision_cut_ref": "cut-1",
            "effective_order": 1,
            "valid_from_order": 0,
            "valid_until_order": 20,
        },
        "state_cut": {
            "cut_kind": "sequence_prefix",
            "cut_ref": "cut-1",
            "history_domain": "participant_behavior_history",
            "order_model": "behavior_history_order",
            "anchor_event_ref": "event-1",
            "anchor_order": 1,
            "history_prefix_length": 2,
            "predecessor_event_refs": ["event-0"],
        },
        "expected_history_heads": [ref("history-head", "history")],
        "provider_states": [{"instance_id": "influence", "state": ref("state-1", "provider-state")}],
        "inputs": [ref("observation-1", "input")],
        "memory_scope": ref("retained-memory", "memory"),
        "clock": ref("clock-1", "clock"),
        "order": 1,
        "phase_ref": "practice",
        "trigger_root": "root-1",
        "trigger": ref("event-1", "trigger"),
        "predecessors": [],
        "depth": 0,
        "effects_consumed": 0,
        "prior_effect_claims": [],
        "rule_firings": [],
        "attempt": 1,
    }
    from raes_contracts._canonical import canonical_json_digest

    context["crossing"]["digest"] = canonical_json_digest(crossing_payload(context))
    return context


def crossing_payload(context):
    return {
        "event_id": "crossing-1",
        "schema_name": "participant-crossing-occurrence",
        "schema_version": "1.0.0",
        "event_type": "participant-crossing-occurrence",
        "extension_policy": "closed",
        "participant_address": context["participant_address"],
        "episode_id": context["episode_id"],
        "occurred_at": "2026-09-20T00:00:00Z",
        "recorded_at": "2026-09-20T00:00:00Z",
        "ingested_at": "2026-09-20T00:00:00Z",
        "clock_authority": "clock-1",
        "ordering_basis": "logical_clock",
        "actor_ref": "teacher",
        "producer_ref": "runtime",
        "authorization_scope": "teaching-authority",
        "provenance_refs": ["result-evidence"],
        "evidence_refs": ["result-evidence"],
        "object_marking_refs": ["public"],
        "occurrence": {
            "direction": "ingress",
            "interaction_kind": "observation",
            "audience_scope_ref": "student-audience",
            "subject": context["subject"],
            "controller_ref": "teacher",
            "authority_basis_refs": ["teaching-authority"],
            "policy": context["policy"],
            "effective_order": 1,
            "order_model": "logical_clock",
            "backend_posture": "exact",
            "loss_and_limitations": ["explicit-flows-only"],
            "stage": "requested",
            "request_id": "request-1",
            "requested_operation": "admission",
            "action_or_projection_ref": "observation-1",
            "required_evidence_refs": ["result-evidence"],
        },
    }


def delivery_payload():
    return {
        "participant_ref": "participants.student",
        "inject_ref": "inject-1",
        "occurrence": {"event_ref": "event-inject-1", "script_ref": "script-1", "story_ref": "story-1"},
        "source_item_ref": "reflection-source",
        "result_item_ref": "reflection-result",
        "observation_boundary_ref": "teaching-observation",
        "delivery_kind": "disclosure",
        "delivery_policy": {
            "policy_ref": "teaching-policy",
            "policy_revision": "rev1",
            "exposure_policy_ref": "exposure-1",
            "audience_scope_ref": "student-audience",
            "visibility_basis_ref": "visibility-1",
            "disclosure_basis_ref": "disclosure-1",
        },
        "order_basis": "orchestration-occurrence-and-shared-time",
        "temporal_constraint_refs": ["expiry-20"],
        "evidence_requirement_refs": ["effect-evidence"],
        "failure_disposition": "reject-no-delivery",
    }


def inject_payload():
    from raes.participant_inject_delivery import ParticipantInjectDelivery
    from raes_contracts._canonical import canonical_json_digest

    target = {
        "kind": "inject",
        "delivery_ref": ref("delivery-binding", "inject-delivery"),
        "inject_ref": "inject-1",
        "event_ref": "event-inject-1",
        "script_ref": "script-1",
        "story_ref": "story-1",
        "source_item_ref": "reflection-source",
        "result_item_ref": "reflection-result",
        "participant_address": "participants.student",
        "episode_id": "episode-1",
        "disclosure_ref": ref("disclosure-1", "disclosure"),
    }
    target["delivery_ref"]["digest"] = canonical_json_digest(
        ParticipantInjectDelivery.model_validate(delivery_payload()).model_dump(mode="json")
    )
    return target


def effect_payload(target=None):
    return {
        "kind": "effect-request",
        "effect_id": "effect-1",
        "key": {
            "run_ref": "run-1",
            "trigger_root": "root-1",
            "rule_id": "hint-followup",
            "rule_revision": "rev1",
            "slot": "followup",
            "firing_epoch": "epoch-1",
        },
        "rule": ref("hint-followup", "rule"),
        "authority": ref("teaching-authority", "authority"),
        "phase": "subsequent",
        "predecessor_effect_ids": [],
        "target": target or inject_payload(),
        "evidence": [ref("effect-evidence")],
    }


def evaluation_payload():
    selection = selection_payload()
    from raes_contracts._canonical import canonical_json_digest

    context = context_payload()
    digest = canonical_json_digest(context)
    results = []
    for slot_id, payload in (
        (
            "fact",
            {
                "kind": "ifc-fact",
                "domain": "teaching-influence-domain/rev1",
                "tokens": ["coached-hint"],
                "source_refs": [ref("observation-1", "input")],
            },
        ),
        ("rule", effect_payload()),
    ):
        results.append(
            {
                "result_id": "result-" + slot_id,
                "slot_id": slot_id,
                "instance_id": "influence",
                "binding_digest": canonical_json_digest(selection["bindings"][0]),
                "context_digest": digest,
                "status": "resolved",
                "payload": payload,
                "evidence": [ref("result-evidence")],
                "next_provider_state": None,
            }
        )
    return {
        "schema_version": "participant-control-evaluation/v1",
        "evaluation_id": "evaluation-1",
        "request": {"selection": selection, "context": context},
        "results": results,
        "support": [
            {
                "instance_id": "influence",
                "feature": "participant_modular_control",
                "declaration_ref": ref("backend-manifest", "manifest"),
                "declared_level": "exact",
                "effective_level": "exact",
                "status": "resolved",
                "context_digest": digest,
                "installation": ref("installation-1", "installation"),
                "constraints": [],
                "limitations": [ref("explicit-flows-only", "limitation")],
                "evidence": [ref("support-evidence")],
                "downgrade_authority": None,
            }
        ],
        "composition": {
            "rule_revision": "sem-235/rev1",
            "disposition": "eligible",
            "blockers": [],
            "contributing_result_ids": ["result-fact", "result-rule"],
            "incumbent_gate_disposition": "permit",
            "incumbent_gate_evidence": ref("gate-evidence"),
        },
        "realizations": [],
    }


def cloned_payload():
    return deepcopy(evaluation_payload())
