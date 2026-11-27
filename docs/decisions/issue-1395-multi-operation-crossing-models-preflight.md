# Issue 1395: Multiple-operation participant-crossing models preflight

Date: 2026-10-13. Requirements: SEM-232, SEM-230, API-423, RUN-319.
Scope: offline model construction for #1395.

[ADR-100](adrs/adr-100-participant-crossing-bisimulation.md) already reserves
multiple fresh operations for a separate profile. Its crossing-kernel boundary
stands; no new ADR or runtime compatibility decision is made here. The
[#971 preflight](issue-971-participant-crossing-models-preflight.md) remains
applicable, especially its ingress, export, independence and assurance guards.
This note identifies the additional design constraints; it is not a transition
specification, implementation plan, or equivalence result.

The governed relation remains `divergence-preserving-branching-bisimulation`
between the declared initial states over the complete named carrier after only
the profile-declared hiding. Constructing a new pair establishes no such result.

## Architecture boundary

Keep `participant-crossing-dpbb-finite-v1@rev2`, its single-operation semantics,
profile bytes and retained bundle intact. Introduce a separately named,
revision-pinned multiple-operation profile inside the existing behavioral
relation family. Do not widen the old literals or reinterpret its parameter
kind. Preserve exact historical reproduction from the source closure named by
the old bundle, using its delivery checkout or retained revision-specific
sources. Changes to shared exporter/contracts/runtime sources can cause honest
old-source drift; repinning old evidence to new bytes does not resolve it.
The behavioral-relations and participant-semantics overview READMEs still name
the rev1 design target. Use ADR-100 and
[`participant-crossing-models.md`](../../specs/formal/participant-semantics/participant-crossing-models.md)
for the executable rev2 boundary; do not mistake those summaries for executable
profile admission or silently retarget the downstream program to the new scope.

The extension seam is **exact profile selection**: it selects the admitted
domains, operation budget, retry/history and failure scope, independently owned
transition authorities, projection/label partition, and output revision. Keep
serialization and bounded ingress nonsemantic. Adding a larger finite budget
must not require rewriting the serializer or historical profile, and admitting
another budget must not silently admit time, concurrency or controller handoff.
Do not introduce a general graph framework, generic retry engine, profile
registry, or second workflow.

Before model construction, the new governed transition authority must settle
the operation bound, complete domains, retry equality coordinates, observable
result protocol and failure actions below. Do not resolve missing semantics
inside exporters or tailor either model to a candidate correspondence. Any
change to ADR-100's accepted decisions uses ADR-059; published contract evolution
uses ADR-009/ADR-061. This note grants no change to runtime retry or enforcement.

Pin the represented operation families and runtime configuration. Action
ingress, supervisory control, retrieval projection and participant-directed
delivery share a crossing boundary but have different validation and effect
paths. `participant_retrieval.py::deliver_participant_directed_view()` governs
delivery of an already-projected carrier; it establishes neither consumption
nor observation. Existing `participant_control_effects.py` and compiler
`participant_inject_deliveries.py` own dispatch and DSL-142 binding. A generic
crossing label cannot establish coverage of those paths, transformed-ingress
revalidation, handoff, mixed dispatch, final-sink or modular-control gates.
Each belongs in the declared model scope or the explicit #972 mapping exclusions.

## Semantic guardrails

### Operation identity and retry eligibility

A fresh operation, an attempt, an API-423 occurrence `request_id`, an operation
receipt id, and a client idempotency key are different identities. Runtime
preparation can generate new occurrence ids even when the store returns an
incumbent receipt. The finite model must specify their correspondence, not use
one undifferentiated `request` coordinate for all of them.

Retain the result and retry-relevant context for **every** admitted operation,
including older refused or indeterminate operations. The single-operation
`last` coordinate cannot represent retrying the first operation after a second
one. A model ledger is a finite formal state coordinate, not a new production
repository or duplicate operation-record DTO.

A governed deny/unsupported decision can be an accepted operation with a
persisted failed outcome and crossing history. An unresolved policy also
produces `accepted=True` with a persisted `FAILED` operation, but
`_prepare_policy_unresolved()` appends no participant facts and keeps decision
and result heads equal. Authentication/identity rejection creates no crossing
operation; other operation-admission denials can return `accepted=False` with
rejection audit and no persisted operation. Preserve these separate paths:
receipt acceptance is not policy permission or successful execution. Neither
every refusal nor every fresh claim advances participant history. An admitted
second operation that changes no relevant head must not automatically make
the first key stale merely because the operation count increased.

Canonical runtime owners are `raes_runtime/control_plane_operation_context.py`,
`control_plane_admission.py` and `control_plane_store.py`:

- `idempotency_claim_identity()` scopes a key by actor and operation kind inside
  one target/run store. `require_idempotency_key()` owns its bounded ASCII shape;
  an empty key is the existing explicit no-idempotency case, not a replay key.
- `OperationAdmissionContext` binds actor, authorization scope, target, run,
  kind, request commitment and parent operation. Exact current context and
  fingerprint must match before disclosing an incumbent. Retained migrated
  claims have a separate compatibility path; do not silently include it.
- `_semantic_request()` in `participant_crossing_records.py` binds stable intent
  (excluding runtime-assigned effective order), policy identity/revision/cut,
  gates, required operation/support, downgrade permission, backend support,
  transformation and selected opacity binding. The intent also binds subject
  kind/ref/digest, participant/episode, audience, controller, authority bases,
  action/projection, markings and required evidence. Pin these dependencies or
  explicitly hold them constant; input-class equality alone is insufficient.
- `_require_same_idempotency_replay()` separately requires candidate decision
  heads to equal the incumbent decision **or result** heads. The immediate retry
  sees the operation's own result cut and remains eligible. Another operation
  advances history and makes the older key conflict even at unchanged policy.

`prepare_participant_crossing()` authenticates the current caller and resolves
current policy/support before constructing a candidate for claim matching.
Knowing a key or retaining a result is not authority to disclose it. Preserve
the actual route ordering, including replay returns that avoid a new effect;
do not add a cache lookup before authorization or repeat final-sink delivery
just to make retries look like fresh crossings.

The actual incumbent is returned through `_claim_record()`, in action
authorization, supervisory control or `commit_prepared_crossing()`. The normal preparation path does
not populate `PreparedParticipantCrossing.existing_receipt`; that optional field
and the early-return guards are not evidence of an early cache lookup. Policy,
context, sink, composition and transformation preparation can precede the claim.
Preserve that ordering or explicitly exclude the affected paths; skipping action
execution on replay does not imply zero resolver/provider calls. Preparation
callbacks must not be treated as a second action executor or safe evidence of
exactly-once external effects.

`expected_participant_history_heads()` in `participant_crossing_state_cut.py`
currently binds episode, behavior, control, crossing and control-evaluation
histories. Model the admitted history vector or justify its finite quotient;
one policy cut, a global provider snapshot revision, a history length, and this
vector are not interchangeable. Mixed-runtime paths add composition heads and
require separate admission or an explicit exclusion.

Each abstract and concrete authority must derive its own retry enabledness and
successors. Shared vocabulary, inert storage, codecs and canonical bytes are
appropriate; a shared replay classifier, gate table, transition oracle, runtime
execution helper or abstract-to-concrete generator would defeat independence.

The mandatory sequence is fresh A, immediate exact retry A, fresh B, then retry
A at unchanged policy. Preserve A's original outcome on conflict, and include
changed-input reuse, separate policy advancement, and repeated eligible retries
for each operation. A replay returns an existing receipt/result; it performs no
new action execution, logical result commit or participant-history append.
Action ingress returns a receipt, whereas egress reconstructs a validated
cached `result_payload`; neither is proof of a repeated effect or delivery.

`RuntimeControlPlane.get_operation()` is a separate status read: for a typed
identity, `_operation_read_allowed()` checks the original actor/authorization
scope and target, without resubmitting the key or requiring current history
equality. Old-key conflict therefore does not mean the old status disappeared.
The P2 route applies administrative read authority and returns the same 404 for
unknown and unauthorized operations. Admit or exclude this read explicitly in
the observation profile; status alone is not the delivered participant payload.

### Projection and complete finite carrier

Choose a fixed finite fresh-operation bound of at least two for the initial
profile, unless a separately justified finite history abstraction supports a
larger claim. State whether the environment admits exactly or at most that
many operations and what remains enabled after exhaustion. A semantic budget
is distinct from an exploration depth or resource cap. Enumerate every admitted
choice and retry ordering to reachable closure; no saturation, identity
recycling, head wraparound, sampled schedule or truncated graph is complete.
Define the budget unit separately from attempts and history commits: a retry or
conflict spends no fresh identity, while a refused claim can consume one without
an effect. Specify the treatment of unclaimed admission rejections. Unlimited
retries cannot carry unbounded attempt counters, fresh UUIDs or timestamps in a
finite state space; any discarded coordinate needs the declared observation
boundary or a justified quotient.

Derive head/order bounds from all admitted record/commit paths, including
refusal, authorization and terminalization. The runtime may append several
occurrences and perform authorization and terminal commits for one action;
`h1` cannot simply mean one API event or one provider revision. Any quotient
must preserve retry equality, result identity, visible ordering, enabledness
and hidden divergence. Forgetting an older entry or equating unequal heads
requires a preservation argument, not only matching example traces.

Declare whether operation/input identity and cached-result provenance are
visible to the participant/audience. If the observable alphabet changes, govern
the projection and label revision too. State-map coordinates and execution
counters alone cannot make distinctions visible to an AUT checker. Conversely,
do not expose private actor or policy data just to distinguish model states.
The old `crossing.delivery` replay protocol cannot silently acquire a claim
that a backend action or delivery occurred again.

Preserve refusal, unsupported and retry-conflict observations. Only the selected
profile's finite mediation classes may become `internal`; no native tau,
conflict, timeout, restart, response loss or history advance may be hidden by
calling it bookkeeping. The old decreasing internal rank is not automatically
valid after adding failure/restart paths: classify actual hidden cycles and
preserve divergence without assuming fairness. Unlimited visible retries in a
finite graph are different from unlimited fresh operations and hidden loops.
Completion of a crossing remains distinct from global deadlock/termination.

### Unknown outcomes and restart

Separate what the caller knows from the durable operation state and external
effect state. Losing a response after a successful commit is different from a
crash before claim, after claim, after authorization/effect, or during uncertain
terminal commit. An untimed profile may admit a declared response-loss event;
it must not infer timer, deadline, cancellation or latency semantics from it.

Reuse the existing meanings in `raes_contracts/operation_lifecycle.py` and
ADR-104. `control_plane_recovery.py` classifies accepted/running claims using
write-ahead provenance and validated effect observation; it does not blindly
execute again. Known absence requires evidence that no late effect remains
possible; an exception or timeout is insufficient. `control_plane_durability.py`
owns authoritative readback and poisoning after uncertain store outcomes.
`control_plane_admission.py` blocks new effectful claims while indeterminate
operations require resolution, while permitting eligible incumbent readback.

At minimum cover durable completed-result replay after a clean restart and
client uncertainty, and name which interrupted/uncertain-commit/reconciliation
paths remain uncovered. If modeled, those paths need explicit finite domains
and independently derived transitions. Do not call clean restart evidence a
crash-recovery or arbitrary-failure theorem. P0 process loss loses the run;
durable replay belongs to the admitted P1 boundary, not every store profile.
Ephemeral sensitive retry proof is intentionally lost on restart; do not
persist secret-derived equality material to make a model case pass.
Caller uncertainty is a formal knowledge coordinate, not a new persisted
`OperationState`. Whether completed, failed, cancelled or `INDETERMINATE`, an
incumbent readback reports the durable state; it does not authorize re-execution.

A conflicting key is not a recommendation to resubmit with a fresh key. A new
identity may duplicate a completed but unobserved effect, and indeterminacy can
forbid fresh mutation. Operator resolution is a separately authorized, linked
operation; do not turn it into an ordinary retry or erase the original claim.

## Cross-cutting layers and canonical incumbents

Module paths below are under `implementations/python/packages/`. These are
obligations for the intended implementation, not newly delivered checks.

| Layer | Existing owner and required boundary |
| --- | --- |
| File/JSON ingress | Extend `implementations/formal/participant_crossing/ingress.py` and `raes_contracts/json_ingress.py`: bounded regular-file reads, descriptor-relative no-follow opens, repository containment, duplicate-free object roots, nonfinite/depth rejection. Profiles are data, never executable modules or paths authorized merely by `SafeRef` syntax. Fail closed on unsupported host capabilities; no weaker symlink fallback. |
| Profile and semantic admission | Build on `BehavioralRelationProfileModel`, `_participant_crossing_profile.py`, `_behavioral_profile_loader.py` and exact catalog/profile revision loaders. Use closed typed parameters with strict integer bounds and single-owner cross-field/domain/label joins. The loader allowlist and historical lookup must admit the new identity. `_validate_profile_join()` and generated `crossing_profile_schema_join()` currently dispatch the old variant versus opacity; admitting a new union member alone will fail those joins. `behavioral_relations._validate_binding_profile()` currently checks the right carrier only for `ParticipantCrossingParametersModel`; every new binary variant must retain that check. Existing opacity consumers must reject the new variant before field access. No `dict[str, Any]` escape or parallel claim validator. |
| Published schema and packaging | `contracts/schemas/profiles/behavioral-relation-profile-v1.json`, `schema_bundle()`, schema invariants, valid/invalid fixtures, schema publication entry and manifest `last_change`, and `raes_contracts/corpus.py` own contract admission and distribution. Keep generated/published parity and wheel/sdist corpus parity, including exact historical profiles. Python acceptance alone does not admit a published profile. |
| Carrier/context validation | Reuse `ParticipantCrossingOccurrenceModel`, `ParticipantRuntimeBaseEnvelopeModel`, `validate_participant_crossing_occurrence_context()` and `participant_crossing_history.py` for synthetic contract fixtures and contextual predecessor/subject/policy/evidence joins. API-406 outcomes/history, API-409 control, and DSL-142 delivery retain ownership; no new generic message or duplicate receipt/status/occurrence schema. A valid carrier establishes neither execution nor observation. |
| Auth and policy | Offline construction opens no HTTP/auth route. Concrete derivation pins `participant_crossing_policy.py` identity, role, controller/subject and audience binding, deny-first independent gates and effective backend capabilities. Preserve legacy/opt-in/required adoption; governed checks remain mandatory once selected. SEM-233 flow-sink, RUN-320 modular-control and opacity interactions in ingress/egress must be represented or named as mapping exclusions, never bypassed to obtain agreement. |
| Host and runtime configuration | Later #972 fixtures use `ControlPlaneConfiguration`, `PlanScope`, admitted store profiles and typed `ControlPlaneIdentity` shapes. `control_plane_profiles.py`/profile admission and `control_plane_composition.py` validate provider capabilities and participant resolver/sink/modular bindings; a backend declaration alone is not installed enforcement. Target/run/episode/audience are not interchangeable. [ADR-104](adrs/adr-104-runtime-control-plane-architecture.md) and the [#1356 boundary](issue-1356-control-plane-participant-access-preflight.md) keep SDK objects/stores and privileged P2 identities inside the trusted host; a P2 audience binding does not restrict full-snapshot access. Any HTTP mapping retains `ControlPlaneSecurityConfig.strict_defaults()`, bounded body admission, composition seals and `no-store` responses. #1395 creates no served endpoint. |
| Env/secret shapes and OS exposure | No new env binding, secret resolver, credentials, listener, shell, network or subprocess checker is needed. Operational settings such as `RAES_REQUIREMENT_UID` cannot select semantics. Synthetic ids/counts/public source digests only; no live payload/policy capture, dotenv, environment dump, token/key in argv/URL, or secret-file access. Hashing a secret is not redaction. If later deployment fixtures touch env inputs, retain `raes/runtime_environment.py`, `runtime_generated_value.py`, `runtime_configuration.py`, `runtime_values.py` and `raes_contracts/secret_references.py` sensitivity/provenance, unique-name and literal/`value_from` gates. No new env syntax. |
| Persistence/concurrency | Runtime comparison uses `ControlPlaneStore.claim_record()`, immutable `OperationAdmissionContext`, `_require_same_idempotency_replay()`, `commit_participant_transition()`, revision CAS and append-only histories; in-memory and SQLite providers implement the same claim. Retain short transactions, mutation authority, authoritative reads, leases/private files, strict codecs, scope/migration checks, WAL durability and single-worker validation (`WEB_CONCURRENCY`, `UVICORN_WORKERS`). A sequential formal kernel does not certify SQLite, concurrent callers, multiple owners or external exactly-once effects. No new store/cache/index or proof fields in snapshots. |
| Errors/audit/observability | The exporter CLI already emits a fixed value-free failure. Use `Diagnostic`/`DiagnosticModel` and `portable_diagnostic_payload()` for structured diagnostics; this validates shape, not sensitive text, so messages and addresses must already be safe. Incumbent conformance sanitization is appropriate only at that boundary. Preserve HTTP `control_plane_api/_responses.py::_conflict_detail()` and redacted validation/internal-error envelopes if later mapping exercises P2. Never retain `str(exc)`, Pydantic inputs, tracebacks, raw keys, fingerprints, host paths or tool output. Existing module loggers and bounded outcome/count labels suffice. Atomic terminal audit, rejection audit, model evidence and ADR-065/066 observability/provenance surfaces stay separate. |
| Export and publication | Reuse `graph.py` for inert storage and `aut.py`/`export.py` for deterministic encoding, endpoint/initial/count/readback checks, original-label state maps and complete-bundle publication. Their current `VISIBLE`/`HIDDEN`, fixed paths, AUT regex, 4096-state and 2 MiB limits are single-profile assumptions: make admission follow the selected profile, keeping safety caps separate from semantic bounds. No silent edge loss when distinct hidden edges coalesce to `internal`; specify canonical duplicate handling. Preserve read-only drift checking, staged directory publication and refusal to overwrite changed evidence. |
| Source/artifact identity | `canonical_json_bytes()`/`canonical_json_digest()` own semantic JSON identities; raw source/AUT bytes have separate exact digests. Runtime `canonical_crossing_digest()` and projection normalization are existing mapping facts, not interchangeable RFC 8785 identities. `stable_projection_subject()` normalizes only declared runtime-owned revision paths, never caller subject/input changes. Pin both transition dependency closures, contract/normative/profile/projection sources, Python lock, exporter and retry/recovery/projection/store dependencies. The old `SOURCE_PATHS` alone omits several new obligations; a top-level file hash or commit id cannot cover them. Build in a fresh interpreter from a trusted checkout whose sources remain unchanged during collection; a disk hash cannot attest loaded code if those bytes race with imports. |
| Workflow and tool admission | Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`, authority/concept/behavioral-claim/schema/assurance gates, `noxfile.py`, `tools/nox_support`, `tools/verification_plan.py` and `.github/workflows/ci.yml`. Set `RAES_REQUIREMENT_UID` to the active requirement when the branch lacks a UID; this RUN-319 preflight uses `RUN-319`. Source-bound formal/specification research evidence uses [content-addressed branch captures](../develop/research-captures.md), not new numbered releases or edits to historical indexes. Later checker acquisition belongs to #974 and the tooling lock/admission/verified-installation owners in `implementations/tooling/README.md`; construction adds no checker dependency. |

The existing staged publisher assumes a trusted output parent and exclusive
publication. Path checks followed by `os.rename()` do not provide race-proof
containment or refusal to replace a concurrently created directory. Preserve
that trust boundary for fixed repository outputs. Any extension to writable,
untrusted or concurrently published destinations must pin the parent directory
and use no-follow, descriptor-relative publication with an atomic no-replace
guarantee. Per-file atomic replacement is insufficient for a complete bundle.

## Evidence and acceptance boundaries

Extend the incumbent `test_issue_971_crossing_{profile,models,export}.py`,
`crossing_model_fixtures.py`, behavioral-relation and JSON-ingress tests without
weakening old-profile rejection cases. Runtime anchors already cover immediate
replay, unchanged-policy history advancement and completed restart replay in
`test_run_319_participant_flow_policy.py`; scoped claims and strict durable
carriers are covered by `test_issue_1184_atomic_idempotency_claims.py` and
`test_issue_1187_control_plane_durable_carriers.py`. Recovery/failure anchors
include `test_issue_1179_startup_reconciliation.py`. These are reusable
behavioral expectations, not an abstract-model oracle or runtime mapping proof.

The incumbent `participant_crossing_fixtures.action_plane()` defaults to
`enforce_final_sink_flow_control=False`, and the restart case explicitly uses
that setting. Those cases establish retry behavior for that selected fixture,
not default SEM-233 enforcement. Pin the fixture configuration in later mapping
evidence; do not copy the disabled sink into a governed scope as a bypass.
Reuse the missing-policy and actor/scope readback cases to keep operation
acceptance, policy refusal, participant history and result visibility distinct.

Acceptance needs independent construction review, closure under every admitted
rule, every quantified domain and initial state, older-key and negative cases,
safe synthetic contract joins, exact deterministic export/readback, cross-
profile rejection, no partial publication, resource exhaustion and source drift.
Do not let fixture helpers recompute expected digests from the candidate and
thereby replace retained-revision checks. Report domain, state, transition and
initial-state counts separately; artifacts retain safe original-label/state
maps and acyclic source/profile/artifact commitments.

Normative, profile, projection, transition, runtime retry/recovery or contextual
contract drift invalidates affected current mapping evidence until reviewed and
rechecked. Immutable historical evidence remains historical. Model construction
must explicitly retain `equivalence_result` and `runtime_realization` as
`not-established`; compatible-looking labels, graphs, traces or digests do not
establish either claim. #972 owns correspondence, #973 negative-result fixtures,
#974 exact DPBB checking, #975 independent reproduction, and #976 reproduced
assurance publication; the new profile needs its own admission to those gates.

Targeted local feedback only; full, integration, fuzz and completion suites
remain CI/CD-only. Preflight verification is limited to the read-only rev2
exporter, existing runtime cases for immediate replay, unchanged-policy history
advancement, completed restart replay, cached governed egress, identity rejection,
unresolved policy, actor/scope status readback and indeterminate recovery, and
file-local repo policy. On 2026-10-13, the retained rev2 exporter drift check and
all 10 selected runtime cases passed; file-local policy passed before and after
editing.
These checks establish incumbent behavior and construction drift only; they do
not verify a new profile, correspondence or equivalence.

## Non-goals and anti-patterns

No runtime semantic change, enforcement bypass, mandatory author annotation,
author-time proof run, request-path checker, new production dependency, SDL/API
surface, controller/policy engine, exception tree, persistence layer, logger or
workflow is authorized by this construction issue. Runtime changes require a
separate explicit compatibility decision and targeted runtime tests, with their
latency impact measured separately from offline model cost.

No equivalence result, live realization, backend conformance, noninterference,
predicate opacity, arbitrary sequential repetition, time/probability/fairness,
true concurrency/partial order, handoff, universal crash recovery, latency or
throughput claim follows. Avoid rekey-to-retry advice, policy-only staleness,
latest-result-only ledgers, secret-bearing fixtures, shared semantic oracles,
hidden observable refusals, automatically refreshed baselines and runtime
changes made solely to force model agreement.
