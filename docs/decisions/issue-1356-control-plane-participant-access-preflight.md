# Issue 1356: Control-plane and participant-access trust boundary

Status: accepted architecture decision (2026-09-24). This note interprets
[ADR-104](adrs/adr-104-runtime-control-plane-architecture.md) section 7 and
[API-404](../requirements/API-404/requirement.md) C1/C3 for participant access.
It changes no runtime behavior or executable authorization claim.

## Decision and authority

Participant clients reach an organizational backend, not RAE's HTTP adapter,
in-process `RuntimeControlPlane`, store, backend adapter, or host. The backend
authenticates the organization user/session, decides entitlement to a selected
run, participant, episode, audience and action, and returns only a participant
response it has authorized. Organizational users, groups, tenants, session
policy, and credential issuance remain backend responsibilities. An
authentication principal is not an SDL participant, controller, `agent` role,
or `deployment_tenant`; no new SDL declaration follows from this decision.

The backend's RAE caller is a privileged **service principal**. Existing
`ControlPlaneIdentity` roles grant route families, not a participant-only read
capability: `BACKEND`, `OPERATOR`, and `AUDITOR` all pass `_ReadIdentity`, which
also admits `/snapshot`. A `ParticipantAudienceSubjectBinding` narrows governed
projection lookup; it does not narrow that principal's snapshot authority.
Consequently a bearer token or trusted proxy identity with a participant
binding must never be issued to a browser, participant agent, mobile client,
or participant-side plugin. A participant-facing backend must not expose a
generic RAE proxy or return raw RAE receipts, statuses, snapshots, diagnostic
payloads, or store records. Its outbound RAE credential stays in a trusted
server component and is never copied into a client process, URL, command line,
response, log, or cache key.

Before a backend participant request reaches RAE, the backend binds its own
authenticated principal and session to **one** target/run, participant address,
exact episode, allowed audience, and permitted operation. It checks these
bindings again for every read, retry, poll, delivery, stream item, callback,
and mutation. RAE receives a target-bound service identity with the appropriate
existing role and, for governed views, exactly one matching
`ParticipantAudienceSubjectBinding`; RAE's one-run store supplies the run
boundary. The backend must not infer an audience from a URL, header, query,
view ref, or the fact that a service principal can read a snapshot. A status or
context request without an episode selector must be resolved against the
backend's selected exact episode before release. A history request's episode
path must equal that binding. An episode change, handoff, audience-policy
change, or run switch requires fresh authorization and a fresh projection;
cached bytes cannot be relabeled or reused across those coordinates.

Participant-facing retrieval requires a configured RUN-319 crossing-policy
resolver and a permitted exact-cut API-423 egress. The current API-408 adapter
also has a legacy path when no resolver is configured; that path has no
crossing evidence and is **not** an accepted participant-facing deployment.
The backend may use RAE's governed status, history and context views only after
its own entitlement check, and must check the returned participant, episode,
and source state cut against its trusted binding before release. It must use
the governed RAE route with a configured resolver; the view schema alone is
not proof of a permitted crossing. Audience and policy authority come from
the backend's decision and RAE's governed crossing, not from interpreting a
view field as an entitlement. RAE enforces its
participant/audience candidate and crossing decision; it does not decide
organizational entitlement. Read-shaped governed egress is a mutation: it
commits crossing evidence before serialization through the existing mutation
authority. A denied, ambiguous, missing-evidence, or stale-cut result fails
closed. Administrative reads may remain available to trusted operators under
ADR-104, but they are never a participant-view fallback.

## Runtime route and authority matrix

This inventories the reference P2 HTTP app; P0/P1 expose the corresponding
in-process methods only to a trusted embedder. `read` means the existing
`_ReadIdentity` role check, `mutate` means `_MutatingIdentity`, and `resolve`
means `_ResolutionIdentity`. All authenticated HTTP identities require the
exact RAE target binding. The backend applies its own user/session and
participant checks before any participant response.

| Surface | Current RAE gate and data | Authorized consumer and participant treatment |
| --- | --- | --- |
| `GET /snapshot`; `GET /apparatus/operational-summary` | `read`; full runtime snapshot or operational summary, revision header, audit | Privileged backend, operator or auditor only. Never forward or derive a participant response from this route. |
| `GET /operations/{operation_id}` | `read`; core matches immutable operation actor **and authorization scope**, otherwise 404 | Submitting service actor/operator for operational polling. IDs and matching scopes are not participant authorization; backend reprojects any client-visible progress. |
| `POST /operations/provisioning`, `/orchestration`, `/evaluation` | `mutate`; planner authorization, typed plan validation, actor-scoped claim, receipt | Trusted backend/operator only. Plans and receipts are control-plane artifacts. |
| `POST /operations/{operation_id}/resolution` | `resolve` (operator); linked indeterminate resolution | Operator only; never a participant retry or recovery shortcut. |
| `POST /workflows/{workflow_address}/cancel`, `/workflows/reconcile-timeouts` | `mutate`; core workflow/run admission, receipt | Trusted backend/operator only; backend must authorize any user-driven cancellation. |
| `POST /participant-executions/{execution_scope_ref}/control`; `GET /participant-executions/{execution_scope_ref}` | `mutate`/`read`; backend execution control/readback, receipt or service state | Administrative service surface. Execution scope is not an audience-bound participant projection. |
| `POST /participants/{participant_address}/episodes/{initialize,reset,restart,terminate}` | `mutate`; typed lifecycle request, core episode/run state, receipt | Trusted backend/operator only. Path and optional episode body are request data, not entitlement. |
| `POST /participants/{participant_address}/control-occurrences` | `mutate` plus core participant/controller binding and API-409 control admission | Authorized service controller only; control authority is distinct from view audience. |
| `GET /participants/{participant_address}/status`; `/episodes/{episode_id}/history`; `/context` | `read`; with resolver, exact participant/audience candidate, episode and API-423/RUN-319 crossing before serialized API-408 view; without resolver, legacy projection | Trusted backend service only. Backend releases a view solely for its separately bound user, run, participant, episode and audience. |
| `GET /health/live`, `/health/ready`; framework `/openapi.json`, `/docs`, `/redoc` | No identity dependency; value-free health or API description | Deployment probe/administration network. No participant data authority; do not treat their reachability as permission to expose P2. |
| Audit log, snapshot/operation store, raw event and crossing histories, backend callbacks | No P2 HTTP route for raw audit or an event stream; in-process/store access belongs to the owner/embedder. Histories also appear inside privileged snapshots and governed participant views. | Owner/operator only. A future event, subscription, export, callback, or cache endpoint must inherit the same release gate for each item and cannot expose raw histories to participants. |
| `RuntimeControlPlane` in-process methods, `RuntimeManager` direct execution, and offline store check/backup/restore | Trusted embedder, direct backend authority, or owner-stopped maintenance; no HTTP participant authorization | Privileged host/operator path only. Store copies, direct snapshots and execution results must not become alternate participant reads or mutations. `RuntimeManager` does not coordinate with the control-plane owner on the same backend. |

HTTP 4xx/5xx envelopes, validation errors, operation diagnostics, receipts,
status readback, and `X-RAES-Snapshot-Revision` are also output surfaces.
They must carry no secret or cross-participant payload. The backend returns its
own bounded, participant-safe errors and never uses a 403/404 distinction or
raw RAE diagnostics to reveal another participant's existence. Participant
progress or notifications derived from operational results still need the
applicable governed carrier and release gate; renaming or filtering status
fields does not make an ungoverned participant feed safe.

The in-process row also covers `snapshot`, `get_snapshot`, `audit_log`,
`observation_execution`, participant action/control and decision-surface
admission, and `deliver_participant_directed_view`. These are not additional
participant transports: HTTP role dependencies do not wrap direct Python
calls. Directed delivery is a separate crossing, not proof of participant
consumption. The current `raes_mcp` authoring/inspection tools are not a live
participant control-plane gateway; adding one would require the same boundary.

## Deployment and cross-cutting guardrails

- Keep P2 on an administration/service network. Terminate TLS, authenticate
  service callers, strip untrusted identity headers before setting verified
  proxy headers, and select exactly one worker with reload disabled. Use
  `ControlPlaneSecurityConfig.strict_defaults()` until explicit identities and
  secrets are loaded. Unknown bearer credentials must fail without header
  fallback. A reverse proxy route allowlist can constrain the participant
  backend's outbound traffic, but does not make its RAE credential scoped at
  the RAE auth layer.
- Reuse `ControlPlaneSecurityConfig`, `_ControlPlaneApiAuth`, the API request
  size and bounded offload guards, `ControlPlaneIdentity` and its subject
  bindings. RAE config currently has no episode- or run-scoped HTTP identity
  field; the backend's selected run/episode must be checked against the pinned
  RAE store and returned carrier. Do not silently add an env flag, query token,
  new role, or second principal model to simulate that binding.
- Reuse the published `raes_contracts` operation, snapshot, API-408 view,
  API-409 control and API-423 crossing carriers and their model/context
  validators; `control_plane_api_models` is their HTTP adapter. Reuse
  `participant_retrieval`, `participant_crossing_egress`, the RUN-319 final
  sink, `control_plane_operation_context`, actor/scope-bound idempotency and
  readback, and the one mutation/store authority. Schema validity alone does
  not grant disclosure; no second DTO, crossing validator, exception hierarchy,
  event log, or persistence workflow is warranted.
- Reuse `_responses._conflict_detail`, redacted FastAPI exception handlers,
  `RequestSizeLimitMiddleware`, `portable_diagnostic_payload`, and bounded
  rejection/operational audit. Log stable reason codes and actor/target
  references only; never log bearer tokens, bodies, backend exception text,
  source snapshot bytes, participant view payloads, or identifying paths.
  Validate any future projection response at its final sink, including cache
  hits, retries and error branches.
- Keep the P1 owner lease, private store directory/database permissions,
  immutable target/run scope, snapshot revision/CAS and single worker rule.
  Build on `control_plane_store_local`, its scope/carrier validation and the
  existing store-maintenance interface for operational copies; do not add a
  parallel participant store or direct reader.
  Load secrets through the deployment's protected secret channel, outside
  process arguments and published config. Do not put a bearer token in a URL,
  environment dump, CLI argument, SDL file, fixture, or versioned artifact.
  Backend caches must be private, bounded by user/session plus target/run,
  participant, episode, audience, policy and source revision, and invalidated
  on authorization or state-cut change.

The extension seam is the backend-to-RAE identity/policy adapter: it maps a
backend-approved `(target, run, participant, episode, audience, operation)`
selection to existing RAE service identity and governed retrieval parameters.
It must permit a future route-scoped RAE credential or a new participant-safe
transport without changing SDL identities, the API-408/API-423 carriers, or
the backend's organizational policy model. Such a credential or transport
requires its own reviewed RAE authorization change; this decision grants none.

## Composition and release checks

These are constraints on the existing boundaries, not additional middleware,
schemas, or a proposed implementation sequence. Module names below are in
`implementations/python/packages/` unless another root is given.

| Layer and canonical incumbent | Required boundary |
| --- | --- |
| Transport/config: `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_api_guards.py`, `control_plane_api/_offload.py` | Preserve immutable credential maps, valid distinct identity-header names, target equality, role checks, positive admission limits and bounded body reading before routing. Backend entitlement must precede trusted identity selection; caller-supplied headers or selectors cannot mint bindings. A shared service principal is not an end-user identity. |
| Runtime composition: `control_plane_configuration.py`, `control_plane_composition.py`, `control_plane_profiles.py`, `registry.py` | Use normalized `run:<id>`, an explicitly selected P1 core/P2 adapter and admitted backend capabilities. Require the crossing resolver and its trusted `resolve_participant_view_evidence` hook for participant retrieval. Preserve explicit final-sink selection: selected SEM-233 enforcement requires `resolve_flow_sink_decision`; selected RUN-320 modular control requires its admitted binding/capability. Do not disable enforcement to make an incompatible resolver start, or confuse a manifest declaration with an installed enforcement provider. |
| Portable shape and contextual authorization: `raes_contracts/contracts/participant_views.py`, `participant_crossing_validation.py`; `raes_runtime/participant_crossing_mediation.py`, `participant_flow_sink.py`, `participant_control_orchestration.py` | Reuse API-408 model validation and API-423 context validation plus operation-bound policy, audience, history-cut and selected final-sink checks. Validate transformed egress against the committed subject. A well-formed view, a visibility-projection ref or a successful HTTP status is not independently verifiable crossing evidence; deployment composition and the governed path supply that assurance. |
| Secrets and environment: `raes_contracts/secret_references.py`; `raes/runtime_environment.py`, `runtime_generated_value.py`, `runtime_configuration.py`, `runtime_values.py` | Service credentials remain deployment secrets outside SDL. This decision introduces no env parser or secret loader. If deployment assets describe runtime env inputs, retain unique names, explicit sensitivity/provenance, redaction, literal/`value_from` exclusions and generated-output reference checks. `SecretReferenceId` is a logical reference, not a bearer value; generated values cannot masquerade as out-of-SDL `operator_secret` material. |
| Host/process and persistence: `control_plane_store_lease.py`, `control_plane_store_paths.py`, `control_plane_store_local.py`, `control_plane_store_records.py`, `control_plane_store_maintenance.py` | Enforce private owner-controlled paths, strict durable codecs, one target/run and one owner; keep `WEB_CONCURRENCY`/`UVICORN_WORKERS` at one and reload off. Proxy/network isolation must prevent direct socket access that bypasses verified-header authentication. Keep credentials out of argv, shell tracing, environment dumps, access logs, crash reports and exported backups/config. Store backups remain privileged even when diagnostics are redacted. |
| Errors and observability: `control_plane_api/_responses.py`, `_operation_routes.py`, `raes_contracts/diagnostics.py`, `raes_runtime/control_plane_audit.py`, `backend_result_diagnostics.py` | Use existing coarse conflict/422/500 envelopes and portable diagnostics; no raw validation input, exception text/type/chain or provider payload. Preserve the selected denial response when secondary audit fails. Keep terminal operational audit atomic with state; best-effort transport rejection audit is a separate guarantee. Backend, reverse-proxy and ASGI logging must obey the same disclosure boundary. |

Shared service identities need special care. `operation_actor_scope` and
`control_plane_admission` bind RAE claims/readback to the service actor and its
complete authorization scope, not the backend's user/session. The backend
must associate each client request and operation reference with its authorized
selection and map client retry keys into that ownership context; forwarding
arbitrary client keys into a shared service namespace is unsafe. Preserve the
mapping for a genuine retry, reauthorize every release, and never generate a
fresh key automatically after timeout, disconnect or an uncertain result.
Changing subject bindings can change the immutable scope and legitimately
make old readback unavailable; do not work around that by dropping the scope
check. Organization-user correlation belongs in backend audit, not a second
RAE actor model or credential-bearing operation context.

`RuntimeControlPlane._project_snapshot_read` returns the observed projection
revision, not a promise about the latest state after the crossing commit.
An idempotent egress can return its retained governed result;
`participant_crossing_projection.stable_projection_subject` normalizes only
runtime-owned revision paths. Do not rewrite retained source refs to a newer
header/revision or use that normalization as backend cache authorization.
Reauthorize against the selected episode/policy and obtain a fresh governed
projection when a current view is required. Governed GETs must not be served
from a shared proxy/browser cache: backend delivery must pass its release gate
even for retained results, including conditional responses and stream items.

## Evidence and workflow boundaries

This interprets API-404-C1/C3 and ADR-104 section 7; it preserves C2 durability,
C4/P3 nonclaims and FM3 invariants 8--11 (idempotency, authorization, provenance,
validation). No profile catalog or published contract change follows. Existing
regression homes are `test_runtime_control_plane_api.py` (auth, governed HTTP
egress, readback, errors), `test_run_319_participant_flow_policy.py` (audience,
transformation, stale-cut replay and atomic crossing),
`test_issue_1003_final_sink_flow_enforcement.py` and the issue-1069 control
tests (selected sink/control enforcement), and
`test_issue_1185_api_404_profile_alignment.py` (profile/nonclaim drift), all in
`implementations/python/tests/`. They do not demonstrate an organizational
backend's entitlement, revocation, session isolation or cache policy. Those
need evidence at the backend boundary, including a shared service actor,
cross-participant/episode requests and authorization changes during delivery.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml`
and `tools/check_repo_policy.py` for repository boundaries. ADR amendments use
`docs/decisions/adrs/adr-index.yaml` and `tools/check_adr_immutability.py`;
future published-schema changes use `contracts/schema-publication-manifest.json`
and `tools/check_generated_schemas.py`, not a parallel DTO generator. Retain
the file-targeted hygiene/secret checks in `.pre-commit-config.yaml` and
`tools/nox_support/policy_lanes.py`; use only relevant local test cases, with
full verification in CI. Design traceability is DOCUMENTS evidence, not a new
runtime IMPLEMENTS/TESTS or distributed-conformance claim.

## Non-goals and anti-patterns

No direct participant-to-RAE authentication, RAE organizational IAM, new SDL
participant/role, new P2 role, new published schema, or new HTTP route is
authorized here. This design does not certify that current P2 deployments
already have a crossing resolver, that legacy projection is safe for a
participant, or that a backend can delegate its broad RAE read credential.
Avoid filtering a full snapshot in the browser/backend as a substitute for
governed projection, treating possession of an operation ID or a
`ParticipantAudienceSubjectBinding` as global read authority, caching a view
without its exact scope, and allowing a generic proxy, event stream, error or
retry path to bypass the backend gate.
