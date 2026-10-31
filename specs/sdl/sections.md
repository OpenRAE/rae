# Catalog 1 — Section Catalog

This catalog enumerates every top-level field of an SDL document: its kind, its
value shape, whether it is required, the shape of its keys, and the sections it
references. It is the normative section enumeration and is written to match the
published `contracts/schemas/sdl/sdl-authoring-input-v1.json` schema; where this
table and that schema diverge, the divergence is a defect to reconcile
([README](README.md)).

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

<!-- sdl-catalog-summary top-level=47 metadata-composition=7 sections=40 maps=37 lists=1 -->

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
`(namespace, field_pointer, concern)` identities are invalid. Expansion and
instantiation remove the block from executable `ScenarioContent` and carry typed
designation and constraint records in phase provenance so compilation can
resolve them without turning authoring machinery into runtime scenario content.

`nodes.*.type` is a structural resource kind, not a deployment mechanism. Its
canonical values are `compute` and `switch`. A `compute` node is portable and
does not imply a virtual machine, container, physical device, or in-process
emulator. Authors who require or bound a mechanism use
`realization.constraints`; an omitted compute-substrate constraint deliberately
leaves that registered concern open. A switch remains a strict connectivity
resource and cannot carry compute-substrate constraints or compute-only fields.

`forwarding_agents` is the **scenario-level** forwarding-agent inventory. It is
distinct from the node-scoped `forwarding_agents` runtime-family collection that
lives under `nodes.<id>.runtime` ([runtime-inventory.md](runtime-inventory.md));
both carry `forwarding_agent_id` identity and the same family invariants, but
they occupy different positions in the document.

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

Participant-directed delivery is an explicit nested binding under
`behavior_specifications.*.participant_inject_deliveries`. It anchors one
participant to one inject occurrence across the event/script/story chain and
binds a participant-visible result, observation boundary, revisioned delivery
policy, shared-time constraint, evidence requirement, and—when applicable—a
mixed-control transition. Direction and intervention bindings also state the
controller, authority scope, effective order, validity interval, and evidence
basis that must agree with that transition and its target controller state.
Their order must satisfy the named temporal constraints, and their control
evidence must be covered by the named evidence requirements. An inject without
that binding remains ordinary orchestration input; `injects.*.environment`
never implies participant delivery.

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
It has a fresh identity, its exact edge ref, exact prior and resulting states,
a resulting revision of expected + 1 for every accepted kind
([MC-03](../formal/participant-semantics/reusable-mixed-control.md#mc-03--exact-state-relation-and-repeated-cycles)),
and a participant-wide `occurrence_revision`. It carries the acting source
controller, grant and scope
([MC-04](../formal/participant-semantics/reusable-mixed-control.md#mc-04--acting-controller-authority-and-handoff)).
An accepted occurrence records its admitted order and inclusive evaluated
bounds; a rejected one keeps attempted and observed values apart and asserts
no validity. Under that form a directed delivery carries a nested `control`
block that names one permission and joins one exact accepted occurrence
([MC-09](../formal/participant-semantics/reusable-mixed-control.md#mc-09--participant-directed-injects)).
The block pins the control policy apart from the delivery policy, uses the
source-state controller and a non-widening scope, and compares no order with
shared time. Ordinary injects and disclosure-only bindings are unchanged. The
rev1 form validates and compiles, but planning refuses it for every backend,
the reference runtime refuses its execution admission and control-plane
construction, and no runtime executes it. The
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

## Extending the section set

A new top-level authoring section is added by: defining its model and the
published schema field, adding a row to this catalog (with its shape,
requiredness, key shape, and references), adding its reference edges to
[`references.md`](references.md), and updating the reference implementation and
its tests. Scenario-native observability or authored evidence-requirement
sections must also satisfy
[`observability-and-evidence.md`](observability-and-evidence.md). No parallel
section registry exists or should be created.
