# SDL Semantic Validation

The semantic validator (`raes.validator.SemanticValidator`) runs the
named semantic pass set after Pydantic structural validation. It collects all
errors rather than failing on the first, so authors see every issue at once.

Under the repository's [coding standards](../reference/coding-standards.md),
this layer is primarily an `FM1` and `FM2` surface. It is where static semantic
invariants such as cross-reference resolution, ambiguity, uniqueness,
reachability, and fail-closed graph constraints are enforced. Those invariants
must stay aligned with the runtime compiler and planner contracts rather than
becoming a validator-only interpretation of the SDL.

## Validation Passes

### OCR-Ancestry SDL Passes

These checks have translated algorithmic ancestry in OCR v0.21.2
`Scenario::formalize()` at revision
`fe83e8281fc4b954967fbaa5a0d099007ddcb06c`; current behavior is governed by
RAES validators and is not claimed compatible with the OCR implementation.

| Pass | What It Checks |
|------|----------------|
| `verify_nodes` | Features, conditions and injects referenced by nodes exist in their respective sections. Role names on feature/condition/inject assignments must match declared node `roles`. Node names ≤ 35 characters. |
| `verify_infrastructure` | Every infrastructure entry has a matching node. Links reference existing switch/network entries. Dependencies reference existing infrastructure entries. Switch nodes cannot have count > 1, and nodes with conditions cannot scale above 1. Complex property IPs must be valid IPs within the linked switch's CIDR. ACL `from_net` and `to_net` references are each checked and must resolve to switch/network entries. |
| `verify_features` | Dependency references exist. **Dependency cycle detection** via topological sort. |
| `verify_conditions` | (Structural: command+interval XOR source — enforced by Pydantic) |
| `verify_entities` | Event references on entities (including nested) exist. |
| `verify_injects` | from-entity and to-entities reference existing (possibly nested) entities. |
| `verify_events` | Condition and inject references exist. |
| `verify_scripts` | Event references exist. Event times within script start/end bounds. |
| `verify_stories` | Script references exist. |
| `verify_roles` | Entity references in node roles resolve to flattened entity names. |

The former scoring-pipeline passes (`verify_metrics`, `verify_evaluations`,
`verify_tlos`, `verify_goals`, and the internal `_verify_assessment_pipeline`
check) were removed with the `metrics`/`evaluations`/`tlos`/`goals` sections by
[ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md). There is
no longer a "references undefined metric/evaluation/TLO/goal" validation error;
`conditions` remain the observable-state surface objective success references.

### Extension passes

Historical classification fields are rejected at structural ingress with
`sdl.classification-migration-required`. External authored assertions use
standalone concept-binding admission, not native vulnerability or behavior
validation passes. See the [migration guide](../../migration/external-classifications.md).

| Pass | What It Checks |
|------|----------------|
| `verify_content` | Content targets reference existing compute nodes. |
| `verify_accounts` | Account nodes reference existing compute nodes. |
| `verify_relationships` | Source and target resolve to any named element in any section, including variables, relationships, content item names, named service bindings, runtime service listener refs, runtime identity-authority refs, runtime DNS refs, runtime network-sensor refs, runtime network detection-engine refs, runtime security-monitoring manager refs, and named ACL rules. Ambiguous bare refs are rejected with qualified alternatives. |
| `verify_relationship_forwarding_edges` | A relationship `forwarding_edge` resolves `forwarder_ref` to a unique node-hosted or scenario-level runtime forwarding agent; the edge `target_listener_role`/`protocol` must agree with at least one of that agent's ship targets. |
| `verify_relationship_service_integrations` | A relationship `service_integration` resolves `consumer_ref`/`engine_ref` to platform applications and `auth_principal_ref` to a principal in the engine application's referenced authorization store when `authorization_ref` is set. |
| `verify_relationship_proxy_upstreams` | A relationship `proxy_upstream` resolves `route_ref` to an application route and the upstream node/service refs; route-level `upstream_target` refs resolve the same way, and when both scopes carry shared target node, target service, and TLS-termination facts they must agree. |
| `verify_runtime_service_listeners` | Runtime service listeners resolve optional same-node service refs, process refs, and host-published port correlations. Concrete service/listener port+protocol values must match. |
| `verify_runtime_identity_authorities` | Runtime identity-authority services resolve to same-node service bindings. Local relationship and policy refs resolve within the owning authority across authority, service, subject, policy, and relationship stable ids. |
| `verify_runtime_dns_services` | Runtime DNS services resolve to same-node service bindings. Configuration, log, and zone-file refs resolve to observed runtime filesystem entries when the node has file inventory. |
| `verify_runtime_network_sensors` | Runtime network sensors name monitored networks that resolve to switch-backed infrastructure entries and, when runtime endpoint inventory exists on the node, to same-node network endpoint attachments. Configuration, log, and evidence refs resolve to observed runtime filesystem entries when the node has file inventory. |
| `verify_runtime_network_detection_engines` | Runtime network detection engines resolve optional same-node sensor refs, network-set refs, control-channel service refs, and filesystem-backed configuration/log/evidence/rule/output/control paths. |
| `verify_runtime_security_monitoring_managers` | Runtime security-monitoring managers and listeners resolve to same-node service bindings. Manager/group/content/detection/setting file refs resolve to observed runtime filesystem entries when the node has file inventory. Agent group member refs, agent group refs, setting component refs, detection content-set refs, and detection correlation refs resolve inside the owning manager. Detection source artifact refs and target refs resolve through the generic named-ref index. |
| `verify_runtime_app_authorizations` | Runtime application-internal RBAC stores resolve `permission_grants` and `role_mappings` `role_ref` values to roles declared within the same authorization (authorization-local role-permission and user-role assignment integrity). |
| `verify_runtime_datastore_services` | Runtime datastore services resolve their owning transport `service` to a same-node service binding, and a non-empty, non-variable `authorization_ref` to an `app_authorization` declared on the same node. The model-local `require_profile_for_data_model` guard fails an under-populated `search_index`/`wide_column`/`key_value` instance. |
| `verify_runtime_platform_applications` | Runtime platform applications resolve their owning transport `service` to a same-node service binding, a non-empty, non-variable `authorization_ref` to a same-node `app_authorization`, legacy content-object `references` to sibling `content_object_id` values, and `marking_refs` to sibling `marking_id` values. Provider-neutral capabilities are independently declared, carry stable application-local ids, and may be targeted by qualified refs; neither the deprecated `platform_kind` nor legacy content presence implies a capability or configuration completeness. |
| `verify_runtime_forwarding_agents` | Runtime forwarding agents resolve each `ship_target`'s `target_node_ref`, when concrete, to a defined node, and a concrete `target_service_ref` to a service on the referenced node (or, for node-hosted agents only, on the owning node). Scenario-level forwarding agents require `target_node_ref` when `target_service_ref` is concrete, and `forwarding_agent_id` values are unique across node-hosted and scenario-level registries. The model-local `require_profile_for_agent_kind` guard fails an under-populated `log_forwarder` (requires a `buffer_policy` plus an ingestion `ship_target`, rejects `ioc_to_rule` transforms) or `content_sync` (requires an `api_pull` source, an `ioc_to_rule` transform, and a `reload_channel`, rejects a `buffer_policy` and `ship_target` enrollment endpoints) instance. |
| `verify_runtime_orchestration_authorities` | Runtime orchestration authorities resolve a non-empty, non-variable `control_interface_ref` to a `RuntimeControlInterface` declared in the same node's `runtime.local_control_interfaces` (by `control_interface_id`); for a `host_root_equivalent` privilege class the referenced interface must additionally be a read-write docker socket (access `read_write`, kind `unix_socket`, path ending in `docker.sock`), with `${var}` interface access/kind/path permissive. The model-local `require_profile_for_privilege_class` guard fails a `host_root_equivalent` authority that carries no concrete `control_interface_ref`. |
| `verify_runtime_mail_services` | Runtime mail services and listeners resolve optional same-node `Node.services` refs. Listener component refs, mailbox domain/store refs, alias target refs, routing source/target refs, and setting component refs resolve inside the owning mail service. Mailbox account refs resolve to top-level accounts, local-user refs resolve to `runtime.local_identity` when present, and setting source paths resolve to observed runtime filesystem entries when the node has file inventory. |
| `verify_relationship_mail_access` | A relationship with `mail_access` must target a runtime mail service. Concrete `listener_ref`, `mailbox_ref`, and `domain_ref` values resolve within that target service, while protocol, auth-mechanism, and TLS-mode fields are structurally normalized by the `RelationshipMailAccess` model. |
| `verify_agents` | Entity references resolve. Starting accounts and initial-knowledge accounts exist in accounts section. Allowed subnets and initial-knowledge subnets must resolve to switch-backed infrastructure entries. Initial-knowledge hosts must resolve to compute nodes. Initial-knowledge services exist in `nodes.*.services[].name`. Interactive-access targets resolve to compute nodes; optional accounts resolve to the same compute node and participant starting accounts; concrete target/channel pairs are unique per participant. |
| `verify_participant_behavior` | Agent action refs resolve to declared action contracts, observation-boundary refs resolve to declared boundaries, interaction refs resolve to declared actions or targetable state, and boundary view rules/transitions resolve to declared observable, hidden, or evidence refs. |
| `verify_objectives` | Objective actors resolve (`agent` or `entity`). Objective actions must be declared by the referenced agent. Targets resolve to named scenario elements, including qualified service/ACL refs and section-qualified top-level refs. Ambiguous bare refs are rejected with qualified alternatives. Success criteria resolve to declared `conditions` (observable state only, per [ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md)). Optional windows resolve through one shared normalized analysis over stories/scripts/events/workflows/workflow-steps, must remain internally consistent, and fail closed on dangling or out-of-window refs. Objective dependencies must resolve and stay acyclic. |
| `verify_workflows` | Workflow `start` and every referenced step must exist. `objective`/`retry` steps must reference declared objectives. Predicate refs must resolve to declared `conditions`/`objectives` (the scoring surfaces were removed per [ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md)), and step-state refs must resolve to prior executable steps whose state is guaranteed to be known before the predicate runs. Workflow graphs must be acyclic and fully reachable from `start`. Parallel joins must be explicit barriers, every explicit branch path must converge on the declared join, branch-local state remains scoped until the join, and post-join predicates may inspect only branch steps guaranteed on every path within their branch before the join. |
| `verify_participant_outcomes` | Outcome interpretation source and target refs resolve for action contracts, objectives, and workflows. The SEM-215 `reward_signal` / `evaluation_result` interpretation layers remain a governed interpretation relation but no longer bind to any SDL `evaluations` section ([ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md)); runtime conformance grounds emitted interpretation records in action results, event evidence, and participant episode history. |
| `verify_variables` | Checks that full-value `${var}` placeholders and embedded `${var}` tokens reference declared variables. Structural validation of variable declaration names, typed defaults, and `allowed_values` still happens in the model/schema layer. |

Pydantic structural validation also enforces model-local node rules before
these semantic passes run. Switch nodes reject compute-only fields, including
`runtime`. Runtime mount, dependency-manifest, and software-component manifest
paths must be absolute paths or variable references. Runtime software-component
`installed_paths`, filesystem inventory paths, container masked paths,
container read-only paths, and device host/container paths must also be
absolute runtime paths or variable references. Runtime local-control interface
paths and bind sources must be absolute paths, Windows named pipe endpoints, or
variable references; Windows named pipe endpoints require `kind: named_pipe`.
Runtime software components must have stable, concrete `component_id` values
that are unique within the node runtime block.
Runtime filesystem inventory UID/GID and size fields are non-negative, mode is
stored as octal permission bits, and content digests must carry both the digest
algorithm and value. Runtime mount sources/options and local-control bind sources
classified as `redacted` or `operator_secret` must omit the corresponding raw
value; the Python models and generated JSON Schemas both reject non-empty raw
values for redacted/operator-secret labels accepted by the value-normalization
rules, including case-insensitive hyphen/underscore enum spellings. Structural
field keys themselves use exact `snake_case` under `sdl-yaml/v1`.
Runtime observed-value surfaces share the ADR-056/ADR-057 raw-value helper:
redacted and operator-secret classifications omit raw values. ADR-057 supersedes
the earlier name-driven omission rule: credential-shaped names do not by
themselves reject values or require redaction, because SDL runtime values are
scenario-realization facts.
[ADR-057](../../decisions/adrs/adr-057-runtime-secret-name-classifier-boundaries.md)
records the realizability decision: generated credentials, hashes, key
material, weak fixture values, public-key fingerprints, working-directory
variables such as `PWD`, and scalar metadata such as `secret_key_length` may all
be recorded when they are facts of the synthetic scenario. Authors still
classify any value as `redacted` or `operator_secret` when the value is
intentionally withheld from the authoritative SDL.

The optional `runtime.local_identity` inventory carries its own model-local
rules. Local user `username` and local group `name` must be non-empty; user
`uid`/`primary_gid` and group `gid` are non-negative; user `home` and `shell`,
when set, must be absolute paths or variable references. Local users are unique
by `username`, local groups are unique by both `name` and `gid`, and sudo rules
are unique by principal plus command scope. A sudo rule with
`command_redacted: true` must omit its `commands` list, keeping a withheld
command scope distinct from a genuinely empty one.

The optional `runtime.identity_authorities` inventory also has model-local and
semantic rules. Authorities, services, subjects, policies, relationships,
attributes, and settings use stable non-empty ids or names. Stable ids must be
unique across the authority-local reference namespace, not just within each
child collection. The model also rejects duplicate attribute and setting names,
normalizes bounded kind/protocol/provenance/value classifications, and enforces
explicit redaction classifications on attributes and settings. Authority
services may reference only services declared on the same node. Authority-local refs resolve
against all stable ids in the authority:
`identity_authority_id`, `service_id`, `subject_id`, `policy_id`, and
`relationship_id`. Provider names and external object identifiers are data, not
reference keys.

The optional `runtime.dns_services` inventory has model-local and semantic
rules. DNS services, zones, and RRsets use stable ids, while observed DNS names
remain data and are not case-folded. DNS service ids are unique within a node
runtime block; zone ids are unique within a DNS service; RRset ids and
owner/class/type bindings are unique within a zone. RRsets must have at least
one record, TTL and type-code fields are bounded integer-or-variable values,
`record_type: other` requires `type_code`, and typed RDATA must match the
owning RRset type. A/AAAA typed address payloads are validated as IPv4/IPv6
respectively. DNS settings such as TSIG, RNDC, password, token, or private-key
settings may carry scenario values unless explicitly classified as
redacted/operator-secret. DNS services may reference only services declared on
the same node. File refs under the DNS service and its zones are checked against
`runtime.filesystem_inventory` when that inventory is non-empty.

The optional `runtime.network_sensors` inventory has model-local and semantic
rules. Network sensors use stable `network_sensor_id` values that are unique within the
node runtime block. Implementations, sensor kinds, monitoring postures, and
capture modes are normalized from bounded enums while allowing full-value
variables where the model permits. `capture_interfaces` and
`monitored_network_refs` reject duplicates. Each monitored network ref must
resolve to a declared switch-backed infrastructure entry; when the same node
records `runtime.network.endpoints`, the monitored network must also be one of
that node's observed endpoint attachments. Configuration, log, and evidence
refs are absolute paths and are checked against `runtime.filesystem_inventory`
when that inventory is non-empty.

The optional `runtime.service_listeners` inventory has model-local and
semantic rules. Listener ids are stable concrete symbols and are unique within
a node runtime block. Network listeners require a port and a bind address or
interface; Unix socket listeners require `socket_path` and must not set a port
or address. Concrete address-family and scope fields must not contradict the
bind endpoint: wildcard addresses use `scope: wildcard`, loopback addresses
cannot be `network_facing`, non-loopback IP addresses cannot be
`loopback_only`, and Unix socket listeners use `local_socket` or `unknown`.
Optional same-node `service` refs must resolve to `Node.services[].name`, and
concrete listener port/protocol values must match the service. Optional
`process_ref` values resolve to `runtime.process` or `runtime.processes` by
process name or PID. Optional `published_port_refs` entries resolve to
`runtime.network.published_ports` by host IP, host port, container port, and
protocol and must match the listener's container-side port/protocol.

The optional `runtime.mail_services` inventory has model-local and semantic
rules. Mail-service ids are stable concrete symbols and unique within a node
runtime block; service-local component, listener, domain, mailbox-store,
mailbox, alias, routing-rule, queue, and setting ids are unique within their
collections and across the service-local reference namespace. Mail protocols,
listener roles, AUTH mechanisms, TLS modes, domain/mailbox/store/queue kinds,
mailbox status, setting provenance, and value classifications are normalized
from bounded enums while allowing full-value variables. Secret-bearing settings
must omit raw values and use redacted/operator-secret classifications. Service
and listener `service` refs resolve to same-node transport bindings; component,
domain, mailbox-store, mailbox, alias, routing, and setting refs resolve inside
the owning mail service. Mailbox `account_ref` values resolve to top-level
accounts, mailbox `local_user_ref` values resolve to `runtime.local_identity`
when local users are declared, and setting source paths are checked against
`runtime.filesystem_inventory` when that inventory is non-empty. A top-level
relationship with `mail_access` targets a runtime mail service and resolves
concrete listener, mailbox, and domain refs inside that target service.

The optional `runtime.network_detection_engines` inventory has model-local and
semantic rules. Engine ids are stable concrete symbols and are unique within
one node runtime block; engine-local rule-source, network-set, output-stream,
and control-channel ids are unique inside the owning engine. Optional
`sensor_ref` values resolve to same-node `runtime.network_sensors` ids.
Network-set refs resolve to switch-backed infrastructure entries.
Configuration, log, evidence, rule-source, output-stream, and control-channel
paths are absolute and are checked against `runtime.filesystem_inventory` when
that inventory is non-empty. Control-channel `service` refs resolve to
same-node `Node.services` bindings.

The optional `runtime.security_monitoring_managers` inventory has model-local
and semantic rules. Managers, listeners, components, agents, agent groups,
content sets, detection definitions, and settings use stable ids. Manager ids
are unique within a node runtime block, and every manager-local stable id is
unique across the manager itself plus its child collections. Implementations,
manager kinds, listener roles, component kinds/statuses, agent statuses,
content kinds/formats, detection engines/kinds, field-predicate operators,
setting provenance, and value classifications are normalized from bounded
enums while allowing full-value variables where the model permits.
Settings such as passwords, API tokens, credentials, shared keys, keytabs, or
private keys may carry scenario values unless explicitly classified as
redacted/operator-secret. Managers and listeners may reference only services
declared on the same node. Manager configuration/log/evidence
refs, agent-group configuration refs, content-set file refs,
detection-definition source/evidence refs, and setting source paths are checked
against `runtime.filesystem_inventory` when that inventory is non-empty. Group
`member_refs` must resolve to manager-local agents, agent `group_refs` must
resolve to manager-local groups, setting `component_ref` values must resolve to
manager-local components, detection `content_set_ref` values must resolve to
manager-local content sets, and detection `if_sid_refs`,
`if_matched_sid_refs`, and `parent_definition_refs` must resolve to
manager-local detection definitions. Detection `source_artifact_ref` and
`target_refs` resolve through the generic named-ref index.

The optional `runtime.app_authorizations` inventory has model-local and
semantic rules. Application authorizations, principals, roles, permission
grants, role mappings, and tenants use stable concrete ids; the
`app_authorization_id` is unique within a node runtime block, and every
authorization-local stable id is unique across the authorization itself plus
its principal, role, permission-grant, role-mapping, and tenant collections.
Resource vocabularies, principal kinds, grant effects, and credential
classifications are normalized from bounded enums while allowing full-value
variables where the model permits. A principal never carries a raw credential
value: its posture is the `credential_classification`, and a principal name
does not force a redaction classification. An authorization that
declares a concrete (non-`unknown`) `resource_vocabulary` must carry at least
one permission grant whose `resource_kind` matches that vocabulary; a declared
but unused vocabulary is rejected, while a `${var}` placeholder or the open
`unknown` sentinel is exempt. Permission-grant and role-mapping `role_ref`
values resolve to roles declared within the same authorization. This is
application-internal RBAC: it is distinct from `runtime.identity_authorities`
(wire-protocol directory subjects and trust edges) and from
`runtime.database_services` engine GRANTs.

The optional `runtime.scheduled_jobs` inventory has model-local and semantic
rules. Scheduled-job ids are stable concrete symbols and are unique within a
node runtime block. The `schedule.kind` is a closed structural recurrence
vocabulary (`interval`, `cron`, `calendar`) carrying no `unknown`/`other`
sentinel, while `run_state.last_result` is an open outcome vocabulary. Boolean
`enabled` flags accept booleans or full-value variables. This surface models
recurrence cadence and observed run-state only; it does not carry job inputs,
outputs, or trigger targets. The `scheduled_jobs` / `service_units` /
`forwarding_agents` boundary is deliberate: `runtime.service_manager_units`
carries systemd-scoped unit lifecycle (including the `timer` unit kind), a
`scheduled_jobs` entry carries product-neutral cadence and run-state for a
recurring job (such as a bare-container ENTRYPOINT loop a systemd unit cannot
express), and what a recurring forwarder ships — its inputs, transforms, and
ship targets — belongs to the referencing forwarding agent, never re-encoded on
the job. An event-triggered task is a trigger relationship, not a recurrence,
and is therefore not a scheduled job.

The optional `runtime.datastore_services` inventory has model-local and semantic
rules. Datastore-service ids are stable concrete symbols and are unique within a
node runtime block; the service-local cluster, persistence, transport-security,
node, partition, template, mapping, setting, node-plugin, and node-endpoint ids
are unique across the service. Engines, data models, partition kinds, node
roles, node-endpoint roles, persistence eviction policies, replication
strategies, transport-security modes, and setting scope/provenance/classification
are normalized from bounded enums while allowing full-value variables. Native
cluster/index UUIDs are observed datastore facts, not SDL reference identities;
references continue to target the stable RAES ids. Count and byte fields on
clusters and partitions accept only non-negative integers or full-value
variables, keeping document cardinality and byte-normalized store size distinct
from `datatype_census`. Node engine provenance is observed inventory: heap byte
bounds normalize human sizes to bytes and a concrete `heap_init_bytes` must not
exceed a concrete `heap_max_bytes`; node-endpoint ports are validated to the
1-65535 range with address and port kept split.
Explicit redacted/operator-secret setting classifications omit raw values; names
alone do not force omission. The `require_profile_for_data_model` guard makes the
discriminator executable: a `${var}` placeholder is exempt and the open
`unknown`/`other`/`relational` tail is permissive, but a concrete `search_index`
requires at least one `index` partition carrying shard/replica geometry and at
least one structured mapping manifest, a `wide_column` store requires at least
one `keyspace` partition with a replication strategy and factor, and a
`key_value` store requires a `persistence` profile and rejects
relational/wide-column partitions. Mapping `partition_ref` values resolve to
sibling datastore partitions, and template `mapping_ref` values resolve to
sibling mapping manifests. Raw mapping/template response bodies are not model
data; bounded manifests carry counts, summaries, digests, and evidence refs.
The owning transport `service` resolves to a same-node binding, and a non-empty,
non-variable `authorization_ref` resolves to a same-node `app_authorization` (the
delegated internal RBAC store).

The optional `runtime.platform_applications` inventory has model-local and
semantic rules. Platform-application ids are stable concrete symbols and unique
within a node runtime block; capability, organization, tenant, content-object,
marking, upstream-binding, connector, and setting ids share the application's
local stable-id namespace. Capability kinds are an open provider-neutral
vocabulary and one application may declare several. A capability asserts a
functional role only; it does not imply configured content, policy, successful
execution, or completeness. The legacy `platform_kind` and `content_objects`
fields remain accepted but are deprecated and do not drive validation.
Content objects remain bounded parsed manifests—typed kind, bounded attributes,
typed references, marking refs, and evidence refs—never raw bodies. Explicit
redacted/operator-secret setting classifications omit raw values, and connector
names do not force redaction classifications. The owning transport `service`
and a non-empty, non-variable `authorization_ref` resolve on the same node;
legacy content-object `references` resolve to sibling content objects and
`marking_refs` resolve to sibling markings.

The optional `runtime.forwarding_agents` inventory and top-level
`forwarding_agents` registry have model-local and semantic rules.
Forwarding-agent ids are stable concrete symbols and unique across node-hosted
and scenario-level registries; the agent-local source, transform, ship-target,
buffer-policy, reload-channel, and setting ids are unique across the agent. Agent
implementations, kinds, source kinds, parse formats, transform kinds, protocols,
buffer crypto, reload-channel kinds, enrollment classifications, and setting
provenance/classification are normalized from bounded enums while allowing
full-value variables. A ship-target enrollment identity is never recorded — only
the closed `none`/`redacted`/`operator_secret` lattice — and explicit
redacted/operator-secret setting classifications omit raw values. The
`require_profile_for_agent_kind`
guard makes the `agent_kind` discriminator executable: a `${var}` placeholder is
exempt and the open `unknown`/`other` tail is permissive, but a concrete
`log_forwarder` requires a `buffer_policy` and at least one `ship_target` carrying
an ingestion endpoint and rejects any `ioc_to_rule` transform, while a concrete
`content_sync` requires at least one `api_pull` source, one `ioc_to_rule`
transform, and one `reload_channel`, and rejects a `buffer_policy` and any
`ship_target` enrollment endpoint. At scenario scope, a ship-target
`target_node_ref` resolves to a defined node and a `target_service_ref` resolves
to a service on the referenced node (or, for node-hosted agents only, on the
owning node). Scenario-level agents have no owning node, so a concrete service
ref must be paired with a concrete target node.
The `scheduled_jobs` / `service_units` / `forwarding_agents` boundary is the same
one described above: a recurring forwarder's cadence belongs to a
`runtime.scheduled_jobs` entry and its systemd lifecycle to
`runtime.service_manager_units`, while what it ships — sources, transforms, and
ship targets — belongs only to the forwarding agent; the inter-node trust edge is
a relationship forwarding edge, not a re-typed ship target.

The optional `runtime.orchestration_authorities` inventory has model-local and
semantic rules. Orchestration-authority ids are stable concrete symbols and unique
within a node runtime block; spawn-template and realized-child ids are unique
across the authority. Engines and privilege classes are normalized from open
taxonomies (both carry `unknown` and `other`) while allowing full-value variables,
and realized-child `count` accepts a non-negative integer, a `${var}`, or none.
The `require_profile_for_privilege_class` guard makes the `privilege_class`
discriminator executable: a `${var}` placeholder is exempt and `namespaced`/
`unknown`/`other` are permissive, but a concrete `host_root_equivalent` authority
requires a non-empty, non-variable `control_interface_ref`. At scenario scope a
non-empty, non-variable `control_interface_ref` resolves to a
`RuntimeControlInterface` declared in the same node's
`runtime.local_control_interfaces` (by `control_interface_id`); for a
`host_root_equivalent` privilege class the referenced interface must additionally
be a read-write docker socket (access `read_write`, kind `unix_socket`, path
ending in `docker.sock`), with `${var}` interface access/kind/path treated as
deferred and therefore permissive. The `RuntimeControlInterface` shell is
referenced, never duplicated: this surface carries the spawn contract (engine,
scope, spawn templates, lifecycle policy, realized children) that the control
interface model has no field for.

The optional `source.build` container image provenance block carries its own
model-local rules. Build-argument and image-default-environment names must be
non-empty and free of `=`, and values classified as redacted must omit the raw
value. Copied-source and source-input destination paths, and image-config
working directories, must be absolute paths or variable references. Source-input
checksums must carry both the checksum and its algorithm. Build-argument names
and source-input identifiers must be unique within a build block, and
image-default environment names must be unique within an image config. An
attestation with `status: absent` cannot also report `verification: verified`,
keeping "no registry-visible attestation" distinct from a failed verification.

When a field contains an unresolved `${var}` placeholder, reference-oriented
passes treat it as deferred rather than as a broken concrete reference. The
validator still does not substitute values; the repo-owned instantiation
phase performs substitution, type-checking, and concrete revalidation before
runtime compilation.

The SDL validator is intentionally structural/semantic. The SDL-native runtime
compiler and runtime conformance helpers perform additional fail-closed binding
checks, including node-local feature dependency enforcement, bound-resource
reference resolution, and SEM-215 outcome-record grounding. A participant outcome
interpretation emitted at runtime must preserve declared source/target bindings
and must ground participant-action outcome sources in the event action result,
evidence refs in event evidence, and participant-episode status sources in
terminal participant-episode history for the same participant and episode.

This also means the validator only enforces what the current SDL syntax can
actually express. Node `runtime` is declarative contract state. The closed
model rejects observation-only health results, generated network/endpoint
identifiers and generated DNS identity, scanner capture provenance, and
scanner-derived package findings. Those facts use experiment evidence records,
inventory ledgers, and derived measures instead. Packages, software components,
dependency manifests, addresses, aliases, MACs, and backend details remain SDL
only when an author deliberately requires them.
The `source.build` block covers observed container image build provenance:
base image and digest, layer chain, structured build-recipe instructions, build
arguments, copied sources, image-default configuration, source-input mapping,
and attestation status.
Broader ecosystem concerns such as participant-implementation manifests,
decision-surface exposure policy contracts, augmentation disclosure, and full
evidence-capture contract surfaces are separate validation domains.
They should not be retrofitted into validator-only behavior before the authored
surface or external contracts exist.

## Enum normalization convention

All SDL enum-or-var parsers share one author-facing normalization rule:
concrete strings are lowercased and hyphen aliases are mapped to underscore
enum values before matching, while full-value `${var}` placeholders and `None`
remain deferred. Runtime fields continue to call
`parse_runtime_enum_or_var`, but that helper delegates to the canonical
`parse_enum_or_var` implementation in `_base.py`, so runtime and non-runtime
enum fields cannot drift on accepted spellings. The shared behavior is covered by
`test_enum_or_var_helpers_share_hyphen_alias_normalization` in
`tests/test_runtime_family_invariants.py`.

## Runtime enum sentinel convention

Runtime service-family enums (every `Enum` defined in an `raes` module whose
name starts with `runtime_`, including the `*_vocab` and `*_definitions`
modules) follow a single, executable sentinel convention:

- An **open** observed-value taxonomy carries **both** `unknown` and `other`.
  `unknown` is the "not yet classified / not captured" value (and is typically
  the field default), and `other` is the escape hatch for an observed value that
  does not match a named member. Most runtime inventory enums are open, because
  capture is best-effort and the named member list is never closed against the
  real world.
- A **closed** structural, protocol, or redaction-lattice vocabulary carries
  **neither** `unknown` nor `other`. A value outside the fixed set is not a
  member of the concept at all (for example
  `RuntimeApplicationRouteUpstreamScheme`, which is exactly `http`/`https`: a
  proxy-to-origin hop that is neither is not an application route upstream).

The single-sentinel state — exactly one of `{unknown, other}` — is forbidden.
It is ambiguous: it neither commits to a closed set nor offers the full
open-taxonomy pair, so consumers cannot tell whether an unmatched observed value
should round-trip as `other` or be treated as `unknown`.

This convention is enforced as an executable drift guard by
`test_runtime_enums_open_or_closed_not_single_sentinel` in
`tests/test_runtime_family_invariants.py`. The test introspects every enum
defined in a runtime-family module and asserts
`("unknown" in values) == ("other" in values)` for each, so any future runtime
enum introduced in a single-sentinel state fails the suite immediately. When a
new enum is genuinely closed, it must carry neither sentinel; otherwise it must
carry both.

## Runtime required-profile guard convention

Some runtime-family spines use an open enum-or-string discriminator to select a
required profile from sibling structured fields. Those discriminators are not
documentation-only claims: each documented required-profile discriminator must
have a matching `require_profile_for_<field>` guard invoked by a registered
Pydantic `mode="after"` model validator. This is the executable "cannot
silently shallow-encode" guarantee for spines that actually make a
discriminated completeness claim, currently `data_model`, `agent_kind`, and
`privilege_class`. Platform applications deliberately do not use this
convention: their deprecated `platform_kind` is classification, composable
`capabilities` carry functional roles, and completeness is a separate
requirement concern.

The convention is enforced by
`test_discriminated_runtime_spines_register_required_profile_guards` in
`tests/test_runtime_family_invariants.py`. The lint discovers runtime-family
models from `RuntimeConfiguration.model_fields`, identifies discriminator
fields whose docs say they select a required profile and whose models carry
sibling structured profile fields, and checks Pydantic's registered
model-validator metadata for the corresponding guard call. A future runtime
spine that declares the same required-profile discriminator shape but omits the
guard fails the test suite.

## Static Semantic Invariants

The validator is the main enforcement point for static SDL semantics, but not
the only source of truth. The same rules must remain consistent with compiled
runtime models and downstream runtime contracts.

Typical invariant categories in this layer include:

- cross-reference existence and disambiguation
- uniqueness rules for names and bindings
- acyclic dependency and workflow graphs
- fail-closed resolution for ambiguous or missing references
- reachability and convergence constraints
- “guaranteed to be known before evaluation” visibility rules

In coding-standards terms:

- `FM1` covers static semantic rules such as ambiguity, uniqueness, and
  fail-closed reference resolution
- `FM2` covers graph/constraint rules such as reachability, visibility, and
  consistency across validator and compiled/runtime forms

Workflows are the clearest current example. Their syntax is described in YAML,
but the important semantics live here and in the runtime architecture: which
steps are reachable, which joins are legal, and which prior step states are
knowable before a predicate executes.

Objective windows are the clearest current `FM2` example. Their authoring
surface is still simple YAML, but the semantic meaning comes from one shared
analysis pass that resolves normalized references, checks story/script/event and
workflow/step consistency, derives refresh semantics, and feeds both validator
errors and compiled runtime forms.

The same pattern applies conceptually to participant and observability
concerns: author-facing syntax, shared semantics, runtime
contracts, and provenance must stay aligned, but they do not all collapse into
the current validator surface.

## Advisories

The normative boundary between a fatal **error** and a non-fatal **advisory** —
including the classification criterion that decides which channel a condition
belongs to — is stated in
{download}`specs/sdl/diagnostics.md <../../../specs/sdl/diagnostics.md>` §5. This page is
non-normative explanation and cites that criterion rather than restating it: an
**error** affects SDL meaning (structural/semantic invariants), while an
**advisory** is a deployability or quality heuristic that leaves SDL meaning
intact.

Successful parses may still carry non-fatal advisories on `Scenario.advisories`. These are not validation errors and do not block parsing.

Current advisory coverage:

- compute nodes without `resources` are allowed, but emit an advisory because some deployment backends may not be able to instantiate them without explicit sizing defaults.

## Error Reporting

The fatal, fail-closed error semantics and the collect-all behaviour described
here are the explanatory companion to the normative diagnostic boundary in
{download}`specs/sdl/diagnostics.md <../../../specs/sdl/diagnostics.md>`.

All passes run to completion. Errors are collected into a list and raised as a single `SDLValidationError`:

```python
try:
    scenario = parse_sdl(yaml_string)
except SDLValidationError as e:
    print(f"{len(e.errors)} errors found:")
    for error in e.errors:
        print(f"  - {error}")
```

## Cross-Reference Resolution

Generic refs are indexed in two forms:

- bare names like `webapp` when they are unique in the generic-ref namespace
- qualified names like `nodes.webapp`, `features.postgres`, `infrastructure.dmz-net`, or `content.mailbox.items.invoice.eml`

The index also includes nested entity dot-paths, named service bindings
(`nodes.<node>.services.<service_name>`), named ACL rules
(`infrastructure.<infra>.acls.<acl_name>`), and runtime-family refs generated
from the SDL runtime-family registry. Registered runtime refs include:

- `nodes.<node>.runtime.service_listeners.<listener_id>`
- `nodes.<node>.runtime.applications.<application_id>`
- `nodes.<node>.runtime.database_services.<database_service_id>` plus
  `.databases.<database_id>`
- `nodes.<node>.runtime.dns_services.<dns_service_id>` plus `.zones.<zone_id>`
  and `.zones.<zone_id>.rrsets.<rrset_id>`
- `nodes.<node>.runtime.identity_authorities.<identity_authority_id>` plus nested
  service, subject, policy, and relationship refs
- `nodes.<node>.runtime.file_services.<file_service_id>` plus nested share,
  principal, access-rule, and access-observation refs
- `nodes.<node>.runtime.mail_services.<mail_service_id>` plus nested component,
  listener, domain, mailbox-store, mailbox, alias, routing-rule, queue, and
  setting refs
- `nodes.<node>.runtime.network_sensors.<network_sensor_id>`
- `nodes.<node>.runtime.network_detection_engines.<network_detection_engine_id>` plus nested
  rule-source, network-set, output-stream, and control-channel refs
- `nodes.<node>.runtime.security_monitoring_managers.<security_monitoring_manager_id>` plus nested
  listener, component, agent, agent-group, content-set, detection-definition,
  and setting refs
- `nodes.<node>.runtime.ssh_servers.<ssh_server_id>` plus
  `.match_rules.<match_id>`
- `nodes.<node>.runtime.app_authorizations.<app_authorization_id>` plus nested
  principal, role, permission-grant, role-mapping, and tenant refs
- `nodes.<node>.runtime.scheduled_jobs.<scheduled_job_id>`
- `nodes.<node>.runtime.datastore_services.<datastore_service_id>` plus nested
  node, partition, and setting refs
- `nodes.<node>.runtime.platform_applications.<platform_application_id>` plus
  nested capability, organization, tenant, content-object, marking,
  upstream-binding, connector, and setting refs

This means a relationship can reference any node, feature, condition,
vulnerability, infrastructure entry, entity
(including nested), inject, event, script, story, content entry, content item,
account, agent, objective, workflow, relationship, variable, named service
binding, registered runtime-family object, registered runtime-family child
object, or named ACL rule. When a bare ref maps to multiple elements,
validation fails and asks the author to use one of the qualified alternatives.
