# Issue 1625: Node and runtime inventory structural variation preflight

Date: 2026-10-25. Inspected revision: `ecd7b205`.

Contract: the supplied GitHub #1625 title and body. No formal requirement is
attached. This note sets design guardrails. It is not a plan or a claim of
shipped support. [ADR-084](adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md)
and its [design reference](../explain/reference/scenario-variation-and-trial-realization.md)
already define the phases. No new ADR is needed.

## Decision and ownership

Extend the closed SDL targets to select nodes and their runtime inventory.
Keep `alternative` as exactly one named choice. Keep `subset` as bounded
membership. Presence needs no new point kind or per-resource `enabled` field.
It is not a backend choice. Outcomes name declared member IDs through the
existing DTOs. An absent choice must have an explicit type and meaning. An
empty string, bad reference or arbitrary `null` cannot mean absence.

The owning slot declares scope, allowed type, stable ID and write rules.
Existing `VariationMember` and `ReferenceTarget` choices replace references.
They cannot acquire the meaning of embedded objects. Select existing typed
rows where references suffice. If a choice needs a payload, use the owning
`Node`/runtime model with a closed type tag. Do not use an untyped fragment or
copy its schema. Keep existing wire meanings.

An absent node does not exist in the selected scenario. Its same-key
`infrastructure` entry holds its deployment data. Handle that entry explicitly
within the node-membership write. Do not leave an orphan deployment.
`InfraNode.count = 0` is invalid; the minimum is one.

This ownership rule grants no broad delete rights. Incoming links, dependencies,
accounts, content, domains and relationships remain in scope for checks.
So do participant access/scope, assertions, objectives, generated artifacts and
evidence demands. Every surviving reference must resolve or the choice fails.
Authors express dependent choices through the existing bounded relations and
typed slots. Never repair a failed choice silently. An absent node cannot
support a child write. Put coupled node/inventory choices in one typed
alternative where needed. Do not skip the child outcome or make it optional
by convention.

Inventory rows keep their owner node and existing IDs. Matching schemas do
not permit copying rows across owners. Nested slots need the full stable
parent ID. Array positions and choice labels are not row IDs. Keep other fields
and list order unless the slot permits order changes. Omitting a row makes no
claim that it is forbidden, unknown or discovered at runtime. It does not assert
an empty closed inventory. Preserve the meaning of `RealizationPresence` and
closure. Backend envelopes still govern what a backend can realize.

The extension seam belongs in the closed target specs in `raes/variation.py`.
Each reviewed slot names its owner, collection, model, ID, point kinds and
write scope. Reuse the family/child metadata in
`_runtime_service_family_registry.py` and traversal in
`_runtime_service_families.py`. Use `runtime_inventory.py` for read-only
collection ID metadata. Do not copy family names and ID fields into another
registry. Being referenceable grants no right to change a row.

Other collections include packages, environment and filesystem inventory.
They need their own ID and shape rules. Do not invent service-family IDs for
them. A future family or nested slot should use this same seam. It should
need no change to outcome schemas, compiler policies or backend APIs. No
arbitrary path interpreter is needed.

## Canonical incumbents and admission layers

Package paths below are relative to `implementations/python/packages/`.

| Layer and existing owner | Required guardrail |
| --- | --- |
| Source ingress: `raes/parser.py`, `_yaml_loader.py`, `_source_profile.py`, `_mapping_scopes.py` | Retain byte/depth/alias limits, duplicate-key rejection, canonical structural keys, literal member IDs and rejection of variable-defined keys. A nested typed candidate must receive these same checks; do not load it with a second YAML parser or treat it as opaque data. |
| Composition/trust: `raes/composition/`, `_module_symbols.py`, `_module_runtime_aliases.py` | Complete trusted composition before selection. Reuse confined import resolution, lock/digest/trust checks, export/private visibility and namespace rewriting for owners, candidates and relations. Rewrite references inside any typed candidate too; no selection-time imports, queries or callbacks. |
| Shape and reference authority: `raes/_base.py::SDLModel`, `nodes.py`, `runtime_configuration.py`, `_declarations.py`, `_reference_targetability.py` | Keep closed discriminated shapes and slot-specific type/owner eligibility. Use the collision-preserving declaration index and purpose rules; do not split dotted names or use a permissive new resolver. Rebuild the index for the selected content. Compute/switch restrictions, OS/architecture rules, duplicate inventory IDs and package/repository correspondence still apply. |
| Family validity: `raes/validator/_variation.py`, `_variation_satisfiability.py` | Reuse local candidate checks and bounded cardinality/requires/excludes satisfiability. Every declared member must be usable. Current candidate probing assumes a reference replacement in an otherwise intact family; do not extend its string-list assignment to object inventories. Local branch validity and cross-point satisfiability do not prove whole-scenario validity. Avoid enumerating the full Cartesian product during family validation. |
| Selection and joint writes: `raes/experiment_selection.py`, `selected_scenario.py` | Require complete, known, in-domain outcomes and valid relations. Resolve writes against the unchanged family, then construct a fresh selected payload. Extend canonical target/write checks to parent-child overlap: removing a node while writing its inventory, or replacing an inventory while editing its children, must reject incompatible writes independent of point names/traversal order. Never skip a child selection because its parent disappeared. |
| Concrete admission: `raes/instantiate.py::instantiate_scenario` and `admit_instantiated_scenario`, `raes/validator/` | Reconstruct through the ordinary owning models, bind variables and run full semantic validation. Include infrastructure/network namespace references, accounts/domain/tenant joins, service/listener/process/file references, stateful resources, participant access, objectives and evidence scopes. `validate_node_realization()` is only a bounded node-context check, not scenario admission. Never mint admission by setting private flags or using unchecked `model_copy(update=...)`. |
| Secrets and environment shapes: `raes/runtime_environment.py`, `runtime_generated_value.py`, `runtime_values.py`, account credential bindings | Preserve redaction/classification and `value`/`value_from` exclusivity. Generated outputs must exist, be consumable rather than `producer_private`, and use the required secret classification. Env-file names remain `PortableIdentifier`, not paths. Operator material stays on existing governed secret-reference/authorized sink carriers. Do not copy credential material into alternative labels, outcomes, factors, plan bindings or digests; secret-name heuristics are not authorization. |
| Experiment and processor: `raes_contracts/contracts/experiment_selection.py`, `experiment_bindings.py`; `raes_processor/trial_compiler/`, `trial_realization.py` | Reuse outcome DTOs, contextual family binding, finite policy/compilation budgets, per-coordinate `select_scenario_family()` admission, apparatus capability/envelope checks and capture admission. Any invalid requested coordinate rejects the whole plan; no dropping, resampling or backend substitution. Subset/order currently support fixed outcomes, not automatic enumeration/sampling; adding targets must not broaden that policy contract implicitly. |
| Identity, portable ingress and persistence: `raes/canonical.py`, `phase_contracts.py`; `raes_contracts/admitted_trial_plan_ingress.py` | Declarations/domains affect family identity; selections never mutate that family or enter its digest. Selected concrete content and existing selection/plan/run lineage affect the instantiated snapshot. Retain original family pins, run identity, import lineage and snapshot re-admission. Removed/reordered members must not leave stale capability-constraint pointers, parameter derivations or realization/explicitness records. Reconcile owned provenance by stable identity; never discard constraints to pass admission. Existing plans, snapshots and archival run/study records suffice; no variation store or new database is needed. |
| Diagnostics and exposure: `raes/_errors.py`, `_model_diagnostics.py`, `instantiate.py::_safe_model_validation_errors`; `raes_processor/trial_compiler/models.py::CompilationFailure`, `raes_contracts/diagnostics.py` | Reuse SDL exceptions and the processor's bounded diagnostic envelope. Report safe point/member IDs, addresses and codes, not candidate payloads, Pydantic input/context, chained exception text or secret-derived values. Apply the same rule to CLI/MCP responses, logs and telemetry; do not add a variation exception hierarchy or payload logging. |
| Host/runtime and authentication boundary: existing CLI/MCP adapters; `raes_runtime/control_plane_api/` | Selection is pure in-process construction: no secret resolution, filesystem writes, subprocesses, environment lookup or new service. Ordinary downstream provisioning retains existing command/path/secret-sink protections; selections must not become shell text or credentials in argv/env/logs. No new endpoint, role or auth configuration is needed. Existing execution entrypoints retain target-bound `ControlPlaneIdentity`/roles, request-size admission, redacted validation/error responses, audit and no-store middleware. A selected scenario does not grant execution or participant access. |

## Publication, compatibility and evidence

The slot table in `specs/sdl/variation-points.md` is normative. It must agree
with the published `contracts/schemas/sdl/sdl-authoring-input-v1.json`.
The parser, language service, composition and public selection API must agree
too. ADR-009/061 govern schema authority and change rules. Reuse
`raes_contracts/contracts/bundle.py::schema_bundle()` and
`tools/check_generated_schemas.py`. A Python-only union change is not enough.
Record schema changes in the `last_change` entries under
`contracts/schema-publication/entries/`, routed by the existing v2
`contracts/schema-publication-manifest.json`, and verify with
`tools/check_schema_publication.py`. Check dependent bundled schemas too.
Keep authoring variation fields out of concrete artifacts and snapshots.
Static, variable-only and reference-only families keep their meanings and
digests. Older consumers must reject unknown targets.

Reuse the focused tests under `implementations/python/tests/`:
`test_sdl_variation_points.py`, `test_sce_002_selected_scenario.py`,
`test_experiment_selection.py`, `test_sce_002_trial_compiler.py`,
`test_sce_002_trial_realization.py` and the runtime-family/source-format/schema
tests. Extend `contracts/fixtures/sdl/variation-points-v1/`.
Evidence must cover:

- Present/absent nodes with deployment data; selected rows with intact payloads
  and IDs; invalid surviving references.
- Parent-child write conflicts and valid dependent choices; imported, private
  and nested references.
- An unchanged family across choices; distinct family, snapshot and run IDs;
  reordered rows and their provenance.
- Redacted shape failures; no plan when one requested trial is invalid.

Include a full experiment-to-selected-snapshot witness. Model acceptance alone
is not enough. Reuse `.ground-control.yaml`, `.gc/plan-rules.md` and repo
policy tools. Do not invent a formal requirement UID for this issue. Run
targeted local checks. Full integration, fuzz and completion suites run in
CI/CD.

## Non-goals and anti-patterns

Do not add another family, experiment or trial root. Do not add a patch/overlay
engine, expression language or randomizer. Reuse schemas, resolvers, validators,
errors and stores. Do not grant blanket reference rights or add another
scheduler or runtime mutation API.

Realization openness is not experiment choice. Runtime facts cannot edit
topology. Inventory grants no right to provision resources. Capture is not
proof of backend support. Avoid defaults, first-member fallback, order-dependent
writes, reference repair, `Any` schemas and weaker checks on unused candidates.
Backend negotiation, credential setup, broader policies and new inventory
vocabulary are outside #1625. Full selected-scenario checks and downstream
capability gates still apply.
