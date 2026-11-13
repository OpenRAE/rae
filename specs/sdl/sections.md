<!-- vale RAES.HeadingCase = NO -->
# Catalog 1 — section catalog

This catalog enumerates every top-level SDL field.
It gives each field's kind, value shape, requirement, key shape, and referenced sections.
This normative section list matches the published `contracts/schemas/sdl/sdl-authoring-input-v1.json` schema.
A difference between this table and that schema is a defect to reconcile
([README](README.md)).

<!-- vale RAES.HeadingCase = YES -->

Value-shape legend:

- **scalar** — a single string value.
- **mapping** — a mapping with fixed keys (a structured object, not keyed by
  user identifiers).
- **map** — a mapping keyed by **user-defined identifiers**, each value an
  element of the named type.
- **list** — an ordered sequence of elements; element identity is carried by an
  `<noun>_id` field on each element, not by a mapping key.

"References" names the other sections an element of this section may name; the
resolution rules and full reference-edge catalog with failure semantics are in
[`references.md`](references.md). A blank "References" cell means the section is
referenced by others but does not itself reference another section.

## Complete top-level field catalog

This table is the complete, mechanically checked top-level language surface.
"Lifecycle" names the document forms in which the field is carried. A field
absent from a lifecycle is forbidden by that phase's closed model; authoring
machinery is not retained as an empty compatibility field. "References" is
`catalogued` when the field owns at least one row in the exact edge index in
[`references.md`](references.md).

| Field | Kind | Shape | Lifecycle | Presence/default | Identity | References | Semantic owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `name` | metadata | scalar | normalized, expanded, instantiated | required | `scenario_name` | none | [document model](document-model.md) |
| `semantic_revision` | metadata | scalar | normalized, expanded, instantiated | optional; default null | none | none | [progressive semantic revisions](../evolution/progressive-semantics.md) |
| `version` | metadata | scalar | normalized, expanded, instantiated | optional; default `*` | none | none | [document model](document-model.md) |
| `description` | metadata | scalar | normalized, expanded, instantiated | optional; default empty string | none | none | [document model](document-model.md) |
| `module` | composition | mapping | normalized | optional; default null | `module.id` | none | [ADR-053](../../docs/decisions/adrs/adr-053-sdl-module-composition-for-inventory-backed-scenarios.md) |
| `imports` | composition | list | normalized | optional; default empty list | `namespace` | none | [ADR-053](../../docs/decisions/adrs/adr-053-sdl-module-composition-for-inventory-backed-scenarios.md) |
| `realization` | composition | mapping | normalized | optional; default null | none | none | [explicitness and realization](../formal/realization/explicitness-and-realization.md) |
| `trial_parallelism` | section | mapping | normalized, expanded, instantiated | optional; default null | none | none | [trial scheduling](../formal/scenario-variation-trial-realization/README.md#svr-031--scheduler-opacity) |
| `nodes` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [nodes and runtime inventory](runtime-inventory.md) |
| `infrastructure` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [document model](document-model.md) |
| `features` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [document model](document-model.md) |
| `conditions` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [proposition semantics](../../specs/formal/objectives/proposition-and-assertion-semantics.md) |
| `propositions` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [proposition semantics](../../specs/formal/objectives/proposition-and-assertion-semantics.md) |
| `assertions` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [proposition semantics](../../specs/formal/objectives/proposition-and-assertion-semantics.md) |
| `entities` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [document model](document-model.md) |
| `injects` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [reference catalog](references.md) |
| `events` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [reference catalog](references.md) |
| `scripts` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [reference catalog](references.md) |
| `stories` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [reference catalog](references.md) |
| `content` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [initial service state](initial-service-state.md) |
| `generated_artifacts` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [stateful resources](stateful-resources.md) |
| `persistent_volumes` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [stateful resources](stateful-resources.md) |
| `accounts` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [account credential bindings](account-credential-bindings.md) |
| `identity_domains` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [authored domain topology](authored-domain-topology.md) |
| `identity_forests` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) |
| `identity_facades` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) |
| `deployment_tenants` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | none | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) |
| `deployment_cells` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) |
| `relationships` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) |
| `forwarding_agents` | section | list | normalized, expanded, instantiated | optional; default empty list | `forwarding_agent_id` | none | [ADR-050](../../docs/decisions/adrs/adr-050-forwarding-agent-runtime-inventory.md) |
| `control_context_assets` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | none | [control-context references](participant-control-context.md) |
| `agents` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [participant model](../formal/participant-semantics/README.md) |
| `action_contracts` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [participant model](../formal/participant-semantics/README.md) |
| `observation_boundaries` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [participant model](../formal/participant-semantics/README.md) |
| `outcome_interpretation_rules` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [participant model](../formal/participant-semantics/README.md) |
| `behavior_specifications` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [behavior specifications](../formal/participant-behavior-model/README.md) |
| `evidence_requirements` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [observability and evidence](observability-and-evidence.md) |
| `execution_policy` | section | mapping | normalized, expanded, instantiated | optional; default null | none | catalogued | [execution and recovery](execution-recovery.md) |
| `safe_state` | section | mapping | normalized, expanded, instantiated | optional; default null | none | catalogued | [safe state](safe-state.md) |
| `augmentation_scope` | section | mapping | normalized, expanded, instantiated | optional; default null | none | none | [augmentation scope](augmentation-scope.md) |
| `time_domains` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | none | [shared time model](../formal/time-model/README.md) |
| `clocks` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [shared time model](../formal/time-model/README.md) |
| `time_domain_mappings` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [shared time model](../formal/time-model/README.md) |
| `time_progression_policies` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [shared time model](../formal/time-model/README.md) |
| `temporal_constraints` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [shared time model](../formal/time-model/README.md) |
| `objectives` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [objective semantics](../formal/objectives/declarative-objective-semantics.md) |
| `workflows` | section | map | normalized, expanded, instantiated | optional; default empty map | `map_key` | catalogued | [workflow semantics](../formal/workflows/state-machine.md) |
| `variables` | section | map | normalized, expanded | optional; default empty map | `map_key` | none | [variables and instantiation](variables-and-instantiation.md) |
| `variation_points` | section | map | normalized, expanded | optional; default empty map | `map_key` | catalogued | [scenario-family variation points](variation-points.md) |

The absent/null `augmentation_scope` carrier means **open**, not closed. Authors
explicitly opt into restrictions; requiring advance authorization of every backend
addition would impose a large, unexpected authoring burden. The policy also
survives into materialized descriptions, where its addresses retain their
original-source meaning. See [augmentation scope](augmentation-scope.md).

<!-- sdl-catalog-summary top-level=49 metadata-composition=7 sections=42 maps=37 lists=1 -->

The section set therefore has two authoring shapes: maps keyed by stable
user-defined identifiers and the scenario-level `forwarding_agents` list, whose
elements carry their own stable identity. The checked summary above is derived
from the rows; changing a row without reconciling it fails the contract gate.

`realization` is the scenario-root, authoring-only designation table. Its
`default` is `closed`, `open`, or `unspecified`; optional `scopes` override that
posture at canonical namespace/pointer identities. Its optional `constraints`
list carries addressed concern-specific mechanism intent. A compute-substrate
constraint uses a `namespace`, a `field_pointer` addressing one compute node, the
literal concern `compute-substrate`, an `open`, `constrained`, or `exact`
posture, and a compatible domain when bounded. Equal
`(namespace, field_pointer, concern)` identities are invalid. Expansion and instantiation remove the block from executable scenario content.

They carry typed designation and constraint records in phase provenance.
Compilation resolves those records without turning authoring machinery into runtime scenario content.

`nodes.*.type` is a structural resource kind, not a deployment mechanism. Its
canonical values are `compute` and `switch`. A `compute` node is portable and
does not imply a virtual machine, container, physical device, or in-process
emulator. Authors who require or bound a mechanism use
`realization.constraints`; an omitted compute-substrate constraint deliberately
leaves that registered concern open. A switch remains a strict connectivity
resource and cannot carry compute-substrate constraints or compute-only fields.

A switch can state a compute-only field only with its empty value: `null`, an
empty string, or an empty collection. That value has the same meaning as an
omitted field, and realization authority treats it as omitted.

`forwarding_agents` is the **scenario-level** forwarding-agent inventory. It is
distinct from the node-scoped `forwarding_agents` runtime-family collection that
lives under `nodes.<id>.runtime` ([runtime-inventory.md](runtime-inventory.md));
both carry `forwarding_agent_id` identity and the same family invariants.
They occupy different positions in the document.

## Realization posture and closure

Realization uses two independent axes, as defined by
[envelope semantics](../formal/realization/envelope-semantics.md#terms):

- **Posture** constrains a value or child scope: `open` delegates selection,
  `constrained` requires a typed domain, and `exact` requires its singleton value.
- **Closure** governs additional realizable dimensions or members:
  `open-world` permits them within the owning semantics; `closed-world` excludes them.
  A local declaration can leave closure unresolved for its owning resolution rules.

The table maps the three vocabularies to these axes.
“Not set” means that the term supplies no declaration on that axis.
It does not erase an independently declared constraint.

| Source vocabulary | Term | Posture axis | Closure axis | Meaning |
| --- | --- | --- | --- | --- |
| Author `realization.default` and `scopes[].posture` | `closed` | Not set | `closed-world` default | Do not fill otherwise unspecified realizable concerns under this default. |
| Author `realization.default` and `scopes[].posture` | `open` | Not set | `open-world` default | Delegate otherwise unspecified realizable concerns; explicit descendants remain binding. |
| Author `realization.default` and `scopes[].posture` | `unspecified` | Not set | No concrete local default | Use a governing concrete scope, or defer to the apparatus default. |
| Concern constraint or envelope binding | `open` | `open` | Not set | Permit selection at the designated realization point within the admitted capability domain. |
| Concern constraint or envelope binding | `constrained` | `constrained` | Not set | Require selection within the stated typed domain. |
| Concern constraint or envelope binding | `exact` | `exact` | Not set | Require the stated singleton value or structure. |
| Recursive record, collection, or scope closure | `open` | Not set | `open-world` in the named universe/profile | Permit additional modeled members while preserving declared children. |
| Recursive record, collection, or scope closure | `closed` | Not set | `closed-world` in the named universe/profile | Exclude additional modeled members without making child values exact. |
| Recursive record, collection, or scope closure | `undefined` | Not set | No local closure | Inherit a concrete lexical scope or document default; unresolved effective closure is `unsupported`. |

This model does not add SDL fields or replace existing wire spellings.
The source context determines which axis a term addresses.
An exact package version can coexist with open package membership.
A closed collection can contain constrained child values.
Presence, knowledge, origin, capability, and observation demand remain independent.

The [author cascade](../formal/realization/explicitness-and-realization.md#scoped-default-cascade)
retains explicit leaf precedence, namespace ownership, and most-specific concrete defaults.
Equal-scope duplicates are invalid; declaration order has no effect.
Explicit `unspecified` retains delegation provenance.
Without a selected apparatus policy, its current fallback is closed.
Omitting `realization` instead retains the legacy closed fallback without an explicit delegation record.
The owning compute-substrate rule still makes an omitted substrate constraint open.

[Recursive closure](recursive-realization-constraints.md#2-records-scopes-and-closure)
retains its own local and lexical resolution rules.
A concrete closure names both its universe and profile revision.
An undefined closure supplies neither name.
The pure recursive relation does not select apparatus policy.
Closure covers its named universe, not every incidental dependency or backend setting.

Envelope bindings retain their separate
[override rules](../formal/realization/envelope-semantics.md#required-semantics).
Semantic openness does not admit unknown SDL fields.
An open author default does not waive explicit leaf constraints.
[Augmentation scope](augmentation-scope.md) separately governs added in-world effects and remains open by default.

## Narrative chain

[External inject triggering](external-injects.md) defines the accepted
occurrence/admission/outcome amendment for existing inject authoring. An
environment and ordinary injects need no declared participants. Plan
installation, queued status and participant delivery do not prove world-effect
execution. This semantic decision introduces no parser fields or wire schema;
its [compatibility contract](../../docs/explain/sdl/external-inject-compatibility.md)
governs explicit executable adoption.

One reference chain runs through the catalog and is called out because its
ordering is normative (resolution and failure semantics in
[`references.md`](references.md)):

- **Narrative chain:** `injects` → `events` → `scripts` → `stories`, with
  `injects` naming `entities` and `events` naming precondition assertions. Objective
  windows bind `stories`/`scripts`/`events`/`workflows`.

Participant-directed delivery is an explicit nested binding under `behavior_specifications.*.participant_inject_deliveries`.
It anchors one participant to one inject occurrence across the event/script/story chain.
It binds a participant-visible result, observation boundary, revisioned delivery policy, shared-time constraint, and evidence requirement.
When applicable, it also binds a mixed-control transition.

Direction and intervention bindings state the controller, authority scope, effective order, validity interval, and evidence basis.
These must agree with the transition and its target controller state.
Their order must satisfy the named temporal constraints.
Their control evidence must be covered by the named evidence requirements.
An inject without that binding remains ordinary orchestration input.
`injects.*.environment` never implies participant delivery.

The view rule that admits the result must itself agree with the delivery's
visibility and disclosure bases. Every control scope and evidence reference
must resolve individually. Required source and result items must each project
to one runtime address; an unaddressable item prevents compilation of that
delivery and produces a diagnostic. Semantic-only authority and evidence
references remain valid anchors without acquiring runtime addresses.

The field-level description above is the legacy fixed-coordinate form, which a
`mixed_control` without `semantics` keeps. The parser also accepts the reusable
form of [ADR-110](../../docs/decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md),
selected only by `semantics: mixed-control-policy-occurrence/rev1` and a
required `form` of `reusable-policy` or `finite-script`. Its
`permitted_transitions` are reusable permissions with no fixed revision, order
or proposal identity ([MC-01](../formal/participant-semantics/reusable-mixed-control.md#mc-01--policy-permissions-and-occurrence-facts)).
A finite script adds ordered `script_steps` that may only narrow their edges
([MC-02](../formal/participant-semantics/reusable-mixed-control.md#mc-02--reusable-policies-and-finite-scripts)).

Each application is one API-409 `participant-control-occurrence-v2` occurrence.
It has a fresh identity, its exact edge ref, and exact prior and resulting states.
Each accepted kind has a resulting revision of expected + 1
([MC-03](../formal/participant-semantics/reusable-mixed-control.md#mc-03--exact-state-relation-and-repeated-cycles)),
and a participant-wide `occurrence_revision`. It carries the acting source
controller, grant and scope
([MC-04](../formal/participant-semantics/reusable-mixed-control.md#mc-04--acting-controller-authority-and-handoff)).

An accepted occurrence records its admitted order and inclusive evaluated
bounds; a rejected one keeps attempted and observed values apart and asserts
no validity. Under that form a directed delivery carries a nested `control`
block that names one permission and joins one exact accepted occurrence
([MC-09](../formal/participant-semantics/reusable-mixed-control.md#mc-09--participant-directed-injects)).

The block pins the control policy apart from the delivery policy.
It uses the source-state controller and a non-widening scope.
It compares no order with shared time. Ordinary injects and disclosure-only bindings are unchanged. The rev1 form validates and compiles.

Planning refuses it for every backend.
The reference runtime refuses its execution admission and control-plane construction.

No runtime executes it. The
[migration contract](../../docs/migration/reusable-mixed-control.md) retains
the old form's historical interpretation, and the
[finite-script conversion record](../../docs/migration/mixed-control-finite-script-conversion.md)
states when a legacy declaration converts.

`propositions` state typed claims; `assertions` use them as preconditions,
invariants, or postconditions. Objective success composes invariant or
postcondition assertions, while events and workflow predicates reference
precondition assertions. `conditions` are executable probe declarations and
must explicitly identify the proposition they realize; they are not observable
facts. The SDL carries no
graded scoring pipeline — the OCR-inherited `metrics`, `evaluations`, `tlos`
(Training Learning Objectives), and `goals` sections were removed with
[ADR-073](../../docs/decisions/adrs/adr-073-scoring-reward-language-scope.md).
Graded scoring, reward, leaderboard values, and evaluation outputs live in the
experiment/evaluator plane
([ADR-055](../../docs/decisions/adrs/adr-055-experiment-core-contract-boundary.md),
[ADR-064](../../docs/decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md),
[ADR-069](../../docs/decisions/adrs/adr-069-cage-2-replication-architecture.md)),
never as authored SDL.

## Participant episode structure

`behavior_specifications.*.episode_policy` is an optional, closed record of
authored episode intent (DSL-120) for the participants that its behavior
specification selects. Its design authority is the
[participant episode model](../formal/participant-episode-model/README.md).
The required `profile` is `participant-episode-policy/v1`. The record declares
at least one of the following:

- `initialization` names precondition assertions for every new episode
  generation.
- `interaction_structure` orders turns by the `decision-epoch` authority and
  names the action contracts a turn offers. Each one must belong to the owning
  behavior specification and to every participant it selects.
- `terminal_conditions` is keyed by local condition identifiers. A `completed`
  condition names invariant or postcondition assertions. A `timed_out`
  condition names one deadline, window, or duration constraint. That
  constraint must bind the owning behavior specification or every participant
  it selects.
- `truncation_conditions` is keyed by local condition identifiers that differ
  from the terminal ones. Each names the invariant or postcondition assertions
  whose evidenced truth ends the episode as `truncated`, and it carries no
  `terminal_reason`. Its assertion set must differ from that of every
  `completed` condition, so one evidenced fact never ends an episode as both.
- `reset_policy` names the admitted `reset`/`restart` control actions and the
  ADR-095 participant-memory scope across the reset boundary. An
  `episode_local_reset` scope also names a `memory_reset_authority_ref`, and a
  `persistent_across_episodes` scope names none. The ADR-095 decision-surface
  assurance and information-state contracts require the same pairing; the
  policy does not supply their values. The authority must resolve to exactly
  one declared targetable element, such as a participant, an entity, or a
  service. An imported unit must resolve it to one element on its own before
  module composition namespaces it, and compilation records that element's
  canonical address.

An episode policy may be the behavior specification's only behavior surface.
The parser and published schemas require at least one nonempty structure element.
Null records and empty condition maps do not satisfy this requirement.

A condition holds only when every assertion it names holds. Every condition
and the reset policy name the evidence requirements that together back the
transition. Semantic validation requires each named requirement to be
declared; it does not check which record the requirement captures.
`interrupted` is never authored, because interruption is externally induced. A participant is governed by at most one episode policy,
because realized episodes are keyed by participant.

The record holds
references only. It rejects realized episode coordinates such as episode
identity, lifecycle status, timestamps, sequence numbers, and decision epochs.
Those stay on the ADR-013 participant episode state and history contracts.
Checks that need a participant selection or a reference still written as a
`${var}` run again after instantiation.

Compilation emits one `participant.episode-policy.<name>` record beside the
selected participants' `participant.behavior.<agent>` episode addresses. It
never initializes, resets, or ends an episode. Compilation alone claims no
executable or runtime adoption.

The [episode policy reference](../../docs/explain/sdl/participant-episode-policies.md)
gives an authoring example, reset rules, and lineage sources.

Episode structure is a first-class member of the behavior specification aggregate (ACT-623).
A policy attaches to participants of every behavior mode, and to a specification without a behavior mode.
The autonomous execution profile cannot contain a policy.
The compiled aggregate names its policy through `episode_policy_address`.
The address is empty when the specification has no policy.

The decision epoch orders turns. The episode `sequence_number` orders only episode instances.

Runtime adoption requires an explicit `ParticipantEpisodeRuntimeBinding` on the control plane.
The binding holds the compiled model and one implementation selection for each governed participant.
Each selection must agree with its manifest identity, digest, decision mode, and episode contract support.
A plan with episode policies is applied, authorized, or admitted only under a binding that holds the exact compiled model of that plan.

The runtime admits only the reset actions of the reset policy, and only terminal reasons that an authored condition produces.
An `interrupted` stop is always admitted. A policy without a `reset_policy` admits all resets and restarts.
These bounds apply to operator and participant requests, mixed-control lifecycle requests, and autonomous clock resets.
The runtime refuses returned or restored episode history that violates the policy.
It preserves ADR-013 participant identity, generation, and append-only history.

Target conformance compares recorded episode history with the compiled policy.
A missing history for a governed participant fails the check.
A target without episode capability, or a scenario without a policy, gives `not-applicable`.
This inspection does not show condition evaluation, memory-reset realization, or native execution.
The [episode runtime binding guide](../../docs/explain/sdl/participant-episode-runtime-binding.md)
explains how to install the binding and read the conformance result.

## Extending the section set

A new top-level authoring section requires its model, published schema field, and a row in this catalog.
The row gives its shape, requiredness, key shape, and references.
Its reference edges belong in [the reference catalog](references.md).
The reference implementation and its tests must also be updated.
Scenario-native observability and authored evidence-requirement sections must also satisfy
[the evidence-plane reference](observability-and-evidence.md).
No parallel section registry exists or should be created.
