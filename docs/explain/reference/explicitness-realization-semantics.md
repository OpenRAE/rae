# Explicitness And Realization Semantics

This note is the implementer-facing architecture companion to `SEM-218`. It
records the architecture guardrails for the implementation that realizes
the spec; it is implementation guidance, **not normative**. The normative
semantic boundary — including the invariants, the phase responsibilities,
the binding gates, and the realization-status framing — lives in
{download}`specs/formal/realization/explicitness-and-realization.md <../../../specs/formal/realization/explicitness-and-realization.md>`.
Where this note's prose differs from the spec, the spec governs; where
the spec is silent and this note records detail, treat that detail as
implementer reference rather than a binding rule. Realization status is
tracked in the `SEM-200` coverage table in
[`shared-semantic-integrity.md`](shared-semantic-integrity.md); the
realization-and-disclosure concept family in
`contracts/concept-authority/concept-families-v1.json` is the native
authority for what may be realized at all.

`SEM-218` defines the difference between an author declaration that is
binding and a concern left open for backend realization (the normative
statement of those rules lives in the spec linked above). The core
engineering risk is concept conflation: treating "not specified yet",
"backend may choose", "processor must preserve exactly", and
"unsupported exact request" as the same state.

## Architecture Decisions

- Reuse the existing semantic authority stack. Explicitness semantics belong
  beside SDL validation, semantic profiles, apparatus manifests, controlled
  vocabularies, and runtime diagnostics; they must not introduce a second
  semantic registry or a second manifest family.
- Keep authoring intent, processor compilation/planning, and backend
  realization as distinct concerns. SDL authoring declares scenario
  meaning. The processor instantiates, compiles, and plans, but does not
  pick values for underspecified concerns — processor manifests carry no
  `realization_support`. The backend realizes only what the plan leaves
  to it and what its manifest declares.
- Treat exact author declarations as binding. If an author declares an exact
  requirement, downstream stages either honor it or reject the artifact with a
  structured error. Silent approximation is forbidden.
- Treat open concerns as explicit permission, not absence of validation. A
  missing exact declaration may allow realization only when the owning schema or
  semantic rule defines that field as realizable and the selected backend's
  manifest declares compatible support.
- Keep rejection semantics fail-closed and diagnostic-driven. Unsupported exact
  requirements should surface through existing `SDLValidationError`,
  `SDLInstantiationError`, or `raes_processor.models.Diagnostic` paths,
  depending on the phase where support is known.
- Carry one complete, resolved, value-free authority collection on every
  backend-facing provisioning plan. It includes closed omissions and preserves
  governing scope plus resolution source; it does not expose authoring
  designation tables or duplicate exact operation values.
- Treat the plan collection as the runtime authority for registered concerns.
  Direct-manager and control-plane execution both recompute registry
  completeness, bind the selected envelope identity, enforce capability as a
  narrowing constraint, reject closed excess state, and derive safe persistence
  plus provenance from that same collection.
- Treat HTTP callers as relays, not planners. Register the exact
  planner-produced provisioning plan through the in-process control-plane
  boundary before HTTP submission; the adapter resolves its canonical digest
  from that trusted registry, so a BACKEND or OPERATOR credential cannot widen
  modes or bounds by rewriting the request body.

## Canonical Incumbents

Issue #1200 preserves mixed constraints through the portable plan, rather than
using a weakest-child aggregate as comparison authority. The optional typed
`structure` entry records exact/open leaves, record additions and required keyed
members without duplicating operation values. Compilation uses authored
explicitness provenance, so normalization defaults are not promoted to author
constraints. Package manager/name selectors intentionally leave an omitted
architecture open; ambiguous partial identities reject before mutation.

Both direct apply and serialized/control-plane readmission consume this
descriptor. The shared structural matcher checks required membership without
depending on observation ordering; canonical concern projection still owns
typed shape, excluded fields and sensitive-value commitments. Unknown/missing
observations do not create satisfaction provenance. Numeric DNS extension codes
retain exact identity through the owning model's contextual classification.
See `test_issue_1200_mixed_runtime_constraints.py` for the positive/negative
apply pairs and `test_issue_1066_runtime_resource_limits.py` for retained
finite-domain and exact-sibling checks. Unsupported mixed shapes receive the
existing actionable authority-bound diagnostic. No new evidence demand or
backend-specific interpretation is introduced.

Build on these existing surfaces before adding anything new:

- SDL parsing and closed models: `raes.parser`, `raes.SDLModel`, and
  Pydantic `extra="forbid"` model boundaries
- scoped author intent: `raes.realization_designation`, plus the
  designation records in expansion and instantiation provenance
- static semantics: `SemanticValidator` and `SDLValidationError`
- instantiation: `instantiate_scenario()` and `SDLInstantiationError`
- shared semantic helpers: `raes.semantics.*` and
  `raes_processor.semantics.*`
- processor/backend declarations: `raes_processor.manifest`,
  `raes_processor.capabilities`, `raes_backend_protocols.capabilities`, and
  `raes_backend_protocols.manifest.backend_manifest_payload()`
- apparatus contract primitives: `raes_contracts.apparatus`,
  `RealizationSupportDeclaration`, `ConceptBinding`, and
  `RealizationSupportMode`
- contract validation: `raes_contracts.contracts.ContractModel`,
  `BackendManifestV2Model`, `ProcessorManifestV2Model`, `schema_bundle()`,
  generated `contracts/schemas/`, and fixture validation
- authority helpers: `manifest_authority`, `controlled_vocabularies`,
  `semantic_profiles`, `reference_models`, and the concept-authority catalogs
- runtime diagnostics and envelopes: `raes_processor.models.Diagnostic`,
  `raes_contracts.planning.ResolvedRealizationAuthority`, runtime
  plan/result/snapshot models, and published control-plane contracts
- workflow gates: `.ground-control.yaml`, `.gc/plan-rules.md`,
  `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`,
  `tools/check_json_artifacts.py`, `tools/check_generated_schemas.py`, and
  `tools/verify_all.py`

## Cross-Cutting Layers

The implementation must pass every layer it touches:

- SDL parser gate: variable substitution must not create hidden exact
  declarations, rename semantic identities, or smuggle realization directives
  through keys.
- SDL model gate: explicitness state must be represented in typed fields or
  existing structured extension surfaces, not in untyped `dict` side channels.
- semantic validation gate: exact declarations must be validated as exact, and
  open realizable concerns must still be checked for shape, scope, and
  ambiguity.
- instantiation gate: defaults and parameters may fill open concerns only when
  the owning semantic rule permits it; concrete scenarios must be revalidated.
- contract/schema gate: external payload shape belongs in `ContractModel`
  descendants and the coordinated hand-governed/reference-model schema
  surface. Reconcile model, schema, publication manifest, and generator parity
  in one change.
- manifest/profile gate: supported contract versions, concept bindings,
  binding scopes, realization support modes, exact requirement kinds, and
  controlled vocabulary terms must resolve through existing authority helpers.
- planner/backend boundary gate: backend support checks must compare the
  compiled requirement against backend manifest `realization_support` instead
  of local string conventions. Process-resource demands additionally compare
  against the declaration's typed resource/scope/value domains.
- provisioning-handoff gate: every applicable registered concern on a
  non-delete operation must have exactly one canonical authority entry. Closed
  concerns need no backend support but forbid added scenario state; non-closed
  concerns require matching support and the selected envelope identity.
- error-envelope gate: unsupported exact requirements and forbidden
  approximations must be reported with stable validation errors or structured
  diagnostics; do not leak raw backend exceptions or private payloads.
- control-plane gate: any runtime-facing realization result must pass existing
  request-size, authentication, authorization, audit, idempotency, and published
  response-model validation. An operation-bearing provisioning request must
  also match an exact planner-produced plan registered outside the HTTP relay
  surface; request authentication and idempotency fingerprints are not planner
  attestation.
- persistence and observation gate: realized choices may be recorded only in
  portable snapshot/result/provenance envelopes. Do not persist secrets,
  bearer tokens, credentials, backend-native objects, or unredacted tracebacks.
- host/OS exposure gate: exact requirement values, credentials, and backend
  tokens must not be passed through process argv, logs, audit details,
  diagnostics, JSON fixtures, or semantic-profile artifacts when they may carry
  sensitive material.

## Extensibility Seam

The seam is a typed realization requirement classifier plus the existing
manifest support declaration, not a backend-specific branch. Future variation
should be added by extending the governed requirement-kind vocabulary and the
`RealizationSupportDeclaration`/manifest contract inputs, then regenerating and
validating schemas.

Keep the classifier independent of any one backend. The next obvious change is
additional exact requirement kinds for other artifact families; that should
require adding governed terms and shared semantic checks, not rewriting planner
or conformance call sites.

Explicit root delegation reaches planning through the injected
`apparatus_realization_default` resolver. Its current fallback is closed; a
future typed apparatus-default contract can supply a different choice without
changing SDL cascade rules or backend implementations.

## Portable Process-Resource Limits

The `process-resource-limits` concern applies SEM-218 to the complete
`Node.runtime.operational_policy.resource_limits.process_limits` collection.
Its semantic identity is `(resource, normalized subject, scope)`; descriptions
and native backend spellings are excluded. Exact comparison is set-exact, so a
missing, substituted, or excess record fails. A constrained soft/hard variable
retains its finite `allowed-values` domain through instantiation and compilation
and the realized leaf must belong to that domain.

The normalized subject is also the inventory-matching contract: every active
name, pid, parent, role, user, group, command, redaction, and working-directory
selector must match one declared `runtime.processes` record. A redacted command
is omitted and requires another stable projected selector; raw command content
cannot be supplied and then erased from semantic identity.

Support is declared through typed `process_resource_limits` entries on the
existing `RealizationSupportDeclaration`, not through the free-form
`constraints` map. Each entry bounds one portable resource by process/subtree
scope, minimum/maximum finite values, and whether `unlimited` is supported.
Exact and constrained planning checks every compiled demand against that
domain. Open planning additionally requires authored open permission,
`OPEN_REALIZATION`, and a non-empty typed apparatus domain. The selected
realization-envelope configuration must repeat the exact typed domain from the
compatible global declaration. Planning and runtime evaluation use only that
intersection, preventing capability advertised for one backend mode from
authorizing another mode.

Every accepted result requires a `process-resource-limits` observation
capability and a matching value-free runtime observation with configuration
scope and `guest-observed` strength. This represents effective inside-workload
readback. Desired-payload echo, runtime inspect output, VM allocation, cgroup
capacity, or datastore `memory_locked` state is insufficient. Backends without
both materialization and effective readback remain honestly unsupported.

## Compute Kind And Realization Mechanism

The canonical node kinds are `compute` and `switch`. `compute` describes what
the scenario needs structurally; it does not select a virtual machine,
container, physical device, or emulator. Mechanism intent is instead an
addressed `compute-substrate` entry in `Scenario.realization.constraints`.
Omitting that entry keeps the compute node portable. Exact and constrained
entries retain their governed domain through instantiation, compilation, and a
separate plan constraint; `supported_node_types` remains only the provisioner's
resource-kind claim.

Runtime selection is a separate observation. The backend must bind the observed
governed mechanism to the operation, selected envelope, and configuration. A
plan echo or provisioner handle is not evidence. OCI and libvirt modes use
daemon readback; the in-process reference mode reports an extension term and is
not presented as a second native isolation mechanism. The runtime gate rejects
missing readback, weak evidence for bounded demand, envelope/domain mismatch,
and unverified execution binding before snapshot persistence.

Legacy `type: vm` is not treated as a generic compute alias. Strict authoring
rejects it. Explicit migration preserves its historical exact meaning by
emitting `type: compute`, an exact `virtual-machine` substrate constraint, and
`legacy-node-type-vm` provenance; collisions are fatal.

## Scoped Default Cascade

The one author-facing inherited-default surface is the optional scenario-root
`realization` block. It carries a `default` posture and zero or more typed scope
entries. Each scope identity is a namespace tuple plus a canonical RFC 6901
field pointer; dotted paths, wildcards, and JSONPath are not accepted author
syntax.

Resolution preserves these distinctions:

- an explicit exact, constrained, or open leaf is authoritative;
- otherwise the most-specific concrete scoped posture wins, independent of
  source order;
- `unspecified` inherits an enclosing concrete posture, or delegates the root
  decision to the selected-apparatus resolver;
- omitting `realization` preserves the legacy closed behavior and is not the
  same state as explicit root delegation.

Composition rewrites declaration pointers through the import symbol map and
qualifies designation records with the import namespace. A module default can
therefore govern that module's declarations without leaking to its host or a
sibling module. The authoring block itself is removed during expansion and
instantiation; typed records travel in the existing phase-provenance aggregates
and then in compiled realization requirements.

Open affects only registered realization concerns. It does not relax closed
Pydantic shapes, invent topology, bypass references, or make every absent
optional field backend-realizable. The apparatus support mode remains a
capability disclosure rather than author intent.

## Authoring Specificity

`classify_authoring_specificity()` is the DSL-115 helper for reviewing
specificity across existing owned surfaces. It reuses the SEM-218 classifier
for exact and constrained authored values, and it records open or
underspecified concerns only when the owning caller supplies the explicit path
in `admitted_open_paths`.

Do not treat a missing field as open by default. The helper's admitted-open
paths are authoring metadata for surfaces whose SDL, contract, or semantic rule
already allows an underspecified form; they are not backend-realization
permission and do not replace manifest `realization_support`, realization
envelopes, or experiment-core contracts.

## Part 2 Implementation Boundary

The typed compiler emission and planner gate must preserve the classifier output
as runtime-model metadata owned by `raes_processor.models.RuntimeModel` and
emitted by `raes_processor.compiler`. The planner should consume that compiled
metadata directly; it must not re-walk SDL YAML, rerun the classifier, infer
exactness from backend capability failures, or treat the backend manifest as an
author-intent source.

Planner rejection belongs in the existing `raes_processor.planner.plan()` /
`ExecutionPlan.diagnostics` path. Unsupported exact or constrained requirement
kinds and open demand without explicit `OPEN_REALIZATION` support should be
reported as stable `Diagnostic` objects that name the compiled
resource address, SDL field path or equivalent field identifier, requirement
kind, and missing `realization_support` capability. Do not introduce a
SEM-218-specific exception hierarchy or throw from normal planning for this
case.

When a backend publishes a finer realization envelope, project that offer onto
the compiled open concern paths and evaluate it with the canonical
`subsumes(offered, requested)` relation. Keep unrelated offered bindings out of
the projection so a constraint on an exact, unrelated field cannot narrow the
author's open concern by accident.

Keep realization-support matching as one manifest-bound helper over
`BackendManifest.realization_support` / `RealizationSupportDeclaration`.
`domain`, `supported_exact_requirement_kinds`, and
`supported_constraint_kinds` are currently opaque non-empty strings, so the
match is exact string membership plus support-mode compatibility. If compiled
explicitness metadata is added to plan payloads or published contracts, it must
go through the existing `ContractModel` / schema-generation path; otherwise keep
it model-side like existing compiler provenance metadata.

## Complete Runtime-Configuration Coverage

Every top-level `RuntimeConfiguration` field has an executable ownership and
enforcement disposition. The canonical concern registry splits mixed runtime
objects at semantic boundaries, carries those paths through compiled and
resolved authority, and validates returned values against the owning closed SDL
type. Configuration concerns exclude readiness, run outcomes, live counters,
loaded state, evidence references, and similar observations before posture is
classified.

Exact runtime support is concern-specific: a backend needs the generic exact
capability, the exact concern-kind token, and a matching observation
capability. Open and constrained concerns use the same manifest and envelope
admission path. None of those declarations replaces independent readback, and
a backend must remain unsupported when it can only echo submitted plan values.

Closed collection authority applies to the scenario-significant managed
projection, not the complete native operating-system inventory. Base-image
packages, transitive dependencies, incidental daemons, native handles, and
measurement apparatus remain on their existing substrate or evidence owners
unless deliberately promoted into the corresponding runtime concern.

## Gotchas And Anti-Patterns

Avoid:

- using `realization_support` as a substitute for authoring semantics
- treating `open-realization` as permission to ignore exact declarations
- treating missing data as equivalent to backend freedom
- accepting dotted, partially tokenized, wildcard, or JSONPath scope targets
- silently downgrading an exact requirement into a constrained or best-effort
  realization
- adding a second exception hierarchy, schema registry, vocabulary table, or
  manifest contract for explicitness semantics
- duplicating support checks in compiler, planner, conformance, and backend
  adapters instead of sharing a pure helper
- stuffing explicitness flags into `constraints` strings without a governed
  schema, vocabulary, or profile rule
- treating semantic profiles as backend capability profiles, or backend
  capability profiles as semantic profiles
- putting normative semantics in `docs/` or implementation constants instead
  of `specs/` and `contracts/`

## Companion Scope

This note is implementation guidance for the SEM-218 normative spec at
{download}`specs/formal/realization/explicitness-and-realization.md <../../../specs/formal/realization/explicitness-and-realization.md>`.
It does not itself define exact-requirement-kind vocabularies or change
manifest payloads — those are governed by the spec and by the
controlled-vocabulary / reference-model authorities. The SEM-218 coverage row
is `active`: the classifier, typed scoped designation cascade, compiler carrier,
planner gate, runtime non-approximation/disclosure gate, and snapshot
provenance delivery are implemented together. Treat the prose above as
architecture guidance for those surfaces and the spec as the binding contract.
