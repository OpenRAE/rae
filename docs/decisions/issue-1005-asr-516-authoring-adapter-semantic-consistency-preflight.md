# Issue 1005 / ASR-516 Authoring Adapter Semantic Consistency Preflight

Date: 2026-09-16

Issue: #1005.

Requirement: ASR-516, `DRAFT` / `SHOULD`.

This note fixes the architecture boundary for reusable RAES authoring-adapter
conformance vectors. It is guidance only: it does not add a vector, schema,
adapter, transport, user journey, pack operation, backend, or runtime outcome.

## Decision Summary

RAES conformance compares admitted authoring outcomes, not user interfaces or
task completion. A CLI, MCP/agent tool, graphical editor, documentation-driven
workflow, or future adapter remains a presentation and transport boundary. It
must submit the same digest-bound input under the same governed operation and
comparison profiles, then project its result into one small adapter-neutral
observation. The observation composes existing RAES authorities for artifacts,
diagnostics, transformation provenance, semantic comparison, and validation
basis; it does not redefine any of them.

One thin, versioned conformance vector/observation family is justified because
no existing contract joins all four required axes. It must remain a composition
contract rather than a new semantic model:

- the vector binds a case id, exact input profile and digest, operation profile
  and digest, comparison profile and digest, resource limits, and expected
  axis-level dispositions;
- a successful observation carries an admitted artifact coordinate derived by
  the owning artifact adapter, never a caller-asserted semantic digest;
- a refused or invalid observation carries no artifact and uses the incumbent
  structured diagnostic channel;
- a transformation observation embeds or digest-binds the existing
  `ArtifactTransformationReportModel`; validation-only operations do not
  fabricate transformation provenance;
- pairwise artifact meaning is decided by the existing semantic-comparison
  request/result and owner projection, not by the wrapper; and
- the verdict reports artifact, diagnostic, and provenance axes independently
  with `equivalent`, `different`, `incomparable`, or `not-applicable`-style
  dispositions and bounded reason codes. A single boolean is insufficient.

The adapter category is descriptive metadata at most. Do not publish a closed
`cli | mcp | gui | docs` enum: it would turn current product shapes into semantic
classes and require a contract revision for the next transport. The extensibility
seam is the digest-bound input, operation, owner-projection, diagnostic, and
comparison profiles.

## Existing Authorities To Reuse

| Concern | Canonical incumbent and required use |
| --- | --- |
| Normative location and distribution | ADR-009/019, `specs/authority/authority-boundary.yaml`, `contracts/fixtures/`, and `raes_contracts.corpus`; vectors are normative fixtures and must ship in the packaged corpus. Examples, tests, and docs are not the vector authority. |
| SDL source admission | `SDLParserLimits`, `sdl-yaml/v1`, `parse_sdl()` / `parse_sdl_file()`, mapping-key analysis, safe YAML loading, migration policy, `Scenario`, and `SemanticValidator`; every SDL-producing path re-enters this production boundary. |
| Canonical SDL identity | ADR-076/078, `canonical_sdl_bytes()` and `canonical_sdl_digest()`; equality is profile-labelled semantic identity of a successfully validated authoring artifact, not YAML text, Python equality, or a caller-supplied hash. |
| Deterministic rendering | `render_sdl_source()` for model-to-source output and `format_sdl_source()` for explicit source migration/formatting; emitted bytes are reparsed. No adapter-specific YAML serializer is permitted. |
| Source-neutral synthesis | `CandidateSynthesisInputModel`, `CandidateSynthesisRecordModel`, the governed synthesis profile, and `synthesize_sdl_candidate()` when a vector actually exercises synthesis. Candidate synthesis is not the generic meaning of all authoring. |
| Transformation provenance | `ArtifactTransformationReportModel`, its all-or-none success/refusal invariant, source/target/policy/derivation digests, checks, identity maps, preservation, losses, and bounded diagnostics. Do not add an adapter provenance bag. |
| Semantic difference | `SemanticComparisonRequestModel`, `SemanticComparisonResultModel`, `contracts/profiles/semantic-comparison/reference-v2.json`, `coordinate_for_artifact()`, `build_impact_scope()`, owner projections, and `analyze_semantic_comparison()`. |
| Diagnostics | `SDLParseDiagnostic` and the existing SDL error channel for source-located parse diagnostics; `Diagnostic` / `DiagnosticModel` for portable diagnostics; `specs/sdl/diagnostics.md` for severity, stage, safety, and error/advisory meaning. |
| Validation claims | ADR-072, the validation-profile catalog, and `ValidationBasisDisclosureModel`; a conformance runner reports only gates actually run and never treats a private `semantic_validated` flag or fixture pass as a stronger claim. |
| Contract shape and ingress | `ContractModel(extra="forbid")`, shared scalar/digest types, discriminated unions, sorted-unique invariants, `x-raes-invariants`, and `parse_bounded_json_object()` / `StrictJsonIngressError`. |
| Conformance execution | `raes_conformance`, especially the fixture-suite and artifact-transformation runner patterns, `sanitized_failure_message()`, stable case ordering, confined fixture paths, and non-vacuous empty-corpus failure. |
| Adapter-neutral authoring core | `raes.language_service` is explicitly shared by MCP, CLI, and future LSP/editor adapters. Production parser, formatter, declaration-index, edit, and diagnostic functions remain below transports. |
| Workflow and publication | ADR-014, the canonical nox graph, `schema_bundle()`, `tools/generate_contract_schemas.py`, schema-publication entries, `tools/check_json_artifacts.py`, `tools/check_generated_schemas.py`, and repository policy/governance checks. |

No new ADR is needed while these boundaries hold. An ADR is warranted only if
implementation changes the meaning of semantic equality, creates a new SDL
lifecycle phase, changes normative diagnostic semantics, grants vectors a new
authority class, or introduces an authenticated/persistent conformance service.

## Comparison Semantics And Concept Boundaries

### Hold the input and operation fixed

"Same admitted input" means that the vector descriptor itself passes its closed,
bounded contract and binds one exact input payload by profile and digest. It does
not mean the payload must already be valid SDL; negative vectors need an admitted
test input whose expected authoring outcome is rejection. The adapter may not
read an ambient file, environment variable, network resource, pack, clipboard,
or UI state to complete the input unless that material is an explicit,
digest-bound vector resource admitted under the selected profile.

Input profiles are a closed registry seam, not an open `Any` payload. Initial
profiles should reuse ordinary strict SDL source and, where appropriate, the
source-neutral candidate-synthesis input. A candidate-synthesis source adapter
coordinate is provenance about an external assertion adapter; it must not be
reinterpreted as the CLI/MCP/GUI presentation path under test.

The operation profile fixes every meaning-affecting option: source format,
migration policy, semantic-validation strength, transform/synthesis profile,
canonicalization profile, and applicable limits. Defaults are part of the
profile. Two paths that silently select different migration or validation modes
did not execute the same operation.

### Compare independent axes

1. **Outcome and artifact.** Both successful paths must return artifacts admitted
   by the owning production gate. Their artifact coordinates and owner semantic
   projections are compared through semantic comparison. Exact source-byte or
   formatted-byte equality is an additional textual assertion only where the
   vector's rendering profile promises it.
2. **Diagnostics.** Compare stable code, severity, error/advisory classification,
   domain/stage, and canonical address. Compare source ranges only for vectors
   that supply the same exact source bytes and select a source-location profile.
   A structured graphical input may legitimately have no YAML range; that axis
   is `not-applicable`, not falsely equal. Human prose is safety-checked and
   bounded but is not the default semantic equality key.
3. **Transformation provenance.** Require the same admitted source digest,
   target canonical digest, operation/policy/canonicalization profiles, checks,
   preservation outcome, identity mapping, and loss semantics. A derivation
   digest or producer coordinate that intentionally binds the adapter path may
   differ; the comparison profile must expose that as a declared provenance
   difference rather than ignoring it or failing artifact equivalence.
4. **Semantic result.** When both sides have admitted artifacts, use the governed
   owner projection and exact two-sided impact scope. A digest mismatch alone is
   not a semantic difference; a digest match does not excuse a missing or
   indeterminate comparison context.

Mixed outcomes are first-class typed differences: success versus rejection,
error versus advisory, complete versus bounded/indeterminate comparison, and
lossless versus lossy provenance must never collapse to "not equal". When no
artifact exists, semantic comparison is `not-applicable`; a comparator must not
manufacture a placeholder artifact to satisfy the semantic-comparison schema.

### Promote an incumbent diagnostic shape; do not copy one

The repository currently has a portable `DiagnosticModel` and a richer
source-located `SDLParseDiagnostic`, plus several presentation projections. If
the published vector contract needs one portable source-location carrier, move
the existing SDL parse-diagnostic fields to the shared contract layer and make
the parser, language service, CLI, and MCP consume that one model. Do not define
a vector-only diagnostic schema, a new exception hierarchy, or another free-form
error envelope.

`raes_cli._semantic_result.CommandDiagnostic`, language-service dictionaries,
and the prose returned by `raes_mcp.tools.authoring` are presentation models,
not normative contracts. Their current differences are exactly what the
conformance projection must isolate; none may become the oracle by being copied
into fixtures.

## Cross-Cutting Security And Runtime Layers

The intended design passes all applicable layers below.

1. **Authentication and authorization.** The fixture corpus, comparator, and
   reference runner are pure offline code and have no authentication surface.
   Adapter or producer identifiers are provenance, not authenticated identity.
   Hub, env-packs, GUI, MCP hosts, and any future remote service authenticate and
   authorize their own requests before invoking RAES. Do not add tokens, roles,
   session state, or transport authorization to the vector contract.
2. **Secret-handling boundary.** Published vectors contain synthetic,
   non-sensitive values only. Real credentials, bearer tokens, private keys,
   environment dumps, customer data, live infrastructure identifiers, and
   operator secrets never enter vector resources, exact representations,
   diagnostics, provenance reports, snapshots, logs, or test failure output.
   Secret/redaction behavior can be tested with inert markers whose values are
   safe to publish. Existing SDL explicit-redaction validation remains the
   semantic authority.
3. **Portable JSON ingress.** Vector, profile, portable input, observation, and
   report JSON pass byte bounds, UTF-8/JSON parsing, duplicate-member and
   non-finite-number rejection, closed `ContractModel` shape validation, shared
   digest grammar, sorted-unique checks, and cross-reference/digest invariants.
   JSON Schema validation alone does not replace Python contextual invariants.
4. **SDL source shape.** SDL bytes pass `SDLParserLimits`, YAML 1.2 Core scalar
   resolution, single-document/tag/directive/alias/node/depth limits,
   duplicate/canonical-key checks, typed construction, identifier rules,
   migration policy, module composition where selected, and semantic validation.
   No vector or adapter may use `skip_semantic_validation` to claim equivalence.
5. **Configuration and environment binding.** Source format, migration mode,
   limits, operation, policy, and projection versions are explicit profile
   inputs. Ambient environment variables, current directory, locale, clock,
   hostname, username, random state, UUIDs, caches, and plugin discovery do not
   affect the expected artifact or comparison. SDL variables and synthesis
   decisions use their existing typed carriers; environment variables are not a
   second parameter-binding shape.
6. **Filesystem and network exposure.** Default cases are self-contained and
   network-disabled. Referenced fixture resources use safe corpus-relative paths,
   resolve beneath the fixture root, and are digest checked. File-backed import
   cases use `parse_sdl_file()` plus the existing resolver, trust, lock, export,
   collision, cycle, and composition-budget gates. A locator is never authority
   to fetch.
7. **OS/process exposure.** In-process calls are preferred. A CLI boundary case
   sends content through stdin or a confined temporary file; source content,
   parameters, secrets, and reports do not appear in process argv. Subprocess
   tests use fixed executable/operation arguments, a controlled environment,
   bounded stdout/stderr, no shell, no network, and no inherited path as
   semantic identity.
8. **Error envelope and logging.** Parser diagnostics preserve stable codes,
   canonical pointers, stages, and applicable ranges without raw values.
   Contract/conformance failures use `sanitized_failure_message()` rather than
   `str(exc)`, Pydantic input rendering, source snippets, tracebacks, or raw MCP
   payloads. The pure comparator logs nothing. Outer adapters may log stable case
   id, vector digest, operation/profile ids, status, and diagnostic codes, but
   not input or artifact bodies.
9. **Output and persistence.** Results are deterministic values returned to the
   caller. Normative vectors live in `contracts/fixtures/` and are packaged via
   `raes_contracts.corpus`; no database, mutable registry, cache, audit blob,
   control-plane store, or runtime snapshot is introduced. A durable external
   attestation remains owned by its product and may reference the vector and
   result digests.

## Whole-Repository Surfaces In Scope

- normative authority: `specs/`, `contracts/schemas/`, `contracts/fixtures/`,
  `contracts/profiles/`, `specs/authority/authority-boundary.yaml`;
- SDL core: parser/source profile, formatter/renderer, scenario models,
  declaration index, semantic validator, composition, canonical identity, and
  candidate synthesis;
- portable contracts: shared base/digest types, diagnostics, transformation
  reports, semantic comparison, validation profiles/disclosures, versions,
  bundle exports, and corpus resolution;
- adapters: semantic CLI, language service, MCP language-service and authoring
  wrappers; these consume the common observation and remain non-normative;
- conformance: fixture loading, confined resource resolution, case execution,
  safe diagnostics, stable reporting, and an explicit no-cases failure;
- publication and verification: schema publication entries, generated-schema
  parity, JSON-artifact routing, corpus packaging tests, determinism witnesses,
  repository policy, requirement governance, and the canonical nox graph.

## Gotchas And Anti-Patterns

- Do not compare YAML/JSON text, Pydantic dumps, command stdout, screenshots,
  user-visible success strings, or task completion as semantic equivalence.
- Do not let an adapter submit its own canonical digest, validation flag, or
  semantic projection as trusted evidence. Derive them from admitted artifacts.
- Do not compare successful artifacts by recursively diffing dictionaries;
  owner projections and the semantic-comparison profile own meaning.
- Do not add a second parser, renderer, schema validator, semantic validator,
  declaration resolver, canonicalizer, diagnostic taxonomy, exception tree, or
  transformation report for conformance.
- Do not reuse `BackendConformanceReport` for authoring adapters. Backend/runtime
  realization, native execution, and authoring equivalence are different claims.
- Do not overload `ArtifactTransformationReportModel` as a test report or
  adapter identity. It owns one semantic operation and its provenance.
- Do not treat candidate synthesis as every authoring path, or treat its source
  adapter coordinate as the UI/transport adapter under comparison.
- Do not promote `SemanticCommandResult.payload`, legacy MCP prose responses, or
  language-service dictionaries into normative contracts. They are projections.
- Do not hard-code current adapter classes into schemas, case directories, or
  comparison branches. Select behavior by governed profiles and owner kinds.
- Do not permit fixture-relative paths to escape the corpus root, remote URLs to
  fetch content, caller-selected import paths, plugin/module names, or callbacks.
- Do not generate expected fixture outputs at test time with the same production
  function being tested. Checked-in expected digests, diagnostics, and typed
  dispositions are independent regression oracles and must have non-vacuous
  mutation/difference cases.
- Do not claim universal adapter equivalence from a finite vector corpus. The
  result is conformance to the named vector/profile revision with explicit
  limitations.

## Non-Goals And Ownership Boundary

- No GUI, editor, LSP, MCP server, CLI user journey, documentation renderer, or
  agent skill is designed or implemented here.
- No cross-product task coordination, usability study, or acceptance workflow;
  Hub HUB-6 / #33 owns those concerns.
- No env-pack authoring, pack file, pack diagnostic, pack resolution, or pack
  persistence; env-packs owns them.
- No backend realization, live execution, runtime/evidence outcome, participant
  behavior, or scientific-success claim; conformant backends and experiment
  contracts own those surfaces.
- No authentication service, remote retrieval, plugin discovery, database,
  cache, telemetry pipeline, audit store, or control-plane endpoint.
- No change to SDL syntax, lifecycle phases, semantic meaning, canonical address
  rules, diagnostic severity, or validation-strength taxonomy merely to make two
  adapters look equal.
- No requirement that presentation bytes, labels, layout, source ranges across
  unlike source forms, or human diagnostic prose be identical.
