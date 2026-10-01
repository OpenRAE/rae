# SDL Phase Contracts

Classification: FM2, refinement/constraint semantics.

This note states the invariants for ADR-078. It is a lightweight formal model,
not a machine-checked proof and not an operational semantics for scenario
behavior.

## Domains

Let:

- `C` be the closed set of executable scenario-content fields;
- `A` be a normalized authoring object;
- `E` be an expanded authoring object;
- `I` be an instantiated scenario;
- `M` be a descriptive materialized scenario;
- `S` be an instantiated snapshot;
- `tokens(x)` be every `${portable-id}` token occurring in a string value of
  `x` (mapping keys are not substitution sites); and
- `fields(x)` be the object's top-level member names.

The phase shapes are:

```text
fields(A) subset-of C union {module, imports, realization, variables, variation_points}
fields(E) subset-of C union {variables, variation_points, expansion_provenance}
fields(I) subset-of C union {instantiation_provenance}
fields(M) subset-of C union {materialization_provenance}
fields(S) = {profile, scenario}
```

The subset relation accounts for optional members of a closed shape. No member
outside the relevant set is admitted. `name` is required in `A`, `E`, and `I`;
`instantiation_provenance` is additionally required in `I`; both `profile` and
`scenario` are required in `S`. `M` requires `name` and
`materialization_provenance`; it describes the world without granting execution
authority.

## Phase-specific member catalog

This table is the complete phase-specific member partition. `C` members are
excluded because they are shared executable content. The table is mechanically
checked against the closed phase models; `optional`, `required`, and `forbidden`
describe member admission, not whether an author chose to write an optional
value.

| Member | Normalized authoring | Expanded authoring | Instantiated | Materialized | Transfer disposition |
| --- | --- | --- | --- | --- | --- |
| `module` | optional | forbidden | forbidden | forbidden | Consumed by expansion; verified module facts are represented by `expansion_provenance.imports` when imports are resolved. |
| `imports` | optional | forbidden | forbidden | forbidden | Consumed by expansion; resolved imports move to `expansion_provenance.imports` and later `instantiation_provenance.imports`. |
| `realization` | optional | forbidden | forbidden | forbidden | Normalized designation records move to `expansion_provenance.realization_designations` and later `instantiation_provenance.realization_designations`. |
| `variables` | optional | optional | forbidden | forbidden | Selected values move to provenance bindings; variable definitions do not survive instantiation. |
| `variation_points` | optional | optional | forbidden | forbidden | Composition preserves and namespaces family declarations. Recorded-selection integration consumes them before instantiation; unresolved non-empty families fail closed. |
| `expansion_provenance` | forbidden | optional | forbidden | forbidden | Its portable import, constraint, explicitness, and realization records feed instantiation provenance. |
| `instantiation_provenance` | forbidden | forbidden | required | forbidden | Required portable derivation context for an instantiated artifact; materialization refers to the source digest, never copies its history onto a different world. |
| `materialization_provenance` | forbidden | forbidden | forbidden | required | Descriptive producer, execution, source and field/member lineage for the post-materialization world. |

## Transition Relations

The supported transitions are partial functions:

```text
normalize : Source -> A or error
expand    : A -> E or error
bind      : (A or E) x Parameters -> I or error
snapshot  : I -> S or error
describe  : (I, admitted execution, realized scope) -> M or error
```

`expand` may be the identity on executable content when no imports exist, but
the trusted expanded representation remains distinct. There is no supported
transition from `I` back to `A` or `E`, and no parser treats `S` as source.
The ordinary source parser also reads `M`, with no composition or binding.
Its shared compiler/planner output is inspection-only. Executing a description
requires an explicit new authoring derivation.

## Invariants

### P1: Phase exclusion

```text
{module, imports, realization} intersect fields(E) = empty
{module, imports, realization, variables, variation_points} intersect fields(I) = empty
{module, imports, realization, variables, variation_points} intersect fields(S) = empty
```

The last line applies to snapshot-envelope members; the nested `scenario` must
itself satisfy the instantiated rule.

The authored `realization` block is therefore authoring machinery, not
executable content. Its normalized designation records survive under provenance
so downstream realization can resolve the scoped cascade without admitting the
source block into `E` or `I`.

### P2: Concreteness

```text
tokens(I) = empty
tokens(S) = empty
```

This includes provenance strings. Substitution is single-pass, but a selected
value that reintroduces a token is not an admitted concrete artifact.

### P3: Binding environment closure

For provenance `P`, define its qualified binding environment:

```text
B(P)[root_binding.parameter] = root_binding.value
B(P)[import.namespace ++ import_binding.parameter] = import_binding.value
```

Root binding identities have one segment. Import-local binding identities have
one segment. Import namespaces are non-empty segment tuples. Every resulting
key in `B(P)` is unique.

### P4: Capability evidence consistency

For each capability constraint `q` in `P`:

```text
q.parameter in domain(B(P))
B(P)[q.parameter] in-json q.allowed_values
resolve_json_pointer(I, q.field_pointer) =json B(P)[q.parameter]
```

`q.field_pointer` is exactly `/nodes/<qualified-id>/os` or
`/infrastructure/<qualified-id>/count`. `=json` distinguishes booleans from
numbers; numeric JSON values compare by numeric value. `in-json` uses the same
equality. Allowed domains contain no duplicate JSON values.

### P5: Explicitness evidence closure

For every explicitness record `r` and every parameter identity `p` in
`r.parameters`:

```text
p in domain(B(P))
```

Model paths are unique within one provenance object. This preserves SEM-218
classification across serialization without reconstructing variable
declarations.

### P6: Import evidence order and portability

Resolved import records occur in declared preorder: an import record precedes
the records for its nested imports, and sibling subtrees retain declaration
order. Namespace tuples recover nesting without parsing dotted display text.

Requested/resolved source identities contain no absolute host/cache path or
registry user information. Digest fields are empty only when the source class
does not produce that digest; otherwise they use `sha256:<64 lowercase hex>`.

### P7: Admission

```text
admitted(I) iff
  closed_shape(I)
  and tokens(I) = empty
  and provenance_consistent(I)
  and semantic_validator(I) succeeds
```

JSON Schema checks `closed_shape` and token/scalar syntax. Runtime model
validation checks provenance relations. Semantic validation checks the SDL
reference and graph rules. No one layer is described as proving all three.

### P8: Canonical snapshot identity

For admitted `I`:

```text
S(I) = {
  "profile": "raes-sdl-instantiated-snapshot/v2",
  "scenario": I
}

bytes(I)  = JCS(S(I))
digest(I) = "sha256:" ++ lowercase_hex(SHA256(bytes(I)))
```

Changing concrete content or provenance changes the snapshot input. Equality
of `digest(I)` is identity under this canonical profile, not behavioral
equivalence or bisimilarity.

## Evidence Mapping

Materialized admission additionally requires exact native-identity differences
from `I`, complete instance bindings and a match with the returned resource
inventory in the producer's operation domain. The original execution authority
gate remains independent and precedes attestation acceptance. Its canonical
identity is `SHA256(JCS({profile: "raes-sdl-materialized/v1", scenario: M}))`.
See [the materialization contract](../../sdl/materialization-attestation.md)
and `test_issue_1241_materialization_*.py` for source-binding, origin, archival
and restart evidence. A producer assertion does not prove physical-world truth.

- typed phase and provenance records:
  `implementations/python/packages/raes/scenario.py` and
  `phase_contracts.py`
- transition and admission functions:
  `implementations/python/packages/raes/instantiate.py`
- typed processor lowering:
  `implementations/python/packages/raes_processor/models/` and
  `implementations/python/packages/raes_processor/planner/`
- canonical snapshot:
  `implementations/python/packages/raes/canonical.py`
- external contracts:
  `contracts/schemas/sdl/instantiated-scenario-v1.json` and
  `instantiated-scenario-snapshot-v1.json`
- model/schema/cross-phase tests:
  `implementations/python/tests/test_sdl_phase_contracts.py` and
  `test_instantiated_scenario_schema.py`

The serialized round-trip tests are differential evidence: compilation of an
in-process artifact and its JSON-deserialized counterpart must agree, including
capability and explicitness semantics.
