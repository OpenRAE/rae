# Issue 1188 Served Control-Plane Profile Alignment Preflight

Date: 2026-09-19

Issue: #1188. Requirement: API-404. Decision: ADR-104. Work package: CP-8.

## Decision

Profile P2 is the existing reference HTTP adapter in front of the same
`RuntimeControlPlane` and one P1 owner. It is not a second operation service,
identity model, authorization namespace, audit writer, persistence workflow, or
mutation scheduler. P2 keeps one immutable target/run store scope, one
process-lifetime owner lease, one core mutation authority, and one application
worker. The HTTP layer authenticates, validates transport shape, performs
bounded admission/offload, and maps core outcomes; the core remains the
authority for referenced-subject authorization, operation context, claims,
terminal state, and audit.

`ControlPlaneIdentity` is the authenticated transport principal and
`OperationAdmissionContext` is the immutable core/persisted authority context.
`operation_actor_scope()` and `operation_admission_context()` are the only
conversion boundary between them. Do not introduce an actor DTO, proxy-user
schema, route-local scope tuple, or caller-supplied actor field. Every HTTP
mutation passes the authenticated `ControlPlaneIdentity` to the core. The core
must reject a missing or untyped identity on a P2 call before a claim or backend
invocation; the existing `identity=None` trusted-embedder behavior remains only
for explicit P0/P1 in-process calls.

Authorization is evaluated against the authoritative referenced object before
disclosure or claim:

- target-wide plan operations, snapshots, and operational summaries require
  the existing exact target binding and applicable role;
- participant-addressed mutations and governed projections additionally use
  the existing `ParticipantControlSubjectBinding` or
  `ParticipantAudienceSubjectBinding` policy, after resolving the referenced
  participant or execution scope through incumbent compiled/runtime state;
- operation status and idempotent replay require the original actor and full
  immutable authorization scope, plus the admitted target/run and operation
  kind; absent and unauthorized operation ids have the same response;
- startup reconciliation has no new caller: it preserves the parent record's
  immutable actor/scope and produces its terminal audit from that context;
- indeterminate resolution retains CP-3 semantics: a newly authenticated
  target-bound operator may be a different actor, but must be reauthorized
  against the parent's target/run and participant scopes. The linked child gets
  the resolver's context and the parent actor is never rewritten.

Role checks in `_ControlPlaneApiAuth` are transport admission, not sufficient
participant or operation authorization. Family-specific core checks in
participant control, crossing, retrieval, recovery, and operation reads are the
incumbents to share or converge. Do not copy their policy into route handlers or
infer authority from an operation id, idempotency key, receipt, request path,
snapshot revision, or auditor role.

## Proxy and credential boundary

`ControlPlaneSecurityConfig.strict_defaults()` remains fail closed. Bearer
tokens retain precedence and constant-time comparison; an invalid presented
bearer token never falls through to proxy headers. Proxy identity is accepted
only when `trust_proxy_identity_headers=True` is supplied by trusted application
composition. That flag is the deployer's assertion that the adapter is not
directly reachable and that the authenticating proxy strips both configured
identity headers from every external request before setting its own values.
Client-provided `x-raes-client-verified`, a configurable equivalent, source IP,
or TLS presence is not proof of that topology.

Strengthen the existing config admission rather than adding an environment
loader: configured header names must be valid, distinct, and must not alias the
Authorization header; bearer keys and principal names must be non-empty; roles,
target names, actor ids, and subject bindings must fit the existing closed
context bounds; and duplicate/ambiguous subject bindings fail composition.
`trusted_identities` and `bearer_tokens` remain immutable copies. P2 adds no
token environment variable, secret file, command-line token, dynamic principal
registration endpoint, or request-body identity override.

## Mutation, audit, and failure boundary

All accepted mutation families continue through `RuntimeMutationAuthority`,
the atomic store claim, and `RuntimeDurabilityMixin`. A terminal operation uses
`commit_terminal_operation()` (or the incumbent participant transition
equivalent) to publish the snapshot/revision outcome, terminal record, and
`terminal_operation_audit()` together. Routes never append a success/failure
terminal audit. Remove the post-hoc receipt-audit calls and their no-op seam
rather than leaving an apparent second audit workflow. Authentication,
authorization/admission denial, request rejection, and read-access audits remain
separate bounded operational evidence and never masquerade as terminal audit.

HTTP failure mapping is one shared adapter concern. Expected authorization,
not-found, claim/revision conflict, validation, and overload outcomes receive
stable coarse envelopes. Unexpected backend, store, policy-provider, or audit
provider failures receive the existing redacted 500 envelope. Route code must
not return `str(exc)` or provider-selected messages; the backend failure
diagnostic must not vary with exception text or class name. Tokens, raw headers,
request bodies, concrete request/host/database paths, SQL/WAL details,
credentials, tracebacks, exception chains, and provider-native values are
absent from responses, diagnostics, audit fields, and logs.

A failed secondary audit must not replace an already selected 4xx/5xx response.
The request-size middleware and global exception handlers therefore need the
same best-effort audit rule. `_LOGGER.exception()` is not a safe provider-error
fallback because it emits a traceback and exception chain; log only a stable,
bounded event label. Do not create a public provider exception hierarchy.

## Read and concurrency boundary

`_ControlPlaneCallExecutor` remains the bounded ASGI offload owner:
`mutate()` reserves bounded mutation admission and delegates serialization to
the core; `run()` keeps non-mutating reads/audits off the event loop. The
process-bound store lease, `require_single_worker_configuration()` checks for
`WEB_CONCURRENCY`/`UVICORN_WORKERS`, and post-fork lease check remain cumulative
guards. A database uniqueness index, asyncio lock, or application-local queue
is not multi-worker coordination. The repository still has no serve command;
TLS termination, proxy configuration, supervisor flags, and service-account
privileges remain deployment responsibilities and no P3 claim follows.

Side-effect-free retrievals use `run()` and `_project_snapshot_read()` so they
can proceed while backend work is in flight. Each snapshot-derived response
must be projected from one authoritative `SnapshotState` cut and carry that
cut's logical revision in `X-RAES-Snapshot-Revision`; provider transaction ids
and response-time rereads are not revisions. `get_operation()` reads the store
and authorizes the immutable record context before returning it.

RUN-319 governed participant egress is deliberately different: when a retrieval
must append crossing history before disclosure, it is a read-shaped mutation
and must stay on the one mutation authority with revision/history-head checks.
Only the legacy/pure projection path may bypass mutation admission. Do not make
governed egress appear noncontending by returning before its evidence commit,
moving crossing history to the audit log, or introducing a second evidence
queue/writer. If nonblocking latency is later required for governed egress too,
that requires a separate decision reconciling ADR-104's single mutation
authority with RUN-319's commit-before-serialization rule; CP-8 must not weaken
either implicitly.

## Canonical incumbents

- Authentication/configuration: `ControlPlaneSecurityConfig`,
  `ControlPlaneIdentity`, `ControlPlaneRole`, participant subject bindings,
  `_ControlPlaneApiAuth`, and `ControlPlaneSecurityConfig.strict_defaults()`.
- Transport shape/admission: closed FastAPI/Pydantic request models,
  `RequestSizeLimitMiddleware`, `RejectionAuditExecutor`, and
  `_ControlPlaneCallExecutor`.
- Authority context and idempotency: `OperationAdmissionContext`,
  `operation_actor_scope()`, `operation_admission_context()`,
  `require_idempotency_key()`, `_require_same_idempotency_replay()`, and the
  atomic provider claim. Caller `request_fingerprint` remains non-authoritative.
- Mutation and lifecycle: `RuntimeMutationAuthority`, `mutation_entry()`,
  `RuntimeDurabilityMixin`, `TerminalCommitMode`, the closed operation
  transition/diagnostic helpers, and CP-3 resolution/reconciliation.
- Persistence/coherence: `ControlPlaneStore`, `ControlPlaneStoreCommitAdapter`,
  `InMemoryControlPlaneStore`, `LocalControlPlaneStore`, `SnapshotState`,
  revision CAS, strict operation/audit codecs, immutable store scope, and
  `RuntimeOwnerLease`.
- DTOs and schemas: the existing `OperationReceiptModel`,
  `OperationStatusModel`, `RuntimeSnapshotEnvelopeModel`, participant view
  models, generated control-plane schemas, and `portable_diagnostic_payload()`.
  No HTTP-only copies or provider-specific public carriers are needed.
- Semantic validation: `control_plane_plan_diagnostics()`, planner-produced
  plan authorization, backend input/result/snapshot-transition validation,
  participant control/crossing policy gates, and participant retrieval
  projection validators. Transport validation does not duplicate them.
- Secret handling: `value_free_account_placement_payload()`, canonical
  value-free request commitments, ephemeral exact retry proof, and backend
  account-credential sanitizers. Digests do not make a secret safe to persist.
- Observability: `AuditEvent`, `terminal_operation_audit()`, stable `Diagnostic`
  codes, ADR-066, and module loggers with value-free fields. Audit, logs,
  participant crossing history, captured evidence, and archival provenance are
  distinct concepts.

## Cross-cutting gates

| Layer | Required passage |
| --- | --- |
| HTTP pre-parser | Request body crosses `RequestSizeLimitMiddleware`; oversized or malformed length fails before parsing or dispatch and uses bounded best-effort rejection audit. |
| Authentication | Bearer or explicitly enabled verified-proxy resolution produces one configured `ControlPlaneIdentity`; bearer failure cannot fall through and proxy headers are never accepted under strict defaults. |
| Transport shape | Existing closed request models reject unknown members and validate field bounds before domain reconstruction. Header idempotency uses the single core key validator. |
| Authorization | Route role/target admission is followed by core participant/operation/reference authorization using authoritative state and the typed identity, before claim, backend work, or disclosure. |
| Immutable context | `operation_admission_context()` validates and freezes actor, complete scope, target/run, kind, parent, and value-free commitment in the existing carrier. |
| Semantic/backend gates | Existing plan, realization, participant, information-flow, credential, backend-return, and snapshot-transition validators run once at their current authority boundaries. |
| Persistence | Atomic claim, expected revision/history heads, strict record codec, terminal transaction/audit binding, immutable store scope, lease admission, and readback/poison behavior remain mandatory. |
| Secret/OS exposure | Security config is explicit in-memory composition; no secret/path enters env or argv. Local storage retains private modes, anti-link checks, identity-pinned opens, admitted WAL/full-sync behavior, and integrity checks. |
| Error envelope/logging | Shared coarse 401/403/404/409/413/422/500/503 responses and safe diagnostics/log labels contain no exception/provider/request/credential/path material. |
| Response coherence | Snapshot-derived output and revision come from the same pinned cut; operation status comes from the authoritative record after context authorization. |

## Extension seam

The seam for the next authentication mechanism is a resolver that produces the
existing `ControlPlaneIdentity`; the seam for the next operation family is one
core authorization decision parameterized by existing `OperationKind`, target,
and resolved participant/operation subjects, followed by the existing context,
claim, mutation, and terminal-commit path. Do not build a generic policy DSL or
route middleware registry. A future P3 provider may change ownership and
coordination beneath these contracts only after its own decision; it does not
change actor or claim identity.

## Verification guardrails

Extend the existing HTTP auth, target-binding, request-size, bounded-admission,
offload, overload, and redacted-error suites rather than creating a parallel
P2 harness. Cover bearer and trusted-proxy paths, default proxy spoofing,
invalid-bearer precedence, both worker environment variables plus process/lease
contention, and identity/config shape failures.

Cross-principal tests must exercise equal idempotency keys, guessed operation
ids, changed scopes, participant bindings, target/run mismatch, retry, status,
and linked resolution without becoming existence or receipt oracles. Atomicity
tests must inject commit rollback/unknown outcomes and prove one terminal record
and one matching core audit, with no route audit. Error tests inject secrets,
paths, SQL, bodies, exception strings, and traceback-bearing provider failures
and scan response, diagnostics, audit, and captured logs. Read tests hold a
backend mutation open and prove pure snapshot/status/summary/legacy participant
reads complete with their observed revision; governed RUN-319 egress remains a
separately asserted mutation contract.

## Non-goals and anti-patterns

- No P3, multiple application workers, multi-host ownership, leader election,
  fencing, durable broker, distributed queue, shared-cache coherence, tenant
  multiplexing, cross-target/run store, or exactly-once backend-effect claim.
- No new identity, actor, receipt, status, revision, audit, provider-error,
  participant-subject, or idempotency schema; no second validator, serializer,
  exception hierarchy, audit sink, or mutation lock.
- No identity-less HTTP core mutation, route-created actor string, trusted
  client identity header by default, bearer-to-proxy fallback, proxy trust
  inferred from a header, IP, or TLS alone, or mutable principal map.
- No route-only subject authorization, authorization by possession, broad
  auditor override of actor-bound status, operation-id enumeration, or 403/404
  distinction that reveals a protected object.
- No post-hoc terminal audit, duplicate retry audit, terminal `save_record()`,
  cache-authoritative receipt/status, lookup-then-claim, backend replay, or
  store transaction across external work.
- No `detail=str(exc)`, exception class/message in a provider diagnostic,
  traceback logging, raw request path/body/header/token, SQL, database path, or
  credential in an observable envelope.
- No claim that a mutating RUN-319 projection is a noncontending read; no
  response before required crossing evidence commits and no audit substitution
  for participant history.
- No new serve CLI, TLS/proxy implementation, environment-based principal or
  secret loader, service unit, health/runbook surface, profile discovery, SDL
  semantics, backend effect semantics, or `RuntimeManager` integration.
