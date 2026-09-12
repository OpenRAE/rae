# Catalog 4 — Runtime-Family Index

The runtime inventory is the node-scoped record of logical service state an SDL
document declares for a node. This file is a normative **index**: it places the
runtime inventory in the document, names each runtime family and its addressing
shape, and states the invariants every family shares **once**. It deliberately
**delegates** each family's per-field semantics to that family's ADR rather than
restating them, so the authoring spec does not duplicate the runtime ADR
sequence.

## 1. Placement and boundary

1. Runtime inventory lives under a node: `nodes.<node>.runtime.<collection>`. It
   is **not** a top-level authoring section.
2. The runtime layer records **logical service state** — what a service is and
   how it is configured — not delivery mechanics. The scenario/delivery boundary
   for runtime node state is fixed by
   [ADR-033](../../docs/decisions/adrs/adr-033-scenario-delivery-boundary-for-runtime-node-state.md);
   the SDL/processor/runtime layering by
   [ADR-004](../../docs/decisions/adrs/adr-004-sdl-runtime-layer.md) and
   [ADR-036](../../docs/decisions/adrs/adr-036-sdl-processor-runtime-module-boundaries.md).
3. Runtime-family elements and their children are addressed by the
   nested runtime-family reference form
   ([references.md §1](references.md)):
   `nodes.<node>.runtime.<collection>.<id>[.<child-collection>.<child-id>…]`.
4. `Node.services[]` is adjacent authored identity, not runtime inventory. Each
   entry identifies a node-local transport binding by port, protocol, and
   optional name; it does not authorize traffic, prove a live listener, publish
   a host port, or classify an audience. Authorization remains in
   `infrastructure.*.acls`, observed bind state in
   `runtime.service_listeners`, and host publication in
   `runtime.network.published_ports`.

## 2. Family index

Each registered node-scoped runtime family has a stable key, a collection name
under `runtime`, a primary `<noun>_id`, an addressable child-collection tree,
and an owning ADR. The owning ADR is the normative authority for that family's
fields, enums, and profiles; this index does not restate them.

| Family key | `runtime.<collection>` | Primary id | Addressable child paths (`collection:id`) | Owning ADR |
|------------|------------------------|------------|------------------------|-----------|
| `service-listeners` | `service_listeners` | `service_listener_id` | none | [ADR-043](../../docs/decisions/adrs/adr-043-runtime-service-listener-surface.md) |
| `applications` | `applications` | `application_id` | none | [ADR-026](../../docs/decisions/adrs/adr-026-application-http-surface-inventory.md) |
| `database-services` | `database_services` | `database_service_id` | `databases:database_id` | [ADR-029](../../docs/decisions/adrs/adr-029-database-logical-state-runtime-surface.md) |
| `dns-services` | `dns_services` | `dns_service_id` | `zones:zone_id, zones:zone_id/rrsets:rrset_id` | [ADR-039](../../docs/decisions/adrs/adr-039-dns-service-runtime-inventory.md) |
| `identity-authorities` | `identity_authorities` | `identity_authority_id` | `services:service_id, subjects:subject_id, policies:policy_id, relationships:relationship_id` | [ADR-032](../../docs/decisions/adrs/adr-032-directory-domain-identity-runtime-surface.md) |
| `file-services` | `file_services` | `file_service_id` | `shares:share_id, principals:principal_id, access_rules:rule_id, access_observations:observation_id` | [ADR-037](../../docs/decisions/adrs/adr-037-runtime-file-service-and-filesystem-presence-semantics.md) |
| `mail-services` | `mail_services` | `mail_service_id` | `components:component_id, listeners:listener_id, domains:domain_id, mailbox_stores:store_id, mailboxes:mailbox_id, aliases:alias_id, routing_rules:rule_id, queues:queue_id, settings:setting_id` | [ADR-038](../../docs/decisions/adrs/adr-038-runtime-mail-service-logical-state.md) |
| `network-sensors` | `network_sensors` | `network_sensor_id` | none | [ADR-042](../../docs/decisions/adrs/adr-042-network-sensor-runtime-monitoring.md) |
| `network-detection-engines` | `network_detection_engines` | `network_detection_engine_id` | `rule_sources:source_id, network_sets:set_id, output_streams:stream_id, control_channels:channel_id` | [ADR-044](../../docs/decisions/adrs/adr-044-network-detection-engine-runtime-inventory.md) |
| `security-monitoring-managers` | `security_monitoring_managers` | `security_monitoring_manager_id` | `listeners:listener_id, components:component_id, agents:agent_id, agent_groups:group_id, content_sets:content_id, detection_definitions:definition_id, settings:setting_id` | [ADR-040](../../docs/decisions/adrs/adr-040-security-monitoring-manager-runtime-inventory.md), [ADR-045](../../docs/decisions/adrs/adr-045-security-monitoring-detection-definition-semantics.md) |
| `ssh-servers` | `ssh_servers` | `ssh_server_id` | `match_rules:match_id` | [ADR-031](../../docs/decisions/adrs/adr-031-ssh-server-configuration-surface.md) |
| `app-authorizations` | `app_authorizations` | `app_authorization_id` | `principals:principal_id, roles:role_id, permission_grants:grant_id, role_mappings:mapping_id, tenants:tenant_id` | [ADR-046](../../docs/decisions/adrs/adr-046-app-authorization-runtime-inventory.md) |
| `scheduled-jobs` | `scheduled_jobs` | `scheduled_job_id` | none | [ADR-047](../../docs/decisions/adrs/adr-047-scheduled-job-runtime-inventory.md) |
| `datastore-services` | `datastore_services` | `datastore_service_id` | `nodes:node_id, nodes:node_id/plugins:plugin_id, nodes:node_id/endpoints:endpoint_id, partitions:partition_id, templates:template_id, mappings:mapping_id, settings:setting_id` | [ADR-048](../../docs/decisions/adrs/adr-048-datastore-service-runtime-inventory.md), [ADR-058](../../docs/decisions/adrs/adr-058-datastore-node-engine-provenance-and-endpoints.md) |
| `platform-applications` | `platform_applications` | `platform_application_id` | `capabilities:capability_id, organizations:organization_id, tenants:tenant_id, content_objects:content_object_id, markings:marking_id, upstream_bindings:binding_id, connectors:connector_id, settings:setting_id` | [ADR-049](../../docs/decisions/adrs/adr-049-platform-application-runtime-inventory.md) |
| `forwarding-agents` | `forwarding_agents` | `forwarding_agent_id` | `sources:source_id, transforms:transform_id, ship_targets:target_id, reload_channels:reload_channel_id, settings:setting_id` | [ADR-050](../../docs/decisions/adrs/adr-050-forwarding-agent-runtime-inventory.md) |
| `orchestration-authorities` | `orchestration_authorities` | `orchestration_authority_id` | `spawn_templates:template_id, realized_children:workload_id` | [ADR-051](../../docs/decisions/adrs/adr-051-orchestration-authority-runtime-inventory.md) |

The node-scoped `forwarding_agents` family is distinct from the scenario-level
`forwarding_agents` authoring section ([sections.md](sections.md)); they share
identity and invariants but occupy different document positions.

Forwarding-agent entries also carry a closed ownership role:
`system_under_test` (the default) or `measurement_apparatus`. This role
classifies ownership relative to the experiment; it does not assert execution,
visibility, delivery, or health. Exact realization of the family means
independently corroborated presence or configuration, as required by the
authored projection, not proof that forwarding behavior occurred. Operational
behavior is expressed through proposition, probe, truth, and evidence
contracts.

### Other node-runtime surfaces

A node's `runtime` also carries surfaces that are not ref-targetable families in
the index above but follow the same invariants and are governed by their own
ADRs: local identity
([ADR-024](../../docs/decisions/adrs/adr-024-local-identity-inventory-surface.md)),
container image provenance
([ADR-023](../../docs/decisions/adrs/adr-023-container-image-build-provenance-surface.md)),
software components
([ADR-034](../../docs/decisions/adrs/adr-034-runtime-software-component-inventory.md)),
service-manager units
([ADR-035](../../docs/decisions/adrs/adr-035-service-manager-unit-state-runtime-surface.md)),
and container init/reaper state
([ADR-027](../../docs/decisions/adrs/adr-027-container-init-reaper-runtime-surface.md)).
These authored identity surfaces are kept **separate** from one another:
authored `accounts`, runtime local identity, application authorization, database
roles, and participant identities are distinct models and MUST NOT be collapsed
into one.

Component software requirements, exact-package shorthand, optional typed
acquisition refinements and the node-local shared `repository_state` surface
follow [software-requirements.md](software-requirements.md). They do not add
ref-targetable service families to the table above.

A node's `runtime.environment[]` variable and `runtime.environment_files[]` entry
may source their value from a **generated-artifact output** instead of a literal,
using a value-free `value_from: {generated_artifact, output}` reference. This is
the `environment` / `env_file` generated-artifact delivery mode; the binding is
authored here, on the node, and the compiler derives the artifact-side consumer
projection. See [stateful-resources.md](stateful-resources.md) for the delivery
modes, cross-resource resolution, `producer_private` exclusion, and the
`supported_generated_artifact_delivery_modes` backend capability. A generated
secret value follows invariant §3.5 below (omit the raw `value`, classify
`redacted`); it is not `operator_secret`.

## 3. Shared invariants

The following invariants hold for every runtime family and child collection.
They are stated here once; a family's ADR specifies the family's fields, but may
not contradict these.

1. **Identity (`<noun>_id`).** Every family element and every addressable child
   element carries a stable `<noun>_id`. The id **MUST** be unique within its
   collection and use the portable local-identifier grammar
   ([document-model.md §6](document-model.md)). Runtime/native/provider ids that
   are not RAES-local declaration identities retain their owning contracts.
   References address elements by these ids ([references.md](references.md)).
2. **Enum sentinels.** An open enum carries a closed core of well-defined values
   plus the sentinels `unknown` and `other`, so an authored value can record
   "not determined" or "outside the closed set" without widening the closed core.
   A sentinel value is discriminator-neutral: it imposes no profile requirement.
3. **Quantity normalisation.** A human-readable byte quantity (for example
   `4 GiB`, `512 MB`) is normalised to a canonical byte count on a `_bytes`-style
   field. The normalised count is the value's meaning; the authored spelling is a
   convenience.
4. **Required-profile guards.** Where a family is a discriminated union (for
   example, a datastore's data-model spine), the discriminator value **requires**
   the profile-specific fields for that value. A profile guard is fail-closed: a
   discriminator that selects a profile without that profile's required fields is
   an error ([diagnostics.md](diagnostics.md)). A discriminator set to a sentinel
   (`unknown`/`other`) requires no profile.
5. **Observed values and redaction.** Runtime inventory records observed posture,
   not live secrets. An explicit `redacted` or `operator_secret` classification
   **MUST** omit the raw value
   ([ADR-056](../../docs/decisions/adrs/adr-056-runtime-observed-values-and-credential-posture.md),
   [ADR-057](../../docs/decisions/adrs/adr-057-runtime-secret-name-classifier-boundaries.md)).
   Name-based secret-classification heuristics are **advisory only**
   ([diagnostics.md](diagnostics.md)); they never silently strip or rewrite a
   value. A posture-only model **MUST NOT** gain raw-credential fields.

## Extending the runtime-family index

A new runtime family is added by: defining its model and published schema,
authoring its owning ADR, registering it in the canonical family registry (key,
collection, primary `<noun>_id`, child-ref tree), and adding one row to the index
above. The shared invariants (§3) apply automatically; the nested runtime-family
reference form ([references.md §1](references.md)) addresses its elements without
bespoke prose. No second runtime-family registry exists or should be created.
