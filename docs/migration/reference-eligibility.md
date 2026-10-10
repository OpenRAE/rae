# Migrating to purpose-specific reference eligibility

Issue #1339 replaces the exclusion-based `targetable` rule with an explicit
eligibility decision for each reference purpose. The
[reference-purpose catalog](../../specs/sdl/references.md#7-reference-purposes-and-eligibility)
is the current contract. This is a breaking authoring change for the fields in
the first table; every other reference field accepts the same declarations as
before.

## Fields that narrow

| Field | No longer accepted | Rewrite |
| --- | --- | --- |
| `objectives.*.targets[]` and `objectives.targets` variation candidates | `conditions`, `injects`, `events`, `scripts`, `stories`, `action_contracts`, `observation_boundaries`, `behavior_specifications`, participant inject deliveries, `variation_points` | Name the proposition that a condition probes, or the participant, organization, resource, or relationship the objective concerns. Use `actions` for action constraints and `window` for narrative scope. |
| `action_contracts.*.interactions.*.target` | `propositions`, `assertions`, `conditions`, narrative entries, behavior surfaces, `variation_points` | Name the participant, organization, resource, or relationship the action acts on. A truth claim belongs in a proposition or objective, not an action target. |
| `action_contracts.*.effects.*.target_refs[]`, which were not checked before | an entry that names any declaration other than a participant, organization, resource, or relationship: the kinds in the row above, plus `objectives`, `workflows`, `variables`, `evidence_requirements`, `time_domains`, `clocks`, `time_domain_mappings`, `time_progression_policies`, `temporal_constraints`, tool affordances, and variation alternatives and members | Name the participant, organization, resource, or relationship the effect changes, or keep a token that names no declaration. |
| `action_contracts.*.interactions.*.shared_state_refs[]` | the kinds refused as interaction targets, plus `agents` and `entities` | Name the resource or relationship whose state the interacting actions read or write. |
| `behavior_specifications.*.authority_scope_refs[]`, mixed-control state `scope_refs[]`, and inject-delivery `control_authority_scope_refs[]` | `propositions`, `assertions`, `conditions`, narrative entries, `variation_points` | Name the participant, organization, resource, relationship, or behavior surface the authority covers. |

An effect `target_refs[]` entry that names no declaration keeps working. It is
observation-boundary information, and recorded action results check it against
the participant's observation boundary as before. An entry that names a
referenceable declaration, by bare name or qualified address, is now checked:
like the other fields it must name exactly one targetable declaration, and that
declaration must be an action target. Every indexed kind is referenceable
except the scenario identity, node roles, workflow steps, and
`outcome_interpretation_rules` entries. A free-form token that equals a declared
bare name is therefore refused unless it names an action target. For example,
`port` beside a variable named `port` fails with `... does not reference any
defined element eligible as an action target; it names variables.port`. Rename
the token or name the intended action target.

Narrowing only refuses references; it never makes a bare name resolve that did
not resolve before. A bare reference in these fields resolves among every
targetable declaration, and then the single match must be eligible. A bare
name that a refused declaration shares, such as a node and a condition that
are both named `web`, stays ambiguous and needs the qualified form
(`nodes.web`). Participant relationship endpoints follow the same rule: a bare
name that also names an organization or resource is ambiguous, so write
`agents.<name>`.

A refused reference fails semantic validation as dangling. In the fields in
the table, the diagnostic names the purpose and the declaration that the
reference does name, for example `Action contract 'probe' interaction[0]
target 'assertions.done' does not reference any defined element eligible as an
action target; it names assertions.done`. An inject delivery's
`control_authority_scope_refs[]` must equal its target controller state's
`scope_refs[]`, so the state's diagnostic refuses it, or the delivery is
reported as disagreeing with the state. Relationship endpoints, proposition
subjects, evidence refs, authority anchors, and the general declared and
targetable fields keep their wording (`any defined element` or `any defined
targetable element`) and gain the same `; it names` detail when the reference
names a declaration. An ambiguous bare name lists the eligible choices first
and then the declarations the purpose refuses, for example `'web' is
ambiguous; use one of: nodes.web; not eligible as an authority scope:
conditions.web`. Participant endpoints and operating scopes keep their
diagnostics. Instantiation reports the same diagnostic for a substituted
variable value, and composition reports it under the import namespace.

There is no compatibility reader. Rewrite a refused reference by hand with the
table above, because only the author knows which declaration was meant.

## Inventory before narrowing

The inventory ran on 2026-10-10 and compared `origin/dev` at 35122105 with
this change. It covered every tracked YAML file outside `.github` that loads as
a mapping with a top-level `name` key, on each repository's integration branch:

| Repository | Commit | Documents | Accepted |
| --- | --- | --- | --- |
| rae: examples, contract fixtures, documentation, specifications, and test data | `dev` 35122105 | 74 | 45 |
| env-packs | `dev` 9ce449d | 54 | 49 |
| lilrae | `dev` a5833df9 | 12 | 6 |
| adapters | `dev` 0272949 | 10 | 0 |
| reference-packs | `main` 445c3ca, its only branch | 0 | 0 |
| hub | `dev` 4f15773 | 0 | 0 |

Full validation outcomes, error text included, are identical before and after
the change for all 150 documents, both as authored and with legacy spellings
accepted. As authored, 100 are accepted and 50 are rejected for unchanged
reasons. The rejected files include intentionally invalid fixtures, pack
manifests and Compose files that are not SDL, and documents that need a
migration first, such as all seven adapters SDL files.

The 114 documents that parse structurally with legacy spellings accepted name
these declaration kinds:

| Field | Declaration kinds named |
| --- | --- |
| `objectives.*.targets[]` | content, named infrastructure ACLs, nodes, relationships, node services |
| interaction `target` and `shared_state_refs[]` | node services |
| effect `target_refs[]` | content, named infrastructure ACLs, nodes, relationships, node services |
| `authority_scope_refs[]` | content, nodes, node services |
| mixed-control and delivery scopes | nodes |
| proposition `subjects[]` | content, nodes, runtime-inventory records |
| evidence `source_refs[]` and `scope_refs[]` | action contracts, agents, content, organizations, nodes, participant inject deliveries, runtime-inventory records, node services |
| generic relationship endpoints | accounts, deployment tenants, features, identity domains, facades, and forests, nodes, runtime-inventory records, node services |
| participant relationship endpoints | agents, and one organization in a fixture that is invalid on purpose |

No accepted reference narrows. The organization endpoint is
`contracts/fixtures/sdl/participant-relationships-v1/invalid/entity-endpoint.yaml`,
which was already rejected.

## Editor behavior

- Completion contexts name the purpose token, such as
  `reference:eligible:objective_subject`. The relationship subtype selects
  `reference:eligible:participant_endpoint`, which offers only agents.
- Interaction targets, shared-state refs, effect target refs, agent authority
  anchors, and agent operating scope now have completions. Temporal-constraint
  subjects complete every declared reference. Participant relationship
  `scope_refs` complete only the operating scopes that both endpoints hold, and
  `authority_basis_refs` only the source's authority anchors. An endpoint that
  does not resolve to one participant, or whose own list is parameterized, does
  not restrict them. Validation also requires a selected
  `control_specification_ref` to cover each scope; completion does not apply
  that bound.
- A variation point's `target.owner` completes and navigates in its target
  slot's owner section, and a candidate's `reference` or governed
  `domain.allowed_refs` entry in the slot's candidate section or purpose, as
  validation resolves them. An `objectives.targets` point is offered only
  objectives as owners and objective subjects as candidates.
- Completion offers one unambiguous spelling per eligible declaration, and
  qualifies a bare name that validation would find ambiguous, including one
  shared with a refused declaration. Documents that do not validate yet use the
  same purposes; infrastructure entries are offered only in qualified form
  because they have no bare alias. Operating-scope fields, agent
  `operating_scope` and participant-relationship `scope_refs`, are the
  exception: their aliases depend on node types, so they complete and navigate
  only in a document that validates structurally.
- Navigation resolves each reference with its field's resolver, as validation
  does, and reports an occurrence of a declaration only when the value resolves
  to exactly that declaration. An ambiguous or refused value is an occurrence of
  no declaration; search for its bare name to find it. Operating scopes resolve
  through their own aliases, including bare service names. Documents that do
  not validate yet resolve names among their top-level entries, except in
  operating-scope fields: `dev` reported a participant-relationship
  `scope_refs` value in such a document as an occurrence, and this change
  reports none.

## Unchanged

Generic relationship endpoints, proposition subjects, evidence source, scope,
channel, trigger, and boundary refs, observation-demand component refs, agent
authority anchors, and agent operating scope accept the same declarations as
before. The inspection payload keeps `referenceable` and `targetable`;
`targetable` now reports the general target purpose. No published schema
changes. Historical evidence, compiled snapshots, and stored records are not
rewritten.

Eligibility only decides what a reference may name. Targeting a participant or
naming an organization as an objective subject grants neither participation,
authority, nor visibility.
