# Issue 275 EXP-719 Treatment And Controlled Variation Preflight

Date: 2026-10-25

Scope: EXP-719 and issue #275's cross-plane factorial generation, executable
allocation, dispatch, and reconstruction requirements. This is architecture
guidance, not an implementation plan or a claim of delivered behavior.

## Authority And Existing Gaps

ADR-055/068/074 already separate experiment design, archival studies/runs, and
live execution. ADR-084 owns selection, deterministic compilation, random
streams, and scheduler opacity; ADR-094 owns cross-plane binding. No additional
ADR or experiment root is needed. Normative changes belong in the existing
experiment-core and scenario-variation/trial-realization specifications and
published contracts; this note cannot override their current semantics.

The current implementation already supplies much of the vocabulary, but has
four consequential gaps:

- `contracts/experiment_study.py` in `raes_contracts` owns factors, conditions,
  and allocation. `factor_kind="treatment"` already represents treatment;
  `allocation_method`, `randomization_unit`, and `blocking_factors` do not
  execute randomization or blocking. Factor levels are names, not owner-bound
  configuration values. Study factor/level checks are stronger than the
  authoring model's checks; generation must not defer admission until analysis.
- `ExperimentProductSelectionPolicyModel` and
  `compile_coordinate_selections()` compose scenario-point selections.
  `trial_compiler/bindings.py::_entry_bindings()` matches descriptors through
  selected scenario outcomes. This does not generate the factor-level product
  across participant configuration and scenario configuration. In particular,
  participant descriptors must not be skipped or forced through a fictional
  SDL variation point.
- `trial_compiler/inputs.py::coordinates()`, the normative `trial-compiler-v1`
  profile, and `trial_coordinate_order.py::canonical_entry_order()` order by
  condition then replicate. `plan_batch_schedule()` uses that helper;
  `BatchExecutionReceiptModel.scheduling_policy_id` and
  `validate_batch_execution_receipt()` enforce the same fixed policy.
  Shuffling only the dispatcher would break receipt validation and replay.
- `ExperimentConditionAssignmentModel` requires refs or legacy parameters;
  allocation distinctness and `_run_satisfies_condition_assignment()` compare
  those criteria, not realized binding descriptors. Explicit binding mode
  rejects legacy parameters. Conditions distinguished only by typed bindings
  therefore need coherent admission and archival matching, not dummy refs or
  weakened distinctness checks.

## Design Boundaries

**One factor design across the existing planes.** Extend the existing
experiment authoring/allocation children with closed typed generation intent.
Explicitly name the participating factor ids and declared levels. Generate the
complete Cartesian set, including scenario and participant-implementation
factors, into the existing condition-assignment representation. A factor is a
scientific axis; a plane identifies configuration authority. One level may
bind multiple owner targets, including across planes, without becoming several
independent factors. Existing apparatus bindings retain their own authority.

Reuse `ExperimentBindingDescriptorModel` for owner target, strict scalar or
secret-reference value, validator identity, and factor/level/condition joins.
Any reusable level-binding declaration must reuse those value/target shapes
and have one authoritative relationship to generated descriptors. Do not copy
owner registries or scalar schemas into a second factorial DSL. Structural SDL
variation continues through `ExperimentSelectionOutcomeModel` and the owning
selection policies; scalar bindings do not become an arbitrary patch language.

Each generated condition has a stable portable identity derived under an exact
generation profile from canonical factor/level identities, independent of
input-map order or a display name. Different level assignments must remain
distinct after owner normalization; ambiguous or operationally identical
comparison conditions fail admission. Reject duplicate/empty executable level
sets, unknown levels, incomplete assignments, conflicting factor bindings,
alias collisions, and conflicting supplied/generated conditions before any
mutation. Fixed controls and nuisance/blocking variables do not automatically
become crossed treatment dimensions. Unsupported combinations fail the design;
silently filtering them would change the promised factorial design.

**One admitted allocation.** Allocation intent belongs to the existing
`ExperimentRunPlanModel`/`ExperimentRunAllocationPlanModel` lineage; its resolved
executable result belongs to `AdmittedTrialPlanModel` at plan scope. Record an
exact policy/version, participating domain and block membership, counts,
referenced stochastic controls, bounded draw provenance, and an ordered
allocation of every admitted entry exactly once. Validate a bijection between
allocation slots and entries, condition/replicate coverage, block constraints,
and ordinals. Preserve the order as meaningful data when serializing with JCS.
Neither entry-map ordering nor a free-text method is executable allocation.

Logical trial coordinates, run ids, dispatch slots, blocks, execution attempts,
and runtime participant turns remain distinct. Reordering the same trials must
not redefine their logical coordinates. The selected identity profile must
state which design changes affect entry/run identity; the complete plan digest
must commit to the allocation. Reuse the existing seal helpers and acyclic
digest chain, avoiding child references to an enclosing digest that includes
the child. Retries preserve the allocation slot and run identity; replacement
trials retain the existing bounded replacement policy and child lineage.

**Randomization is admission work.** Reuse
`ExperimentStochasticControlModel.executable_binding`, the accepted
`blake3-xof-v1` profile, `random_stream_engine`, and the governed
`condition-assignment` draw purpose. The current RNG profile exposes only
`bounded-integer`; a permutation needs an exact versioned allocation procedure
over that transform, including canonical pool, choice bounds, address
coordinates, rejection/exhaustion, and tie behavior. Do not assume a library
shuffle or an unpublished permutation transform. Preserve allocation-only
controls even though the compiler currently retains controls used by entry
draws.

Allocation draws precede final condition assignment and are plan-level facts.
Define stable pre-allocation slot/block addresses and an allocation concern
under the governed address/profile lineage. `StreamAddressModel` currently
names a variation point, and plan entry validation requires each entry draw's
coordinate to equal that entry's coordinate. Reuse these carriers only where
their meanings fit; version the owning address profile if necessary. Do not
invent an SDL point, derive a draw from the condition it is choosing, copy
plan-wide draws into every entry, or relax the entry-coordinate invariant.

Reconstruction requires the same admitted factor domain, counts, blocks,
allocation procedure, control/entropy identity, namespace, and exact profile
versions. A seed alone is insufficient. Host, worker, wall time, completion
order, retry count, and aggregate spec/plan digest are forbidden draw inputs.
Unavailable governed entropy fails closed; it never triggers a fresh seed.

**Dispatch consumes the recorded order.** Evolve the shared contract-owned
order helper used by `trial_scheduler.py` and `batch_execution.py`; both must
validate the same admitted allocation and scheduling-policy identity. Keep
`trial-coordinate-canonical-v1` semantics for existing plans. New allocation
or block semantics need explicit supported profile/policy identities, with
unknown versions rejected. Do not silently reinterpret `trial-compiler-v1`,
derive block membership from descriptive strings, or change the legacy
canonical sort key. Update its normative profile and closed profile literals
alongside the new behavior.

A serialized coordinator commits dispatch decisions in recorded order before
delegating work. Resume consumes the existing execution receipts and retains
the remaining slots; it does not reshuffle. Isolation proofs, live leases,
parallelism ceilings, attempt deadlines, cancellation, and cleanup remain the
existing scheduler/realization responsibilities. Randomization grants no
additional concurrency or resource authority.

Randomized allocation, or blocked allocation with explicit within/between-block
ordering, must avoid systematic condition-first dispatch. A blocked policy
must specify counts, membership, and treatment ordering within each block;
merely grouping all of one condition together does not address drift. Pin
participant/model configuration and manifests where the owner supports it;
preserve actual apparatus context, observed setup evidence, clocks, and
deviations for API/model revision, host load/state, cache/carryover, and
cleanup failures. Random order mitigates confounding; it cannot guarantee an
external API or host is unchanged. Undisclosed drift cannot support a claim of
controlled equivalence. Runtime availability never authorizes reselection.

## Cross-Cutting Gates And Canonical Incumbents

Paths below are under `implementations/python/packages/` unless stated otherwise.

| Layer | Required reuse and admission rule |
| --- | --- |
| Authoring ingress | `raes_contracts/experiment_spec.py::parse_experiment_spec()` owns the 64 KiB bound, safe YAML, duplicate-key/alias rejection, finite JSON, and sanitized contract errors. MCP `tools/experiment_authoring.py` delegates to it. Keep new forms flat and bounded; do not add a permissive alternate loader or echo rejected payloads. |
| Contract/config shape | `ContractModel(extra="forbid")`, strict binding scalar types, portable ids, keyed identity maps, discriminated unions, and published semantic invariants own structure. New executable counts reject Boolean, fractional, and string coercion. Validate factor/level coverage, uniqueness, and key/id equality in authoring and study through shared semantic helpers, preserving legacy descriptive compatibility. |
| Expansion/resource limits | Reuse `TrialCompilationLimitsModel`, selection output bounds, and `CompilationFailure`/`TrialCompilationResult`. Bound factor/level counts, Cartesian conditions, block/replicate multiplication, total bindings/draws, address work, diagnostics, and serialized bytes before expensive expansion. Reject overflow/limit exhaustion atomically; no partial plan. |
| Scenario authority | `ExpandedScenario`, `ExpandedScenarioBindingTargetResolver`, `validate_experiment_selection_against_family()`, `instantiate_scenario()`, and `admit_instantiated_scenario()` retain SDL parsing, composition/trust, target/domain/satisfiability, and post-instantiation checks. Generation cannot bypass family membership or backend realization-envelope admission. |
| Participant/apparatus authority | `validate_experiment_binding_targets()` resolves only the declared plane/owner. Reuse selected manifest identity/version/digest checks, kind-specific allowlists, `configuration_registry`, `realize_participant_configuration()`, its trusted complete-configuration validator, and `validate_participant_configuration_selection()`. Apply declared defaults atomically; reject canonical/alias collisions before constructing maps. Preserve realized values, origin, and configuration digest. Capability declarations alone do not prove owner validation or realization. |
| Stochastic admission | `random_stream_profiles`, `StreamAddressModel`, `RandomStreamDrawRecordModel`, and the controlled vocabulary/profile corpus own exact support, addresses, transforms, collision checks, and bounded provenance. A valid profile string is insufficient unless selected apparatus supports it; selection draws and allocation draws retain separate scopes. |
| Plan ingress/integrity | `json_ingress.py::parse_bounded_json_object()`, `parse_admitted_trial_plan_json()`, and `revalidate_admitted_trial_plan()` retain byte/depth/duplicate-member/non-finite checks and complete reconstruction. Extend plan-local joins and seals for allocation coverage and profile/control agreement; self-consistent hashes prove integrity, not authorization or scientific validity. |
| Secrets and environment | `SecretReferenceBindingValueModel`, `SecretReferenceId`, and governed entropy refs carry only non-sensitive identities. No resolved credentials, hidden answers, secret entropy, sensitive locators, or hashes of low-entropy secrets enter levels, labels, portable draw inputs, plan digests, provenance, fixtures, errors, or logs. Owner configuration is not an environment-variable binding: no new env map, file lookup, provider lookup, or secret resolver. Existing authorized sinks alone may resolve references. |
| Host/process boundary | The pure compiler and scheduler need no subprocess, network, filesystem side effects, or environment lookup. `realize_admitted_trial_entry()` remains the backend handoff. Factor data must never choose a command, module, plugin, path, shell fragment, or process environment. Any existing trusted adapter invocation keeps fixed argv, no shell interpolation, protected credential channels, bounded output/timeouts, and redacted errors; tokens and sensitive values never enter argv. |
| Authentication/authorization | Offline design adds no listener or controller. Execution stays on `RuntimeControlPlane` and `ControlPlaneSecurityConfig.strict_defaults()`, `_auth.py` target-bound identities and declared route authorities, request-size middleware, sealed route table, no-store responses, request fingerprints/idempotency, and `AuditEvent`. Administrative transport admission, participant information-flow/action policy, owner target admission, and secret access are separate gates; allocation grants none of them. |
| Errors/observability | Reuse `ExperimentSpecValidationError`, `AdmittedTrialPlanIngressError`, bounded `Diagnostic`/`DiagnosticModel`, compiler failure envelopes, and existing HTTP 4xx/ redacted `{"detail":"internal server error"}` behavior. Report safe codes, bounded addresses, policy/profile ids, digests, counts, stages, and dispositions. No raw Pydantic inputs, validator messages containing values, backend exception strings, prompts, full configuration, or tracebacks in public errors/audit/logs. No new exception hierarchy or telemetry pipeline. |
| Persistence/archival joins | Reuse sealed plans, `BatchExecutionReceiptModel`, cleanup receipts, `TrialRunProvenanceModel`, `RealizedBindingProvenanceModel`, `ExperimentRunModel`, and `ExperimentStudyModel`. Extend `_run_satisfies_condition_assignment()` and the existing task/run/study and admitted-plan reconciliation validators to prove intended versus realized conditions across both planes. Preserve evidence proof requirements, ambiguity rejection, eligible-run counts, stochastic consistency, invalidation and replacement rules. `ControlPlaneStore` remains live state; it cannot substitute for sealed allocation or archival evidence. No allocation database/cache/store. |

## Publication, Extensibility, And Evidence

The extension seam is an exact allocation/generation profile plus typed policy
parameters: participating factor ids/level bindings, replication counts,
explicit block membership/order, and an existing stochastic-control reference.
Adding a factor, level, participant target, or block should be data behind that
seam, without editing the canonical dispatcher or adding an owner-specific
field. A new allocation algorithm or coordinate meaning adds supported profile
semantics and vectors; it is not a free-form policy string, callable, generic
expression evaluator, or dynamic plugin. Owner target/validator extensions
remain the ADR-094 registry seam; a new authority plane is a contract change.

Published schemas under `contracts/schemas/` are authority (ADR-009/019/061).
Affected surfaces include authoring input, study, binding descriptors where
their meaning changes, admitted plan, batch receipt, and any affected random
address/profile carrier. Reuse `schema_bundle()`, conformance registration and
semantic routing, fixtures, and public exports. Record schema hashes and
`last_change` in `contracts/schema-publication/entries/`; the current v2
`schema-publication-manifest.json` points to that directory. Draft schema
status does not authorize silently changing an accepted execution profile.

Reuse the tests for experiment authoring/bindings/selection, admitted plans,
`test_sce_002_trial_compiler.py`, `test_sce_006_batch_scheduler.py`, trial
realization/analysis, random-stream vectors, and bounded JSON ingress.
Required evidence covers a true two-plane product; complete per-condition
owner realization; same-input allocation reconstruction after serialization
and across worker/partition order; block/count/permutation integrity; dispatch
and receipt agreement; tampered or unsupported allocation rejection; legacy
plan compatibility; safe error/secret handling; and pre-expansion limits.
Assert semantic properties and pinned vectors, not that random order happens
to differ for every seed or eliminates statistical drift.

Workflow stays with `.ground-control.yaml`, `.gc/plan-rules.md`,
`.pre-commit-config.yaml`, and `noxfile.py`. Canonical gates include
`tools/check_repo_policy.py`, `tools/check_schema_publication.py`,
`tools/check_generated_schemas.py`, `tools/check_authority_boundary.py`,
`tools/check_concept_authority_governance.py`,
`tools/check_contract_requirement_tracing.py`, `tools/check_semantic_coverage.py`,
and `tools/check_specification_coverage.py`.
Use `RAES_REQUIREMENT_UID=EXP-719` and targeted local checks/tests; full,
integration, fuzz, and completion suites remain CI/CD work. Keep traceability
aligned with every affected authority; the supplied binding-schema link alone
does not evidence allocation or dispatch.

## Non-Goals And Anti-Patterns

This preflight changes no code, contracts, accepted profiles, requirement
status, or runtime behavior. EXP-719 implementation spans authoring through
allocation admission, dispatch, and archival joins; a schema-only or
scenario-only product does not satisfy issue #275.

Do not introduce a treatment service/schema, second experiment DSL, target
registry, SDL binder, RNG, scheduler, persistence layer, error hierarchy, or
audit stream. Do not reinterpret red-agent variants, participant turn order,
SDL order variation, runtime `Condition`/preconditions, adaptive difficulty,
or per-run random values as experiment condition allocation. Existing adaptive
treatment disclosures and classification remain mandatory when applicable.

Fractional/optimal designs, adaptive reallocation, statistical analysis or
scoring engines, new HTTP/CLI/MCP execution endpoints, provider construction,
secret resolution, live host allocation, and external hosting/transfers are
outside this change. Generic configuration injection, outcome-based
resampling, silent pruning, runtime condition substitution, mutable archival
records, and undocumented replay/equivalence claims are prohibited shortcuts.
