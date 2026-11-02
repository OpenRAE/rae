# Portable Artifact Requirement Satisfaction

Status: normative

Requirement: #920

Decision: [ADR-098](../../docs/decisions/adrs/adr-098-portable-artifact-requirement-satisfaction.md)

This specification defines how a backend-neutral `Source` can require and
prove a concrete artifact without conflating semantic identity, operational
availability, acquisition, materialization, or observed build provenance. The
machine-readable authority is `artifact-requirement-v1` under
`contracts/schemas/artifact-requirements/`.

## 1. Contract family and ownership

The semantic family has three phase-specific carriers:

1. `Source.artifact_requirement` is author-owned demand.
2. `backend-manifest-v2.realization_support[].artifact_mechanisms` is
   backend-owned capability.
3. `RealizationProvenanceEntry.artifact_satisfaction` is backend-produced,
   processor-validated runtime disclosure.

The carriers MUST NOT be collapsed. Operational availability is supplied to
planning separately and MUST NOT be serialized into semantic requirement
identity. Absence of `Source.artifact_requirement` preserves selector-only
`Source` behavior and is not a fourth explicitness posture.

## 2. Requirement posture

Every present requirement has a stable `requirement_id`, one existing
explicitness class, and at least one permitted satisfaction route.

### 2.1 Exact

An exact requirement MUST:

- name exactly one immutable `ArtifactIdentity`;
- bind provider-neutral artifact id, version, SHA-256 digest, and media type;
- match its owning `Source.name` and `Source.version`;
- use only the `exact-artifact` mechanism; and
- declare no constraints, candidates, locked inputs, or materialization
  specifications.

An implementation MUST reject unavailable exact bytes. It MUST NOT fall back
to another digest, rebuild the artifact, substitute a compatible version, or
reinterpret a wildcard selector as exact evidence.

### 2.2 Constrained

A constrained requirement MUST NOT carry `exact_artifact` and MUST declare a
non-empty bounded authority domain through one or more of:

- typed constraints with finite allowed values;
- explicitly admitted immutable candidates;
- immutable locked inputs joined to associated-artifact and trust-policy
  references; or
- digest-bound materialization specifications whose input ids resolve to those
  locked inputs.

Candidate order is not fallback order. A backend may select only a declared,
available candidate and MUST disclose the selected `candidate_id`.
Materialization authority is a closed profile reference, not shell text,
environment variables, a Dockerfile, or `Source.build`.

### 2.3 Open

An open requirement MUST NOT carry `exact_artifact`, candidates, artifact
constraints, or materialization specifications. It may still require immutable
inputs and trust policy. It delegates output selection only to a backend whose
matching realization declaration has
`support_mode: open-realization` and a matching permitted mechanism route.
Open does not waive trust, evidence, or disclosure obligations.

## 3. Mechanisms, acquisition, and timing

A mechanism is identified by `mechanism`, `profile`, `version`, and SHA-256
profile digest. Portable base mechanisms are:

- `exact-artifact`;
- `backend-owned-artifact`;
- `published-candidate`;
- `dynamic-composition`; and
- `materialization-specification`.

Extensions MUST use `x-<authority>:<term>`. Arbitrary free-form mechanism names
are invalid.

Acquisition is one of `pull`, `copy`, `import`, `local-lookup`, or `none`.
Timing is one of `publication`, `pack-ingestion`, `backend-preparation`, or
`realization`. These dimensions are orthogonal to posture and mechanism.
Backend capability MUST enumerate exact acquisition/timing pairs under each
mechanism profile; separate unjoined lists are non-conforming because they
claim a Cartesian product.

## 4. Compilation and admission

The processor MUST lower a present requirement into the existing compiled
realization-demand graph at every realized owner:

- node or switch/network;
- content;
- feature binding;
- condition binding;
- inject; or
- event.

The compiled requirement uses domain `runtime-realization`, kind
`source-artifact`, the authored explicitness/provenance, the canonical resource
address, and the authored requirement payload. It MUST NOT create a second
planner or artifact resource graph.

Planning admits a requirement only when:

- the posture is supported by the matching realization declaration;
- one permitted mechanism/acquisition/timing route is advertised;
- the exact digest is available for exact demand;
- every required constraint id is satisfied;
- every locked input id is verified; and
- at least one candidate id is available when candidates are declared; and
- at least one authored materialization-specification digest is available when
  materialization alternatives are declared.

Operational fact inputs MUST be partitioned by canonical compiled address.
Candidate ids, constraint ids, and locked-input ids are local to one
`ArtifactRequirement`; a fact admitted for one address MUST NOT satisfy a
same-named declaration at another address. The processor-owned availability
context also carries the integrity, authenticity, admission, provenance, and
evidence references that its trust boundaries have independently verified.
Registry URLs, cloud regions, account/project ids, channels, credentials,
tokens, and host paths MUST NOT enter semantic identity or diagnostic text.

Stable admission diagnostics are:

| Failure | Code |
|---|---|
| Exact artifact unavailable | `artifact.unavailable-exact-artifact` |
| Constraint not satisfied | `artifact.unsatisfied-constraint` |
| Open realization unsupported | `artifact.unsupported-open-realization` |
| Locked input not verified | `artifact.missing-locked-input` |
| No candidate available | `artifact.unavailable-candidate` |
| No materialization specification available | `artifact.unavailable-materialization-specification` |
| No exact supported mechanism route | `artifact.unsupported-backend-mechanism` |

## 5. Runtime satisfaction and provenance

Before accepting a returned snapshot, the processor MUST parse
`payload.artifact_satisfaction` as the closed satisfaction contract and check:

- `requirement_id` equals the compiled requirement;
- the disclosed backend identity equals the selected manifest identity;
- mechanism, acquisition, and timing equal one permitted route and one
  mechanism-indexed capability route admitted from that manifest;
- an exact artifact equals the authored immutable identity;
- a disclosed candidate resolves to its declared immutable artifact and was
  available for this compiled address;
- a materialization selection resolves to a declared specification, uses that
  specification's digest-bound mechanism profile, discloses its exact authored
  specification digest, and discloses exactly its locked inputs;
- every disclosed constraint and locked-input id was independently admitted
  for this compiled address;
- the realized artifact digest is present in both the disclosure and the
  processor-owned verified integrity set; and
- the selected materialization-specification digest is present in the
  address-scoped trusted availability context; and
- authenticity, admission, provenance, and evidence references are subsets of
  the processor-owned verified sets, including every authored trust-policy or
  associated-artifact reference.

Omission, malformed disclosure, route substitution, or exact artifact
substitution MUST reject the backend result with
`runtime.backend-contract-invalid`. A valid disclosure is attached to the
existing `RealizationProvenanceEntry` before snapshot persistence. Exact
satisfaction retains `author-declared` provenance; backend selection on an
admitted constrained or open surface is `backend-realized`.

The disclosure may carry authenticity, admission, provenance, and evidence
references. It MUST NOT carry location or channel fields. Backend-provided
reference strings do not prove authenticity or integrity: the runtime gate
accepts them only when they resolve through the processor-owned verification
context established by the applicable trust and evidence contracts.

## 6. Security and conformance

All public models and schemas are closed. Implementations MUST reject these
inputs:

- unknown fields;
- duplicate semantic ids or routes;
- invalid digest syntax;
- ungoverned mechanism names;
- unresolved materialization input joins;
- contradictions between posture and authority.

The published schema structurally requires `Source.artifact_requirement`.
Draft 2020-12 cannot express cross-object equality and local-id joins, so the
governed `x-raes-invariants` profile publishes them. Diagnostics MUST identify
stable requirement, field, and capability terms. They MUST NOT echo realized
values or operational secrets.

This specification authorizes no network access, registry mutation,
credential lookup, archive extraction, subprocess execution, or artifact
build. Conformance is established by the typed models, Draft 2020-12 published
schemas, valid/invalid fixtures, compiler/planner/runtime tests, and schema
publication ledger parity.
