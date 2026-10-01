# Issue 1185 API-404 Profile Alignment Preflight

Date: 2026-09-20

Issue: #1185. Requirement: API-404. Decision: ADR-104. Work package:
CP-11. Dependency: CP-10 (#1189), landed in `7128f0cc`.

## Decision

API-404 remains the normative requirement and remains `ACTIVE`, but its broad
inventory-era sentence must not be read as one universal deployment guarantee.
Its clauses and profile matrix must express three cumulative boundaries:

1. P0, P1, and P2 share the in-process contract: typed immutable actor context,
   authorization on mutation and disclosure, one target/run scope,
   actor-scoped idempotency, revision compare-and-swap, one mutation authority,
   validation, and atomic operational audit.
2. P1 and P2 additionally guarantee crash-consistent local state, retained
   idempotency, exclusive owner admission, and startup classification without
   automatic effect replay.
3. P2 additionally guarantees authenticated bounded HTTP admission,
   actor-bound disclosure, owner-serialized mutation, and revision-carrying
   reads over an explicitly selected P1 core.

P0's identity is supplied by the trusted embedder. That is an identity and
authorization duty, not a transport-authentication claim. Its state,
idempotency records, and audit are process-lifetime only; process loss has no
restart-recovery or retained-deduplication guarantee. P3 is an unavailable
future seam with no requirement satisfaction or implementation guarantee.

The requirement must describe obligations, not reproduce provider capability
flags. `raes_runtime.control_plane_profiles` remains the sole executable profile
catalog. ADR-104 and the FM3 model remain design authority; neither is
executable evidence by itself.

## Clause boundary and profile matrix

Use stable clause identifiers so traceability and documentation tests can name
the obligation without parsing prose. The exact prose may stay concise, but it
must preserve these semantic cuts:

| Clause | Obligation | P0 | P1 | P2 | P3 |
| --- | --- | --- | --- | --- | --- |
| common in-process contract | Typed actor provenance, authorization, scoped idempotency, target/run isolation, validation, revision CAS, single mutation authority, and atomic operational audit while the composition exists | required | required | required | not available |
| durable local contract | Crash-consistent authoritative state, retained claims, one owner lease, strict persisted carriers, startup reconciliation, and no automatic replay | explicit nonclaim | required | required through P1 | not available |
| served transport contract | Authenticated and bounded HTTP admission, actor-bound disclosure, single-worker ownership, and revision-bearing reads | no transport claim | no transport claim | required | not available |
| excluded stronger claims | No inferred high availability, multitenancy, multi-owner coordination, exactly-once backend effects, TLS/proxy deployment, or universal recovery proof | explicit where applicable | explicit where applicable | explicit where applicable | no guarantees; future ADR/model required |

The matrix must use the landed claim vocabulary where one exists:
`in-process-safety`, `actor-scoped-idempotency`, `target-run-isolation`,
`revision-cas`, `atomic-audit`, `durable-state`, `retained-idempotency`,
`lease-admission`, `startup-reconciliation`, `authenticated-transport`,
`actor-bound-disclosure`, `owner-serialized-mutation`, and
`revision-carrying-reads`. Do not mint requirement-local synonyms that appear
to be new runtime guarantees.

Authorization and validation remain FM3 invariants enforced by the existing
core even though they are not separate `ControlPlaneClaim` identifiers. Do not
drop them from API-404, and do not add duplicate catalog entries merely to make
the prose mechanically one-to-one.

ADR-104 section 4 and the FM3 `invoke`/write-ahead wording use "durable" while
describing the common operation cut. Do not copy that word into the common
clause without its profile qualification. For P0, `RUNNING`, the terminal
record, and audit are authoritative and atomic only within the live process;
only P1/P2 make them crash-persistent. ADR-104 section 2 and the FM3
"Concurrency and failure obligations" section already establish that
qualification, so this wording hazard does not require a new architectural
decision.

## Evidence and traceability authority

Only landed code and tests establish satisfaction. Keep design provenance as
`DOCUMENTS` links, but do not treat a GitHub issue, ADR, formal model,
implementation-program row, research replay, or preflight note as proof that a
profile guarantee runs.

| Requirement boundary | Canonical landed implementation | Canonical landed evidence |
| --- | --- | --- |
| Executable profile identity and availability | `implementations/python/packages/raes_runtime/control_plane_profiles.py`; `raes_runtime/__init__.py` | `test_issue_1189_control_plane_profile_declarations.py` |
| Common P0--P2 identity, authorization, idempotency, revision, isolation, and audit | `control_plane.py`; `control_plane_operation_context.py`; `control_plane_admission.py`; `control_plane_mutation.py`; `control_plane_store.py` | `test_issue_1187_control_plane_profiles.py`; `test_issue_1187_control_plane_lifecycle_properties.py`; `test_issue_1184_atomic_idempotency_claims.py` |
| P0 process-loss nonclaim | `control_plane_store_memory.py` | `test_issue_1187_control_plane_process_loss.py::test_p0_process_loss_loses_run_and_claim_even_when_external_effect_survives` |
| P1/P2 durability and recovery | `control_plane_store_local.py` and its codec, path, lease, record, snapshot, durability, and recovery siblings | `test_issue_1187_control_plane_process_loss.py`; `test_issue_1187_control_plane_durable_carriers.py`; `test_issue_1179_startup_reconciliation.py`; durable cases in `test_issue_1187_control_plane_profiles.py` |
| P2 transport authentication and disclosure | `control_plane_api/__init__.py`; `control_plane_api/_auth.py`; `control_plane_api_guards.py`; `control_plane_security.py` | `test_issue_1187_control_plane_security_conformance.py`; P2 cases in `test_issue_1187_control_plane_profiles.py`; `test_runtime_control_plane_api.py` |

Requirement trace records must keep the repository grammar parsed by
`RepositoryRequirementClient`: one exact `IMPLEMENTS`, `TESTS`, or `DOCUMENTS`
record per bullet with a recognized artifact type and backtick-delimited
identifier. Every local path cited by API-404 must exist at the reviewed commit.
The current repository-source governance check validates syntax, status, phase,
changed-Python coverage, and path ownership; it does not validate target
existence or prove a clause-to-test relationship. The CP-11 documentation check
must therefore pin those two facts directly.

The check needs an independent expected profile/clause matrix. It may read the
production declarations and the requirement document, but it must not compute
the expected answer from the same production mapping it is testing. It must
also pin P0's durability and restart-recovery nonclaims, P2-only authenticated
transport, P3's empty guarantee set and unavailable selection, and existence of
the requirement's local code/test evidence targets. Reuse
`profile_declaration()` and `RepositoryRequirementClient`; do not introduce a
second profile registry or a second traceability parser.

## Cross-cutting passage

CP-11 changes governance prose and its drift check, not runtime behavior. The
claims it publishes still pass through all of these incumbent layers:

| Layer | Required boundary |
| --- | --- |
| Typed composition | `ControlPlaneConfiguration`, `ControlPlaneOptions`, `ControlPlaneProfile`, `profile_declaration()`, and `PlanScope` remain the closed profile/run shapes. Omitted selection makes no named-profile claim. |
| Provider and persistence admission | `require_profile_capabilities()` checks layer-qualified facts; `adapt_control_plane_store()` independently checks callable/signature shape. P0 uses scope-bound memory state. P1/P2 retain lease-before-inspection, private-path, WAL, schema/migration, strict-codec, digest, integrity, and immutable target/run checks. |
| Identity and authorization | P0/P1 consume `ControlPlaneIdentity` from the trusted embedder. P2 alone passes `_ControlPlaneApiAuth`, bearer precedence or explicitly trusted proxy identity, exact target binding, role/subject authorization, and core admission. Possession of an operation id or idempotency key is never authority. |
| Request and process admission | P2 retains `RequestSizeLimitMiddleware`, bounded mutation/rejection-audit executors, and `require_single_worker_configuration()`. `WEB_CONCURRENCY` and `UVICORN_WORKERS` remain count-only gates, not secret or profile inputs. |
| Secrets and OS exposure | The requirement and test use stable identifiers and synthetic credentials only. They add no token, credential, store path, profile, or run scope to environment variables, process arguments, logs, diagnostics, audit details, or public carriers. TLS termination, proxy stripping, secret loading, filesystem ownership, supervision, and backup policy remain deployment duties. |
| Error envelopes | Keep existing `Diagnostic`/`DiagnosticModel`, denial receipts, stable FastAPI `HTTPException` responses, generic redacted 500 handling, and value-free capability errors. No provider exception text, type, path, SQL, raw request, token, or traceback may become requirement evidence or public output. |
| Audit and observability | `AuditEvent`, terminal atomic audit, bounded rejection audit, value-free health, and module loggers retain distinct roles. Logs and health do not satisfy the audit clause; append-only audit is not tamper evidence, participant observation, or archival run provenance. |
| Governance workflow | `docs/requirements/API-404/requirement.md` is canonical under `tools/policy/requirement_order.yaml`; `tools/policy/repository_requirements.py`, `tools/check_requirement_governance.py`, `.ground-control.yaml`, and `.gc/plan-rules.md` remain the workflow. Keep `RAES_REQUIREMENT_UID=API-404` for local policy checks because the branch has no requirement UID. |

No schema, DTO, controller, service, repository, codec, exception hierarchy,
logger, environment binding, CLI option, HTTP endpoint, or schema-publication
ledger entry is needed.

## Extension seam

Stable clause identifiers plus the profile-to-clause matrix are the
documentation seam. A new store provider satisfies the existing P1 clauses by
the existing protocols and provider facts; it does not add a requirement
profile. A new P2 authentication mechanism still resolves to
`ControlPlaneIdentity`. A future profile can add a matrix row without rewriting
the common clauses, but P3 cannot gain a required clause or guarantee until a
new ADR and formal model define coordination, fencing, partition behavior,
cache coherence, scheduling, and tenant isolation.

## Non-goals and anti-patterns

- No runtime, schema, store, HTTP, CLI, or deployment behavior change.
- No API-404 completion status invented. `ACTIVE` is the current governed
  status; the repository has no `COMPLETE` status.
- No guarantee inferred from a concrete store class, HTTP presence, successful
  lease, passing health probe, documentation statement, or test fixture name.
- No P0 transport-authentication, durability, restart-recovery, retained
  deduplication, or exactly-once-effect implication.
- No P1 transport-authentication claim; its actor boundary is the trusted
  embedder.
- No P2 TLS, proxy correctness, secret management, multi-worker, high
  availability, multitenancy, or exactly-once-effect claim.
- No P3 guarantee, placeholder satisfaction, selectable composition, or
  speculative capability list.
- No conflation of control-plane operating profiles with backend, SDL/domain,
  validation, realization, or conformance profiles.
- No duplicate profile table in JSON/YAML, published schema, Ground Control
  sidecar, test fixture, or documentation helper.
- No duplicate validation, store protocol, operation lifecycle, audit model,
  diagnostic family, exception hierarchy, or requirement parser.
- No trace link to a planned branch, unmerged test, future evidence bundle, or
  GitHub issue used as a substitute for implementation evidence.
- No ADR-104 amendment unless the implementation changes an architectural
  guarantee. The landed CP-10 amendment already defines this boundary.
