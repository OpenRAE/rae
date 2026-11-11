# Dependent declaration variation: architecture preflight

Issue #1733 is the contract; this run has no formal requirement UID.
This note gives implementation guardrails, not an implementation plan or a
claim that the feature exists. No new ADR is needed: [ADR-084](adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md)
already assigns typed selection to SDL and complete trial admission to the
processor. [Variation points](../../specs/sdl/variation-points.md) remains the
normative language authority.

## Decision and boundaries

Extend the existing closed structural target vocabulary. Authors explicitly
select dependent declarations out and couple choices through existing
`requires` / `excludes` relations. Keep `nodes.presence` semantics: it removes
only the node and its same-key infrastructure entry. Never infer a dependency
cascade, silently repair references, or weaken whole-scenario admission.

The necessary selection units are:

| Authored section | Selection unit and constraint |
| --- | --- |
| `accounts`, `content` | Presence of the whole keyed declaration. Existing node-reference slots still support explicit retargeting. |
| `persistent_volumes` | Whole-volume presence, plus membership of existing consumer rows on a retained shared volume. |
| `generated_artifacts` | Membership of existing consumer rows; whole-artifact presence is also needed when removal would leave an orphan. |
| `relationships` | Presence of the whole relationship, preserving endpoint and subtype rules on retained relationships. |
| `propositions` | Presence of the whole proposition. Do not trim subjects or change quantifiers/thresholds implicitly. |
| `evidence_requirements` | Presence of the whole requirement. Do not silently narrow source/scope, capture obligations, or disclosure policy. |

Removing a declaration does not remove its incoming references. Accounts may
still be used by participants or identity domains; propositions by conditions,
assertions or objectives; evidence requirements by propositions and capture
contracts. Surviving references must resolve. Existing typed retargeting and
collection slots can express some adjustments; unsupported adjustments remain
explicit refusals, not permission for a generic deletion engine. This issue
does not promise that every arbitrary dependency graph is expressible.

Shared consumers are records, not node references. Their existing identity is
`(node, mount_destination)` within a resource (`stateful_resources.py`). A
consumer selector must resolve the node canonically and identify an exact
existing row within the owning resource. Preserve its access mode, selected
outputs, payload and source order. Reject unknown, duplicate or ambiguous
selectors. Neither list positions nor variation member labels are identity.
There are no consumer declaration IDs in the declaration index: do not invent
fake qualified references, require new IDs on existing rows, or encode mount
paths as dotted SDL addresses. Any selector shape must be closed and reuse
the existing node-resolution and mount-path validation rules.

## Incumbents and extension seam

Paths below are relative to `implementations/python/packages/` unless stated.

| Boundary | Canonical incumbent and required reuse |
| --- | --- |
| Typed targets and members | `raes/variation.py`, `raes/variation_structure.py`, including `STRUCTURAL_TARGET_SPECS`, strict Boolean presence, closed `SDLModel` fields and member/slot compatibility. Keep old node and runtime-inventory member forms and canonical bytes compatible. |
| Identity and composition | `raes/_declarations.py`, `_declaration_index.py`, `_identifiers.py`, and `raes/composition/_references.py`, `_terminal.py`, `_sections.py`. Compose before selection; rewrite owner references, consumer node selectors and relation points through export/private symbols. Preserve local member labels and mount paths. |
| Selection and conflicts | `raes/selected_structure.py`, `raes/selected_scenario.py`. Resolve all writes against the unchanged admitted family, validate the complete write set, then apply it to an independent payload. |
| Semantic admission | `raes/family_admission.py`, `raes/validator/_variation.py`, `_variation_satisfiability.py`, and `raes/instantiate.py`. Reuse family reconstruction, bounded relation satisfiability, and the full `SemanticValidator`. |
| Field evidence | `raes/_selection_provenance.py`, `phase_contracts.py`, `_declaration_sources.py`. Removed records lose only their owned evidence; retained records keep constraints and source attribution. |
| Authoring tools | `raes/_language_metadata.py`, `_language_structural_variation.py`, `_language_references.py`, and `language_service.py`. Completion and navigation must use the same owner/candidate restrictions, including incomplete input. |
| Trial lifecycle | `raes/experiment_selection.py`, `raes_processor/trial_compiler/realization_admission.py`, `readmission.py`, and `raes_processor/trial_realization.py`. Existing member outcomes, typed target descriptors and public selection carry the extension. |

The extension seam belongs in the existing structural slot specifications:
explicit owner section/kind, member shape, and selection operation, with a
consumer-row identity rule where needed. Replace the current assumption that
every structural owner is a node and every non-node-presence alternative is
runtime inventory. Share that knowledge across validation, canonical target
calculation, composition and editor support. A future reviewed declaration
presence slot should reuse this operation; it must not require another
selector pipeline. Registry membership or reference targetability alone must
never grant variation write permission. Do not create a general patch API,
plugin registry, parallel schema family, or resource repository/service layer.

Presence conflicts must extend to each supported owner and its descendants,
including whole-resource removal versus consumer edits and declaration removal
versus existing reference/collection writes. Equal writes are idempotent;
different writes to the same canonical target fail. A reference *to* an absent
node is not an ownership descendant: an explicitly removed declaration or
consumer may validly refer to that node in the unchanged family. Use structured
identity tokens, not string prefixes: `host` and `host.child` can be distinct
qualified declaration names. Point names and iteration order cannot decide
which write wins.

Consumer filtering moves list positions. Extend existing provenance remapping
by stable row identity for capability constraints, parameter derivations,
realization designations/constraints and explicitness. Preserve escaped JSON
pointers and composed names. Do not discard surviving evidence to make phase
validation pass. Keep incremental validation dependency tracking in
`raes/_incremental_reuse.py` sound when new sections are read; do not mutate
objects whose identity backs cached validation.

## Security and validation boundaries

| Layer the selected artifact crosses | Required behavior |
| --- | --- |
| Source parsing and import trust | Use `raes/parser.py`, `_yaml_loader.py`, source token/graph limits and `composition/_import_admission.py`. No second YAML loader, external lookup, callback or secret read during selection. Preserve bounded input and alias handling. |
| Model and published schema shapes | Keep `Scenario`/`ExpandedScenario`, target-member discrimination and published JSON Schema in agreement. The current `AlternativeVariationPoint` schema conditional distinguishes only node presence from inventory; changing Python unions alone is insufficient. Unknown slots, extra fields and coerced presence values fail. Instantiated/materialized scenarios and snapshots still forbid unresolved variation. |
| Selection authority | The closed slot grants the write, not an arbitrary owner/path supplied by a caller. Require exact owner kind and candidate membership in the original family. `ExpandedScenarioBindingTargetResolver` must retain family/digest/point/target/owner/outcome checks; structural choices remain excluded from scalar bindings. No new HTTP/MCP endpoint, authentication policy or authorization bypass is needed. Existing transport authority remains in force. |
| Complete semantic admission | Validate only the completed joint selection as a concrete scenario. Do not require a removal to pass whole-scenario validation in isolation before its coupled removals apply. Local relation satisfiability is not proof that every selection is semantically valid, nor ADR-086 solver evidence or backend feasibility. Any invalid requested trial rejects the complete plan; no skipping or resampling. |
| Resource and host-path safety | Reuse `stateful_resources.py` and `_stateful_resource_references.py`: contained POSIX paths, OS suitability, mount uniqueness, access modes, dependency references and artifact consumption checks. A retained volume requires at least one consumer. A retained artifact requires consumption; SSH consumer-selected outputs must remain covered. Removing the last file consumer is valid only if the remaining artifact satisfies all existing rules. |
| Secrets and environment shapes | Reuse `runtime_environment.py`, `runtime_generated_value.py` and `resolve_consumable_generated_artifact_output()`. Surviving `value_from`, env-file, content `text_from` and proposition `expected_from` bindings must resolve. Preserve literal/source exclusivity, redacted classification for generated secrets, the `operator_secret` restriction, producer-private output restrictions, content sensitivity and portable env-file names. Do not turn references into values or select out derived projections directly. |
| Compiler/planner and runtime | `raes_processor/compiler/stateful_resources.py` derives mount/environment/content projections from the selected scenario. `planner/stateful_admission.py` validates their closed delivery-mode shapes and exact source/target joins. Removing a node must not leave a projection for it. Selection performs no generation, mount, subprocess or deployment; no new argv/environment credential exposure is justified. Existing backend capability/materialization gates still apply. |
| Errors and operational logs | Reuse `raes/_errors.py`, `_model_diagnostics.py`, compiler diagnostics, and [ADR-116 policy](../develop/exceptions-and-logging.md). Value-object validators use `ValueError` for Pydantic conversion; public selection refusal uses `SDLSelectionError` under `SDLError`. Keep compiler errors value-free and CLI/MCP unexpected-error boundaries sanitized. Never expose raw Pydantic inputs, exception chains, consumer payloads or secret values. Use `raes_contracts.operational_logging` if logging is needed; no new exception hierarchy or logging configuration. |
| Identity, persistence and replay | Reuse `raes/canonical.py`, shared canonical JSON, phase provenance, trial seals and source-aware readmission. Keep the input family unchanged and bind selected content to recorded selections. Reconstruct/revalidate through public APIs; an admission flag or deserialized model is insufficient evidence. Selection changes desired declarations, not persistent-volume data, lifecycle policy, archival records or runtime cleanup. |

## Contract and verification guardrails

Normative slot/member documentation belongs in `specs/sdl/variation-points.md`
and reference semantics in `specs/sdl/references.md`; this note is not a second
language specification. The published authority is `contracts/schemas/`, with
`raes_contracts/contracts/bundle.py::schema_bundle()` kept identical. Follow
ADR-061 and the existing schema-publication manifest/entry ledger for every
changed schema, including embedded copies. Keep schema-only positive/negative
fixtures aligned with Python acceptance. Preserve legacy reference alternatives
with omitted target kind and unchanged static-family behavior.

The existing regression patterns are
`test_issue_1625_structural_variation.py`, `test_sce_002_selected_scenario.py`,
`test_scenario_family_admission.py`, `test_stateful_realization_resources.py`,
`test_issue_1074_generated_artifact_env_consumers.py`, and the trial compiler /
realization tests under `implementations/python/tests/`. Required evidence:

- present/absent coupled selections across all seven sections;
- retained shared rows and multiple mounts on one node;
- last-consumer and SSH-output failures;
- dangling transitive references;
- wrong-owner and unknown selectors;
- conflicting and identical writes in reversed order;
- composed private owners;
- provenance after row compaction;
- published-schema rejection;
- compile/replay through the public trial path with no partial plan on failure.

Test resource admission and sanitized error surfaces, not only the immediate
selector result.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, the existing
`tools/check_repo_policy.py`, schema publication/generated-schema checks,
catalog parity checks and canonical nox lanes. Preserve package import
directions and the source-file cap. Run only targeted local checks; full suites
belong in CI. Do not invent a requirement UID for this issue, hand-edit release
versions/changelogs, or amend accepted ADRs to document routine slot additions.

Non-goals:

- automatic dependency discovery or pruning;
- arbitrary field patches;
- new proposition or evidence semantics;
- generated-output pruning;
- arbitrary runtime inventory expansion;
- experiment grouping or randomization;
- a new solver;
- runtime fact-driven topology;
- backend-specific selection;
- storage destruction.

The implementation owns typed declaration/consumer selection and its existing
cross-cutting integrations; execution, persistence and observation authorities
remain with their current owners.
