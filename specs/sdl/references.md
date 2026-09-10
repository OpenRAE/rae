# Catalog 2 — Reference-Resolution Catalog

This catalog defines how one SDL element names another: the reference forms, the
resolution algorithm, the fail-closed ambiguity rule, the treatment of
unresolved variable placeholders, and the catalog of cross-section reference
edges with their failure semantics.

References are resolved during **semantic validation**, after structural parsing
and module expansion ([document-model.md §7](document-model.md)). Reference
failures are fatal and are collected together ([diagnostics.md](diagnostics.md)).

## 1. Reference forms

A reference is a string that names a target element. Five forms exist:

1. **Bare** — a single identifier, e.g. `web_db`. Resolved within the section(s)
   the referencing field expects.
2. **Qualified** — a dotted path that names the section and identifier
   explicitly, e.g. `conditions.system_online`, or a deeper path that addresses
   a nested element, e.g. `nodes.web1.services.httpd`. Used to address an element
   unambiguously, or to address an element that has no bare form.
3. **Nested runtime-family** — a qualified path into a node's runtime inventory:
   `nodes.<node>.runtime.<collection>.<id>` and, for child collections,
   `…<collection>.<id>.<child-collection>.<child-id>` to any depth the family
   defines ([runtime-inventory.md](runtime-inventory.md)).
4. **Workflow-step** — `<workflow>.<step>`, naming a step within a workflow.
   Used by objective windows. The workflow portion may be a composition-generated
   qualified name and the step is exactly one portable local-id segment
   ([document-model.md §6](document-model.md)).
5. **Module-composed (namespaced)** — after a module import is expanded, imported
   elements are addressed under their import namespace, and node segments are
   rewritten to their namespaced form. Module-composed references resolve against
   the expanded document
   ([ADR-053](../../docs/decisions/adrs/adr-053-sdl-module-composition-for-inventory-backed-scenarios.md)).

Dots are path syntax, never authored identifier content. A dotted node key in a
raw or normalized authoring object is invalid. A dotted node segment seen after
composition is a validated namespace path and is carried structurally until the
canonical renderer produces the external string; it is not recovered with a
longest-match rule.

## 2. Resolution algorithm

1. A reference **MUST** resolve to **exactly one** declared element of a kind the
   referencing field accepts.
2. A field defines its **candidate set** — the section or sections a value may
   name. Some fields accept a single section (e.g. an objective's `success` →
   `assertions`); others accept a set of targetable sections (e.g. an
   objective's `target`, a relationship's `source`/`target`). The candidate set
   is part of each field's definition and is reflected in the edge catalog (§5).
3. A **bare** reference resolves against the candidate set. A **qualified**
   reference resolves by exact lookup of the typed canonical address and
   **MUST** match it exactly. Implementations **MUST NOT** discover ownership by
   `split`, `partition`, `rsplit`, longest-prefix guessing, declaration order,
   or first match. Compact aliases such as `<qualified-workflow>.<step>` are
   constructed and resolved from declared workflow/step pairs.
4. Some targetable candidate sets are deliberately restricted. For example, an
   objective `target` excludes the `variables`, `objectives`, and `workflows`
   prefixes; an agent `operating_scope` is restricted to compute nodes,
   switch-backed infrastructure, services, and content. A reference outside its
   field's candidate set does not resolve and fails as dangling (§4).
5. Resolution is **declaration-based**: only declared elements are resolution
   targets. There is no implicit creation of a target by referencing it.
6. Alias lookup occurs only after the canonical declaration index has retained
   kind and provenance for every declaration and rejected address collisions.
   A set or map that has already erased a duplicate rendering is not evidence of
   uniqueness.

## 3. Unresolved variable placeholders

1. A field whose value is a variable placeholder (`${name}`) is **not** resolved
   as a reference during authoring-time semantic validation; the placeholder
   stands for a value not yet bound.
2. The only requirement on an unresolved placeholder at authoring time is that
   `name` **MUST** be a declared variable
   ([variables-and-instantiation.md](variables-and-instantiation.md)). A
   placeholder naming an undeclared variable is a fatal error.
3. After instantiation substitutes a concrete value, the normal reference rules
   (§2) apply to that value. A reference that becomes dangling or ambiguous only
   after substitution fails at instantiation.
4. A direct or deserialized instantiated artifact is not exempt. Its required
   provenance can explain binding and resolution inputs, but it does not create
   declarations or authorize references. Artifact admission reruns the same
   declaration-index and reference checks before compilation or snapshotting.

## 4. Failure semantics (fail-closed)

Reference resolution is fail-closed. Two failure modes exist, both fatal:

1. **Dangling** — the reference names no declared element in its candidate set
   (or, for a qualified reference, the path does not exist). This is an error.
2. **Ambiguous** — a bare reference matches **more than one** declared element in
   its candidate set. This is an error. An ambiguous reference **MUST NOT** be
   resolved by first match, by declaration order, or by source-file locality.
   The author resolves the ambiguity by using a qualified reference.

Additional structural reference constraints — uniqueness of an addressed
`<noun>_id`, acyclicity of dependency graphs (`features.dependencies`,
`objectives.depends_on`, workflow step graphs), and closure of workflow control
flow (every referenced successor/join step exists) — are likewise fatal when
violated.

All reference failures in a document are reported together in a single
validation pass rather than one-at-a-time ([diagnostics.md](diagnostics.md)).

## 5. Cross-section reference edge catalog

Each row is a reference edge: a source section's field names a target. Unless
noted, an unresolved (dangling) or ambiguous reference is a fatal error.

The SDL carries no graded scoring pipeline: the OCR-inherited `metrics`,
`evaluations`, `tlos`, and `goals` sections were removed with
[ADR-073](../../docs/decisions/adrs/adr-073-scoring-reward-language-scope.md), so
no reference edge targets them. Graded scoring, reward, and evaluation outputs
live in the experiment/evaluator plane (ADR-055/064/069). `conditions` remain
probe implementations; propositions and assertions carry portable truth.

### Narrative chain

| Source | Field | Target |
|--------|-------|--------|
| `injects` | from/to entity | `entities` |
| `events` | precondition assertion refs | `assertions` |
| `events` | inject refs | `injects` |
| `scripts` | event refs | `events` |
| `stories` | script refs | `scripts` |

### Composition graph

| Source | Field | Target |
|--------|-------|--------|
| `features` | dependencies | `features` (acyclic) |
| `nodes` | feature/condition/inject refs | `features` / `conditions` / `injects` |
| `infrastructure` | node / link / dependency | `nodes` / switch-backed `infrastructure` |
| `content` | target | `nodes` (compute) |
| `content` | `service_materialization.target_service_ref` | a named service on the target compute node |
| `content` | `service_materialization.shared_service_relationship_ref` | `relationships` |
| `content` | `service_materialization.ordering_content_refs[]` | `content` |
| `content` | `service_materialization.readback_assertion_refs[]` | `assertions` |
| `content` | `service_materialization.evidence_requirement_refs[]` | `evidence_requirements` |
| `content` | `service_materialization.observation_boundary_refs[]` | `observation_boundaries` |
| `content` | `service_materialization.requirements.field_semantics` keys and values | concrete portable values, not references |
| `generated_artifacts` | consumers[].node | `nodes` |
| `generated_artifacts` | ordering/refresh dependencies | `generated_artifacts` / `persistent_volumes` (acyclic ordering) |
| `persistent_volumes` | consumers[].node | `nodes` |
| `persistent_volumes` | ordering/refresh dependencies | `generated_artifacts` / `persistent_volumes` (acyclic ordering) |
| `accounts` | node | `nodes` (compute) |
| `accounts` | domain | `identity_domains` |
| `identity_domains` | authority account | `accounts` |

### Agents, objectives, participant surfaces

| Source | Field | Target |
|--------|-------|--------|
| `agents` | entity | `entities` |
| `agents` | starting accounts | `accounts` |
| `agents` | interactive-access target / account | `nodes` (compute) / `accounts` |
| `agents` | subnets / initial-knowledge subnets | switch-backed `infrastructure` |
| `agents` | initial-knowledge hosts | `nodes` (compute) |
| `agents` | initial-knowledge services | declared services on nodes |
| `agents` | starting assertions | `assertions` (preconditions) |
| `agents` | actions / observation boundaries | `action_contracts` / `observation_boundaries` |
| `action_contracts` | interaction related-action | `action_contracts` |
| `observation_boundaries` | view-rule information refs | own observable/hidden/evidence refs |
| `behavior_specifications` | tool-affordance tool/action/observation refs | `content` / `action_contracts` / `observation_boundaries` |
| `behavior_specifications` | tool-affordance visibility identity | own nested affordance declaration, classified by each referenced observation boundary |
| `objectives` | actor | `agents` or flattened `entities` |
| `objectives` | action | the bound agent's `action_contracts` |
| `objectives` | target | targetable elements (excl. `variables`/`objectives`/`workflows`) |
| `objectives` | success criteria | `assertions` (invariants/postconditions, [ADR-079](../../docs/decisions/adrs/adr-079-backend-neutral-proposition-and-truth-semantics.md)) |
| `objectives` | window | `stories`/`scripts`/`events`/`workflows` (with closure rules) |
| `objectives` | depends_on | `objectives` (acyclic) |
| `outcome_interpretation_rules` | source | `action_contracts`/`objectives`/`workflows` |
| `outcome_interpretation_rules` | target | `objectives`/`workflows` |

### Shared time model

| Source | Field | Target |
|--------|-------|--------|
| `clocks` | time domain | `time_domains` |
| `time_domain_mappings` | source / target domain | `time_domains` |
| `time_progression_policies` | clock | `clocks` |
| `temporal_constraints` | clock | `clocks` |
| `temporal_constraints` | subjects | ordinary referenceable SDL declarations or workflow steps |

### Observability and evidence authoring

| Source | Field | Target |
|--------|-------|--------|
| `evidence_requirements` | source refs | targetable elements, including scenario-native observability runtime-family refs |
| `evidence_requirements` | scope refs | targetable elements |
| `evidence_requirements` | channel refs | targetable elements |
| `evidence_requirements` | trigger / boundary refs | targetable elements |

`evidence_requirements` entries are authored capture obligations. They are not
objective targets, workflow steps, variables, or evidence records. Bare
runtime-family child identifiers do not resolve; authors use the qualified
`nodes.<node>.runtime.<collection>.<id>` form when a node-scoped runtime-family
element is the source or channel.

### Workflows

| Source | Field | Target |
|--------|-------|--------|
| `workflows` | start | own steps |
| `workflows` | step successors (`on_success`/`on_failure`) | own steps |
| `workflows` | compensation | other `workflows` |
| `workflows` | predicate assertion refs | `assertions` (preconditions) |
| `workflows` | predicate step refs | own steps (executable) |
| `workflows` | scripted-step procedure refs | `action_contracts` with `procedure` granularity |
| `workflows` | scaffold refs | `observation_boundaries` with scaffold-compatible view rules |
| `workflows` | allowed action families | `action_contracts` with `aggregate` granularity |

Parallel/join control flow MUST be closed: every branch reaches its join and no
join is unreferenced.

### Typed relationships

`relationships` carry a subtype that fixes the kinds of `source`/`target` and
any role-bearing refs
([ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md)):

| Subtype | Endpoints / role refs resolve to |
|---------|----------------------------------|
| generic | targetable elements (`source`/`target`) |
| `database_access` | `source` → an `applications` element; `target` → a `database_services` element; role ref → a declared role on the target |
| `mail_access` | `target` → a `mail_services` element; listener/mailbox/domain refs → declared children of that mail service |
| `forwarding_edge` | `forwarder_ref` → exactly one `forwarding_agents` element (node-scoped or scenario-level); protocol/role MUST agree with a declared ship target |
| `service_integration` | consumer/engine refs → `platform_applications`; auth-principal ref → a declared app-authorization on the engine's node |
| `proxy_upstream` | upstream → a resolved runtime application/endpoint |
| `domain_controller_for` | `source` → a compute node; `target` → an `identity_domains` entry |
| `joins_domain` | `source` → a compute node; `target` → an `identity_domains` entry; controller refs → controller nodes for the same domain |

### Variables

| Source | Field | Target |
|--------|-------|--------|
| any field | `${name}` placeholder | a declared `variables` entry (name only, at authoring time) |

### Scenario-family variation points

Variation targets and candidates are resolved after composition. The closed
target slot narrows the owner and candidate kinds described below; `targetable`
does not permit a point to widen its slot. Relation member ids are local to the
relation's resolved point.

| Source | Field | Target |
|--------|-------|--------|
| `variation_points` | parameter target variable | `variables` |
| `variation_points` | reference/collection/timing target owner | slot-declared owner section |
| `variation_points` | governed allowed refs and alternative/subset/order member refs | slot-declared candidate section |
| `variation_points` | requires/excludes point | `variation_points` |
| `variation_points` | requires/excludes members | members of the resolved point |
| `variation_points` | precedence/fixed-position members | members of the owning order point |

## 6. Machine-checkable reference-edge index

This index gives every cross-section or cross-declaration authoring reference a
stable candidate-domain token. Registered node-runtime inventories and their
local child edges remain governed by the family index in
[`runtime-inventory.md`](runtime-inventory.md); relationship fields that cross
from a top-level section into those inventories are listed here. `targetable`
means the declaration index excluding `variables`, `evidence_requirements`,
`objectives`, and `workflows`; it is not a synonym for every named object.
`declared`, `derived:*`, `runtime:*`, `vocabulary:*`, `registry:*`, `contract:*`,
and `opaque:*` name deliberately distinct resolution mechanisms and **MUST NOT**
be collapsed into a generic symbol lookup.

"Normative owner" points only to language-neutral prose or an accepted ADR.
"Implementation evidence" points to the independently maintained reference
implementation check. An implementation link is evidence of conformance, never
the source of the row's normative meaning.

| Source path | Candidate domain | Resolution phase | Failure | Normative owner | Implementation evidence |
| --- | --- | --- | --- | --- | --- |
| `nodes.*.features[]` | `features` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [node validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `nodes.*.features.*` | `derived:node_roles` | semantic validation | fatal dangling role when non-empty | [reference rules](#5-cross-section-reference-edge-catalog) | [node validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `nodes.*.conditions[]` | `conditions` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [node validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `nodes.*.conditions.*` | `derived:node_roles` | semantic validation | fatal dangling role when non-empty | [reference rules](#5-cross-section-reference-edge-catalog) | [node validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `conditions.*.proposition` | `propositions` | semantic validation | fatal dangling or ambiguous when present | [proposition semantics](../formal/objectives/proposition-and-assertion-semantics.md) | [proposition validator](../../implementations/python/packages/raes/validator/_propositions.py) |
| `propositions.*.subjects[]` | `targetable` | semantic validation | fatal dangling or ambiguous | [proposition semantics](../formal/objectives/proposition-and-assertion-semantics.md) | [proposition validator](../../implementations/python/packages/raes/validator/_propositions.py) |
| `propositions.*.evidence_requirements[]` | `evidence_requirements` | semantic validation | fatal dangling or ambiguous | [proposition semantics](../formal/objectives/proposition-and-assertion-semantics.md) | [proposition validator](../../implementations/python/packages/raes/validator/_propositions.py) |
| `assertions.*.proposition` | `propositions` | semantic validation | fatal dangling or ambiguous | [proposition semantics](../formal/objectives/proposition-and-assertion-semantics.md) | [proposition validator](../../implementations/python/packages/raes/validator/_propositions.py) |
| `nodes.*.injects[]` | `injects` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [node validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `nodes.*.injects.*` | `derived:node_roles` | semantic validation | fatal dangling role when non-empty | [reference rules](#5-cross-section-reference-edge-catalog) | [node validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `nodes.*.roles.*.entities[]` | `entities` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [section validator](../../implementations/python/packages/raes/validator/_sections.py) |
| `infrastructure.*.$key` | `nodes` | semantic validation | fatal when no same-named node exists | [reference rules](#5-cross-section-reference-edge-catalog) | [infrastructure validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `infrastructure.*.links[]` | `infrastructure` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [infrastructure validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `infrastructure.*.properties[].*` | `infrastructure` | semantic validation | fatal unless the key names a linked switch-backed entry | [reference rules](#5-cross-section-reference-edge-catalog) | [infrastructure validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `infrastructure.*.acls[].from_net` | `infrastructure` | semantic validation | fatal unless the target is switch-backed | [reference rules](#5-cross-section-reference-edge-catalog) | [infrastructure validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `infrastructure.*.acls[].to_net` | `infrastructure` | semantic validation | fatal unless the target is switch-backed | [reference rules](#5-cross-section-reference-edge-catalog) | [infrastructure validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `infrastructure.*.dependencies[]` | `infrastructure` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [infrastructure validator](../../implementations/python/packages/raes/validator/_nodes_infra_network.py) |
| `features.*.dependencies[]` | `features` | semantic validation | fatal dangling, ambiguous, or cyclic | [reference rules](#5-cross-section-reference-edge-catalog) | [section validator](../../implementations/python/packages/raes/validator/_sections.py) |
| `entities.*.events[]` | `events` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [section validator](../../implementations/python/packages/raes/validator/_sections.py) |
| `injects.*.from_entity` | `entities` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [section validator](../../implementations/python/packages/raes/validator/_sections.py) |
| `injects.*.to_entities[]` | `entities` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [section validator](../../implementations/python/packages/raes/validator/_sections.py) |
| `events.*.assertions[]` | `assertions` | semantic validation | fatal dangling, ambiguous, or non-precondition role | [proposition semantics](../formal/objectives/proposition-and-assertion-semantics.md) | [proposition validator](../../implementations/python/packages/raes/validator/_propositions.py) |
| `events.*.injects[]` | `injects` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [section validator](../../implementations/python/packages/raes/validator/_sections.py) |
| `scripts.*.events[]` | `events` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [section validator](../../implementations/python/packages/raes/validator/_sections.py) |
| `stories.*.scripts[]` | `scripts` | semantic validation | fatal dangling or ambiguous | [reference rules](#5-cross-section-reference-edge-catalog) | [section validator](../../implementations/python/packages/raes/validator/_sections.py) |
| `content.*.target` | `nodes` | semantic validation | fatal unless target is a compute node | [initial service state](initial-service-state.md) | [content validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `content.*.service_materialization.target_service_ref` | `derived:node_services` | semantic validation | fatal unless the exact service exists on the content target compute node | [initial service state](initial-service-state.md) | [service materialization validator](../../implementations/python/packages/raes/validator/_service_materialization.py) |
| `content.*.service_materialization.shared_service_relationship_ref` | `relationships` | semantic validation | fatal unless a matching typed shared-service relationship owns cross-tenant mutable state/reset | [initial service state](initial-service-state.md) | [service materialization validator](../../implementations/python/packages/raes/validator/_service_materialization.py) |
| `content.*.service_materialization.ordering_content_refs[]` | `content` | semantic validation and planner ordering | fatal dangling, self, or cyclic dependency | [initial service state](initial-service-state.md) | [content compiler](../../implementations/python/packages/raes_processor/compiler/placement.py) |
| `content.*.service_materialization.readback_assertion_refs[]` | `assertions` | semantic validation | fatal unless each ref is an observed-state postcondition | [initial service state](initial-service-state.md) | [service materialization validator](../../implementations/python/packages/raes/validator/_service_materialization.py) |
| `content.*.service_materialization.evidence_requirement_refs[]` | `evidence_requirements` | semantic validation | fatal unless each ref exists and every readback proposition requires it | [initial service state](initial-service-state.md) | [service materialization validator](../../implementations/python/packages/raes/validator/_service_materialization.py) |
| `content.*.service_materialization.observation_boundary_refs[]` | `observation_boundaries` | semantic validation | fatal dangling ref | [initial service state](initial-service-state.md) | [service materialization validator](../../implementations/python/packages/raes/validator/_service_materialization.py) |
| `generated_artifacts.*.consumers[].node` | `nodes` | structural model validation | fatal dangling or ambiguous | [stateful resources](stateful-resources.md) | [scenario model](../../implementations/python/packages/raes/scenario.py) |
| `generated_artifacts.*.ordering_dependencies[]` | `generated_artifacts,persistent_volumes` | structural model and planner graph validation | fatal dangling, ambiguous, or cyclic | [stateful resources](stateful-resources.md) | [scenario model](../../implementations/python/packages/raes/scenario.py) |
| `generated_artifacts.*.refresh_dependencies[]` | `generated_artifacts,persistent_volumes` | structural model validation | fatal dangling or ambiguous | [stateful resources](stateful-resources.md) | [scenario model](../../implementations/python/packages/raes/scenario.py) |
| `persistent_volumes.*.consumers[].node` | `nodes` | structural model validation | fatal dangling or ambiguous | [stateful resources](stateful-resources.md) | [scenario model](../../implementations/python/packages/raes/scenario.py) |
| `persistent_volumes.*.ordering_dependencies[]` | `generated_artifacts,persistent_volumes` | structural model and planner graph validation | fatal dangling, ambiguous, or cyclic | [stateful resources](stateful-resources.md) | [scenario model](../../implementations/python/packages/raes/scenario.py) |
| `persistent_volumes.*.refresh_dependencies[]` | `generated_artifacts,persistent_volumes` | structural model validation | fatal dangling or ambiguous | [stateful resources](stateful-resources.md) | [scenario model](../../implementations/python/packages/raes/scenario.py) |
| `accounts.*.domain_ref` | `identity_domains` | semantic validation | fatal dangling, ambiguous, or inconsistent topology | [authored domain topology](authored-domain-topology.md) | [domain topology semantics](../../implementations/python/packages/raes/semantics/domain_topology.py) |
| `identity_domains.*.authority_account_ref` | `accounts` | semantic validation | fatal dangling, ambiguous, or authority outside domain controllers | [authored domain topology](authored-domain-topology.md) | [domain topology semantics](../../implementations/python/packages/raes/semantics/domain_topology.py) |
| `identity_forests.*.root_domain_ref` | `identity_domains` | semantic validation | fatal dangling or root outside declared membership | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) | [enterprise identity semantics](../../implementations/python/packages/raes/semantics/enterprise_identity.py) |
| `identity_forests.*.domain_refs[]` | `identity_domains` | semantic validation | fatal dangling, duplicate, or domain in multiple forests | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) | [enterprise identity semantics](../../implementations/python/packages/raes/semantics/enterprise_identity.py) |
| `identity_facades.*.service_ref` | `targetable` | semantic validation | fatal unless target is a named compute service | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) | [enterprise identity semantics](../../implementations/python/packages/raes/semantics/enterprise_identity.py) |
| `deployment_cells.*.tenant_ref` | `deployment_tenants` | semantic validation | fatal dangling or ambiguous | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) | [deployment tenancy semantics](../../implementations/python/packages/raes/semantics/deployment_tenancy.py) |
| `deployment_cells.*.node_refs[]` | `nodes` | semantic validation | fatal dangling, duplicate, or node in multiple cells | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) | [deployment tenancy semantics](../../implementations/python/packages/raes/semantics/deployment_tenancy.py) |
| `accounts.*.node` | `nodes` | semantic validation | fatal unless target is a compute node | [reference rules](#5-cross-section-reference-edge-catalog) | [account validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `relationships.*.source` | `targetable` | semantic validation | fatal dangling or ambiguous; subtype may narrow domain | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [relationship validator](../../implementations/python/packages/raes/validator/_relationships.py) |
| `relationships.*.target` | `targetable` | semantic validation | fatal dangling or ambiguous; subtype may narrow domain | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [relationship validator](../../implementations/python/packages/raes/validator/_relationships.py) |
| `relationships.*.database_access.role_ref` | `derived:database_roles` | semantic validation | fatal outside the target database service | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [relationship validator](../../implementations/python/packages/raes/validator/_relationships.py) |
| `relationships.*.mail_access.listener_ref` | `derived:mail_listeners` | semantic validation | fatal outside the target mail service | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [mail validator](../../implementations/python/packages/raes/validator/_runtime_mail.py) |
| `relationships.*.mail_access.mailbox_ref` | `derived:mailboxes` | semantic validation | fatal outside the target mail service | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [mail validator](../../implementations/python/packages/raes/validator/_runtime_mail.py) |
| `relationships.*.mail_access.domain_ref` | `derived:mail_domains` | semantic validation | fatal outside the target mail service | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [mail validator](../../implementations/python/packages/raes/validator/_runtime_mail.py) |
| `relationships.*.forwarding_edge.forwarder_ref` | `runtime:forwarding_agents` | semantic validation | fatal dangling or ambiguous across scenario and node scopes | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [relationship validator](../../implementations/python/packages/raes/validator/_relationships.py) |
| `relationships.*.service_integration.consumer_ref` | `runtime:platform_applications` | semantic validation | fatal dangling or ambiguous | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [relationship validator](../../implementations/python/packages/raes/validator/_relationships.py) |
| `relationships.*.service_integration.engine_ref` | `runtime:platform_applications` | semantic validation | fatal dangling or ambiguous | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [relationship validator](../../implementations/python/packages/raes/validator/_relationships.py) |
| `relationships.*.service_integration.auth_principal_ref` | `derived:engine_authorization_principals` | semantic validation | fatal outside the engine authorization scope | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [relationship validator](../../implementations/python/packages/raes/validator/_relationships.py) |
| `relationships.*.proxy_upstream.route_ref` | `derived:source_application_routes` | semantic validation | fatal outside the source application | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [proxy relationship validator](../../implementations/python/packages/raes/validator/_relationships_proxy.py) |
| `relationships.*.proxy_upstream.upstream_node_ref` | `nodes` | semantic validation | fatal dangling or ambiguous | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [proxy relationship validator](../../implementations/python/packages/raes/validator/_relationships_proxy.py) |
| `relationships.*.proxy_upstream.upstream_service_ref` | `derived:upstream_node_services` | semantic validation | fatal without a resolvable upstream node and service | [ADR-052](../../docs/decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) | [proxy relationship validator](../../implementations/python/packages/raes/validator/_relationships_proxy.py) |
| `relationships.*.domain_join.controller_refs[]` | `nodes` | semantic validation | fatal dangling, ambiguous, or controller outside target domain | [authored domain topology](authored-domain-topology.md) | [domain topology semantics](../../implementations/python/packages/raes/semantics/domain_topology.py) |
| `relationships.*.shared_service.mutable_state_refs[]` | `persistent_volumes` | semantic validation | fatal dangling or conflicting state ownership | [enterprise identity and deployment tenancy](enterprise-deployment-tenancy.md) | [deployment tenancy semantics](../../implementations/python/packages/raes/semantics/deployment_tenancy.py) |
| `agents.*.entity` | `entities` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `agents.*.actions[]` | `action_contracts` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `agents.*.starting_accounts[]` | `accounts` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `agents.*.interactive_access.*.target_ref` | `nodes` | semantic validation | fatal dangling, ambiguous, or non-compute target | [participant semantics](../formal/participant-semantics/README.md) | [participant interactive-access semantics](../../implementations/python/packages/raes/semantics/participant_interactive_access.py) |
| `agents.*.interactive_access.*.account_ref` | `accounts` | semantic validation | fatal dangling, same-node mismatch, or outside participant starting accounts | [participant semantics](../formal/participant-semantics/README.md) | [participant interactive-access semantics](../../implementations/python/packages/raes/semantics/participant_interactive_access.py) |
| `agents.*.starting_assertions[]` | `assertions` | semantic validation | fatal dangling, ambiguous, or non-precondition role | [participant semantics](../formal/participant-semantics/README.md) | [proposition validator](../../implementations/python/packages/raes/validator/_propositions.py) |
| `agents.*.initial_knowledge.hosts[]` | `nodes` | semantic validation | fatal unless the target is a compute node | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `agents.*.initial_knowledge.subnets[]` | `infrastructure` | semantic validation | fatal unless the target is switch-backed | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `agents.*.initial_knowledge.services[]` | `derived:node_services` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `agents.*.initial_knowledge.accounts[]` | `accounts` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `agents.*.allowed_subnets[]` | `infrastructure` | semantic validation | fatal unless the target is switch-backed | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `agents.*.authority_anchors[]` | `declared` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `agents.*.operating_scope[]` | `derived:operating_scope` | semantic validation | fatal dangling or ambiguous outside compute nodes, switch-backed infrastructure, services, and content | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `agents.*.observation_boundaries[]` | `observation_boundaries` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `action_contracts.*.interactions.*.related_actions[]` | `action_contracts` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `action_contracts.*.interactions.*.target` | `targetable` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `action_contracts.*.interactions.*.shared_state_refs[]` | `targetable` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `action_contracts.*.temporal_contracts.*.backend_disclosure_refs[]` | `derived:backend_timing_disclosures` | structural validation | fatal dangling local disclosure id | [participant semantics](../formal/participant-semantics/README.md) | [temporal model](../../implementations/python/packages/raes/participant_temporal_semantics.py) |
| `action_contracts.*.backend_timing_disclosures.*.affected_temporal_ids[]` | `derived:temporal_contracts` | structural validation | fatal dangling local temporal id | [participant semantics](../formal/participant-semantics/README.md) | [temporal model](../../implementations/python/packages/raes/participant_temporal_semantics.py) |
| `observation_boundaries.*.view_rules.*.information_ref` | `derived:boundary_information` | semantic validation | fatal outside declared boundary information | [participant semantics](../formal/participant-semantics/README.md) | [participant semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `observation_boundaries.*.view_rules.*.evidence_refs[]` | `derived:boundary_evidence` | semantic validation | fatal outside declared boundary evidence | [participant semantics](../formal/participant-semantics/README.md) | [participant semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `observation_boundaries.*.view_transitions.*.information_ref` | `derived:boundary_view_rules` | semantic validation | fatal without a matching view rule | [participant semantics](../formal/participant-semantics/README.md) | [participant semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `observation_boundaries.*.view_transitions.*.evidence_refs[]` | `derived:boundary_evidence` | semantic validation | fatal outside declared boundary evidence | [participant semantics](../formal/participant-semantics/README.md) | [participant semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `outcome_interpretation_rules.*.source_bindings.*.ref` | `action_contracts,objectives,workflows` | semantic validation | fatal dangling for SDL-bound layers | [participant semantics](../formal/participant-semantics/README.md) | [outcome semantics](../../implementations/python/packages/raes/semantics/participant_outcome.py) |
| `outcome_interpretation_rules.*.target_bindings.*.ref` | `objectives,workflows` | semantic validation | fatal dangling for SDL-bound layers | [participant semantics](../formal/participant-semantics/README.md) | [outcome semantics](../../implementations/python/packages/raes/semantics/participant_outcome.py) |
| `behavior_specifications.*.participant_refs[]` | `agents` | semantic validation | fatal dangling or ambiguous | [behavior model](../formal/participant-behavior-model/README.md) | [behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `behavior_specifications.*.participant_role_refs[]` | `derived:agent_roles` | semantic validation | fatal unless bound by a referenced participant | [behavior model](../formal/participant-behavior-model/README.md) | [behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `behavior_specifications.*.action_contract_refs[]` | `action_contracts` | semantic validation | fatal dangling or ambiguous | [behavior model](../formal/participant-behavior-model/README.md) | [behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `behavior_specifications.*.observation_boundary_refs[]` | `observation_boundaries` | semantic validation | fatal dangling or ambiguous | [behavior model](../formal/participant-behavior-model/README.md) | [behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `behavior_specifications.*.outcome_interpretation_rule_refs[]` | `outcome_interpretation_rules` | semantic validation | fatal dangling or ambiguous | [behavior model](../formal/participant-behavior-model/README.md) | [behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `behavior_specifications.*.authority_scope_refs[]` | `targetable` | semantic validation | fatal dangling or ambiguous | [behavior model](../formal/participant-behavior-model/README.md) | [behavior validator](../../implementations/python/packages/raes/validator/_content_objectives.py) |
| `behavior_specifications.*.tool_affordances.*.tool_ref` | `content` | semantic validation | fatal dangling, ambiguous, or outside the `scenario-content` tools-and-artifacts reference model | [participant semantics](../formal/participant-semantics/README.md) | [tool-affordance validator](../../implementations/python/packages/raes/validator/_participant_tool_affordances.py) |
| `behavior_specifications.*.tool_affordances.*.action_contract_refs[]` | `action_contracts` | semantic validation | fatal dangling, outside the owning behavior specification, or outside a resolved participant | [participant semantics](../formal/participant-semantics/README.md) | [behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `behavior_specifications.*.tool_affordances.*.observation_boundary_refs[]` | `observation_boundaries` | semantic validation | fatal dangling, outside the owner/participant, or without explicit view classification | [participant semantics](../formal/participant-semantics/README.md) | [behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.participant_ref` | `agents` | semantic validation | fatal dangling or outside the owning behavior specification | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.inject_ref` | `injects` | semantic validation | fatal dangling or outside the anchored event occurrence | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.occurrence.event_ref` | `events` | semantic validation | fatal dangling or not containing the bound inject | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.occurrence.script_ref` | `scripts` | semantic validation | fatal dangling or not containing the anchored event | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.occurrence.story_ref` | `stories` | semantic validation | fatal dangling or not containing the anchored script | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.source_item_ref` | `targetable` | semantic validation | fatal dangling or ambiguous | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.result_item_ref` | `targetable` | semantic validation | fatal dangling, ambiguous, hidden, or unclassified at the participant boundary | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.observation_boundary_ref` | `observation_boundaries` | semantic validation | fatal dangling or outside the owner/participant | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.temporal_constraint_refs[]` | `temporal_constraints` | semantic validation | fatal dangling or not binding this delivery declaration | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.evidence_requirement_refs[]` | `evidence_requirements` | semantic validation | fatal dangling or not binding this delivery declaration | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.control_transition_ref` | `derived:mixed_control_local_ids` | structural and semantic validation | fatal dangling, wrong-kind, or incomplete control agreement | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.controller_ref` | `agents` | semantic validation | fatal disagreement with the selected control-transition target controller | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.control_authority_scope_refs[]` | `targetable` | semantic validation | fatal dangling, ambiguous, or disagreement with the selected target-state scope | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.participant_inject_deliveries.*.control_evidence_refs[]` | `targetable` | semantic validation | fatal dangling, control disagreement, or absent evidence-requirement coverage | [participant semantics](../formal/participant-semantics/README.md) | [participant-inject delivery validator](../../implementations/python/packages/raes/validator/_participant_inject_deliveries.py) |
| `behavior_specifications.*.behavior_mode` | `vocabulary:behavior_mode` | structural validation | fatal invalid vocabulary value | [behavior model](../formal/participant-behavior-model/README.md) | [behavior model](../../implementations/python/packages/raes/participant_behavior/__init__.py) |
| `behavior_specifications.*.mixed_control.participant_ref` | `agents` | semantic validation | fatal unless owned by the enclosing behavior specification | [behavior model](../formal/participant-behavior-model/README.md) | [behavior validator](../../implementations/python/packages/raes/validator/_mixed_control.py) |
| `behavior_specifications.*.mixed_control.controller_states.*.controller_ref` | `agents-or-self` | semantic validation | fatal operator/role/identity impersonation or dangling agent | [behavior model](../formal/participant-behavior-model/README.md) | [behavior validator](../../implementations/python/packages/raes/validator/_mixed_control.py) |
| `behavior_specifications.*.mixed_control.controller_states.*.authority_basis_refs[]` | `derived:controller_authority_anchors` | semantic validation | fatal dangling, ambiguous, or authority widening | [behavior model](../formal/participant-behavior-model/README.md) | [behavior validator](../../implementations/python/packages/raes/validator/_mixed_control.py) |
| `clocks.*.time_domain_ref` | `time_domains` | semantic validation | fatal dangling | [shared time model](../formal/time-model/README.md) | [time-model validator](../../implementations/python/packages/raes/validator/_time_model.py) |
| `time_domain_mappings.*.source_domain_ref` | `time_domains` | semantic validation | fatal dangling, duplicate, or cyclic mapping | [shared time model](../formal/time-model/README.md) | [time-model validator](../../implementations/python/packages/raes/validator/_time_model.py) |
| `time_domain_mappings.*.target_domain_ref` | `time_domains` | semantic validation | fatal dangling, duplicate, or cyclic mapping | [shared time model](../formal/time-model/README.md) | [time-model validator](../../implementations/python/packages/raes/validator/_time_model.py) |
| `time_progression_policies.*.clock_ref` | `clocks` | semantic validation | fatal dangling or incompatible reset/replay lifecycle | [shared time model](../formal/time-model/README.md) | [time-model validator](../../implementations/python/packages/raes/validator/_time_model.py) |
| `temporal_constraints.*.clock_ref` | `clocks` | semantic validation | fatal dangling | [shared time model](../formal/time-model/README.md) | [time-model validator](../../implementations/python/packages/raes/validator/_time_model.py) |
| `temporal_constraints.*.subject_refs[]` | `targetable` | semantic validation | fatal dangling or ambiguous | [shared time model](../formal/time-model/README.md) | [time-model validator](../../implementations/python/packages/raes/validator/_time_model.py) |
| `behavior_specifications.*.mixed_control.controller_states.*.scope_refs[]` | `derived:behavior-and-controller-scope` | semantic validation | fatal dangling, ambiguous, or scope widening | [behavior model](../formal/participant-behavior-model/README.md) | [behavior validator](../../implementations/python/packages/raes/validator/_mixed_control.py) |
| `behavior_specifications.*.mixed_control.controller_states.*.evidence_refs[]` | `declared` | semantic validation | fatal dangling or ambiguous | [behavior model](../formal/participant-behavior-model/README.md) | [behavior validator](../../implementations/python/packages/raes/validator/_mixed_control.py) |
| `behavior_specifications.*.mixed_control.transitions.*.from_state_ref` | `derived:mixed_control_local_ids` | structural and semantic validation | fatal dangling, stale, reversed, or ambiguously ordered local ref | [behavior model](../formal/participant-behavior-model/README.md) | [behavior model](../../implementations/python/packages/raes/participant_behavior_specification.py) |
| `behavior_specifications.*.mixed_control.transitions.*.to_state_ref` | `derived:mixed_control_local_ids` | structural and semantic validation | fatal dangling, stale, reversed, or ambiguously ordered local ref | [behavior model](../formal/participant-behavior-model/README.md) | [behavior model](../../implementations/python/packages/raes/participant_behavior_specification.py) |
| `behavior_specifications.*.mixed_control.transitions.*.proposal_ref` | `derived:mixed_control_local_ids` | structural and semantic validation | fatal dangling, stale, reversed, or ambiguously ordered local ref | [behavior model](../formal/participant-behavior-model/README.md) | [behavior model](../../implementations/python/packages/raes/participant_behavior_specification.py) |
| `behavior_specifications.*.mixed_control.transitions.*.evidence_refs[]` | `declared` | semantic validation | fatal dangling, ambiguous, or silent handoff | [behavior model](../formal/participant-behavior-model/README.md) | [behavior validator](../../implementations/python/packages/raes/validator/_mixed_control.py) |
| `behavior_specifications.*.mixed_control.transitions.*.completion_evidence_refs[]` | `declared` | semantic validation | fatal dangling, ambiguous, or silent handoff | [behavior model](../formal/participant-behavior-model/README.md) | [behavior validator](../../implementations/python/packages/raes/validator/_mixed_control.py) |
| `behavior_specifications.*.realization_profile_ref` | `opaque:realization_profile` | structural validation | fatal invalid reference shape; resolution belongs to realization | [behavior model](../formal/participant-behavior-model/README.md) | [behavior model](../../implementations/python/packages/raes/participant_behavior/__init__.py) |
| `behavior_specifications.*.backend_feature_support_refs[]` | `registry:behavior_features` | semantic validation | fatal unsupported feature identifier | [behavior model](../formal/participant-behavior-model/README.md) | [behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `behavior_specifications.*.evidence_contract_refs[]` | `contract:participant_evidence` | semantic validation | fatal unknown contract identifier | [behavior model](../formal/participant-behavior-model/README.md) | [behavior semantics](../../implementations/python/packages/raes/semantics/participant_behavior/__init__.py) |
| `evidence_requirements.*.source_refs[]` | `targetable` | semantic validation | fatal dangling or ambiguous | [evidence authoring](observability-and-evidence.md) | [evidence validator](../../implementations/python/packages/raes/validator/_evidence_requirements.py) |
| `evidence_requirements.*.scope_refs[]` | `targetable` | semantic validation | fatal dangling or ambiguous | [evidence authoring](observability-and-evidence.md) | [evidence validator](../../implementations/python/packages/raes/validator/_evidence_requirements.py) |
| `evidence_requirements.*.channel_refs[]` | `targetable` | semantic validation | fatal dangling or ambiguous | [evidence authoring](observability-and-evidence.md) | [evidence validator](../../implementations/python/packages/raes/validator/_evidence_requirements.py) |
| `evidence_requirements.*.trigger_ref` | `targetable` | semantic validation | fatal dangling or ambiguous | [evidence authoring](observability-and-evidence.md) | [evidence validator](../../implementations/python/packages/raes/validator/_evidence_requirements.py) |
| `evidence_requirements.*.boundary_ref` | `targetable` | semantic validation | fatal dangling or ambiguous | [evidence authoring](observability-and-evidence.md) | [evidence validator](../../implementations/python/packages/raes/validator/_evidence_requirements.py) |
| `variation_points.*.target.variable` | `variables` | semantic validation | fatal dangling or wrong variable type | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.target.owner` | `targetable` | semantic validation | fatal dangling or wrong slot owner type | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.domain.allowed_refs[]` | `targetable` | semantic validation | fatal dangling or wrong slot candidate type | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.alternatives.*.reference` | `targetable` | semantic validation | fatal dangling or wrong slot candidate type | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.members.*.reference` | `targetable` | semantic validation | fatal dangling or wrong slot candidate type | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.alternatives.*.requires[].point` | `variation_points` | semantic validation | fatal dangling or ambiguous | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.alternatives.*.requires[].members[]` | `derived:variation_members` | semantic validation | fatal outside the resolved variation point | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.alternatives.*.excludes[].point` | `variation_points` | semantic validation | fatal dangling or ambiguous | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.alternatives.*.excludes[].members[]` | `derived:variation_members` | semantic validation | fatal outside the resolved variation point | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.members.*.requires[].point` | `variation_points` | semantic validation | fatal dangling or ambiguous | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.members.*.requires[].members[]` | `derived:variation_members` | semantic validation | fatal outside the resolved variation point | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.members.*.excludes[].point` | `variation_points` | semantic validation | fatal dangling or ambiguous | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.members.*.excludes[].members[]` | `derived:variation_members` | semantic validation | fatal outside the resolved variation point | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.precedence[].before` | `derived:variation_members` | structural validation | fatal outside the owning order point | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.precedence[].after` | `derived:variation_members` | structural validation | fatal outside the owning order point | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `variation_points.*.fixed_positions.*.$key` | `derived:variation_members` | structural validation | fatal outside the owning order point | [variation points](variation-points.md) | [variation validator](../../implementations/python/packages/raes/validator/_variation.py) |
| `objectives.*.agent` | `agents` | semantic validation | fatal dangling or ambiguous | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.entity` | `entities` | semantic validation | fatal dangling or ambiguous | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.actions[]` | `derived:agent_actions` | semantic validation | fatal outside the bound agent action contracts | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.targets[]` | `targetable` | semantic validation | fatal dangling or ambiguous | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.success.assertions[]` | `assertions` | semantic validation | fatal dangling, ambiguous, or precondition role | [proposition semantics](../formal/objectives/proposition-and-assertion-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.depends_on[]` | `objectives` | semantic validation | fatal dangling, ambiguous, or cyclic | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.window.stories[]` | `stories` | semantic validation | fatal dangling or ambiguous | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.window.scripts[]` | `scripts` | semantic validation | fatal dangling or outside referenced stories | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.window.events[]` | `events` | semantic validation | fatal dangling or outside referenced scripts | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.window.workflows[]` | `workflows` | semantic validation | fatal dangling or ambiguous | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `objectives.*.window.steps[]` | `workflow_steps` | semantic validation | fatal malformed, dangling, or outside referenced workflows | [objective semantics](../formal/objectives/declarative-objective-semantics.md) | [objective semantics](../../implementations/python/packages/raes/semantics/objective_semantics/__init__.py) |
| `workflows.*.start` | `workflow_steps` | semantic validation | fatal dangling step | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.when.assertions[]` | `assertions` | semantic validation | fatal dangling, ambiguous, or non-precondition role | [proposition semantics](../formal/objectives/proposition-and-assertion-semantics.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.when.objectives[]` | `objectives` | semantic validation | fatal dangling or ambiguous | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.when.steps.*.step` | `workflow_steps` | semantic validation | fatal dangling, self-referential, non-executable, or unavailable before evaluation | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.cases.*.when.assertions[]` | `assertions` | semantic validation | fatal dangling, ambiguous, or non-precondition role | [proposition semantics](../formal/objectives/proposition-and-assertion-semantics.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.cases.*.when.objectives[]` | `objectives` | semantic validation | fatal dangling or ambiguous | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.cases.*.when.steps.*.step` | `workflow_steps` | semantic validation | fatal dangling, self-referential, non-executable, or unavailable before evaluation | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.objective` | `objectives` | semantic validation | fatal dangling or ambiguous | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.procedure_ref` | `action_contracts` | semantic validation | fatal dangling or non-procedure granularity | [goal-oriented step semantics](../formal/workflows/goal-oriented-steps.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.scaffold_refs[]` | `observation_boundaries` | semantic validation | fatal dangling or scaffold-incompatible boundary | [goal-oriented step semantics](../formal/workflows/goal-oriented-steps.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.allowed_action_families[]` | `action_contracts` | semantic validation | fatal dangling or non-aggregate granularity | [goal-oriented step semantics](../formal/workflows/goal-oriented-steps.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.next` | `workflow_steps` | semantic validation | fatal dangling, cyclic, or unreachable | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.on_success` | `workflow_steps` | semantic validation | fatal dangling, cyclic, or unreachable | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.on_failure` | `workflow_steps` | semantic validation | fatal dangling, cyclic, or unreachable | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.on_exhausted` | `workflow_steps` | semantic validation | fatal dangling, cyclic, or unreachable | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.then` | `workflow_steps` | semantic validation | fatal dangling, cyclic, or unreachable | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.else` | `workflow_steps` | semantic validation | fatal dangling, cyclic, or unreachable | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.cases.*.next` | `workflow_steps` | semantic validation | fatal dangling, cyclic, or unreachable | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.default` | `workflow_steps` | semantic validation | fatal dangling, cyclic, or unreachable | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.branches[]` | `workflow_steps` | semantic validation | fatal dangling or outside a closed parallel branch | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.join` | `workflow_steps` | semantic validation | fatal dangling, non-join, multiply owned, or outside branch closure | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.workflow` | `workflows` | semantic validation | fatal dangling or cyclic | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |
| `workflows.*.steps.*.compensate_with` | `workflows` | semantic validation | fatal dangling, cyclic, or invalid as a compensation target | [workflow semantics](../formal/workflows/state-machine.md) | [workflow validator](../../implementations/python/packages/raes/validator/_workflows_verify.py) |

The index is compared by exact source path, domain, phase, failure semantics,
and implementation evidence against the checked reference contract, and its
completion-aware subset is compared with language-service metadata. Adding,
removing, or renaming an edge on only one surface fails the repository contract
gate; a matching row count cannot hide a different edge.

## Extending the reference catalog

A new reference edge is added by defining the field's candidate set, adding a
row here, and enforcing it in the reference implementation and tests. New
runtime-family child refs follow the nested runtime-family form (§1.3)
automatically once registered in the family index
([runtime-inventory.md](runtime-inventory.md)); they do not need bespoke prose.
