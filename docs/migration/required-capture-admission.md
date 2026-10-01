# Required Capture Admission Migration

Issue #1237 returns an immutable, process-local content proof from authoritative
run validation. Metadata is snapshotted and revalidated before reader callbacks;
consumers must retain that proof and reject it after task/run content changes.
Revalidate from bytes after serialization or a process boundary.

Evidence validation admits at most 1024 artifacts, capture specifications,
capture requirements, records, or reader entries per invocation, with 256 MiB
aggregate declared artifact bytes and 64 MiB per artifact. Shared artifacts are
read once, but every capture requirement still receives its own relation,
metadata, integrity, output-contract, and field-selector checks. Artifact
locators remain inert: credential userinfo, secret query fields, fragments, host
paths, and `file:` URIs are rejected; published relative artifact paths remain
supported. Proof bindings retain only a locator identity digest.

Issue #1112 changes capture support from descriptive capability discovery to a
fail-closed execution contract.

Backend manifests that may execute SDL `evidence_requirements` or experiment
capture specifications must publish `capabilities.observation.capture_offers`.
Each offer is atomic: it binds the output contract and fields to the artifact,
media, capture, source, scope, channel, window, integrity, sensitivity,
availability, fidelity, disclosure, retention, and export terms that are
actually supported. Legacy `supported_*` lists remain discovery summaries and
are not an admission fallback. A manifest with no matching offer is rejected
before effects. The in-repo stub and reference-emulation manifests deliberately
publish no capture offers because their runtimes do not implement the promised
artifact production path; tests that exercise admission declare narrow,
scenario-specific offers explicitly.

Offers for SDL requirements that use `scope_refs` must enumerate the exact
authored targets in `scope_refs`; `*` is rejected. Trial compilers resolve
scenario-family variables before matching these and all other capture terms.

SDL authors should add `output_contract` and `field_selectors` whenever an
authored evidence requirement is intended to execute. Existing requirements
that omit both fields remain structurally readable, but they cannot make a
field-level output promise. Precise installation declarations do not imply a
capture requirement.

Trial compilers must acquire every referenced capture-spec payload and include
its digest in `admitted-trial-plan-v1.input_refs.capture_spec_refs`. Missing,
substituted, ambiguous, or unsupported capture specs fail admission. Trial
realization supplies the same exact payloads and rechecks the selected backend.

Run consumers that make evidence-satisfaction claims use
`validate_experiment_run_evidence()` with exact capture specs, evidence records,
and bounded byte readers. The validator does not fetch URIs. It checks the
artifact identity, byte count, checksum, media and role, required integrity,
the authoritative `output_contract` schema and owning semantic model, RFC 6901
field selectors, required redaction state, and sensitivity across requirement,
record, and artifact. Study conditions that require evidence consume the same
validated requirement-to-artifact bindings.
Historical `satisfies_refs`, payload summaries, and backend assertions remain
metadata; they are not proof of emitted content.

## Media-type coherence (issue #1401)

Required capture currently has a closed, JSON-based output-proof vocabulary.
Until a separately governed byte contract and verifier exist for another
encoding, the eligible media types are `application/json` and the registered
array-root `application/jsonl` encoding. Reject an entire authored
SDL `media_types` list or experiment `expected_media_types` list if any member
is unsupported; a supported alternative must not mask an impossible one.
`text/plain`, `application/x-ndjson`, and PCAP are therefore invalid required
capture declarations. This tightens earlier SDL authoring behavior, including
the PCAP example in the DSL-124 test, and needs an explicit authoring diagnostic.
An omitted SDL media-type list remains unconstrained on this dimension.

The authoritative eligibility source is
`raes_contracts.evidence_output_validation.evidence_output_registrations()`:
registry resolution couples each output-contract id to its published schema,
semantic validator, and JSON root, from which the supported encodings derive.
An explicit SDL `output_contract` or a
capture-spec `output_contract` must resolve there, and every declared media
type must be valid for that specific contract. An SDL requirement with no
output contract retains its existing intent-only semantics, but its declared
media types must still belong to the union of eligible encodings. In particular,
`application/jsonl` cannot be paired with the object-root
`experiment-evidence-record-v1`. Neither that record contract nor an arbitrary
`application/json` label licenses unrelated JSON or text artifact bytes.

Keep one eligibility rule shared by SDL and capture-spec validation and the
existing offer and content validators. The model validators must expose an
explicit unsupported-media or incompatible-contract error; the published SDL,
capture-spec, and backend-manifest schemas and their semantic-invariant metadata
must not imply broader eligibility. Preserve the existing atomic offer matcher,
admission diagnostics, bounded byte reader, checksum and locator checks, schema
and semantic validation, RFC 6901 field checks, and process-local proof object.
The field selectors address the decoded JSON document; for JSON Lines they
address the decoded array. Do not interpret them as selectors into arbitrary
text, or use an evidence-record envelope as a stand-in for the artifact bytes.

This decision governs required-capture proof, not descriptive legacy
`supported_media_types` summaries, runtime capture implementation, storage,
export, or a generic non-JSON contract framework. A future encoding belongs as
an explicit registry-owned contract/encoding plus bounded byte parser and
content proof, with publication and conformance evidence before it becomes
eligible at authoring or in an offer. No URI fetch, credential handling, or
serialized proof token is introduced here.

## Shared proof and extension points

Issue #1237 makes `validate_experiment_run_evidence()` and
`validate_experiment_run_against_task()` return `ValidatedRunEvidence` from
`raes_contracts.evidence_proof`. Task observation checks, metric artifact
relations, study allocation, and evidence conditions consume that proof.
Its bindings contain immutable snapshots of the validated capture, record,
and artifact identities. Canonical task/run content digests prevent reuse for
another run or after the validated inputs change. Callers must obtain a new
proof by validating the exact content again; reference tuples and serialized
metadata cannot construct a proof. Structural-only validation does not produce
evidence bindings.

Evidence output eligibility lives in
`raes_contracts.evidence_output_validation.evidence_output_registrations()`.
Each entry couples a published schema resolved through the contract corpus,
the owning semantic validator, and its JSON root. JSON Lines is supported only
for array roots. Offers and emitted content fail closed if either the schema
or semantic owner is missing. Schema references resolve offline.
`contracts/schema-publication-manifest.json` remains the publication ledger.

Capture extensions use `raes_contracts.capture_dimensions.CAPTURE_DIMENSIONS`.
Each dimension declares its authored projection, collection representation,
comparison rule, and diagnostic. The Pydantic offer and protocol dataclass
retain explicit fields. Additions must cover both authored projections,
manifest round trips, independent matching/diagnostic cases, and the shared
pre-effect conformance tests. Exact scope targets, wildcard subsets, media
overlap, availability, fidelity, and disclosure retain distinct semantics.
