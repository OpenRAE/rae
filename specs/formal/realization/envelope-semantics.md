# Realization envelope semantics

This note defines the formal design boundary for issue #667. It extends the
SEM-218 realization model with a portable expression for a set of scenario
instances.

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY**
in this note are to be interpreted as described in RFC 2119.

## Scope

This note governs:

- envelope expressions authored in SDL or declared by a backend;
- scoped open/constrained/exact posture;
- closed-world semantics from field scope to scenario scope;
- instance membership;
- envelope subsumption;
- deterministic witness generation;
- negative conformance for closed envelopes;
- backend-manifest carriage constraints for schema evolution.

Out of scope:

- replacing `run_target_conformance(reference_scenario=...)`;
- adding implementation helpers, CLI commands, APIs, persistence, or runtime
  behavior;
- defining experiment-core run-set semantics;
- defining new SDL variable syntax beyond the existing variable catalog.

## Realization status

This spec is design authority. The relation helper, the envelope expression
contract model, fixtures, and property tests are implemented by issue #668:

- `raes_contracts.realization_envelope` carries the closed, versioned envelope
  expression (`realization-envelope/v1`) — the admitted-fragment domain kinds,
  scoped bindings, posture, closure, and witness policy of this note;
- `raes.realization_envelope` implements `member`, `subsumes`, `witness`, and
  `generate_negative_probes` as one deterministic engine over that contract.

Issue #100 publishes the schema carrier at
`contracts/schemas/realization-envelope/realization-envelope-v1.json`, packages governed
backend instances under `contracts/realization-envelopes/`, and carries an
immutable envelope/configuration identity through backend-manifest-v2,
provisioning-plan-v1, and runtime-snapshot-v1. Backend carriers embed this same
expression and add closed realization/observation disclosures; they do not
introduce a second set language.

The remaining downstream boundary is target-conformance integration:

- SEM-218 remains the active exact/constrained/open realization authority;
- `backend-manifest-v2.realization_support` remains the coarse capability floor,
  while the selected envelope is the configuration-bound value and disclosure
  authority;
- `run_target_conformance(reference_scenario=...)` remains the temporary #663
  bridge for fixed-topology and simulation backends.

## Canonical inputs

Implementations of this spec MUST build on these authority surfaces:

- SDL variables and instantiation:
  [`specs/sdl/variables-and-instantiation.md`](../../sdl/variables-and-instantiation.md).
- SEM-218 explicitness and realization:
  [`explicitness-and-realization.md`](explicitness-and-realization.md).
- Backend manifest declarations:
  `BackendManifest`, `BackendManifestV2Model`, `backend_manifest_payload()`,
  and `RealizationSupportDeclaration`.
- Contract authority:
  `ContractModel`, `schema_bundle()`,
  `contracts/schema-publication-manifest.json`, and generated schema checks.
- Conformance/runtime diagnostics:
  `run_target_conformance()`, `OperationStatus`, and `Diagnostic`.

## Terms

**Scenario instance.** A fully instantiated, structurally valid, semantically
valid SDL scenario with no unresolved variables.

**Envelope expression.** A versioned expression denoting a set of scenario
instances.

**Domain descriptor.** A typed value set for one variable or field. The initial
portable domain kinds are `exact`, `enum`, `boolean`, `numeric-interval`,
`governed-reference`, and `record`.

**Scope.** The semantic extent where a posture applies. Scopes are ordered from
most local to broadest:

1. field
2. node
3. topology
4. app
5. scenario

`topology` and `app` are sibling aggregate scopes under `scenario`; neither is
more specific than the other for a field outside its aggregate.

**Posture.**

- `open`: the value or child scope is left to realization at a point the SDL
  semantics designates as realizable.
- `constrained`: the value or child scope MUST satisfy a typed domain.
- `exact`: the value or child scope MUST equal a singleton domain.

**Closure.**

- `open-world`: unspecified realizable dimensions under the scope may still be
  admitted when the owning SDL semantics allows them.
- `closed-world`: unspecified realizable dimensions under the scope are outside
  the envelope.

Closure is orthogonal to posture. A constrained field can live under an
open-world node, and an exact node can live under a closed-world scenario.

## Envelope shape

An envelope expression consists of:

- `schema_version`: the envelope expression contract version;
- `id`: a stable local or published identifier;
- `scope`: the top-level scope the expression constrains;
- `domains`: named domain descriptors;
- `bindings`: scoped bindings from SDL paths or governed scope refs to domain
  descriptors and posture;
- `closure`: scoped open-world or closed-world overlays;
- optional `witness_policy`: deterministic default selection policy;
- optional `source_ref`, `contract_id`, and `digest` when the expression is
  referenced from another artifact.

The shape above is semantic, not yet a published JSON schema.

The relation operates on the **realization projection** of an admitted scenario,
not on every member of its exchange artifact. The projection excludes fields
annotated `x-raes-realization-dimension: false`. In
`instantiated-scenario-v1`, `instantiation_provenance` is such artifact metadata:
it remains mandatory for admission and participates in canonical snapshot
identity, but a backend neither chooses nor realizes it. Closed-world envelope
checks therefore MUST NOT treat that field as an unspecified realizable
dimension. This projection does not weaken provenance validation or remove the
field from the artifact.

## Required semantics

<!-- vale RAES.HeadingCase = NO -->
### R1 - envelopes denote sets

Every envelope expression denotes a set of scenario instances. A concrete
scenario instance `s` is a member of envelope `E` exactly when:

<!-- vale RAES.HeadingCase = YES -->

1. `s` is structurally and semantically valid under the ordinary SDL rules;
2. every effective binding in `E` is satisfied by the corresponding value or
   child scope in the realization projection of `s`;
3. every closed-world scope in `E` has no unspecified realizable dimension in
   the realization projection of `s`;
4. every governed reference in `E` resolves under the applicable concept or SDL
   authority.

Invalid SDL is never a member, even if it satisfies the envelope domains.

### R2 - Effective bindings use most-specific-wins

For a concrete SDL path, the effective binding is the most specific binding
whose scope contains that path. Implementations MUST parse the complete
canonical path; accepting only the tokenizable fragments of a malformed path is
not conforming. When bindings address the same path depth, semantic scope order
breaks the tie: field, node, topology/app, then scenario. Topology and app remain
sibling scopes.

If two bindings have equal specificity and incompatible domains or posture, the
envelope is invalid. If a more-specific binding widens a value that an enclosing
closed-world scope made exact or excluded, the envelope is invalid unless the
enclosing binding explicitly marks that child as overrideable.

That `overrideable` condition governs explicit envelope domain bindings. It
does not prohibit the separate SEM-218 lexical author-default cascade from
overriding inherited open/closed posture in either direction. In closure
resolution, an effective `open-world` overlay removes inherited
`closed-world` state at the same or a descendant path.

Most-specific-wins is therefore deterministic; it is not merge-order dependent.

### R3 - Domain membership is structural

Domain descriptors admit only mechanically checkable sets:

- `exact(v)`: values equal to `v`;
- `enum({v1, ... vn})`: values equal to one listed member;
- `boolean`: `true` or `false`, optionally restricted to an exact boolean;
- `numeric-interval(type, lower, upper, lower_closed, upper_closed)`: numbers
  of the declared numeric type inside the bounded interval;
- `governed-reference(authority, allowed_refs)`: references in a finite
  governed set;
- `record(fields, extra)`: product structure whose field domains must be
  satisfied and whose `extra` flag controls undeclared fields.

Portable envelopes MUST NOT use arbitrary Python predicates, backend callbacks,
external queries, recursion, unbounded regex or SMT fragments, non-linear
arithmetic, or quantification over unbounded collections.

### R4 - Subsumption is set inclusion

`subsumes(offered, requested)` is true exactly when every scenario instance in
`requested` is also in `offered`.

The relation is evaluated without enumerating all instances. In the admitted
fragment it reduces to:

- domain subset checks for each effective binding;
- record/product field subset checks;
- closed-scope key-set checks;
- governed-reference subset checks;
- compatibility of posture and closure overlays.

When a backend declares `offered` and an author requests `requested`,
conformance may proceed only if `subsumes(offered, requested)` is true.

### R5 - Witness generation is deterministic and validated

`witness(E, policy, seed)` returns one concrete scenario instance in `E`, or a
diagnostic proving no witness can be generated in the admitted fragment.

The default policy is deterministic:

- exact domains choose their value;
- enums choose the lexicographically first canonical value unless a seed policy
  selects another member;
- bounded numeric intervals choose the lower closed endpoint when available,
  otherwise the smallest representable value inside the interval under the
  declared numeric type;
- governed references choose the first canonical ref unless a seed policy
  selects another allowed ref;
- records generate all required fields and no extra fields when closed.

The generated witness MUST be parsed, instantiated if needed, and semantically
validated through the normal SDL pipeline. A witness is executable evidence for
one instance. It is not a proof of subsumption or backend honesty.

### R6 - Closed envelopes require negative conformance

When a backend declares a closed-world envelope, conformance MUST generate
negative probes for closed dimensions that can be varied without introducing
secrets or unsafe side effects.

A negative probe is a request that differs from a valid witness by one
out-of-envelope variation:

- an enum value outside the offered set but inside the governing vocabulary;
- a numeric value outside the offered interval but inside the governing type;
- an extra field or child under a closed record/scope;
- an omitted required exact field;
- a governed reference outside the offered ref set.

The backend MUST refuse the negative probe through the ordinary
`OperationStatus` / `Diagnostic` surface and MUST NOT mutate runtime state. A
backend that accepts or silently approximates the probe fails closed-envelope
conformance.

### R7 - Manifest carriage is expression identity plus digest

A backend manifest that carries envelope semantics MUST either embed a small
envelope expression or reference a published envelope artifact by:

- contract id;
- expression id;
- version;
- digest;
- optional human-readable summary.

Both carriage modes use the same expression contract. The manifest carrier MUST
render through `backend_manifest_payload()` and validate through the manifest
contract model once schema evolution lands.

Current `realization_support.constraints` strings are not the envelope carrier.
They may remain compatibility hints, but they do not define membership,
subsumption, witness generation, or closure.

### R8 - Diagnostics identify paths, not sensitive values

Envelope diagnostics MAY name:

- envelope ids and refs;
- SDL paths;
- domain kind;
- relation kind (`membership`, `subsumption`, `witness`, `negative-probe`);
- non-sensitive governed identifiers;
- digest and contract ids.

Diagnostics MUST NOT echo credentials, bearer tokens, private keys, process
argv, host paths, backend-native ids, raw backend object representations,
hidden truth, scoring state, or full tracebacks.

## Invariants

**I1 - One semantic language.** Authored scenario families and backend
realizability declarations are compared as envelope expressions in the same SDL
semantic model.

**I2 - Closed-world is scoped.** Closure applies only at declared scopes and
does not implicitly close unrelated sibling scopes.

**I3 - Silence is not universal realizability.** An omitted bound is open only
when the owning SDL semantics designates that point as realizable.

**I4 - Subsumption precedes execution.** A backend-declared offered envelope
must subsume the requested envelope before conformance executes a witness.

**I5 - Witnesses are validated.** Generated witnesses pass the ordinary SDL
structural and semantic validation pipeline before runtime use.

**I6 - Negative probes are refusal tests.** Closed-world declarations require at
least one generated refusal test for each safely variable closed dimension.

**I7 - Public artifacts are secret-free.** Envelopes, manifests, witnesses,
fixtures, diagnostics, and conformance reports carry ids, refs, digests, and
bounded summaries, not sensitive concrete values.

## Implementation mapping

This section names the intended future seams. It is not a claim that the code
exists today.

| Concern | Future owner | Existing incumbent |
| --- | --- | --- |
| Envelope contract DTO | `raes_contracts` | `ContractModel`, generated schema bundle |
| SDL envelope syntax and validation | `raes` | variables, instantiation, semantic validation |
| Relation helper | `raes` or shared semantics helper | SEM-218 explicitness helper pattern |
| Backend manifest carriage | `raes_backend_protocols` / `raes_contracts` | `BackendManifest`, `backend_manifest_payload()` |
| Planning admission | `raes_processor` | `realization_support_diagnostics()` |
| Target conformance witness and negative probes | `raes_conformance` | `run_target_conformance(reference_scenario=...)` |
| Runtime refusal evidence | `raes_runtime` / control plane | `OperationStatus`, `Diagnostic` |

## Non-goals

- No runtime behavior changes.
- No contract schema publication.
- No backend manifest v3 publication.
- No replacement of the #663 bridge in this issue.
- No solver dependency.
- No new manifest capability language.
- No experiment-core run-set semantics.

## References

- [ADR-070: Realization Envelope Semantics](../../../docs/decisions/adrs/adr-070-realization-envelope-semantics.md)
- [Realization-envelope prior art and design criteria](../../../docs/research/realization-envelope/prior-art-and-design-criteria.md)
- [Explicitness And Realization Semantics](explicitness-and-realization.md)
- [Variable and Instantiation Catalog](../../sdl/variables-and-instantiation.md)
