# Issue 1356: Control-plane and participant-access trust boundary

Status: accepted architecture decision (2026-09-24). This note interprets
[ADR-104](adrs/adr-104-runtime-control-plane-architecture.md) section 7 and
[API-404](../requirements/API-404/requirement.md) C1/C3 for participant access.
It changes no runtime behavior or executable authorization claim.

## Decision and authority

RAES has two composition shapes. P0/P1 are SDK calls inside an embedding
application; P2 is an optional HTTP adapter over a P1 core. The trusted
**host application** owns participant-facing access in either shape. It may
be a local product such as LilRAE or an organizational service such as BigRAE.
Here “host” means that product, not a RAES realization-backend adapter.
Participant-facing UI or agent code receives an authorized result from the
host; it receives neither the privileged `RuntimeControlPlane` object and
store nor a P2 read identity. BigRAE retains organizational users, groups,
tenants, sessions, authentication and policy; a local host applies its own
caller boundary without inventing organizational accounts. An authentication
principal is not an SDL participant, controller, `agent` role, or
`deployment_tenant`.

**P0/P1 SDK:** There is no RAES HTTP credential or listener. The embedding
process supplies typed actor context for mutations and controls which code
can call SDK methods and receive their results. `get_snapshot()` takes no
caller identity and returns the full snapshot; participant retrieval methods
accept optional identity context. HTTP role dependencies do not protect direct
Python calls. Giving untrusted participant code the control-plane object,
store, or an unrestricted SDK wrapper gives it privileged access. A host that
cannot keep that object private cannot safely share one run's state with
mutually restricted participants. In a single-user local application the owner
may call the SDK directly as the trusted host; this decision does not require
an HTTP service or organizational account layer for that use.

**P2 HTTP:** `ControlPlaneSecurityConfig.strict_defaults()` contains no
tokens or trusted proxy identities. A deployment may configure bearer tokens
or verified proxy identities mapped to `ControlPlaneIdentity`; neither is an
RAES-issued universal credential. The configured identity has an exact target
binding and route roles. `BACKEND`, `OPERATOR`, and `AUDITOR` all pass
`_ReadIdentity`, which admits both API-408 participant view routes and
`/snapshot`. A `ParticipantAudienceSubjectBinding` narrows governed view
lookup only; it does not narrow snapshot access. “Service identity” is a
deployment use of these existing identities, not a distinct enforced role.
The host keeps its configured P2 token or proxy identity private and never
delegates it to a browser, participant agent, mobile client or plugin.

For each participant-facing release, the host binds its own caller and
session to one target/run, participant address, exact episode, allowed
audience and permitted operation. It checks that selection for every read,
retry, poll, delivery, stream item, callback and mutation. In P2, RAE checks
the configured identity's target and route role; for governed views it also
requires one matching participant/audience binding and commits the crossing
decision. The one-run store supplies the run boundary, but P2 has no
episode-scoped credential. In P0/P1, the host supplies the actor and any
governed audience binding to the SDK; it remains responsible for caller
authentication and result release. Neither shape lets RAE infer the host's
user entitlement from a URL, operation ID, view ref or runtime actor.

The host checks returned participant, episode and source state cut against
its selection before release. A status or context request without an episode
selector must be resolved against the host's selected exact episode; a
history request's path episode must match it. An episode change, handoff,
audience-policy change or run switch requires fresh authorization and a fresh
projection. Cached bytes cannot be relabeled across those coordinates.

Participant-facing retrieval requires a configured RUN-319 crossing-policy
resolver and permitted exact-cut API-423 egress in the host's RAE composition.
The current SDK and HTTP adapter still have a legacy projection path when no
resolver is configured. That path can return a view without crossing evidence;
RAE does **not** reject it merely because the host intends participant-facing
use. The host must refuse such a deployment or result. It may release governed
status, history and context views only after its own entitlement check and
the applicable RAE crossing. A valid view schema alone is not proof of a
permitted crossing. Read-shaped governed egress commits crossing evidence
before serialization through the existing mutation authority. Administrative
snapshots, operation records, raw histories, receipts, diagnostics and errors
are never participant-view fallbacks.

## Runtime route and authority matrix

This table inventories the optional reference P2 HTTP app. `read` is the
existing `_ReadIdentity` role check, `mutate` is `_MutatingIdentity`, and
`resolve` is `_ResolutionIdentity`. All authenticated P2 identities require
the exact target binding. These checks authenticate the host's P2 caller;
they do not authenticate the host's participant-facing user. The host applies
its own caller and participant checks before releasing any result.

| Surface | Current P2 gate and data | Caller and release rule |
| --- | --- | --- |
| `GET /snapshot`; `GET /apparatus/operational-summary` | `read`; full runtime snapshot or operational summary, revision header, audit | Privileged host, operator or auditor identity. Never release these as participant views. |
| `GET /operations/{operation_id}` | `read`; core matches immutable operation actor **and authorization scope**, otherwise 404 | Submitting host actor/operator for operational polling. IDs and matching service scopes do not authorize the host's end user; the host governs any client-visible progress. |
| `POST /operations/provisioning`, `/orchestration`, `/evaluation` | `mutate`; planner authorization, typed plan validation, actor-scoped claim, receipt | Trusted host/operator only. Plans and receipts are control-plane artifacts. |
| `POST /operations/{operation_id}/resolution` | `resolve` (operator); linked indeterminate resolution | Operator only; never a participant retry or recovery shortcut. |
| `POST /workflows/{workflow_address}/cancel`, `/workflows/reconcile-timeouts` | `mutate`; core workflow/run admission, receipt | Trusted host/operator only; host must authorize any user-driven cancellation. |
| `POST /participant-executions/{execution_scope_ref}/control`; `GET /participant-executions/{execution_scope_ref}` | `mutate`/`read`; backend execution control/readback, receipt or service state | Administrative service surface. Execution scope is not an audience-bound participant projection. |
| `POST /participants/{participant_address}/episodes/{initialize,reset,restart,terminate}` | `mutate`; typed lifecycle request, core episode/run state, receipt | Trusted host/operator only. Path and optional episode body are request data, not entitlement. |
| `POST /participants/{participant_address}/control-occurrences` | `mutate` plus core participant/controller binding and API-409 control admission | Authorized service controller only; control authority is distinct from view audience. |
| `GET /participants/{participant_address}/status`; `/episodes/{episode_id}/history`; `/context` | `read`; with resolver, participant/audience candidate and API-423/RUN-319 crossing before serialized API-408 view; without resolver, legacy projection | Trusted host identity only. Host releases a governed view solely for its separately bound caller, run, participant, exact episode and audience. The route's role check alone does not supply those bindings. |
| `GET /health/live`, `/health/ready`; framework `/openapi.json`, `/docs`, `/redoc` | No identity dependency; value-free health or API description | Deployment probe/administration network. No participant data authority; do not treat their reachability as permission to expose P2. |
| Audit log, snapshot/operation store, raw event and crossing histories, host callbacks | No P2 HTTP route for raw audit or an event stream; in-process/store access belongs to the owner/embedder. Histories also appear inside privileged snapshots and governed participant views. | Owner/operator only. A future event, subscription, export, callback, or cache endpoint must inherit the same release gate for each item and cannot expose raw histories to participants. |
| `RuntimeControlPlane` in-process methods, `RuntimeManager` direct execution, and offline store check/backup/restore | Trusted embedder, direct realization-backend authority, or owner-stopped maintenance; no HTTP participant authorization | Privileged host/operator path only. Store copies, direct snapshots and execution results must not become alternate participant reads or mutations. `RuntimeManager` does not coordinate with the control-plane owner on the same realization backend. |

The P0/P1 boundary is method access inside the embedding process; the P2
boundary also has transport authentication:

| Composition | RAE-enforced boundary | Host-enforced boundary |
| --- | --- | --- |
| P0/P1 SDK | Runtime ownership, target/run store scope, actor-bound mutation and readback, and a participant crossing when configured. `get_snapshot()` has no caller-identity gate; the SDK does not authenticate a product user. | Keep the control-plane object and store private; authenticate or otherwise identify the local/product caller; authorize its participant, episode, audience and operation before calling or releasing a result. |
| P2 HTTP over P1 | Configured bearer token or verified proxy identity, route role and exact target checks; operation actor/scope readback; participant/audience crossing only with a resolver. There is no participant-only read role, run/episode-bound HTTP credential, or automatic rejection of the legacy no-resolver view path. | Keep the P2 identity and socket private from participant clients; authorize the product caller and exact result scope; reject ungoverned views and reauthorize cached or replayed results. |

HTTP 4xx/5xx envelopes, validation errors, operation diagnostics, receipts,
status readback, and `X-RAES-Snapshot-Revision` are also output surfaces.
They must carry no secret or cross-participant payload. The host returns its
own bounded, participant-safe errors and never uses a 403/404 distinction or
raw RAE diagnostics to reveal another participant's existence. Participant
progress or notifications derived from operational results still need the
applicable governed carrier and release gate; renaming or filtering status
fields does not make an ungoverned participant feed safe.

The in-process row also covers `snapshot`, `get_snapshot`, `audit_log`,
`observation_execution`, participant action/control and decision-surface
admission, and `deliver_participant_directed_view`. These are not additional
participant transports: HTTP role dependencies do not wrap direct Python
calls, and possession of the SDK object grants access to its public methods.
Directed delivery is a separate crossing, not proof of participant
consumption. The current `raes_mcp` authoring/inspection tools are not a live
participant control-plane gateway; adding one would require the same boundary.

## Deployment and cross-cutting guardrails

- Keep P2 on an administration/service network. Terminate TLS, authenticate
  service callers, strip untrusted identity headers before setting verified
  proxy headers, and select exactly one worker with reload disabled. Use
  `ControlPlaneSecurityConfig.strict_defaults()` until explicit identities and
  secrets are loaded. Unknown bearer credentials must fail without header
  fallback. A reverse proxy route allowlist can constrain the host's outbound
  P2 traffic, but does not make a configured P2 identity narrower at the RAE
  auth layer.
- Reuse `ControlPlaneSecurityConfig`, `_ControlPlaneApiAuth`, the API request
  size and bounded offload guards, `ControlPlaneIdentity` and its subject
  bindings. RAE config currently has no episode- or run-scoped HTTP identity
  field; the host's selected run/episode must be checked against the pinned
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
  references only; never log bearer tokens, bodies, realization-backend
  exception text, source snapshot bytes, participant view payloads, or
  identifying paths.
  Validate any future projection response at its final sink, including cache
  hits, retries and error branches.
- Keep the P1 owner lease, private store directory/database permissions,
  immutable target/run scope and snapshot revision/CAS; the single-worker
  server rule applies when P2 is used.
  Build on `control_plane_store_local`, its scope/carrier validation and the
  existing store-maintenance interface for operational copies; do not add a
  parallel participant store or direct reader.
  Load secrets through the deployment's protected secret channel, outside
  process arguments and published config. Do not put a bearer token in a URL,
  environment dump, CLI argument, SDL file, fixture, or versioned artifact.
  Host caches must be private, bounded by caller/session plus target/run,
  participant, episode, audience, policy and source revision, and invalidated
  on authorization or state-cut change.
- For P0/P1 SDK embedding, keep the control-plane object and store inside the
  trusted process or trusted component. An in-process participant plugin with
  access to that object can call privileged methods; a host must isolate such
  code or avoid sharing one run with mutually restricted participants.

The extension seam is the host-to-RAE policy adapter: it maps a host-approved
`(target, run, participant, episode, audience, operation)` selection to SDK
actor and governed retrieval parameters, or to a configured P2 identity and
the same governed retrieval parameters. A future route-scoped P2 credential or
participant-safe transport requires its own reviewed RAE authorization change;
this decision grants none and changes no SDL identity or API-408/API-423 carrier.

## Composition and release checks

These are constraints on the existing boundaries, not additional middleware,
schemas, or a proposed implementation sequence. Module names below are in
`implementations/python/packages/` unless another root is given.

| Layer and canonical incumbent | Required boundary |
| --- | --- |
| P2 transport/config: `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_api_guards.py`, `control_plane_api/_offload.py` | Preserve immutable credential maps, valid distinct identity-header names, target equality, role checks, positive admission limits and bounded body reading before routing. The host must authorize its participant-facing caller before releasing results; caller-supplied headers or selectors cannot mint P2 bindings. A shared service identity is not an end-user identity. |
| Runtime composition: `control_plane_configuration.py`, `control_plane_composition.py`, `control_plane_profiles.py`, `registry.py` | Use normalized `run:<id>`, an explicitly selected P0/P1 core with optional P2 adapter and admitted realization-backend capabilities. A participant-facing host requires the crossing resolver and its trusted `resolve_participant_view_evidence` hook for retrieval; the current legacy path does not enforce this requirement. Preserve explicit final-sink selection: selected SEM-233 enforcement requires `resolve_flow_sink_decision`; selected RUN-320 modular control requires its admitted binding/capability. Do not disable enforcement to make an incompatible resolver start, or confuse a manifest declaration with an installed enforcement provider. |
| Portable shape and contextual authorization: `raes_contracts/contracts/participant_views.py`, `participant_crossing_validation.py`; `raes_runtime/participant_crossing_mediation.py`, `participant_flow_sink.py`, `participant_control_orchestration.py` | Reuse API-408 model validation and API-423 context validation plus operation-bound policy, audience, history-cut and selected final-sink checks. Validate transformed egress against the committed subject. A well-formed view, a visibility-projection ref or a successful HTTP status is not independently verifiable crossing evidence; deployment composition and the governed path supply that assurance. |
| Secrets and environment: `raes_contracts/secret_references.py`; `raes/runtime_environment.py`, `runtime_generated_value.py`, `runtime_configuration.py`, `runtime_values.py` | Service credentials remain deployment secrets outside SDL. This decision introduces no env parser or secret loader. If deployment assets describe runtime env inputs, retain unique names, explicit sensitivity/provenance, redaction, literal/`value_from` exclusions and generated-output reference checks. `SecretReferenceId` is a logical reference, not a bearer value; generated values cannot masquerade as out-of-SDL `operator_secret` material. |
| Host/process and persistence: `control_plane_store_lease.py`, `control_plane_store_paths.py`, `control_plane_store_local.py`, `control_plane_store_records.py`, `control_plane_store_maintenance.py` | Enforce private owner-controlled paths, strict durable codecs, one target/run and one owner. For P2 keep `WEB_CONCURRENCY`/`UVICORN_WORKERS` at one and reload off; proxy/network isolation must prevent direct socket access that bypasses verified-header authentication. Keep configured P2 credentials out of argv, shell tracing, environment dumps, access logs, crash reports and exported backups/config. Store backups remain privileged even when diagnostics are redacted. |
| Errors and observability: `control_plane_api/_responses.py`, `_operation_routes.py`, `raes_contracts/diagnostics.py`, `raes_runtime/control_plane_audit.py`, `backend_result_diagnostics.py` | Use existing coarse conflict/422/500 envelopes and portable diagnostics; no raw validation input, exception text/type/chain or provider payload. Preserve the selected denial response when secondary audit fails. Keep terminal operational audit atomic with state; best-effort transport rejection audit is a separate guarantee. Backend, reverse-proxy and ASGI logging must obey the same disclosure boundary. |

Shared P2 service identities need special care. `operation_actor_scope` and
`control_plane_admission` bind RAE claims/readback to the supplied operation
actor and its complete authorization scope, not the host's user/session. The host
must associate each client request and operation reference with its authorized
selection and map client retry keys into that ownership context; forwarding
arbitrary client keys into a shared service namespace is unsafe. Preserve the
mapping for a genuine retry, reauthorize every release, and never generate a
fresh key automatically after timeout, disconnect or an uncertain result.
Changing subject bindings can change the immutable scope and legitimately
make old readback unavailable; do not work around that by dropping the scope
check. Product-user correlation belongs in host audit, not a second RAE actor
model or credential-bearing operation context. In P0/P1 the host supplies the
typed operation actor directly and owns its mapping to product callers.

`RuntimeControlPlane._project_snapshot_read` returns the observed projection
revision, not a promise about the latest state after the crossing commit.
An idempotent egress can return its retained governed result;
`participant_crossing_projection.stable_projection_subject` normalizes only
runtime-owned revision paths. Do not rewrite retained source refs to a newer
header/revision or use that normalization as host cache authorization.
Reauthorize against the selected episode/policy and obtain a fresh governed
projection when a current view is required. Governed GETs must not be served
from a shared proxy/browser cache: host delivery must pass its release gate
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
`implementations/python/tests/`. They do not demonstrate a host's caller
entitlement, revocation, session isolation or cache policy. Those need evidence
at the host boundary, including cross-participant/episode requests and
authorization changes during delivery; P2 hosts also need a shared service
identity case.

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
participant, or that a host can delegate its broad P2 read identity.
Avoid filtering a full snapshot in the browser/host as a substitute for
governed projection, treating possession of an operation ID or a
`ParticipantAudienceSubjectBinding` as global read authority, caching a view
without its exact scope, and allowing a generic proxy, event stream, error or
retry path to bypass the host gate.
