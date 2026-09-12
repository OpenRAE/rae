# Issue 1202: Typed Domain Profiles Preflight

Date: 2026-09-05. Inspected revision: `c3b30c6c`.

Contract: GitHub issue #1202 and the supplied 2026-09-05 corrective design
intent. This note is architecture guidance, not an implementation plan, an
accepted ADR, or evidence that the acceptance criteria execute today. It makes
no runtime, schema, vocabulary, or public-syntax change.

The repository already has most of the surrounding machinery: concept
authority, immutable artifact identities, explicit local resolution, published
contract schemas, backend manifests, realization-support declarations,
semantic comparison results, typed runtime observations, provenance, and
bounded diagnostics. The missing element is one neutral contract that lets
typed domain meaning travel through those owners without turning private
profiles into core vocabulary terms or executable plugins.

## Governing architecture

Use one shared contract family for standard and private profiles, with distinct
roles for:

- a **definition**, which binds an authority-qualified profile identity to an
  immutable revision and content digest, a pinned typed schema, a semantic
  contract identity, allowed composition/nesting, and allowed host contexts;
- a **binding**, which attaches profile data and its exact definition
  coordinate to a named core owner, concept family, lifecycle phase, and use;
- a **resolution context**, which is an immutable, caller-supplied set of
  admitted local definitions and schemas, with explicit trust and resource
  limits; and
- a **support declaration**, which says which exact profile coordinate and
  semantic operations an apparatus or local processor supports.

These roles may share primitives, but must not collapse into one registry
record. A locator is not an identity, schema validity is not semantic support,
and possession of a definition is not permission or ability to interpret it.
Profile documents are inert data and must not contain import paths, commands,
callbacks, package-install instructions, or other executable handler
selection. Semantic handlers are pre-installed code selected through a local,
context-injected mapping keyed by the exact semantic contract identity. There
must be no mutable process-global plugin registry.

The portable profile coordinate must include explicit namespace authority,
profile identity, exact revision, and immutable content digest. Identity
comparison is exact and case-sensitive unless that authority's contract
declares another normalization rule. The existing `x-authority:term` spelling
is useful for governed string vocabularies but is not proof of ownership and is
not sufficient profile identity. SDL composition's `QualifiedName` identifies
scenario paths, not external namespace authority; do not reuse it as if those
were the same concept. Namespace ownership comes from the local admission and
trust chain binding an authority to its namespace, not from a self-asserted
string inside the definition.

A standard classification, if useful, is optional metadata separate from
profile identity. A private definition is complete and portable without public
registration. The same logical coordinate resolving to different digests is a
fatal collision; two authorities may use the same local name without
colliding. Multiple indistinguishable candidates are ambiguous, never
first-wins. Revision ranges, `latest`, silent aliases, or digest-free fallback
would defeat reproducibility and are out of scope.

The schema may be embedded or carried as a separately identified artifact, but
an unpinned locator alone is insufficient. Hash the versioned semantic
projection with `raes_contracts._canonical.canonical_json_digest()` after it is
validated as JSON-compatible; do not mint another canonicalizer or reuse SDL
source canonicalization. The contract must define the digest projection without
self-reference: exclude the profile digest field itself, and, for a separate
schema artifact, bind its exact coordinate and digest. Keep schema revision,
profile semantic revision, and implementation/handler support distinct. Digest
equality establishes content identity and integrity, not trust, semantic
equivalence, or execution safety.

Bindings must name the owning core surface and lifecycle use. A definition may
declare compatibility with existing concept families and host surfaces, but a
private profile is not a new concept family by default. `ConceptBinding` and
the external-concept-binding resolver are precedents for exact contextual
binding and explicit resolution; neither should be overloaded to carry domain
data or execution authority. Nested child bindings use the same coordinate and
context rules. Start with finite nested values and bounded, acyclic local
references as established by the #1201 semantic model; recursive schemas or
unbounded graphs require a separate decision.

An extension is required only when its detail is authored as a constraint,
needed by a semantic operation, or explicitly exchanged. An open scope does
not require the author to name backend-internal repositories, generators, or
materialization choices. A report request can require a typed binding for a
choice that the author did not constrain; it does not retroactively make that
choice authored intent or require experimental retention/export. Definition
provenance, authored binding provenance, backend-choice disclosure, and
observed evidence remain separate records.

## Resolution and unsupported meaning

Parsing performs no network access, credential lookup, module import, package
installation, or code execution. Resolution consumes only the explicit local
context supplied to that operation. Packaged standard definitions may come
from the installed normative corpus; private definitions may come from pinned
caller inputs or already-admitted associated artifacts. If future explicit
retrieval is offered, it is a separate pre-operation that must use existing
artifact/module trust controls and produce an admitted local input. It must not
be hidden inside parsing, validation, comparison, planning, replay, or capture.

The host contract, not an unknown profile, decides whether an opaque value is
allowed. The required outcome is:

| Definition and requested use | Required outcome |
| --- | --- |
| Exact definition resolves; dialect and every required schema vocabulary are supported | Perform bounded structural validation. Optional unsupported vocabularies may only yield an explicit limitation where the dialect permits that treatment. |
| Definition resolves; required semantic validator, comparator, or interpreter is unsupported | Refuse that semantic operation before planning, mutation, or a conformance claim. Structural validity must not be presented as semantic validity. |
| Definition is absent, but the owning surface explicitly permits non-binding opaque annotation/exchange | Preserve the bounded value, exact coordinate, and limitation without claiming validity, refinement, equality, executability, or observed truth. |
| Definition is absent/incompatible/colliding, or the value contributes to a constraint, required comparison, execution instruction, or required typed report | Return a stable unsupported/conflict diagnostic and stop before mutation. |

Unknown, redacted, delegated, opaque, invalid, and unsupported are different
states. Opaque preservation is not a wildcard constraint and cannot satisfy a
required semantic operation. Budget exhaustion means limited/unsupported, not
invalid or unsatisfiable. Definition digest equality cannot substitute for
semantic comparison of two bound values.

Support negotiation must be operation-specific. At minimum, keep structural
schema validation, profile semantic validation/refinement, comparison, and
interpretation/execution distinct. Generic opaque carriage is a host policy,
not evidence that the profile is supported. A support row identifies an exact
profile and semantic-contract coordinate plus the supported operations and
limits; it does not carry a Python class, executable path, or dynamically
loaded validator.

The current governed
`capabilities.provisioner.supported_domain_profiles` string list is specific to
authored identity-domain topology. Preserve it as a compatibility projection
for that contract until deliberately migrated, but do not make it the new
authority. It lacks authority, revision, digest, schema/vocabulary support,
operation support, and contextual binding. Neutral support DTOs belong in
`raes_contracts`; declarations belong on the existing owning apparatus surface
(for example, provisioner realization support for execution, and the selected
local comparison context for comparison), not in a new universal registry.

## Canonical incumbents and cross-cutting reuse

All package paths below are relative to `implementations/python/packages/`.
These are mandatory integration points, not independent alternatives.

| Concern | Canonical incumbents | Obligation |
| --- | --- | --- |
| Concept identity and contextual resolution | `contracts/concept-authority/`, `raes_contracts/contracts/catalogs.py`, `controlled_vocabularies.py`, `contracts/external_concept_bindings.py`, `raes_contracts/external_concept_bindings.py`, ADR-012 and ADR-062 | Reuse authority, governed-extension, exact-subject, contextual outcome, and collision disciplines. Do not add a concept family or controlled-vocabulary term for every profile. Keep external classification separate from typed domain meaning. |
| Profile and artifact identity | `raes/_source.py::ArtifactIdentity` and `ArtifactMechanismProfile`, `raes_contracts/artifact_requirements.py`, associated-artifact manifests, ADR-071, ADR-077, and ADR-098 | Reuse exact revision/digest and verified-distribution patterns. Do not stretch an artifact-mechanism profile into a general domain schema or treat a digest as admission/trust. |
| Contract models and publication | `raes_contracts/contracts/base.py::ContractModel`, `contracts/bundle.py::schema_bundle()`, `tools/generate_contract_schemas.py`, `contracts/schema-publication-manifest.json`, ADR-061 and ADR-075 | Source typed portable DTOs in `raes_contracts` and keep generated schema/fixture/model parity. Public RAES carrier schemas use the publication ledger. Private profile schemas remain independently distributable and must not be copied into the core publication registry. |
| Bounded JSON and canonical identity | `raes_contracts/json_ingress.py`, `raes_contracts/_canonical.py` | Reject oversized input, duplicate members, invalid roots, non-finite values, and ambiguous encodings before model validation. Add explicit depth/node/scalar/reference/evaluation/diagnostic budgets; bytes alone are insufficient. Use the shared RFC 8785 digest helper. |
| Existing profile loaders | `participant_flow_policy_profiles.py`, `behavioral_relation_profiles.py`, `random_stream_profiles.py`, and the normative corpus loader | Reuse exact-id-before-I/O and fail-closed local-loading behavior. Do not clone one hard-coded allowlist/path loader per domain or make private profiles global corpus members. |
| Backend and realization support | `raes_backend_protocols` manifest/capability dataclasses and adapters, `raes_contracts/contracts/capabilities.py`, `raes_contracts/apparatus.py::RealizationSupportDeclaration`, `artifact_requirements.py::ArtifactMechanismCapability` | Extend the existing manifest/support matrix with exact, operation-specific rows and preserve dataclass/model/payload parity. Do not add a boolean, a parallel backend registry, or Cartesian support claims. Backend contract-version support remains a separate dimension. |
| Authoring, composition, and compilation | `raes` parser/models/validators/composition, the #1201 recursive partial-description semantics, `raes_processor/compiler/`, `CompiledRealizationRequirement`, and `CompiledRealizationAuthority` | Keep core keys closed while allowing only explicitly bound profile data. Preserve binding identity, contextual owner, required use, delegation, and sibling constraints through composition and canonicalization. Do not register every nested profile leaf as a realization concern. |
| Admission and alternate submission | `raes_processor/semantics/realization_support.py`, planner `core.py`, `raes_backend_protocols/domain_topology.py`, and `raes_runtime/control_plane_submission.py` | Use one shared support/resolution decision for planner and direct submission. A required unsupported profile fails before backend invocation or durable mutation. Preserve existing topology admission while separating its legacy profile string from the new coordinate. |
| Semantic comparison | `raes_contracts/semantic_comparison.py`, `SemanticComparisonProfileModel`, `ComparisonLimitsModel`, `RelationStatus`, `ComparisonCompleteness`, and bounded-domain relations | Extend owner-specific semantic projections and reuse result/limit vocabulary. Never compare raw dictionaries or profile digests as value semantics. Unsupported required comparison yields a stable refusal/incomparable result, not false equality. |
| Runtime observations and sanitization | `raes_processor/semantics/realization_concern_observations.py`, `realization_snapshot_sanitization.py`, `raes_contracts/runtime_state.py`, and published realization-plan/snapshot models | Route typed bindings through the shared validator/projection seam before capture or comparison. Preserve annotation limitations and exact coordinates. An arbitrary `SnapshotEntry.payload` or metadata dictionary is not a safe extension channel. |
| Provenance, evidence, and disclosure | `RealizationProvenanceEntry`, realization support `disclosure_kinds`, evidence/capture contracts, validation profiles, ADR-064 and ADR-066 | Record the basis actually requested and produced. Profile/schema provenance does not prove execution or observation. Do not require disclosure, capture, retention, or export for an irrelevant backend-internal choice. |
| Errors and operational observability | `raes/_errors.py`, `raes/_model_diagnostics.py`, `raes_contracts/diagnostics.py::Diagnostic`, operation receipts/status, API request guards, and backend suppressed-failure reporting | Reuse bounded structured diagnostics; do not create a profile exception hierarchy. Distinguish missing definition, ambiguous/colliding authority, revision/digest mismatch, unsupported required vocabulary/operation, validation failure, and limit exhaustion. Messages must be value-free and safe for API/audit surfaces. |
| Persistence and replay | `ControlPlaneStore`, `LocalControlPlaneStore`, existing snapshot/operation/observation codecs and atomic replace/CAS behavior | Persist the exact coordinate and safe typed/opaque carrier in existing records. Replay resolves only from an explicit admitted context and never fetches. Do not add a profile database, cache, sidecar, or hidden mutable registry. |

Do not conflate this domain-profile contract with
`SemanticProfileModel` (repo-wide authoring/exchange/processing/execution stack
compatibility), validation profiles (claim/evidence strength), reference models
(recurrent structural templates), module-registry modules (software packaging),
or `ArtifactMechanismProfile` (artifact realization). They may reference one
another at explicit boundaries, but none is a substitute for the missing
contract.

## Cross-cutting gates

The intended design must pass every layer below.

| Layer | Required treatment |
| --- | --- |
| Source and configuration shapes | `raes/_yaml_loader.py`, `_source_validation.py`, `_mapping_key_analyzer.py`, `_source_profile.py::SDLParserLimits`, `SDLModel`, and `ContractModel` remain authoritative. Preserve safe YAML, duplicate/key/source diagnostics, variables, strict core keys, model-level invariants, and parser limits. The extensibility seam is a typed profile-binding field on an owning model, never `metadata`, `Any`, or arbitrary top-level JSON. Direct JSON/model ingress receives equivalent limits. |
| Schema validator admission | Select a pinned in-process JSON Schema implementation/dialect deliberately and disclose supported vocabularies. Repository `check-jsonschema` subprocesses are policy tooling, not runtime validation. Disable implicit remote `$ref`, dynamic code/custom callbacks, and unbounded format/regex/reference evaluation. Schema retrieval and handler admission are separate. |
| Secrets and environment | Reuse `runtime_values.enforce_observed_value_redaction`, `runtime_environment.py`, `secret_references.py`, generated-artifact reference validation, and ADR-056/057. A profile cannot redefine literal/secret-reference shapes, smuggle credentials through nested data or locators, read environment variables while resolving, or rely only on secret-looking field names for sanitization. |
| URI, artifact, and supply-chain security | Use `uri_safety.validate_safe_absolute_uri()` for inert credential-free identity/locator shape and existing module/artifact trust controls for any separately authorized retrieval. URI validation alone is not SSRF protection. Enforce scheme/destination/redirect, compressed/uncompressed size, path traversal/symlink, signature/digest, trust-root, and cache controls at the explicit retrieval boundary. |
| Planner/runtime authorization | Reuse realization authority, target/participant entitlement, manifest compatibility, configuration-bound planning, idempotency, dependency/order, reconciliation, and cleanup gates. Profile support never grants resource authority. Planner and direct submission must have identical refusal behavior. |
| API exposure | Reuse `ControlPlaneSecurityConfig`, `_ControlPlaneApiAuth`, target/audience checks, `RequestSizeLimitMiddleware`, bounded audit dispatch, and published response envelopes. Private definitions and reports are not automatically visible to every reader. Operation routes currently expose `str(ValueError)` in a 409 response, so new profile errors must contain no payload, URI credential, schema fragment, path, native output, or secret; prefer stable diagnostics. |
| Persistence and lifecycle exposure | Reuse store serialization, atomicity, idempotency, snapshot sanitization, marking, retention, and export owners. Validate/sanitize before queues, temporary buffers, persistence, logs, and comparison—not only on response. A report request does not authorize experimental capture, retention, or export. |
| Host/OS boundary | Normal profile handling requires no subprocess. Never place profile payloads, locators, tokens, or schemas in shell strings or argv. Any future separately approved interpreter process needs a fixed executable/vector, restricted environment, private bounded input, timeout/output/resource limits, and redacted failure handling; downloaded profile data may not select it. |
| Error envelope and logging | Use `SDLError` at SDL boundaries and `Diagnostic`/operation status for expected support outcomes. Preserve generic redacted 422/500 behavior and stable audit reason codes. Do not log private payloads, schema contents, locators, raw exceptions, Pydantic inputs, tracebacks, or native output. Bound diagnostic count and length as well as validation work. |

Package ownership follows `tools/policy/adr_policy.yaml`: neutral identity,
definition, binding, support, diagnostic, and resolution-result DTOs plus pure
validation live in `raes_contracts`; SDL placement and authoring rules live in
`raes`; compiler/planner projection and comparison use live in
`raes_processor`; backend manifest adapters and execution support live in
`raes_backend_protocols`; runtime admission/persistence orchestration lives in
`raes_runtime`; portable probes live in `raes_conformance`. A lower package
must not import an implementation handler from a higher layer.

The extensibility parameter is the explicit, immutable resolution/admission
context passed to parsing/validation/comparison/admission, together with the
required semantic operation. Tests and offline users can supply private pinned
definitions through this seam; production callers can supply only artifacts
already admitted by local trust policy. Ambient filesystem search, environment
lookup, network discovery, entry-point scanning, and import side effects are
not valid resolution inputs.

Workflow authority remains `.ground-control.yaml`, `.gc/plan-rules.md`,
`noxfile.py`, `tools/nox_support/`, `Makefile`, and
`.pre-commit-config.yaml`. This issue is the authoritative contract for a
requirement-free change: do not fabricate a requirement UID; use the existing
`--skip-requirement` workflow and issue/PR traceability. Later implementation
must run the repository policy, requirement-governance, and full verification
gates. Any public schema change also needs generator parity, fixtures, and a
schema-publication ledger entry. Keep release-please-owned versions and
`CHANGELOG.md` untouched.

## Review guardrails and acceptance probes

Later verification must cover, at contract, model, processor, runtime, and
backend-manifest boundaries where applicable:

- one standard and one private/offline profile using exactly the same
  definition, binding, support, and diagnostic shapes;
- nested profile data and nested child bindings with deterministic context,
  finite budgets, round-trip preservation, and no sibling loss;
- same-coordinate/different-digest collisions, ambiguous namespace ownership,
  absent definitions, incompatible revisions/digests, unsupported required
  schema vocabularies, and unsupported semantic operations;
- bounded opaque preservation only on a host-permitted non-binding surface,
  including exact limitation/provenance round trips and negative assertions
  that it is not called valid, comparable, executable, or observed;
- refusal before backend mutation and store writes for required unsupported
  validation, comparison, and execution, including directly submitted plans;
- remote-reference, path-traversal, duplicate-JSON-key, decompression,
  depth/node/reference/evaluation, adversarial regex, secret-bearing URI,
  executable-handler, logging, API-error, and authorization negative cases;
- backend dataclass/model/payload/schema/fixture parity, publication-ledger
  checks for public carrier changes, and local resolver determinism with
  network/filesystem/subprocess probes disabled; and
- the two corrective anchors: an irrelevant backend-internal private
  repository/generator requires no profile, registry entry, report, or
  provenance; the same detail, when explicitly constrained or requested in a
  typed report, carries the shared coordinate and fails honestly if its
  required semantics are unsupported.

Provenance tests must distinguish the definition source and trust decision,
the author-supplied binding, a backend-selected choice, and any later
observation/evidence. Conformance must not infer successful realization from
schema validity, handler availability, a returned opaque value, or matching
digests.

## Gotchas, anti-patterns, and non-goals

Avoid a generic extension bag; a second schema publication mechanism; a
process-global registry; per-domain loader/validator/exception hierarchies;
first-match namespace resolution; revision fallback; automatic network or
filesystem discovery; schema-generated Python classes; arbitrary custom
keywords/formats; remote `$ref`; profile-selected imports/subprocesses; raw
dictionary comparison; support booleans; and storing unsanitized profile data
in snapshot metadata. Avoid duplicating validation between Pydantic, JSON
Schema, planner, runtime, and backends: each layer owns its existing invariants
and calls the shared profile decision once.

Do not equate a profile namespace with a scenario namespace, a schema dialect
with a semantic contract, a definition digest with value equality, a validator
with an interpreter, support with authority, an opaque value with an open
constraint, or requested reporting with observation/retention/export. A
parent's support does not silently grant support for nested children, and a
parent schema must not weaken a child's required semantics. Never silently
drop an unknown binding during canonicalization, composition, capture, or
replay.

This issue does not design arbitrary executable plugins, require public
registration, migrate every existing catalog, add a new service/API/store,
standardize backend recipes, make internal backend choices author-visible, or
broaden evidence collection. #1201 owns the recursive partial-description
semantics; #1203 owns the recursive authoring algebra; #1204 owns end-to-end
compiler/admission carriage; #1205 owns software/acquisition separation;
#1206-#1208 own specific catalog migrations; and #1212 owns scoped observation
demand. #1202 supplies the shared typed profile and support-negotiation contract
those efforts may reuse without pre-implementing their domain semantics.
