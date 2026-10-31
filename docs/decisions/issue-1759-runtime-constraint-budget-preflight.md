# Issue 1759: runtime constraint evaluation budget preflight

Recorded 2026-10-31 against `af8935054`. Non-normative architecture guidance
for issue #1759; no implementation or implementation plan. The supplied issue
is the contract; there is no formal requirement UID to invent.

## Decision and evidence

Keep the fix in the existing pure relation owner,
`raes_contracts.realization_structure`, behind its public
`evaluate_realization_constraint(document, actual, *, limits=...)` interface.
ADR-105 and the [recursive constraint specification](../../specs/sdl/recursive-realization-constraints.md)
already define the semantics and bounded outcomes. No new ADR, constraint
language, evaluator, runtime-only exception or applications-specific policy is
needed. Address repeated scope work before considering a larger shared default.
A budget increase alone leaves the same scaling failure for the next input.

Inspection found two multiplicative paths:

- `_common.closure_for()` scans and decodes every scope for each container
  needing inherited closure. `_evaluation_context.evaluate_closure()` uses it.
- `_scopes._declared_scope_children()` scans every scope again for each closed
  overlay. `evaluate_scope_overlays()` also resolves each target from the root.
  Improving closure lookup alone does not address the closed-overlay scan.

The compiler's `realization_recursive_constraints._SourceMetadata` emits scopes
for projected containers, including defaulted empty collections. Source JSON
size and route count therefore understate the work of the compiled document.
Normalization or source binding success does not prove evaluation fits its
budget: the evaluator separately admits the constraint, then shares one budget
across actual-value admission, overlays and recursive comparison.

A local, generated application with one HTTP application and routes containing
an ID, path, GET method, 200 response and template reproduced the issue through
`parse_sdl`, `compile_runtime_model` and recursive concern projection:

| Routes | Source JSON bytes | Compiled scopes | Default evaluation, authored / observed |
| --- | --- | --- | --- |
| 5 | 915 | 53 | conformant / conformant |
| 10 | 1,770 | 103 | limit-exceeded / limit-exceeded |
| 15 | 2,640 | 153 | limit-exceeded / limit-exceeded |

With an explicit diagnostic-only `max_operations=200000`, the 15-route value
was conformant. Instrumentation counted 6,708 constraint-admission operations
and 48,069 evaluation operations; closure lookup alone spent 23,409 operations
(`153 * 153`). The default is 16,384. This establishes a local mechanism,
not reproduction of the external env-packs v7.0.0 file, which was not fetched.
The repository's TechVault examples are not evidence of that exact release.

## Relation guardrails and extensibility seam

Reuse `EvaluationContext`, `RelationBudget`, `admit_constraint_document`,
`validate_bounded_value`, and the existing closure/overlay owners. Any prepared
scope lookup belongs inside this owner and lasts for one admitted evaluation.
It must serve both ancestor-closure resolution and declared-descendant lookup
without repeated whole-scope scans. A bounded internal token index is suitable;
no public prepared-document DTO, global cache or separate engine is warranted.
Do not mutate the document or its serialized representation to accelerate a
read. Frozen Pydantic models do not make their contained dictionaries immutable.

Index construction, token processing, target resolution and lookup must remain
charged finite work, including when the selected budget is deliberately small.
Bound allocation before building derived structures. Keep the existing separate
constraint-admission phase; do not reset the evaluation budget per scope, node
or reference, retry with larger limits, or remove charges while retaining the
same scans. Exhaustion must bound remaining work and diagnostics as well as
return the right status. Do not attach budget counters to persistent state.

Keep `limits=` and `RealizationConstraintLimits` as the caller-controlled seam.
More routes, another concern, nested scopes or extension profiles must use the
same implementation without pack names, route thresholds or backend knobs.
Any justified default change needs measured cost and adversarial-limit evidence
across shared consumers, not a constant chosen to pass this fixture.

Preserve these independent meanings:

- Concrete node-local closure wins; otherwise the most-specific lexical scope
  wins, then the document default. Retain named universe/profile boundaries and
  unsupported undefined closure. A parent scope cannot erase exact descendants
  or a locally closed child. Scope order must not change conformance.
- Overlays still apply beneath delegated or additional members without a
  materialized constraint node. A lookup optimization must not skip them.
  Retain absent-target behavior and unsupported ambiguous collection addressing.
- Use `raes_contracts.json_pointer` and the existing semantic-address and
  identity helpers. Match decoded token tuples, never raw string prefixes:
  `/a` is not an ancestor of `/ab`. Keep root/empty-name and escaped `~`/`/`
  cases, sequence positions, keyed semantic identities, aliases and duplicate
  rejection. Check identity collisions; hashes alone are not semantic identity.
- Preserve required/optional/forbidden presence, omission versus null/empty,
  strict JSON types, bounded domains, knowledge states, conjunction, definition
  hop/cycle checks and non-expanded graph references. Delegation is permission;
  unknown or redacted knowledge is not. Equality is not a general shortcut for
  this relation and does not establish independent observation.

## Whole-repository boundaries to reuse

Package paths below are relative to `implementations/python/packages/`.

| Layer and canonical incumbents | Obligation for this fix |
| --- | --- |
| SDL and binding: `raes.parser`, `SDLModel`, semantic validation, `runtime_application`, `runtime_environment`, compiler instantiation/provenance | Retain parser bounds, typed shape and cross-field checks, variable binding/revalidation and source provenance. Bind flags with existing typed inputs; no env-variable or secret-resolution bypass. Route declarations describe the modeled application; they do not configure control-plane authentication. |
| Safe projections: `semantics.realization_concerns`, `realization_runtime_concern_profiles`, `realization_typed_runtime_projection`, `realization_concern_observations`, `raes.runtime_values` | Keep the registered applications profile, TypeAdapter validation, author/observed modes, ordered recursive data and excluded reporting fields. Preserve sensitivity checks, protected raw-value rejection, presence markers and commitments, including application exposed fields. Never compare or cache raw authored secrets instead of safe projections. |
| Recursive admission and shapes: `realization_structure._models`, `_limits`, `_common`, `bounded_domains`, `json_pointer` | Keep closed discriminated models, positive capped limits, scalar/member/node/depth/identity/hop bounds and direct model/JSON admission. Reuse the six relation statuses and `RealizationRelationResult`; only `conformant` succeeds. Do not duplicate schema validation or conflate structural admission with authority. |
| Compiler, planner and backend selection: `compiler.realization_recursive_constraints`, `planner.realization_authority`, `realization_preparation`, `realization_collections`, `prepared_node_projection`, `materialization_inventory` | Preserve source bindings and consume the same public evaluator. Existing composition/refinement, description and profile consumers also share this owner. Do not repair only the final runtime call, rewrite the authored constraint as an exact value, or change universal capability subsumption or backend selection. |
| Portable/authenticated plans: `contracts.realization_plans.ResolvedRealizationAuthorityModel`, `plan_projection`, `control_plane_api_models._provisioning_plan`, `realization_constraint_binding` | Keep recursive document/binding pairing, duplicate/address/pointer checks and the ban on two independently editable structures. Retain canonical digests and lossless DTO round trips, including explicit null. A checksum binds content; it is neither planner authorization nor satisfaction. No published shape change is expected. |
| HTTP auth/configuration: `control_plane_api._auth`, `ControlPlaneSecurityConfig`, `ControlPlaneConfiguration`, `control_plane_submission`, `RequestSizeLimitMiddleware` | Preserve target/role authorization, trusted planner-plan authorization, bounded body parsing and safe responses. The evaluator needs no new endpoint, config field, environment override or transport-size increase. Larger transport or aggregate plan allowances do not grant a larger relation budget. |
| Host/runtime admission: `backend_input_contracts`, `backend_snapshot_contracts`, `runtime_value_limits`, `backend_calls`, `backend_apply_results`, `semantics.realization_runtime_evaluation` | Keep pre-copy input bounds and result shape/address/transition checks. `PLAN_VALUE_LIMITS` and `RUNTIME_SNAPSHOT_VALUE_LIMITS` govern aggregate carriers, not this per-constraint relation. Retain corroboration and selected observation obligations, safe post-sanitization revalidation and the trusted predecessor on rejection. The relation stays in-process: no subprocess, shell, token in argv, filesystem access, network fetch, plugin execution or new service. |
| Errors, observability and persistence: `Diagnostic`, `ApplyResult`, `backend_result_diagnostics`, `realization_snapshot_sanitization`, `control_plane_store*`, `raes_contracts.operational_logging` | Preserve bounded value-free relation diagnostics and the existing runtime failure envelope. The current gate maps relation failure to silent approximation; changing that mapping is not needed to fix evaluation. If exposing its cause, retain the status without raw constraints, expected/actual values, Pydantic inputs, backend exception text or host paths. Follow ADR-116 and `docs/develop/exceptions-and-logging.md`: expected findings use diagnostics; unexpected failures reach the existing boundary, with logging once. Reuse audit/receipt correlation and snapshot/store codecs; no new exception hierarchy, log stream, store or persisted lookup cache. |

`contracts/schemas/realization-constraints/recursive-realization-constraint-v1.json`
is normative, with embeddings in plan contracts. An internal lookup change must
not alter it. If a later design changes a published shape or meaning, ADR-009/061
require explicit compatibility review, publication entry/content hashes and
`schema_bundle()` parity through the existing schema tools; changing Python
alone is insufficient authority.

## Verification boundary and non-goals

The implementation needs a deterministic offline regression with the compiled
applications document, both safe projection modes and default limits. Use the
pinned pack only through established acquisition practices, or a representative
local fixture; do not download a pack during tests or depend on another checkout.
Include enough defaulted containers/scopes to expose both repeated scans. Pair
unchanged conformance with a changed exact route leaf, forbidden closed extras,
an allowed open variation, deliberate exhaustion and safe bounded diagnostics.
Exercise several sizes and scope distributions with deterministic work evidence;
avoid fragile elapsed-time assertions or fixing the old inefficient exact count
as a contract. Keep a compiler-produced portable plan through normal runtime
result admission with valid corroboration; direct relation success alone does
not prove the gate or backend evidence path works.

Reuse `test_issue_1203_recursive_normal_form.py`,
`test_issue_1200_mixed_runtime_constraints.py`,
`test_issue_1204_specialized_constraints.py`,
`test_issue_985_realization_projection.py` and the existing runtime fixtures.
Seven selected #1203 scope, sequence, reference and limit tests passed during
this preflight. They are baseline evidence, not verification of a fix.

Workflow owners are `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/check_repo_policy.py`, `tools/policy/adr_policy.yaml`, `noxfile.py`,
`tools/nox_support`, `.pre-commit-config.yaml` and canonical CI. Preserve
ADR-015/117 size/import boundaries; consumers use the public contract owner,
not its private helpers. Use targeted checks locally, requirement-free policy
handling where applicable, and leave full verification to CI. Do not fabricate
a UID or change release-owned version/changelog files.

Non-goals are implementing this fix in preflight, an external pack bridge,
backend-specific workarounds, unbounded or caller-data-selected budgets, new
SDL/plan schemas, new auth/configuration, live backend execution, broader
realization/observation semantics, automatic capture/export, persistence changes,
and a generic indexing framework. Conformance remains subject to finite limits;
planner acceptance is not a promise that arbitrary valid documents fit every
caller-selected budget.
