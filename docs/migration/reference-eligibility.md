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
registered declaration, by bare name or qualified address, is now checked:
like the other fields it must name exactly one targetable declaration, and that
declaration must be an action target. Every indexed kind is referenceable
except the scenario identity, node roles, workflow steps, and
`outcome_interpretation_rules` entries; naming these kinds as an effect target
is rejected too, including inside imported modules. A free-form token that equals a declared
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

## Typed relationship endpoints

Each relationship type and typed detail field now has an explicit endpoint
decision, listed in the
[subtype decision table](../../specs/sdl/references.md#7-reference-purposes-and-eligibility).
The ten endpoint purposes, such as `node_endpoint` for a `domain_controller_for`
source or `mail_service_endpoint` for a `mail_access` target, admit declaration
kinds rather than categories. An endpoint must satisfy the purpose of its type
and of every typed detail it carries.

Typed endpoints refuse nothing new. Each kind set equals what the subtype's own
check already accepted: the identity, topology, and tenancy checks are tested
for equality against the policy, and the `database_access` and `mail_access`
checks now read the policy's sets. A typed endpoint that names the wrong kind
gains the shared diagnostic next to the subtype's existing message, for example
`Relationship 'trust' source 'conditions.alive' does not reference any defined
element eligible as an identity forest endpoint; it names conditions.alive`. A
typed endpoint whose purposes no declaration satisfies, such as a
`domain_controller_for` source that also carries `database_access`, names each
purpose that its match fails.

Runtime child records are named by family inside the policy, so a `mail_access`
target admits a mail service listener and refuses a security-monitoring manager
listener. Published declaration kinds do not change: external-concept
`subject_kind`, transformation-report `declaration_kind`, and the inspection
payload report the same kinds as before, such as `runtime-listeners` for a mail
listener.

## Inventory before narrowing

The inventory ran on 2026-10-13 and compared `origin/dev` at a391904a with
this change, including the typed relationship endpoint purposes and their
conjunction. It covered every tracked YAML file outside `.github` that loads as
a mapping with a top-level `name` key, on each repository's integration branch:

| Repository | Commit | Documents | Accepted |
| --- | --- | --- | --- |
| rae: examples, contract fixtures, documentation, specifications, and test data | `dev` a391904a | 81 | 50 |
| env-packs | `dev` 1d8adfb | 97 | 92 |
| lilrae | `dev` d77c06f4 | 12 | 6 |
| adapters | `dev` 0272949 | 10 | 0 |
| reference-packs | `main` 445c3ca | 0 | 0 |
| hub | `dev` 4f15773 | 0 | 0 |

Full validation outcomes, error text included, are identical before and after
the change for all 200 documents, both as authored and with legacy spellings
accepted. As authored, 148 are accepted and 52 are rejected for unchanged
reasons. The rejected files include intentionally invalid fixtures, pack
manifests and Compose files that are not SDL, and documents that need a
migration first, such as all the adapters SDL files.

The 162 documents that parse structurally with legacy spellings accepted name
these declaration kinds, by reference purpose. A reference counts when it
resolves to one declaration among its purpose's resolution domain; the fields
of each purpose are listed in the
[reference-purpose catalog](../../specs/sdl/references.md#7-reference-purposes-and-eligibility).

| Purpose | Declaration kinds named |
| --- | --- |
| objective subject | content, named infrastructure ACLs, nodes, relationships, node services |
| action target | content, named infrastructure ACLs, nodes, relationships, node services |
| shared state | node services |
| authority scope, including mixed-control and delivery scopes | content, nodes, node services |
| observation subject | action contracts, agents, content, organizations, nodes, participant inject deliveries, runtime-inventory records, node services |
| authority anchor | content, organizations |
| declared | action contracts, organizations, nodes, participant inject deliveries |
| targetable | action contracts, conditions, content, observation boundaries, runtime applications |
| relationship endpoint (generic types and details) | accounts, features, nodes |
| node endpoint | nodes |
| identity domain endpoint | identity domains |
| identity authority endpoint | identity forests |
| identity facade endpoint | identity facades |
| deployment tenant endpoint | deployment tenants |
| node service endpoint | node services |
| runtime application endpoint | runtime applications |
| database endpoint | runtime database services |
| participant endpoint | agents, and one organization in a fixture that is invalid on purpose |

No document names a `forest_trusts` endpoint or a `mail_access` target. No
accepted reference narrows: every typed endpoint names a kind that its
subtype's check already accepted. The organization endpoint is
`contracts/fixtures/sdl/participant-relationships-v1/invalid/entity-endpoint.yaml`,
which was already rejected.

## Editor behavior

- Completion contexts name the purpose token, such as
  `reference:eligible:objective_subject`. A relationship endpoint's context
  names the purposes that its type and typed details select for that side:
  `reference:eligible:<purpose>` for one, such as
  `reference:eligible:participant_endpoint`, which offers only agents, and
  `reference:eligible:<p1>+<p2>` for several, in policy order. A typed
  endpoint's context therefore changes from
  `reference:eligible:relationship_endpoint` to its endpoint purpose, for
  example `reference:eligible:node_endpoint` for a `domain_controller_for`
  source. A conjunction that no declaration satisfies, such as
  `reference:eligible:node_endpoint+runtime_application_endpoint`, offers
  nothing.
- Interaction targets, shared-state refs, effect target refs, agent authority
  anchors, and agent operating scope now have completions. Temporal-constraint
  subjects complete every declared reference. Participant relationship
  `scope_refs` complete only the operating scopes that both endpoints hold, and
  `authority_basis_refs` only the source's authority anchors. An endpoint that
  does not resolve to one participant, or whose own list is parameterized, does
  not restrict them. Validation also requires a selected
  `control_specification_ref` to cover each scope; completion applies the same
  active controller-state selection and excludes scopes outside it, including
  when completing an individual list item.
- A variation point's `target.owner` completes and navigates in its target
  slot's owner section, and a candidate's `reference` or governed
  `domain.allowed_refs` entry in the slot's candidate section or purpose, as
  validation resolves them. An `objectives.targets` point is offered only
  objectives as owners and objective subjects as candidates.
- Completion offers one unambiguous spelling per eligible declaration, and
  qualifies a bare name that validation would find ambiguous, including one
  shared with a refused declaration. Documents that do not validate yet use the
  same purposes and one index that the validator's index builder makes from the
  top-level entries that validate on their own, plus the names of the other
  top-level entries; infrastructure entries are offered only in qualified form
  because they have no bare alias. A declaration inside an entry that does not
  validate on its own is not in that index: it is neither offered nor reported
  as an occurrence, and it does not make a spelling ambiguous. For example, a
  content item `alpha` in a content entry with a stray field, next to node
  `alpha`, leaves `alpha` naming the node until the entry validates; validation
  may then refuse `alpha` as ambiguous. Operating-scope fields, agent
  `operating_scope` and participant-relationship `scope_refs`, are the
  exception: their aliases depend on node types, so they complete and navigate
  only in a document that validates structurally.
- Relationship suggestions also satisfy the owning subtype's known attribute
  and contextual rules. Self-links are excluded for participant relationships
  and forest trusts; topology sources must be compute nodes; placement targets
  must be carriers in the compatible cell. The semantic validator checks
  candidates in a valid context, including controller direction and selected
  policy bounds. In incomplete documents, known attributes still apply.
- Navigation resolves each reference with its field's resolver, as validation
  does, and reports an occurrence of a declaration only when the value resolves
  to exactly that declaration. An ambiguous or refused value is an occurrence of
  no declaration; search for its bare name to find it. Operating scopes resolve
  through their own aliases, including bare service names. Documents that do
  not validate yet resolve names through the same partial index as completion,
  except in operating-scope fields: `dev` reported a participant-relationship
  `scope_refs` value in such a document as an occurrence, and this change
  reports none. A bare node-service or runtime-record name, which the index
  gives no alias, is no occurrence in either kind of document.
- The Python helpers `language_diagnostics`, `language_completions`,
  `language_references`, `language_format`, and `apply_structured_edit` accept
  an optional `path`. With it, local imports compose as in `parse_sdl_file()`,
  so imported declarations complete, navigate, and validate under their
  namespaces, and a namespace imported twice reports the same collision. A
  registry import is refused rather than fetched (see the
  [language-service tools](../explain/sdl/language-service.md#python-helpers)).
  Without a path, and in the MCP tools, behavior is unchanged.

Nested local declarations now have definitions at their authored key or
identifier range. With `path`, imported definitions include the actual module
file, original path and range, composed path, namespace, module identity and
fragment digest. An imported declaration's semantic diagnostic reports its
original file and range together with the canonical composed address. Loading
and composition capture this metadata; editor helpers do not independently
walk imports. Cyclic or overlong locked chains and malformed workspace trust
or lock files return bounded SDL errors, and editor calls never fetch registry
imports, even through a chain of locked records.

Authority scopes compile through the same declaration identities validation
selected. Bare node names remain node scopes beside same-named services.
Participants, entities, relationships and other catalogued semantic-only
surfaces retain their authored scope references without a runtime address;
this conveys no runtime enforcement. Runtime-addressable scopes, including
generated artifacts and persistent volumes, keep their actual compiled
addresses. See the [projection table](../../specs/sdl/references.md#runtime-projection-of-authority-and-operating-scopes).

## Unchanged

Generic relationship endpoints, proposition subjects, evidence source, scope,
channel, trigger, and boundary refs, observation-demand component refs, agent
authority anchors, and agent operating scope accept the same declarations as
before. The inspection payload keeps `referenceable` and `targetable`;
`targetable` now reports the general target purpose. The only published
schema change is the `Relationship` description in five schemas, which now
states endpoint eligibility and typed narrowing; it is a description-only
change on the same contract versions. Historical evidence, compiled snapshots,
and stored records are not rewritten.

Eligibility only decides what a reference may name. Targeting a participant or
naming an organization as an objective subject grants neither participation,
authority, nor visibility.
