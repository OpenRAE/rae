# Issue 1697: provenance for admitted prepared resources

Date: 2026-10-29. Requirement: none; issue #1697 is the delivery contract.
This is architecture guidance, with no implementation or implementation plan.

## Decision and ownership

Derive SEM-218 concern entries for first-party portable resources admitted by
`backend-realization-preparation-v1` at the existing runtime acceptance boundary.
The accepted snapshot owns this ledger. Preparation selects a completion; it
does not prove delivery or supply trusted provenance. Neither a consumer nor a
backend may fill the gap by writing `realization_provenance`.

The inspected code already separates the original authority (`_RealizationApplyContext.plan`)
from the admitted operation/completion (`operation_plan`, `completion_plan`).
`backend_apply_results._realization_disclosure_result()` derives entries from
the original authority and supplemental requirements. Those inventories do not
cover a resource introduced by preparation. Preserve the original authority;
replacing it with the selected plan would confuse backend choices with author
intent and invalidate the original authority checks.

Reuse ADR-004/036, SEM-218, the
[preparation contract](../../specs/sdl/backend-realization-preparation.md),
[provenance preservation guidance](issue-760-sem-218-provenance-preservation-preflight.md),
and [descendant design](issue-1649-runtime-descendants-design.md).
No new ADR, provenance vocabulary, public DTO, or persistence channel is needed.

## Concern derivation and ledger invariants

- Use `prepared_node_projection.prepared_additional_node_operations()` and the
  authenticated `preparation.node_collection` identity inventory to identify
  prepared portable members. Do not infer permission from plan absence, an
  address prefix, an open child concern, or a successful backend result.
- Share the processor's concern derivation with
  `materialization_inventory._node_concern_provenance()` where their semantics
  coincide. Its canonical inputs are `realization_concern_descriptors()`, typed
  node values, supplied-field presence, and descriptor applicability. Construct
  the existing `CompiledRealizationRequirement` / `RealizationProvenanceEntry`
  through `realization_provenance_entry()`. Runtime imports must use the public
  `raes_processor.planner` facade, as required by `tools/policy/adr_policy.yaml`.
- A concern introduced solely through open membership is `OPEN` and
  `BACKEND_REALIZED`. An exact admitted completion is a delivery obligation,
  not an exact author declaration. In particular, do not use
  `prepared_node_support._prepared_node_requirements()`'s `EXACT` support-check
  posture as disclosure explicitness. Retain independently applicable original
  constraints and original author/processor origins.
- Cover both `node` and `network` resources using their existing typed owners.
  Switch concerns must use the typed `spec.node` and `NetworkRuntime` identity;
  do not assume compute-only flattened OS fields exist. Capture containers follow ordinary compute-node
  rules. No capture name, image, role, or backend-specific concern list belongs
  in derivation. Use canonical qualified names and the admitted governing scope;
  do not reconstruct names by splitting dotted addresses or invent module scopes.
- Preserve supplied empty concerns such as `runtime.environment: []`.
  Missing, null, defaulted, redacted, and explicitly empty are distinct. Compiler
  `_dump()` includes defaults; a fresh model dump is not evidence that every
  default was selected. Reuse typed presence/projection rules and descriptor
  exclusions, including non-stateful mount applicability. Restored commitment
  placeholders are validation aids, never observed values or author facts.
- The registry is not the entire concern system. Compute-substrate uses
  `realization_compute_substrate` and `realization_observation_demand`;
  source-artifact uses `artifact_realization`. Preserve their applicable
  selection, support, demand and satisfaction rules rather than assuming a
  registry walk covers them or fabricating observation/artifact evidence.
- Assemble one deterministic ledger by `(address, field_path, domain,
  requirement_kind)`, the identity already used by materialization inventory.
  Preserve trusted rows for unaffected resources, including prepared members
  retained without a new operation. Replace affected current concern rows
  without duplicates or stale removed concerns; accepted deletion must not
  resurrect a resource's current rows through a predecessor merge. Existing
  archives/history retain their own historical meaning.
- Derivation must be the same with or without materialization negotiation.
  `backend_materialization`, `backend_inventory`, and
  `materialization_inventory._provenance_ledger()` must preserve these accepted
  first-party rows through reporting and refresh. A first-party prepared member
  is not a delegated holder's descendant: never manufacture parent/source links,
  creation receipts, or `RuntimeInventoryReport.descendants` to obtain its rows.
  Added materialized resource bindings keep `source_node=None`, as enforced by
  `materialization_admission._validate_binding_origin()`; the original holder
  must not be substituted as their source.
  Existing descendant entries and authorized backend-selection handling remain
  under the descendant contract.

## Cross-cutting layers the change must pass

Package names below refer to `implementations/python/packages/`.

| Layer and canonical owners | Required behavior |
| --- | --- |
| SDL/phase admission: `raes` parser, `instantiate_scenario`, closed `Node`/`InfraNode`, `SemanticValidator`; compiler explicitness and realization designation | Original author classification remains immutable. Prepared values use `prepared_node_admission` and `prepared_node_semantics`, not a second SDL classifier or compilation that labels backend SDL as authored. Materialized SDL keeps `parse_sdl`, `validate_materialization_origins`, and complete inventory checks. |
| Authorization/configuration: `RuntimeTarget`, `RuntimePlanAuthorizationMixin`, `runtime_plan_digest`, `_require_preparation_contract`, `_prepared_response` | Retain callable/manifest validation, exact planner authorization even for effect-capable empty plans, operation/predecessor bindings, and complete manifest/configuration digest checks. Keep original authority and selected completion distinct. No new config keys, env options, or authorization route are needed. |
| Portable shape and work bounds: `backend_input_contracts`, `contracts.backend_preparation.preparation_response_model`, `validate_realization_value`, `runtime_value_limits` | Derive only from the admitted bounded operation inventory and safe payloads. Keep closed response shapes, identity/action checks, duplicate-address refusal, aggregate byte/member/depth limits, and isolation before backend calls. Avoid serializing/copying unbounded native values or repeatedly scanning the whole inventory per concern. |
| Membership/support/policy: `realization_collections`, `evaluate_realization_constraint`, `prepared_node_admission`, `prepared_node_support`, `backend_profiles` | Require positive enclosing collection authority with namespace, universe, cardinality, dependency/cycle, capability, configured offer, artifact availability, semantic and profile checks. Collection permission does not grant roles, identity-domain membership, generated-artifact consumers, or participant bindings. Deriving a row grants no further permission. |
| Native result and delivery: `backend_apply_results`, `backend_entry_transitions`, `backend_effect_transitions`, `backend_snapshot_contracts`, `prepared_delivery_violation` | Preserve raw-result shape, authorized effects, honest change accounting, immutable runtime-owned carriers, and exact selected-completion checks before sanitization. Revalidate sanitized values with admitted transient observations before attaching successful runtime-derived rows. A backend-written ledger remains invalid. |
| Secrets/env/host exposure: `RuntimeEnvironmentVariable`, `validate_environment_observation`, descriptor sanitizers, `prepared_node_payload_projection`, `backend_account_credentials` | Retain closed environment binding and sensitivity shapes, commitment validation, credential-egress checks, and native mount/port/capability/limit owners. The ledger carries references/enums, never selected values, secrets or resolved bindings. Add no secret lookup, subprocess, process argv, host file, service, upload or native collection. Preparation stays read-only. |
| Errors/API/observability: `Diagnostic`, `backend_result_diagnostics`, `value_free_backend_diagnostics`, `ControlPlaneSecurityConfig`, API `_auth`/`_responses`, `control_plane_api_guards` | Keep existing bounded `runtime.backend-preparation-invalid` / `runtime.backend-contract-invalid` failures and redacted transport errors. Preserve authenticated, target-bound, role-checked snapshot reads, request limits and existing audit/operation records. Do not expose backend exceptions, validation inputs, native reprs or values through new logs, metrics labels or audit details; no new exception hierarchy or logging channel. |
| Persistence/publication: `RealizationProvenanceEntryModel`, `RuntimeSnapshotEnvelopeModel`, `snapshot_contract`, `control_plane_store_snapshots`, `finalize_protocol_result`, terminal store commits | Existing `runtime-snapshot-v1` and enum shapes already carry the rows. Preserve public/store round trips, native proposal digest checks before and after acceptance, protected archive admission and revision/owner-generation checks. Derive accepted state without mutating the committed native proposal; snapshot, terminal record and audit remain under the existing atomic commit owner. No schema bump, sidecar, DB migration or separate write workflow. |

Preparation refusal, closed/unknown collection permission, failed validation,
missing/mismatched delivery, or a rejected successful native claim must not mint
successful rows. A rejected claim retains the immediate trusted predecessor
with no candidate details or changed addresses. Preserve its existing ledger.
Honest native partial-failure cleanup remains a separate existing contract:
recoverable resources do not establish success provenance, and this repair must
not erase cleanup inventory. Descendant inventory/archive refusal remains atomic;
legacy materialization's retained-cleanup failure behavior must not be silently
redefined. Provenance also does not establish independent observation, physical
ownership, capture demand, exactly-once effects, or rollback of native effects.

## Extension seam and required evidence

Keep the shared derivation seam in processor concern semantics, parameterized by
canonical address, qualified node identity, admitted typed/safe supplied values,
and provenance/posture/governing context. Preparation and descendant admission
provide their own authority/lifecycle context. Future registered runtime concerns
should flow through the descriptor registry without editing runtime or adding a
parallel catalog. Dedicated non-registry concerns retain their existing owners.
This needs a small shared function where necessary, not a new provenance service
or generalized resource framework.

Acceptance evidence must exercise the public stub reproduction, a compute/capture
container, full concern identities/classes/origins, original processor-origin
preservation, explicit-empty/default/protected values, and failure refusal.
Check prepared retention/update/deletion, authenticated plan submission, durable
reload, negotiated materialization plus descendant reporting/refresh, and native
proposal immutability. These are behavioral boundaries, not merely tuple-length
or helper-output assertions. Existing test homes include
`test_issue_1204_resource_collections.py`, `test_issue_1204_collection_lifecycle.py`,
`test_sem_218_runtime_realization.py`, `test_issue_1649_inventory_provenance.py`,
and `test_issue_1649_supervised_inventory.py`.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`,
`tools/nox_support`, `.pre-commit-config.yaml`, and the existing targeted test
selection. The configured Python 3.14 tooling environment is required; host
Python 3.12 cannot parse this checkout. Run only relevant local cases; full,
integration and fuzz suites remain CI-owned. This requirement-free issue does
not justify inventing a requirement UID. Consumer-visible correction belongs
on the existing `fix:` release path; release-please owns version/changelog edits.

## Non-goals and anti-patterns

This preflight changes guidance only. Implementation scope is runtime-owned
SEM-218 reporting for already admitted prepared portable resources and its
preservation across existing acceptance/persistence paths. It does not change
SDL syntax, membership policy, support negotiation, materialization contracts,
descendant causality, capture implementation, observation demand, deployment
topology, or downstream consumer code. No release, merge or publication occurs
in preflight.

Consumers must not fabricate rows.
Backend provenance claims do not establish authority.
Avoid capture-specific branches and template equality as origin proof.
Exact selected values do not establish author intent.
Check presence without truthiness shortcuts.
Do not replace the whole ledger or merge unchecked predecessor rows.
Keep provenance out of metadata and details.
Reuse the existing schemas, validators, projection codecs, diagnostics and commit workflow.
do not add competing versions of them or relax module-boundary policy.
