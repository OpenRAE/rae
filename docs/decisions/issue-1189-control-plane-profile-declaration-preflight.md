# Issue 1189 Control-Plane Profile Declaration Preflight

Date: 2026-09-20

Issue: #1189. Requirement trace: API-404. Decision: ADR-104. Work package:
CP-10.

## Decision

The canonical owner is one immutable typed catalog in `raes_runtime`. Each
entry owns the profile id and label, stable guarantee and nonclaim identifiers,
one-target/one-run scope, actor boundary, required composition capabilities,
and whether selection is available. The public runtime surface returns those
same declaration objects; stores, the HTTP adapter, tests, and documentation do
not maintain profile-name or guarantee tables of their own.

This declaration is runtime composition metadata. It is not a
`raes_contracts` model, a published JSON Schema, a store record, a backend
profile, a domain profile, or an HTTP payload. The historical profile rows in
the #1151 design program remain design evidence and are not loaded as a second
runtime registry.

Omitted selection is a compatibility state with no named-profile claim. It is
not inferred as P0 from an in-memory store or as P2 from HTTP use, and it must
not be returned by discovery as though validation had occurred. New consumers
that rely on a profile guarantee select it explicitly; migrating every existing
constructor call site to a named profile is not part of CP-10.

Profile selection occurs at the boundary that can establish the claim:

- P0 and P1 are selected and validated by the core library composition.
- P2 is selected by `create_control_plane_app()` over a core that has already
  satisfied P1. The core alone does not claim P2, and the adapter cannot turn a
  P0 core into P2.
- P3 has a catalog entry so callers can inspect its nonclaim, but selection
  fails before provider admission or other side effects. It has no guarantees
  or speculative distributed requirements.

Selection is never inferred from a store class, method presence, path, HTTP
use, or a successful lease. Construction compares the selected profile with
declared provider facts and fails on every missing requirement. It never
downgrades. Extra provider capabilities do not strengthen the selected
profile's guarantees.

## Canonical profile matrix

| Profile | Scope and actor boundary | Persistence, lease, revision, and audit | Recovery observation | Guarantees and nonclaims |
| --- | --- | --- | --- | --- |
| P0 ephemeral | One target and one run per store. A trusted embedder supplies the existing typed immutable actor context. | Process-lifetime state; no owner lease. Logical revision CAS, atomic claims/terminal commits, and append-only operational audit remain required while the process lives. | Not applicable after process loss; there is no restart recovery claim. | Guarantees the in-process safety, validation, authorization, idempotency, isolation, revision, and atomic-audit contract. Does not claim durability, restart recovery, multi-process ownership, high availability, or multitenancy. |
| P1 local durable | One target and one run per store. A trusted embedder supplies the same actor context. | Crash-consistent transactional state, one process-bound exclusive owner lease, logical revision CAS, atomic terminal audit, strict codecs, and immutable persisted scope are required. | Startup reconciliation is required. Backend recovery observation is optional and is read only from the target manifest; unsupported or unobservable effects become `INDETERMINATE`. | Adds durable claims, retained idempotency, lease admission, and no-replay startup classification. Does not claim multi-owner operation, high availability, exactly-once backend effects, or multitenancy. |
| P2 served | P1's one target and one run per store. The reference HTTP authentication boundary derives the immutable actor context before core admission. | Exactly P1's store requirements plus single-worker HTTP ownership and bounded transport admission. | Exactly P1's rule; HTTP does not create or strengthen backend observation. | Adds authenticated transport, actor-bound disclosure, owner-serialized mutation, and revision-carrying reads. Does not claim multi-worker ownership, TLS/proxy deployment, high availability, exactly-once effects, or multitenancy. |
| P3 coordinated | Unavailable. No target/run or actor model is declared yet. | No guarantees or required capability set is declared. | Future decision only. | Reports only that coordination, fencing, distributed scheduling, cache coherence, and tenant isolation require a future ADR and formal model. |

Use closed machine identifiers for the catalog fields and keep their human text
beside them in the same immutable declaration. Do not model the matrix as a set
of loosely related booleans or mutable dictionaries. P0's in-memory audit and
P1/P2's durable audit share the same audit semantics but have different
persistence claims; the declaration must preserve that distinction.

## Provider facts and admission

The profile catalog states requirements. Each composition contributor states
only the facts it owns:

- a store declares atomic claim/terminal commit, logical revision CAS,
  operational audit, immutable scope, persistence, and lease facts;
- the core supplies the one mutation authority, actor-bound operation context,
  strict validation, and startup reconciliation behavior;
- the target's existing manifest and optional recovery observer remain the
  sole recovery-observation declaration and implementation pair;
- the HTTP adapter supplies bounded authenticated transport, the existing
  security policy, single-worker admission, and revision-bearing response
  projection.

Capability identifiers must encode their owning layer so unrelated providers
cannot satisfy each other's requirements by unioning generic flags. Provider
claims are static composition facts, not dynamic readiness. Lease loss,
durability poisoning, draining, and unresolved recovery remain in
`control_plane_readiness()` and do not mutate the selected profile.

Provider facts are internal admission inputs, not a second public catalog. The
HTTP adapter composes from an already validated P1 declaration plus its own
HTTP facts; it must not reach through the core to a private store-capability
set or re-inspect the store. Likewise, a store may expose a general scope or
runtime-admission operation, but it must not gain a profile-named method: stores
provide facts and enforcement, while the composition selects profiles.

Custom stores use the same provider declaration shape as built-ins. Their
declaration is an attestation, not proof: `adapt_control_plane_store()` still
owns callable/signature validation, the store protocols still own the call
shape, runtime admission still exercises the lease and scope checks, and the
existing conformance suite supplies behavioral evidence. Do not duplicate
`_BASE_STORE_METHODS`, `_ATOMIC_STORE_METHODS`, or their signature inspection
inside profile validation.

Admission preserves the incumbent validation order. Typed profile and run-scope
shape, catalog availability, and the static capability match run before provider
effects. Store protocol/signature validation then remains mandatory; P0 binds
its in-memory scope, while P1 acquires and verifies its lease before local path,
schema, migration, integrity, state-load, or recovery work. P2 additionally
requires an explicitly selected P1 core, then passes the existing worker-count,
security-config, request-bound, and executor construction gates before an app
can be exposed. A failure after resource acquisition follows the existing
provider-before-lease close order. A capability declaration must never short
circuit any of these authorities.

The static capability match itself runs before lease acquisition, filesystem
creation or inspection, store reads, recovery, route registration, and backend
calls. A mismatch reports sorted stable capability identifiers only. It does
not include the provider representation, path, SQL, exception chain, target/run
values, or security configuration.

## Cross-cutting incumbents

| Concern | Canonical incumbent to reuse |
| --- | --- |
| Runtime options and normalized run scope | `ControlPlaneOptions` and `ControlPlaneConfiguration`; reject unknown options and keep `PlanScope` validation. |
| Store call shape and atomic mutation | `ControlPlaneStore`, `AtomicControlPlaneStore`, `RuntimeAdmittedControlPlaneStore`, and `adapt_control_plane_store()`. |
| P0/P1 provider behavior | `InMemoryControlPlaneStore`, `LocalControlPlaneStore`, `SnapshotState`, revision CAS, atomic claims/terminal commits, strict codecs, and immutable store scope. |
| Ownership and host posture | `RuntimeOwnerLease`, `require_single_worker_configuration()`, and the current runtime lifecycle close/drain order. |
| Recovery observation | `BackendManifest.recovery_observation`, `RecoveryObservationCapabilities`, registry target-shape/signature validation, and `control_plane_recovery`. |
| Actor and authorization boundary | `ControlPlaneIdentity`, `OperationAdmissionContext`, `operation_actor_scope()`, `operation_admission_context()`, participant subject bindings, and current core authorization checks. |
| HTTP security and admission | `ControlPlaneSecurityConfig.strict_defaults()`, `_ControlPlaneApiAuth`, `RequestSizeLimitMiddleware`, and `_ControlPlaneCallExecutor`. |
| Audit and observability | `AuditEvent`, `terminal_operation_audit()`, `require_audit_event_fields()`, stable `Diagnostic` codes, value-free health, and module loggers. |
| Failure mapping | Existing `TypeError`/`ValueError` composition failures and shared redacted HTTP response handlers; no new public exception hierarchy or provider error envelope. |
| Offline maintenance | `maintain_local_control_plane_store()`, `LocalControlPlaneStore.admit_maintenance()`, and `raes_cli.runtime`; these validate the same scope, path, lease, codec, and migration authorities without pretending to be a live P1 composition. |
| Direct execution | `RuntimeManager`, `RuntimeManager.apply()`, and direct backend calls remain outside the profiled control plane and gain no profile guarantees. |
| Documentation and evidence | ADR-104, the FM3 model, `runtime-architecture.md`, `control-plane-operations.md`, and the CP-9 conformance matrix. |
| Repository workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`, and `tools/verify_all.py`; keep API-404 IMPLEMENTS/TESTS traceability aligned without creating a schema-publication change. |

The other repository profile systems are different concepts. Do not reuse or
extend backend conformance profiles, SDL/domain profiles, validation profiles,
realization profiles, or `raes_runtime.backend_profiles` for control-plane
operating profiles.

## Security and whole-repo passage

| Layer | Required passage |
| --- | --- |
| Typed configuration | Profile selection enters through the existing trusted composition shape. Only closed profile ids are accepted; P3 and unknown values fail before initialization. Target and run continue through `runtime_target_scope()` and `PlanScope`. |
| Store shape and semantics | The provider declaration is the early static match; `adapt_control_plane_store()` still validates callable shape before scope/admission effects. Local admission still validates lease, immutable scope, codecs, schema, SQLite mode, integrity, and filesystem identity. |
| Target capability shape | `RuntimeTarget` construction keeps exact manifest/component presence and method-signature checks. Recovery observation is never guessed from a callback or store capability. |
| HTTP authentication and authorization | P2 still uses strict security defaults, bearer precedence, explicit proxy trust, typed identities, target binding, participant/operation authorization, bounded request admission, and one worker. Profile interrogation grants no authority. |
| Secret handling | Profile and capability data contain only stable identifiers. Tokens, credentials, headers, raw requests, paths, backend exceptions, and exact retry proofs remain outside the declaration. Existing value-free commitments and credential sanitizers are unchanged. |
| Environment and process exposure | CP-10 adds no profile, token, or store-path environment variable or command-line option. `WEB_CONCURRENCY` and `UVICORN_WORKERS` remain count-only single-worker gates. TLS, proxy stripping, service-account credentials, and secret loading remain deployment inputs. |
| Error envelopes and logs | Composition failures happen before an app is available. If an unexpected provider failure later crosses HTTP, existing coarse redacted handlers apply. Capability mismatch text and logs use stable identifiers without provider values, tracebacks, or paths. |
| Health and audit | Introspection is side-effect free: it emits no audit event and is not a liveness/readiness result. Existing health and operational audit carriers retain their separate meanings. |
| Lifecycle cleanup | A rejected profile performs no provider work. A later constructor failure uses the incumbent drain/provider-close/lease-release ordering and must not leave an admitted owner or partially exposed app. |

No new transport parser, environment binding, secret loader, store codec, JSON
Schema, schema-publication ledger entry, audit sink, diagnostic family, or
logging path is needed.

## Drift and verification guardrails

One independent acceptance matrix should pin the expected P0--P3 ids and every
field above. Other tests consume the production catalog rather than restating
it, while still proving these boundaries:

- P0 with the in-memory provider and P1 with the local provider satisfy their
  exact required capability sets;
- selecting P1 with an ephemeral or capability-deficient provider fails before
  any provider method or filesystem effect;
- P2 accepts only the reference HTTP composition over a validated P1 core and
  rejects P0, missing authenticated admission, or multi-worker posture;
- removing each required provider capability fails construction; no case
  returns a weaker declaration;
- P1/P2 without a recovery observer still construct and classify an unknown
  interrupted effect as `INDETERMINATE`;
- P3 inspection returns only its unavailable nonclaim, and every selection path
  rejects it before touching providers;
- omitted selection remains a legacy unclaimed composition and is never
  inferred from a store class, HTTP adapter, or successful admission;
- core interrogation, store capability matching, and HTTP composition return or
  compare the canonical typed declaration rather than copied strings;
- offline maintenance and direct `RuntimeManager` paths neither require nor
  report a control-plane operating profile;
- structural documentation tests compare the explain table's stable profile,
  guarantee, and nonclaim identifiers with the canonical catalog.

The existing CP-9 tests remain the behavioral evidence for the declared
guarantees. Capability matrix tests do not replace crash, concurrency,
authorization, redaction, recovery, or process-loss evidence, and should not
derive their expected result from the same production mapping they test.

## Extension seam

The next persistence provider implements the existing store protocols and
supplies the same immutable provider-fact declaration. If its facts satisfy P1,
no profile entry, HTTP policy, or documentation vocabulary changes. The next
HTTP authentication mechanism resolves to the existing `ControlPlaneIdentity`
and does not alter P2. If a future composition layer contributes a genuinely
new fact, it owns a new layer-prefixed capability family; generic flags are not
unioned across store, core, target, and transport boundaries.

P3 is intentionally a different change. It needs a future ADR and formal model
for fencing, coordination, partitions, cache coherence, scheduling, and tenant
isolation before its declaration can gain requirements or guarantees. Do not
reserve speculative flags now.

## Non-goals and anti-patterns

- No profile inference from concrete classes, `hasattr()`, store paths,
  successful operations, HTTP presence, or environment variables.
- No implicit P0/P1/P2 claim for omitted selection and no bulk migration of
  legacy constructors under this issue.
- No negotiation, best-effort mode, automatic downgrade, or automatic upgrade
  to the strongest provider capability set.
- No store-owned profile id, HTTP-owned guarantee table, documentation JSON
  catalog, or second runtime mapping loaded from the #1151 design artifact.
- No profile-named store method and no HTTP access to private core/store
  capability state; compose from validated declarations at each boundary.
- No P2 claim on a bare core or in-memory store, and no P3 placeholder that can
  pass selection.
- No conflation of static capability, dynamic readiness, conformance evidence,
  or deployment topology.
- No requirement that every backend support recovery observation; explicit
  indeterminacy is part of the P1/P2 guarantee.
- No new public exception hierarchy, discovery endpoint, OpenAPI profile DTO,
  persisted profile record, schema, migration, audit event, or health field.
- No profile requirement or claim on offline check/backup/restore tooling,
  `RuntimeManager`, or direct backend execution.
- No change to operation, receipt, status, snapshot, actor, authorization,
  idempotency, revision, audit, recovery, or store-scope semantics.
- No TLS endpoint, proxy implementation, secret loader, process supervisor,
  backup policy, multitenancy, multi-worker ownership, high availability, or
  exactly-once backend-effect claim.
- No API-404 statement rewrite; CP-11 owns requirement reconciliation after the
  executable profile surface lands.
