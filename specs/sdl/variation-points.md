# Bounded scenario-family variation points

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
before selection. Public instantiation of an unresolved family MUST fail closed.
The public `select_scenario_family()` API applies complete recorded selections.
It MUST NOT use variable defaults or first members as implicit selections.

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
| `alternative` | reference or structural target | `alternatives` is a non-empty identifier-keyed map of members. Exactly one member is selected downstream. |
| `subset` | `{kind: collection, owner: <ref>, slot: <collection slot>}` | `members` is non-empty; `minimum` defaults to 0 and `maximum` defaults to the member count. |
| `order` | collection target | `members` is non-empty; `precedence` is an acyclic edge list and `fixed_positions` maps members to unique zero-based positions. |
| `logical-timing` | `{kind: logical-timing, owner: <ref>, slot: <timing slot>}` | a scalar `domain` plus the slot's required `unit`. |

## 3. Bounded scalar domains

The scalar domain algebra is shared with realization-envelope domains but has
no realization authority:

- `exact`: one Boolean, integer, number, or string in `value`.
- `enum`: one or more type-strict, unique scalar `values`.
- `boolean`: both Boolean values when `value` is absent, or one exact Boolean.
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
| `objectives.assigned_participant` | `objectives` | `agents` |
| `objectives.owner` | `objectives` | flattened `entities` |

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
| `objectives.targets` | `objectives` | eligible objective subjects ([reference purposes](references.md#7-reference-purposes-and-eligibility)) |
| `objectives.depends_on` | `objectives` | `objectives` |

### Structural slots

A structural target has `{kind: structural, owner: <owner ref>, slot: <slot>}`.
Only `alternative` points admit this target kind.
The slot prefix names the owner section.
The owner MUST resolve to exactly one declaration in that section.
Each member has the type required by its slot.
Existing reference alternatives retain their `reference` member form.

| Slot | Alternative member |
| --- | --- |
| `nodes.presence` | `{kind: node-presence, present: <Boolean>, inventory?: <collection selections>}` |
| `accounts.presence` | `{kind: declaration-presence, present: <Boolean>}` |
| `content.presence` | Declaration presence member |
| `persistent_volumes.presence` | Declaration presence member |
| `generated_artifacts.presence` | Declaration presence member |
| `relationships.presence` | Declaration presence member |
| `propositions.presence` | Declaration presence member |
| `assertions.presence` | Declaration presence member |
| `evidence_requirements.presence` | Declaration presence member |
| `persistent_volumes.consumers` | `{kind: resource-consumers, consumers: [{node: <node ref>, mount_destination: <path>}, ...]}` |
| `generated_artifacts.consumers` | Resource consumer member |
| `nodes.runtime.service_listeners` | `{kind: runtime-inventory, references: [<qualified member ref>, ...]}` |
| `nodes.runtime.applications` | Runtime inventory member |
| `nodes.runtime.database_services` | Runtime inventory member |
| `nodes.runtime.dns_services` | Runtime inventory member |
| `nodes.runtime.identity_authorities` | Runtime inventory member |
| `nodes.runtime.file_services` | Runtime inventory member |
| `nodes.runtime.mail_services` | Runtime inventory member |
| `nodes.runtime.network_sensors` | Runtime inventory member |
| `nodes.runtime.network_detection_engines` | Runtime inventory member |
| `nodes.runtime.security_monitoring_managers` | Runtime inventory member |
| `nodes.runtime.ssh_servers` | Runtime inventory member |
| `nodes.runtime.app_authorizations` | Runtime inventory member |
| `nodes.runtime.scheduled_jobs` | Runtime inventory member |
| `nodes.runtime.datastore_services` | Runtime inventory member |
| `nodes.runtime.platform_applications` | Runtime inventory member |
| `nodes.runtime.forwarding_agents` | Runtime inventory member |
| `nodes.runtime.orchestration_authorities` | Runtime inventory member |
| `nodes.runtime.network_detection_engines.rule_sources` | Runtime inventory member |

`present` MUST be a Boolean, without string or numeric coercion.
An absent node alternative MUST NOT contain inventory selections.
Absence removes the node and its same-key infrastructure entry.
It does not remove incoming references or other declarations.
Surviving references MUST resolve after all selections.

A present node alternative MAY contain an `inventory` map.
Each key is one runtime collection slot from the table.
Each value is a unique list of qualified references to existing records.
This form couples node presence and inventory membership in one choice.

Runtime references MUST identify top-level records on the target node in the target collection.
Nested children remain inside their owning record.
Member labels and list positions are not inventory identities.
Selections preserve record payloads, semantic identifiers, and source order.
An empty reference list selects no records in the collection.
Omission does not assert forbidden presence, closed inventory, or runtime discovery.
Unselected node fields and inventory collections remain unchanged.

The `nodes.runtime.network_detection_engines.rule_sources` slot selects child records.
Its owner MUST resolve to exactly one network detection engine, by its qualified runtime reference.
Its references MUST identify rule sources of that engine.
The selection replaces only the `rule_sources` list of that engine.

The runtime family registry supplies stable collection identities.
Only the explicit slot table grants variation write permission.
Registration alone does not grant that permission.
Packages, environment entries, filesystem entries, and other nested collections are outside these slots.

A declaration presence member selects the whole owner declaration.
An absent member removes that declaration only.
It does not remove incoming references or other declarations.
Authors couple dependent declarations to node absence with `requires` and `excludes` relations.

A resource consumer member lists the consumer rows that the owner resource keeps.
Each selector MUST identify one existing row by its node and mount destination.
The node reference follows the resource consumer rule.
Two selectors MUST NOT identify the same row.
Selections preserve row payloads and source order.
Unselected rows leave the resource.
An empty list selects no rows.
The owning resource validator decides if the selected rows are valid.

All writes resolve against the unchanged family.
Different values for the same canonical target MUST fail admission.
The canonical target is `<owner section>.<owner name>.<slot field>`.
The rule source target is the qualified engine reference, followed by `.rule_sources`.
Node absence conflicts with other writes to that node or its descendants.
Declaration absence conflicts with other writes to that declaration or its descendants.
Coupled and separate inventory writes MUST agree when they address the same collection.
A rule source write conflicts with an inventory write to the engine collection of the same node.
Conflict detection MUST NOT depend on point identifiers or traversal order.
Owned provenance follows retained records by stable identity after selection.
Removed records carry their owned provenance out of the selected scenario.
Surviving constraints remain authoritative at their new positions.

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

A reference alternative, subset, or order member contains a declared `reference`.
A structural alternative contains the typed content specified above.
All member forms admit an optional `description` and optional `requires` and `excludes` relations. Each
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

This example declares a family only.
An admitted experiment/trial artifact records selections before concrete scenario construction.

The following point selects a node and its declared scheduled jobs:

```yaml
variation_points:
  optional-host:
    kind: alternative
    target: {kind: structural, owner: worker, slot: nodes.presence}
    alternatives:
      absent: {kind: node-presence, present: false}
      baseline:
        kind: node-presence
        present: true
        inventory:
          nodes.runtime.scheduled_jobs:
            - nodes.worker.runtime.scheduled_jobs.baseline
```

The `worker` node and its `baseline` job must already exist in the family.
Selections remain outside the original family digest.
Every selected scenario must pass complete SDL semantic admission.

The following points remove a node with an account and a shared volume mount:

```yaml
variation_points:
  sync-host:
    kind: alternative
    target: {kind: structural, owner: sync, slot: nodes.presence}
    alternatives:
      absent:
        kind: node-presence
        present: false
        requires:
          - {point: sync-account, members: [absent]}
          - {point: shared-mounts, members: [without-sync]}
      present: {kind: node-presence, present: true}

  sync-account:
    kind: alternative
    target: {kind: structural, owner: sync-api, slot: accounts.presence}
    alternatives:
      absent: {kind: declaration-presence, present: false}
      present:
        kind: declaration-presence
        present: true
        requires: [{point: sync-host, members: [present]}]

  shared-mounts:
    kind: alternative
    target: {kind: structural, owner: rules, slot: persistent_volumes.consumers}
    alternatives:
      without-sync:
        kind: resource-consumers
        consumers: [{node: sensor, mount_destination: /var/lib/rules}]
      all:
        kind: resource-consumers
        consumers:
          - {node: sensor, mount_destination: /var/lib/rules}
          - {node: sync, mount_destination: /var/lib/rules}
        requires: [{point: sync-host, members: [present]}]
```
