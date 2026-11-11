<!-- vale RAES.HeadingCase = NO -->
# Diagnostics — errors and advisories

This file documents the SDL diagnostic boundary: the stages at which a document
is checked, the fail-closed error semantics, and the distinction between a fatal
**error** and a non-fatal **advisory**. It states the normative criterion that
classifies a condition as an error or an advisory (§5); it does not introduce a
new diagnostic mechanism, and it does not reclassify any existing condition.

<!-- vale RAES.HeadingCase = YES -->

## 1. Diagnostic stages

An authored SDL document is checked at three transformation stages, in order.
Portable instantiated artifacts also have an admission gate. Each is
**fail-closed**:
a problem at a stage stops the document from advancing past that stage.

1. **Source / parse / structural.** `sdl-yaml/v1` decoding, operational bounds,
   structural shape, and typed construction: the root is a mapping, keys are
   strings, mapping entries remain unique, canonical structural fields are
   exact, values have the right shapes, and **no unknown key is present**
   ([document-model.md §§1, 4-5](document-model.md)). A problem is a parse error.
2. **Semantic validation.** Cross-section reference resolution
   ([references.md](references.md)), uniqueness, acyclicity, control-flow
   closure, and the runtime-family invariants
   ([runtime-inventory.md](runtime-inventory.md)). A semantic problem is a
   validation error.
3. **Instantiation.** Variable binding, type/constraint checks, undeclared
   parameters, and unresolved placeholders
   ([variables-and-instantiation.md §3](variables-and-instantiation.md)). A
   problem here is an instantiation error. Instantiation re-runs semantic
   validation on the concrete document, so semantic errors can also surface at
   this stage.
4. **Instantiated-artifact admission.** A direct or deserialized
   `instantiated-scenario-v1` payload is checked for its closed phase shape,
   required and internally consistent provenance, absence of substitution
   tokens, and ordinary semantic validity before compilation or canonical
   snapshot creation. Structural/provenance failures use the instantiation
   error surface; semantic failures use the validation error surface. Admission
   never trusts a caller-set private validation flag.

## 2. Collect-all semantics

The semantic-validation and instantiation stages **collect all errors in a pass**
and report them together, rather than failing at the first problem. An author
fixing a document sees the full set of errors a stage found, not one error at a
time. Parsing may stop at the first structural fault that prevents composition
of a YAML node graph. Once that graph is available, the mapping-key preflight
collects all exact duplicates, migration-merge conflicts, canonical-field
violations, and field-alias collisions before construction; none is hidden by
a last-write-wins mapping.

## 3. Errors are fatal

An **error** is fatal: it prevents the document from advancing past its stage. A
parse error prevents semantic validation; a semantic error prevents a document
from being treated as valid; an instantiation error prevents a concrete document
from being produced. There is no "warn and continue" for an error.

> *Implementation evidence (non-normative): the reference implementation reports
> these as `SDLParseError`, `SDLValidationError`, and `SDLInstantiationError`;
> the latter two carry the full collected error list. This specification does
> not define a new exception hierarchy or diagnostic envelope.*

## 4. Advisories are non-fatal

An **advisory** is a non-fatal observation about a document that is otherwise
valid. Advisories are carried alongside a successfully parsed/validated
document; they do not prevent it from advancing.

The boundary rule is symmetric and **MUST** be honoured:

1. An advisory **MUST NOT** be described or treated as an optional error. A tool
   **MUST NOT** unilaterally promote an advisory to a failure.
2. An error **MUST NOT** be demoted to an advisory to let an invalid document
   pass.

Existing advisory conditions, documented here by reference (not redefined):

- **Explicit source migration.** A migration operation may accept a recognized
  legacy field spelling or disjoint `<<` merge and emit a source-ranged warning.
  This does not reclassify the construct as valid canonical source: strict
  `sdl-yaml/v1` decoding still rejects it, and the migrated output must pass
  strict decoding. Ambiguity and unknown fields remain fatal in migration mode.

- **Compute node without resources.** A compute node declared without a
  `resources` block is **valid** SDL; it is flagged as an advisory because it may
  be undeployable unless a backend supplies defaults. It is not an error.
- **Name-based secret-classification heuristics.** A field whose *name* suggests
  it carries a secret, but which is not explicitly classified
  `redacted`/`operator_secret`, may raise an advisory. The heuristic is advisory
  **only**: it never silently strips or rewrites a value, and an unflagged value
  is not, by the heuristic alone, an error
  ([ADR-057](../../docs/decisions/adrs/adr-057-runtime-secret-name-classifier-boundaries.md),
  [runtime-inventory.md §3](runtime-inventory.md)). Explicit redaction
  (`redacted`/`operator_secret` omitting the raw value) is the **error-enforced**
  rule; the name heuristic is the advisory complement.

> *Implementation evidence (non-normative): advisories are surfaced on the parsed
> scenario's advisory list and the language-service diagnostics, separately from
> the error channel.*

## 5. Classification criterion

This section states the normative rule that decides whether a condition is an
**error** or an **advisory**. It resolves the classification deferred by review
**IMP-3**: the boundary is single-sourced here, and the classification of an
individual condition follows from this criterion rather than from each pass's
implementation.

The criterion is **meaning preservation**:

1. A condition is an **error** if and only if it affects the *meaning* of the SDL
   document — whether the document denotes a well-defined scenario at all. The
   meaning-affecting categories are: structural shape and closure (the §1 stage-1
   checks, including unknown-key rejection); cross-section reference resolution
   ([references.md](references.md)); identifier uniqueness; reference ambiguity;
   dependency and control-flow acyclicity; control-flow reachability,
   convergence, and "known-before-evaluation" visibility; required-profile guards
   on discriminated runtime spines ([runtime-inventory.md](runtime-inventory.md));
   variable binding, type, and constraint checks at instantiation
   ([variables-and-instantiation.md §3](variables-and-instantiation.md)); and
   explicit-redaction enforcement ([runtime-inventory.md §3](runtime-inventory.md)).
   A document that violates one of these has no single well-defined meaning, so
   the stage **MUST** fail closed (§3).
2. A condition is an **advisory** if and only if the document still has a single
   well-defined meaning and the condition reports a *deployability* or *quality*
   heuristic that does not change what the scenario means — for example, a
   construct a backend may be unable to realise without defaults, or a non-binding
   observation an author may wish to review. Advisories are non-fatal (§4).

**Borderline rule.** SDL diagnostics are fail-closed.
When a condition's classification is unclear, the default is **error**.
An advisory is permitted **only** for a clearly identified deployability or quality heuristic that leaves SDL meaning intact.
A violation that could leave the document's meaning undefined is an error.
It is also an error if two conforming tools could disagree about document validity.

This rule governs the classification of a *new* condition.
Section 4 forbids severity changes through relabeling of an *already-classified* condition.

The existing conditions in §4 satisfy this criterion.
"Compute node without resources" and the name-based secret heuristic are deployability/quality heuristics.
They leave meaning intact and are advisories.
Reference resolution, uniqueness, acyclicity, ambiguity, required-profile guards, and explicit redaction affect meaning.
They are errors.

A change to a condition's error/advisory channel **MUST** apply this criterion.
A new diagnostic category **MUST** also apply it.
The change **MUST** appear here, in the published schemas, and in the reference implementation together.
This keeps one source for the boundary.

## 6. Mapping-key diagnostics

Exact duplicate keys, conflicting effective keys introduced by `<<`, and
distinct structural field spellings that normalise to one field use the stable
diagnostic code `sdl.mapping_key_conflict`. They are fatal at the `parse` stage
and **MUST** be raised before typed SDL model construction sees the mapping.

An explicitly non-string or complex mapping key uses
`sdl.mapping_key_type`. A cyclic YAML alias graph uses `sdl.alias_cycle`. These
conditions are likewise fatal at the `parse` stage and carry the canonical
target path and primary source range; they do not have a second authored-key
range when no competing declaration exists.

Each diagnostic **MUST** carry:

1. the canonical target path as an RFC 6901 JSON Pointer, with schema field
   segments canonicalised and user-defined/native-map segments preserved and
   escaped;
2. both authored key spellings (the spellings are identical for an exact
   duplicate); and
3. the one-based line and column range of both key tokens. The later/conflicting
   key is the primary range and the earlier key is a related range. When the
   conflict is contributed through a YAML merge, the ranges identify the
   original key declarations and the canonical path identifies the effective
   target mapping.

Implementations **MUST** expose this failure through the existing parse-error
channel rather than a parallel diagnostic hierarchy. Public structured adapters
(including language-service and MCP responses) preserve the code, stage,
canonical path, and both ranges. Plain-text CLI/library rendering may format the
same fields as prose but must not replace them with raw YAML values or silently
downgrade the error to a generic model-validation failure.

> *Implementation evidence (non-normative): the reference implementation's
> parse-error class for this channel is `SDLParseError`.*

## 7. Source-profile and migration diagnostics

Source diagnostics use the same structured envelope as mapping-key diagnostics.
Each carries a stable code, `parse` stage, severity, message, RFC 6901 path,
one-based half-open source range, and source identity when file-backed. A
diagnostic never includes the mapped value, whole source document, parameter
map, secret, or traceback.

| Code | Meaning | Strict severity | Migration severity |
|------|---------|-----------------|--------------------|
| `sdl.utf8` | Input cannot be represented as valid UTF-8 | error | error |
| `sdl.source_format` | Unsupported source-profile identifier | error | error |
| `sdl.migration_policy` | Unknown migration-policy identifier | error | error |
| `sdl.parse` | YAML syntax, stream, or composition failure | error | error |
| `sdl.directive` | YAML directive is present | error | error |
| `sdl.explicit_tag` | Explicit YAML tag is present | error | error |
| `sdl.source_limit` | A `sdl-yaml/v1` resource bound is exceeded | error | error |
| `sdl.non_json_value` | Constructed value is outside the SDL JSON domain | error | error |
| `sdl.mapping_key_type` | Mapping key does not construct as a string | error | error |
| `sdl.mapping_key_conflict` | Duplicate or canonicalized collision | error | error |
| `sdl.alias_cycle` | Alias graph is cyclic | error | error |
| `sdl.identifier.invalid` | Declaration identity violates the portable local-id contract | error | error |
| `sdl.model.invalid` | Typed model field violates its declared structural contract | error | error |
| `sdl.noncanonical_field` | Recognized legacy structural-field spelling | error | warning |
| `sdl.noncanonical_merge` | YAML 1.1 `<<` migration syntax | error | warning |
| `sdl.legacy_node_type_vm` | Historical `type: vm`, preserving exact virtual-machine intent | error | warning |

For `sdl.noncanonical_field`, `authored_keys` contains the authored and
canonical spellings, and the path points to the canonical field. For
`sdl.noncanonical_merge`, the path points to the effective mapping. Warnings
are retained on the successfully migrated scenario and by formatting, MCP, and
CLI adapters. Strict validation is the default at every ordinary parse ingress;
migration acceptance requires an explicit caller choice.

`sdl.legacy_node_type_vm` is not a case-folding alias for `compute`. A migration
MUST rewrite the resource kind to `compute` and add an exact
`compute-substrate = virtual-machine` realization constraint with migration
provenance. It MUST reject a colliding authored substrate constraint. The
canonical migrated output contains neither `type: vm` nor an implicit mechanism
choice. Historical instantiated `v1` artifacts use the same semantics-preserving
upgrade at their versioned deserialization boundary.

An identifier diagnostic points to the exact defining key or scalar-id token
and carries that token's source range. Its bounded message states the grammar
without echoing the invalid spelling, adjacent value, document fragment,
parameter map, or traceback. The accepting migration profile does not demote or
rewrite an invalid identity; identifier migration requires an explicit atomic
rename of the declaration and all resolved references.

A typed-model diagnostic preserves the structural contract statement so an
author can determine why the field is invalid. Framework input rendering,
documentation URLs, input objects, tracebacks, and unbounded diagnostic text
are never exposed. The JSON Pointer and source range remain the authoritative
locator, and the bounded message **MUST NOT** exceed 512 characters.

> *Implementation evidence (non-normative): the reference parser removes
> Pydantic input rendering, documentation URLs, and framework prefixes; escapes
> control characters; and converts raw `ValidationError` instances into
> `sdl.model.invalid` diagnostics.*

## 8. Instantiation and artifact-admission disclosure

Instantiation and instantiated-artifact admission diagnostics identify a
bounded variable/field location and failure class. They **MUST NOT** render a
supplied parameter value, an `allowed_values` domain, a complete parameter map,
the concrete artifact, trust-policy contents, credentials, a raw framework input
dump, documentation URL, or traceback.

When structural reconstruction fails, the public diagnostic renders an RFC 6901
location plus a stable validation category through the instantiation-error
channel; a raw framework exception is not the public artifact-admission
contract. Semantic errors discovered after successful structural admission
remain on the semantic-error channel and retain the collect-all semantics of
the semantic pass.

> *Implementation evidence (non-normative): the reference implementation wraps
> structural failures in `SDLInstantiationError`; semantic failures remain
> `SDLValidationError`; and raw `ValidationError` instances are not exposed.*

Resolved values necessarily occur in the concrete fields they populate and in
the portable replay binding record. Authoring, MCP, compiler, and operation
summary surfaces **MUST NOT** echo a second raw binding map. Count-only summaries
are permitted.
