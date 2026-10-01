# ADR-078: Closed SDL Phase Contracts and Portable Derivation Evidence

## Status

accepted

## Date

2026-07-12

## Classification

Classification: FM2

Required artifacts: ADR, normative phase invariants, distinct typed phase
representations, published schemas and fixtures, cross-phase conversion tests,
and serialized-artifact differential tests.

Waivers: no theorem prover or static typestate checker is required. The Python
reference implementation enforces these contracts at runtime and does not claim
that arbitrary Python code cannot use unsafe construction APIs.

## Context

ACES previously represented an instantiated scenario by subclassing the
authoring model. The generated `instantiated-scenario-v1` schema therefore
retained `variables`, `imports`, and `module`, even though the normative SDL
prose said variable definitions do not survive instantiation. Resolution facts
needed by the processor lived in Python private attributes. A deserialized
artifact could lose those facts, and a caller could ask the compiler to skip
semantic validation.

The phase name consequently promised more than the type and schema guaranteed.
That is unacceptable for an exchange artifact used in reproducible experiments:
an independent producer must be able to tell which fields belong to a phase,
an independent consumer must be able to reject phase-inappropriate fields, and
the processor must not obtain different meaning from in-process private state.

## Decision

### 1. Use disjoint closed representations

Let `C` be the common executable scenario sections. ACES defines these phase
shapes:

```text
NormalizedAuthoring = C + {module, imports, variables}
ExpandedAuthoring   = C + {variables, expansion_provenance}
Instantiated        = C + {instantiation_provenance}
Snapshot            = {profile, scenario: Instantiated}
Materialized        = C + {materialization_provenance}
```

The sets are exact. A field not shown for a phase is forbidden, including an
empty `variables: {}`, empty `imports: []`, or `module: null` shell.

`Scenario` is the normalized authoring representation. It accepts only local
declaration identities. `ExpandedScenario` is an internal, trusted result of
module resolution and namespace rewriting. It may carry generated qualified
identities and remaining root variables, but it has no `module` or `imports`
member. `InstantiatedScenario` is not a subtype of `Scenario`; it has no
authoring-machinery member or compatibility property. The private structural
binder may construct bound content but cannot mint the public instantiated
type.

`ExpandedScenario` is not published as an exchange schema. It carries
resolver-produced trust context and exists only between composition and final
instantiation. The two public derived contracts are
`instantiated-scenario-v1` and
`instantiated-scenario-snapshot-v1`. The descriptive public phase added by
#1241 is `materialized-scenario-v1`; it shares the common scenario vocabulary
but has no authoring or instantiation machinery.

### 2. Make phase transitions partial and fail closed

The supported public path is:

```text
sdl-yaml/v1
  -> normalized Scenario
  -> trusted ExpandedScenario (when imports exist)
  -> InstantiatedScenario
  -> optional canonical snapshot
```

Each arrow is a partial function: invalid input has no output artifact.
`instantiate_scenario()` always validates its authoring input, binds once,
reconstructs the closed instantiated representation, validates provenance
consistency and absence of substitution tokens, and reruns semantic validation.
There is no public `validate_semantics=False` option.

Direct or deserialized instantiated artifacts use
`admit_instantiated_scenario()`. Compiler entry points apply that same semantic
admission before lowering. Canonical snapshot creation also admits the artifact.
Pydantic's `model_construct()` remains an explicitly unsafe framework escape
hatch and is not an ACES ingestion API.

### 3. Carry replay-relevant derivation evidence on the wire

Every instantiated artifact contains a required, closed
`instantiation_provenance` value with:

- the profile-labelled digest of the semantically validated expanded authoring
  object;
- the selected instantiation profile, when one was selected;
- root parameter bindings, each with a segment-valued identity, origin
  (`provided` or `default`), and scalar JSON value;
- resolved imports in declared preorder, with namespace segments, requested
  selector, resolved module identity, checkout-independent source identity,
  content/manifest/export digests when applicable, signer id when applicable,
  and module-local bindings;
- the narrow capability constraints needed after substitution for
  `nodes.<id>.os` and `infrastructure.<id>.count`, addressed by RFC 6901 JSON
  Pointer and qualified parameter identity; and
- portable explicitness records needed to preserve SEM-218 realization meaning
  across serialization.

The provenance records are closed and immutable value objects in the reference
API. Binding values are limited to the SDL variable domain: JSON string,
integer, finite number, or boolean. Equality follows JSON semantics:
booleans are distinct from numbers, while numerically equal JSON numbers are
equal. Every capability parameter must resolve to exactly one root or imported
binding, its selected value must belong to the retained domain, and its pointer
must resolve to the same concrete field value. Explicitness parameter
identities must likewise resolve.

Resolved source identities never contain absolute host/cache paths or registry
credentials. The artifact does not retain trust-policy contents, headers,
credentials, cache locations, raw signatures, or source documents. Signer id is
an attribution fact from an already completed trust check, not a signature.

The compiler lowers each portable capability fact to one typed
`CompiledCapabilityConstraint` addressed to a compiled resource. The planner
does not reconstruct variable declarations or coordinate a variable-spec map
with a second field-reference map.

`instantiation_provenance` is artifact metadata, not a backend-realizable SDL
dimension. Realization-envelope membership projects fields annotated
`x-aces-realization-dimension: false` out of closed-world child enumeration.
The field remains required, validated, and included in snapshot identity; the
projection only prevents a backend capability envelope from claiming that it
must realize the derivation record itself.

This evidence provides a replay recipe and verification anchors. It does not
make a replay self-contained: source availability, the referenced module bytes,
and an independently selected trust policy are still required to repeat import
resolution. A provenance record is a claim carried by an artifact, not proof
that a named process actually ran.

### 4. Separate authored identity from instantiated snapshot identity

`aces-sdl-semantic/v1` continues to identify the validated expanded authoring
meaning. Its envelope and bytes are not redefined by this decision. The legacy
`module_variable_specs` and `module_node_variable_refs` members in that profile
remain compatibility projections derived from typed expansion evidence; they
are not live instantiated fields.

`aces-sdl-instantiated-snapshot/v1` is a separate envelope containing an
explicit profile label and exactly one admitted `InstantiatedScenario`. It is
serialized with RFC 8785 JCS and digested with SHA-256. A provenance change
therefore changes the snapshot digest even if the concrete scenario sections
are unchanged.

The snapshot is an identity for bytes and meaning under this profile. It is not
a claim of behavioral equivalence between scenarios, apparatuses, participants,
or runs. In particular, digest equality is not Park-Milner bisimilarity. Any
future behavioral-equivalence claim must define the labelled transition system,
observable actions, hidden actions, and bisimulation relation it uses.

### 5. State the schema and semantic boundaries separately

The Draft 2020-12 schemas enforce closed object shapes, required profile and
provenance members, identifier grammars, scalar constraints, and absence of
`${name}` in any instantiated string. Model validation additionally enforces
provenance collection invariants. Semantic admission enforces cross-reference,
graph, and pointer-to-concrete-value relations that JSON Schema does not express.

Therefore:

```text
admitted(x) = schema_valid(x)
              and provenance_consistent(x)
              and semantic_valid(x)
```

Schema validity alone is necessary but not sufficient for compiler admission.
Documentation and diagnostics must not collapse these layers into a claim that
the JSON Schema proves all SDL semantics.

### 6. Keep sensitive values off secondary response surfaces

Parameter values necessarily appear where substitution places them and in the
replay binding record. Tools must not duplicate them into summaries,
diagnostics, logs, or operation metadata. Binding failures report bounded
locations and error classes without rendering supplied values or allowed-value
domains. MCP authoring/operation responses report binding and import counts,
not a second raw parameter map.

## Lineage And Limits

### Post-materialization description amendment (#1241)

`MaterializedScenario` is accepted by the ordinary bounded SDL parser and
semantic validator, including qualified source identities. Its shared compiler
and planner produce inspection-only plans. No implicit transition turns it into
executable author intent. Required materialization provenance binds the source,
producer/configuration, plan, operation and predecessor; exact member differences
and instance bindings describe additions and changes without forging source
instantiation history. `raes-sdl-materialized/v1` is its separate canonical
profile. The original realization-authority and prepared-membership gates remain
binding; disclosure cannot excuse a violation.

Negotiated successful materialization includes even no-additions descriptions.
Runtime admission preserves a typed result and protected immutable SDL bytes in
the existing run archive. The distinct `materialization-attestation` reference
never replaces the run's original `scenario_snapshot_ref`. File publication
precedes durable references; a failure retains cleanup inventory and does not
authorize replay. This is safe operational provenance, not an implicit request
for observation, evidence capture or participant access. The normative details
are in [materialization-attestation.md](../../../specs/sdl/materialization-attestation.md).

The separation of operations by object state is informed by Strom and Yemini's
[typestate](https://doi.org/10.1109/TSE.1986.6312929) work. ACES adopts the
design lesson of distinct state-indexed operation surfaces, not its compile-time
guarantee: Python/Pydantic validation here is dynamic, and the transition types
are not a dependent-type proof.

The provenance vocabulary is conceptually aligned with the W3C
[PROV Data Model](https://www.w3.org/TR/prov-dm/): scenarios are entity-like
artifacts, composition/instantiation are activity-like transformations, and
bindings/digests describe derivation context. ACES does not serialize PROV-N,
PROV-XML, or PROV-O, does not carry the complete PROV relation set, and makes no
W3C PROV conformance claim.

Closed exchange shapes use
[JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12/json-schema-core).
Deterministic snapshot bytes use the Informational
[RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html).
Neither source defines SDL semantics, proves provenance truth, or establishes
behavioral equivalence.

The distinction from behavioral equivalence follows the original line of work
from Park's
[Concurrency and Automata on Infinite Sequences](https://wrap.warwick.ac.uk/47224/).
This ADR deliberately establishes artifact phase identity only; operational and
multi-agent observational semantics remain separate work.

## Consequences

Positive:

- a schema-valid instantiated payload cannot retain authoring machinery or a
  substitution token;
- serialization no longer drops compiler-relevant capability or explicitness
  meaning;
- module resolution evidence is checkout-independent and ordered;
- direct construction cannot bypass compiler semantic admission; and
- authored and instantiated canonical identities cannot be confused.

Costs and compatibility:

- `instantiated-scenario-v1` is tightened while it remains draft; payloads
  created under the former permissive shape must be reinstantiated;
- every instantiated artifact is larger because derivation evidence is
  explicit;
- semantic validation runs at public instantiation and direct-artifact
  admission, including compiler and snapshot boundaries; and
- consumers of former Python private fields must migrate to typed provenance.

## Verification

The FM2 evidence consists of:

- `specs/formal/sdl-phases/README.md`;
- `contracts/schemas/sdl/instantiated-scenario-v1.json` and
  `instantiated-scenario-snapshot-v1.json`;
- cross-phase valid/invalid fixtures under `contracts/fixtures/sdl/`;
- `implementations/python/packages/aces_sdl/phase_contracts.py`;
- `implementations/python/tests/test_sdl_phase_contracts.py`;
- `implementations/python/tests/test_instantiated_scenario_schema.py`; and
- compiler/MCP regression tests proving serialized equivalence and bounded
  disclosure.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-07-12 | #724 | Clarified that required instantiation provenance remains validated artifact identity metadata but is excluded from realization-envelope child-dimension enumeration. |
| 2026-09-14 | #1241 | Added the closed descriptive materialized SDL phase, execution-bound provenance and distinct protected archival identity without changing original realization authority. |
