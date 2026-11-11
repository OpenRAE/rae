# Source-neutral SDL candidate synthesis

## Scope and ownership

RAES accepts governed, versioned external assertions as authoring input and may
produce an ordinary SDL candidate. It owns the neutral assertion contract,
transformation provenance, semantic-loss/refusal representation, deterministic
candidate rendering, and re-entry through normal SDL validation.

Source adapters and env-packs own retrieval, credentials, pagination,
source-specific parsing, extraction-query execution, and pack orchestration.
Hub owns user journeys. The RAES core performs no network access, plugin
discovery, environment lookup, subprocess dispatch, or source-specific branch.

The published contracts are:

- `contracts/schemas/candidate-synthesis/sdl-candidate-synthesis-input-v1.json`;
- `contracts/schemas/candidate-synthesis/sdl-candidate-synthesis-profile-v1.json`;
- `contracts/schemas/candidate-synthesis/sdl-candidate-synthesis-record-v1.json`.

## Pinned input boundary

`sdl-candidate-synthesis-input/v1` binds one complete assertion set to:

- source authority, scheme/assertion-format identity, revision, content
  digest, and canonical assertion-set digest;
- extraction-query id, version, and digest;
- source-adapter id, version, and digest;
- transformation-profile id, version, and digest;
- one or more exact information-flow policy references whose constraints remain
  attached to the source and copied into the synthesis record;
- policy digest, assumptions, and explicit author or governed-policy
  decisions; and
- the target SDL scenario identity and version.

The closed assertion union distinguishes concepts, relationships,
preconditions, ordering, parameterization, and examples. External concept and
relation terms reuse `ExternalConceptSchemeCoordinateModel`. Assertion
coordinates must join exactly to the source envelope, all internal references
must resolve, and identities and collections use deterministic order. A
locator remains inert and is never permission to fetch.

The bounded JSON ingress rejects excess bytes, duplicate members, non-finite
numbers, unknown fields, invalid discriminators, stale pins, and mismatched
assertion-set digests before synthesis.

## Trusted transformation profile

The initial fixed profile is the canonical artifact
`contracts/profiles/candidate-synthesis/concept-nodes-v1.json`. It maps a
concept assertion to an ordinary SDL node only when exactly one explicit
decision provides the canonical `nodes.<id>` target and native node type. Its
digest covers every output-affecting rule id, default id, supported type,
limit, refusal posture, rendering profile, and canonicalization profile.
Dispatch is keyed by the artifact's exact id, version, and complete-content
digest; source authority, scheme id, query text, URI, module path, class name,
callback, or plugin name cannot select code.

The profile does not guess relations, ordering, preconditions,
parameterization, identifiers, or defaults. Unsupported or unresolved meaning
returns one of the typed reasons:

- `ambiguous-ordering`;
- `missing-native-semantics`;
- `unsupported-relation`;
- `unresolved-parameterization`;
- `stale-input`; or
- `transformation-profile-unavailable`.

A material unresolved choice produces no candidate bytes, canonical candidate
digest, or construct traces. It is never hidden in SDL prose, placeholders,
empty collections, arbitrary relationships, or guessed values.

## Candidate and provenance record

A successful operation returns strict ordinary `sdl-yaml/v1` and a separate
`sdl-candidate-synthesis-record/v1`. The record composes
`ArtifactTransformationReportModel` and keeps these surfaces distinct:

- imported source assertions;
- transformation assumptions;
- unresolved choices;
- explicit author or governed-policy decisions;
- generated native construct traces; and
- transformation checks, diagnostics, digests, and loss evidence.

Construct contributions use the closed origins `imported-assertion`,
`transformation-assumption`, `inferred-structure`, `transformation-default`,
`author-decision`, and `governed-policy-decision`. Supporting an origin does
not authorize the engine to invent one: every contribution names an exact
assertion, admitted assumption, profile rule/default, or decision.

The record embeds the complete admitted input and, on success, the complete
transformation profile artifact. It recomputes the input digest and resolves
every contribution against those embedded owners. The record separates the
input/derivation digest, exact UTF-8 candidate digest, and canonical SDL
semantic digest. Source, query, adapter, profile, policy, assumption, or
decision changes therefore remain inspectable even when the SDL semantic
candidate is unchanged. An unavailable-profile refusal carries no invented
profile artifact.

## Validation and admission

The engine builds a closed authoring value, renders deterministic YAML through
the shared SDL formatting seam, and reparses the emitted bytes with production
`parse_sdl()` and semantic validation. It does not use
`skip_semantic_validation` and does not add generated-content syntax or a
validated bypass flag.

After review, the candidate follows the manual lifecycle unchanged:

`parse/composition -> semantic validation -> instantiation -> instantiated admission -> compiler/planner admission`

Synthesis success is not instantiation, admission, compilation, planning,
backend support, execution, observation, truth, or equivalence. Semantic
changes between candidates use the existing governed semantic-comparison
profile and owner adapter. Derivation change and SDL semantic change are
reported as separate axes.

Where a generated candidate creates an exact RAES subject for an external
concept, integrations may emit the ordinary `external-concept-bindings/v1`
document after that subject exists and must use
`admit_external_concept_bindings()` with pinned local snapshots. The synthesis
record does not duplicate or weaken that binding contract.

## Information and failure handling

Aggregation, derivation, hashing, and SDL generation do not declassify source
information. Portable inputs, records, diagnostics, fixtures, and candidates
must not contain retrieval credentials, request headers, operator secrets,
environment-driven semantics, or sensitive query parameters. Participant
delivery remains behind the existing authenticated audience, information-flow,
redaction, disclosure, and audit boundaries.

Expected ambiguity and unsupported meaning are typed dispositions with bounded
diagnostics. Diagnostics identify stable codes and safe record/assertion
addresses; they do not echo rejected source bodies, query text, secret-bearing
locators, exception payloads, or environment state.

## Non-goals

This contract does not promise automatic semantic equivalence, make an
external assertion executable, add source-specific syntax or retrieval, create
a pack workflow, or automatically admit, instantiate, compile, realize, or
execute a candidate. It adds no database, cache, mutable registry, API,
controller, or parallel conformance workflow.
