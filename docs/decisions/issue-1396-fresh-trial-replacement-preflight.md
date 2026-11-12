# Issue #1396 — Failed or invalid trial replacement preflight

Architecture guidance for the supplied issue; prerequisite #1361 is represented
in the current tree. No formal requirement UID, implementation plan, new wire
contract, or claim of executable replacement support is introduced here.

Retain [ADR-068](adrs/adr-068-experiment-trials-replication-and-replay-claims.md),
[ADR-084](adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md),
[ADR-113 §§4,9](adrs/adr-113-reusable-execution-machinery.md), the adopted
[authored retry design](../research/execution-architecture/authored-retry-policy.md),
and [supervision S6](../../specs/formal/runtime-control-plane/supervision.md#s6--author-directed-subsequent-work).
These settle the ownership boundaries; another ADR is unnecessary.

## Decisions and current contract gaps

**Replacement belongs to experiment allocation.** Extend the existing
`ExperimentRunPlanModel` authoring boundary with an optional, closed, bounded
replacement choice that works for both `target_run_count` and structured
allocation. Omission permits zero replacements. `replication_policy` and
`stopping_rule` remain descriptive text; never parse them into executable
permission. Do not require an otherwise ordinary experiment to author an SDL
operation policy merely to replace a failed trial.

#1361 already supplies `ExecutionPolicy.response = new-trial`,
`on_exhausted = new-trial`, `fresh_trial_limit`, selected failure classes and
validity consequences. These request subsequent work; they do not own the
experiment's allocation budget. Reuse those meanings and scoped resolution.
`execution_policy_capability_gaps()` currently returns
`trial-allocation-authority-required` unconditionally for these choices.
Backend capability declarations alone cannot discharge that rejection. Any
supported path must bind the exact experiment authorization and remaining
budget through planning and admission, including `operation_policy_admission`;
unsupported or unbound paths must continue to refuse. Do not remove the guard
globally or add a caller-controlled `allow_new_trial` boolean.

**Bound a lineage, not each failed descendant afresh.** Define the authored limit
as additional admitted trials for one original allocation slot, excluding the
original. Every descendant consumes that same finite budget, including a
replacement that also fails; applicable scoped `fresh_trial_limit` values may
further restrict it, never multiply or replenish it. Bound aggregate allocation
work/bytes with the incumbent compilation limits before expansion. Exhaustion
retains the shortfall and its reason; it cannot silently increase the target,
reset a counter, weaken validity, or claim study completion. Distinguish denied
admission, committed allocation, execution failure and cleanup refusal. Budget
consumption is tied to unique admitted allocation, not successful execution or
transport delivery; rejected candidate work must also remain bounded.

**Keep every sealed plan immutable.** A replacement has a separately admitted
coordinate, entry and archival `run_id`, with linked parent/original allocation
and policy provenance. Preserve old plan bytes, identities, receipts and run
versions. Use the existing compiler/admitted-plan seam for new work, with
governed linkage on the owning contracts; the scheduler only consumes admitted
entries. Do not append entries to a sealed plan, recompile all old entries under
a new plan identity, relabel an attempt, or introduce `experiment-trial-v1`.

Current coordinate/identity/compiler profiles have exact output-affecting
algorithms and fixed conformance vectors. They do not express conditional
replacement lineage. A changed identity/coordinate algorithm needs a new profile
and vectors, not changed semantics under a v1 name. Reuse `TrialCoordinateModel`,
`trial_coordinate_order`, compiler `profiles.py`, JCS sealing and the acyclic
digest chain. Bind lineage without a parent/child digest cycle. Preserve
unaffected entries and streams. Initialization, factor/condition/block
assignment, selection and randomness must be explicit admitted facts: a new
trial is neither an implicit resample nor a promise of identical stochastic
values. Do not insert worker order, wall time, operation retry counts or engine
delivery ids into semantic random-stream addresses. Reuse the existing
selection policies and `random_stream_engine`, not another sampler.

**Preserve evidence and validate analysis inclusion separately.** Reuse
`ExperimentRunModel`, `ExperimentInvalidationModel.superseded_by`,
`derived_from_refs`, `TrialRunProvenanceModel`, batch/cleanup receipts and the
run/evidence/derived-measure graph. Strengthen the owning semantic joins for
replacement refs: exact run kind/version, same experiment/task and allocation
lineage, distinct identities, no dangling/ambiguous refs, self-links, cycles or
two effective successors for one slot. Preserve the original failure, invalidity
reason, timestamps, outcomes and evidence even when a later archival version
adds supersession. A link is not evidence of successful replacement. Do not
rewrite immutable terminal operations or fabricate missing results/evidence to
satisfy archival minimum fields.

There are three existing analysis traps, all requiring coherent owning changes:

- `experiment_analysis._run_is_eligible_for_study_analysis()` excludes invalidated,
  superseded and not-evaluated runs, but a failed outcome alone is still eligible.
  A scientific negative result is not automatically an invalid trial. Apply the
  authored replacement trigger and supersession rules explicitly; no blanket
  removal of all failed results or selection of the best successful descendant.
- Analysis rejects ineligible `evaluation-run` members; it does not silently
  filter them. `trial_analysis._validate_study_run_membership()` currently
  requires every linked archival run to have calibration/evaluation membership.
  Retention and included analysis membership therefore need a coherent join;
  do not delete old artifacts or mislabel failed trials as calibration runs.
- `trial_analysis._validate_study_allocation()` counts every plan entry against
  `target_runs_per_condition`. Account for original slots and replacements
  across linked admitted plans without increasing the scientific target or
  disabling over-allocation checks. At most one eligible run per original slot
  contributes. Keep task, condition, blocking, stochastic-control consistency,
  evidence-content and missing-data validators, and disclose shortfalls/bias.

**Fresh initialization and isolation are admission requirements.** Re-enter
ordinary selection, instantiation, apparatus and backend admission through
`realize_admitted_trial_entry`; construct new run-local workflow, participant,
time, runtime and secret-resolution state. No copied failed snapshot/history or
hidden backend state. Reuse SCE-006/007 clean-state requirements, obligation
dependency/trigger validation, probes, `validate_trial_cleanup_receipt()`,
`entry_owned_resource_refs()` and isolation proof/live-lease joins. A valid
receipt can truthfully report failed/partial/unverified cleanup; structural
validity alone never authorizes reuse. Cleanup failure remains independent of
the primary result and blocks the affected resources. Keep quarantine until
cessation and clean-state evidence establish reuse. Independently isolated new
resources are possible only with proof that old work cannot reach them; new
ids, directories, backends, lease expiry or process exit do not prove that.

## Cross-cutting gates and canonical incumbents

Python paths below are relative to `implementations/python/packages/`. These
are obligations for the intended implementation, not claims that existing
validators already understand replacement.

| Layer | Canonical owner and required treatment |
| --- | --- |
| Authoring and schema ingress | `raes_contracts/experiment_spec.py:parse_experiment_spec` owns bounded safe YAML, duplicate-key/alias rejection, finite JSON values and safe contract diagnostics. `contracts/experiment_spec.py` and `experiment_study.py` own closed shapes and allocation consistency. Extend these once; MCP `experiment_authoring.py`, examples and scaffolds consume them. Replacement limits need strict bounded integers, rejecting booleans/coercion and excessive expansion; `PositiveInteger` alone does not establish this. SDL policy changes, if necessary, retain `raes` parser, phase, composition, instantiation and lexical-policy validators rather than creating an experiment-specific SDL parser. |
| Compiler, DTOs and integrity | `raes_processor/trial_compiler/{inputs,policies,profiles,compiler}.py`, `TrialCompilationLimitsModel`, `seal_admitted_trial_entry/plan`, `raes_contracts/admitted_trial_plan_ingress.py`, `trial_realization.py`, `plan_projection.py` and native plan reconstruction are the existing seams. Validate complete plans and in-process carriers, exact refs and content commitments before consuming entries. Bound lineage traversal and candidate work. Carry admitted policy/linkage through inspection and both serialization directions; no metadata-only authority or private-attribute-only proof. |
| Configuration, manifests and backend willingness | `raes_backend_protocols/{manifest,capability_admission,operation_supervision}.py`, `raes_contracts/execution_policy.py`, runtime `operation_policy_admission.py`, `control_plane_configuration.py` and `control_plane_profiles.py` own their separate closed shapes. Authored allocation is not a deployment retry setting. Keep manifest/profile allowlists, installed-provider agreement and contextual willingness before effects. A declaration of `new-trial` support, durability profile or backend idempotency is insufficient authorization. Unsupported paths remain explicit refusals. |
| Auth and disclosure | Runtime `control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_admission.py`, `control_plane_api_guards.py`, `control_plane_plan_authorization.py` and `control_plane_operation_context.py` retain trusted actor, role/subject, target/run scope, request/offload limits, exact plan authorization and actor-bound audit. Parent visibility does not grant child dispatch, evidence dereference or secret access. Reauthorize each new trial and current resources; digests/lineage refs/idempotency keys are not credentials. Do not raise the global HTTP limit to match the 32 MiB plan-ingress ceiling. |
| Secrets, environment and result sinks | `raes/runtime_environment.py`, planner `stateful_admission.py`, `raes_contracts/account_credentials.py`, runtime `runtime_fact_binding_policy.py`, `runtime_fact_dispatch.py`, `backend_calls.py` and `result_contracts.py` retain binding scope/audience/freshness, protected sinks, trusted predecessor and release checks. `value_from` excludes literal `value` and `operator_secret`; classified secret literals cannot carry raw secrets. Rebind authorized references in a new isolated run context, never copy resolved values, credential caches, generated facts or participant observations from the failed run. Portable lineage contains value-safe refs only. |
| State, persistence and recovery | Runtime `control_plane_mutation.py`, `control_plane_durability.py`, `control_plane_store_records.py`, `control_plane_store_record_migration.py`, `control_plane_store_paths.py` and `control_plane_recovery.py` retain one-writer/CAS atomic snapshot-terminal-audit cuts, leases, strict codecs, private paths and immutable terminals. They own operation durability, not study allocation. The experiment coordinator must serialize budget claim and child identity/linkage in its established state authority before dispatch, with scoped idempotency and restart-safe readback. If the embedding coordinator has no such authority, that is an explicit durability prerequisite; neither a second RAES store nor `RuntimeSnapshot.metadata` fixes it. Recovery reconciles existing claims, never independently requests replacements. |
| Error envelopes and observability | Reuse `ExperimentSpecValidationError` and its safe details, compiler `CompilationFailure`, shared `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload()`, runtime `control_plane_api/_responses.py:_conflict_detail`, redacted validation/500 responses, module loggers and `control_plane_audit.py`. Record safe policy/parent/child ids, budget counts, stages and cleanup/exhaustion dispositions; logs are not allocation truth or archival evidence. Never expose raw Pydantic inputs, native exception text, plans, secret refs, host paths, argv, environment dumps or tracebacks. No duplicate exception hierarchy, audit stream or logger framework. |
| Host, workers and scheduling | Reuse existing backend process/containment and credential injection seams: private run-local work/storage, owned port/resource leases, bounded safe path/name handling, fixed argv and controlled environment. No shell interpretation of policy/reference strings, tokens in argv, broad inherited environments, new listener or service. `trial_scheduler.py` controls admitted dispatch only; worker completion order cannot choose replacements. Engine replay, redelivery, backend retries, operation recovery and Continue-As-New preserve existing identities and budgets and confer no fresh-trial permission. |

The allocation decision must be idempotent across duplicate failure/invalidity
notifications, concurrent coordinators, late invalidation and uncertain commit
acknowledgements. Bind the decision to the exact parent, original slot, authored
policy revision, qualifying evidence and child allocation. A crash must not
produce either a second child or an unaccounted budget debit. Reconciliation of
an already authorized decision is distinct from an independent recovery policy;
no stale callback may revive a replaced trial or publish over its successor.

## Extensibility, publication and verification boundaries

The seam is a versioned experiment-owned replacement choice plus an exact
parent/evidence/budget admission context, feeding the existing compiler and
one-entry realizer. Keep trigger selection (failed versus invalid), additional
trial bound and lineage scope explicit. Future narrower condition policies or
another supported failure class should extend this owner and its admission
parameters, not backend-name branches, environment switches or a generic policy
interpreter. Adaptive-difficulty follow-up proposals already require separate
trial admission; reuse that boundary without treating replacement as a difficulty
intervention or silently changing treatments.

Follow ADR-009/061/074/078 and the schema's stability rules for any authoring,
plan, profile or archive extension. `contracts/schemas/` remains normative;
`schema_bundle()` must match. The v2 `contracts/schema-publication-manifest.json`
routes change summaries/hashes to `contracts/schema-publication/entries/`, with
removals in `tombstones/`. Use `schema_invariants.py` for semantic obligations;
annotations alone do not execute them. Update affected contract/profile
registration, fixtures and canonical formal/language docs together. Author
migration guidance must explain omission, trigger/limit counting, exhaustion,
old descriptive prose, and the distinction from #1361's operation request and
SCE-007 attempts. Preserve legacy omission behavior and reject unsupported new
semantics; never infer permission when loading old records.
Omitted optional fields must not inject null/default records into legacy
canonical projections and silently change existing plan identities. Preserve
legacy vectors; a selected replacement policy must enter its owning content
commitment. Changed output semantics require the governed profile/version path.

Meaningful evidence belongs in the existing `test_issue_1361_*`,
`test_sce_002_{admitted_trial_plan,trial_compiler,trial_realization}.py`,
`test_sce_006_{batch_scheduler,cleanup_contracts}.py`, `test_plan_projection.py`,
`test_runtime_contracts.py` and experiment-core test families. Cover omission,
failed/invalid triggers, scientific failure versus invalidity, independent
attempt/trial budgets, a failed replacement, exact-limit exhaustion, forged or
cyclic lineage, duplicate/concurrent/restarted decisions, uncertain commit,
unchanged old identities/streams, fresh initial state, cleanup refusal and
quarantine, and single-count analysis with retained old evidence. Include
negative tests showing backend/transport/engine recovery cannot allocate a
child. Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, policy/schema tooling
and targeted local checks; full/integration/fuzz/completion suites remain CI-only.
Do not invent a Ground Control requirement UID for this issue-only work.

## Non-goals and anti-patterns

This issue does not add within-trial retry semantics, checkpoint continuation,
a second scheduler/workflow engine, a new trial/run repository, generic stopping
rule execution, adaptive experiment optimization, scientific scoring, or physical
safety guarantees. It does not certify a downstream allocator or promise rollback,
exact replay or artifact availability. Keep experiment policy, operational
recovery, backend effect knowledge, cleanup, archival status and analysis
eligibility separate. Avoid success-only histories, free-text policy interpreters,
counter resets per descendant, digest bypasses, duplicate schemas/validators,
shared failed-run state and new services or data transfers.

## Implementation acceptance mapping

All paths below are relative to `implementations/python/packages/` unless noted.

- [x] Explicit author choice and omission: `raes_contracts/contracts/trial_replacement.py:16`
  and `contracts/experiment_spec.py` bind closed triggers and strict finite
  additional-trial limits, preserving omitted-field commitments.
- [x] Separately admitted fresh identity: `raes_processor/trial_compiler/replacement.py`
  and `replacement_inputs.py` compile one new sealed plan through existing
  selection/admission. Ordinary realization initializes the new entry; existing
  plans and streams are unchanged. The new compiler profile has fixed vectors.
- [x] Preserved evidence and single-count analysis:
  `raes_contracts/contracts/trial_replacement_archive.py` preserves exact parent
  versions; `trial_replacement_analysis.py` validates contiguous lineage and
  eligible leaves. `trial_analysis.py:validate_admitted_trial_study` retains
  authoritative evidence/target validation with full archived parent history.
- [x] Recovery grants no allocation authority: the explicit pure allocation API
  has no runtime recovery/transport call site. The incumbent scheduler dispatches
  only admitted entries and #1361's unbound-operation refusal remains enforced.
  Durable coordinators must atomically claim/persist decisions before effects
  and use authoritative readback; compilation does not certify that boundary.
- [x] Bounds, exhaustion, cleanup refusal and migration: focused tests in
  `implementations/python/tests/test_issue_1396_trial_replacement.py` cover
  strict input, fresh instantiation, triggers, cleanup failure, duplicate and
  replayed decisions, stale/forked history, shared exhaustion, shortfalls and
  content-backed study analysis. Migration guidance is
  `docs/explain/reference/trial-replacement-migration.md`; published schemas and
  publication records match the reference schema bundle.

The issue has no requirement UIDs. Existing ACTIVE SCE-002 and EXP-706
traceability is reconciled for the new owning helpers and verification surfaces;
no requirement lifecycle transition is proposed. Verification is targeted;
repository-wide, integration, fuzz and completion suites remain CI-only.

### Review repair verification

The review and decisions are recorded on the issue:
https://github.com/OpenRAE/rae/issues/1396#issuecomment-6297546626.

- `core-F1`: supersession retains version-bound evidence relations and validation
  disclosures on the exact original artifact through the predecessor link,
  rather than falsely rebinding their authority to a new archival version.
  Regression: `test_supersession_preserves_version_bound_assertions_on_the_historical_parent`
  covers both owning carriers and retained-history reconciliation.
- `core-F2`: allocation and analysis require every intermediate replacement to
  resolve the first archival version reserved by its predecessor, not only the
  final leaf. Regression:
  `test_intermediate_replacement_must_resolve_the_reserved_first_archive_version`
  covers both public allocation and an independently sealed invalid history.

Both regressions failed on the reviewed tree before repair. The focused
replacement module passes after the repairs. File-local policy and lint pass;
no full or integration suite was run locally.
