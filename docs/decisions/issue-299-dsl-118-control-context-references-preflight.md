# Issue 299: Participant control-context references preflight

Date: 2026-10-27. Requirement: DSL-118 (DRAFT).

This note sets architecture guardrails for the supplied issue, including its
experiment-factor scope. It does not define syntax, implement support, or give
an implementation sequence. No new ADR is needed. Existing decisions cover the
boundaries; the missing work is their connection through the SDL pipeline.

## Ownership and identity

[ACT-620](../../specs/supply-chain/participant-control-context-assets.md) already
owns immutable asset versions, applicability, lifecycle, content commitments,
and selection/disclosure records. Its implementation is
`raes_contracts/contracts/participant_control_context.py`, with trusted agreement
checks in `raes_contracts/participant_control_context.py`.
Use `ParticipantControlContextAssetReferenceModel` and
`control_context_asset_reference()` for the exact
`asset_id`, `asset_version`, and `asset_digest` triple. Do not create a second
instruction/policy descriptor or reference schema.

An authored reference expresses selection intent. It is not an authorized
ACT-620 selection record: the latter needs trusted run, participant, episode,
generation, audience, authority, and state-cut context. Static compilation
checks local resolution, exact commitments, and declared scope. It cannot
certify live lifecycle, role membership, authorization, or delivery from
authored claims. Those checks remain at the existing trusted consumer boundary.
Missing trusted context cannot become a successful full-validation claim.

An asset with kind `policy` contains guidance. It is not an executable
`MixedControlPolicy`, `ControlArtifactReferenceModel`, exposure/IFC policy,
API-409 permission, or ADR-108 control mechanism. Observation boundaries
already classify instructions and scaffolds; asset kinds do not replace that
visibility model. Issue #300 owns decision-time exposure. Declaring, importing,
attaching, or selecting an asset must not reveal it to a participant.

Keep these identities distinct: local declaration name, asset id/version,
descriptor digest, payload checksum, associated-set digest, module digest,
SDL semantic digest, participant implementation/configuration digest, and
delivery occurrence. ACT-620 hashes the complete descriptor, including null
fields, with `canonical_contract_digest()`. A checksum covers exact payload
bytes. Neither proves authenticity, permission, or participant understanding.
Versions are opaque; no ordering, `latest`, range selection, or fallback.

## Composition, scope, and compilation

Use ordinary SDL declaration/reference machinery for local names and imports.
Do not turn existing `content`, `generated_artifacts`, behavior `extensions`,
or free-form metadata into an asset catalog. Those surfaces have other owners.
Any declaration map needed for authored references is a symbol table over
ACT-620 identities, not another asset registry or lifecycle authority.

Namespace local declaration names and authored participant/behavior references
through existing symbol maps. Preserve the referenced immutable descriptor,
including its applicability, provenance, locator, version, and digest. Do not
run a generic recursive string rewrite or variable substitution over a pinned
descriptor. Rewriting its participant addresses changes its descriptor digest.
An imported asset's applicability must still match the composed participant:
use valid canonical addresses or the existing trusted role-applicability path;
an unmapped source address is an incompatibility, not permission to weaken scope
or recompute an authored pin. Module exports control symbol visibility, not
participant disclosure.

Reuse `Agent.effective_role()` and `select_participants()` for authored scope.
Affiliation, role, participant, controller, implementation, and deployment tenant
are distinct. A behavior specification selecting several participants must
check each resulting participant binding. Direct and reusable declarations
need one deterministic conflict rule: reject competing selections unless an
explicitly governed combination rule exists. Never derive precedence from
asset kind, declaration order, module order, or last-write-wins behavior.
Sharing one exact version across participants is valid; it does not merge
their selections or exposure decisions.

Compilation must retain exact asset references and resolved participant scope
in the existing participant/behavior runtime projections. A reference kept only
in an unvalidated `spec` dictionary, annotation, or display string does not meet
the pipeline contract. Preserve the content commitment transitively through the
descriptor digest and exact descriptor resolution. A locator alone is not a
commitment. Authoring, expanded, instantiated, directly admitted, and
deserialized artifacts must receive the corresponding checks. Do not trust a
caller-set validation flag or unchecked `model_copy(update=...)`.

## Experiment-factor seam

[ADR-094](adrs/adr-094-authoritative-cross-plane-experiment-bindings.md) owns
participant bindings. Reuse the selected participant manifest's
`configuration_registry`, canonical target id, declared scalar type,
sensitivity, and owner validator id/version. The existing `BindingValue` admits
scalars or secret-reference identities; it does not admit an asset object.
Use a bounded literal string naming an exact declared asset reference, with
one unambiguous resolution to the ACT-620 triple. Do not serialize JSON into the
string, use a mutable URI, or repurpose `SecretReferenceId` for private context.

The trusted owner validation seam must join that string to the exact available
asset reference and intended participant scope. A generic scalar shape check
does not establish that join. If this feature requires the owner validator,
absence of that validator must fail admission; the incumbent complete-config
hook is optional for other configurations. Do not import validators named in
untrusted documents or execute asset content as a validator.

Reuse `validate_experiment_binding_targets()`, selected-manifest pin checks,
`realize_participant_configuration()`, and
`trial_compiler/bindings.py::entry_participant_configurations()`.
Check factor/level/condition ownership, selected implementation and manifest,
aliases before canonical-target collision checks, defaults, exact scalar types,
and the complete configuration. Equal duplicate targets also fail.
The existing sealed `AdmittedTrialEntryModel` retains the complete result;
`realize_admitted_trial_entry()` passes it to the existing run producer.
Preserve descriptor, origin, manifest/configuration digest, exact asset
selection, and run joins. A factor recorded only as a descriptive parameter or
a configuration that never reaches the participant selection is insufficient.
Bind resolution to the retained admitted declaration or an existing governed
reference carrier. The same string must not resolve to a different asset after
export, reload, or a change to a consumer's current catalog.

Do not mutate a shared scenario family or recompute a configuration from current
defaults after admission. Participant-plane selection belongs in the admitted
configuration and its provenance. Scenario-plane changes use the public SDL
selection/instantiation authority instead. Do not infer a plane from a target
name or permit both paths to write one selection silently. Asset resolution
must remain stable for the admitted trial; lifecycle eligibility is rechecked
by the authorized consumer at use time. Reject an invalid trial through the
existing atomic whole-plan failure path, with no partial result or skipped row.

The extension seam is the existing owner registry and versioned validator,
plus explicitly supplied exact asset resolution. Another participant, asset
version, target, or approved consumer must not require a new binding plane,
asset-kind-specific compiler branch, global registry, or run type.

## Cross-cutting gates and canonical incumbents

Package paths below start at `implementations/python/packages/`. These gates
constrain the design; they do not expand #299 into runtime implementation work.

| Layer and existing owner | Required treatment |
| --- | --- |
| Source and closed shapes: `raes/parser.py`, `_yaml_loader.py`, `_source_validation.py`, `_mapping_scopes.py`, `_base.py`; `raes_contracts/json_ingress.py`, `contracts/base.py` | Preserve source byte/depth/alias bounds, duplicate and normalized-key collision rejection, literal declaration keys, closed models, count/string limits, and non-finite-number rejection. New declaration maps must agree with parser and schema key classification. Contract JSON uses the existing bounded parser. No second YAML/JSON loader, permissive dictionary, or variable-defined declaration key. |
| Imports and supply chain: `raes/composition/`, `_module_symbols.py`, `_module_declarations.py`, `module_registry/` | Reuse confined import admission, budgets, exports/private symbols, lock records, digest/signature/trust checks, and provenance. Module version constraints do not become asset version constraints. Import trust does not authorize an asset's disclosure. No new downloader, registry, cache, or lockfile. |
| References and semantics: `raes/_declarations.py`, `_reference_targetability.py`, `_language_metadata.py`, `_language_references.py`, `validator/`, `semantics/participant_behavior/` | Resolve through the existing index and owning typed reference rules. Completion, navigation, semantic validation, composition, and compiler resolution must agree. Make an explicit reference-purpose eligibility decision; do not classify an asset as a runtime resource merely to make it navigable. Reject unknown, ambiguous, conflicting, or incompatible references. |
| Instantiation and identity: `raes/instantiate.py`, `_behavior_authoring.py`, `phase_contracts.py`, `canonical.py`; `raes_processor/compiler/participant_behaviors.py`, `models/behavior_resources.py` | Preserve variable checks and revalidation after substitution and direct artifact admission. Keep immutable asset pins out of text substitution. Use existing canonical profiles and typed runtime projections. Changed authored selections affect scenario meaning; declaration-free legacy documents must retain their existing canonical bytes. No ambient lifecycle lookup in canonicalization. |
| Content and lifecycle: `raes_contracts/participant_control_context.py`, `associated_artifacts.py`, `uri_safety.py` | Reuse exact-version/digest resolution, trusted lifecycle/authority/cut checks, and `validate_control_context_asset()` with its supported parent, manifest, bounded readers, checksum and size checks. The URI is inert; safe URI syntax does not authorize fetching or prevent SSRF. Static reference validation makes no byte-verification claim without bytes. No filesystem traversal, credential lookup, or network acquisition during validation. |
| Authentication and exposure: `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_api_participant_retrieval.py`; `raes_contracts/contracts/participant_context.py`, `participant_decision_surface_exposure_v2.py`; `raes_processor/models/participant_exposure_authority_v2.py` | Preserve authenticated target/run identity and independently trusted participant/episode/generation/audience bindings. Reuse context transformations, marking inheritance, exact-cut exposure and crossing gates. Administrative retrieval without a governed crossing resolver is not a participant release path. Asset applicability and valid SDL grant no entitlement. No new route, role, token, or auth configuration is required. |
| Configuration, secrets, and OS: `raes_contracts/contracts/experiment_bindings.py`, `participant_configuration.py`, `secret_references.py`; `raes/runtime_environment.py`, `runtime_configuration.py`, `runtime_generated_value.py`, `runtime_values.py` | Keep references portable and non-sensitive; private bytes stay in consumer storage. Asset existence, hashes, locators, and provenance may also require protection. No environment binding or subprocess is required. A later approved adapter must retain unique env names, literal/`value_from` exclusion, sensitivity/provenance, explicit redaction, and generated-output checks. Never put private context or credentials in argv, shell text/tracing, environment dumps, public temporary files, or diagnostic output. Secret-name heuristics are advisory, not a security gate. |
| Errors and observability: `raes/_errors.py`, `_model_diagnostics.py`; `raes_contracts/diagnostics.py`; `raes_processor/trial_compiler/models.py`; `raes_runtime/control_plane_api/_responses.py`, `control_plane_audit.py` | Reuse SDL stage exceptions, collect-all semantic checks, bounded source diagnostics, `CompilationFailure`, `Diagnostic`/`Severity`, and `portable_diagnostic_payload`. Missing/stale/incompatible references are fatal, not warnings. Keep resolver/infrastructure failure distinct from expected refusal. Shared CLI/MCP/HTTP adapters retain coarse redacted error envelopes. Bounded messages are not automatically sanitized: never interpolate private values, Pydantic inputs, full rejected objects, or chained exception text. Use existing audit events; logging proves no delivery. No new logger or exception hierarchy. |
| Persistence and release: `raes/canonical.py`; `raes_contracts/admitted_trial_plan_ingress.py`, `contracts/experiment_run.py`, `experiment_evidence.py`; `raes_runtime/control_plane_store.py`, `control_plane_store_local_codec.py`, `control_plane_store_records.py` | Reuse admitted snapshots, sealed trial entries, run provenance and artifact/evidence references. Re-admit on load and preserve exact selection joins. Live delivery retains existing revision/history-head checks, atomic commits and actor-scoped idempotency. No asset database, sidecar journal, or private content in portable records. Withdrawal must not rewrite historical selections or imply erased participant knowledge. |

## Publication and evidence boundaries

Normative language belongs in `specs/sdl/`; ACT-620 remains the asset authority.
Published schemas under `contracts/schemas/` are hand-governed authority under
ADR-009/061. Keep `schema_bundle()`,
`tools/generate_contract_schemas.py`, dependent SDL phase schemas and generated
bundles identical to that authority. Record each changed contract's
`last_change` hash under `contracts/schema-publication/entries/`, routed by
`contracts/schema-publication-manifest.json`. Preserve existing contract wire
meanings and schema stability rules; no generator-only schema change.

Use existing conformance registration and fixtures, schema parity/publication
checks, JSON artifact and requirement-tracing checks, and the example library
catalog. Capability claims in `raes_contracts/manifest_authority.py` must match
actual supported consumption. Do not add a new reusable-asset trust family
casually: ADR-071 policies require complete family coverage. The incumbent
associated-artifact mechanisms already cover the content bytes.

Evidence must cross boundaries, not stop at model acceptance: local and imported
references; shared assets and distinct participant selections; intentional
withholding; namespace collisions/private exports; same-version changed
descriptor, missing/ambiguous/incompatible references; post-substitution and
direct-artifact rejection; canonical and serialization round trips; and a
factor-to-sealed-trial-to-run witness for exact participant asset selection.
Include absent owner validation, conflicting direct/reusable/factor selections,
stale or withdrawn use, and safe error output. Preserve existing exposure tests
without claiming #299 implements delivery or runtime enforcement.

Relevant existing regression homes include `test_act_620_control_context_*.py`,
`test_sem_208_participant_behavior.py`, `test_sdl_module_registry.py`,
`test_language_service.py`, `test_sdl_diagnostic_boundary.py`,
`test_sdl_canonicalization.py`, `test_instantiated_scenario_schema.py`,
`test_experiment_bindings.py`, and `test_issue_1626_trial_participant_bindings.py`
under `implementations/python/tests/`. Select only relevant modules/cases locally.
Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/check_repo_policy.py`, and file-targeted pre-commit hygiene/secret checks.
Set `RAES_REQUIREMENT_UID=DSL-118` when needed. Full suites stay in CI/CD.
Design guidance does not activate the requirement or establish IMPLEMENTS/TESTS
fulfillment. Examples, reference navigation, publication records, and migration
guidance must describe the same admitted syntax and disclosure limits.

## Non-goals and anti-patterns

No executable policy or prompting language, prompt precedence/composition,
template execution, automatic permission, participant-specific framework,
asset lifecycle redesign, decision-time exposure implementation (#300),
secret resolver, transport, storage service, scheduler, or parallel workflow.
No raw instruction text embedded in SDL, configuration literals, logs, or
portable evidence. Do not disguise guidance as observed truth, tool output,
scoring material, a generated runtime resource, or executable control.
Reuse the existing layers and add only the authored reference semantics and
their checked passage, including the required participant trial binding.
