# Issue 1358 Denied Egress Outcome Preflight

Date: 2026-09-24. Contract: issue #1358 (no Ground Control requirement).

## Decision boundary

The terminal operation status describes the **final release outcome**, after
API-423 crossing, SEM-233 flow-sink, and any selected modular control gates.
A permitted crossing decision is evidence that an earlier gate passed; it is
not evidence that a participant view was released. On a final flow-sink refusal,
retain that earlier decision and its history head, commit one `FAILED` operation
status with the existing flow-sink denial diagnostic, the denied audit, and the
resulting snapshot in the incumbent atomic participant transition. Keep the
accepted receipt as an immutable admission acknowledgment. The denied record
must have no releasable `result_payload`; the caller receives the existing
value-free `PermissionError` and no view.

`participant_flow_sink.py::flow_sink_denied_record()` already classifies an
ingress final-sink denial as `FAILED` and adds
`runtime.participant-flow-sink-denied` plus the canonical terminal diagnostic.
The egress path should reuse that classification with
`participant_crossing_commit.py::commit_prepared_crossing()` and its existing
claim, expected-head, revision, audit, and publication semantics. Do not add a
second terminal state, store method, audit stream, or exception hierarchy.
The operation record, audit, and history must describe one state cut before
the caller can receive any governed carrier.

History retains `requested`/`decided` (and a valid transformation, if any) as
earlier work. A denied release has no `delivered` or `observed` fact. The
actor-bound denial audit carries the distinct `flow_final_disposition` and
flow decision references; consumers must join that final fact with the
operation status rather than interpret an API-423 `permit` as delivery. The
current API-423 history validator permits a `delivery-attempted/withheld`
record only after an API-423 **deny**. In particular,
`_with_opacity_egress_observation(..., delivered=False)` cannot be used after
an API-423 permit followed by SEM-233 refusal. The current selected opacity
profile normalizes the API-423 decision to deny before this final-sink path;
retain that behavior. Do not rewrite a permitted decision, fabricate a
delivery attempt, or weaken the validator to make such a record pass. If an
explicit later-refusal history fact proves necessary, that is a portable-carrier
decision governed by ADR-009 and schema publication, not an ad hoc history
dictionary.

## Cross-cutting owners

| Boundary | Canonical incumbent and guardrail |
| --- | --- |
| Entry and authorization | `participant_retrieval.py` funnels status, history, context, decision-surface, and participant-directed views through `ParticipantViewSerialization` and `serialize_participant_view()`. `participant_crossing_policy.py::_require_crossing_identity`, `ControlPlaneIdentity` and audience bindings retain target, actor, participant, and audience authority. A stored operation id or idempotency key grants none. |
| Exact final permit | `control_plane_composition.py::select_final_sink_flow_control_resolver()` and `ControlPlaneConfiguration.enforce_final_sink_flow_control` select the resolver at construction; `participant_flow_sink.py::resolve_participant_flow_sink_decision()` binds the exact participant, episode, audience, sink kind, API-423 decision, and live history heads. `validate_participant_flow_control_resolved_context()` remains the semantic validator. Missing, stale, malformed, or throwing resolvers fail closed. Do not infer capability from a method found at call time or use an earlier permit as a final permit. |
| Crossing and opacity validation | `ParticipantCrossingIntent`, `ParticipantCrossingOccurrenceModel`, `validate_participant_crossing_occurrence_context()`, `validate_participant_opacity_runtime_enforcement()`, and `participant_crossing_state_cut.py` own shape, predecessor, authority, order, and head checks. `participant_crossing_egress.py::_view_subject()` and `_governed_egress_view()` own exact view digest and trusted transformation revalidation. Do not duplicate these checks in a new DTO or serializer. |
| Operation and persistence | `OperationState`, `OperationStatus`, `operation_terminal_diagnostics()`, `ControlPlaneOperationRecord`, `control_plane_store.py` transition and idempotency validators, `RuntimeDurabilityMixin`, `InMemoryControlPlaneStore`, and `LocalControlPlaneStore` own immutable receipt/context, legal `RUNNING -> FAILED`, atomic snapshot/record/audit commit, CAS, readback, and restart. `control_plane_store_records.py` is the strict persisted codec. A claim is not a terminal commit, and an exception from a store commit is not proof that nothing committed. |
| Readback and effects | `RuntimeControlPlane.get_operation()` reloads store records and enforces actor/scope read authority. Egress replay must classify the incumbent **status** before reading its payload, both for a prepared replay and when the atomic claim returns another operation id; only a committed `SUCCEEDED` record with a governed payload may release bytes. `participant_control_receipts.py::claim_outcome()` maps owner status to effect disposition, and `participant_control_effects.py` dispatches only from admitted evaluations. A denied egress owner must therefore resolve as failed, never applied. |
| Audit and exposure | `AuditEvent`, `control_plane_audit.py::require_audit_event_fields()`, and `flow_sink_audit_details()` own bounded, closed, value-free evidence. Use the existing `flow-sink-denied` reason; preserve the API-423 disposition as an earlier fact. `control_plane_api/_auth.py`, `_operation_routes.py`, `_responses.py`, `RequestSizeLimitMiddleware`, and `ControlPlaneSecurityConfig.strict_defaults()` retain authenticated reads and coarse redacted 4xx/5xx envelopes. Do not expose resolver exceptions, view payloads, credentials, or audit internals in logs or errors. |

## Security and extensibility checks

This repair changes no external request, target, manifest, environment, or
secret-binding shape. The existing `ControlPlaneConfiguration`, `RuntimeTarget`
manifest validation in `registry.py`, and explicit final-sink selection must
still admit the composed runtime. It introduces no secret resolution or
environment delivery: the existing value-free operation admission context and
audit allowlist keep sensitive request/view material out of durable diagnostics
and logs. It introduces no executable, process argument, subprocess, or
network endpoint, so no token may be moved into argv or a broad process
environment. If the result is surfaced through HTTP, retain the existing
authenticated status route and redacted error envelopes; direct runtime
retrieval retains its `PermissionError` boundary.

The reusable seam is the prepared crossing's final classification **at the
sink**, before `commit_prepared_crossing()`. It must work for each existing
`ParticipantViewSerialization` view and the selected concrete sink kind,
without branching on view model, backend name, or store provider. A future
final gate can use the same operation-status and atomic-commit semantics while
keeping its own validated decision and bounded audit details; it cannot turn
an earlier crossing permit into a terminal success.

## Assurance and scope

Targeted evidence should cover every non-permit SEM-233 class, no returned
payload, `FAILED` status with both denial and canonical terminal diagnostics,
one denied audit, preserved earlier crossing decision, and no delivered or
observed history. Exercise same-key readback (including an incumbent returned
by a racing claim), actor/scope mismatch, both stores, local-store close and
reopen, and the effect owner's failed disposition. Include the selected opacity
path so the API-423 `withheld` invariant is not accidentally violated. Build
on `test_issue_1003_final_sink_flow_enforcement.py`,
`test_issue_964_participant_opacity_runtime.py`,
`test_issue_1069_participant_control_effects.py`, and the existing operation,
idempotency, and store tests. Keep local verification targeted; CI owns the
full suite. `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, and
`tools/check_repo_policy.py` remain the workflow owners; a portable carrier
change would additionally require the published-schema manifest, generated
schema parity, coverage, and compatibility gates.

Non-goals: changing SEM-233 policy, broadening API-423 or opacity claims,
adding a new public lifecycle state or schema, changing authored workflows,
altering backend effects, adding an HTTP participant route, or retroactively
rewriting committed operations. Avoid treating `receipt.accepted`, an API-423
permit, a delivery-attempt label, or a thrown exception as the final outcome.
