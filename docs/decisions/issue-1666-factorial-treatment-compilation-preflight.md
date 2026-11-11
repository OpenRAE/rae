# Issue 1666: Factorial treatment compilation preflight

Date: 2026-10-28. EXP-719 is the requirement; issue #1666 defines this
delivery boundary. This note sets architecture guardrails, not an
implementation plan or a claim of delivered support.

## Decision and existing authority

Implement the already published `factorial-treatments-v1` contract through the
existing trial lifecycle. [ADR-084](adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md)
owns selection, atomic admission, identities and replay;
[ADR-094](adrs/adr-094-authoritative-cross-plane-experiment-bindings.md) owns
scalar targets and complete participant configuration. No new ADR, treatment
engine, root schema, configuration archive or workflow is needed. The
[#1665 design](issue-1665-factorial-typed-selections-design.md) and
[normative profile](../../specs/formal/experiment-core/README.md#typed-factorial-treatments-factorial-treatments-v1)
already specify syntax, bounds and source joins. Keep their distinction between
contract publication and executable support until this issue supplies evidence.

Compiler support must carry the profile, complete effects and exact source
records through `trial_compiler/inputs.py`, `policies.py`, `bindings.py`,
`compiler.py` and `profiles.py`. Relaxing profile rejection cannot establish
support. The draft comparison and readmission modules in this checkout must
remain parts of this lifecycle, with the same owners and failure contracts.

Package paths below start at `implementations/python/packages/`.

## Treatment composition and equality

Reuse `contracts/experiment_factorial.py` and `experiment_factorial_treatments.py`
in `raes_contracts` for bounded Cartesian materialization and repetitions.
The compiler consumes their generated allocation and criteria; it must not
maintain another product generator or derive effects from factor labels.
Reuse the existing binding templates, selection outcome union,
`ExperimentScenarioSelectionDescriptorModel` and `AdmittedSelectionRecordModel.treatment`.
A structural member stays a typed member; its payload remains in SDL.
Model settings belong to each selected participant's manifest registry. Prompt
choices use its pinned `control_context` domain, not free text or an apparatus
parameter. Multiple participants have independent addresses and registries.
No model, prompt, factor, level, member or node name is reserved by the compiler.

Within each coordinate, combine scalar scenario outcomes, typed selections and
invariant fixed policies before whole-scenario admission. A fixed policy has
`purpose: fixed-configuration`, `output_bound: 1`, no binding claims and no
fabricated factor provenance. Selection-only designs have no descriptor set;
participant-only designs need no invented SDL points. Keep `explicit-required`.
Manual typed criteria without the supported factorial profile still fail closed.
Every actual family point must be covered exactly once. Duplicate points fail
even when equal; different points retain SDL's existing agreement rules for
their resolved writes. Do not confuse those two checks.

Typed target admission belongs beside the existing SDL target resolver in
`raes/selected_scenario.py`. Reuse `_canonical_target_id()`, the declaration
index and the governed SDL owner; expose the needed narrow SDL-owned operation
instead of importing private helpers into the processor. Check family id and
digest, point, canonical target, owner and outcome together, including when
there are no ordinary policies. An early return in
`validate_experiment_selection_against_family()` must not skip that case.
Do not weaken `ExpandedScenarioBindingTargetResolver`'s scalar rejection to
make structural targets look like strings. Owner names never load executable
validators; trusted validators come from existing supplied maps.
Their normalization must be deterministic for the pinned owner version and
selected scenario so independent recompilation agrees. They must not acquire
secrets, fetch assets, inspect process environment or mutate shared inputs.

`select_scenario_family()` remains the single writer and admission path.
It resolves choices against the unchanged composed family, checks domains,
requires/excludes and write conflicts, reconciles surviving provenance, and
instantiates and semantically validates the complete result. Reuse
`selected_structure.py` and `_selection_provenance.py`: node absence removes
the node and its same-key infrastructure, but does not repair incoming links.
Unequal coupled/separate inventory writes fail; equal writes may agree.
Absence conflicts with descendant writes. Qualified names must resolve through
the declaration index, never dot splitting. Revalidate participant scope,
control-context applicability, realization envelopes, tool support and capture
demands on that selected scenario. One invalid requested coordinate rejects the
entire design, with deterministic bounded diagnostics and no partial plan.

Extend the existing distinctness gate with a documented projection of resolved
effects for the new profile. Compare the admitted scenario's effective content,
complete normalized participant values including defaults, and any other
admitted scalar plane effects. Every selected participant configured anywhere
in the design needs its complete result in every condition. Do not silently
drop an affected participant when a structural choice invalidates its scope.

Neither descriptor `realization_payload()` nor a snapshot/configuration digest
alone proves different effects. The former still contains member/owner/pin
identity; the latter can differ solely through provenance. Exclude source,
condition, member and policy labels, default/override origin, authoring hashes
and trial lineage as evidence of a difference. Compare prompt effects through
the resolved pinned content and operative slot/scope, rather than treating a
declaration spelling or provenance-only descriptor digest as a new prompt.
No content fetch or model execution is needed or authorized for comparison.
Opaque secret references establish reference identity, not secret equivalence.

Do not blindly discard all `instantiation_provenance`: capability bounds,
parameter derivations and realization constraints/designations there feed
`raes_processor/compiler/realization_*` and provisioning. Preserve their
operative meaning while excluding provenance-only differences. Use existing
JCS helpers and one comparison gate, not a second effect identity or behavioral
equivalence framework. Do not sort semantically ordered inventory or outcomes.
Keep the old scalar profile's bytes, identity vectors and behavior intact.

## Cross-cutting boundaries

These layers are cumulative. Shape acceptance never replaces owner admission,
whole-scenario validation, provenance matching or runtime permission.

| Layer and canonical incumbent | Required guardrail |
| --- | --- |
| Input parsing: `raes_contracts/experiment_spec.py`, `json_ingress.py`; `raes_cli/_semantic_portable.py`; SDL `parser.py` and composition | Preserve the 64 KiB experiment input limit, safe YAML with duplicate/alias rejection, string-key and finite-number checks, bounded duplicate-rejecting JSON, and SDL source/import limits, locks, visibility and digests. Use already acquired trusted artifacts; selection introduces no fetch, path discovery or import bypass. |
| Shapes and contextual joins: `raes_contracts/_base.py::ContractModel`, `contracts/experiment_spec.py`, `experiment_study.py`, `experiment_treatments.py` | Keep closed fields, strict scalar types, finite values, discriminated outcomes and exact factor/level/condition relationships. Boolean and numeric equality must stay distinct. Closed models and frozen request wrappers do not freeze nested contents: reconstruct caller-held models from payloads at public admission boundaries. Reuse materialization agreement checks on direct model validation as well as loaders; no loader-only invariant or parallel DTO. |
| Work and resource bounds: `experiment_factorial_treatments.py`, `contracts/trial_compilation.py::TrialCompilationLimitsModel` | Retain the combined 10000 work-unit limit across logical runs, including fixed choices and nested subset/order members, and the 8 MiB expanded authoring limit with a check before expansion. Preserve coordinate/product/domain, entry binding, diagnostic and 32 MiB plan limits. Bound typed entry/archive collections too; a scalar-only cap cannot cover structural work. Check counts before allocation and actual bytes before return. |
| SDL selection and semantic admission: `selected_scenario.py`, `selected_structure.py`, `instantiate.py`, `validator/` | Use canonical owner/slot/domain checks and fresh-payload whole-scenario validation. Preserve reference, dependency, scope, runtime inventory and realization constraints. Neither an author-set validation flag nor validating individual nodes establishes admission. |
| Manifest ownership and configuration: `raes_contracts/experiment_bindings.py`, `participant_configuration.py`; compiler `apparatus.py`, `bindings.py` | Resolve exact selected manifests and digests, canonical aliases, owner/type/sensitivity/value-kind declarations and complete defaults. Reject equal duplicate canonical writes. Preserve normalization's owner, type, target-set, origin, secret-reference and control-context invariants; seal the complete result once. |
| Prompt/control context: `raes/participant_control_context.py::SDLControlContextConfigurationValidator`, both contract control-context modules, `uri_safety.py` | Bind validation with `for_scenario()` to the selected concrete scenario. Check participant/role scope and exact ACT-620 asset id/version/descriptor digest and content checksum. Keep safe absolute URI checks rejecting credentials and secret query fields. Locators remain inert; selection does not prove authorized disclosure or delivery. |
| Secret and environment shapes: `raes_contracts/secret_references.py`, `contracts/experiment_bindings.py`; SDL `runtime_environment.py`, `runtime_generated_value.py`, `runtime_values.py`, `_stateful_resource_references.py` | Participant secret targets carry only opaque non-sensitive secret ids. Never acquire secrets or include resolved secret bytes in artifacts, hashes, fixtures, errors or logs. SDL runtime facts retain their explicit classification rules; `name_indicates_secret()` is advisory. Retained inventory still obeys redaction, literal versus generated-source exclusivity, consumable output rules and `producer_private` rejection. Env-file names remain logical identities. Structural environment treatments grant no arbitrary env/package/filesystem patch permission. |
| Processor and planner handoff: `raes_processor/compiler/stateful_resources.py`, `planner/stateful_admission.py`, `compiler/execution_policy.py`, `planner/execution_policy.py` | Derive generated-value consumer projections from the selected node's existing bindings; carry output references, never bytes. Planner admission must still match the exact node, environment target and output, and retain execution-policy checks. Do not rebuild these projections inside the factorial compiler or turn a logical env-file name into a host path. |
| Integrity and persistence: `contracts/admitted_trial_plan.py`, `admitted_trial_plan_components.py`, `admitted_trial_plan_ingress.py`; `raes/phase_contracts.py`; `raes_processor/trial_realization.py` | Reuse acyclic JCS seals, exact input refs, bounded JSON reload, full nested reconstruction and existing snapshot provenance. Keep optional legacy fields absent. Plans/configuration results/snapshots/runs are the carriers; no new database, store, URI scheme or `ControlPlaneStore` archive. |
| Failures and observability: loader `_safe_validation_details()`, `raes/_errors.py`, `CompilationFailure`, `TrialCompilationResult`, `AdmittedTrialPlanIngressError`, `raes_contracts/diagnostics.py`, CLI/MCP adapters | Preserve existing bounded value-free error envelopes and stable codes. Use `DiagnosticModel` and `portable_diagnostic_payload()` at portable boundaries: pointer escaping and field lengths still apply to internal `Diagnostic` values. Do not serialize raw Pydantic input/context, owner exception text, chained causes, payloads or private locators. Treat authored identifiers and diagnostic addresses as untrusted. Reuse current logging; operational logs, experiment evidence and participant-visible disclosures remain separate under ADR-066. No new exception or audit hierarchy. |
| Authentication and host exposure: `raes_runtime/control_plane_api/_auth.py`, `_operation_routes.py`, `control_plane_security.py`; existing planner/runtime sinks | This pure compilation/realization change adds no endpoint, credential, env lookup, subprocess or network call. A seal grants no dispatch authority. Later execution retains target-bound principals/roles, participant bindings, planner authorization, bounded requests, redacted errors, audit and no-store responses. Never turn identifiers/outcomes into shell text, host paths, bearer tokens in argv, or exported secrets. Keep owner-private command commitments separate from portable plan digests. |

## Reload, replay and archive claims

Emit `profiles.treatment_profile` consistently in plan intent and sealed output;
keep the existing designed compiler, coordinate and identity profiles. Do not
forge a selection policy or a random draw to represent a factorial effect.
Invariant fixed selections keep their real policy origin. All ordering and
repetitions reuse `trial_compiler/inputs.py`, `profiles.py` and canonical
coordinate ordering. `contracts/experiment_allocation.py` already owns bounded
Fisher-Yates draws and `_validate_allocation()` independently reconstructs them.
Do not replace it with sampling, shuffle traversal, or post-admission filtering.

Preserve the exact descriptor and source joins in each admitted typed selection.
`instantiate_admitted_trial_entry()` already carries complete selection records
through `AdmittedSelectionProvenance`; keep that public seam and recheck typed
owner/target/outcome agreement against its supplied family. The full realizer
checks pinned experiment/task/capture/apparatus inputs and returns the sealed
participant configurations. It must not rerun owner normalization at dispatch.

Distinguish self-consistent reload from source-aware admission.
`validate_plan_treatments()` must check claimed typed records even when their
descriptors have been removed; a profile tag alone proves neither coverage nor
that a treatment was not deleted.
Enforce all plan-local joins during nested reconstruction. Where the pinned
authoring input is supplied, verify the complete expected coordinate, binding,
treatment and fixed-selection sets against it, including absence and addition.
Use the same owner rules for fresh compilation and independent readmission.
A freshly resealed, internally consistent rewrite cannot authenticate its own
original intent: source-aware checks need the trusted expected pins and original
artifacts. Do not promise that a self-digest or plan-only API supplies them.

Reuse `contracts/experiment_conditions.py` for study matching and
`contracts/trial_analysis.py::validate_admitted_trial_run()` for plan-aware
archive checks. The latter already requires the exact admitted typed descriptor
set and participant configuration identities; the former requires every typed
criterion including source joins. Preserve those different matching contracts.
Equal effective treatments do not excuse wrong provenance. Keep snapshot,
plan/entry/run, processor-plan, allocation-control, attempt and cleanup joins.
Matching recorded claims does not prove model execution, prompt delivery or
observed environment state.

## Extension, evidence and delivery boundaries

The extension seam is the canonical SDL owner/slot/outcome operation, parameterized
by declared targets, together with the existing participant manifest registry and
validator id/version map. A further reviewed inventory slot or participant setting
must not require new factorial syntax, archive DTOs or name-specific compiler
branches. `variation_structure.py` and the
[SDL slot table](../../specs/sdl/variation-points.md#4-typed-target-slots) own write
permission; runtime-family registration alone does not authorize a slot.
New authority planes require contract and ADR review under ADR-094. New
allocation algorithms require their own accepted profile; neither extension
belongs in a name-based treatment dispatcher.

Required evidence crosses independently configured participants' model and pinned
prompt choices with structural environment choices and repetitions. Include
unrelated author-chosen names, coupled presence/inventory, fixed points,
selection-only and participant-only forms, effective duplicates after defaults
and provenance changes, all invalid joins/conflicts/references, safe failures,
canonical reload, source-aware reconstruction, traversal independence, allocation
replay and resealed omission/substitution. Reuse `test_exp_719_factorial_*`,
`test_exp_719_review_regressions.py`, `test_issue_1665_*`,
`test_issue_1625_structural_variation.py`, `test_issue_1626_trial_participant_bindings.py`,
`test_dsl_118_trial_control_context.py` and existing SCE-002 plan/realization tests.
Contract-only member tests are not compiler lifecycle evidence.

Update support statements in the two existing formal references and binding
guide, and provide a public example using the public loader/compiler/one-entry
interfaces. Explain supported forms, invariant fixed points and atomic refusal
of invalid combinations. Keep internal decisions outside `docs/public`; its
curated documentation boundary is enforced by `tools/check_public_docs.py`.
If an actual contract change is necessary, ADR-009/061 require normative schema
updates for every embedding root, bundle parity, contextual invariants,
fixtures and publication entries. Reuse `schema_bundle()`,
`tools/generate_contract_schemas.py`, `tools/check_generated_schemas.py` and
`tools/check_schema_publication.py`; do not republish unchanged contracts just
to enable existing shapes.
The v2 publication manifest points to `contracts/schema-publication/entries/`
and `tombstones/`; use those existing per-contract records for actual changes.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml`,
ADR-015 package direction/size limits and existing policy tooling. Set
`RAES_REQUIREMENT_UID=EXP-719` when the branch lacks that UID. Local
checks are targeted; full test, integration, fuzz and completion suites belong
to CI/CD. Normal release uses `release-please-config.json`,
`.github/workflows/release-please.yml`, the exact-commit canonical verifier and
the corpus-bundled distribution checks documented in
[releasing](../explain/releasing.md). The eventual consumer-visible change needs
a releasable Conventional Commit title. Do not hand-edit versions/changelogs or
ask downstream users to adopt an unreleased checkout.
ADR-115 keeps concrete backend distributions outside this repository; portable
support and package verification must not import a concrete backend, contact
a daemon or restore a backend implementation to supply this example.

Non-goals are a shared experiment runtime or record producer (#1629/#1630),
concrete model execution, live environment observation, prompt delivery,
secret resolution, runtime mutation, mixed-backend execution coordination,
apparatus configuration execution, new allocation algorithms, provisioning
features, hosting or persistence migrations. Do not add a patch language,
second SDL binder, generic effect/plugin dispatcher, example-specific registry,
duplicate schema/validator/exception hierarchy, or a second release workflow.
