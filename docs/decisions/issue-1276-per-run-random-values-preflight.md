# Issue #1276: Configurable per-run random values preflight

The supplied GitHub issue is the contract; this is a requirement-free
architecture review. This note records design boundaries, not an implementation
plan or a claim of implemented support. No new ADR is needed: the existing
stateful-resource, phase, profile-selection, evaluation, and control-plane
authorities cover the architecture. The gaps below require contract extensions.

## Ownership and generation

Extend `generated_artifacts`, retaining one producer, canonical
`provision.generated-artifact.<id>` address, complete output set, and lifecycle
unit. A portable `random_value` generator with closed, typed parameters is the
appropriate built-in meaning. Do not turn required variables into generators,
generate during parsing/instantiation/compilation, or introduce a second
top-level secret/value registry. Instantiated SDL carries the recipe and
references, never its realized value. “Per instantiation” describes the lifetime
of a realized instance, not permission to substitute a secret into serialized
`InstantiatedScenario` content.

Generated outputs also remain distinct from immutable supply-chain
`ArtifactRequirement` satisfaction and associated-artifact capture manifests.
Do not force a secret output into those public digest/evidence contracts merely
because both surfaces use the word “artifact.”

Use `GeneratedArtifactKind` in `raes_contracts/vocabulary.py` and
`GeneratedArtifact` in `raes/stateful_resources.py`. The repository also already
supports typed `DomainProfileBindingModel` generator selections and exact
`artifact-generation` plan-profile admission; see
[profile selections](../../specs/sdl/profile-selections.md). Preserve that seam
for future generation formats/semantics. A standard portable random generator
must not depend on a TechVault-private profile being installed. Do not create
another plugin registry, free-form options map, or executable template language.

The typed recipe must specify unambiguous units and bounds: random character
count versus entropy bits, alphabet/encoding, and literal formatting. A bounded
prefix/random-segment/suffix representation can express `TECHVAULT{<32 hex>}`
without a general expression evaluator. Define escaping, encoding, newline
behavior, and maximum rendered size. Reject contradictory length/entropy
requests, duplicate or degenerate alphabets, invalid counts (including bools),
unknown formats, control characters unsafe for the selected delivery, and
unbounded templates. For uniform draws, 32 hex characters carry 128 random
bits; literal wrappers contribute none. Publish an explicit minimum for secret
generation rather than silently accepting guessable flags or silently padding
an invalid recipe. Future alphabet/format cases belong in this parameter/profile
seam, not output names, provenance strings, or provider-specific SDL.

Require backend-owned cryptographically secure generation with unbiased
sampling and bounded failure. No public seed, scenario hash, timestamp, UUID
assumption, or operator-supplied constant can satisfy fresh unpredictability.
`raes_contracts/random_stream_engine.py` implements replayable experiment
streams; `raes_reference_backend/artifact_generation.py` implements a
public-seed digest profile. Neither is a random-secret producer. Keep experiment
replay/provenance and secret generation independent; do not publish secret seeds
or promise bitwise secret replay. Define whether multiple outputs are projections
of one draw or independent values; do not silently count correlated projections
as additional entropy. Separate independently scoped flags use separate artifacts.

## Scope is not reconciliation

Keep generation scope distinct from the existing `regenerate_on_change` /
`reuse_valid` reuse policies. Preserve their current meanings and define the
allowed scope/lifecycle combinations, including what a recipe change does
within an active scope. Do not let an ordinary refresh silently rotate a live
flag. Scope identity and recipe compatibility must participate in admission and
reconciliation; matching filenames or unchanged recipe bytes are insufficient.

| Requested scope | Required identity and behavior |
| --- | --- |
| Per run | A new authoritative execution run gets a fresh generation, including when the SDL and target are unchanged. Resume, retry, reconciliation and evaluator restart within that run retain it. |
| Per instantiation | A distinct realized scenario instance gets a fresh generation; runs reusing that instance retain it. A serialized scenario digest is not a unique instance identity. |
| Once | One generation for the declared backend-owned artifact instance lifetime, with an explicit ownership namespace and destruction boundary; never a global cache keyed only by SDL id. |

The execution identity must include the isolated target/range and scenario
instance as appropriate. Two participants in distinct ranges must not share a
generation because their SDL artifact ids match. Participants intentionally
sharing one run share its value unless separate artifact scope is declared;
“per participant” is not implied by “per run.” Fresh random draws give a
probabilistic collision guarantee, not mathematical global uniqueness.

There is a concrete missing bridge: `ProvisioningPlan` and `EvaluationPlan` in
`raes_contracts/planning.py` have no run identity; `operation_admission_context()`
in `raes_runtime/control_plane_operation_context.py` can fall back to
`run:default`. An operation id, idempotency key, target name, or that default
cannot stand in for a new run or instance. Bind the same validated, value-free
scope through the existing operation/run authority to producer, delivery and
evaluator. Missing or contradictory scope must fail before mutation, including
embedded and direct-plan entry points. Do not create a second run scheduler.

Reuse `RuntimeManager`, operation admission/idempotency, target mutation
serialization, durability/recovery, and the existing dependency/refresh/delete
graph. A new scope must not disappear as `ChangeAction.UNCHANGED`. Concurrent
duplicate requests must converge on one generation. Publish all consumer
projections and the verifier's active generation coherently; partial failure
must not leave a new file paired with an old verifier. Snapshot rollback alone
does not undo native effects. Backend-private state must survive the recovery
needed by the claimed scope; loss of active state fails closed rather than
quietly regenerating. Cleanup follows scope ownership and reverse dependencies,
without deleting values still owned by longer-lived instances.
Late evaluations retain their original run binding; they must never resolve
against whichever generation happens to be current on a reused target.

## Delivery and verification

Reuse `GeneratedArtifactValueSource` and
`resolve_consumable_generated_artifact_output()` in
`raes/runtime_generated_value.py`. References are artifact id plus artifact-local
output name; reuse module namespacing, identifier validation and reference
catalogs. Sensitivity and distribution entitlement remain separate. Secret
outputs may be intentionally delivered to selected consumers; `producer_private`
outputs cannot become consumer-visible through a new binding type.

- **Files:** use existing read-only selected-output projections, canonical
  relative output paths and POSIX mount destinations. Define the resulting file
  path from destination plus output path; do not reinterpret destination as a
  filename or let content and mounts acquire conflicting ownership.
- **Environment:** reuse `RuntimeEnvironmentVariable.value_from` and
  `RuntimeEnvironmentFile`. Secret scalar bindings require `redacted` and omit
  raw `value`; `operator_secret` remains external operator material. Env files
  are opaque files, not automatic `NAME=value` wrappers around arbitrary flags.
  Bindings remain authored once on the consuming node, with compiler-derived
  artifact projections and exact delivery-mode capability admission.
- **Content text:** `Content.text` is currently an authored string, and
  `_compile_content_placements()` copies content into the plan. A typed deferred
  source/rendering binding is needed at that existing content boundary, reusing
  the same output reference. Preserve literal text and define mutual exclusion
  or explicit literal/reference composition; do not add magic `${...}` secret
  interpolation to the general variable walker. Rendering happens inside the
  backend's protected materialization boundary. `Content.sensitive` alone does
  not stop bytes being serialized. Do not require a duplicate artifact consumer
  declaration for a content binding.
- **Verification:** an evaluator must reference the same artifact/output and
  active scope without receiving its expected value through SDL or plan fields.
  Extend the existing proposition/condition/evaluator boundary with a typed
  deferred expected source where needed; `StringPredicate.expected` currently
  accepts literals only. Use observed-state evidence and the existing
  proposition/assertion/objective truth and result contracts. Submission
  observation, comparison authority and score aggregation remain separate.
  Admission must bind the submission's authorized range/run and comparison
  source; an arbitrary reference is not a grant to retrieve secrets. Missing,
  stale or unavailable expected state cannot yield success. Compare exact
  specified bytes using a constant-time primitive in the protected backend;
  preserve intentional case/newlines rather than guessing normalization.

The content and evaluation cases are required by the issue, not optional
follow-ups after an enum-only change. Today
`stateful_resource_reference_errors()` and
`generated_artifact_payload_diagnostic()` recognize file/environment consumers
only. Extend those incumbents for the new typed uses and their exact derived
projections; do not disable orphan checks, fabricate mounts, or create parallel
resolvers. Preserve `producer_private` semantics: an evaluator comparison may
use an authorized producer service, but cannot turn private material into a
generally consumable output. Reuse evaluation capabilities, not a CTF scoring
engine, shell comparison script, or new public secret-retrieval endpoint.

## Cross-cutting gates and incumbents

Package paths below are relative to `implementations/python/packages/`.

| Layer | Canonical incumbent and required treatment |
| --- | --- |
| Source, model and phase admission | `raes/_yaml_loader.py`, `_source_validation.py`, `SDLModel(extra="forbid")`, `PortableIdentifier`, concrete phase reconstruction and unresolved-variable checks. Retain source limits/duplicate rejection; bound the recipe; secrets remain absent from every phase and derivation record. |
| Semantic references and composition | `raes/_stateful_resource_references.py`, `SemanticValidator`, composition's symbol/dependency rewriting and proposition/content validators. Resolve every new use, preserve local output names, check sensitivity, entitlement, path ownership and real dependencies. Current exact mount-destination collision checks alone do not detect overlapping child paths or content collisions. |
| Compiler and planner | `raes_processor/compiler/stateful_resources.py`, `compiler/placement.py`, `compiler/evaluation.py`, `planner/resources.py`, `planner/prepared_node_projection.py`. Preserve scope/recipe/reference metadata through payloads, exact realization requirements, prepared-node reconstruction, refresh and reverse deletion. Respect ADR-036 package import boundaries and ADR-015 file size limits. |
| Capability, profile and direct-plan admission | `ProvisionerCapabilities`, `ProvisionerCapabilitiesModel`, backend-manifest v2, `planner/stateful_admission.py`, `control_plane_submission.py`, profile selection/preparation authority. Generator support alone cannot promise every scope/format/delivery/comparison; require exact supported semantics and fail before mutation. Reuse kind/mode sets and pinned profiles, not one boolean per option. A generic HTTP payload dict is not admission. |
| Realization and observations | `project_environment()`, `validate_environment_observation()`, `sanitize_realization_snapshot()`, `realization_payloads_match()`, `realization_disclosure()` and SEM-218 requirements. Compare declared recipe/scope/bindings, never expected random bytes. Preserve value-free observations; declaration equality or presence alone does not prove freshness, entropy, native isolation or successful delivery. |
| Secret handling and persistence | `enforce_observed_value_redaction()`, account credential projection as a protected-boundary precedent, `RuntimeSnapshot`/`SnapshotEntry`, `LocalControlPlaneStore` and operation history codecs. Classification is explicit; name heuristics are advisory. Keep generated/submitted values, private verifiers and seeds out of generic JSON, provenance, profile values, commitments, reports and audit details. Existing account-specific projection does not automatically protect new content/evaluation fields. Backend storage remains private and scoped; reuse durable control-plane metadata, not its JSON files as a secret vault. |
| Authentication and API/config shapes | `ControlPlaneSecurityConfig`, API `_auth.py`/guards, plan authorization, participant control/audience bindings and operation admission. Retain verified identity, roles, exact target authority, request/queue limits and idempotency. Bind scope to that authority rather than trusting caller labels. Existing authorized snapshot reads still must never disclose values. No new token/config/environment lookup or weaker proxy-header trust. |
| Errors, results and observability | `Diagnostic`, `ApplyResult`, `backend_calls.py`, backend result validation, `evaluation_result_contracts.py`, `proposition_truth_contracts.py`, API response envelopes and canonical operation audit/history. Use bounded reason codes and safe coordinates. Reject malformed backend output through existing failure paths; no new exceptions/logger. Do not echo Pydantic inputs, backend exception text, submitted values, native paths or rendered text in any success or error envelope. Generic `detail`/`details`/evidence references are potential leaks. |
| Host/process boundary | Native producer and existing delivery drivers own path containment, symlink/traversal rejection, restrictive ownership/modes, atomic replacement, isolated ranges and cleanup. Never place secrets in command text, argv, provisioner environment, image layers, retained cloud-init/seed artifacts or stdout/stderr. Intentional target-process environment delivery is allowed only for its selected consumer; account for process inspection and child inheritance. Use protected byte channels and fixed argv with bounded, non-shell execution when native tooling is necessary. |
| Participant/evidence boundary | Existing participant view/flow controls and evaluation evidence/truth models govern disclosure. A flag is intentionally discoverable at its authorized host location; randomization is not proof of opacity. Publish comparison outcome and safe evidence coordinates, not expected/submitted bytes, reversible encodings, public verification hashes or unsolicited value commitments that create an offline guessing oracle. |

## Publication, assurance and boundaries

Reuse `schema_bundle()` and the hand-governed schemas/publication ledger under
`contracts/`, including transitive embeddings. SDL authoring, instantiated
scenario/snapshot, satisfiability evidence, plan DTOs and backend-manifest
schemas must stay consistent where affected. Retain JSON Schema constraints
plus published `x-raes-invariants` for relational rules; do not claim schema
validation replaces semantic admission. Keep SDL reference/section/lineage and
controlled-vocabulary authority aligned. Do not edit accepted ADRs to evade
their pin gate. Canonical verification remains `.ground-control.yaml`,
`.gc/plan-rules.md`, `noxfile.py`, repo policy and schema-publication/parity tools;
this issue must not acquire a fabricated requirement UID. Release-please owns
version/changelog changes.

Extend the existing stateful-resource, #1074 environment, #1208 profile,
manifest, proposition truth, runtime planner/control-plane/API and crash
consistency suites. Assurance must cover identical recipes in distinct scopes;
stable retries/resume/concurrent admission; file/environment/content and
verification agreement; stale/wrong-range rejection; malformed direct plans;
unsupported capabilities; and absence of secret sentinels from success,
failure, persistence and observation paths. Exercise backend failure between
generation and delivery. Deterministic test entropy belongs only in an injected
backend test seam; different sample strings do not prove cryptographic quality.
Preserve existing deterministic-stream and certificate/config/SSH behavior.
Do not widen reference/libvirt capability claims from stub or parse-only tests.

Non-goals are a production RNG/storage-provider prescription, vault API,
rotation scheduler, scoring platform, participant policy redesign, replay of
secret bytes, generic template/expression engine, Windows mount dialect, or
TechVault/env-pack changes. The backend owns generation, protected persistence,
delivery and comparison mechanics; portable scope, shape, sensitivity, binding,
verification semantics and honest capability admission remain in scope. Merely
documenting that a backend could supply a required variable does not ship this
issue.
