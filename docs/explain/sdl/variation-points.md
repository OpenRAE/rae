# Scenario-Family Variation Points

Use `variation_points` when one SDL document should describe a finite family of
valid scenarios. A point declares what may vary and where; a later experiment
declares how trials choose among those possibilities.

The normative contract is the
{download}`bounded variation-point specification <../../../specs/sdl/variation-points.md>`.

## A small family

```yaml
name: payload-family

variables:
  payload_path:
    type: string
    allowed_values: [/opt/payload-a, /opt/payload-b]

nodes:
  primary: {type: compute, resources: {ram: 1 GiB, cpu: 1}}
  secondary: {type: compute, resources: {ram: 1 GiB, cpu: 1}}

content:
  payload: {type: file, target: primary, path: '${payload_path}'}

variation_points:
  payload-path:
    kind: parameter
    target: {kind: variable, variable: payload_path}
    domain: {kind: enum, values: [/opt/payload-a, /opt/payload-b]}

  payload-host:
    kind: alternative
    target: {kind: reference, owner: payload, slot: content.target}
    alternatives:
      primary-host: {reference: primary}
      secondary-host: {reference: secondary}
```

This document declares two independent points. It does not select a path or
host, and the selected values do not become declaration identifiers.

## Choosing a kind

- `parameter` varies an existing typed SDL variable over an exact, enum,
  Boolean, or bounded numeric domain.
- `governed-reference` varies one typed reference over a finite set under a
  named authority.
- `alternative` chooses exactly one named referenced semantic object.
- `subset` chooses a cardinality-bounded set of named members.
- `order` orders stable member ids subject to precedence and fixed-position
  constraints.
- `logical-timing` varies an admitted logical timing field with an explicit
  unit.

Targets use a closed `slot` vocabulary. They are not JSON pointers or patches;
the slot determines both the owner type and the permitted candidate type.

## Constraints

Alternative, subset, and order members can declare `requires` and `excludes`
relations:

```yaml
requires:
  - point: deployment-mode
    members: [isolated]
```

Relations are checked after module composition, so imported point references
are namespaced consistently. Subset bounds, order precedence, and fixed
positions are validated before trial planning. Admission also proves that the
whole constraint set has a satisfying selection and that every named member can
participate in one. Empty integer intervals and impossible combinations fail at
authoring time rather than surfacing during trial allocation.

The reference validator bounds its satisfiability search to 100,000 states and
fails closed when that resource budget is exhausted.

Member admission checks that each member yields an admissible scenario. It runs
only when the earlier semantic checks pass. A scenario with earlier errors
reports those errors first. Its members are checked after the author fixes
them.

## Phase behavior

`variation_points` exists only in authored and expanded SDL. Module composition
qualifies point ids, target refs, relation refs, and parameter-owned variables.
An empty registry preserves the canonical bytes and digest of an ordinary SDL
document.

Selection and trial allocation are intentionally outside this feature. Until
the recorded-selection transition is available, trying to instantiate a
non-empty family fails with an unresolved-variation diagnostic. That prevents
variable defaults or declaration order from becoming accidental selection
policy.
