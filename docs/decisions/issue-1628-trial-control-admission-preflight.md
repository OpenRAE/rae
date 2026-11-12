# Issue 1628: Trial control admission

Date: 2026-10-26.
The issue supplies the delivery contract.
No formal requirement is attached.
Native GitHub blocked-by links govern dependencies.
This note gives design limits, not a task plan or proof of dependency closure.

## Decision and owners

ADR-084, ADR-104, ADR-113, and ADR-115 settle the owners.
No new ADR is needed.
RAE admits trial controls.
The shared runtime owns live operation authority.
Backends supply native effects and evidence.

Admission must reject the whole plan if any selected backend lacks required support.
This check must happen before any entry starts.
A check on one entry at dispatch cannot provide that whole-plan rule.

Paths below start at `implementations/python/packages/`.
`raes_processor/trial_compiler/compiler.py` owns atomic trial compilation.
It returns one sealed plan or safe diagnostics.
Use this boundary for ordinary, mixed, and replacement trials.
`apparatus.py` checks manifest identity, digest, compatibility, and envelope.
`realization_admission.py` selects mixed profiles and components.
Check each coordinate's selected backends, including reachable mixed stages.
Unused caller manifests cannot supply support.
Backends cannot pool their guarantees.
An empty backend set must fail.
Keep capture, participant configuration, and resource-coverage checks.

`_EntryCompilationAuthority` holds selected manifests and capture support.
Keep converted backend values there.
Derive capture support from those same values.
Do not add another selection or conversion path.

## Controls and declarations

`AdmittedExecutionControlModel` owns the attempt timeout, timeout response, cancellation response, and cleanup plan reference.
`TrialCleanupPlanModel.retry_policy` owns attempt repetition through `ExecutionRetryPolicyModel`.
Resolve the exact cleanup plan and its entry/run joins.
Keep obligation order, terminal triggers, reset coverage, and resource owners.
Do not copy retry policy into execution controls.
Trial repetition is distinct from replacement, workflow retry, transport replay, and native operation policy.

Use one pure shared calculation with typed controls and cleanup policy.
Reuse `OperationGuarantee` in `raes_contracts/contracts/backend_operation.py`:

- `cancel` on timeout requires `cancellation`.
- Repetition requires `cessation-evidence`.
- Repetition with `after_effect_policy=disallow` also requires `effect-observation`.

Reuse `raes_backend_protocols/capability_admission.py::require_cleanup_plan_capability()`.
It checks required actions and probes, initial-state probes, reusable state, and residual-state disclosure.
Best-effort obligations keep their weaker checks.
Cleanup validators still check reset and compensation joins.

Require only the guarantees that the controls need.
`abort` and `cleanup-and-fail` do not imply rollback or cessation.
Keep `on_cancellation` as authored.
Trial deadlines, cleanup budgets, operation budgets, and scenario time remain distinct.
Any numeric conversion must preserve duration and finite runtime bounds.
Do not truncate, overflow, extend deadlines, or invent defaults.

The current manifest has no static operation guarantee declaration.
Native `ExecutionPolicyCapabilities.responses` does not prove trial cancellation or cessation.
The live `BackendOperationCapabilitiesModel.guarantees` has the correct terms.
The pure compiler must not call a provider to obtain them.
Add only the missing static declaration to backend manifest capabilities.
Make it optional when no supervision guarantee is required.
Missing support must refuse a demanding entry.
Never put a provider or live invocation state into a manifest.

Use bounded, unique, closed terms.
Require the existing `BACKEND_OPERATION_CONTRACT_IDS` family.
Keep both conversion directions in `raes_backend_protocols/manifest.py`, including envelope-aware conversion.
Keep constructor checks on internal manifests.
Omit absent optional fields so unchanged declarations keep their digests.
A claim does not prove installed shape, conformance, or willingness.
`registry_target_validation.py` and `require_operation_provider()` still own installed checks.

Derive demands from sealed controls and cleanup policy.
Do not store another guarantee list on admitted entries.
A future stored projection would need canonical joins and a governed contract change.
The shared calculation and selected-backend map are the extension seam.
Do not add backend-name conditions or scheduler rules.

Local commit `c4d90a39` contains reverted intent from PR 1398.
Reuse the reasoning, not the whole patch.
Its entry-contract edits and numbered research releases are not implied by this issue.
Its removed helpers are not current owners.

## Cross-cutting fit

- **Parsing and integrity:** Reuse `ContractModel`, strict primitives, manifest validators, canonical digests, and compiler limits.
  Reconstruct caller-held values at existing trust boundaries.
  Frozen containers do not freeze nested models.
  External plans still use bounded ingress and complete-plan reconstruction.
  Keep seals, exact entry membership, and one semantic validator.
- **Published contracts:** The backend-manifest-v2 schema is the portable authority.
  Keep types, adapters, `schema_bundle()`, fixtures, and consumers aligned.
  Record the change and hash in the per-contract publication entry referenced by `contracts/schema-publication-manifest.json`.
  ADR-009 and ADR-061 still apply.
  Do not auto-claim support for backends.
- **Configuration and runtime:** Keep `RuntimeTarget` and registry shape checks.
  Keep control-plane composition, store, and profile checks.
  The compiler consumes acquired digest-bound values without discovery, I/O, or environment lookup.
  Runtime still checks installed capability, backend identity, exact command/kind, capability digest, and willingness before effects.
  Ordinary native requests currently carry an empty guarantee list.
  Do not describe runtime admission as an implicit check of trial-derived demands.
- **Authorization:** Pure compilation grants no principal or effect permission.
  Trusted embedders retain P0 duties.
  Existing HTTP paths keep strict defaults, request limits, role checks, and actor/target/run context.
  Dispatch, control, cleanup, and evidence access retain separate authority.
  Add no route or credential.
- **Secrets and disclosure:** Keep secret references, participant configuration owners, fact-binding policy, provenance, and final-sink checks.
  Do not flatten configurations into environment dictionaries.
  Preserve sensitivity, unique names, and literal/value-source rules.
  Do not resolve secrets or read ambient credentials during admission.
  Safe diagnostics must hide payloads and backend details.
- **Host and process:** Add no subprocess, listener, host probe, or backend contact.
  Keep process supervision and safe private store paths.
  Tokens must not enter argv or environment dumps.
  A timeout or process kill does not prove remote cessation or safe reuse.
  Occupied slots remain owned until existing release checks pass.
- **Errors and audit:** Reuse `CompilationFailure`, `TrialCompilationResult`, `Diagnostic`, and deterministic failure selection.
  Use a stable bounded code, address, and safe message.
  Never expose raw validation or backend text.
  Existing HTTP redaction, audit events, and runtime correlation remain authoritative.
  The compiler needs no new logger or audit store.
- **State and recovery:** Add no mutable store.
  Keep distinct plan, entry, run, attempt, and operation identities.
  Preserve atomic state commits, revision checks, leases, claims, and reconciliation.
  An acknowledgement is not trial completion.
  Existing trial, cleanup, and batch result validators keep joins.
  Runtime evidence owners establish actual cessation and clean state.
  A log, claim, or failure receipt cannot permit retry or resource reuse.

## Verification and limits

Tests must cover supported and refused controls, required and best-effort cleanup, and missing declarations.
They must distinguish selected from unused backends and ordinary from mixed profiles.
An unsupported later entry must expose no partial plan.
Map order and coordinate partitions must not change safe diagnostics.
Check manifest/schema round trips and absence of provider calls or effects.
Relevant tests include the trial compiler, mixed admission, cleanup, manifest adapter, native operation, policy admission, and replacement modules.
Test behavior rather than prose spelling or helper existence.

Existing workflow, authority, import, schema-publication, and verification-plan checks remain required.
Keep the 500-line source limit.
Use focused owning modules rather than enlarging monoliths or copying helpers.
Run targeted checks locally.
CI owns full, integration, fuzz, and completion suites.
Do not invent a requirement UID for this requirement-free issue.

This change does not implement timers, cleanup, retry execution, or a new trial operation kind.
It adds no scheduler, queue, store, DTO, driver, service, allocation policy, or scoring rule.
`BackendTrialUnit` keeps its neutral single-entry handoff.
An old seal still needs current support checks at consumption.
Early declarations complement live checks.
They cannot replace them or justify stronger conformance claims.
