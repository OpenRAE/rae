# Catalog 3 — Variable and Instantiation Catalog

This catalog defines SDL variables — their types, defaults, and constraints —
the `${…}` substitution syntax, the instantiation algorithm, and what an
instantiated document is no longer permitted to contain. Variables and
instantiation are the SDL's parameterisation seam under
[ADR-001](../../docs/decisions/adrs/adr-001-scenario-description-language.md) and
[ADR-003](../../docs/decisions/adrs/adr-003-workflows-targetable-subobjects-and-enum-variables.md).

## 1. Variable definitions

A `variables` entry ([sections.md](sections.md)) is keyed by a variable name and
defines a typed, optionally-constrained parameter:

| Field | Meaning |
|-------|---------|
| `type` | One of `string`, `integer`, `boolean`, `number`. **REQUIRED**. |
| `default` | The value used when no parameter is supplied. **OPTIONAL**. |
| `allowed_values` | A closed set of permitted values. **OPTIONAL**. |
| `required` | Whether a value must be supplied at instantiation when no default exists. Defaults to false. |
| `description` | Free text. **OPTIONAL**. |

Type conformance rules, enforced when the variable is defined:

1. If `default` is set, it **MUST** match `type`. `integer` excludes booleans;
   `number` admits integers and floats but excludes booleans; `boolean` is
   strictly boolean; `string` is strictly string.
2. Every member of `allowed_values` **MUST** match `type`.
3. If both `default` and `allowed_values` are set, `default` **MUST** be a member
   of `allowed_values`.

The variable **name** (the map key) **MUST** use the portable local-identifier
grammar `^[a-z0-9][a-z0-9_-]{0,63}$`
([document-model.md §6](document-model.md)).

## 2. Reference syntax

A variable is referenced by a `${name}` placeholder, where `name` matches the
variable-name grammar above. Two placeholder positions are distinguished:

1. **Full-value placeholder** — the entire field value is `${name}`. On
   instantiation it is replaced by the variable's **typed** value (an integer
   stays an integer, a boolean stays a boolean).
2. **Embedded token** — `${name}` appears inside a larger string (e.g.
   `host-${index}`). On instantiation each token is replaced by the **string**
   form of the variable's value and the surrounding text is preserved.

A placeholder **MUST NOT** appear in an identifier-defining map key
([document-model.md §6](document-model.md)); variables parameterise values, not
identities.

Module parameter names, import-parameter keys, and
`scenario-instantiation-request-v1.parameters` keys use the same grammar.
Parameter values retain their owning field types. For any declaration `d` and
two valid parameter environments `p1` and `p2`, canonical identity is invariant:
`address(d, p1) = address(d, p2)`.

Variables are **not** resolved at parse time. An authored document preserves
`${…}` placeholders structurally; resolution happens only at instantiation.
Authoring-time semantic validation checks every `${name}` token, whether it is a
full-value placeholder or embedded in a larger string, and fails if `name` is
not declared in `variables`.

## 3. Instantiation algorithm

Instantiation turns an authored (and, if applicable, expanded) document into a
concrete one, given a mapping of parameter values and an optional profile. It is
**fail-closed**: any of the following is a fatal instantiation error
([diagnostics.md](diagnostics.md)), and all such errors are reported together.

For each declared variable, a value is chosen in this order:

1. the supplied parameter value, if the variable's name is a supplied parameter;
2. otherwise the variable's `default`, if set;
3. otherwise, if the variable is `required`, a **missing-required-value error**;
4. otherwise the variable is left unbound (it has no value and no default and is
   not required).

Each chosen value is then checked:

5. its type **MUST** match the variable's `type`, else a **type-mismatch error**;
6. if `allowed_values` is set, the value **MUST** be a member, else an
   **allowed-values error**.

Across the whole parameter mapping:

7. a supplied parameter whose name is **not** a declared variable is an
   **undeclared-parameter error**. Instantiation does not silently ignore extra
   parameters.

Substitution then replaces placeholders throughout the document (§2). Finally:

8. any placeholder that remains unresolved after substitution — because its
   variable was left unbound (step 4) — is an **unresolved-placeholder error**.
   A concrete document **MUST NOT** carry surviving `${…}` placeholders.

The substituted document is re-validated structurally and **re-run through
semantic validation** ([references.md](references.md)); a reference that only
becomes dangling or ambiguous after substitution fails here.

## 4. Post-instantiation exclusions

An instantiated document is concrete. It **MUST NOT** contain:

1. unresolved `${…}` placeholders (§3 step 8); and
2. a `variables` member, even an empty one;
3. an `imports` member, even an empty one; or
4. a `module` member, even a null one; or
5. a `realization` member, even a null one.

This is the authoring → instantiated distinction: a value that exists only to
be substituted (a `${…}` reference) and the machinery that substitutes it (the
`variables` definitions) do not survive into the instantiated form. `module`
is packaging metadata, `imports` are composition instructions, and `realization`
is an authoring designation block. Verified resolution facts and normalized
realization-designation records survive under provenance instead.

Every `instantiated-scenario-v1` payload **MUST** carry a closed
`instantiation_provenance` object. Its members are:

| Member | Meaning |
|--------|---------|
| `authored_digest` | Required `raes-sdl-semantic/v2` / SHA-256 identity of the validated expanded authoring object. Profile, algorithm, and digest value are explicit. |
| `selected_profile` | Optional instantiation-profile selector. Absence means no named profile was selected; it does not imply a hidden default profile. |
| `bindings` | Root bindings in variable declaration order. Each has a one-segment parameter identity, `provided` or `default` origin, and selected scalar value. |
| `imports` | Verified resolved imports in declared preorder. Each carries namespace segments, requested and resolved identities, available digests, signer id, and module-local bindings. |
| `capability_constraints` | Finite domains retained only for concrete `nodes.<id>.os` and `infrastructure.<id>.count` fields, addressed by RFC 6901 pointer and qualified parameter identity. |
| `explicitness` | Portable SEM-218 model-path classifications whose parameter identities remain resolvable after variable definitions are removed. |
| `realization_designations` | Portable SEM-218 root/scoped posture records. Each carries a namespace, RFC 6901 field pointer, and `closed`, `open`, or `unspecified` posture after the authoring-only `realization` block is removed. |

A qualified imported binding identity is the import's `namespace` tuple
concatenated with its one-segment local parameter identity. Root and qualified
identities **MUST** be globally unique. Every capability or explicitness
parameter identity **MUST** resolve to one binding. A capability binding's value
**MUST** belong to its retained domain and equal the value at its concrete JSON
Pointer. JSON equality distinguishes booleans from numbers; numerically equal
JSON numbers compare equal. Duplicate domain values are forbidden under that
equality.

Import records preserve declared preorder and namespace segments, so nested
structure does not have to be recovered by splitting dotted display strings.
Requested/resolved source identities **MUST NOT** carry absolute host/cache
paths or registry credentials. Trust-policy contents, request headers, cache
locations, raw signatures, and source documents are excluded. A signer id and
digest are resolution evidence, not a replacement for a signature or an
independently chosen trust policy.

Realization designation identities are unique by namespace and field pointer.
They preserve the authored cascade across expansion and instantiation but do not
claim that downstream realization occurred or turn the authoring block into
executable scenario content.

The provenance supplies selected inputs and verification anchors for replay. It
does not make replay self-contained or prove that the described transformation
ran: repeated resolution still depends on source availability, source bytes,
and current trust policy. Tools **MUST NOT** duplicate binding values into
summaries, diagnostics, logs, or operation metadata merely because they are
present in the artifact.

The published JSON Schema enforces the closed phase shape, required provenance,
scalar syntax, and absence of substitution tokens. Cross-field provenance
relations and SDL references/graphs require model and semantic admission. Thus
schema validity is necessary but not sufficient for compiler admission.

## 5. Authoring vs. instantiated reference checks

Reference resolution treats the two forms differently
([references.md §3](references.md)):

- **Authored:** a field holding `${name}` is not resolved as a reference; only
  `name`'s declaration is required.
- **Instantiated:** the substituted concrete value is subject to the full
  reference rules.

This lets an author parameterise a reference (e.g. a node `os` or an
infrastructure `count`) and defer its validation to the point where the concrete
value is known.

## Extending the variable model

New variable types or constraint kinds are added by extending the variable
model and the published schema, adding the type/constraint to this catalog, and
updating the instantiation checks (§3) and tests. The four-step instantiation
contract — choose, type-check, constraint-check, substitute-and-revalidate —
is the stable seam; new constraints slot into the check phase.
