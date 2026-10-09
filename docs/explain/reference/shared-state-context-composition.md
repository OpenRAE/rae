# Shared state and derived context composition

API-410 requires plain-data contracts for shared operational state and for
derived, participant-relevant context. Two published contract families meet it:

- [`participant-shared-state-record-v1`](../../../contracts/schemas/participant-runtime/participant-shared-state-record-v1.json)
  (RUN-307) reports one revision of a shared-state address.
  [`runtime-snapshot-v1`](../../../contracts/schemas/snapshots/runtime-snapshot-v1.json)
  holds the current record for each address in `shared_state_records` and an
  append-only `shared_state_history`.
- [`participant-context-view-v1`](../../../contracts/schemas/control-plane/participant-context-view-v1.json)
  (API-408, SEM-214) carries one participant-local view. It declares its
  source layers, transformation rule, freshness basis, comparability claim,
  evidence, visibility projection, and limitations.

This note derives one view from one published shared-state revision. It then
lists the validator that checks each binding between the two contracts.

## The shared-state revision

The published fixture
[`serialized-service-state-commit.json`](../../../contracts/fixtures/participant-runtime/participant-shared-state-record-v1/valid/serialized-service-state-commit.json)
reports revision `rev8` of `hosts.web01.service.http`. The record belongs to
participant `participants.red.llm` in episode `ep-red-004`, and its
predecessor is `hosts.web01.service.http@rev7`. Its one `read_write` access
read `rev7` and wrote `rev8` in snapshot `snapshots.sim.tick88`, inside atomic
group `joint-13`. The record names `serialize` as its conflict policy,
`projections.shared-state.default.v1` as its visibility basis, and
`redaction.shared-state.v1` as its redaction policy.

## A view derived from that revision

<!-- api-410-composition-view:start -->
```json
{
  "view_id": "views.context.participants.red.llm.service-posture.tick88",
  "participant_address": "participants.red.llm",
  "episode_id": "ep-red-004",
  "generated_at": "2026-05-26T10:50:02Z",
  "source_snapshot_ref": "snapshots.sim.tick88",
  "view_ref": "views.context.service-posture.v1",
  "meaning_ref": "semantics.context.service-posture.v1",
  "participant_scope": "participant_local",
  "audience_scope": "participant_visible",
  "observation_point": "sim.tick.88",
  "derived_from_refs": ["snapshots.sim.tick88", "hosts.web01.service.http@rev8", "obs-red-87"],
  "source_layers": [
    {
      "source_id": "shared-state-snapshot",
      "source_layer": "source_snapshot",
      "ref": "snapshots.sim.tick88",
      "temporal_relation": "same_observation_point",
      "observation_point": "sim.tick.88",
      "evidence_refs": ["evidence.sim.tick88.state"],
      "provenance_refs": ["provenance.backend_realized"]
    },
    {
      "source_id": "observation-red-87",
      "source_layer": "participant_observation",
      "ref": "obs-red-87",
      "temporal_relation": "bounded_staleness",
      "observation_point": "sim.tick.87",
      "freshness_basis_ref": "freshness.one-tick.v1",
      "evidence_refs": ["obs-red-87"],
      "provenance_refs": ["provenance.backend_realized"]
    }
  ],
  "transformation": {
    "transformation_rule_ref": "rules.context.service-posture.v1",
    "description": "Summarize the committed service configuration with the participant's last observation",
    "input_source_ids": ["shared-state-snapshot", "observation-red-87"],
    "output_semantics_ref": "semantics.context.service-posture.v1"
  },
  "comparability": {
    "comparability_class": "portable_with_disclosed_weakening",
    "comparison_basis_ref": "comparability.service-posture.same-rule-and-projection.v1",
    "backend_disclosure_refs": ["backend-disclosures.tick-serialized-writes.v1"],
    "limitations": ["Comparable only for backends that serialize shared-state writes per simulation tick"]
  },
  "evidence_refs": ["evidence.sim.tick88.state", "obs-red-87"],
  "provenance_refs": ["provenance.backend_realized"],
  "semantic_limitations": ["The observation input can lag the committed revision by one tick"],
  "derivation_basis_ref": "rules.context.service-posture.v1",
  "payload_ref": "evidence.context.red.service-posture.tick88",
  "visibility_projection_ref": "projections.shared-state.default.v1",
  "marking_definition_refs": ["markings.internal.v1"],
  "redaction_policy_ref": "redaction.shared-state.v1"
}
```
<!-- api-410-composition-view:end -->

- Scope: the view is participant-local. It names the same participant and
  episode as the record.
- Derivation: the `source_snapshot` layer cites the snapshot that holds the
  revision, and `derived_from_refs` names the exact revision. No
  `source_layer` value names a shared-state record directly.
- Freshness: the snapshot layer applies at the view's observation point,
  `sim.tick.88`, which is the record's logical order. The observation from
  `sim.tick.87` is `bounded_staleness` and names its freshness basis.
- Visibility and evidence: the view applies the record's visibility basis and
  redaction policy, keeps its marking, and cites its evidence.
- Limitations: the view discloses weakened comparability with a backend
  disclosure, and its semantic limitation states the one-tick lag.

An ACT-604
[`participant-information-state-record-v1`](../../../contracts/schemas/participant-runtime/participant-information-state-record-v1.json)
record can cite both carriers as sources: the shared-state record with relation
`shared_state_projection` and the view with relation `derived`.
`validate_participant_information_state_context` then requires both sources to
resolve to the record's participant, episode, visibility projection, and
redaction policy. The shared-state record must also fall inside the record's
sequence cut. Each cited ref must name the record it resolves to: a shared-state
ref names the record's `event_id` or `state_address`, and a view ref names its
`view_id` or `view_ref`.

[`test_issue_253_api_410_contracts.py`](../../../implementations/python/tests/test_issue_253_api_410_contracts.py)
loads the JSON above through the model and the published schema. It joins the
view with the published record in one information state. It also exercises the
join, access-marker, freshness-basis, view-source, and retrieval rejections
from the next section.

## Where each binding is checked

| Binding | Checked by |
| --- | --- |
| A record has a revision or digest. Each access carries the revision markers its kind needs. | `ParticipantSharedStateRecordModel`, `ParticipantSharedStateAccessModel`, and the published schema |
| A record matches its snapshot key, and each access names the record's address. Behavior and joint-action state references resolve. | `iter_participant_shared_state_snapshot_violations` and `iter_participant_concurrency_snapshot_violations`, at backend apply and in snapshot conformance |
| Shared-state history is append-only. | `iter_participant_shared_state_history_transition_violations`, at backend apply |
| A joint-action conflict class matches the overlapping reads and writes. | `ParticipantJointActionRecordModel` and the snapshot concurrency validator |
| View source ids are unique, transformation inputs name declared layers, and layer refs appear in `derived_from_refs` or `source_snapshot_ref`. | `ParticipantContextViewModel` only; the published schema does not express these rules |
| A stale layer names its freshness basis. Weakened comparability names a backend disclosure. A participant-visible archival source needs a view rule and a redaction policy. | `ParticipantContextViewModel` and the published schema |
| Shared-state and view sources agree with one information state. | `validate_participant_information_state_context` |
| A runtime view names the snapshot revision it came from. An unknown participant or episode gets no view. A governed view needs exactly one audience binding. | `get_participant_context_view` and `GET /participants/{participant_address}/context` |

## Limits

- No validator reads a view together with the snapshot it cites. Nothing checks
  that `source_snapshot_ref` or `derived_from_refs` resolve to a recorded
  revision.
- Standalone validation of a shared-state record does not compare its accesses
  with the record. The model, the published schema, and
  `validate_contract_payload` accept an access to another address, or a
  `write_revision` that differs from `revision`. Only the snapshot validator
  compares addresses, and no validator compares an access revision with the
  record's `revision`.
- No validator resolves `predecessor_revision_refs` against
  `shared_state_history`.
- The ACT-604 join admits any shared-state revision at or before the cut,
  including a superseded one, and a bare state-address ref that pins no
  revision. The host supplies `information_state_context_resolver`, which
  decides the record a ref resolves to; the runtime has no built-in resolver.
- No validator resolves an access's `atomic_group_ref` against the snapshot's
  joint-action records. The concurrency validator checks only the other
  direction: each state reference in a joint-action access set must name
  recorded shared state.
- The view model does not compare the `observation_point` of a
  `same_observation_point` layer with the view's observation point.
- The runtime retrieval path builds one `source_snapshot` layer. Over HTTP,
  that layer is the current snapshot revision, so the runtime does not build
  views like the example.
- A published contract does not show that a backend can compute a given view.
  No backend conformance profile requires `participant-context-view-v1`, and
  the conformance validator registry has no entry for it.
