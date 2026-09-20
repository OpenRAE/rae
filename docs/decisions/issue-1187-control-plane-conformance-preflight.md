# Issue 1187 Control-Plane Conformance Preflight

Date: 2026-09-20

Issue #1187 (CP-9) is the delivery contract under requirement API-404.
[ADR-104](adrs/adr-104-runtime-control-plane-architecture.md) and its
[operation model](../../specs/formal/runtime-control-plane/README.md) remain
the architecture authority. This note constrains test design; it introduces
no runtime behavior, portable contract, or implementation plan.

## Decision and existing coverage

Use one parameterized conformance suite over the landed compositions, with
shared behavioral assertions and narrowly scoped provider/transport fixtures.
Keep specialized regression modules where they belong; one suite does not
require one large file or copied versions of their assertions.

| Composition | Required interpretation |
| --- | --- |
| P0: `RuntimeControlPlane` with `InMemoryControlPlaneStore` | In-process lifecycle, atomic publication, CAS, identity, isolation, validation, and no duplicate invocation. A fresh process loses the run, receipts, and claims; no restart durability or persistent deduplication claim. |
| P1: core with `LocalControlPlaneStore` | P0 safety plus lease-admitted, scope-pinned SQLite persistence, abrupt-process-loss recovery, and offline maintenance. |
| P2: `create_control_plane_app()` over a P1 core | Required P1 guarantees plus authenticated transport, bounded admission, coherent revision-bearing reads, and lifespan drain. HTTP over memory remains useful adapter coverage but is not P2 durability evidence; the CP-8 obligations must also pass. |

These are required profile contracts, not a declaration that this checkout
already conforms. CP-9 depends on CP-2, CP-3, CP-6, CP-7, and CP-8. Inspection
on the date above found concrete gaps against the
[CP-8 preflight](issue-1188-served-control-plane-profile-preflight.md):
`ControlPlaneSecurityConfig` accepts identity headers aliased to Authorization
or to each other, and empty bearer/principal entries;
`backend_result_diagnostics._backend_call_failed()` includes the provider
exception class name. The provisioning planner-denial route also awaits
`record_audit()` directly before choosing its 403, unlike the best-effort
shared rejection handler. Preserve adversarial expectations for these cases;
resolve product defects in their owning scope before claiming full P2
conformance. A skip or expected failure documents a gap, not a profile pass.

The CP-9 delivery addresses these three findings in the existing configuration,
backend-diagnostic, and shared HTTP denial-audit owners. Regression evidence is
`test_issue_1187_control_plane_security_conformance.py`: ambiguous/empty
configuration fails composition, provider type/message/chain material stays out
of durable status and HTTP output, and audit failure preserves the intended 403
for all three planner submission routes.

Review also identified exception-class disclosure in observation-adapter
failures. The existing required-observation failure regression now verifies
redaction in status, stored records, audit, and logs; `observation_execution.py`
keeps the same stable diagnostic code without the exception class. Fresh
source-bound formal and specification-coverage captures preserve their previous
outcomes and limitations, leaving the historical captures byte-exact. Those
corpora do not substitute for this suite's crash/profile evidence.

Operating profiles are not `BackendCapabilityProfile`, domain/realization
profiles, validation profiles, or scenario `deployment_tenants`.
`raes_conformance`'s backend corpus and `full-remote-control-plane` profile do
not declare P0--P2 ownership or durability. Do not extend that published schema
or its CLI merely to select this suite. The memory adapter's
`crash_atomic=True` denotes its atomic mutation capability, not process-loss
persistence. Do not infer an operating profile from that flag.

The deferred work is already represented by
`implementations/python/tests/test_issue_1092_control_plane_crash_consistency.py`.
Reuse its codec, rollback, filesystem, lease, migration, and cache regressions;
do not retrieve or re-land PR #1136 as a second implementation. Its
`KeyboardInterrupt` cases exercise exception rollback and orderly reopen,
not abrupt death. ADR-104 and current code supersede the old #1092 preflight's
blanket interrupted-to-failed recovery and optional non-atomic store fallback.

Other incumbent test owners, all under `implementations/python/tests/`:

| Concern | Existing owner |
| --- | --- |
| Closed lifecycle, context, public DTO/schema parity | `test_issue_1182_operation_lifecycle_contract.py` |
| Mutation families, terminal/audit atomicity, cancellation settlement | `test_issue_1181_unified_control_plane_mutations.py` |
| Observation, three recovery classifications, quarantine, linked resolution | `test_issue_1179_startup_reconciliation.py` |
| Revision CAS and coherent response cuts | `test_issue_1180_snapshot_revision_cas.py` |
| Lease admission, immutable scope, provider-close ordering | `test_issue_1183_store_ownership_leases.py` |
| Atomic actor/kind-scoped claims, commitments, authoritative reads | `test_issue_1184_atomic_idempotency_claims.py` |
| Transport/authentication and bounded rejection work | `test_runtime_control_plane_api.py`, `test_issue_1093_request_rejection_offload.py` |
| Health, backup/restore, strict audit, redacted failures | `test_issue_1186_control_plane_recovery_operations.py` |

Extract shared test fixtures only when needed by multiple cases; follow the
existing `*_fixtures.py` pattern and `create_stub_target()` composition.
Avoid importing whole test modules as a fixture API or copying their private
helpers. Positive cases must pass actual admission, not monkeypatch it away.

## Fault evidence and behavioral oracles

Kill-point coverage must distinguish exception injection from uncatchable
child-process termination. For durable profiles, cover both sides of claim
publication/start, backend invocation/effect, and terminal commit: before the
transaction, after each snapshot/record/audit write, after database commit,
and before cache publication/response. Include claim-transaction partial
writes. A lost response after commit must retain the original receipt and one
terminal audit. A kill before a committed claim leaves no operation; after a
committed claim it leaves recoverable work or the complete terminal cut.

Reuse the existing multiprocessing `spawn`, events/barriers, temporary stores,
and bounded joins. The child must acknowledge the exact fault boundary and
remain blocked there until termination; sleeps and a generic nonzero exit are
not evidence it was reached.
Reopen in a fresh owner/process without orderly shutdown of the killed owner.
Always reap children and bound waits, including failed assertions; never kill
a process by a broad name match. Isolate paths per test and worker. Platform
limitations must be explicit skips, never reported as demonstrated guarantees.
Process-kill evidence is not power-loss or arbitrary-filesystem proof.
Construct stores, targets, and application lifespans inside spawned children;
pass inert fixture parameters, not open connections, leases, or runtime objects.
Private transaction hooks may locate a fault, but must delegate to the real
provider writes and commit. A hook that performs the transaction itself tests
a replacement implementation. Release inspection leases before restarting the
core, and repeat kills during recovery terminalization to check that each
observed recovery cut is atomic and has no duplicate terminal audit.
Concurrent runtime submissions share one admitted owner; a competing process
must lose lease admission. Bypassing that lease to race SQLite writers would
exercise an unsupported runtime topology, not P1/P2 conformance.

Observe backend effects and invocation counts independently of the control
plane snapshot and dead child's memory. A test-owned durable effect witness
or independently supervised fake backend may supply that evidence; it must
survive the killed owner and distinguish dispatch, applied effect, and unknown
outcome. It is a test oracle, not a production ledger or recovery mechanism.
Check the pre-reconciliation durable cut through admitted store access, then
the core's post-startup cut: startup itself legitimately adds terminal state.
Never assert only the returned exception, HTTP status, or an in-memory counter.

Recovery fixtures implement `RecoveryObserver.observe_effect()` with matching
manifest `RecoveryObservationCapabilities` and the existing request/result
carriers. Exercise absent, applied, and indeterminate outcomes, unsupported
kinds, exceptions/timeouts, mismatched operation/commitment, and invalid applied
snapshots. Validate applied results through `_validated_backend_result()`.
Count invocations across startup, same-key retries, timeout, disconnect,
cancellation, and repeated reopen: none authorizes replay. Distinguish known
write-ahead `ACCEPTED` from unattributed migrated claims. Indeterminacy
quarantines new effects; authorized resolution creates a fresh linked child
and preserves the parent's terminal record, claim, actor, and audit.
An observer raising `TimeoutError` establishes failure classification, not an
enforced observation deadline: `observe_effect()` is synchronous. Bound the
test supervisor's wait without claiming a runtime timeout guarantee. Likewise,
using a fresh idempotency key after losing sensitive retry proof is a new
submission, not evidence that repeating an external effect is safe.

Use the FM3 matrix and CP-1's independently enumerated legal pairs as the
oracle for bounded Hypothesis transition sequences and malformed-carrier
mutations. Do not compute expected results with the production transition
predicate being tested. Illegal transitions must preserve the entire state
cut; terminal exact persistence retries are no-ops, not self-transitions.
Admission denial creates audit only, not a stored `REJECTED`/`FAILED` record.
Mutation checks must show that invalid transitions or omitted invariant
enforcement are detected; changing inputs without checking rejection and
unchanged state is insufficient. No general mutation-testing platform is needed.

Exercise every mutation family through its existing entry point, including
workflow cancellation/timeouts, precomputed results, participant control and
actions, episodes, read-shaped crossing mutations, and resolution. Parameterize
the shared assertions by `OperationKind` and an entry-point fixture; explicitly
account for families with no backend effect instead of manufacturing an invoke.
Retain snapshot-bearing versus record-only `TerminalCommitMode` behavior and
participant expected-head checks alongside snapshot CAS.

## Cross-cutting gates to preserve

Names below refer to the existing Python packages under
`implementations/python/packages/`; test adapters delegate to these owners.

| Layer and canonical incumbent | Required passage and adversarial evidence |
| --- | --- |
| Composition: `ControlPlaneConfiguration`, `PlanScope`, `runtime_target_scope()`, `RuntimeTarget`, registry `_validate_runtime_target_shape()` | Explicit target/run, valid component signatures and manifest capabilities, crossing/information-state resolvers where required. Reject mismatched scope before reads/migration. Never derive trusted scope from a receipt, filename, request, or database contents. |
| HTTP pre-parser/config: `ControlPlaneSecurityConfig.strict_defaults()`, `RequestSizeLimitMiddleware`, closed request DTOs | Exercise unknown/malformed members, invalid/duplicate lengths, streaming size limits, positive queue bounds, and overload. Bounded `RejectionAuditExecutor` must not dispatch rejected work or replace its error when auditing fails. |
| Authentication/authorization: `_ControlPlaneApiAuth`, `ControlPlaneIdentity`, core operation/participant authorization | P0/P1 trust embedder authentication; P2 derives context from authenticated transport. Default-deny spoofed proxy headers; invalid bearer cannot fall through to proxy identity. Match target, role, actor and complete subject/audience scope before claim or disclosure. Equal keys for different actors/kinds are distinct claims; guessed ids, changed scopes, and caller fingerprints grant no authority. Test direct core calls as well as HTTP. Trusted-proxy stripping/TLS remain host deployment obligations, not proved by an ASGI test. |
| Plan/backend semantics: `control_plane_plan_diagnostics()`, `RuntimePlanAuthorizationMixin`, backend input/result and snapshot-transition validators | Use admitted planner outputs and real realization, account-credential, participant control/crossing, information-state and final-sink gates. Valid JSON or a successful observer response cannot bypass semantic validation. Reuse participant and realization fixtures instead of inventing permissive fake DTOs. |
| Secrets/environment: `operation_admission_context()`, value-free account projection, ephemeral exact retry proof, `backend_account_credentials.py`, `raes/runtime_environment.py` | Use synthetic sentinels only. Persist value-free commitments, not secret hashes or exact fingerprints; credential-bearing retries after restart fail closed when ephemeral proof is lost. Scenario environment fixtures must obey name, classification/provenance, literal-versus-`value_from`, and redacted/operator-secret constraints. Service security config stays explicit in memory, separate from SDL environment bindings. |
| Mutation/ownership: `RuntimeMutationAuthority`, `RuntimeLifecycleMixin`, `RuntimeOwnerLease`, `_ControlPlaneCallExecutor` | One owner, no transaction across backend calls, second-process/fork rejection, bounded queued work, cancellation settlement, responsive pure reads, drain before provider close before lease release. Provider-close failure retains authority. `WEB_CONCURRENCY`/`UVICORN_WORKERS` rejection is additional to the lease, not a substitute. |
| Persistence/coherence: `ControlPlaneStoreCommitAdapter`, atomic stores, `SnapshotState`, `SnapshotRevisionConflict`, `RuntimeDurabilityMixin` | Competing claims/CAS have at most one winner; snapshot, terminal record and actor audit publish together. Test stale caches, commit-then-error, authoritative readback and poisoning on failed readback. Response value and revision must describe the same cut. Never equate snapshot revision with history head, digest, timestamp or SQLite transaction id. |
| Durable/transport carriers: `OperationReceiptModel`, `OperationStatusModel`, `RuntimeSnapshotEnvelopeModel`, `decode_payload()`, `_OperationRecordModel`, `_AuditEventModel`, exhaustive snapshot codec, shared transition/scope/audit-binding validators | Check hash corruption separately from well-hashed but semantically malformed state; missing/unknown/coerced fields, receipt/status or indexed-key mismatch, invalid scope/history, and snapshot-field drift fail closed. Preserve deliberate value-free projection on round-trip. Use existing schema migrations for old formats; no silent defaulting, sanitizing or dropping history. |
| Filesystem/OS/maintenance: `control_plane_store_paths.py`, lease admission, `maintain_local_control_plane_store()` | Retain private modes, owner/type/link/reparse checks, pinned directory/database identities, WAL/full-sync admission, `quick_check`, file-before-directory fsync and restore rollback. No application raw-open/close/chmod of live SQLite-managed files or sidecars: it can break SQLite locks. Corruption fixtures use isolated offline/admitted provider access. Restore is lease-exclusive and repeats normal admission/recovery; a database backup does not restore external effects. |
| Errors/observability: `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload()`, `AuditEvent`, `_conflict_detail()`, shared request handlers and module loggers | Assert coarse HTTP/CLI envelopes and stable namespaced diagnostics, not provider wording. Inject sentinel secrets, paths, SQL and exception chains; inspect response, durable audit/status and captured logs/output. Secondary audit failure preserves the primary envelope. Append-only audit differs from telemetry, participant history and experiment evidence; hashes are corruption checks, not authenticity. Public health stays value-free and audit-free. |

Fault selectors, test identity, store paths and clocks belong in test factories,
not production environment switches, request headers or new service settings.
Never put credentials in subprocess argv, environment dumps, failure reports or
captured artifacts. Use operational monotonic/wall time for synchronization and
timeouts; `TimeRuntime` and scenario time are unrelated. Exercise P2 with the
real lifespan and authenticated adapter, without adding a serve command or
external network dependency.
Control inherited worker settings explicitly with pytest's existing
`monkeypatch` fixtures, restoring them after each case; exercise invalid values
in rejection cases. Synthetic bearer config belongs inside the child/test
factory, never in developer credential files or a new environment loader.

## Extension and workflow boundaries

The extension seam is a small test-owned factory parameterized by reference
composition, store location/scope, actor, operation entry point, recovery
observer, and fault boundary. A new admitted provider supplies factory and
provider-specific fault hooks, reusing the invariant assertions. Keep its
declared guarantees/nonclaims explicit and fail collection/coverage checks
when an implemented profile or required family is omitted. Unavailable
optional/platform cases remain visibly unexecuted; skips cannot produce a
blanket conformance pass. Do not add a runtime profile registry, plugin system,
parallel schema, exception hierarchy, auth resolver, workflow engine, or generic
fault-injection API for tests.
Keep this test matrix separate from CP-10's production profile declaration and
discovery work; consume that declaration when available rather than publishing
a competing catalog. Pytest case ids/results should identify composition,
operation family, fault boundary, and outcome using bounded synthetic labels.

Reuse pytest/Hypothesis from `implementations/python/pyproject.toml`, the
`noxfile.py` registry, `tools/nox_support/{config,test_lanes,graph}.py`,
`tools/verification_plan.py`, `.github/workflows/ci.yml`, and its reusable
`.github/workflows/canonical-verification.yml`. Default pytest
excludes `integration`, `fuzz`, and `docker`: process/whole-system cases belong in the
existing integration lane and property cases in the fuzz lane. A default or
changed-test-only pass is not complete CP-9 evidence. Keep deterministic,
bounded cases in the appropriate existing lanes rather than a parallel runner.
Use the existing shard manifest/reduction tooling
(`tools/pytest_shard.py`, `tools/pytest_shard_plugin.py`) for collection
completeness. The canonical unit/integration graph does not include fuzz;
record that lane separately. Avoid dual `integration`/`fuzz` marking that would
silently run expensive subprocess cases in both lanes. Native OS lock evidence
must name the platform exercised; a monkeypatched Windows path on POSIX is
branch coverage only. Hermetic CP-9 evidence needs no real backend or Docker.

`.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml`,
`tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, and
`tools/verify_all.py` remain the policy/verification owners. Set
`RAES_REQUIREMENT_UID=API-404` on branches without the UID. The selected
requirement authority is repository-backed in
`tools/policy/requirement_order.yaml`; use its existing resolver and governance
gate, without changing the authority or bypassing traceability. No published
schema changes are needed; if a discovered defect requires one, use the existing schema-publication
manifest/ledger, `schema_bundle()` parity, and contract fixtures. A failing
invariant is a product finding, not permission to weaken the expected result
or silently broaden this test issue into redesign.

Results are finite observations for named profile, operation, fault point and
platform. P0 process loss is explicitly outside durability; P1/P2 do not imply
P3, multiple service owners, tenant multiplexing, distributed fencing,
exactly-once effects, tamper evidence, or universal recovery proof.
`RuntimeManager`, backend effect semantics, SDL/planner behavior, deployment
TLS/secrets/supervision, new providers and production recovery workflows are
outside CP-9 implementation boundaries. This preflight changes guidance only.
