# Bounded Scenario-Family Variation Points

Status: **normative**.

Requirements: SCE-002

Decisions: [ADR-084](../../docs/decisions/adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md)
and accepted [ADR-070](../../docs/decisions/adrs/adr-070-realization-envelope-domain-witness-algebra.md)

## 1. Scope and authority

The optional top-level `variation_points` map declares a finite, reusable SDL
scenario family. SDL owns each point's domain, typed target, and closed
cross-point constraints. It does not own experiment factors, enumeration,
sampling, allocation, seeds, random streams, backend feasibility, or runtime
facts.

The section is admitted in normalized and expanded authoring objects and is
forbidden in instantiated scenarios and snapshots. Composition MUST complete
before selection. Until the recorded-selection transition is available, public
instantiation of a non-empty family MUST fail closed; it MUST NOT silently use
variable defaults or first members as selections.

## 2. Common form

Each map key is a stable SDL identifier and each value is a closed object with
a `kind`, a typed `target`, kind-specific bounded data, and an optional
`description`. The kind set is exactly:

```text
parameter
governed-reference
alternative
subset
order
logical-timing
```

Unknown kinds and extra fields are invalid. Arbitrary document paths, patches,
callbacks, expressions, templates, external queries, and backend selectors are
not target or domain forms.

| Kind | Target | Bounded declaration |
| --- | --- | --- |
| `parameter` | `{kind: variable, variable: <variables ref>}` | `domain` is `exact`, `enum`, `boolean`, or `numeric-interval`. |
| `governed-reference` | `{kind: reference, owner: <ref>, slot: <reference slot>}` | `domain` is `{kind: governed-reference, authority, allowed_refs}` with at least one unique ref. |
| `alternative` | reference target | `alternatives` is a non-empty identifier-keyed map of members. Exactly one member is selected downstream. |
| `subset` | `{kind: collection, owner: <ref>, slot: <collection slot>}` | `members` is non-empty; `minimum` defaults to 0 and `maximum` defaults to the member count. |
| `order` | collection target | `members` is non-empty; `precedence` is an acyclic edge list and `fixed_positions` maps members to unique zero-based positions. |
| `logical-timing` | `{kind: logical-timing, owner: <ref>, slot: <timing slot>}` | a scalar `domain` plus the slot's required `unit`. |

## 3. Bounded scalar domains

The scalar domain algebra is shared with realization-envelope domains but has
no realization authority:

- `exact`: one Boolean, integer, number, or string in `value`;
- `enum`: one or more type-strict, unique scalar `values`;
- `boolean`: both Boolean values when `value` is absent, or one exact Boolean;
  and
- `numeric-interval`: a finite lower and upper bound, an `integer` or `number`
  numeric type, and explicit lower/upper closure flags.

Numeric intervals MUST have ordered bounds. An integer interval MUST have
integral endpoints and contain at least one integer after endpoint closure is
applied. A zero-width interval MUST be closed at both ends.

A parameter domain MUST match its variable type. When the variable has
`allowed_values`, the point domain MUST be a subset of those values. A
logical-timing domain MUST match the owning field's scalar type and unit.

## 4. Typed target slots

Targets name an owning declaration and a closed slot. The slot determines the
required owner kind and candidate kind; authors cannot widen either with data.

### Reference slots

| Slot | Owner | Candidate |
| --- | --- | --- |
| `conditions.proposition` | `conditions` | `propositions` |
| `content.target` | `content` | compute `nodes` |
| `accounts.node` | `accounts` | compute `nodes` |
| `accounts.domain_ref` | `accounts` | `identity_domains` |
| `identity_domains.authority_account_ref` | `identity_domains` | `accounts` |
| `objectives.agent` | `objectives` | `agents` |
| `objectives.entity` | `objectives` | flattened `entities` |

### Collection slots

| Slot | Owner | Candidate member |
| --- | --- | --- |
| `nodes.features` | `nodes` | `features` |
| `nodes.conditions` | `nodes` | `conditions` |
| `nodes.injects` | `nodes` | `injects` |
| `events.assertions` | `events` | precondition `assertions` |
| `events.injects` | `events` | `injects` |
| `stories.scripts` | `stories` | `scripts` |
| `agents.starting_accounts` | `agents` | `accounts` |
| `agents.starting_assertions` | `agents` | precondition `assertions` |
| `objectives.targets` | `objectives` | targetable declarations |
| `objectives.depends_on` | `objectives` | `objectives` |

### Logical-timing slots

| Slot | Scalar type | Required unit |
| --- | --- | --- |
| `conditions.interval` | integer | `seconds` |
| `scripts.start_time` | integer | `seconds` |
| `scripts.end_time` | integer | `seconds` |
| `scripts.speed` | number | `multiplier` |
| `stories.speed` | number | `multiplier` |

`logical-ticks` is reserved as a unit vocabulary value but no current target
slot admits it. Host time, scheduler time, queue position, and wall-clock time
are not logical-timing targets.

## 5. Structural members and constraints

An alternative, subset, or order member contains a declared `reference`, an
optional `description`, and optional `requires` and `excludes` relations. Each
relation names one variation point and a non-empty unique list of that point's
member identifiers.

Every member reference MUST resolve to the target slot's candidate kind. Every
relation point and member MUST exist after composition. The same point/member
pair MUST NOT be both required and excluded by one member.

Subset bounds MUST satisfy:

```text
0 <= minimum <= maximum <= member count
```

Order precedence edges MUST name distinct declared members, be unique, and form
an acyclic graph. Fixed-position keys MUST name declared members; positions
MUST be unique and within `[0, member count)`. The combined precedence and
fixed-position constraints MUST admit at least one complete ordering.

The complete set of alternative, subset, order, cardinality, `requires`, and
`excludes` constraints MUST admit at least one selection. Every declared
structural member MUST participate in at least one satisfying selection; a
member that can never be selected is not a valid domain member.

These local checks do not replace whole-scenario admission. Every downstream
selection remains subject to the owning SDL field validator and the complete
semantic validator.

## 6. Composition, identity, and safety

Composition namespaces variation-point identifiers before any selection.
Targets, candidate references, relation point references, and preserved
parameter variables are rewritten through the same export/private symbol
rules as their declarations. Structural member identifiers remain local to
their point.

An absent registry and an explicit empty registry have identical canonical SDL
bytes and digest. A non-empty registry is canonical authoring content, so its
domains and constraints participate in family identity. Selection policy and
selected values do not participate in that authoring identity.

Diagnostics MUST identify the failing point or member without rendering domain
candidate values. Raw credentials and secret values MUST NOT appear in domains,
member values, canonical identities, fixtures, logs, or diagnostics.

## 7. Example

```yaml
variables:
  payload_path:
    type: string
    allowed_values: [/opt/payload-a, /opt/payload-b]

variation_points:
  payload-path:
    kind: parameter
    target: {kind: variable, variable: payload_path}
    domain: {kind: enum, values: [/opt/payload-a, /opt/payload-b]}

  host-choice:
    kind: alternative
    target: {kind: reference, owner: payload, slot: content.target}
    alternatives:
      primary-host: {reference: primary}
      secondary-host: {reference: secondary}
```

This example declares a family only. It does not authorize SDL instantiation
until an admitted experiment/trial artifact records selections for both points.
