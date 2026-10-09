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
action target; it names assertions.done`. Relationship endpoints, proposition
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

The inventory ran on 2026-10-09 against `origin/dev` at 35122105. It covered
132 YAML documents with a top-level `name` key: the rae examples, contract
fixtures, documentation, specifications, and test data, plus the env-packs,
lilrae examples and test fixtures, reference-packs, adapters, and hub
repositories. Full validation outcomes are identical before and after the
change for all 132 documents: 94 are accepted and 38 are rejected for
unchanged reasons.

The 101 documents that parse structurally name these declaration kinds:

| Field | Declaration kinds named |
| --- | --- |
| `objectives.*.targets[]` | content, named infrastructure ACLs, nodes, relationships, node services |
| interaction `target` and `shared_state_refs[]` | node services |
| effect `target_refs[]` | content, named infrastructure ACLs, nodes, relationships, node services |
| `authority_scope_refs[]` | content, nodes, node services |
| mixed-control and delivery scopes | nodes |
| proposition `subjects[]` | content, nodes, runtime-inventory records |
| evidence `source_refs[]` and `scope_refs[]` | content, organizations, nodes, participant inject deliveries, runtime-inventory records |
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
  `authority_basis_refs` only the source's authority anchors, which is what
  their validator accepts. An endpoint that does not resolve to one
  participant, or whose own list is parameterized, does not restrict them.
- A variation candidate's `reference` completes and navigates in its target
  slot's section or purpose, so an `objectives.targets` candidate is offered
  objective subjects only.
- Completion offers one unambiguous spelling per eligible declaration, and
  qualifies a bare name that validation would find ambiguous, including one
  shared with a refused declaration. Documents that do not validate yet use the
  same purposes; infrastructure entries are offered only in qualified form
  because they have no bare alias.
- Navigation resolves each reference with its field's resolver, as validation
  does, and reports an occurrence of a declaration only when the value resolves
  to exactly that declaration. An ambiguous or refused value is an occurrence of
  no declaration; search for its bare name to find it. Operating scopes resolve
  through their own aliases, including bare service names. Documents that do
  not validate yet resolve names among their top-level entries.

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
