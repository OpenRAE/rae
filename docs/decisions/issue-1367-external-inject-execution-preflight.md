# Issue #1367 — External inject execution through the shared runtime

Date: 2026-10-15. Architecture preflight for issue #1367 across API-404,
DSL-111 and RUN-314. Prerequisites are #1366,
#1359 and #1362. Existing authoring and published occurrence contracts establish
part of DSL-111; their trace links do not establish externally triggered runtime
execution. This note changes no runtime, schema or capability claim and is not
an implementation plan.

## Existing decisions and integration boundaries

Retain [ADR-112](adrs/adr-112-external-inject-triggering-and-execution.md),
[EI-01–EI-06](../../specs/sdl/external-injects.md),
[ADR-104](adrs/adr-104-runtime-control-plane-architecture.md),
[ADR-113](adrs/adr-113-reusable-execution-machinery.md) and
[ADR-063](adrs/adr-063-reference-emulation-backend.md). The
[inject contract reference](../explain/reference/inject-occurrence-contracts.md)
already specifies the request, occurrence, outcome, correlation and pure
validators. Its adoption/security rules apply here. No new ADR is needed.
Python paths below are relative to `implementations/python/packages/`.

API-404's profile qualification applies to the whole occurrence path. Reuse
`control_plane_profiles.py::select_profile()` / `require_profile_capabilities()`
and `adapt_control_plane_store()`; no inject-specific profile registry is needed.

| Stable clause | Application to #1367 |
| --- | --- |
| API-404-C1 | P0/P1/P2 retain typed actor/scope admission, exact retries, one mutation authority, revision CAS and atomic outcome/audit publication. In P0 those facts last only for the live process. |
| API-404-C2 | Crash-persistent occurrence, slot, order and invocation claims require P1/P2 store ownership, strict versioned reopening and recovery without redispatch. A memory store's atomic interface alone proves no process-loss durability. |
| API-404-C3 | A named P2 trigger/readback surface requires `create_control_plane_app(profile=P2)` over an explicitly selected P1 core, with sealed method-bound administrative admission, bounded workers and actor-authorized disclosure. Direct P0/P1 calls trust their embedder rather than authenticating a transport. |
| API-404-C4 | Publish only supported, evidenced compositions. Omitted profile selection makes no named-profile claim; an executing backend, PostgreSQL or Temporal cannot promote the composition to P3 or imply exactly-once effects. |

Repository inspection identifies these boundaries that publication alone does
not bridge:

- `control_plane.py::submit_orchestration()` installs a plan through
  `Orchestrator.start()`. `ReferenceOrchestrator` records bound/queued entries;
  `InProcessDriver` records operations. Neither executes authored inject
  content. A trigger must resolve and execute the pinned source against each
  selected concrete target through an explicitly installed executing adapter.
  Description-only injects remain valid authoring but unsupported execution.
- `control_plane_supervised_execution.py::invocation_request()` produces native
  plan commands. `require_backend_execution_policy_admission()`,
  `operation_policy_admission.py`, `operation_provider_execution.py` and
  `operation_worker_authority.py` assume native plans and owner-private native
  commitments. An inject invocation instead commands exactly
  `inject_occurrence_reference(occurrence)`. Resolve that command through its
  trusted owner and retain the selected admitted plan's policy/budget checks;
  do not pass an occurrence as a plan, relabel it `orchestration-plan-v1`, or
  bypass policy to make dispatch work. Native policy validation also equates
  the command and invocation identity with `plan.operation_id` when present;
  do not reuse the plan-installation operation ID for a fresh occurrence or
  mutate the authorized plan to force that equality. Keep native-plan
  validation intact.
- `operation_provider_execution.py::_finalize_native_outcome()` requires a
  `runtime-snapshot-v1` result. The published inject fixture instead produces
  an `associated-artifact-manifest-v1`. Resolve and validate the typed
  occurrence outcome separately from the produced result and any native
  snapshot transition. `OperationEvidenceResolver.resolve_result()` also
  promises `ApplyResult`, not an arbitrary artifact: extend the owning typed
  result boundary deliberately, rather than returning an artifact under that
  signature or widening all results to unchecked dictionaries. The outcome
  embeds the backend response; using the
  outcome itself as that response's produced result creates a circular
  commitment. Reuse `TerminalCommitMode.OPERATION_ONLY` and the existing
  `settle()`/atomic terminal commit for an artifact-only result; publish a
  snapshot only when a validated native transition exists. Operation-only
  commits do not advance snapshot revision, so that revision cannot substitute
  for the inject ordering-head comparison. No empty snapshot or participant
  view substitutes for readback.
- `ControlPlaneOperationRecord`, `_OperationRecordModel` and `InvocationLedger`
  have no typed occurrence/outcome fields. Extend the incumbent ledger and
  strict codecs, identity/transition validators and supported store versions
  together. Do not hide authority in `result_payload`, snapshot entry metadata
  or process-local maps. `result_payload` already has observation and crossing
  consumers; overwriting it can erase unrelated evidence.
- `claim_record()` atomically claims actor/kind/client keys and effect
  reservations, but not inject occurrence/slot/order identities or the run's
  expected ordering head. Those facts and the expected store cut must be one
  store transaction with the operation claim. A preflight lookup plus ordinary
  `claim_record()` is insufficient. `validate_inject_occurrence_claims()` has a
  1,024-claim bound and cannot verify the opaque head chain; it is no concurrent
  index or ordering authority. Preserve uniqueness across reopening and
  retention, or refuse at a declared capacity; never truncate claims to fit.

The shared runtime owns admission, trusted order, dispatch permission,
supervision and terminal publication. The concrete backend owns artifact
execution, native target access, protected input/secret resolution and
effect/cessation readback. Backend declarations and shape checks establish
neither willingness nor realization. General world execution requires no
participant, controller, episode or participant-runtime component.

Planner authorization is currently process-local:
`RuntimePlanAuthorizationMixin` trusts registered composite-plan digests, not
caller-provided plan JSON or a matching reference alone. Reopening a store
restores claims and evidence, not that registration, native HMAC keys, live
deadlines or dispatch grants. Startup currently cancels write-ahead accepted
work and marks consumed invocations indeterminate. Preserve that conservative
boundary; trusted reconstruction for read-only reconciliation must not become
fresh execution authority. The occurrence's pinned source and selected bindings
must remain resolvable for evidence without re-resolving floating authoring.

## Cross-cutting layers and canonical incumbents

| Layer | Required reuse and guardrail |
| --- | --- |
| HTTP trust boundary | Compose routes inside `create_control_plane_app()` before `_require_route_transport_authority()` and the composition seal. Use `_AdministrativeMutationIdentity` for triggers and `_AdministrativeReadIdentity` plus core actor/scope authorization for readback. P2 is a host-mediated administrative service, not a participant endpoint; an auditor cannot trigger. `ControlPlaneSecurityConfig.strict_defaults()`, exact target binding, invalid-bearer hard failure and explicit proxy trust remain mandatory. A request's carried identity/admission fields confer no authority. |
| Ingress and contract validation | Count bytes with `RequestSizeLimitMiddleware`; use `raes_contracts/json_ingress.py::parse_bounded_json_object` with explicit byte/depth bounds before ordinary JSON decoding loses duplicate keys or accepts nonfinite values. FastAPI's normal body decoding plus a Pydantic model does not provide this guarantee. Preserve authentication-before-detailed-validation-error behavior. Reuse `InjectTriggerRequestModel`, `OperationContractModel`, bounded strict primitives and cross-message helpers for HTTP, direct calls, resolved artifacts and restored records. Keep `request_key` the single retry identity; if HTTP also uses `Idempotency-Key`, require agreement rather than creating two claims. |
| Authored intent, target and time | Reuse `raes` authoring/reference validators, `raes_processor/compiler/orchestration.py`, canonical address rendering and `RuntimePlanAuthorizationMixin`. Resolve the exact planner-authorized execution plan and its node/binding/instance revisions, source and realization pins. V1 selects only compiled `Node.injects` bindings; entity names and address suffixes cannot select a host. Namespaced node and inject names both contain dots. Retain intrinsic/event/schedule assertions through the proposition/assertion owner (`proposition_truth_contracts.py` validates carried truth), plus shared `time_coordinator.py`/time contracts. Unsupported, unknown, stale or ambiguous truth/targets refuse. Independent placement cannot bypass applicable preconditions. |
| Artifact and input trust | `OperationArtifactReferenceModel` provides identity/integrity, not authenticity, fetch permission or evidence truth. Reuse `raes/_source.py` artifact requirements, `raes_processor/semantics/artifact_realization.py` and reusable-asset trust policy under ADR-071/077. Backend-owned source resolution must honor their admitted routes/provenance; these validators do not acquire payloads. `validate_associated_artifact_manifest()` checks immutably staged bounded readers, not arbitrary URIs or archives. Resolve floating authored sources once to immutable execution pins. The admitted realization owns a closed, bounded input contract; omitted input means no parameters. No request-supplied executable, callback URL/path, arbitrary command or replacement source. |
| Secrets and environment shapes | Reuse `SecretReferenceId`, `runtime_fact_binding_policy.py` and protected dispatch patterns where applicable; their participant-specific admission is not a prerequisite for a world inject. `Inject.environment` is a string list with no assignment/shell grammar. Runtime bindings use `RuntimeEnvironmentVariable`/`runtime_generated_value.py`: valid names, literal/`value_from` exclusivity, no `operator_secret` generated value, and raw-value omission for redacted/operator secrets. Reapply visibility/freshness/type gates on rebinding. Account-specific redaction in `control_plane_operation_context.py`/`control_plane_store_payloads.py` does not protect arbitrary inject material. |
| Composition and provider admission | Extend `ControlPlaneOptions` and `ControlPlaneConfiguration` together for any necessary trusted resolver capability, including installed call-shape validation. Retain normalized `run:<id>`, typed profile/supervision and strict finite apparatus bounds. Build on `RuntimeTarget`/`RuntimeTargetComponents`, `registry_target_validation.py`, `manifest_authority.py`, `require_inject_occurrence_provider()` and `require_backend_operation_admission()`. Both inject backend IDs and all four operation protocol IDs, installed methods, exact capabilities and current willingness must agree. Missing guarantees refuse. Backend profiles and runtime P0/P1/P2 guarantees are separate axes; P3 stays unavailable. |
| Execution and persistence | Reuse `RuntimeMutationAuthority`, `LocalExecutionAdapter`, `claim_accepted()`/`settle()`, `InvocationLedger`, `ControlPlaneStoreCommitAdapter`, `control_plane_durability.py` and the memory/SQLite/PostgreSQL store owners. Preserve short state cuts, separately bounded effect/control/store capacity, write-ahead one-use grants, owner/execution generation fences and effect reservations. Backend calls run outside transactions/state permits. Expected head, semantic order, clock coordinate, snapshot revision and attempt generation are distinct. Atomic terminal state/outcome/audit publication and revision CAS remain authoritative. Lost store acknowledgement poisons/reconciles through existing durability handling; it cannot grant dispatch. |
| Outcome and native-result admission | Use `require_inject_occurrence_invocation()`, `validate_backend_operation_response()`, `validate_inject_occurrence_outcome()` and `OperationEvidenceResolver`. Verify evidence content/authenticity and every selected binding in request order, not merely digest syntax or nonempty refs. Retain `finalize_protocol_result()`/`_validated_backend_result()`, predecessor isolation, realization authority, changed-address, workflow/participant/time and credential-egress checks whenever a native snapshot is published, including failed/partial/recovered results. Artifact-result validation belongs to its owning contract. A backend's success/release booleans cannot replace runtime release gates. |
| Errors, audit and observability | Reuse `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload()`, canonical terminal diagnostics, `_responses.py::_conflict_detail()` and redacted 422/500 handlers. Authorize claim/outcome/correlation access through `_operation_read_allowed()` before disclosure; unknown and unauthorized readback are indistinguishable. Reuse `AuditEvent` and `control_plane_audit.py` action-specific closed detail keys; arbitrary inject dictionaries are rejected. Keep bounded best-effort denial audit, fixed logger labels and `Cache-Control: no-store`. No raw exceptions, Pydantic input echoes, native stdout/stderr, credentials or provider locators in errors/progress/audit. ADR-066 and `observability_plane_semantics.py` retain distinct operational, participant and archival evidence roles. |
| Host, OS and optional remote delivery | Preserve the [P2 deployment boundary](../public/guides/control-plane.md): private service credentials/storage, TLS/proxy limits, counted bodies, one worker, bounded offload/drain and lease-before-store-inspection. Native drivers retain target ownership/revision verification and private native IDs. Reuse their fixed argv/bounded-call patterns without claiming their provisioning/read-only methods already execute injects. No secret in argv, URLs, shell interpolation, environment dumps, artifacts or engine history; no broad inherited environment or new credential loader. Optional remote delivery retains `RemoteAuthorityConfiguration` HTTPS/protected-token/bounds checks and `RemoteOperationAuthority` header-only credentials, no redirects and `trust_env=False`. No new service/hosting or transport is required by this issue. |

RFC 8785 commitments cover the actual portable carriers, including references.
Only approved non-secret references belong there; identifiers and guessable
secret digests can disclose material too. Preserve native-plan HMAC ownership
in `operation_command_commitment.py`; it is not a replacement for the published
occurrence digest. Sensitive inputs need the existing value-free/ephemeral
exact-retry boundary extended deliberately. Loss of ephemeral proof after
restart retains the claim and refuses unverifiable equality, never redispatches.

The HTTP byte limit does not bound referenced source/input/evidence content,
decompression or native output. Their owning resolvers/adapters must enforce
content and output bounds before buffering/decoding and share the original
shrinking deadline; per-binding callbacks cannot renew it. Artifact IDs remain
logical references, never fetch URLs or filesystem paths supplied by a caller.
`RuntimeEnvironmentVariable.validate_name()` checks nonempty names and rejects
`=`, but is not a complete native process validator. The selected adapter must
also reject NULs and unsafe native argument/environment shapes, control inherited
environment and working-directory/executable selection, and use its protected
input channel for secrets. Passing a schema is not permission to interpolate a
value into a shell or expose it in argv.

`OperationIdentifier` is length-bounded, not a safe filename, environment name,
shell fragment or native resource selector. Keep it opaque; use encoded route
segments, parameterized store queries and backend-owned target lookup. Reuse
`raes_backend_protocols/naming.py::provider_resource_name()` for compiler-owned
resource addresses when native naming is needed. Do not add sanitization that
changes the portable identity or aliases two claims. If optional worker RPCs
carry inject artifacts, `RemoteOperationAuthority._rpc()` currently uses ordinary
`json.loads`: its byte limit alone does not reject duplicates/nonfinite values.
Apply the shared strict ingress at that adoption boundary too.

## Concrete realization boundary for RUN-314

Reuse `raes_reference_backend/target.py`'s descriptor/config factories and the
same admitted driver/resource owner used by its provisioner. Carry the installed
provider through both `RuntimeTargetComponents` and direct `RuntimeTarget`
construction. Gate declarations on the configured executing adapter; enabling
OCI provisioning must not make the default `InProcessDriver` or every backend
claim inject execution. Keep `envelopes.py`, the selected published
`contracts/realization-envelopes/` artifact, manifest configuration digest,
SEM-218 provenance and registry shape checks consistent with that mode.

`drivers/oci.py` and `drivers/oci_observation.py` already own workspace labels,
native IDs and current-resource readback. Resolve the selected instance/revision
through that owner immediately before effect and readback; never select a native
object by an address suffix or accept a daemon ID from the caller. Existing
`compute-substrate` observation proves owned container presence, not that the
authored payload ran or its requested effect occurred. Inject evidence must
bind its own occurrence, source/input pins, selected targets and observed
effect. Libvirt's `guest_transport.py` is a bounded facts reader, not a command
channel. Neither driver provides a generic inject executor today.

Retain `drivers/oci_image_trust.py::ImageTrustPolicy` for any OCI image launch;
a syntactically valid digest pin alone proves no publisher authorization. The
admitted realization must also bound execution identity/privilege, target paths,
network/host access, payload size, output collection and elapsed time. Fixed
argv prevents shell interpolation, not option injection or overbroad execution
authority; do not pass authored shell strings, inherit host credentials, mount
host/daemon sockets into payload containers or add privileged host access to
make an inject work.
`_invoke()`'s `capture_output=True` is not an output-size bound for executable
payloads. Use the protected input channel admitted by the adapter, keep native
output private, and treat a timeout after possible dispatch as uncertain until
effect/cessation readback establishes otherwise.

## Truthful settlement, recovery and participant joins

| Fact at the boundary | Permitted claim |
| --- | --- |
| Denied before claim | Bounded rejection audit, no accepted occurrence or invocation. |
| Claimed, then authority/precondition/willingness fails before dispatch | Existing `CANCELLED` withdrawal with refusal diagnostic and retained claims; no fabricated backend outcome. |
| `start_operation()` refuses | Only validated per-binding absence/cessation evidence permits `effect-absent`. The generic provider path currently retains `INDETERMINATE` after consumed-grant refusal; do not weaken that fallback for missing evidence. A `check_operation()` refusal is not outcome readback. |
| Backend reports completion | `effect-applied` requires every binding applied with cessation and verified readback. Success additionally requires validated produced result, required evidence and release gates. Fully known mixtures remain `known-partial`; any unknown/unceased target makes the aggregate `indeterminate` while preserving known facts. |
| Timeout, exception, invalid/foreign evidence or effect-before-terminal-commit failure | Retain uncertain effects and conflicting reservations. An unsuccessful `ApplyResult`, cancellation acknowledgement or predecessor snapshot proves no absence or rollback. |
| Crash or late evidence | Observe the original pins/attempt through existing supervision/reconciliation owners; append attributable linked evidence, never reissue the consumed grant or rewrite terminal history. Administrative resolution alone proves no cessation. |

Occurrence IDs, retry keys, operation IDs, schedule slots and attempt/invocation
IDs remain distinct. Exact authorized retry returns the original operation and
occurrence plus any committed readback/correlation, without renewed admission,
budget or execution. Fresh permitted repetition requires a fresh occurrence/key.
Scheduled and external requests
share one trusted ordering authority; stale heads refuse without rebasing.
Arrival order, lock acquisition and UUIDs are not that authority. Preserve
conservative target/run exclusion unless resource independence is admitted;
binding-address narrowing alone does not isolate expanded target instances.

Persist the world outcome independently of disclosure/delivery/observation.
`inject_occurrence_correlation()` and
`validate_inject_occurrence_correlation()` join only a validated, committed,
successful applied outcome and its produced result. Expose that exact join to
authorized consumers without implementing a new participant delivery service.
Existing DSL-142 delivery, API-423 crossing/final-sink and ADR-110 control
occurrence owners retain audience, episode, independent policy/time/marking and
delivery-reservation checks. Correlation grants none of those permissions.
Delivery denial cannot undo world success; required delivery may still withhold
composed progress. A retry of delivery cannot refire the inject. Legacy fixed
event/script/story anchors retain their meaning; do not synthesize anchors or
relax old readers to accommodate a new occurrence.

## Extensibility, assurance and exclusions

The necessary seam belongs at trusted resolution of a versioned realization's
source/input/target/evidence contracts, composed through the existing runtime
configuration and operation provider. Another inject artifact or executing
backend should supply another admitted binding/profile, not require editing a
central inject-name switch. V1's non-node target limitation requires an explicit
versioned contract extension, not an inferred host or a free-form metadata bag.
Runtime policy, ordering, retries and terminal commits stay shared; this seam is
not a plugin registry, command language or second scenario interpreter.

Use the #1353 bounded model and #1423/#1366 fixture tests as semantic/contract
witnesses only. In particular, `test_issue_1362_provider_execution.py` uses a
no-op provider with synthetic absence evidence; it cannot establish this issue's
world execution. Reuse its synchronization patterns, #1184 atomic-claim tests,
#1187 durable/process-loss/security fixtures, and #1362 provider/lost-ack,
reconciliation, state-authority and HTTP-capacity tests. Extend #1359's exact
route inventory/request matrix for every new served route.

Acceptance needs the actual public/core/store/executing-adapter path: a
participant-free authored payload changes its selected target and independently
read-back content reflects that payload; exact duplicates execute once;
pre/post-claim refusal does not execute; failed execution distinguishes known
absence/partial effects from uncertainty; crash/reopening and reconciliation do
not execute again. Include competing occurrence/slot/head claims, stale or
namespaced bindings, unknown assertions, malformed/secret-bearing inputs,
foreign/late results, missing fan-out reports and unauthorized readback/leakage.
Observe actual target effects and durable facts, not only call counts or a
provider-returned success flag. Concrete backend evidence must disclose the
adapter/environment and failure cut; label fixtures/models separately.
Crash/durable-correlation evidence requires a real durable P1/P2 store; a P0
in-memory witness cannot supply it. Cover every composition advertised as
supported, including worker grant/result paths when remote delivery is enabled.

For RUN-314, extend the existing reference-backend evidence family rather than
adding a competing native-runtime harness. `test_reference_backend_oci_driver.py`
covers argv/trust/redaction with substituted runners; it is not concrete effect
evidence. `test_reference_backend_docker_integration.py` and
`test_reference_backend_docker_gate.py`, `integration_docker` in `noxfile.py`,
and `.github/workflows/release-please.yml` own real-container admission. Keep
the [#1110 exact-SHA release gate](issue-1110-required-container-release-gate.md)
required and reject missing runtime/image, skips or zero collected tests there.
Its existing provisioning/conformance evidence alone does not prove inject
execution. Reuse `tools/oci_release_image.py` and the current reviewed
`release-test-alpine` entry in `implementations/tooling/artifacts.lock.json`,
not the historical image digest in that design note. Real integration remains
CI work; this preflight neither executes payloads nor provisions infrastructure.

Repository consumers in scope include HTTP/OpenAPI and core facades, target
registry/manifests/profiles, artifact/evidence resolvers, all supported store
codecs/reopening/maintenance, local and optional remote worker paths, receipt/
status readers (including CLI/MCP), participant consumers and packaged corpus.
Optional PostgreSQL retains `PostgreSQLStoreConfiguration` protected-password,
TLS and connection/statement/lock bounds, and its single-owner ledger remains
separate from engine history. Any dependency change uses the canonical
`implementations/python/{pyproject.toml,uv.lock}`, tooling development profiles
and `implementations/tooling/artifacts.lock.json` with their existing generators
and `.github/workflows/canonical-verification.yml`; no parallel installer.
Preserve old closed receipt/status schemas unless a governed change is needed.
Use `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/verification_plan.py`, repo policy and ADR-015/036 import/source-size
rules. Published contract changes require schema/generator parity, invariant
bindings, facade/version/allowlist/corpus consistency and current v2 publication
records in `contracts/schema-publication/entries/` (tombstones for removals),
with the existing schema/publication/coverage tools. JSON Schema annotations do
not run contextual validators; the conformance registry currently does not
register the inject contracts. Do not claim conformance-CLI adoption from
fixtures alone. Supported historical stores must preserve claims/evidence;
unsupported readers refuse rather than dropping them. No historical queued
record can be migrated into an evidenced occurrence. Keep DSL-111 traceability
bounded to delivered behavior; API-404 and RUN-314 retain their separate security
and backend assurance obligations. When the branch has no requirement UID, set
`RAES_REQUIREMENT_UID` to the requirement being checked: `API-404`, `DSL-111`
or `RUN-314` for its respective security, modeling or backend boundary. Run
targeted checks locally;
full/integration/fuzz/completion suites belong to CI. Release automation owns
changelog/version files.

Non-goals: implementing the issue during preflight; new SDL grammar or mandatory
participants; participant registration, disclosure transport or control-model
redesign; arbitrary remote execution; a second scheduler/store/workflow engine;
duplicate schemas, validation or exception/audit hierarchies; new trial or
automatic retry/resume/rollback allocation; universal cancellation or exactly-once
remote effects; P3/multi-writer operation; new infrastructure or backend-wide
capability claims. Delivery is bounded to the accepted trigger/occurrence path,
necessary trusted resolution and concrete execution, durable truthful readback,
authorized correlation and evidence for those behaviors.
