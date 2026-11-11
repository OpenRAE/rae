# Issue 1665: Factorial typed scenario selections preflight

Date: 2026-10-27. The supplied issue is the authoritative contract; no formal
requirement is attached. This note defines architecture guardrails, not syntax,
an implementation plan, or delivered support.

## Ownership and compatibility

[ADR-084](adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md)
owns scenario selection, atomic trial admission, identities and archival joins.
[ADR-094](adrs/adr-094-authoritative-cross-plane-experiment-bindings.md) owns
scalar bindings and complete participant configuration. Compose these existing
authorities within the experiment authoring/allocation lineage. No new ADR,
experiment root, configuration registry or general effect engine is needed.

A level may contribute scalar bindings, typed scenario selections, or both.
Reuse `ExperimentFactorLevelBindingModel` for bindings and
`ExperimentSelectionOutcomeModel` for selection values. Structural alternatives
use `kind: member` with the declared member id, including a node-presence member
with coupled inventory. The family owns the alternative's payload. A treatment
does not copy a node or inventory definition into the experiment.

Keep the scalar `BindingValue`, `BindingScalarType`, descriptor and participant
configuration meanings intact. A member id is not a scalar configuration value.
Carry typed treatment provenance through the existing selection contract
lineage alongside bindings. Reuse `BindingOwnerModel` and SDL target identities;
share the source/target/outcome shape between condition criteria, admitted
records and archive matching rather than inventing different DTOs at each hop.
Do not generalize the scalar descriptor to accept arbitrary objects or put
structural outcomes through `value_type: string`.

The current `AdmittedSelectionRecordModel` has policy/point/outcome fields but
no source factor, level, condition or owner. The scalar-only
`RealizedBindingProvenanceModel` cannot fill that gap. The extension must retain
and validate exact factor, level, condition, family, point, canonical target
and governed owner joins through admission, serialization and archival matching.
An opaque annotation or a family pin alone is insufficient. A wrong source join
must fail even when the selected member or effective configuration is equal.
Existing scalar matching semantics remain unchanged.

Publish a new named factorial profile alongside `factorial-bindings-v1`.
Keep old scalar serialization, materialization, condition/binding identities
and profile vectors unchanged. New behavior needs explicit profile admission;
changing a draft schema does not authorize reinterpreting an existing profile.
Preserve condition identity as the canonical declared factor-to-level map;
selection content belongs in the existing design/entry/plan commitments.
Any new effect identity needs a documented collision-free canonical projection,
without changing the old scalar binding identity formula. Family, snapshot,
condition, configuration, entry, run and execution-attempt identities remain
distinct. Follow ADR-059 if a later design actually changes accepted ADR meaning.

## Coverage, conflicts and effective treatments

Every crossed factor and level is author-declared. No model, prompt, node,
environment, participant address or factor name has special meaning. One level
may affect several owners; effect count does not create extra factors. Every
executable level must contribute an effect across the supported kinds.
Selection-only and participant-only designs must work without dummy scalar
descriptors, legacy parameters, invented refs or fabricated SDL points.
The current condition nonemptiness and `explicit-required` descriptor-coverage
checks must accommodate typed selection criteria explicitly under the new
contract, rather than switching the design to `descriptive`.

For every generated coordinate, factor effects plus declared fixed selections
must cover every family point exactly once. Reuse fixed selection policies
with `purpose: fixed-configuration` and `output_bound: 1` for invariant points;
they apply equally to all conditions and have no fabricated factor provenance.
Reject overlap with a factor-selected point, duplicate point selections even
when equal, missing points, unknown points and competing source claims.
Do not implicitly select the first member or infer a fixed choice from an
unselected family. The smallest extension does not admit sample, enumerate,
stratified or product policies alongside factorial generation. Fixed policies
must not smuggle in unrelated binding-descriptor claims.

Every selected participant configured anywhere in the design needs its complete
effective configuration in each condition, including levels with no override.
Recheck its applicability against each selected scenario; removing a node must
not silently drop an affected participant or its configuration obligations.

Canonicalize owner targets before checking binding collisions; equal duplicates
also fail under ADR-094. Point coverage and effective write conflicts are
different checks. Preserve SDL's existing agreement rules for writes from
different points: coupled and separate inventory writes may agree; unequal
writes fail. Node absence conflicts with a descendant write. Resolve all writes
against the unchanged composed family, independent of order and point labels.
Do not reject or accept overlap by splitting qualified names on dots.

Point/domain validity is insufficient. Requires/excludes, surviving references,
participant applicability and the whole selected scenario must remain valid.
Absence removes the node and its same-key infrastructure entry; it does not
repair incoming references. One invalid Cartesian combination rejects the
entire factorial design. Never omit, resample, rename or relabel a condition to
make the remainder admissible.

Check distinctness after authoritative selection and complete participant
normalization, including defaults. Compare effective scenario content/writes
and participant values, excluding source labels, member labels, policy ids,
default/override origin and plan/run provenance as evidence of a difference.
Keep typed member identity in provenance even when comparing effective effects.
Two valid selections can leave the same scenario, for example inventory choices
that retain the same records. Different provenance must not disguise identical
treatments. Reuse the existing distinctness gate and canonical helpers rather
than adding a second competing signature algorithm.

Preserve pre-expansion limits on dimensions, levels, conditions, logical runs
and binding work. Bound total work across both effect kinds, fixed selections
repeated over coordinates and nested outcome members; separate per-kind caps
must not multiply the existing allowance. Preserve `TrialCompilationLimitsModel`
entry, domain, plan-byte and diagnostic bounds. Count before allocating products;
strict integers and checked multiplication must fail before expansion. Compact
input and supplied materializations must agree exactly; neither overrides the
other. Bound the expanded serialized representation as well as author input.

## Cross-cutting admission and security layers

Package paths below start at `implementations/python/packages/`.

| Layer and canonical incumbent | Required treatment |
| --- | --- |
| Experiment ingress: `raes_contracts/experiment_spec.py`, `json_ingress.py`; `raes_cli/_semantic_portable.py` | Keep the 64 KiB experiment loader bound, safe YAML, duplicate-key/alias rejection, mapping/string-key checks and finite numbers. Portable JSON retains bounded, duplicate-rejecting parsing. Direct contract validation must enforce the same in-document relationships. No new parser or loader-only checks. |
| Contract shape and source joins: `raes_contracts/_base.py::ContractModel`, `contracts/experiment_factorial.py`, `experiment_spec.py`, `experiment_study.py`, `experiment_selection.py` | Keep closed fields, discriminated outcome kinds, exact scalar types and factor/level/allocation membership. Share parent-level relationship checks where the full context exists. Never use `Any`, encoded JSON strings, coercion or display names as authority. |
| SDL trust and ownership: `raes/parser.py`, `composition/`, `_declarations.py`, `_reference_targetability.py`, `selected_scenario.py` | Complete trusted composition and preserve import locks/digests, visibility and namespace rewriting. Extend the SDL-owned typed target-resolution seam using its canonical owner/target logic; keep `ExpandedScenarioBindingTargetResolver`'s scalar rejection meaningful. Validate family, point, target and owner together, including when no ordinary selection policies exist. No selection-time fetches, imports or validator loading from document names. |
| Typed choice and scenario admission: `raes/experiment_selection.py::validate_selection_outcome()`, `selected_scenario.py::select_scenario_family()`, `selected_structure.py`, `instantiate.py`, `validator/` | Reuse outcome/domain validation, requires/excludes, conflict checks, fresh-payload construction, provenance reconciliation and whole-scenario semantic admission. Recheck references, participant scope, runtime dependencies and realization constraints after joint choices. Neither local node validation nor an author-set admission flag proves this. |
| Participant configuration: `raes_contracts/experiment_bindings.py::validate_experiment_binding_targets()`, `participant_configuration.py`; `raes_processor/trial_compiler/apparatus.py`, `bindings.py` | Resolve the exact selected manifest, aliases, owner, type, sensitivity and allowed value kind. Realize complete defaults/overrides atomically with the trusted validator map. Preserve normalization invariants and the complete result in the sealed entry; do not recompute configuration at dispatch. |
| Control-context assets: `raes/participant_control_context.py::SDLControlContextConfigurationValidator`, `raes_contracts/contracts/participant_control_context.py`, `raes_contracts/participant_control_context.py`, `uri_safety.py` | For instruction/prompt configuration reuse the manifest's exact `control_context` domain and `for_scenario()` validation against the selected concrete scenario. Preserve the ACT-620 id/version/descriptor-digest pin and its transitive content checksum. Keep safe absolute URI checks, including credential userinfo and secret-query rejection, without dereferencing locators. A locator alone is insufficient. Static selection does not prove live lifecycle, disclosure, delivery or permission. |
| Secrets and environment: `raes_contracts/secret_references.py`, `contracts/experiment_bindings.py`; `raes/runtime_environment.py`, `runtime_generated_value.py`, `runtime_values.py` | Portable secret references retain only their non-sensitive identity. No resolved secret enters payloads, digests, factors, diagnostics or telemetry. Retained SDL records still enforce classification, literal/generated-source exclusivity, consumable outputs and rejection of `producer_private` outputs. Env-file names remain portable identities, not paths. Selecting inventory cannot bypass these validators. |
| Integrity, persistence and archive: `raes_contracts/contracts/admitted_trial_plan.py`, `admitted_trial_plan_components.py`, `admitted_trial_plan_ingress.py`, `experiment_conditions.py`, `trial_analysis.py`; `raes_processor/trial_realization.py` | Reuse seals, JCS digests, pinned input refs, full JSON reconstruction and `revalidate_admitted_trial_plan()`. Extend existing condition matching and `validate_admitted_trial_run()` for typed provenance without losing joins or participant digests. Tampering with valid-looking nested records must fail even after resealing. Existing plans, snapshots and runs are the carriers; no new store, URI scheme or `ControlPlaneStore` configuration archive. |
| Failures and observability: experiment loader `_safe_validation_details()`, `raes/_errors.py`, instantiation safe diagnostics; `raes_processor/trial_compiler/models.py::CompilationFailure`, `TrialCompilationResult`; `raes_contracts/diagnostics.py`; conformance `sanitized_failure_message()` | Keep bounded value-free diagnostics and existing CLI/MCP envelopes, including `AdmittedTrialPlanIngressError`. Do not expose Pydantic input/context, raw owner exception text, configurations, private locators or chained causes. Preserve the existing logger; no payload logging or parallel exception/audit hierarchy. Authored identifiers and error locations are untrusted text too. |
| Authentication and host/runtime exposure: existing CLI/MCP adapters; `raes_runtime/control_plane_api/_auth.py`, `_operation_routes.py`, `control_plane_security.py` | Contract/selection work is pure: no new endpoint, role, environment lookup, secret resolution, network call or subprocess. A sealed plan grants no dispatch authority. Later execution retains target-bound identity/roles, planner authorization, request bounds, redacted errors, audit and no-store middleware. Labels/outcomes must never become shell text, arbitrary paths, provider locators or credentials in argv/env. Reuse authorized runtime sinks; portable JCS commitments must not replace owner-private native-command commitments. |

## Supported forms and extension seam

[The SDL slot table](../../specs/sdl/variation-points.md#4-typed-target-slots)
is the authority for node configuration. Reuse declared scalar parameters and
the reviewed `nodes.presence`/runtime-inventory alternative slots. Inventory
selection retains top-level records on the exact owner node, including their
ids, payloads, nested children and source order. Empty selection and omission
have different meanings. Packages, environment entries, filesystem entries and
nested collection writes are unsupported structural targets today.

A necessary new slot needs justification, shape and semantic validation at its
owning SDL model and explicit slot allowlist. Runtime-family registration alone
grants no write permission. Factor names and compiler branches must not encode
individual slots. Keep the seam at SDL target/outcome admission, parameterized
by canonical owner and slot; a further reviewed inventory collection should not
need new factorial syntax, archive types or backend APIs. Participant expansion
uses its existing manifest registry and governed validator id/version map.
Reuse reference/member/subset/order/literal outcome types where supported;
their existence does not automatically authorize new enumeration or sampling.

## Publication, evidence and implementation boundaries

Normative changes belong in `specs/formal/experiment-core/README.md`,
`specs/formal/scenario-variation-trial-realization/README.md` and the binding
reference guide. Update SDL guidance only if its supported forms change.
Publish the new profile's semantics and compatibility limits explicitly in
affected profile literals and schemas, including the designed compiler surface
when its admitted meaning changes. Unknown profiles fail closed; a
contract-only publication must not make the old compiler claim execution support.

ADR-009/061 make `contracts/schemas/` normative. Account for authoring, study,
run and admitted-plan schemas and every other root embedding changed children;
do not assume a Python model edit or one root update is enough. Keep
`raes_contracts/contracts/bundle.py::schema_bundle()` parity through
`tools/generate_contract_schemas.py` and `tools/check_generated_schemas.py`.
Record each affected hash and `last_change` under
`contracts/schema-publication/entries/`, routed by the existing v2 manifest,
and use `tools/check_schema_publication.py`. Preserve unchanged scalar schemas;
apply the actual draft/stable policy rather than automatically renaming every
contract. Publish contextual invariants with `contracts/schema_invariants.py`
and reuse conformance registration; JSON Schema alone cannot prove arbitrary
cross-document owner, source or family joins.

Positive/negative fixtures must distinguish structural identity from a string,
exercise joint node-presence/inventory and participant configuration, and cover
selection-only designs, fixed coverage, invalid combinations, aliases/defaults,
effective duplicates, all source joins, bounds and redacted failures. Reuse
`test_exp_719_factorial_*`, `test_experiment_selection.py`,
`test_issue_1625_structural_variation.py`,
`test_issue_1626_trial_participant_bindings.py` and existing admitted-plan/archive
tests. Preserve old scalar identity vectors and exercise round trips and
resealed tampering at the contract boundary. Model acceptance is not evidence
of compiler, backend or lifecycle support; that follow-on work remains separate.

Use `.ground-control.yaml`, `.gc/plan-rules.md` and existing repo policy tools.
This issue has no requirement UID to invent. Local verification is targeted;
full test, integration, fuzz and completion suites belong to CI/CD.

Non-goals are runtime mutation, new provisioning support, scheduling/allocation
changes, secret acquisition, asset delivery, services or persistence migrations.
Do not add a patch language, second SDL binder, duplicate outcome schema,
generic plugin dispatcher, example-specific catalog or alternate workflow.
Scenario choice, participant implementation configuration, apparatus authority,
runtime facts, realization openness and observed execution remain separate
concepts with their existing owners and evidence requirements.
