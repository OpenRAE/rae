# Issue #1361 — Authored execution and recovery requirements preflight

Date: 2026-10-04. Scope: supplied issue #1361; prerequisite #1360.
Architecture guidance only; no implementation plan, new normative contract, or
claim of executable recovery support. The issue is the delivery contract; there
is no attached Ground Control requirement.

## Authority and representation boundary

Retain [ADR-104](adrs/adr-104-runtime-control-plane-architecture.md),
[ADR-113 §4](adrs/adr-113-reusable-execution-machinery.md), its adopted
[authored retry design](../research/execution-architecture/authored-retry-policy.md),
and the [#1360 publication](../../specs/formal/runtime-contracts/backend-operation-supervision.md).
These already establish the architectural boundaries; no new ADR is needed.
The issue's historical [owner clarification](https://github.com/OpenRAE/rae/blob/077f7d04/docs/research/runtime-refactor/README.md)
leaves syntax/defaults open; the later adopted retry design supplies scoped
resolution and the conservative fallback. Do not invent additional accepted
defaults or promote its illustrative use cases into mandatory declarations.

Reuse existing authoring wherever it expresses the requirement. Add only the
missing execution/recovery choices to their owning language and contracts.
Resolve one complete effective policy with its defining scope, reference,
revision and provenance. Carry it through instantiated SDL, compilation and
the exact admitted native plan/requirement artifact. The backend request uses
that artifact's content-bound identity through `command`/`requirement_refs`;
it does not acquire a parallel recovery-policy vocabulary. Policy must be
inspectable without backend effects, and changing it must change the relevant
semantic/plan/request commitments. Requirements must survive serialization,
HTTP reconstruction and recovery without consulting today's source defaults.

Python paths below are relative to `implementations/python/packages/`.

| Existing semantic owner | Reuse and limit |
| --- | --- |
| `raes/orchestration/{_workflow,_steps}.py`, `raes/semantics/workflow.py`, `raes/validator/_workflows_{analysis,verify}.py`; compiler `workflows.py`/`workflow_steps.py`; `raes_contracts/workflow/contracts.py` | Workflow retry bounds, failure/exhaustion edges, timeout and compensation already have meaning and validation. Preserve the compiled `WorkflowExecutionContract` and step contracts; do not convert a control-graph retry into a transport retry. Omitted compensation remains disabled. |
| `raes/participant_execution.py`, compiler `participant_autonomous_execution.py` | Participant stop/continue and selected failure-class retry policies already exist. Preserve `stop`, zero candidate retries and their declared bounds where applicable; these are participant-action semantics, not universal operation defaults. |
| `raes_contracts/contracts/{trial_compilation,trial_cleanup,admitted_trial_plan_components}.py` | `TrialExecutionAuthorityModel` and `AdmittedExecutionControlModel` own attempt timeout/cancellation and cleanup linkage. `TrialCleanupPlanModel.retry_policy` alone owns the existing `ExecutionRetryPolicyModel`; do not duplicate it in execution controls. Its `disallow` concerns after-effect repetition, not all repetition or resumption. Existing reset-reference coverage, dependency and evidence validators remain binding. |
| `raes_processor/trial_compiler/`, `raes_contracts/contracts/{admitted_trial_plan,batch_execution,trial_analysis}.py` | Sealed plan/entry/run identities, allocation, attempts, independent cleanup receipts and analysis already have authorities. A fresh trial requires separately admitted allocation, a new run identity and preserved failed-trial evidence. An attempt retains its entry/run. The batch scheduler does not allocate trials. |
| `raes_contracts/{participant_episode,participant_episode_closure}.py`, `contracts/experiment_plan_controls.py`; runtime participant lifecycle/control | Episode reset/restart, RL termination/truncation and planned episode termination remain distinct from operation cancellation, workflow end and experimental trial failure. Recovery must not manufacture an episode or rewrite its history. |
| `raes/time_model.py`, compiler `time_model.py`, backend `capability_admission.py`, runtime `control_plane_timeouts.py` | Authored clock/domain/segment and progression remain semantic time; apparatus deadlines are separate bounded budgets. Snapshot durability does not establish time continuity, a continuation boundary or permission to resume. |

Existing owners do not yet provide the whole accepted design: general lexical
failure-policy inheritance, fresh-trial/exhaustion policy and verified
continuation requirements need governed representation. Their absence is not
permission for a generic policy interpreter or another workflow engine.

## Resolution, admission and extensibility

Use the accepted scenario-default → enclosing lexical scope → explicit local
choice rule. Resolve the nearest **complete** policy, not a field-wise mixture.
Explicit never-repeat is a value, not omission. Missing permission authorizes
no second effect; existing explicit workflow/participant policies still count
as authored choices. Child overrides do not alter siblings or weaken binding
requirements. Preserve definition-site binding across imports and workflow
calls; an explicit application-site choice requires its own validation.
Duplicate scopes, ambiguous/dangling references, cycles, unsupported revisions
and incompatible constraints are errors, independent of import/list order.

Reuse `raes/realization_designation.py`'s canonical namespace/JSON-pointer scope
mechanics and `raes_contracts/addressing.py`; open/closed realization authority
is a different concern and cannot encode permission to retry. New references
must participate in `composition/_expand.py:_rewrite_payload_with_symbols`,
shared by import expansion and semantic transformations, and in bounded
composition/provenance. Flat name prefixes alone cannot preserve imported
defaults. Revalidate parameter-bound values through `instantiate.py` and the
closed phase models; keep authoring machinery out of instantiated snapshots
under ADR-078. Do not use private attributes as the only portable policy record.

Keep SDL validity separate from selected-backend executability. The compiler
preserves a valid requirement even when a backend cannot realize it. Planner
capability diagnostics prevent execution of an incompatible plan; contextual
willingness is checked at actual admission and again before effects. Inspection
must retain the requested policy and explain rejection, never clamp limits,
drop guarantees, substitute backends or silently choose another recovery action.

`require_operation_provider()` checks opt-in contracts and installed signatures;
`require_backend_operation_admission()` checks identity, operation kind,
guarantees, capability commitment and willingness. Neither resolves native
`requirement_refs` or proves their contents/evidence. The owning authority must
validate exact contract kind/version/content and binding constraints. The v1
guarantee vocabulary has **no general continuation/checkpoint guarantee**.
Never map resume to `effect-observation`, store durability or method presence.
An unrealizable required continuation must be rejected explicitly; accepting it
requires a governed compatible contract extension and actual provider support.

The extensibility seam is a versioned, scoped effective policy plus exact native
requirement references and contextual provider admission. Keep operation kind,
retry unit, permitted failure/effect classes, response/validity consequences,
clock/budget basis, evidence obligations, exhaustion disposition and optional
trial authority explicit where applicable. Reuse existing field meanings;
profile/revision selection should allow the next policy variation without
backend-name or IT/OT branches. Do not require every policy to contain trial,
participant, engine or physical-OT fields. Admit cross-scope dependencies:
resetting shared state/time can violate another scope's policy. An intentionally
injected fault is not automatically infrastructure damage to repair.

## Cross-cutting gates and whole-repository obligations

These are requirements on the intended implementation, not assurances that
every incumbent already enforces the new fields.

| Layer and canonical incumbents | Required treatment |
| --- | --- |
| SDL ingress: `raes/{parser,_source_validation,_yaml_loader,_mapping_scopes,_base}.py`, `schema_catalogs.py`, `validator/`; module registry trust/lockfiles | Keep safe YAML, duplicate-key, byte/depth/alias-work and JSON-domain gates. Use `SDLModel`, canonical identifiers, enum/variable parsers and shared map catalogs so policy names are literal identities, not normalized field keys. Semantic reference checks follow structural validation; imports retain existing trust and bounded resolution, not arbitrary file/network policy loading. |
| Phase/compiler/planner: `raes/{scenario,phase_contracts,instantiate}.py`, `raes_processor/{compiler,planner}/`, `raes_contracts/planning.py` | One semantic resolution owner serves every execution composition. Preserve phase provenance, bound references/expansion and strict resolved numeric/enum values; no unresolved variable can reach dispatch. Use incumbent diagnostics for invalid combinations and manifest incompatibility. Preserve ADR-015/036 import direction and source caps; SDL cannot import processor/runtime/backend policy code. |
| Portable DTOs and commitments: `raes_contracts/contracts/{base,realization_plans,backend_operation}.py`, `plan_projection.py`, `canonical.py`; runtime `control_plane_api_models.py`, `control_plane_plan_authorization.py`, `manager_plan_admission.py`, `backend_input_contracts.py` | Extend owning shapes and both conversion directions consistently. Closed models are insufficient for strict finite/bounded quantities and cross-object joins; reuse strict primitives and native validators. Bound values before copying/hashing. Include effective policy in exact planner authorization and request commitments; HTTP authentication cannot authorize a caller-modified plan. Preserve differing native plan/backend digest conventions rather than inventing another encoder. Validate in-process carriers too, not only JSON. |
| Manifest/config/profile shapes: `raes_backend_protocols/{capabilities,backend_manifest,manifest,capability_admission,operation_supervision}.py`, `raes_contracts/{manifest_authority,versions,backend_profiles}.py`, runtime `registry_target_validation.py`, `control_plane_configuration.py`, `control_plane_profiles.py` | Reuse manifest conversion, contract allowlists and installed-component agreement wherever touched. Keep authored policy in plans; constructor options/transport env are apparatus configuration. Backend profile support and P0–P3 durability/deployment guarantees are different axes. Ordinary P0 remains usable; no implicit opt-in or P3 claim. |
| Auth/disclosure: runtime `control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_admission.py`, `control_plane_operation_context.py`, `control_plane_api_guards.py` | Trusted identity determines actor and exact target/run/scope. Policy refs/handles/digests grant no authority. Preserve bearer/proxy rules, request-size and bounded offload gates, planner authorization, supervisor-specific identity and operator-only administrative resolution. Inspection and status also obey disclosure policy. |
| Secrets/env bindings: `raes/runtime_environment.py`, planner `stateful_admission.py`, `raes_contracts/account_credentials.py`, runtime `runtime_fact_dispatch.py`/`runtime_fact_binding_policy.py` | Carry authorized value-safe references, never resolved secrets in policy/provenance/history. Rebinding rechecks scope, audience, freshness, source/type and protected-sink rules. Environment `value_from` excludes literal values and `operator_secret`; redacted/operator-secret literals cannot hold raw material. Retain ephemeral credential-sensitive retry proof; a persisted public digest after restart is insufficient. Preserve CLI account-placement redaction. |
| Backend outcomes and final sinks: runtime `backend_calls.py`, `backend_call_contracts.py`, `backend_result_diagnostics.py`, `result_contracts.py`, workflow/evaluation result validators and participant final-sink checks | Policy cannot bypass trusted-predecessor isolation, native state/history validation, changed-scope/effect accounting or credential egress/release gates. Refusal, cessation, effect knowledge and requirement satisfaction are separate facts. A rejected result/exception does not prove absent effects; accepted cancellation does not prove cessation or rollback. Unknown effects/cessation retain indeterminacy and exclusion. |
| Persistence/recovery: runtime `control_plane_mutation.py`, `control_plane_durability.py`, `control_plane_store_records.py`, `control_plane_store_record_migration.py`, `control_plane_store_paths.py`, `control_plane_recovery.py` | Use the existing one-writer atomic snapshot/terminal/audit cut, CAS, strict codecs, private paths and leases. If persisted owning carriers change, migrate explicitly; never restore a stronger policy from omitted old fields. Preserve admitted policy identity and immutable terminal parents. Separate unknown store acknowledgement/readback from unknown backend effects. Recovery observes/reconciles; it cannot allocate retries/trials or discharge quarantine by lease expiry. No additional policy store. |
| Error envelopes/observability: `raes/_errors.py`, `_model_diagnostics.py`, `raes_contracts/diagnostics.py`; trial compiler `CompilationFailure`; runtime `control_plane_api/{_responses,_operation_routes}.py`, `control_plane_audit.py`, `control_plane_health.py` | Reuse source-anchored errors, stable safe diagnostic codes, `portable_diagnostic_payload()`, redacted HTTP 422/500/conflict responses, module loggers and actor-bound audit. New validator prose must not echo sensitive input; bounding a message does not redact it. No new exception hierarchy or raw native exception/output in inspection, logs or refusal reasons. Progress, health, participant observations and archival experiment evidence retain distinct purposes. |
| Host/engine/deployment: existing backend drivers, ADR-113 adapters, package/tooling policy, `raes_contracts/corpus.py` | This representation adds no shell, listener, credential loader or execution service. Policy references are not executable paths. No tokens in argv or broad environment dumps/inheritance. Runtime workers are trusted; hostile guest workloads remain backend-contained. Engine replay/redelivery/Continue-As-New cannot renew effect permission, budgets or trial identity. Load packaged schemas/profiles through the corpus seam. |

## Publication and verification boundaries

Use ADR-009/061/078 publication and migration conventions. Schema authority is
`contracts/schemas/`; Python `schema_bundle()` must match it. The current v2
`contracts/schema-publication-manifest.json` routes the change ledger to
`contracts/schema-publication/entries/` and removals to `tombstones/`: do not add
obsolete inline manifest fields. Record contract-facing summaries/hashes,
respect each schema's stability/version rules, update supported-contract/profile
registration where needed, and publish semantic obligations through
`schema_invariants.py`. JSON Schema annotations do not execute those obligations.
Update affected SDL phase/plan schemas, fixtures, canonical language/formal
docs and author migration guidance together. Explain omission, inheritance,
accepted defaults and incompatibility; migration must never grant extra effect
permission. Follow `.ground-control.yaml`, `.gc/plan-rules.md` and the canonical
policy tooling; do not invent a requirement UID for this issue-only delivery.

Meaningful verification must show preservation from authored source through
composition, instantiation, compilation, native plan projection/reconstruction,
inspection and backend admission. Reuse `test_sdl_phase_contracts.py`,
`test_sdl_module_registry.py`, `test_sdl_catalog_parity.py`,
`test_plan_projection.py`, `test_plan_inspection_cli.py`, SCE-002 trial tests,
`test_sce_006_cleanup_contracts.py` and #1360 contract/rejection corpora.
Cover every accepted alternative and default, nested/sibling/definition-site
binding, scope-order independence, invalid combinations, missing trial authority,
unsupported continuation, capability/refusal mismatches and safe diagnostics.
Policy-only changes must affect commitments; stale/recovered artifacts must
retain their original policy. Contrast the same idempotent backend under allowed
and forbidden repetition, preserve cleanup failure separately, and prevent retry
multiplication across nested workflow/activity/transport layers. A contract test
cannot certify backend truth or executable recovery. Run explicit relevant
modules/cases and changed-file policy/schema checks locally; full, integration,
fuzz and completion suites belong to CI/CD.

## Non-goals and anti-patterns

This issue carries and admits requirements; it does not implement the distributed
engine, a checkpoint format, automatic recovery, a new trial allocator, backend
physical safety, a second scenario runtime or a new exception/logging stack.
Do not add metadata policy bags, independently editable copies of retry/cleanup
intent, duplicate per-transport validators or an engine retry DSL. Do not infer
author intent from durability, application labels, technical idempotency or
framework defaults. Do not equate operation, invocation, authored attempt,
trial/run and participant episode identities; termination in one plane cannot
silently terminate or restart another. Explicitly selected physical-OT constraints
remain contextual future capabilities, never universal authoring obligations or
implied safety certification.

## Implementation acceptance mapping

- [x] Issue: carry accepted representation through validation, composition,
  compilation and inspection, reusing existing constructs →
  `raes_contracts/execution_policy.py:27`,
  `raes/composition/_execution_policy.py:10`,
  `raes_processor/compiler/execution_policy.py:13`, and
  `tests/test_issue_1361_execution_policy.py:98` under
  `implementations/python/packages/` and `implementations/python/` respectively.
- [x] Issue: retain choices/defaults and reject unsupported/unwilling realizations →
  `raes_contracts/execution_policy.py:172`,
  `raes_processor/planner/execution_policy.py:9`,
  `raes_contracts/contracts/backend_operation_validation.py` and
  `tests/test_issue_1361_policy_admission.py:30`.
- [x] Issue: distinguish native operation/workflow retry units from trial/episode
  identity changes without mandatory experiment/participant/OT declarations →
  `raes_contracts/execution_policy.py:125`,
  `tests/test_issue_1361_execution_policy.py:194` and its intentional-fault/fresh-trial regression, and
  `specs/sdl/execution-recovery.md:43`.
- [x] Issue: verify alternatives, invalid combinations and incompatibility;
  publish schema/migration changes → the `tests/test_issue_1361_*policy*.py`
  modules, eleven affected `contracts/schemas/` carriers with matching
  `contracts/schema-publication/entries/` records, and
  `docs/explain/reference/execution-recovery-migration.md`.

There are no issue-scoped requirement UIDs or requirement lifecycle transitions.
Existing requirement links to the shared facade, native plan and SDL carriers
remain applicable: the retry and plan-operation classes retain their public
imports and incumbent semantics after extraction into dependency-neutral helpers.
Verification uses explicit relevant pytest modules and changed-file policy
checks; full suites remain CI responsibilities.

### Review repair verification

The published review decision is
https://github.com/OpenRAE/rae/issues/1361#issuecomment-5976887877.

- `core-F1`: preparation reconstruction forwards both native policy fields.
  Regression: `tests/test_issue_1361_policy_admission.py::test_preparation_admission_preserves_primary_and_scoped_policies`
  exercises executable preparation admission and checks the exact policy values at apply.
- `core-F2`: imported node feature/condition/inject policy pointers follow their
  renamed binding keys with RFC 6901 escaping. Regressions:
  `tests/test_issue_1361_policy_composition.py::test_imported_binding_policy_follows_its_renamed_key`
  and `::test_imported_binding_pointer_preserves_json_pointer_escaping`.
- `core-F3`: namespace-wide policies follow actual exported/private declaration
  renames. Regression:
  `tests/test_issue_1361_policy_composition.py::test_nested_module_policy_follows_mixed_exported_and_private_descendants`
  covers private-only and mixed visibility, inherited defaults and section overrides,
  and isolation from outer/root siblings.

The preparation admission and imported feature/inject/mixed-visibility tests
failed on the reviewed code before the repairs. The relevant policy, preparation
and module-registry modules then passed: 274 tests, 5 deselected. No full suite
was run locally.
