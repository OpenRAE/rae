# Issue #1361 — SDL execution and recovery requirements preflight

Date: 2026-09-27. Status: preflight guidance. Scope: issue #1361, after
prerequisite issue 1360. This note records boundaries for the
authoring-to-plan change; it defines neither SDL syntax nor an implementation
sequence. [ADR-113](adrs/adr-113-reusable-execution-machinery.md), its
[authored retry design](../research/execution-architecture/authored-retry-policy.md),
and the [#1360 operation contracts](issue-1360-backend-operation-contracts-preflight.md)
remain the semantic owners. The #1348 exploration is available at revision
`077f7d04` in repository history; its owner decisions distinguish durability
from resumption, allow a failed experiment to require a new trial, and make
backend inability or unwillingness a reason to refuse an authored requirement.
No new ADR is needed: ADR-113 already owns the decision, while this note locks
down its language-to-plan adoption boundary.

## Boundaries to preserve

- Carry the author's *effective requirement* and its defining scope/version
  through SDL composition, instantiation, compilation, plan projection and
  backend admission. Missing local policy inherits; explicit never-repeat is a
  value. Resolve a complete policy at the nearest defining scope, with the
  conservative no-second-effect fallback when no scope permits repetition.
  Preserve existing workflow, trial and cleanup defaults separately; do not
  reinterpret omission as automatic retry, resumption or fresh-trial creation.
- Reuse `WorkflowStep` (`retry`, `max_attempts`, `on_failure`,
  `on_exhausted`), `WorkflowTimeoutPolicy` and compensation for workflow
  control. Reuse `ExecutionRetryPolicyModel`, `TrialCleanupPlanModel`,
  `TrialExecutionAuthorityModel` and `AdmittedExecutionControlModel` for the
  trial attempt/cleanup controls they already own. Their present fields do
  not encode general interruption resumption, failure-class selection or
  fresh-trial allocation. Extend the owning contract only where a required
  choice has no representation; do not overload `after_effect_policy`,
  workflow retry or a platform application's job `execution_policy`.
- A backend invocation, operation idempotency replay, authored workflow
  attempt, participant episode and experiment trial/run have different
  identities. Ending a trial cannot relabel its old run or increment a retry
  counter to manufacture a fresh trial. A fresh trial needs the existing
  experiment allocation, new run identity, isolation and cleanup authority;
  the choice is invalid where no trial context exists. A failed old trial and
  its evidence remain intact.
- Capability, contextual willingness, effect knowledge, cessation and
  continuation safety are separate facts. A manifest or durable store cannot
  establish all of them. Admission rejects unsupported requirements; a later
  backend refusal or uncertain effect remains explicit under #1360's
  versioned request/response and reconciliation contracts. No backend,
  scheduler or execution engine may weaken the committed requirement or
  choose a recovery action from application type or an IT/OT label.
- Preserve authored intentional faults and mixed-scope dependencies. Reset,
  compensation and fresh initialization have their own effects and proof
  obligations. Unknown effect state, a timeout, an accepted cancellation or
  process loss alone cannot authorize another effect or prove clean state.

## Existing coverage and the remaining contract gap

- `WorkflowStep`, `WorkflowExecutionContract` and workflow result/history
  validation already own workflow attempts and failure edges. They do not own
  backend invocation replay, interruption recovery or experiment allocation.
- `ExecutionRetryPolicyModel`, `TrialExecutionAuthorityModel` and
  `AdmittedExecutionControlModel` already own trial attempt, timeout and cleanup
  facts. Today that authority is supplied separately to `TrialCompilationRequest`,
  not authored in `ScenarioContent`, and therefore is not evidence that an SDL
  choice survived composition or ordinary compilation.
- `RuntimeModel`, `PlanOperation` and the provisioning/orchestration/evaluation
  plan contracts currently carry no complete scoped recovery requirement.
  `BackendOperationRequestModel.requirement_refs` and `required_guarantees` can
  reference or project an admitted requirement, but cannot become its editable
  semantic source. The v1 guarantee vocabulary also has no general resumption or
  fresh-trial meaning.
- `require_cleanup_plan_capability()` admits cleanup actions and observations;
  backend manifests and #1360 admission distinguish installed capability from
  contextual willingness. Neither one allocates a retry/trial or supplies the
  missing authored policy.

A derived guarantee tuple on an admitted trial entry is only a backend-admission
projection of these authored choices, never their source. The
[delivery resolution](#delivery-resolution) records how the issue was scoped.

## Cross-cutting owners and gates

| Boundary | Canonical incumbent and required treatment |
| --- | --- |
| SDL input and validation | `raes/_base.py` (`SDLModel.extra=forbid`), `_source_profile.py`/`SDLParserLimits`, `scenario.py`, `parser.py`, `composition/`, `phase_contracts.py`, `instantiate.py`, `validator/_workflows_verify.py`, `validator/_workflows_analysis.py` and `raes/semantics/workflow.py`; use their closed shapes, bounded YAML/import graph, canonical addresses, reference resolution, variable substitution, composition stability and semantic diagnostics. Validate conflicting scopes and invalid choices in the owning semantic layer, then revalidate instantiated concrete values. Do not add a second parser/default resolver or merge partial policies field-by-field during import. |
| Compilation and plan inspection | `raes_processor/compiler/{pipeline,workflows,workflow_steps}.py`, `models/runtime_model.py`, `trial_compiler/`, `planner/core.py`, `raes_contracts/planning.py`, `contracts/{realization_plans,admitted_trial_plan,trial_cleanup}.py`, `plan_projection.py` and `raes_cli/processor.py`; retain resolved requirements, origin and identity in typed, digest-bound published projections. Inspect the *compiled* requirement, including defaults, instead of reconstructing intent from prose or backend profile. Keep the three runtime domain plans and the admitted trial plan's distinct authorities; do not hide policy in arbitrary operation payloads. |
| Runtime/configuration shape | `raes_runtime/control_plane_configuration.py`, `registry.py`, `registry_target_validation.py`, `raes_backend_protocols/{backend_manifest,manifest,capabilities}.py` and `raes_contracts/contracts/manifests.py`; preserve closed option/manifest shapes, installed-component agreement and method-shape probes. This issue should need no new process, endpoint, credential loader or generic runtime setting. If an optional provider surface is touched, declaration, conversion, component presence and call-shape checks change together; schema availability alone never advertises support. |
| Backend admission | `raes_backend_protocols/capability_admission.py` (including `require_cleanup_plan_capability()`), backend manifests, `raes_processor/planner/`, `raes_runtime/manager_plan_admission.py` and `raes_contracts/contracts/{backend_operation,backend_operation_validation}.py`; compare the exact committed requirement with available capability and contextual willingness. Resolve and type-check requirement refs, derive any backend guarantees canonically from the admitted requirement, and reject a mismatch before dispatch. Existing libvirt plan admission remains concrete realization checking, not a portable policy authority. |
| Identity, auth and persistence | `raes_runtime/control_plane_security.py`, `control_plane_admission.py`, `control_plane_operation_context.py`, `control_plane_store_*`, `raes_contracts/operation_lifecycle.py`, `contracts/admitted_trial_plan.py` and `contracts/trial_cleanup.py`; authorize actor and target/run scope, commit the effective policy and provenance, use existing CAS/idempotency/audit and immutable plan digests, and keep restart readback lossless before making durability claims. Engine task identity is not authorization. |
| Errors and observation | `raes/_errors.py`, `raes_contracts/diagnostics.py`, `raes_runtime/diagnostics.py`, `raes_cli.processor._sdl_error_summary()`, control-plane operation receipt/status, API `_responses.py`, and #1360 response/reconciliation carriers; report bounded, stable diagnostic codes and safe addresses. Retain uncertainty and refusal as evidence, without copying Pydantic input values, backend exception text, raw request values or secrets into CLI, HTTP error envelopes, audit or logs. Use the existing module loggers only for fixed redacted operational events; do not add another exception or logging hierarchy. |
| Schemas and publication | `contracts/schemas/sdl/`, `contracts/schemas/plans/`, the v2 `contracts/schema-publication/entries/` records indexed by `schema-publication-manifest.json`, `raes_contracts.contracts.schema_bundle()`, `tools/generate_contract_schemas.py`, `check_generated_schemas.py`, `check_schema_publication.py` and `check_schema_coverage.py`; schema is normative, Python is a matching implementation. Update source/instantiated/materialized phase contracts and only the plan schemas that actually carry the value, their per-contract `last_change` hashes, routed coverage, public SDL semantics and an author migration guide together. Do not hand-add an ungoverned parallel schema or silently change an old default. |

## Security and runtime crossing

SDL is data, not permission to execute. Its parser and closed SDL/phase
validators reject oversized, ambiguous, malformed or unresolved declarations;
the composition budget also bounds imports, depth, nodes and bytes. Authenticated
control-plane admission still checks actor, target/run and plan identity.
Backend manifest/config shape checks and the #1360 bounded JSON operation
contracts then check exact capabilities, guarantees, context and current
willingness. Existing `raes/runtime_environment.py` and
`raes_runtime/backend_account_credentials.py` govern environment bindings
and credential egress; a recovery requirement contains references and
value-free commitments, never credentials or secret-bearing defaults.
`control_plane_operation_context.py` owns the safe projection. Runtime and
backend requests must use bounded carriers, not shell fragments, process
arguments, environment values or opaque executable strings; no new OS-level
exposure is required by this issue. Existing diagnostic and HTTP envelopes
must stay bounded and redacted. Operation state, audit and store codecs must
round-trip the admitted choice without promoting a backend response to
runtime authority. If a new raw JSON ingress is introduced despite this issue's
transport-neutral scope, it must pass `raes_contracts/json_ingress.py` before
closed model validation; `ContractModel.extra=forbid` alone does not reject
duplicate members, non-finite values or excessive aggregate size.

## Extensibility and verification boundary

The seam is a governed, complete effective-policy value plus source scope and
version in the admitted artifact, referenced by an exact operation request.
Any `OperationGuarantee` set is a canonical, non-editable projection of that
value, not a second authority. A later failure class, backend guarantee or
scoped policy can extend the policy and its one projection seam without editing
every workflow step or adding an application-specific mandatory declaration.
Keep retry-attempt and fresh-trial budgets independent; backend-specific
willingness remains a contextual admission decision.

Verify the published source and phase schemas, composition/default/override
round trips, compiled plan inspection, invalid cross-scope combinations,
workflow/trial identity separation, and capability versus contextual refusal.
Use `test_sdl_{models,parser,validator,phase_contracts}.py`,
`test_sdl_module_registry.py`, `test_runtime_planner.py`,
`test_sce_002_{trial_compiler,admitted_trial_plan}.py`,
`test_sce_006_cleanup_contracts.py`, `test_plan_inspection_cli.py`, backend
manifest tests and `test_issue_1360_backend_operations.py` as targeted regression
surfaces. Publish author migration for any changed syntax or defaults.

Anti-patterns and non-goals: do not treat a derived guarantee list as the
authored contract; add a free-form `execution_requirements`/metadata dictionary;
duplicate retry, cleanup, workflow, operation-state or exception schemas; infer
policy from durability, application type, backend name or IT/OT labels; multiply
attempts across transport, workflow and trial layers; reinterpret omission as
permission; mutate old run identity/history; or serialize Python callbacks,
exceptions, futures or engine objects. Runtime orchestration, backend execution,
new HTTP routes, checkpoint formats, engine retry mapping, new OT safety
profiles, physical-OT certification, distributed supervision and automatic
trial allocation are outside this issue's implementation boundary.

## Delivery resolution

The owner decided the representation during delivery. It supersedes the
scoped-policy guidance above wherever the two differ:

- **No new SDL recovery construct.** Authors already express failure responses,
  in as much detail as they need, through existing constructs. Workflow
  `retry`, `max_attempts`, `on_failure`/`on_exhausted` branches, compensation
  and timeout cover in-world responses, including deliberate resets and injects.
  The trial execution authority (`on_timeout`, `on_cancellation` and the
  SCE-007 cleanup plan's `ExecutionRetryPolicyModel`) covers trial attempts.
  A scoped policy table, a policy enum or author-supplied guarantee lists were
  rejected as unnecessary. Saying nothing remains valid: nothing is repeated,
  resumed or replaced.
- **Replacement trials** have no machine-actionable representation today.
  `replication_policy` and `stopping_rule` are free text that no code reads,
  and nothing produces `superseded`/`superseded_by`. Replacement trials are
  tracked separately as [#1396](https://github.com/OpenRAE/rae/issues/1396).
- **Nothing infers recovery from durability.** Store reopening classifies
  `ACCEPTED`/`RUNNING` operations and never re-dispatches them, and
  `INDETERMINATE` blocks new effects until an operator resolves it. Idempotent
  replay returns the existing receipt without calling the backend. No path
  selects recovery from an application type, IT/OT label or backend name.
- **Workflow choices already reach admission.** The planner rejects an
  orchestrator that does not declare the required workflow feature.

The delivered gap was trial-level. Authored timeout and retry choices were
sealed into the admitted trial plan, but nothing checked that the selected
backend could honour them: `require_cleanup_plan_capability()` was never
called, and manifests could not declare #1360 operation guarantees. The
delivery closes that gap as follows:

| Authored choice | Backend guarantee RAE requires |
| --- | --- |
| `on_timeout: cancel` | `cancellation` |
| `retry_policy.max_attempts > 1` | `cessation-evidence`: attempts stay sequential, so the previous attempt must be proven stopped |
| the same with `after_effect_policy: disallow` | also `effect-observation`: the absence of effects must be established |

- `required_operation_guarantees()` in `raes_contracts` is the single projection.
  `AdmittedExecutionControlModel.required_guarantees` records it. The field is
  omitted when empty, so existing plans keep their bytes and digests. The
  admitted plan recomputes it from the entry and its cleanup plan and rejects
  any edit.
- Backend-manifest-v2 gains an optional `capabilities.operation_supervision`
  declaration. It requires the backend operation contract family and is neither
  willingness nor evidence.
- Trial compilation calls `require_execution_authority_capability()` for every
  backend selected for an entry, including mixed-composition profiles. The
  check covers both the cleanup plan and the derived guarantees. An entry whose
  realization selects no backend, such as a processor-only mixed composition,
  is refused rather than admitted vacuously.
- A backend that cannot honour a choice is refused with
  `trial-compiler.execution-authority-unsupported`. It is never treated as best
  effort.
- The default choices (a single attempt, with no cancellation on timeout)
  require nothing, so ordinary P0 work, CTFs and simulations gain no obligation.
- Runtime dispatch (#1362) copies the recorded guarantees into
  `BackendOperationRequestModel.required_guarantees`. The existing
  `require_backend_operation_admission()` then checks them against the installed
  provider's capabilities and contextual willingness.
