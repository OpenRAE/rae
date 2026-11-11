# Explicitness and realization semantics

Public runtime strings keep their authored constraints after parameter values
are bound. Portable `parameter_derivations` name typed inputs and literal text.
Imports qualify each input name. Admission rebuilds the selected output and
checks it against the field. The runtime validator checks the path, name or
address too.

A parameter with no finite domain compiles as a processor-origin literal for
the selected binding. It grants no right to choose another string. A finite
whole-field parameter keeps its full domain. A string with one finite input
keeps the finite set of outputs. Repeated uses of that input stay correlated.
Multiple independent finite inputs fail closed until a contract can express
their joint relation. The compiler does not expand a Cartesian product.

The mailbox owner permits capture of derivations for its public address. This
permission does not publish secrets or other classified settings. The compiler
must use the registered safe projection. Backend support, observation and checks
against silent approximation still apply.

This note explains how to implement `SEM-218`. It is guidance, **not normative**.
The spec defines the rules, phase roles, binding gates and realization status:
{download}`specs/formal/realization/explicitness-and-realization.md <../../../specs/formal/realization/explicitness-and-realization.md>`.
The spec governs any conflict with this note. Details absent from the spec
remain guidance. The `SEM-200` coverage table in
[`shared-semantic-integrity.md`](shared-semantic-integrity.md) tracks status.
The realization-and-disclosure family in
`contracts/concept-authority/concept-families-v1.json` governs what may be realized.

`SEM-218` separates binding author declarations from choices left to the backend.
Keep four states distinct: not specified yet, backend may choose, processor must
preserve exactly, and unsupported exact request.

## Architecture decisions

- Reuse the existing authority stack. Keep explicitness rules beside SDL
  validation, semantic profiles, apparatus manifests, vocabularies, and runtime
  diagnostics. Do not add a second semantic registry or manifest family.
- Keep author intent, processor work, and backend realization distinct.
  SDL declares scenario meaning. The processor instantiates, compiles, and plans.
  It does not choose values for concerns left open. Processor manifests carry no
  `realization_support`. The backend makes only choices that the plan permits
  and its manifest supports.
- Treat exact author declarations as binding. Later stages must honor an exact
  requirement or reject the artifact with a structured error. They must not
  silently approximate it.
- Validate open concerns too. A missing exact declaration grants freedom only
  when the owning schema or rule allows a backend choice for that field.
  The selected backend's manifest must also declare compatible support.
- Reject unsupported exact requirements through existing `SDLValidationError`,
  `SDLInstantiationError`, or `raes_processor.models.Diagnostic` paths,
  depending on the phase where support is known.
- An authored-empty open concern can plan without observation support.
  Omission or an empty report without a matching observation means no added
  member. It produces no provenance. Reported members and matching observations
  still need full corroboration.
  Author observation demands remain binding.
  Failed apply inventory remains available for cleanup under existing authority and sanitization checks.
- Each provisioning plan sent to a backend carries one complete, resolved
  authority collection. It holds no raw values. It includes closed omissions and preserves
  governing scope plus resolution source. It does not expose authoring
  designation tables or duplicate exact operation values.
- Treat the plan collection as the runtime authority for registered concerns.
  Direct-manager and control-plane execution both check that the registry is
  complete. They bind the selected envelope identity and narrow choices to
  backend support. They reject excess state under closed authority. They derive
  safe storage and provenance from this same collection.
- Treat HTTP callers as relays, not planners. Register the exact
  planner-produced provisioning plan through the in-process control-plane
  boundary before HTTP submission. The adapter resolves its canonical digest
  from that trusted registry. A BACKEND or OPERATOR credential cannot widen
  modes or bounds by rewriting the request body.

## Canonical incumbents

Issue #1200 preserves mixed constraints in the portable plan. A weakest-child
summary cannot replace them as comparison authority. The optional typed
`structure` entry records exact/open leaves, record additions and required keyed
members without duplicating operation values. The compiler uses authored explicitness provenance.
Defaults added during normalization do not become author constraints. Package manager/name selectors leave an omitted
architecture open by design. Ambiguous partial identities reject before mutation.

Both direct apply and serialized/control-plane readmission consume this
descriptor. The shared structural matcher checks required members.
Observation order does not affect matching. Canonical concern projection still owns
typed shape, excluded fields and sensitive-value commitments. Unknown or missing observations do not prove satisfaction.
The owning model keeps numeric DNS extension codes exact in their context.
See `test_issue_1200_mixed_runtime_constraints.py` for the positive/negative
apply pairs and `test_issue_1066_runtime_resource_limits.py` for retained
finite-domain and exact-sibling checks. Unsupported mixed shapes receive the
existing actionable authority-bound diagnostic. This creates no new evidence demand or backend-specific rule.

An open scope lets a backend choose an omitted scalar. This holds even when
every enclosing record and collection is closed. The plan reports this authority as
`constrained`, and its recursive document delegates that scalar. Authored sibling values stay fixed. Closed collections keep the same members. An open scalar scope does
not open the whole runtime family or any unrelated omitted concern. Preparation
checks the selected value against the original document. Completion checks that
the backend delivered the admitted selection.

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
- failed apply validation: `raes_processor.planner.realization_cleanup_diagnostics`,
  which validates original authority and omits success provenance
- workflow gates: `.ground-control.yaml`, `.gc/plan-rules.md`,
  `tools/check_repo_policy.py`, `tools/check_requirement_governance.py`,
  `tools/check_json_artifacts.py`, `tools/check_generated_schemas.py`, and
  `tools/verify_all.py`

## Cross-cutting layers

Each changed layer must pass its checks:

- SDL parser gate: binding variables must not create hidden exact declarations. It
  must not rename semantic identities or smuggle realization directives through
  keys.
- SDL model gate: keep explicitness state in typed fields or existing structured
  extensions. Do not use untyped `dict` side channels.
- semantic validation gate: check exact declarations as exact. Check the shape
  and scope of open concerns too. Reject ambiguity.
- instantiation gate: defaults and parameters may fill open concerns only when
  the owning semantic rule permits it. Validate each concrete scenario again.
- contract/schema gate: external payload shape belongs in `ContractModel`
  descendants and the coordinated hand-governed/reference-model schema
  surface. Update the model, schema, publication manifest,
  and generator together. Their outputs must agree.
- manifest/profile gate: supported contract versions, concept bindings,
  binding scopes, realization support modes, exact requirement kinds, and
  controlled vocabulary terms must resolve through existing authority helpers.
- planner/backend boundary gate: backend support checks must compare the
  compiled requirement against backend manifest `realization_support` instead
  of local string conventions. Also compare process-resource demands
  against the declaration's typed resource/scope/value domains.
- provisioning-handoff gate: every applicable registered concern on a
  non-delete operation must have exactly one canonical authority entry. Closed
  concerns need no backend support but forbid added scenario state. Non-closed
  concerns require matching support and the selected envelope identity.
- error-envelope gate: unsupported exact requirements and forbidden
  approximations must be reported with stable validation errors or structured
  diagnostics. Do not leak raw backend exceptions or private payloads.
- control-plane gate: any runtime-facing realization result must pass existing
  request-size, authentication, authorization, audit, idempotency, and published
  response-model validation. An operation-bearing provisioning request must
  also match an exact planner-produced plan registered outside the HTTP relay
  surface. Request authentication and idempotency fingerprints are not planner
  attestation.
- persistence and observation gate: realized choices may be recorded only in
  portable snapshot/result/provenance envelopes. Do not persist secrets,
  bearer tokens, credentials, backend-native objects, or unredacted tracebacks.
- host/OS exposure gate: exact requirement values, credentials, and backend
  tokens must not be passed through process argv, logs, audit details,
  diagnostics, JSON fixtures, or semantic-profile artifacts when they may carry
  sensitive material.

## Extensibility seam

The seam is a typed realization requirement classifier plus the existing
manifest support declaration, not a backend-specific branch. For new choices, extend the governed requirement-kind vocabulary.
Update `RealizationSupportDeclaration` and manifest inputs. Then regenerate
and validate the schemas.

Keep the classifier independent of each backend. New artifact families may need
more exact requirement kinds. Add governed terms and shared semantic checks for
them. Keep planner and conformance call sites unchanged.

Planning resolves root delegation through
`apparatus_realization_default`. The caller injects this resolver. Its fallback is closed. A future typed
apparatus-default contract can supply a different choice. SDL cascade rules and
backend implementations can stay the same.

## Portable process-resource limits

The `process-resource-limits` concern applies SEM-218 to the complete
`Node.runtime.operational_policy.resource_limits.process_limits` collection.
Its identity is `(resource, normalized subject, scope)`. Descriptions
and native backend spellings are excluded. Exact comparison requires the same set of records.
Missing, substituted, or excess records fail. A constrained soft/hard variable keeps its finite `allowed-values` domain.
Instantiation preserves it. Compilation preserves it too. The realized leaf must
belong to it.

The normalized subject also governs inventory matching. Each active selector
must match one declared `runtime.processes` record. Selectors include name, pid,
parent, role, user, group, command, redaction, and working directory. Omit a redacted command. Use another stable projected selector instead. Raw command content
cannot be supplied and then erased from semantic identity.

Support is declared through typed `process_resource_limits` entries on the
existing `RealizationSupportDeclaration`, not through the free-form
`constraints` map. Each entry bounds one portable resource. It names the process or subtree scope.
It sets minimum and maximum finite values. It also states whether `unlimited`
is supported.
Exact and constrained planning checks every compiled demand against that
domain. Open planning also requires authored open permission,
`OPEN_REALIZATION`, and a non-empty typed apparatus domain. The selected
realization-envelope configuration must repeat the exact typed domain from the
compatible global declaration. Planning and runtime checks use only that intersection.
Support advertised for one backend mode cannot authorize another mode.

Each accepted result needs a `process-resource-limits` observation capability.
It also needs a matching runtime observation with no raw values. Its scope must
be configuration. Its source constraint must be exactly `guest-observed`.
This reports effective values read from inside the workload. Desired-payload echo, runtime inspect output, VM
allocation, cgroup capacity, or datastore `memory_locked` state is insufficient.
A backend must both deliver and read back the effective values.
Without both, it remains unsupported.

## Compute kind and realization mechanism

The canonical node kinds are `compute` and `switch`. `compute` describes what
the scenario needs structurally. It does not select a virtual machine,
container, physical device, or emulator. Mechanism intent is instead an
addressed `compute-substrate` entry in `Scenario.realization.constraints`.
Omitting that entry keeps the compute node portable. Exact and constrained
entries retain their governed domain through instantiation, compilation, and a
separate plan constraint. `supported_node_types` remains only the provisioner's
resource-kind claim.

Runtime selection is a separate observation. The backend must bind the observed governed mechanism to its operation.
It must also bind the selected envelope and configuration. A
plan echo or provisioner handle is not evidence. Native modes use daemon
readback. An in-process test double reports an extension term.
It makes no claim of native isolation. Before saving a snapshot, the runtime gate rejects missing readback.
It also rejects weak evidence for bounded demand, envelope/domain mismatch,
and unverified execution binding.

Legacy `type: vm` is not treated as a generic compute alias. Strict authoring
rejects it. Explicit migration preserves its historical exact meaning by
emitting `type: compute`, an exact `virtual-machine` substrate constraint, and
`legacy-node-type-vm` provenance. Collisions are fatal.

## Scoped default cascade

Authors set inherited defaults in the optional scenario-root
`realization` block. It carries a `default` posture and zero or more typed scope
entries. Each scope has a namespace tuple and a canonical RFC 6901
field pointer. Dotted paths, wildcards, and JSONPath are not accepted author
syntax.

Resolution preserves these distinctions:

- an explicit exact, constrained, or open leaf is authoritative;
- otherwise the most-specific concrete scoped posture wins, independent of
  source order;
- `unspecified` inherits an enclosing concrete posture, or delegates the root
  decision to the selected-apparatus resolver;
- omitting `realization` preserves the legacy closed behavior and is not the
  same state as explicit root delegation.

Composition rewrites declaration pointers through the import symbol map.
It qualifies designation records with the import namespace. A module default can govern its own declarations.
It cannot leak to its host or a sibling module. The authoring block itself is removed during expansion and
instantiation. Typed records travel in the existing phase-provenance aggregates
and then in compiled realization requirements.

Open affects only registered realization concerns. It does not relax closed Pydantic shapes. It cannot invent topology or bypass
references. It does not make every absent optional field backend-realizable. The apparatus support mode remains a
capability disclosure rather than author intent.

## Authoring specificity

`classify_authoring_specificity()` is the DSL-115 helper for reviewing
specificity across existing owned surfaces. It reuses the SEM-218 classifier for exact and
constrained authored values. It records open or underspecified concerns only
when the owning caller supplies the explicit path in `admitted_open_paths`.

Do not treat a missing field as open by default. The helper's admitted-open
paths record author intent. The owning SDL, contract, or rule must already allow
that form. These paths do not grant backend permission.
They do not replace manifest `realization_support`, realization
envelopes, or experiment-core contracts.

## Part 2 implementation boundary

The compiler and planner must preserve classifier output as runtime-model
metadata. Its owner is `raes_processor.models.RuntimeModel`.
The `raes_processor.compiler` package emits it. The planner should consume that compiled
metadata directly. It must not re-walk SDL YAML or rerun the classifier.
Backend capability failures do not imply exactness. The backend manifest
does not supply author intent.

Planner rejection belongs in the existing `raes_processor.planner.plan()` /
`ExecutionPlan.diagnostics` path. Report unsupported exact or constrained requirement kinds as stable `Diagnostic`
objects. Do the same for open demand without explicit `OPEN_REALIZATION` support.
Name the compiled resource address, SDL field path or equivalent field identifier,
requirement kind, and missing `realization_support` capability. Do not introduce a
SEM-218-specific exception hierarchy or throw from normal planning for this
case.

When a backend publishes a finer realization envelope, project that offer onto
the compiled open concern paths. Evaluate it with the canonical
`subsumes(offered, requested)` relation. Keep unrelated offered bindings out of
the projection so a constraint on an exact, unrelated field cannot narrow the
author's open concern by accident.

Keep realization-support matching as one manifest-bound helper over
`BackendManifest.realization_support` / `RealizationSupportDeclaration`.
`domain`, `supported_exact_requirement_kinds`, and
`supported_constraint_kinds` are currently opaque non-empty strings, so the
match is exact string membership plus support-mode compatibility. If compiled
explicitness metadata is added to plan payloads or published contracts, it must
go through the existing `ContractModel` / schema-generation path. Otherwise keep
it model-side like existing compiler provenance metadata.

## Complete runtime-configuration coverage

Each top-level `RuntimeConfiguration` field has a tested owner and enforcement
rule. The canonical concern registry splits mixed runtime objects at semantic
boundaries. It carries those paths through compiled and resolved authority.
It validates returned values against the owning closed SDL type. Configuration concerns exclude readiness, run outcomes, live counters,
loaded state, evidence references, and similar observations before posture is
classified.

Exact runtime support is concern-specific. A backend needs three things:
the generic exact capability, the exact concern-kind token, and a matching
observation capability. Open and constrained concerns use the same manifest and envelope
admission path. These declarations do not replace independent readback.
A backend that can only echo submitted plan values remains unsupported.
The operational policy sets the required `presence` or `configuration` scope.
It normally allows either authoritative daemon-native or guest-native readback. Driver self-attestation alone does not prove the claim.
A claim that inherently depends on a particular vantage, such as effective
in-workload process limits, carries an exact source constraint instead. Source categories cannot always substitute for each other.

Closed collection authority covers the managed projection that matters to the
scenario. It does not cover the whole native operating-system inventory. Base-image
packages, transitive dependencies, incidental daemons, native handles, and
measurement apparatus remain on their existing substrate or evidence owners
unless deliberately promoted into the corresponding runtime concern.

## Gotchas and anti-patterns

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

## Companion scope

This note guides implementers of the SEM-218 spec at
{download}`specs/formal/realization/explicitness-and-realization.md <../../../specs/formal/realization/explicitness-and-realization.md>`.
It does not itself define exact-requirement-kind vocabularies or change
manifest payloads — those are governed by the spec and by the
controlled-vocabulary / reference-model authorities. The SEM-218 coverage row is `active`. The classifier, typed scoped
designation cascade, compiler carrier, and planner gate work together.
So do the runtime non-approximation/disclosure gate and snapshot provenance
delivery. Use this note as guidance for those surfaces. The spec is the binding contract.

## Constraint evaluation work

`evaluate_realization_constraint` applies finite limits to constraint admission
and value evaluation. The evaluator builds a temporary tree of decoded scope
tokens for each call. Inherited closure and closed-scope child checks share that
tree. Tree construction and lookup consume the evaluation operation budget.
This avoids scanning all scopes for each application route or nested container.
The default limits remain unchanged. Exhausted work returns `limit-exceeded`.
Matching input values do not bypass exact constraints or scope checks.
