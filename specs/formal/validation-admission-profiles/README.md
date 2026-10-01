# Validation and Admission Profiles Formal Specification

This domain specifies the ASR-511 and ASR-515 validation/admission profile
model. It defines how RAES distinguishes structural, semantic, behavioral, and
stronger validity claims, and how artifacts disclose the basis and limitations
of those claims.

This specification originated as the docs/spec design artifact for issue #97.
Issue #97 itself did not publish schemas, fixtures, Python models, validators,
API endpoints, runtime behavior, storage, or conformance probes. Follow-on
issues #258 and #259 now provide the bounded validation-profile and
validation-basis disclosure contracts, schemas, fixtures, models, validators,
carrier integrations, and focused tests described in the implementation
coverage below. Those delivered surfaces do not expand this specification's
normative claim boundaries or make every validation claim equally strong.

## FM Classification

Classification: FM2, Semantic Graph / Constraint.

Rationale:

- The design is more than local shape. It defines ordered strength classes,
  profile membership, gate results, evidence references, and cross-artifact
  disclosure semantics.
- The required properties include type separation, no implicit strength
  escalation, explicit weak or absent gates, safe publication views, and reuse
  of existing scenario, experiment-core, participant-runtime, conformance, and
  claim-evidence authorities.
- The executable evidence for this issue is structural policy verification
  over the authority roots. Contract models and validators are owned by the
  spawned implementation issues.

## Authoritative Artifacts

- Architecture decision:
  `docs/decisions/adrs/adr-072-validation-and-admission-profiles.md`.
- Normative prose: this directory.
- Preflight guardrails:
  `docs/decisions/issue-97-asr-511-515-validation-strength-disclosure-preflight.md`.
- Clause matrix:
  `docs/research/validation-admission-profiles/traceability-matrix-asr-511-515.md`.

## Definitions

### Validation Subject

A validation subject is the artifact or claim whose basis is being disclosed.
Initial subject kinds are:

- `scenario`;
- `scenario_snapshot`;
- `experiment_task`;
- `experiment_run`;
- `experiment_study`;
- `backend_conformance_claim`;
- `participant_conformance_claim`; and
- `published_claim`.

A subject reference must be stable enough for the audience that reads the
disclosure. Public subjects use portable ids, contract refs, digests, or
artifact refs. Internal subjects may use stronger private references, but a
public view must not expose backend-native ids, hidden truth, secrets, raw
payloads, or process details.

### Validation Profile

A validation profile is a governed description of a validation basis. It has:

- a profile id and version;
- an intended subject-kind set;
- a minimum strength class;
- required and optional gate kinds;
- evidence and diagnostic expectations;
- limitation categories; and
- extension rules.

The profile id must identify this profile family. A field named only `profile`
is ambiguous unless its contract or vocabulary binding says whether it is a
validation profile, semantic profile, backend profile, instantiation profile,
or another governed profile family.

### Strength Class

Strength classes are ordered from weakest to strongest:

1. `structural`
2. `semantic`
3. `behavioral`
4. `evidence_backed`
5. `falsification_backed`

`structural` means syntax, schema, closed-world shape, type, and vocabulary
checks passed.

`semantic` means structural validation passed and RAES domain invariants,
reference resolution, lifecycle separation, and cross-artifact consistency
checks passed for the subject.

`behavioral` means semantic validation passed and a concrete processor,
backend, runtime, conformance, or admission path exercised the relevant
behavior and returned governed diagnostics.

`evidence_backed` means the semantic or behavioral claim is backed by
preserved evidence, provenance, diagnostics, and limitations sufficient for
review.

`falsification_backed` means the evidence-backed claim has an explicit
falsification protocol and evidence status under ADR-021.

### Gate Result

A gate result records one check that contributed to the basis. Gate result
statuses are:

- `passed`;
- `failed`;
- `partial`;
- `not_run`;
- `not_applicable`;
- `unknown`;
- `unsupported`; and
- `withheld`.

Gate results may reference validators, processors, backends, conformance cases,
diagnostics, evidence records, artifacts, digests, or reports. A gate result
must not inline secrets, hidden answers, raw evidence payloads, prompts,
environment dumps, process argv, backend-private object representations, or
full tracebacks.

### Validation-Basis Disclosure

A validation-basis disclosure states what supports one subject's validity or
admission claim. It carries:

- `subject_ref` and subject kind;
- profile id and version;
- achieved strength class;
- gate result rows;
- producer or validator reference;
- evidence, artifact, diagnostic, or report refs;
- limitations and not-covered disclosures;
- issuance time or version context; and
- optional publication scope or audience.

The disclosure can be embedded in a carrier or published as a referenced
artifact. Either form preserves the same semantics.

## Invariants

### Strength And Gate Ordering

1. A disclosure MUST NOT claim a strength class higher than the strongest gate
   basis actually represented by its gate results.
2. A required gate with status `failed`, `partial`, `not_run`, `unknown`,
   `unsupported`, or `withheld` MUST lower or qualify the achieved strength.
3. A structural gate alone MUST NOT support a semantic, behavioral,
   evidence-backed, or falsification-backed claim.
4. A semantic gate alone MUST NOT support a behavioral claim unless a concrete
   processor, backend, runtime, conformance, or admission path is represented.
5. An evidence-backed claim MUST cite reviewable evidence, provenance,
   diagnostics, or artifact refs.
6. A falsification-backed claim MUST cite a falsification protocol and evidence
   status under ADR-021.

### Disclosure Completeness

7. A disclosure MUST name its subject, profile id, profile version, achieved
   strength, and gate results.
8. A disclosure MUST represent weak, absent, unsupported, withheld, or unknown
   required gates explicitly; omission is not a valid way to preserve a
   stronger claim.
9. A disclosure MUST include limitations whenever evidence is redacted,
   withheld, lossy, partial, unavailable, or audience-restricted.
10. A disclosure MUST distinguish internal strength from public strength when
    a public view hides evidence or diagnostics.

### Authority Separation

11. Validation profiles MUST NOT be treated as GOV-920 semantic profiles,
    backend capability profiles, scenario-instantiation profiles, SEM-218
    realization support, API-407 feature support, or participant action
    admission dispositions.
12. Participant action `admission_disposition` MUST NOT carry scenario, task,
    run, study, conformance, or claim validation-basis results.
13. Private in-memory validation flags MUST NOT be portable disclosure
    records.
14. Runtime snapshots, operation details, audit blobs, backend logs, tags, and
    free-form metadata MUST NOT be the only carrier for validation strength.

### Carrier Reuse

15. Scenario and scenario-snapshot disclosures MUST build on SDL parsing,
    closed-world models, semantic validation, instantiation, and scenario
    snapshot identity rather than raw YAML dictionaries or source-file layout.
16. Experiment task disclosures MUST preserve task protocol, apparatus
    constraints, validity notes, and supporting artifact separation.
17. Experiment run disclosures MUST preserve run traceability, apparatus
    context, realized-form disclosures, augmentation disclosures, evidence
    artifacts, result summaries, and lineage separation.
18. Experiment study disclosures MUST preserve membership, allocation,
    factors, analysis plan, validity notes, and report/export separation.
19. Conformance disclosures MUST use governed conformance diagnostics and
    published profile/contract refs rather than backend-native logs.

### Safe Publication

20. Disclosures, diagnostics, fixtures, examples, logs, and API responses MUST
    NOT expose credentials, bearer tokens, private keys, hidden answers,
    prompts, raw evidence payloads, backend-native object reprs, process argv,
    environment dumps, or full tracebacks.
21. Public disclosures SHOULD prefer ids, refs, digests, diagnostic codes,
    bounded summaries, and redacted evidence refs.

## Non-Goals

- No schema or fixture is published by issue #97.
- No Python contract model or validator is added by issue #97.
- No runtime, processor, backend, API, persistence, evidence store, or UI
  behavior is added by issue #97.
- No existing validation, admission, conformance, concept-authority, or
  profile subsystem is redesigned by issue #97.

## Implementation Coverage

Issue #97 establishes the architecture and normative semantics for ASR-511 and
ASR-515. The follow-on implementation work is now delivered:

- #258 publishes the ASR-511 validation-profile taxonomy, catalog, contracts,
  schemas, fixtures, validators, and carrier integration, with focused
  coverage in `test_validation_profiles.py`.
- #259 publishes the ASR-515 validation-basis disclosure contracts, schemas,
  fixtures, models, validators, and carriers, with focused coverage in
  `test_validation_disclosure.py`.

These are bounded contract and validator surfaces. They do not turn a
structural check into a semantic, behavioral, evidence-backed, or
falsification-backed claim without the corresponding governed gate evidence.

### Governed scenario satisfiability

ADR-086 adds `raes-finite-domain-satisfiability-v1` as a concrete
falsification-backed analysis boundary for its explicitly bounded SDL fragment.
Its `scenario-satisfiability-evidence/v1` envelope records the exact source,
normalized constraint model, pinned solver configuration, completed outcome,
and witness/core/unsupported payload. The profile's detailed theory,
translation coverage, replay rules, and nonclaims are normative in
[`specs/formal/scenario-satisfiability/`](../scenario-satisfiability/README.md).

This profile does not upgrade the general validation strength of every
scenario. Unsupported occurrences remain an explicit unsupported gate, and
backend realization and runtime behavior remain separate gates.

### Typed exploit-path analysis

Issue #827 adds `raes-exploit-path-analysis-v1` as a concrete typed
attack-transition graph/query boundary for an admitted instantiated scenario
snapshot. Its `exploit-path-analysis-evidence/v1` envelope records the exact
input source, authored digest, snapshot digest, normalized attack graph, query,
search configuration, completed outcome, and one of witness, invalid-path
failure evidence, or unsupported disclosure. The profile's transition,
binding, query, replay, diagnostics, and nonclaims are normative in
[`specs/formal/exploit-path-analysis/`](../exploit-path-analysis/README.md).

This profile does not upgrade weaker evidence into exploit-path proof. Network
reachability, topology connectivity, service/listener presence, vulnerability
or ATT&CK labels, workflow reachability, scenario satisfiability, objective
success, participant-local action success, backend realization, deployment
success, scanner output, and runtime observation remain separate gates unless
the exploit-path graph contains governed bindings and transitions that state
exactly how those facts participate in the v1 path semantics.
