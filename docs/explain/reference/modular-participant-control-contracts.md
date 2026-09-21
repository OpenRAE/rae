# Modular participant-control contracts

API-424 publishes portable records and a structural provider protocol for
[sem-235/rev1](../../../specs/formal/participant-semantics/modular-participant-control.md).
The architectural authority is ADR-108 at
`ebb70a34b8e7d1cc8964c443841ae57e12ed1014`; the semantic publication is #1070,
merged at `65ca8e41`. These contracts implement neither provider installation
nor effect dispatch. RUN-320 remains the orchestration owner.

## Published boundaries

| Contract | Meaning |
| --- | --- |
| `participant-control-selection-v1` | Exact apparatus/profile/mechanism bindings, typed slots, applicability, acyclic dependencies and finite bounds |
| `participant-control-evaluation-v1` | Immutable admitted context, all typed contributions, declared/effective support, composition and separate realization receipts |
| `participant-control-teaching-profile-v1` | Closed wire projection of teaching-influence/rev1; two tokens, union propagation, retained memory and no release |

The normative schemas are in `contracts/schemas/participant-runtime/`, with
per-contract publication records, fixtures and identical `schema_bundle()`
output. Installed distributions include all three schemas and the teaching
profile in the `raes_contracts` corpus. This is a participant-control profile,
not an SDL extension, interoperability profile or backend-allocation profile.

`ParticipantControlProvider` lives in `raes_backend_protocols.protocols`.
Its `resolve(request)` returns a tuple of typed results and performs no world
effects. The operator constructs the provider; scenario content cannot name
imports, executables or configuration expressions. The protocol deliberately
does not support runtime method-presence checks as evidence of capability.
All nested request/result values are frozen, with detached immutable tuples.
Proposed provider-state references are speculative, not committed state.

## Validation and authority

```python
from raes_contracts.contracts import (
    parse_participant_control_evaluation,
    validate_participant_control_resolved_context,
)

def validate_received_record(encoded, trusted_resolver):
    record = parse_participant_control_evaluation(encoded)
    validate_participant_control_resolved_context(record, trusted_resolver)
    return record  # Validated record, not permission to execute an effect.
```

Ingress rejects duplicate members, non-finite numbers, excessive bytes/depth,
unknown fields, domain/revision mismatches and mistyped results. Public parser
and resolver failures contain no rejected values. Direct Pydantic exceptions
are internal diagnostics and must not be returned to a participant.

The trusted resolver returns `ParticipantControlValidationContext` from
independently admitted operator state, never from indexes supplied by the
provider. It establishes the exact request, safe-to-disclose artifacts,
installed bindings, effective support, resolved results, effect authorizations,
incumbent gate evidence and owner receipts. Evidence hashes alone prove none
of these facts. API-409/API-423 occurrence validators and SEM-233 relation
validation retain their existing ownership; inject requests additionally join
the existing `ParticipantInjectDelivery` artifact and its visibility basis.
Other effect authorizations must be resolved by their incumbent owners before
entering `authorized_effects`; that map binds the full intent digest to K.

For independently resolved backend manifests, the support callback calls
`raes_backend_protocols.participant_control_admission.resolve_participant_control_support`.
This checks the manifest content and reuses API-407's evidence/strength resolver.
The governed `participant_modular_control` feature requires both selection and
evaluation contracts. It does not advertise support in any backend. Declaration,
installation, effective support and observed realization remain separate.
Non-exact support remains explicitly weakened/blocked in revision 1; an
authority reference never upgrades its strength or removes another obligation.

Conformance reports evaluation validation as `structural-context-required`.
Without `control_context_resolver`, `validate_contract_payload` returns
`conformance.semantic-context-required`; schema validation is not a trusted
semantic verdict. Selection and teaching-profile checks make structural claims.
Selection/evaluation records occupy the processor/backend operational plane,
not participant-visible history. Every participant disclosure still needs
the incumbent projection, authority, audience and final-sink checks.

## Identity and composition

K includes the entire admitted run/apparatus, participant/episode, subject,
crossing/direction, sink/audience/destination, controller/authority, policy,
state cut, expected heads, inputs/provider states, memory, clock/order/phase,
trigger/predecessors and causal counters. No missing coordinate is a wildcard.
Changing a selection requires a new admitted request/cut; historical records
are immutable. Trusted state authenticates any selection transition.

New-record digests use RFC 8785 JCS plus SHA-256 over the complete JSON model,
including explicit null/default fields. Arrays retain wire order. Contributor
ids are ordered by `(instance_id, slot_id)`; blockers and teaching tokens are
sorted and duplicate-free. The teaching-profile digest covers its full closed
artifact. The incumbent SEM-233 profile keeps its existing digest convention.
Crossing artifact digests cover the original wire projection without adding
unset optional fields; inject-delivery and manifest digests cover their full
normalized model. A digest is neither a credential nor execution identity.

Every selected slot has a result or explicit absence record. Mandatory facts
must resolve; mandatory decisions must permit, and transitive dependencies
must be satisfied. Advisory negatives do not implicitly veto. Every contributor
is retained even on conflict, failure or unsupported support. Empty optional
selection preserves incumbent gates. Unordered interacting effects conflict;
different strings do not establish independence. Delay windows use one clock
and intersect; incompatible transformations/routes/handoffs/lifecycle requests
conflict without an arrival-order winner.

Ordering never substitutes for target compatibility. A pause, interruption,
cancellation or shutdown cannot precede an inject, handoff, permit, delay or
transformation whose affected target must remain live. Participant, episode and
run scopes are compared by their typed coordinates. Workflow/execution
membership is not expressed in these targets, so it conservatively overlaps
until the owning authority can express a compatible contract. The reverse
order (operation while live, then shutdown) is distinct. Audit/review/denial
records do not themselves require live targets.

Requested effects use closed MPC-09 alternatives. Review binds its withheld
parent, obligation, supervisory authority, approval/denial and expiry/resumption;
delay binds a clock/window; lifecycle binds scope, operation and authority.
Transformation and inject results retain fresh identity. Required predecessors
withhold the parent until a fresh evaluation; subsequent effects have separate
outcomes. The logical key is `(run, trigger root, rule id/revision, slot, firing
epoch)`, excluding retry/cut/transport identity. Per-rule firing history and
per-root budgets travel with K and must come from trusted retained state.
Conflicting logical content remains recordable, never selected by ordering.

K also carries bounded `prior_effect_claims`: the retained key, allocated
effect id and full canonical intent digest for each replay-relevant claim.
They must match the admitted run/root and retained firing epochs; the total
consumption counter includes them and may also include other historical claims.
Only previously unclaimed keys consume new effects, fan-out or depth budget.
An unchanged replay at an exhausted budget remains recordable, not permission
to dispatch again. Same key with changed content is a conflict, including when
there is no remaining budget. Duplicate identities preserve every phase
blocker and every dependency edge; no first-arriving variant wins.

Owner receipts distinguish applied, failed, indeterminate, unsupported and
withheld. Validation does not prove atomic commit, crash recovery, exactly-once
execution, current dispatch freshness, provider protection, learning outcomes,
backend equivalence or noninterference.

## Runtime orchestration (RUN-320)

The reference runtime consumes these contracts; it does not extend them.
`RuntimeControlPlane(participant_control=...)` binds one admitted
`ParticipantControlSelectionModel` to exact operator-created provider
instances and one trusted resolver
(`raes_runtime.participant_control_binding`). Provider objects are passed in
already constructed: no scenario field, import path, URL, environment value or
method probe selects executable code, and the binding is refused unless the
backend declares `participant_modular_control` support.

At each governed sink — action ingress, control ingress and egress
serialization — the runtime resolves the admitted request for that exact cut,
checks it against the live crossing (participant, episode, direction,
audience, controller, the occurrence's own subject, the committed crossing
record's event identity and digest, policy revision and every expected history
head), then invokes each selected provider
once through `ParticipantControlProvider.resolve` behind the mutation
authority's re-entry fence. Returned models are rebuilt from their portable
projection. A provider exception, malformed return or absent slot becomes an
explicit `failed`/`missing` result: a contributor is never dropped and a
failure never permits. What a composition *admits* is decided once, by API-424,
so a rejected proposal — from a conflict, stale cut, unsupported or weakened
mechanism, or denial — is never promoted into a retained claim or a receipt
binding by one index while another refuses it.

Composition uses the contract owner's own
`derive_control_composition`, so the runtime reproduces no blocker, conflict
or disposition rule. The validated evaluation joins the crossing's atomic
commit as an append-only `participant_control_evaluation_history` record
before any backend call or participant disclosure; a non-eligible composition
commits its refusal instead, with bounded `control_evaluation_id`,
`control_selection_id` and `control_disposition` audit references.

The admitted context must also carry what its causal root already consumed.
The runtime folds the committed history for that run and trigger root and
refuses a context that declares fewer retained claims, firing epochs, consumed
effects or resolution attempts than the history proves — consumed effects as a
watermark of what committed contexts declared and newly admitted, not merely a
count of retained claims — so one root cannot
re-spend an exhausted budget, re-admit a claimed key at a later cut, or be
re-resolved without limit by declaring a fresh attempt each time. An
evaluation spends an attempt whether or not it resolves an effect.

Admitted effects are dispatched separately by
`dispatch_participant_control_effects`, after the parent committed. An
eligible composition dispatches its subsequent effects; a composition blocked
only by required predecessors dispatches exactly those, leaving the parent
withheld until it is reevaluated at a fresh cut. Within a phase the declared
`predecessor_effect_ids` graph is the execution order — record order is
serialization — and a dependent whose predecessor did not apply is withheld
rather than run. Each effect is a new operation through the incumbent owner of
its closed target kind: an inject through the governed participant-directed
delivery crossing, a handoff through the RUN-310 controller transition. The
owner input must be the effect the request names, not merely one in the same
scope — the inject's result identity, cut and disclosure, and the handoff's
declaration, expected state revision and completion obligation are all bound
before submission. The owner's crossing evidence, which names the audience its
crossing is decided for, is part of that resolver-supplied input and is bound
to the admitted cut's audience; the caller that requests a drain supplies
nothing the owner sees. An owner the resolver cannot supply, or one whose input
does not bind, is reported `unsupported` with zero dispatch.

Splitting dispatch from the commit does not change whose effect it is. An
effect acts for the principal of the operation that admitted it — the record
whose committed transition appended the evaluation, which the ADR-104 store
already names as that transition's result history head. The drain caller is
authorized before any committed state is read, exactly as every incumbent
participant mutation is — an authenticated principal with a mutating role,
bound to the target and the participant — and may request execution without
becoming the principal: each effect is submitted to its owner as the originating principal,
restricted to its bindings for this participant, so a principal can never
cause an effect it could not perform itself, and an owner's refusal is a fixed
property of that origin rather than of whoever drains. The principal's scopes
are those recorded when its operation was admitted: the runtime holds no
principal registry to re-resolve them, so revoking a principal afterwards does
not withdraw an effect it already caused — the owner's own policy admission at
the current cut is the check that still applies.

Before any owner is invoked, the effect is claimed durably under a context that
retains the originating actor, authorization scope, target and run and names
that operation as parent. The claim is keyed by the logical effect key `(run,
trigger root, rule id/revision, slot, firing epoch)` under the origin's actor,
so every drain resolves the same claim and none can execute an effect twice —
PC-11 allocates identity once per key, so a later evaluation that re-requests
a key reports the first outcome and never claims it under another origin — and
the store's replay validation binds it to the effect's content, so an
unrelated record under that key is refused rather than read. The whole drain —
scan, claims, submissions and records — runs under one held mutation. An
outcome is read from the owner operation the claim submitted, resolved inside
the owner's own claim scope so another actor's record under the derived key
never answers: an accepted receipt is admission, not application, so a refused
owner operation is `failed`. With no owner record, only the owner's own refusal
of the request is an outcome of the effect; any other error propagates and
leaves the claim open. Both owners claim write-ahead, so an open claim with no
owner record is PC-11's durable proof that dispatch never began, and a later
drain resumes it; anything that may have begun is never repeated. A known outcome is recorded in the same atomic commit that closes the
claim, as a content-identified realization transition that never rewrites the
committed evaluation. An uncertain outcome is not recorded: its claim stays
open, startup recovery classifies it through the incumbent lifecycle, a later
drain reads the owner record rather than repeating the action, and an
uncertain prerequisite authorizes no dependent. A claim recovery has already
terminalized is immutable, so once its owner's record proves the outcome it is
appended under a record linked to that claim — which the store admits only
after an operator has resolved the claim through the incumbent recovery
lifecycle, so a drain never reports an outcome as recorded while that barrier
stands. A withhold and an unsupported
owner are likewise recomputed on each drain rather than recorded, so nothing
that depends on the drain caller is ever persisted as an outcome. The history
itself is runtime-owned: a backend result may carry it forward but never add,
drop or edit a record, and the local store's schema 6 records the carrier
explicitly, so a build that predates it refuses the store instead of rewriting
it without its retained claims.

The legacy SEM-233 final-sink path is retained but explicitly negotiated:
`enforce_final_sink_flow_control` selects that adapter once at construction
instead of discovering a resolver method per sink.

## Verification map

All paths are repository-relative. These are bounded contract witnesses,
not runtime-delivery claims.

- [x] API-424: closed, versioned portable selection and public provider protocol → `implementations/python/packages/raes_backend_protocols/protocols.py:33`.
- [x] API-424: exact profile, mechanism, implementation, configuration, authority and evidence → `implementations/python/packages/raes_contracts/contracts/participant_control_selection.py:35`.
- [x] API-424: exact apparatus, participant, crossing, policy/cut, history, provider state and causality → `implementations/python/packages/raes_contracts/contracts/participant_control_coordinates.py:170`.
- [x] API-424: typed results, all contributors and explicit resolution/composition/realization dispositions → `implementations/python/packages/raes_contracts/contracts/participant_control_results.py:81`.
- [x] API-424: reuse incumbent carriers, distinguish declaration/installation/effects → `implementations/python/packages/raes_contracts/contracts/participant_control_resolution.py:192`.
- [x] API-407: unambiguous participant feature support distinct from general realization → `implementations/python/packages/raes_backend_protocols/participant_control_admission.py:12`.
- [x] API-409: external proposal, approval/denial, direction, intervention, handoff, override and cancellation retain incumbent controller/order/policy/provenance/disposition → `implementations/python/packages/raes_contracts/contracts/participant_control_validation.py:27`.
- [x] API-423: plain-data ingress/egress, transformation, disclosure, intervention and inject with bounded provenance, without duplicate transport → `implementations/python/packages/raes_contracts/contracts/participant_control_resolution.py:81`.
- [x] SEM-235: revisioned composition, closed domains, joins, source/propagation/memory/release and world-boundary semantics retain their existing publication → `specs/formal/participant-semantics/modular-participant-control.md:16`.
- [x] SEM-235: finite selections, mandatory/advisory roles, acyclic dependencies and absence/failure behavior → `implementations/python/packages/raes_contracts/contracts/participant_control_composition.py:40`.
- [x] SEM-235: typed effects, fresh identity, exact causal scope and finite budgets → `implementations/python/packages/raes_contracts/contracts/participant_control_effect_composition.py:120`.
- [x] SEM-235: SEM-233 historical meaning retained through its owning validator → `implementations/python/tests/test_api_424_security_profile.py:92`.
- [x] issue: closed schemas, matching publication and valid/invalid portable fixtures → `implementations/python/tests/test_api_424_publication.py:13`.
- [x] issue: independently installed backend consumer imports/resources → `implementations/python/tests/test_corpus_packaging.py:306`.
- [x] issue: no open taint/label/policy/effect/plugin/context/metadata authority or executable selector/private payload → `implementations/python/tests/test_api_424_participant_control_contracts.py:25`.
- [x] issue: method presence, importability or manifest term do not prove installed support → `implementations/python/tests/test_api_424_capability_admission.py:57`.
- [x] issue: multiple mechanisms, IFC-triggered inject and conflict without arrival-order winner → `implementations/python/tests/test_api_424_control_effects.py:118`.
- [x] issue: downgrade remains disclosed and non-eligible → `implementations/python/tests/test_api_424_composition_boundaries.py:67`.
- [x] issue: stale cuts and dishonest capability contextual fixtures → `implementations/python/tests/test_api_424_publication.py:75`.
- [x] issue: finite JSON ingress, including exponent-overflow rejection → `implementations/python/packages/raes_contracts/json_ingress.py:39`.
- [x] RUN-320: admitted selection bound to exact operator-created providers, never discovered code → `implementations/python/packages/raes_runtime/participant_control_binding.py:59`.
- [x] RUN-320: exact-cut resolution, protocol invocation, composition and commit before any effect → `implementations/python/packages/raes_runtime/participant_control_orchestration.py:76`.
- [x] RUN-320: append-only evaluation history in the ADR-104 store, across both supported stores → `implementations/python/packages/raes_contracts/participant_control_evaluation_history.py:17`.
- [x] RUN-320: schema 6 records the evaluation carrier; an older build refuses the store → `implementations/python/packages/raes_runtime/control_plane_store_record_migration.py:164`.
- [x] RUN-320: governed effect dispatch through incumbent owners, idempotent on the logical key → `implementations/python/packages/raes_runtime/participant_control_effects.py:195`.
- [x] RUN-320: the owner input is bound to the complete typed target before submission → `implementations/python/packages/raes_runtime/participant_control_effects.py:359`.
- [x] RUN-320: durable per-root attempt consumption, not a per-request bound → `implementations/python/packages/raes_runtime/participant_control_causal_state.py:56`.
- [x] RUN-320: the drain caller is authorized before any committed state is read → `implementations/python/packages/raes_runtime/participant_control_receipts.py:85`.
- [x] RUN-320: an effect acts for, and is claimed under, the operation that admitted it → `implementations/python/packages/raes_runtime/participant_control_receipts.py:199`.
- [x] RUN-320: the effect is submitted to its owner as the originating principal → `implementations/python/packages/raes_runtime/participant_control_receipts.py:140`.
- [x] RUN-320: one held mutation spans the drain's scan, claims, submissions and records → `implementations/python/packages/raes_runtime/participant_control_effects.py:92`.
- [x] RUN-320: a known outcome closes its claim and appends its realization in one commit → `implementations/python/packages/raes_runtime/participant_control_records.py:52`.
- [x] SEM-235: one definition of what a composition admits serves every consumer → `implementations/python/packages/raes_contracts/contracts/participant_control_composition.py:363`.
- [x] RUN-320: the implicit SEM-233 resolver hook is replaced by an explicitly selected adapter → `implementations/python/packages/raes_runtime/control_plane_composition.py:38`.
