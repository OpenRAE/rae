# Reference eligibility changes

This reference records the purpose-specific eligibility change in issue #1339.
It applies to the Python contract retained in RAES 11.0.2.
Use [rewrite and validate references](../../migration/reference-eligibility.md#rewrite-and-validate) for the operating task.
The inventory below describes its named historical revisions only.

Issue #1339 replaces the exclusion-based `targetable` rule with an explicit
eligibility decision for each reference purpose. The
[reference-purpose catalog](../../../specs/sdl/references.md#7-reference-purposes-and-eligibility)
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

An effect `target_refs[]` token may name no declaration.
That token remains observation-boundary information.
Recorded action results still check it against the participant's observation boundary.
A bare or qualified token naming a registered declaration is now checked.
It must name exactly one targetable declaration.
That declaration must be an action target.

Every indexed kind is referenceable except scenario identity, node roles, workflow steps, and `outcome_interpretation_rules` entries.
Those kinds are also refused as effect targets, including inside imported modules.
A free-form token matching a declared bare name is refused unless it names an action target.
For example, `port` beside variable `port` fails with
`... does not reference any defined element eligible as an action target; it names variables.port`.
Rename the token or name the intended action target.

Narrowing only refuses references.
It does not make a previously unresolved bare name resolve.
These fields resolve bare names among all targetable declarations.
The single match must then be eligible.
A name shared with a refused declaration remains ambiguous.
For a node and condition both named `web`, use `nodes.web`.
The same rule applies to participant relationship endpoints.
If an organization or resource shares the name, use `agents.<name>`.

A refused reference fails semantic validation as dangling.
For the table's fields, its diagnostic names the purpose and the declaration it found.
For example:
`Action contract 'probe' interaction[0] target 'assertions.done' does not reference any defined element eligible as an action target; it names assertions.done`.
An inject delivery's `control_authority_scope_refs[]` must equal its target controller state's `scope_refs[]`.
The state's diagnostic can therefore refuse it.
Alternatively, the delivery is reported as disagreeing with the state.

Other reference fields keep their existing diagnostic wording.
These include relationship endpoints, proposition subjects, evidence refs, authority anchors, and general declared/targetable fields.
Their wording is `any defined element` or `any defined targetable element`.
They gain `; it names` details when a reference names a declaration.
Ambiguous bare-name diagnostics list eligible choices first, then refused declarations.
For example:
`'web' is ambiguous; use one of: nodes.web; not eligible as an authority scope: conditions.web`.
Participant endpoints and operating scopes keep their diagnostics.
Instantiation reports the same diagnostic for a substituted variable value.
Composition reports it under the import namespace.

There is no compatibility reader.
Only the author knows the intended declaration.
Use the table above to rewrite a refused reference by hand.

## Typed relationship endpoints

Each relationship type and typed detail field now has an explicit endpoint
decision, listed in the
[subtype decision table](../../../specs/sdl/references.md#7-reference-purposes-and-eligibility).
The ten endpoint purposes, such as `node_endpoint` for a `domain_controller_for`
source or `mail_service_endpoint` for a `mail_access` target, admit declaration
kinds rather than categories. An endpoint must satisfy the purpose of its type
and of every typed detail it carries.

Typed endpoints refuse nothing new.
Each kind set equals what its subtype check already accepted.
Tests compare the identity, topology, and tenancy checks with the policy for equality.
The `database_access` and `mail_access` checks now read the policy's sets. A typed endpoint that names the wrong kind
gains the shared diagnostic next to the subtype's existing message, for example
`Relationship 'trust' source 'conditions.alive' does not reference any defined
element eligible as an identity forest endpoint; it names conditions.alive`. A
typed endpoint whose purposes no declaration satisfies, such as a
`domain_controller_for` source that also carries `database_access`, names each
purpose that its match fails.

Runtime child records are named by family inside the policy, so a `mail_access`
target admits a mail service listener and refuses a security-monitoring manager
listener. Published declaration kinds do not change.
External-concept `subject_kind`, transformation-report `declaration_kind`, and inspection output keep the same kinds.
A mail listener still uses `runtime-listeners`.

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

All 200 documents kept the same full validation outcomes, including error text.
This held both as authored and with legacy spellings accepted. As authored, 148 are accepted and 52 are rejected for unchanged
reasons. The rejected files include intentionally invalid fixtures, pack
manifests and Compose files that are not SDL, and documents that need a
migration first, such as all the adapters SDL files.

The 162 documents that parse structurally with legacy spellings accepted name
these declaration kinds, by reference purpose. A reference counts when it resolves to one declaration in its purpose's resolution domain.
Each purpose's fields appear in the
[reference-purpose catalog](../../../specs/sdl/references.md#7-reference-purposes-and-eligibility).

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

### Purpose contexts

Completion contexts name the purpose token, such as `reference:eligible:objective_subject`.
A relationship endpoint's context uses the purposes selected by its type and typed details for that side.
One purpose uses `reference:eligible:<purpose>`.
For example, `reference:eligible:participant_endpoint` offers only agents.
Several purposes use `reference:eligible:<p1>+<p2>` in policy order.

A typed endpoint no longer uses generic `reference:eligible:relationship_endpoint`.
It uses its endpoint purpose instead.
A `domain_controller_for` source uses `reference:eligible:node_endpoint`.
A conjunction with no eligible declaration offers nothing.
For example, `reference:eligible:node_endpoint+runtime_application_endpoint` offers nothing.

### Field completion

Completion covers interaction targets, shared-state refs, and effect target refs.
It also covers agent authority anchors and operating scope.
Temporal-constraint subjects complete every declared reference.
Participant relationship `scope_refs` offer only operating scopes held by both endpoints.
Their `authority_basis_refs` offer only the source's authority anchors.
An unresolved endpoint or parameterized endpoint list does not restrict those offers.

Validation requires the selected `control_specification_ref` to cover each scope.
Completion uses the same active controller-state selection.
It excludes scopes outside that selection, including individual list-item completions.

A variation point's `target.owner` completes and navigates in the target slot's owner section.
Its candidate `reference` or governed `domain.allowed_refs` uses the slot's candidate section or purpose.
These are the same choices validation resolves.
An `objectives.targets` point offers only objectives as owners.
It offers objective subjects as candidates.

### Partial documents and ambiguity

Completion offers one unambiguous spelling per eligible declaration.
It qualifies any bare name that validation finds ambiguous.
This includes names shared with refused declarations.

Incomplete documents use the same purposes and one partial index.
The validator's index builder supplies that index.
It contains top-level entries that validate on their own.
It also contains names of the other top-level entries.
Infrastructure entries have no bare aliases and are offered only in qualified form.

A declaration inside an invalid entry is not in the index.
It is neither offered nor reported as an occurrence.
It does not make another spelling ambiguous.
For example, an invalid content entry may contain `alpha` beside node `alpha`.
While that entry has a stray field, `alpha` names the node.
After the entry validates, validation may refuse `alpha` as ambiguous.

Operating-scope fields are the exception.
These are agent `operating_scope` and participant-relationship `scope_refs`.
Their aliases depend on node types.
They complete and navigate only when the document validates structurally.

### Relationship suggestions

Suggestions also meet the owning subtype's known attribute and context rules.
Participant relationships and forest trusts exclude self-links.
Topology sources must be compute nodes.
Placement targets must be carriers in the compatible cell.
In a valid context, the semantic validator checks candidates.
Those checks include controller direction and selected policy bounds.
Known attributes still apply to incomplete documents.

### Navigation and occurrences

Navigation uses each field's resolver, as validation does.
It reports an occurrence only when a value resolves to exactly that declaration.
An ambiguous or refused value is an occurrence of no declaration.
Search for its bare name to find it.
Operating scopes use their own aliases, including bare service names.

Incomplete documents use the same partial index as completion, except for operating-scope fields.
Previously, `dev` reported participant-relationship `scope_refs` occurrences in such documents.
This change reports none.
Bare node-service and runtime-record names have no index aliases.
They are not occurrences in either kind of document.

### Local imports

These Python helpers accept an optional `path`:
`language_diagnostics`, `language_completions`, `language_references`, `language_format`, and `apply_structured_edit`.
With it, local imports compose as in `parse_sdl_file()`.
Imported declarations complete, navigate, and validate under their namespaces.
Importing a namespace twice reports the same collision.
Registry imports are refused, not fetched.
See [language-service tools](../sdl/language-service.md#python-helpers).
Without a path, behavior is unchanged.
MCP tool behavior is unchanged too.

Nested local declarations have definitions at their authored key or identifier range.
With `path`, imported definitions include the actual module file and original path/range.
They include composed path, namespace, module identity, and fragment digest too.
An imported declaration's semantic diagnostic reports its original file and range.
It also gives the canonical composed address.
Loading and composition capture this metadata.
Editor helpers do not independently walk imports.

Cyclic or overlong locked chains return bounded SDL errors.
Malformed workspace trust or lock files do too.
Editor calls never fetch registry imports, even through locked-record chains.

### Runtime projection

Authority scopes compile through the declaration identities selected by validation.
Bare node names stay node scopes beside same-named services.
Participants, entities, relationships, and other catalogued semantic-only surfaces keep authored scope references without a runtime address.
This grants no runtime enforcement.
Runtime-addressable scopes keep their actual compiled addresses.
These include generated artifacts and persistent volumes.
See the [projection table](../../../specs/sdl/references.md#runtime-projection-of-authority-and-operating-scopes).

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
