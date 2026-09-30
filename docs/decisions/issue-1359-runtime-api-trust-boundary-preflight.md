# Issue 1359: Runtime API trust-boundary enforcement preflight

Status: architecture guidance for implementation. This note applies the
accepted [issue #1356 decision](issue-1356-control-plane-participant-access-preflight.md)
to the current repository. It changes no runtime behavior, requirement,
published contract, or profile guarantee.

## Decision to implement

The selected exposure model is **host-mediated, administrative-only P2**.
Participant-facing code does not receive a RAE credential, the
`RuntimeControlPlane` object, or store access. The organizational or local host
authenticates its own caller, selects the exact target/run, participant,
episode, audience and operation, calls RAE with a privileged service identity,
and releases only an authorized governed result.

`ControlPlaneIdentity` remains the authenticated transport principal. An SDL
participant, runtime actor, controller, audience, deployment tenant and host
user are different concepts. `ParticipantAudienceSubjectBinding` and
`ParticipantControlSubjectBinding` constrain a semantic operation after
transport admission; they do not create a role or authenticate an end user.

This resolves the issue's “participant-view-limited credential” criterion as
follows:

- a target-bound identity with participant/audience bindings but without a
  `BACKEND`, `OPERATOR` or `AUDITOR` route role is not an admitted P2 reader and
  must fail both governed-view and administrative reads;
- an identity with one of those read roles is an administrative service
  identity even when it also carries an audience binding. Under the accepted
  API-404-C3 contract it can read `/snapshot`; it must never be described or
  delegated as a participant-limited credential; and
- creating a participant-only role, episode-scoped token or direct
  participant-to-RAE transport would be a different exposure model requiring a
  new reviewed decision and API-404/ADR-104 amendment.

No new authorization schema is required. The incumbent seam is
`control_plane_api/_auth.py`: bearer or explicitly trusted verified-proxy
authentication, exact target binding, then one of the existing read, mutating
or operator-resolution dependencies. New operation or inject routes must enter
through that seam and then invoke their existing core semantic authorization;
they must not implement route-local token parsing, role sets or subject tuples.
Names and documentation at that seam should make its administrative meaning
unambiguous. The route role is transport admission, never disclosure,
controller or backend-effect authority by itself.

Configuration is part of that boundary. Python annotations on
`ControlPlaneIdentity` are not runtime admission: the current class itself does
not fully reject untyped roles, malformed target values, non-tuple subject
collections or overlong actor/scope components. Validate the exact closed
identity and binding shape once when `ControlPlaneSecurityConfig` copies and
freezes its principal maps, against the existing operation-context and audit
bounds. Do not defer malformed trusted configuration until a request, operation
commit or audit write, and do not compensate with route-local checks.

## Current route and authority matrix

Every current route that reveals runtime state or can cause an effect is
privileged. Only the value-free probes and framework descriptions are public.

| Surface | Required P2 authority | Additional core/release boundary |
| --- | --- | --- |
| `GET /health/live`, `GET /health/ready` | Public, value-free probe | Preserve the closed health payload. No target, run, actor, operation, revision, count, path or provider value. |
| `/openapi.json`, `/docs`, `/redoc` | Public framework description on the administration network | Describes capability, not permission. A deployment may disable or network-restrict it; it cannot reveal runtime state. |
| `GET /snapshot`, `GET /apparatus/operational-summary` | Administrative read: `BACKEND`, `OPERATOR` or `AUDITOR`, exact target | Raw snapshots, histories, diagnostics and summaries never become participant views. |
| `GET /operations/{operation_id}` | Administrative read, exact target | `RuntimeControlPlane.get_operation()` additionally requires the original actor and complete immutable authorization scope; unknown and unauthorized IDs remain indistinguishable. |
| `POST /operations/{provisioning,orchestration,evaluation}` | Administrative mutation: `BACKEND` or `OPERATOR`, exact target | Reuse planner authorization, typed plan validation, immutable operation context, actor-scoped claim, idempotency and one mutation authority. |
| `POST /operations/{operation_id}/resolution` | `OPERATOR`, exact target | Reauthorize the linked parent scope; administrative disposition is not participant recovery or effect proof. |
| `POST /workflows/{workflow_address}/cancel`, `POST /workflows/reconcile-timeouts` | Administrative mutation | Reuse workflow/run admission, operation context and idempotent receipt. |
| `POST /participant-executions/{execution_scope_ref}/control`, `GET /participant-executions/{execution_scope_ref}` | Administrative mutation/read | Execution scope is service state, not an API-408 projection or audience entitlement. |
| `POST /participants/{participant_address}/episodes/{initialize,reset,restart,terminate}` | Administrative mutation | Participant and optional episode values are request data. Core lifecycle/run checks own their meaning; they are not credential scope. |
| `POST /participants/{participant_address}/control-occurrences` | Administrative mutation | Core additionally requires the exact participant/controller subject binding and API-409/RUN-310 admission. Audience binding is not control authority. |
| `GET /participants/{participant_address}/status`, `GET /participants/{participant_address}/episodes/{episode_id}/history`, `GET /participants/{participant_address}/context` | Administrative read | With a crossing resolver, require one exact participant/audience binding and commit API-423/RUN-319 crossing evidence before serialization. The episode and source cut are validated by retrieval/crossing contracts. Without a resolver this is a legacy administrative projection and must not be released to a participant. |

There is no P2 raw audit, event-stream, callback, export or cache route. A new
route in any of those families inherits the authority of the data/effect it
exposes. Per-item authorization is required for streams and callbacks; checking
only subscription creation is insufficient. A future external inject trigger is
an administrative mutation that creates an actor-bound operation. Optional
participant delivery remains a later, separately governed API-423 crossing; an
authored inject, operation receipt or successful effect does not grant that
delivery.

The P0/P1 SDK boundary remains trusted object possession. HTTP dependencies do
not protect direct Python calls. `get_snapshot()`, `snapshot`, `audit_log()`,
`observation_execution()`, participant control/action methods, directed-view
delivery and direct store reads are privileged host methods, not alternate
participant transports.

## Canonical incumbents and cross-cutting gates

| Layer | Canonical incumbent and required use |
| --- | --- |
| Authentication and route admission | `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `ControlPlaneSecurityConfig.strict_defaults()`. Preserve immutable credential maps, constant-time bearer comparison, hard failure for an invalid presented bearer token, explicit proxy-header trust, valid/distinct non-Authorization header names and exact target equality. Admit exact `ControlPlaneRole` values and exact, bounded identity/subject-binding shapes at configuration time; annotations and later operation/audit failures are not configuration validation. |
| Transport shape and bounded execution | `create_control_plane_app()`, `RequestSizeLimitMiddleware`, `_ControlPlaneCallExecutor`, closed FastAPI/Pydantic request models, `control_plane_store.require_idempotency_key()` and the single-worker gate. Body limits do not bound the request line, path, query or headers. Reuse the owning address/reference validators where they match; otherwise add one bounded transport-shape check at ingress rather than duplicating semantic validation in routes. Server/proxy request-line and header limits remain mandatory. A future inject route also inherits the bounded, duplicate-aware JSON ingress and exact carrier validation required by the [issue #1353 preflight](../explain/sdl/issue-1353-external-inject-triggering-preflight.md); a permissive body model is not an authorization or shape gate. |
| Operation identity, readback and retry | `control_plane_operation_context.py`, `control_plane_admission.py`, `control_plane_store.require_idempotency_key()`, atomic claims and `RuntimeControlPlane.get_operation()`. Persist the actor and complete authorization scope; authorize before returning a retained receipt/status or idempotent replay. Operation IDs, idempotency keys and request commitments are identifiers, not bearer authority. |
| Participant disclosure | `participant_retrieval.py`, `control_plane_api_participant_retrieval.py`, `participant_crossing_egress.py`, `participant_flow_sink.py`, API-408 models in `raes_contracts/contracts/participant_views.py` and API-423 contextual validation in `participant_crossing_validation.py`. Project and validate before serialization; never serialize a full snapshot and filter it afterward. |
| Participant control and inject composition | `participant_control_mediation.py`, `participant_control_orchestration.py`, API-409 carriers and compiled DSL-142/API-423 bindings. Keep effect authority, controller authority, participant disclosure and delivery as separate gates. Do not make participant fields optional on an administrative operation carrier to reuse it as a view. |
| DTOs and schemas | Existing `OperationReceiptModel`, `OperationStatusModel`, `RuntimeSnapshotEnvelopeModel`, participant view models, route request DTOs and generated `contracts/schemas/control-plane/` artifacts. Authorization is internal adapter policy, not a second HTTP DTO or published participant schema. |
| Persistence and concurrency | `ControlPlaneStore`, `control_plane_store_local*`, `RuntimeMutationAuthority`, revision CAS, owner lease, strict codecs and atomic terminal operation/audit commit. No participant store, authorization cache, second event writer or route-owned persistence transaction. |
| Errors and diagnostics | `control_plane_api/_responses.py`, the redacted 422/500 handlers, `portable_diagnostic_payload()`, `backend_result_diagnostics.py` and existing stable 403/404/409 details. Never expose `str(exc)`, rejected values, provider payloads, paths, SQL, headers, tokens or traceback chains. Secondary audit failure cannot replace the selected denial. |
| Audit and logging | `control_plane_audit.py` and terminal operation audit. Use bounded action/reason codes and safe identifiers only. Authentication/rejection/read audits stay distinct from atomic terminal audit. Proxy, ASGI and backend logs obey the same disclosure rule. |
| Configuration, secrets and OS boundary | `ControlPlaneSecurityConfig` is supplied by trusted composition; `require_single_worker_configuration()`, `control_plane_store_paths.py` and the local-store lease retain process/filesystem admission. This issue adds no SDL field, environment parser, token endpoint or CLI credential. If a later deployment artifact represents secret or environment inputs, reuse `raes_contracts/secret_references.py` and `raes/runtime_environment.py`/`runtime_configuration.py` rather than inventing a token env grammar. Keep credentials out of URLs, argv, shell history/tracing, environment dumps, fixtures, versioned files, access logs, crash reports and backups. Retain private store permissions, one worker, reload disabled, TLS termination, request-line/header limits and an administration/service network; disable or redact proxy/ASGI access logging that would capture sensitive selectors. |
| Repository workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`, targeted control-plane tests and CI full suites. Published-schema changes, if ever justified, use the existing schema publication manifest/generator; ADR amendments use the ADR index and immutability tooling. |

### Cached, replayed and alternate outputs

Authorization applies at every output, not only at the first computation.
Authenticated runtime responses, including errors and idempotent readback,
must carry a shared `Cache-Control: no-store` policy at the P2 application
boundary so a route cannot omit it accidentally. Deployment proxies must not
cache authenticated responses or key them only by URL. Host-side caches remain
outside RAE and must be scoped by caller/session, target/run, participant,
episode, audience, policy and source revision, with reauthorization on every
release and invalidation on handoff, revocation or state-cut change.

The retained result of an idempotent governed GET remains bound to its original
actor/scope, crossing subject and source cut. Do not relabel it with a current
revision, use `X-RAES-Snapshot-Revision` as authorization, or bypass the
crossing because bytes already exist. Errors, redirects, conditional responses,
future stream items and callbacks are disclosure surfaces too. No response may
fall back to a snapshot, raw operation diagnostic or provider error when a
projection fails.

## Extensibility seam

The extension seam has two independent parameters:

1. the route selects one existing transport authority: public value-free,
   administrative read, administrative mutation or operator resolution; and
2. the core operation supplies any additional typed subject policy required by
   its semantics: original operation actor/scope, participant/controller, or
   participant/audience/exact-cut crossing.

That split lets a new operation, inject, export or stream route reuse P2
authentication without editing every incumbent route, and lets a new governed
carrier reuse API-423 without turning audience into a transport role. A future
inject route takes only this transport-authority parameter from #1359; its
authored binding, occurrence, payload, capability, supervision, effect evidence
and optional delivery semantics remain owned by the #1353/ADR-112 boundary. A
future direct-participant exposure mode would be a new first parameter and is
deliberately unavailable; it cannot be smuggled in through a nullable binding,
role alias, route tag or configuration flag.

## Verification guardrails

Evidence must exercise the real ASGI/HTTP boundary, not call auth helpers or
core methods alone. The route matrix needs positive administrative cases and
negative unauthenticated, wrong-target, wrong-role and no-role audience-bound
cases for every route family. It must also cover cross-actor operation readback,
cross-participant governed retrieval, ambiguous/missing audience binding,
episode mismatch, legacy no-resolver posture, controller mismatch, exact retry
versus conflicting idempotency reuse, malformed configured principals, bounded
non-body selectors, redacted error paths, no-store headers and route-inventory
drift when a new route is registered. Public probes must remain value-free.
Framework routes must not be counted as authenticated runtime APIs.

The test identity with a read role plus audience binding should explicitly prove
that it is broad administrative authority under the accepted model. The
no-role, audience-bound identity is the negative “participant-limited” case.
This prevents tests or deployment examples from silently asserting a narrower
credential contract than the runtime enforces.

## Non-goals and anti-patterns

This issue does not add organizational IAM, tenancy, host-user sessions, direct
participant authentication, a participant role, an episode/run token, TLS, a
serve command, a credential loader, multi-worker coordination, P3, an event
API, a response cache, or a new published carrier. Backend-owned organizational
authentication and policy stay at the host boundary.

Avoid:

- treating audience/controller bindings, URL selectors, operation IDs,
  revisions, receipts or idempotency keys as credentials;
- copying role checks into route modules or adding a second principal,
  exception, audit, DTO, validation or persistence hierarchy;
- granting `AUDITOR` mutation authority or treating `BACKEND` as participant
  disclosure authority;
- filtering snapshots after serialization, returning raw diagnostics on
  projection failure, or using 403/404 differences as a host-user oracle;
- accepting a caller-supplied identity, participant, episode, audience or
  policy claim without joining it to trusted configured/compiled/runtime
  state;
- treating type annotations as runtime configuration validation, or treating a
  body-size limit as a bound on credentials, request lines, selectors or access
  logs; and
- weakening the resolver, final-sink, revision, single-writer or atomic-audit
  boundaries to make a route appear read-only or noncontending.
