# Issue 1711: Contracts dependency preflight

Date: 2026-10-31

Contract: supplied issue #1711 and requirement `MOD-001`. Inspection revision:
`a601b696c`. This is architecture guidance, not an implementation plan.
No application, test, schema or policy changes are authorized by this note.

## Maintainer decision

On 2026-10-31 the maintainer chose strict layers (option A in the issue plan).
The decision resolves the boundary decision in the next section:

- The SDL-bound APIs move to their owners in `raes` and `raes_processor`.
  Their old `raes_contracts` paths stop working. No compatibility re-export stays.
- A new top-level package, `raes_schemas`, composes the published schemas.
- Seven validator locator strings change in five published schemas. Each
  schema gets a change-ledger entry.

On the same day the maintainer added the import cycles inside `raes_contracts`
to this issue. No issue of milestone 73 owned them.

The [design](issue-1711-strict-layers-design.md) and
[ADR-121](adrs/adr-121-strict-package-layers.md) record the decisions. The other
guardrails in this note stay binding.

## Boundary decision required

The intended direction is `raes` → `raes_contracts`. Neutral shared values and
their intrinsic validation belong in contracts; SDL parsing, expansion,
instantiation, semantic admission and SDL-specific projections belong in
`raes`. Processor compilation and live runtime authority retain their existing
owners. ADR-036 already establishes these responsibilities; ADR-117 supplies
the structural checks. No new package, dependency container or hierarchy is
needed for the shared-value extractions.

However, some existing public contracts APIs already perform SDL operations:

- `raes_contracts.contracts.schema_bundle()` takes no arguments and generates
  schemas from `Scenario`, `InstantiatedScenario`, `MaterializedScenario` and
  `InstantiatedScenarioSnapshot`. Its cached template also resolves published
  validator locators, some pointing into `raes`.
- `raes_contracts.associated_artifacts.require_instantiated_scenario_reference`
  instantiates and admits scenarios. `validate_associated_artifact_manifest`
  checks concrete scenario classes, phase, validation state and SDL digests.
- `raes_contracts.satisfiability.SatisfiableWitnessModel` and
  `raes_contracts.exploit_path.ExploitPathAnalysisInputModel` embed the concrete
  snapshot model, migrate legacy joins and recompute admitted SDL identity.
- `contracts.experiment_evidence_refinement` resolves caller-supplied scenarios
  and evidence requirements against canonical authored identities.

Lifting these operations into `raes` is the ownership-consistent direction,
but a contracts re-export back to that owner would violate the issue's required
dependency direction. Promoting their entire dependency closure into contracts
would relocate SDL models and semantic admission, beyond neutral DTO ownership.
A required callback or prior global registration would change existing calls.
These are compatibility decisions, not ordinary import rewrites.

Implementation needs a design that preserves these existing calls and their
checks while enforcing the dependency direction. This preflight has not
established such a design for these APIs. If resolving the conflict requires
changing SDL ownership or an observable contract, retain the affected code and
ask the maintainer under the issue's explicit stop rule. This note grants no
exception to zero reverse imports or public-path stability.
Do not make a runtime import dynamic, resolve it through `sys.modules`, inject
attributes into another package, or rely on startup order to disguise the edge.

## Shared ownership and canonical incumbents

All package paths below are under `implementations/python/packages/`.
An AST inventory finds 57 reverse import statements in 39 contracts files,
including the two `TYPE_CHECKING` imports in evidence refinement. The live
function-local totals are 152 imports in 67 contracts files and 56 in 26 SDL
files; not every deferred import exists only to break a cycle. Grimp places
404 modules in the cross-package strongly connected component when it excludes
`TYPE_CHECKING` imports and 410 when it includes them.

| Concern and current owner | Guardrail for extraction |
| --- | --- |
| `raes.identifiers` / `_identifiers` | `raes_contracts.identifiers` should own the existing aliases, `QualifiedName`, predicates, schema constants and refusal helpers. Preserve ASCII grammar, optional empty values, local versus qualified/module identities, `__private` placement, length bounds, and `sdl.identifier.invalid` error codes. Keep filesystem run IDs and compiled addresses distinct. |
| `raes._base` via `raes.value_parsing` | Share the existing variable-token grammar, schema marker and normalization functions without pulling in the SDL facade. Whole-field substitution differs from embedded-token detection. Keep placeholders, normalization, coercion and errors unchanged. |
| `raes.explicitness`, participant attribution/behavior/local-outcome/mixed-control/outcome/temporal modules | Move shared enums once and retain old public paths as explicit imports of the same objects. Keep authoring classification, temporal binding and outcome interpretation logic with their semantic owners. Similar names in authored, observed, proposed and executed states do not imply interchangeable types. |
| `raes.semantics.workflow` → `raes_contracts.workflow.contracts` | The existing `WorkflowStepSemanticContract`, construction rules and step-result validation are already pure shared logic. Keep one implementation and existing mappings, coercions, error ordering and public entry points. Do not duplicate workflow execution, compensation, timeout or retry machinery. |
| `raes.artifact_requirements` / `_source`, `evidence_requirements`, `participant_inject_delivery`, `participant_outcome_semantics`, `phase_contracts` | These are typed model dependencies, not only enum imports. Identify each actual shared model and its full validator/type dependencies. Keep artifact identity, source selector, capture intent, observed evidence, delivery authority and phase provenance distinct. Preserve the existing media-proof validation in `raes_contracts.evidence_output_validation`. |
| `raes.schema_catalogs`, `_mapping_scopes`, `_runtime_service_family_registry`; `observability_plane_semantics` | Reuse the canonical collection/child/identity metadata and plane mapping. The runtime-family registry contains actual SDL module objects and supplies facade exports; it is not inert metadata despite its description. Contracts must not acquire those module imports. A neutral metadata view must derive from one source, with model/export bindings staying in SDL, rather than duplicating family lists or plane classifications. |
| Canonicalization, bytes and diagnostics | Reuse `raes_contracts.canonical`, `digests`, `json_serialization`, `json_pointer`, `diagnostics`, `addressing`, `planning` and `versions`. The shared-primitives work is already present at this revision. `raes.canonical` adds SDL phase/admission rules; a raw JSON digest is not its replacement. |

Use direct public imports of owning modules internally. Existing public paths
may explicitly re-export a name from a lower owner; preserve object identity
instead of subclasses, copied enums, copied constrained aliases or wrappers
with different exception behavior. Do not merge `SDLModel` and `ContractModel`:
the former has `populate_by_name=True`; phase records also have frozen and
serialization rules. Retain the effective model configuration and validators
when extracting a genuinely shared value. A base-class change can alter
accepted aliases, revalidation, equality, dumps and Pydantic definition names.

## Cross-cutting layers that must still pass

| Layer and canonical incumbent | Required behavior |
| --- | --- |
| Source and JSON ingress: `raes.parser`, `_source_profile`, `_source_validation`; `raes_contracts.json_ingress` | Keep safe YAML construction, source-profile/migration selectors, byte/scalar/alias/depth limits and source diagnostics. JSON paths retain duplicate-member, non-finite-number, integer, encoding, root-shape and caller-supplied size/depth refusals before model construction. Do not replace bounded parsers with bare `json.loads` or model-only validation. |
| Contract shapes: `_base`, `contracts.base`, owning Pydantic field/model validators, schema hooks, `_validation` | Retain closed fields, strict integers, discriminators, cardinality, defaults, aliases, serializers and cross-field order. Keep portable JSON Schema constraints aligned with Python validation; neither substitutes for the other. No new schema or second validation framework. |
| Phase and evidence admission: `raes.instantiate.admit_instantiated_scenario`, `materialization.admit_materialized_scenario`, `validator.SemanticValidator`, `canonical`; contracts associated-artifact and evidence-refinement validators | Preserve re-admission, concrete phase/type checks, legacy snapshot migration and digest joins. A private `semantic_validated` flag or a caller-supplied digest does not replace reconstruction and semantic validation. Keep original parent/snapshot distinctions, reference uniqueness, refinement rules and no-input-mutation behavior. |
| Environment/configuration shapes: `raes.runtime_environment`, `runtime_generated_value`, `runtime_values`; `raes_runtime.control_plane_security.ControlPlaneSecurityConfig` | Preserve literal/value-from exclusions, the rejection of generated values classified `operator_secret`, bounded portable env-file names, producer-private output refusal and secret-output redaction checks. Preserve `GovernedVocabulary` and current unknown/extension/variable rules. Add no ambient environment selector, import-time configuration, new registry setting or security-config field. |
| Secret and locator handling: `raes_contracts.uri_safety.validate_safe_absolute_uri`; `raes.runtime_values.enforce_observed_value_redaction`; phase provenance and source-identity validators | Keep credential-userinfo and secret-query refusals, per-caller scheme/fragment rules, raw-value omission for explicit redaction classifications, host-path/traversal refusals and credential-free import provenance. Identifier spelling alone does not decide sensitivity. References remain inert; no URI dereferencing or secret-store access is introduced. |
| Authorization and effects: runtime `control_plane_api/_auth.py`, `control_plane_security`, participant-control admission; `raes_backend_protocols.inject_execution` | Shared DTO validation grants no authority. Preserve target-bound identity, roles, proxy/bearer policy, revocation and audit. Retain the resolver's current-authority/revision checks and non-secret bounded inject evidence. No controller, provider, dispatch, tenant/principal or backend policy moves into contracts. |
| Trusted non-wire context: contracts `participant_control_resolution`, `participant_control_inject_resolution`, `participant_control_security_resolution`, `participant_flow_control_context` and `_host_isolation` | Reuse the existing typed contexts, exact delivery/application/security-fact joins and host-callback isolation. Preserve trusted-index ownership, audience/episode coordinates, policy cuts and digest bindings; provider assertions cannot stand in for resolved authority. Do not add another context DTO or callback framework to bypass these gates. |
| Errors and operational logs: `raes_contracts.errors`, `operational_logging`, `diagnostics`; `docs/develop/exceptions-and-logging.md` | Keep ADR-116's single exception hierarchy and boundary-owned translations. Pydantic validators retain `ValueError`/`PydanticCustomError`; preserve the legacy-snapshot conversion of SDL refusals into `ValueError`. Keep diagnostic codes, locations, order, messages and return-versus-raise distinctions. Libraries never configure logging. No new catch-all, duplicate log, payload dump or traceback leakage. |
| Public error envelopes: runtime `control_plane_api/_responses.py`, `_operation_routes.py` handlers and `control_plane_api_guards`; CLI `entrypoint` and MCP server boundary | Same failure reaches the same status/detail/output and is logged at the same boundary. Preserve coarse 401/403/409/503 and unexpected 500 handling. Keep `portable_diagnostic_payload` and value-free logging; model/exception text must not start leaking through HTTP, MCP or CLI after a move. |
| Persistence and OS exposure: runtime store codecs/history and snapshot/result admission; `raes_contracts.immutable_history`; `raes_operations.run_artifacts`; SDL module-registry verified-source/archive helpers | Keep exact durable bytes, digest framing, history heads, the 128-level durable bound, transactions, revisions and idempotency. Keep bounded artifact readers, descriptor checks, no-follow archive/source handling, permissions and atomic publication. No database migration, new I/O, service, cache, subprocess or credential in argv/logs is needed for this refactor. |

The security implication is mostly preservation: extracting a shared type
changes every consumer's gate, including generated env bindings and backend
readback. Passing a local model check alone does not demonstrate these layers
remain equivalent. Retain narrower caller policies, for example inject
evidence's 32-artifact/64-KiB-per-artifact limits, rather than replacing them
with associated-artifact defaults.

## Schema, import and runtime compatibility

Published schemas under `contracts/schemas/` remain normative (ADR-009).
This checkout has 289 `validator` occurrences, with 142 distinct locators;
the issue's 273 count is historical. Preserve every locator exactly and keep it
resolvable, including private methods and the six distinct locators rooted in
`raes`. Published locator compatibility does not authorize new source imports
of private names. Preserve `$defs`/`$ref`, titles, annotations, profile/version
strings, schema-factoring and transform order, and bundle key ordering.

Reuse `contracts.schema_constraints`' invariant annotation checks and
`schema_invariants`, `schema_factoring`, `corpus` and `manifest_authority`.
`schema_bundle()` retains its complete output and fresh deep copy per call.
Do not serve checked-in schemas as the generator's output: that would make
`tools/check_generated_schemas.py` compare the publication to itself. Do not
edit schemas or the publication ledger to bless refactor drift. Any unavoidable
schema or validator-path change requires maintainer approval before coding it.

Preserve class/enum identity, resolved annotations and `isinstance` behavior
through all existing public paths. Consider observable qualified names and
Pydantic reference collisions when moving classes; do not blanket-rewrite
`__module__` or install pickle/import hooks. Validate cold imports in different
orders, direct module imports, runtime type-hint resolution and installed-wheel
imports, rather than relying on a test session that already loaded SDL.
`raes_contracts.__init__` stays inert. Its bootstrap closure with `errors` and
`operational_logging` remains standard-library-only and Python 3.12 compatible;
normal application code targets Python 3.14.

Remove cycle-only function-local imports after their dependency is eliminated;
do not hoist every deferred import. Corpus access, optional dependency loading
and schema assembly can have separate reasons for deferral. Record a reason
for any retained finding; a retained `raes` import still fails acceptance.
The dynamic validator resolver is another real dependency path, not a permitted
escape hatch for SDL assembly.

## Structural governance, extension seams and evidence

For implementation, `tools/policy/adr_policy.yaml` must leave contracts with no
allowed first-party dependency on `raes`; keep `raes` consuming contracts.
Use its existing config shape and ADR-117's `tools/policy/import_contracts.toml`
layer order. Remove resolved exact import ignores and drain affected entries
in `structural_baseline.json`. Never rebaseline new cycle/private-import/class
identities, weaken analyzer settings, or use the exceptions file to waive them.
The direct AST boundary check includes `TYPE_CHECKING`; grimp's configured
graph excludes it but includes function-local imports. Both are necessary.
Review dynamic imports separately. Do not add a parallel import checker or
remove unrelated sibling cycles merely to report a smaller aggregate count.
ADR-015's 1,000-line limit is a backstop, not a module-splitting design.

Future shared values extend the public neutral owner; no plugin registration
or generic service is required. For runtime families, the existing metadata
seam is `collection_name`, `id_field`, nested `child_refs` and explicit
`reference_policy`; SDL module/export bindings stay above it. A new family
must not require editing a second schema-only catalog. Schema transforms keep
their existing explicit `contract_id` and schema inputs. If the maintainer
approves separating SDL bundle assembly, its composition input should be
explicit owned schema contributions, without global registration; this does
not resolve or waive the current zero-argument API compatibility decision.

Whole-repo consumers in scope for compatibility are all ten packaged roots,
the wheel/sdist configuration and corpus build hook in `implementations/python`,
`contracts/schemas/` and the publication manifest, `tools/generate_contract_schemas.py`,
`tools/check_generated_schemas.py`, `tools/check_schema_publication.py`,
`tools/check_repo_policy.py`, the structural configs above, `.ground-control.yaml`,
`.gc/plan-rules.md`, `noxfile.py`, `tools/nox_support/`, repository hooks and
`.github/workflows/`. No replacement build, policy or workflow is needed.
Accepted ADRs remain governed by `tools/check_adr_immutability.py`; this note
does not amend ADR-036 or authorize moving SDL ownership wholesale.

Use existing behavior tests: `test_sdl_identifiers`, `test_sdl_phase_contracts`,
`test_sdl_canonicalization`, `test_instantiated_scenario_schema`,
`test_associated_artifact_manifests`, `test_scenario_satisfiability`,
`test_exploit_path_analysis`, workflow semantics/result tests, generated-env
consumer tests, ADR-116 boundary tests and ADR-117 structural tests. Verify
exact refusal/dump/digest/schema results and cross-path object identity.
Only existing tests that import or patch a removed private name may change,
and must retain the same public behavior assertions. Add focused coverage for
uncovered boundaries, without rewriting fixtures or expectations to fit a move.
Run targeted local checks; full, integration, fuzz, completion and repository-wide
policy suites belong in CI. Set `RAES_REQUIREMENT_UID=MOD-001` because this
branch name does not contain the supplied requirement UID.

Non-goals:

- issue implementation in this preflight;
- new functionality, schema versions, admission hardening or relaxed validation;
- digest or storage migrations;
- new exceptions, logging, configuration, dependencies or services;
- wholesale SDL relocation;
- controller, repository or workflow consolidation;
- broad test rewrites;
- release or version edits;
- line-count-driven module fragmentation.
