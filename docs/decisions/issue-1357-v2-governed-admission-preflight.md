# Issue #1357 — v2 governed admission preflight

Scope: the public Python `admit_participant_decision_surface_selection_v2()`
entry point. The GitHub issue is the contract. This note records boundaries for
implementation; it does not change runtime behavior or ADR-095 semantics.

## Architecture decision

The v2 selection binder owns agreement with the delivered surface; ordinary
participant-action admission owns caller and ingress-crossing authority. Keep
that sequence. Forward the caller's original identity and crossing evidence
through the v2 entry point to `admit_participant_action()` together with the
bound request and existing retry context. The v1 selection entry point and
`ParticipantSubmissionOptions` already provide the submission-context pattern.
The v2 path currently forwards only `idempotency_key` and
`request_fingerprint`, so a configured governed ingress cannot receive the
identity and evidence that ordinary admission requires. Keep one canonical
submission-options vocabulary and shape check; do not create a v2 authority DTO.

`ParticipantActionAdmissionRequest` is the backend-neutral action request, not
the caller's authenticated identity or crossing evidence. The v2 selection is
a participant choice bound to a surface id, decision epoch, view digest and
delivery ref; it grants no new authority. The surface's derivation cut and
delivery cut are distinct from the fresh ingress crossing cut. Preserve their
participant/episode, action, audience, policy and occurrence identities through
the existing validators. Neither a selected action nor a delivery record may
synthesize caller authority, required evidence or a crossing occurrence.

## Cross-cutting boundaries

| Layer | Existing owner and required behavior |
| --- | --- |
| Published shape and proposal | `contracts/schemas/control-plane/participant-decision-surface-v2.json`, `raes_contracts.contracts.participant_decision_surface_v2`, `raes_contracts.participant_binding_v2` and `ParticipantActionAdmissionRequest` own surface/selection fields, agreement, apparatus resolution and governed argument-shape validation. Use their typed carriers and existing checks; no duplicate schema or parser. |
| Exact-cut and disclosure | `validate_participant_decision_surface_v2_anchor()` re-resolves the derivation anchor; `validate_participant_decision_surface_v2_delivery()` re-resolves authoritative delivery. ADR-095 and SEM-226 keep projection, disclosure, delivery, participant observation, selection and admission distinct. Never put assurance-only refs or crossing evidence in the participant-facing view. |
| Submission and authentication | `ParticipantSubmissionOptions.from_fields()` owns optional submission shape. `ControlPlaneIdentity` and `_require_crossing_identity()` own authenticated principal, target, role and exact participant/controller binding. A governed ingress requires the original typed identity; `operation_actor_scope(None)` denotes a trusted embedded process and must not replace a served caller. |
| Crossing and policy | `ParticipantCrossingEvidence` supplies caller-owned evidence metadata; `action_crossing_intent()`, `prepare_participant_crossing()`, `participant_crossing_policy`, `participant_flow_sink` and API-424 control mediation derive and validate the live occurrence, policy, evidence, capability, audience and final-sink decisions. Evidence refs are claims to check against trusted resolver context, not proof by presence. Unknown, stale, mismatched or unauthorized context fails closed. |
| State and effect | `RuntimeMutationAuthority`, `control_plane_mutation()`, `external_control_plane_call()`, `expected_participant_history_heads()`, the operation record and atomic store commit own serialized state cuts, re-entry fencing, replay and durable crossing/action history. Preserve the existing pre-mutation check and recheck under the mutation permit; do not dispatch a backend action before the governed decision and claim. |
| Failure and observation | `_participant_binding_diagnostic()`, `_reject_diagnostics()`, `OperationReceipt`, `operation_admission_context()` and crossing denial audit own the current rejection forms. Bind early rejections to the supplied actor where available, and keep audit details and returned diagnostics bounded and value-free. Do not wrap ordinary `PermissionError`/`ValueError` into a new exception hierarchy or expose raw evidence/policy payloads. |

The public v2 method is a Python control-plane API; the current HTTP adapter
does not expose this admission method. Thus no new HTTP request body, auth
dependency, error envelope, configuration or environment binding is in scope.
If an HTTP route is later introduced, it must use `ControlPlaneSecurityConfig`
and the existing API authentication and response machinery, with typed identity
coming from the auth dependency rather than the request body. This change
needs no credential lookup, secret value, subprocess argument or environment
variable. Do not pass identity or evidence through `argv`, logging, diagnostic
text or participant-visible serialization. Existing operation commitments and
audit records remain the persistence surface; no new journal or cache.

## Verification boundary and anti-patterns

The targeted v2 runtime test should show a valid delivered selection reaches
governed ordinary admission with the correct authenticated actor and crossing
occurrence, then reject absent identity/evidence, stale surface or crossing
cut, wrong participant/episode/action/audience/controller, and unauthorized
role/target/subject. Check that rejection leaves action/behavior history and
backend effects absent, except for the incumbent denial audit or crossing
record where that boundary intentionally records one. Reuse the existing
`participant_crossing_fixtures.py` resolver, identity and evidence fixtures
alongside `test_sem_220_participant_decision_surface_v2_runtime.py`; preserve
the mutation/concurrency and replay tests for the same path. Run only targeted
local checks under `.ground-control.yaml`, `.gc/plan-rules.md` and `noxfile.py`;
broad suites belong to CI. The published schema is governed by
`contracts/schema-publication-manifest.json` and
`tools/check_generated_schemas.py`; this forwarding change does not call for a
schema edit or a second contract artifact.

Do not copy RUN-319 crossing validation into the v2 binder, infer a controller
from the chosen action, use the decision epoch as policy order, treat the
delivery ref as ingress evidence, turn a rejected crossing into success, or
relax an existing validator to fit a forwarded value. The next submission
context variation belongs in the shared `ParticipantSubmissionOptions` seam
and then passes through both selection entry points and ordinary admission;
it should not require another v2-only options parser.

Non-goals: changing the v2 wire schema, ADR-095, v1 historical meaning,
participant projection or delivery rules, policy semantics, backend execution,
HTTP routing, secret/config handling, or store formats. A separate mixed-runtime
support change must resolve the current v2 target guard against the ordinary
action path's mixed-runtime guard before claiming mixed admission support.
