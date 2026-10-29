# Issue #1017 — Executable mixed-backend conformance

Architecture preflight, 2026-10-28. The supplied issue title, body and acceptance
criteria are the contract; there is no attached requirement. This is design
guidance, not an implementation plan or an assertion of backend support.

Retain [ADR-102 §13](adrs/adr-102-mixed-cross-backend-participant-control.md),
[ADR-110](adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md),
[ADR-113](adrs/adr-113-reusable-execution-machinery.md), and
[ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md). The
[mixed execution reader rules](../migration/mixed-backend-execution.md),
[reusable control rules](../migration/reusable-mixed-control.md), and
[backend conformance guidance](../explain/reference/backend-conformance.md)
already establish the architecture. No new ADR or accepted-text amendment is
needed. Current source supersedes historical inventories in the
[#1372](issue-1372-mixed-backend-execution-preflight.md) and
[#1364](issue-1364-repeatable-control-cancellation-preflight.md) preflights.

## Decisions and current support boundaries

Python paths below are relative to `implementations/python/packages/`.

- Extend the `raes_conformance.conformance` verifier and its existing report
  family. Exercise admitted compositions through `RuntimeControlPlane`, exact
  `RuntimeTarget` allocations, and the shared invocation machinery. Contract
  corpus validation remains useful shape evidence, never executable capability
  evidence. Do not add another dispatcher, supervisor, policy fold or ledger.
- `raes_cli/conformance.py` currently calls only `run_fixture_suite()`.
  `run_target_conformance()` accepts a single target and injected harnesses;
  neither the CLI's fixture pass nor its profile inference certifies a mixed
  composition. Unknown live profile surfaces already fail closed. Independently
  runnable cases need a public, documented callable/example using trusted
  installation, with explicit case selection and machine-readable results;
  importing private pytest helpers is not that interface. Keep the existing
  fixture CLI behavior truthful and preserve the API-stable conformance facade.
- Reuse `MixedRuntimeBinding.backend_installations`,
  `MixedBackendInstallation` and `MixedBackendService` for the selected edge or
  transition. `MixedEdgeExecutionBinding` / `MixedHandoffBinding` callbacks are
  historical executable paths with different contracts; exercising them alone
  cannot establish adoption of the revised portable carriers. Assert that the
  actual invocation retains the mixed binding, shared request and stage reports.
- **There is no supported joint reusable-control/mixed-runtime path today.**
  `ControlPlaneConfiguration._require_mixed_control_configuration()` explicitly
  rejects `mixed_control` together with `mixed_runtime`. Its constructor also
  rejects distributed execution with portable mixed installations. Include these
  as explicit unsupported combinations. Separate #1364 and #1372 passes cannot
  establish their conjunction. Removing those gates or inventing an adapter to
  evade them is runtime integration work, not conformance verification. A future
  joint positive claim requires independently delivered, supported integration.
- ADR-115 keeps concrete backends, native readiness, credentials and resource
  lifecycle in backend distributions. RAES owns portable cases and injected
  conformance interfaces. RAES must not discover/import a backend distribution,
  contact a daemon or load credentials automatically. A reference/test service
  can establish a bounded runtime witness, never concrete realization. Do not
  resurrect removed libvirt, TechVault or cross-backend corpus workflows based
  on historical docs. Native evidence remains a backend-distribution gate.

The extension seam is the existing trusted runner/harness configuration. It
parameterizes these inputs:

- the admitted composition/entry;
- installed targets and per-role service pins;
- the compiled control policy/episode where supported;
- the independent evidence/readback owner;
- case selection and finite supervision bounds.

Another
bridge, mapping, backend configuration or loss profile should use that seam
without backend-name branches, executable identifiers in portable data, or edits
to a second capability table. Keep backend profile contract sets in
`contracts/profiles/backend/`, loaded by `raes_contracts.backend_profiles`;
live behavior still needs an explicitly supported runtime surface.

## Evidence obligations

Reuse `validate_mixed_backend_bindings()`, `require_mixed_backend_admission()`,
`validate_mixed_backend_stage_reports()` and `established_mixed_backend_state()`
with their original contextual owners. Pure validators check consistency;
`OperationEvidenceResolver` and authenticated installed readers establish the
provenance and meaning of evidence. A self-labelled producer/digest/reference,
distinct Python object, common interface, or echoed request is insufficient.

| Claim or negative case | Required witness at the owning boundary |
| --- | --- |
| Selected allocation and mapping | Observe the exact admitted destination provider and its native action/readback. Demonstrate a non-identity native translation or admitted affine mapping with a distinguishable expected result, preserving compiled participant/action, configuration, authority and audience. Wrong, missing, foreign or stale bindings refuse with zero owning effect calls. A mapping callback name proves nothing. |
| Timing and ordering | Drive the installed coordinator over committed two-clock readback and verify the mapped rational coordinates, segment, microstep, ordering basis, coupling and post-call readback. An incomparable grant prevents dispatch; missing evidence stays unknown. Receipt order, wall time and sorted report sequences cannot prove governed order, physical synchronization or a hard real-time guarantee. Do not round an inexact tick into an exact one. |
| Dispatch refusal | Exercise willingness changing after initial acceptance and after a time grant, before the one-use effect claim. `mixed_backend_invocation._coordinate_dispatch()` re-admits before `_dispatch()`; test that boundary as well as construction failure or an always-refusing backend. Retain audit-only pre-claim refusal, shared cancellation before dispatch, and evidence-based settlement after a consumed grant. No fallback provider or weakened guarantee follows refusal. |
| Execution, delivery, observation | Verify bridge effects through native result validation, destination receipt through its pinned reader, and participant/audience observation through its own authorized reader. Missing delivery does not erase execution. Observation is optional unless demanded; absent optional observation must not manufacture a fact or invalidate otherwise verified success. A status response, audit event or archive record is not participant observation. |
| Declared losses | Check the admitted loss and evidence references against the transformation and observed readback, retaining limitations in reports/history. Include undeclared or contradictory loss and missing evidence. Merely copying a limitation reference is not verification; exact support cannot be silently weakened. |
| Native handoff | Transfer and independent owner/time readback must bind predecessor history head, phase revision, original owners and order. Stale/failed handoff retains the prior phase only with confirming readback; uncertain responsibility blocks dependent work and does not authorize source continuation. Native responsibility, acting controller and execution-owner generation are different facts. |
| Repeated control | On supported #1364 paths, repeat take/return and proposal/decision/cancel cycles with fresh occurrence/proposal identities under the same admitted policy. Reuse the canonical contextual validator/fold and live-cut owner. Check revision/head/order fencing, revoked authority and stale approval at actual action admission. A finite scripted sequence or repeated policy-edge metadata alone is insufficient. Report the unsupported joint mixed-runtime path separately. |
| Partial, unknown and cancellation | Retain validated residual effects, stage facts and reservations. Shared and mixed transcript gates jointly decide settlement; partial/unknown mixed execution or unresolved delivery remains `INDETERMINATE`, with no new `PARTIAL` operation state. Control acceptance does not establish PREVENTED, PARTIAL_LIMITATION or TOO_LATE: those need target-owner evidence. Timeout, lost reply or worker termination proves neither cessation nor absence. |
| Replay, recovery and cleanup | An exact authorized retry, repeated receipt, reopen or late completion must not reissue a consumed effect or rewrite a terminal parent. Verify retained stages, original installation, residual scope and readiness/exclusion after loss of acknowledgement. Cleanup is independently observed, bounded and resource-scoped; incomplete cleanup stays visible. Unresolved work must retain its owner/resources; do not discard it to make the case stop. |

Each independently runnable case needs isolated setup and an explicit expected
disposition, including negative cases whose *correct rejection* passes the case.
Unsupported execution is a separate non-passing outcome for a requested claim,
not a passing negative test or an omitted/skipped matrix entry. Bound candidate
combinations; enumerate the tested selection and unsupported requests without
claiming a Cartesian product of all backends, mappings and guarantees.

Use `ConformanceCaseResult`, `BackendConformanceReport`,
`backend_conformance_report_payload()` and `validate_backend_conformance_report()`.
Reuse `BehavioralClaimBindingModel` and the governed behavioral relation catalog
for bounded scope and explicit nonclaims. Retain these facts:

- each component's backend/version, manifest, envelope and configuration identity;
- the admitted profile/entry and the mapping/service pins;
- the probe/probe-set and the tool/environment identity;
- the evidence origin and the producer/reader provenance;
- expected/accounted operations, execution basis and cleanup/residual facts.

One aggregate configuration digest is insufficient
without resolvable component coordinates. Add only missing coordinates to the
incumbent case/report projection, with its validation; no parallel report schema.

Keep `fixture-only`, `hermetic-live`, and `native-live` distinct from realization
ownership and observed-execution provenance. A caller-selected execution-basis
label cannot upgrade reference evidence. The report already checks assurance
chains and requires exact digests for backend-conformance claims; preserve those
checks and ensure mixed cases supply authenticated underlying evidence. The
current report-level native flag check only requires some native case; it does
not establish native execution of every requested mixed obligation. Require
complete requested coverage and consistent case outcome/pass fields: empty case
sets or an unrelated native pass cannot certify the combination. Never drop
failed/unsupported cases or promote finite probes to universal proof. An
independent expected-observation inventory must not be derived from the backend's
answers.

## Cross-cutting gates and canonical incumbents

| Layer | Required treatment and existing owner |
| --- | --- |
| Source, corpus and wire ingress | Use bounded SDL parsing/compilation and `raes_contracts/json_ingress.py` / `runtime_value_limits.py`, closed `ContractModel` / operation models and their contextual validators. Reject duplicate members, non-finite or coercive coordinates, oversized input and unsupported lineages before copying/hashing. Revalidate mutable nested in-process inputs. Resolve fixture/profile defaults through `raes_contracts.corpus`, with explicit confined override roots and profile-ID validation; never execute/fetch fixture content. `_load_json()` in conformance diagnostics is ordinary JSON loading, not the bounded trust-boundary parser. |
| Configuration and capability admission | `ControlPlaneConfiguration`, `registry_target_validation.py`, `MixedRuntimeBinding`, `MixedBackendInstallation`, manifest authority and backend `capability_admission.py` own shapes, service roles/signatures, exact component/profile/envelope/configuration joins and effective support. API-407 strength, SEM-218 realization, installed method shape, contextual willingness and executed evidence are separate checks; no manifest union. `OperationSupervisionConfiguration` owns strict finite budgets/capacities. Preserve the joint-path refusals above. |
| Control and authorization | Reuse `MixedControlRuntimeBinding`, compiler policy projection, `validate_participant_control_occurrence_context()` and `fold_participant_control_episode_v2()`, live-cut resolution and `participant_control_action_admission.py`. Preserve authenticated `ControlPlaneIdentity` / `ParticipantControlSubjectBinding`, exact target/run/participant/controller scope, grants and episode. `participant_crossing_boundary.py` and `participant_flow_sink.py` retain final-sink/disclosure authority. Service IDs and native owners confer no caller authority. If HTTP is exercised, retain strict security defaults, `_auth.py`, request-size/queue limits, idempotency, sealed route roles and supervisor/worker authorization. Fixtures must not bypass these using an unauthenticated identity. |
| Secrets and environment | Reuse `RuntimeEnvironmentVariable` and `enforce_observed_value_redaction`, `secret_references.py`, runtime-fact binding policy, planner `stateful_admission.py` and `prepared_node_projection.py`. Environment names are nonblank and exclude `=`; literal `value` and `value_from` are exclusive; generated values cannot claim `operator_secret`; redacted/operator-secret plaintext is forbidden. Generated delivery also passes exact mode/projection/node/output/consumer/sensitivity joins. These SDL shapes are separate from host credential injection, which remains with the backend owner. No new environment bag or secret loader. Never read the user's secret file. |
| Host, runtime and OS | No service reference resolves to an import, command, URL or filesystem path. Use injected services and `LocalExecutionAdapter` under `RuntimeMutationAuthority`, with separate bounded control/store/effect capacity; no second timeout/thread engine. No extension executes while holding a state permit or store transaction. Preserve served single-worker/profile checks, `control_plane_store_paths.py` / `control_plane_store_lease.py`, private database/sidecar permissions, ownership/link checks and leases. No tokens/payloads in argv, shell interpolation, broad inherited environment, logs or command digests. Native endpoint access, process isolation and resource cleanup remain distribution-owned; add no hosting, dependency or service discovery. |
| Backend results, persistence and recovery | Keep `backend_calls.py`, snapshot/changed-address/ownership validators, participant history validation and credential egress checks. `InvocationLedger`, `ControlPlaneOperationRecord`, `RuntimeDurabilityMixin`, store commit adapters and `operation_reconciliation*.py` own one-use grants, immutable commitments, atomic snapshot/history-head CAS/audit publication and recovery. Cover the selected memory/local/PostgreSQL codec without creating a conformance database. Lost acknowledgements require authoritative readback; uncertain effects retain quarantine/readiness failure. Local transactionality does not imply atomic external effects. |
| Errors and observability | Reuse `Diagnostic` / `Severity`, conformance `sanitized_failure_message()`, `backend_result_diagnostics.py`, `backend_account_credentials.py`, `AuditEvent` and existing loggers. Preserve existing validation/conflict exceptions, not a mixed-conformance hierarchy. HTTP `_responses.py` / operation routes retain redacted 4xx/5xx, disclosure-safe lookup and no-store. Sanitize addresses, evidence refs and causes as well as messages; bounded text and `portable_diagnostic_payload()` shape are not redaction. Never interpolate backend/Pydantic exception input, native payloads, tokens, private paths or credential-dependent hashes into reports. ADR-066 keeps operational telemetry, participant observation and experiment collection distinct. |
| Report output and resource ownership | Default to the incumbent sanitized report projection/stdout; durable output is caller-selected. `ProbeRuntimeOwner` demonstrates retaining temporary archive ownership until runtimes close. `RunMaterializationArchive` protects its specific materialization contract and is not a generic conformance report store. Do not restore removed evidence writers or invent retention/export demand. Backend-owned native runs retain their own protected artifact/cleanup boundary; evidence references are identities, not permission to fetch or upload. |
| Publication and workflow | `contracts/schemas/` is normative; use existing validators/schema bundle, fixtures and publication entries if a contract change is unavoidable, with ADR-061 compatibility and generated parity. Do not change a schema solely to fit a probe. Respect ADR-015/036 source caps/import boundaries and facade parity. Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml`, `tools/verification_plan.py`, `noxfile.py`, `.pre-commit-config.yaml` and canonical CI. This issue has no requirement UID: do not fabricate one or claim IMPLEMENTS for a prerequisite. No release-owned changelog/version edits or new workflow. |

The whole-repo consumer set has these members:

- the SDL/compiler and admitted trial context;
- the published contract/profile corpus and backend protocols/registry;
- mixed and control controllers, shared execution/supervision, stores and readers;
- API disclosure and the conformance facade/report/CLI;
- packaged corpus resolution, the host runtime and the backend-distribution evidence boundary.

Keep supported pure/single-target paths
and historical reference-only readers honest while extending the verifier.

## Verification scope, anti-patterns and non-goals

Build on `test_issue_1371_mixed_backend_contracts.py`,
`test_issue_1372_mixed_execution.py`, `test_issue_1372_review_regressions.py`,
`mixed_execution_fixtures.py`, the #1355 mapping/time witnesses,
`test_issue_1364_{reusable_runtime,cancellation,cancellation_evidence,review_regressions}.py`,
and the #1362 supervision/ledger/recovery/privacy tests. These already demonstrate
real runtime paths under test-owned services; they are reusable test patterns,
not a public backend realization harness. Extend the existing conformance CLI,
report honesty, facade parity and target tests where those boundaries change.
Assert prohibited call counts as well as states and distinct evidence, and
include changed/forged/duplicate/stale reports, reset clock segments, declared
loss mismatch, refusal races, responsive supervision and recovery. Full native,
integration, fuzz and repository-wide suites remain CI/backend-distribution
work; local feedback must select relevant modules/cases only.

Avoid these anti-patterns:

- golden metadata presented as execution, or a stub advertised as a concrete backend;
- common-interface equivalence, or joint support inferred from independent passes;
- bypassed configuration refusals or duplicate schemas/validation/outcome tables;
- a second report or persistence system, or runtime fallback;
- fabricated delivery/observation/cessation.

Distinct service pins do not prove independently
observed native truth. Optional observation and required delivery are not the
same release condition. Evidence retention is not experimental collection.

Non-goals:

- implementing missing runtime joins or backend capabilities;
- a concrete backend/federation framework, new SDL policy or support levels;
- distributed worker activation or generic retries/rollback/compensation;
- exactly-once external effects or universal liveness/equivalence/noninterference proof;
- physical timing certification or new external hosting/publication.

The implementation boundary is portable executable verification and truthful,
independently runnable evidence for supported selections, with explicit
unsupported reports for everything it cannot establish. This preflight changes
guidance only.
