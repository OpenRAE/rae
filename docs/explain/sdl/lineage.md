# Lineage and Prior Work

RAES is not designed as a clean-room language. It is a consolidation layer over
cyber range SDLs, adversary emulation formats, agent-evaluation environments,
runtime architectures, and security event schemas that solve adjacent parts of
the same problem.

This page is a short map of the main influences. It is not a provenance or
compatibility claim, and it is not an exhaustive bibliography. For design
rationale, see [Design Precedents](precedents.md). For a dimension-by-dimension
comparison against precedent systems, including where those systems lead RAES, see
[Related-Work Comparison](related-work-comparison.md).

The normative audit record is
[`contracts/provenance/sdl-lineage-ledger-v2.json`](../../../contracts/provenance/sdl-lineage-ledger-v2.json).
It distinguishes intellectual lineage from artifact/code derivation and from
implementation examples, pins source revisions and bibliographic identities,
and records directional compatibility and notice disposition. An influence
listed on this page is not, by itself, a claim that RAES adopted syntax,
semantics, examples, or code from that source.

## Specification Surface

- [Open Cyber Range SDL](https://documentation.opencyberrange.ee/docs/sdl/reference/)
  is the closest direct SDL precedent. RAES starts from its author-facing
  section surface, including logical nodes, infrastructure, features,
  conditions, entities, injects, events, scripts, and stories. RAES keeps the
  logical scenario surface separate from backend realization instead of
  treating the SDL as a deployment format, and per
  [ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md) it
  dropped OCR's scoring concepts (metrics/evaluations/TLOs/goals) — graded
  scoring/reward lives in the experiment/evaluator plane.
- [Open Cybersecurity Schema Framework](https://ocsf.io/) influences the event
  and schema side of the architecture. Its schema, profile, extension, and
  attribute-dictionary model is the main precedent for portable telemetry and
  disciplined schema evolution.
- Domain-specific language work, especially the classic DSL literature and
  formal cyber-range DSLs such as VSDL and CRACK, informs the separation
  between concrete YAML syntax, semantic models, validation, compilation, and
  runtime contracts.

## Scenario Concepts

- [CACAO Security Playbooks v2.0](https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.pdf)
  informs variables, objective composition, workflow graph structure, and the
  distinction between authored playbook intent and concrete execution.
- [STIX 2.1](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html)
  informs typed directed relationships and cross-object references. RAES adapts
  that pattern for scenario elements rather than threat-intelligence objects.
- CyRIS, KYPO, OCR, VSDL, and CRACK are prior scenario-definition systems.
  Their strongest shared lesson is that scenario meaning must be more than a
  deployment script.
- SBOM standards such as [CycloneDX](https://cyclonedx.org/specification/overview/)
  and [SPDX](https://spdx.dev/use/specifications/) inform the runtime software
  component identity vocabulary: component type, version, purl/CPE, hashes, and
  package or manifest lineage are useful portable facts. RAES adapts those
  identity concepts under `Node.runtime.software_components`; it does not import
  raw SBOM documents, scanner output, or invocation/capability semantics into
  the SDL schema.

The authored/defaulted/planned/realized/observed/derived distinction tested by
[issue #160](https://github.com/OpenRAE/rae/issues/160) is a carrier
boundary, not a vocabulary tag. SDL and `model_fields_set` carry authored and
defaulted meaning; compiler plans carry planned operations; realization
provenance and realized-form disclosures carry admitted choices; evidence
records and inventory ledgers carry observations; derived-measure contracts
carry interpretations. Docker identifiers, health results, and scanner state
therefore remain evidence even when an SDL model could otherwise represent the
same scalar shape. Deliberate authoring is the only promotion into scenario
requirements.

## Directory, Domain, And Identity Authority Semantics

The `runtime.identity_authorities` surface is issue #401's response to an
observed gap in APTL's TechVault AD inventory. It is not a clean-room
invention, but it also is not a clone of any one directory or attack-graph
format.

RAES relies on prior work in four different ways:

- **Scenario-language precedents:** top-level `accounts` keeps the CyRIS account
  placement lineage. CyRIS implements `add_account`/`modify_account` as
  host/user management operations in code
  ([modules.py](https://github.com/crond-jaist/cyris/blob/8b65a30581cdd8e126c7b1fa26db2a4b770b7f17/main/modules.py)),
  so RAES continues to treat `accounts` as curated scenario/provisioning
  resources. RAES does not infer a full directory service from those accounts.
- **Primary industry standards:** LDAP/X.500 ([RFC 4510](https://www.rfc-editor.org/rfc/rfc4510),
  [RFC 4512](https://www.rfc-editor.org/rfc/rfc4512)), Kerberos
  ([RFC 4120](https://www.rfc-editor.org/rfc/rfc4120)), SCIM
  ([RFC 7643](https://www.rfc-editor.org/rfc/rfc7643),
  [RFC 7644](https://www.rfc-editor.org/rfc/rfc7644)),
  [SAML V2.0 Assertions and Protocols](http://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf),
  OAuth 2.0 ([RFC 6749](https://www.rfc-editor.org/rfc/rfc6749)),
  [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0-18.html),
  [NIST SP 800-63C-4](https://doi.org/10.6028/NIST.SP.800-63C-4),
  [NIST SP 800-162](https://doi.org/10.6028/NIST.SP.800-162), and
  [NIST SP 800-207](https://doi.org/10.6028/NIST.SP.800-207) supply
  terminology for authorities, naming contexts, realms, issuers, tenants,
  subjects, groups, attributes, policy inputs, federation boundaries,
  attribute-based authorization, and zero-trust identity/resource boundaries.
  RAES adapts their shared concepts, not their full protocol objects.
- **Primary access-control literature:** Lampson's
  [access matrix](https://doi.org/10.1145/775265.775268), Saltzer and
  Schroeder's [protection principles](https://doi.org/10.1109/PROC.1975.9939),
  Ferraiolo/Kuhn [RBAC](https://www.nist.gov/publications/role-based-access-controls),
  Sandhu et al.'s [RBAC96 model](https://doi.org/10.1109/2.485845), and NIST
  ABAC support the separation among subject, attribute, policy, relationship,
  and authority boundary. That is why RAES models policies and
  membership/trust/federation edges as first-class records instead of storing
  them only as prose or untyped relationship properties.
- **Downstream/evidence precedents:** BloodHound/OpenGraph validates the
  usefulness of node/edge identity graphs for attack-path analysis, while OCSF,
  UCO, and CASE are evidence and concept-authority influences. RAES does not
  make any of them the canonical runtime inventory schema: BloodHound graphs
  are downstream analysis overlays, OCSF is telemetry/event-oriented, and
  UCO/CASE are concept/evidence vocabularies broader than the SDL authoring
  surface.

Reference status is explicit. The identity and access-control authorities above
are primary standards, government reports, or peer-reviewed access-control
literature. The cyber-range and V&V sources are adjacent methodological support:
Russo/Costa/Armando, Swiler, Oberkampf/Roy, and Sargent are citable proceedings,
technical-report, or book sources; Garg et al. is used as a current survey
preprint rather than as settled normative authority. The working Zotero library
tracks these identity-authority references under `raes-sdl-identity-authority`
and the adjacent V&V subset under `adjacent-vv-lineage`; because that library is
private, the Garg et al. preprint citation is also snapshotted in-repo under
[`docs/research/primary/`](../../research/primary/literature/cyber-range-scenario-survey.md)
so the reference is verifiable from the repository alone.

The design deliberately keeps provider-stable identifiers as data rather than
as RAES reference identity. AD SIDs/objectGUIDs, LDAP DNs/entryUUIDs, SCIM
`id`/`externalId`, SAML NameIDs, and OIDC `iss` + `sub` values are preserved in
specific fields or bounded attributes when needed for translation/evidence, but
the portable RAES references are stable `*_id` symbols scoped by the scenario
and authority. Within one authority those ids share a single local namespace,
so an id cannot be reused across service, subject, policy, relationship, and
authority records. This matches the verification/validation posture in the
cyber-range literature (for example Russo, Costa, and Armando's
[Scenario Design and Validation for Next Generation Cyber Ranges](https://doi.org/10.1109/NCA.2018.8548324)
(IEEE NCA 2018), and Garg, Boualouache, Imeri, and Roth's
[A Survey of Cyber Range Training Exercise Scenario Description, Generation, and Execution](https://doi.org/10.36227/techrxiv.175942879.94813577/v1)
(TechRxiv preprint, 2025 — snapshotted in-repo at
[docs/research/primary](../../research/primary/literature/cyber-range-scenario-survey.md)),
and Swiler plus Oberkampf/Roy/Sargent on
[cyber-emulation V&V](https://doi.org/10.2172/1897016),
[scientific-computing V&V](https://doi.org/10.1017/CBO9780511760396), and
[simulation-model V&V](https://doi.org/10.1109/WSC.2010.5679166)): a model
should state what it can preserve and compare rather than smuggle
backend/vendor assumptions into an ambiguous field.

## Enterprise Identity And Deployment-Tenancy Authoring

The authored enterprise extension in
[ADR-087](../../decisions/adrs/adr-087-enterprise-identity-and-deployment-tenancy-authoring.md)
builds on the identity-authority boundary above without promoting observed
directory inventory or provider deployment configuration into scenario
authority.

- **Forest and trust lineage:** Microsoft's
  [Active Directory logical model](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/plan/understanding-the-active-directory-logical-model)
  distinguishes a forest from its member domains and keeps that logical model
  independent of controller count and network topology. Its
  [forest-root guidance](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/plan/selecting-the-forest-root-domain)
  also makes the root an explicit, durable member of the forest. These are the
  product precedents for explicit forest membership, root identity, and typed
  trust edges. RAES does not clone AD DS schemas, automatic intra-forest trust,
  administrative groups, sites, or replication behavior.
- **Federation lineage:** OpenID Connect, SAML, SCIM, and NIST SP 800-63C-4,
  already cited for identity-authority semantics, motivate separating a
  directory authority from the facade that exposes a federation protocol.
  RAES preserves portable direction, mapping intent, and claim ownership while
  leaving clients, credentials, provider mapper documents, and realized issuer
  state to deployment and evidence surfaces.
- **Placement lineage:** TOSCA's
  [`HostedOn` relationship](https://docs.oasis-open.org/tosca/TOSCA-Simple-Profile-YAML/v1.1/TOSCA-Simple-Profile-YAML-v1.1.html)
  is the direct topology precedent for preserving a logical node while
  expressing placement on a distinct host. RAES narrows that idea to an
  explicit carrier relation and kernel-boundary intent. It does not adopt
  TOSCA lifecycle operations or imply container namespace sharing.
- **Multi-tenancy lineage:** Kubernetes
  [multi-tenancy guidance](https://kubernetes.io/docs/concepts/security/multi-tenancy/)
  distinguishes tenant identity, control-plane and data-plane isolation,
  default-deny network policy, node isolation, workload identity, persistent
  storage boundaries, and deliberately shared services. RAES uses those
  distinctions to keep cell membership, cross-tenant posture, authentication,
  mutable-state ownership, and reset ownership separate. A deployment cell is
  not a Kubernetes namespace, cluster, cloud project, subnet, quota boundary,
  or proof that isolation was realized.

The resulting forest, facade, tenant, cell, endpoint-persona, and shared-service
vocabularies are RAES-native authoring contracts. The cited systems are
intellectual and implementation precedents, not schema authorities or
compatibility targets. Provider adapters still own allocation and
materialization; realized-form disclosures and evidence still own claims that
the declared identity, placement, isolation, authentication, state, and reset
properties actually occurred.

## DNS Service Runtime Semantics

The `runtime.dns_services` surface is issue #426's response to an observed
gap for DNS authoritative and recursive runtime inventory. It is not a clone
of any one DNS server configuration language, provider API, or DNS telemetry
format.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model scenario topology, deployable services/features, and validation or
  deployment concerns. They do not expose a portable first-class DNS zone,
  RRset, resolver-policy, or DNSSEC-posture inventory that RAES could reuse
  directly, so RAES introduces a typed node-scoped runtime surface rather than
  encoding the state inside `Node.services`, `runtime.applications`,
  `runtime.network`, or raw content files.
- **Primary DNS standards:** DNS concepts and record wire semantics come from
  [RFC 1035](https://www.rfc-editor.org/rfc/rfc1035). RRset grouping follows
  [RFC 2181](https://www.rfc-editor.org/rfc/rfc2181). Zone transfer and
  incremental transfer posture are informed by
  [RFC 5936](https://www.rfc-editor.org/rfc/rfc5936) and
  [RFC 1995](https://www.rfc-editor.org/rfc/rfc1995). DNSSEC posture follows
  [RFC 4033](https://www.rfc-editor.org/rfc/rfc4033),
  [RFC 4034](https://www.rfc-editor.org/rfc/rfc4034), and
  [RFC 4035](https://www.rfc-editor.org/rfc/rfc4035). SRV RDATA follows
  [RFC 2782](https://www.rfc-editor.org/rfc/rfc2782), dynamic update posture
  follows [RFC 2136](https://www.rfc-editor.org/rfc/rfc2136), and extension
  types are bounded by the
  [IANA DNS Parameters](https://www.iana.org/assignments/dns-parameters/dns-parameters.xhtml)
  registry. RAES adapts shared protocol concepts rather than importing raw
  zone-file syntax.
- **Server and configuration precedents:** BIND, NSD, Knot DNS, PowerDNS,
  CoreDNS, Terraform DNS providers, DNSControl, octoDNS, Kubernetes DNS, and
  Consul DNS show the recurring implementation facts RAES must preserve:
  authoritative zones, RRsets, forwarders, recursion controls, transfer policy,
  dynamic updates, DNSSEC validation/signing posture, and evidence sources.
  These references are implementation lineage, not schema authority.
- **Evidence and downstream consumers:** OCSF/ECS DNS fields, Zeek DNS logs,
  STIX domain-name objects, passive DNS, provider APIs, AXFR/IXFR captures,
  and backend inspect payloads remain evidence or downstream translation
  concerns. RAES records bounded runtime inventory and evidence refs; it does
  not make query telemetry or raw server config the SDL model.

Observed DNS names are preserved as data and are not case-folded. Portable
RAES references are stable `dns_service_id`, `zone_id`, and `rrset_id` symbols.
This follows the same validation posture used elsewhere in SDL: the model
states which protocol facts it can preserve, and it leaves server-specific
syntax as evidence rather than smuggling that syntax into untyped fields.

## Security-Monitoring Manager Runtime Semantics

The `runtime.security_monitoring_managers` surface is issue #428's response to
an observed gap for SIEM and security-monitoring manager inventory. It is not a
clone of Wazuh, Splunk, Elastic Security, Security Onion, Microsoft Sentinel,
or any one event schema. It is a portable node-scoped runtime inventory for the
manager facts that surrounding RAES surfaces cannot own.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model topology, deployable services/features, tasks, validation, and
  deployment concerns. None expose a portable first-class security-monitoring
  manager inventory. RAES therefore adds a typed `Node.runtime` surface rather
  than encoding manager state inside `Node.services`, `runtime.processes`,
  `runtime.service_manager_units`, `runtime.filesystem_inventory`, or raw
  content files.
- **Log-management and security-monitoring literature:** NIST SP 800-92 frames
  computer security log management as infrastructure and processes for
  collection, analysis, storage, maintenance, and operational use. RAES adapts
  that infrastructure/process split by recording manager identity, listeners,
  modules, agents, groups, content corpora, settings, and evidence refs without
  making log telemetry itself the SDL runtime inventory.
- **Implementation precedents:** Wazuh demonstrates the recurring manager
  concepts RAES must preserve: a central manager/server, agent connection and
  enrollment services, an analysis engine, manager API, agent groups and shared
  configuration, rules, decoders, queues, integrations, and manager components.
  These are implementation lineage and evidence sources, not schema authority.
- **Event and detection-content precedents:** OCSF is vendor-neutral event
  schema lineage, and Sigma is portable detection-rule lineage. They justify a
  product-neutral posture for content and telemetry vocabulary. RAES records a
  bounded parsed detection-definition manifest for loaded definitions, but it
  does not import OCSF events, raw Sigma rule bodies, Wazuh XML, SIEM queries,
  or alert records into SDL as first-class runtime records.

Portable RAES references are stable `security_monitoring_manager_id`, `listener_id`,
`component_id`, `agent_id`, `group_id`, `content_id`, `definition_id`, and
`setting_id` symbols. Native manager identifiers, daemon names, file names,
ruleset ids, rule ids, decoder names, agent labels, and API ids are preserved
as observed data or evidence when needed, but they are not automatically RAES
reference identity. Manager settings such as passwords, enrollment secrets, API
tokens, shared keys, keytabs, or private keys may be scenario values; explicit
`redacted`/`operator_secret` classifications omit raw values when the author
marks a value withheld.

The resulting model follows the same V&V posture as the DNS, mail, database,
file-service, and identity-authority surfaces: state which manager concepts
are stable enough to compare, target, and validate; keep vendor-specific
configuration, telemetry, rule-engine execution, and raw rule syntax as
evidence or downstream translation concerns.

## Generic Runtime Service Listener Semantics

The `runtime.service_listeners` surface is issue #431's response to an
observed gap in APTL's MISP container inventory. It is not a replacement for
authored services, host-published port bindings, protocol-specific runtime
inventories, or scanner output. It is the bounded node-scoped place for generic
observed listener facts: bind endpoint, port, transport, address family,
listener scope, owner, readiness evidence, and provenance.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model topology, deployable services/features, tasks, validation, and
  deployment concerns. They do not expose a portable first-class observed
  listener inventory with bind-address/interface semantics. RAES therefore
  adds a typed `Node.runtime` surface instead of hiding bind state in
  `Node.services`, `runtime.network.published_ports`, `runtime.applications`,
  or free-text descriptions.
- **Host and process-inventory precedents:** osquery's
  [`listening_ports`](https://fleetdm.com/tables/listening_ports) table keeps
  address, port, protocol, and owning PID as separate facts. systemd socket
  units such as
  [`ListenStream=` and `ListenDatagram=`](https://www.freedesktop.org/software/systemd/man/latest/systemd.socket.html)
  show the operational split between a socket endpoint and the service it can
  activate. RAES adapts that separation through `service`, `process_ref`, and
  listener endpoint fields without importing systemd unit syntax.
- **Container and orchestrator precedents:** Docker
  [port publishing](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/)
  separates a container-side listener from a host-side published binding.
  Kubernetes distinguishes container ports, Services,
  [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/),
  and readiness/liveness/startup
  [probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/).
  RAES keeps in-node listener state, host publication, and readiness evidence
  as adjacent but distinct runtime facts.
- **Evidence and telemetry precedents:** Nmap
  [XML output](https://nmap.org/book/output-formats-xml-output.html) can
  report remotely observed port state and service hints, but it cannot prove a
  local bind address or owning process by itself. OpenTelemetry server
  [address and port attributes](https://opentelemetry.io/docs/specs/semconv/attributes-registry/server/)
  and OCSF [network endpoint](https://schema.ocsf.io/) vocabulary are useful
  product-neutral checks for endpoint terminology. They remain evidence and
  downstream translation lineage rather than SDL schema authority.

Portable RAES references are stable listener ids under
`nodes.<node>.runtime.service_listeners.<listener_id>`. Native process names,
PIDs, scanner table names, service-manager unit names, and probe strings remain
observed data or evidence unless the author explicitly uses them in bounded ref
fields. A wildcard bind address inside a container or node namespace is not
automatically host-public; host exposure remains `runtime.network.published_ports`.

## Network Detection Engine Runtime Semantics

The `runtime.network_detection_engines` surface is issue #430's response to an
observed gap for IDS/NDR engine inventory. It is not a Suricata clone and does
not interpret rule languages or alert telemetry. It records portable,
node-scoped facts about a detection engine that adjacent surfaces cannot own:
enabled app-layer parser families, loaded rule-source inventories, network
zoning/address-set variables, bounded output streams, reload/control channels,
and evidence refs.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model topology, deployable services/features, tasks, validation, and
  deployment concerns. None expose a portable first-class detection-engine
  inventory. RAES therefore adds a typed `Node.runtime` surface rather than
  encoding engine state inside `Node.services`, `runtime.network_sensors`,
  `runtime.filesystem_inventory`, `runtime.software_components`, or prose
  relationships.
- **IDS/NDR tooling:** Suricata, Snort, Zeek, Security Onion, and NDR products
  show recurring engine facts RAES must preserve: parser coverage, rule or IOC
  sources, address sets, output streams, reload controls, and evidence refs.
  These references are implementation lineage, not schema authority.
- **Telemetry and rule-content precedents:** OCSF, ECS, STIX, Sigma, YARA, and
  vendor rule formats inform vocabulary boundaries. RAES does not replace
  those schemas or inline their events, rules, packets, or IOC payloads.
- **Evidence discipline:** raw rules, alerts, packet captures, IOC exports,
  config files, and backend inspect payloads remain evidence artifacts or
  downstream translation inputs. The SDL stores bounded inventory and refs.

## Application-Internal Authorization Semantics

The `runtime.app_authorizations` surface is the SCN-010 response to the
most-replicated expressivity gap in the corpus: application-internal RBAC that
recurs across search clusters, key-value stores, dashboards, threat-intel
platforms, and case-management systems. It is deliberately not a wire-protocol
directory (that stays `runtime.identity_authorities`) and not a database engine
GRANT surface (that stays `runtime.database_services`). Its defining addition is
the resource-scoped permission grant — role → actions → resource pattern — that
neither adjacent surface can own.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model topology, deployable services/features, and validation/deployment
  concerns. None expose a portable first-class application-internal RBAC store,
  so RAES adds a typed node-scoped seam rather than overloading
  `runtime.identity_authorities`, `runtime.database_services`, or
  `runtime.applications`.
- **Primary RBAC and ABAC standards:** Ferraiolo and Kuhn's
  [Role-Based Access Controls](https://www.nist.gov/publications/role-based-access-controls),
  Sandhu et al.'s [RBAC96 model](https://doi.org/10.1109/2.485845),
  [ANSI INCITS 359](https://webstore.ansi.org/standards/incits/ansiincits3592004)
  (the RBAC standard), and NIST
  [SP 800-162](https://csrc.nist.gov/publications/detail/sp/800-162/final) ABAC
  supply the model's spine: principals, roles, role-permission assignment,
  user-role assignment, and resource-scoping. The resource-scoped
  `permission_grant` is anchored by RBAC96 / ANSI INCITS 359
  permission-assignment and SP 800-162 resource-scoping; tier placement
  (storage RBAC versus presentation RBAC) is derived from which spine references
  the authorization, not declared on the model.
- **Product RBAC precedents:** OpenSearch Security, Elasticsearch security,
  Cassandra `system_auth`, Redis ACLs, Kibana/OpenSearch Dashboards roles,
  MISP/TheHive/Cortex role catalogs, and Shuffle RBAC show recurring facts RAES
  must preserve: principals with reserved/hidden flags, named roles,
  resource-scoped grants, role mappings, and tenants. These are implementation
  lineage, not schema authority.
- **Credential discipline:** raw bcrypt hashes, API keys, and passwords are
  never stored. A principal records only a `credential_classification`
  (`none` / `redacted` / `operator_secret`), and the model has no field that can
  hold a raw secret.

## Scheduled-Job Cadence Semantics

The `runtime.scheduled_jobs` surface is the SCN-010 response to the gap for
recurring node-scoped work (gap IDs MISP-DSS-02 / TIP-004) that
`runtime.service_manager_units` cannot express: a bare-container ENTRYPOINT
cadence loop has no systemd unit. The surface is deliberately hollowed to
cadence plus run-state only; inputs, outputs, and trigger targets belong to the
referencing forwarding agent, and an event-triggered task is a trigger
relationship rather than a recurrence.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model topology, deployable services/features, and validation/deployment
  concerns. None expose a portable first-class product-neutral scheduled-job
  cadence, so RAES adds a typed node-scoped seam rather than overloading
  `runtime.service_manager_units` (systemd-scoped) or the forwarding agent.
- **Primary recurrence standards:** POSIX.1-2017
  [crontab](https://pubs.opengroup.org/onlinepubs/9699919799/utilities/crontab.html)
  and RFC 5545 [iCalendar RRULE](https://www.rfc-editor.org/rfc/rfc5545) supply
  the product-neutral recurrence vocabulary that the closed `schedule.kind`
  (`interval` / `cron` / `calendar`) abstracts.
- **Scheduler precedents:** systemd
  [`systemd.timer`](https://www.freedesktop.org/software/systemd/man/systemd.timer.html)
  and Kubernetes
  [CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
  show recurring scheduler facts RAES must preserve as cadence and run-state.
  These are implementation lineage, not schema authority.
- **Run-state observability:** NIST
  [SP 800-92](https://csrc.nist.gov/publications/detail/sp/800-92/final)
  (log management) and
  [SP 800-137](https://csrc.nist.gov/publications/detail/sp/800-137/final)
  (continuous monitoring) frame the observed `run_state`
  (`last_run` / `next_run` / `last_result`) as monitoring evidence rather than
  control intent.

## Non-Relational Datastore Semantics

The `runtime.datastore_services` surface is the SCN-010 (DSL-132) response to a
gap for the participant-observable logical state of *non-relational* datastores
— the search cluster, wide-column store, and key-value store that the
irreducibly-relational `runtime.database_services` cannot shape. Its defining
addition is the open `data_model` discriminator paired with a
`require_profile_for_data_model` guard that makes each data model's defining
geometry (search shard/replica counts, wide-column replication, key-value
persistence, and bounded search-index mapping manifests) executable rather than
optional. Search-index mappings and templates are captured as bounded manifests
with counts, summaries, digests, refs, and evidence pointers rather than as raw
backend JSON bodies.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model topology, deployable services/features, and validation/deployment
  concerns. None expose a portable first-class non-relational datastore logical
  state, so RAES adds a typed node-scoped seam rather than overloading
  `runtime.database_services` (irreducibly relational), `Node.services`
  (transport), or `runtime.software_components` (component identity).
- **Primary data-model and consensus standards:** Codd's relational model
  ([CACM 13(6)](https://doi.org/10.1145/362384.362685)) and
  [ISO/IEC 9075](https://www.iso.org/standard/76583.html) (SQL) bound what stays
  relational; Zobel and Moffat's
  [inverted-index survey](https://doi.org/10.1145/1132956.1132959) anchors the
  search-index shard/replica geometry; Ongaro and Ousterhout's
  [Raft](https://raft.github.io/raft.pdf) and Gilbert and Lynch's
  [CAP proof](https://doi.org/10.1145/564585.564601) anchor cluster/replication
  posture.
- **Engine precedents:** Lakshman and Malik's
  [Cassandra](https://doi.org/10.1145/1773912.1773922), DeCandia et al.'s
  [Dynamo](https://doi.org/10.1145/1323293.1294281), Chang et al.'s
  [Bigtable](https://research.google/pubs/pub27898/), and Redis
  [RESP3](https://github.com/redis/redis-specifications/blob/master/protocol/RESP3.md)
  / [ACL](https://redis.io/docs/management/security/acl/) /
  [persistence](https://redis.io/docs/management/persistence/) show recurring
  facts RAES must preserve: keyspaces with replication strategy/factor, search
  shard/replica geometry, and RDB/AOF/eviction persistence. These are
  implementation lineage, not schema authority.
- **Hardening and transport discipline:** NIST
  [SP 800-92](https://csrc.nist.gov/publications/detail/sp/800-92/final),
  [SP 800-53](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final),
  and [SP 800-209](https://csrc.nist.gov/publications/detail/sp/800-209/final)
  (storage security), with [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446)
  (TLS 1.3) and [RFC 5280](https://www.rfc-editor.org/rfc/rfc5280) (PKIX), frame
  the transport-security posture and explicit redaction classifications. Raw
  key material and credentials may be scenario-realization facts when they
  belong to the synthetic range; out-of-scenario operator secrets remain
  outside SDL inventory.

The node-scoped extension (SCN-010 DSL-141,
[ADR-058](../../decisions/adrs/adr-058-datastore-node-engine-provenance-and-endpoints.md))
closes the `wazuh.indexer` parity gap (Brad-Edwards/aptl#341) that ADR-048 left
at the node level: typed engine provenance (version, build hash, build type),
JVM/process memory posture (initial/maximum heap bytes, `mlockall`), a per-node
engine-plugin inventory with per-plugin version, and a product-neutral
client/peer endpoint inventory. The Elasticsearch/OpenSearch
[Nodes Info API](https://www.elastic.co/guide/en/elasticsearch/reference/current/cluster-nodes-info.html)
reports each of these per node; the client/peer listener split is structural
across the search-cluster tech class (OpenSearch http/transport, Cassandra
native/internode, Redis client/cluster-bus), which is why RAES types an
engine-neutral `role` taxonomy rather than engine-named address fields.

## Security-Platform Application Semantics

The `runtime.platform_applications` surface is the SCN-010 (DSL-133) response to
a gap for the declared logical state of participant-visible platform
applications. Issue #956 corrected the original product-category model: an open
`platform_kind` plus required product-shaped content profile could neither
represent multi-role applications nor prove configuration completeness. The
current authority is a provider-neutral, composable `capabilities` collection.
`platform_kind` and `content_objects` remain deprecated compatible input and
neither implies the other.

RAES relies on prior work in four ways:

- **Internal and scenario-language precedents:** ADR-032 is the direct internal
  precedent: an Active Directory scenario produced a provider-neutral
  identity-authority core, with vendor identifiers retained as data. Open Cyber
  Range SDL, CyRIS, KYPO, VSDL, and CRACK model topology, deployable
  services/features, and validation/deployment concerns but do not define a
  portable application-capability inventory. TOSCA and CAMP distinguish
  capabilities, requirements, artifacts, and configuration. RAES applies that
  separation at its existing node-runtime boundary rather than claiming format
  compatibility or overloading `runtime.applications` (HTTP routes) and
  `runtime.software_components` (component identity).
- **Content and intelligence-sharing boundaries:** RDF 1.1
  ([concepts](https://www.w3.org/TR/rdf11-concepts/)) with Angles and Gutierrez's
  [graph-database survey](https://doi.org/10.1145/1322432.1322433) frame typed
  references over raw bodies.
  [STIX 2.1](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html) /
  [TAXII 2.1](https://docs.oasis-open.org/cti/taxii/v2.1/taxii-v2.1.html), the
  [MISP data model](https://www.misp-project.org/datamodels/), FIRST
  [TLP 2.0](https://www.first.org/tlp/), MITRE
  [ATT&CK](https://attack.mitre.org/), NIST
  [SP 800-150](https://csrc.nist.gov/publications/detail/sp/800-150/final), and
  [ISO/IEC 27010](https://www.iso.org/standard/68427.html) distinguish
  intelligence content, exchange, marking, and sharing concerns; NIST
  [SP 800-61r2](https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final)
  / [r3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) frames incident
  handling. These sources motivate separate functional roles; none defines a
  required RAES product profile. Initial authored content and portable
  search-index field-schema state stay under top-level `content` and the closed
  `service_materialization` profiles per ADR-088. Native field types and mapping
  bodies do not cross that boundary.
- **Automation and presentation precedents:** OASIS
  [CACAO v2.0](https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.html)
  and [OpenC2](https://docs.oasis-open.org/openc2/oc2ls/v1.0/oc2ls-v1.0.html)
  separate playbooks, commands, agents, and targets. RAES therefore records
  `workflow_automation` and `analysis_execution` capability roles without
  importing playbook/action execution semantics. NIST
  [SP 800-92](https://csrc.nist.gov/publications/detail/sp/800-92/final) and
  [ISO/IEC/IEEE 42010](https://www.iso.org/standard/74393.html) frame the
  presentation and monitoring context. These are design precedents, not schema
  authority.
- **Transport and federation discipline:** [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110)
  (HTTP semantics), [RFC 7239](https://www.rfc-editor.org/rfc/rfc7239)
  (forwarded), and [RFC 6749](https://www.rfc-editor.org/rfc/rfc6749) (OAuth 2.0)
  bound connector, binding, and authorization posture. Sharing/distribution
  policy does not become an application capability, and raw bodies,
  credentials, and key material remain outside the surface.

The six initial capability kinds are RAES-native semantic categories:
`threat_intelligence_management`, `intelligence_exchange`, `case_management`,
`analysis_execution`, `workflow_automation`, and `analytics_presentation`.
Products such as MISP, OpenCTI, TheHive, Cortex, Shuffle, and Kibana are examples
and evidence only. The lineage is inspirational rather than a derivation or
compatibility claim; the normative authority remains the RAES contract and
ADR-049.

## Forwarding And Intel-Sync Agent Semantics

The `runtime.forwarding_agents` surface is the SCN-010 (DSL-136) response to a
gap for the participant-observable agent-side shipping state — the
`(source, transform, ship-target, buffer)` spine of a log-forwarding sidecar and
the intel-sync co-process — that the SIEM/security-monitoring *manager*
(`runtime.security_monitoring_managers`) and the detection-engine *consumer*
(`runtime.network_detection_engines`) provably cannot shape. Its defining
addition is the open `agent_kind` discriminator paired with a
`require_profile_for_agent_kind` guard that makes each member's defining shipping
profile executable rather than optional.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model topology, deployable services/features, and validation/deployment
  concerns. None expose a portable first-class forwarding-agent shipping
  inventory, so RAES adds typed node-scoped and scenario-level seams rather than
  overloading the manager surface, the detection-engine surface, or
  `runtime.scheduled_jobs` (cadence-only).
- **Primary log-transport standards:** The syslog family —
  [RFC 5424](https://www.rfc-editor.org/rfc/rfc5424) (syslog protocol),
  [RFC 5425](https://www.rfc-editor.org/rfc/rfc5425) (TLS transport),
  [RFC 6587](https://www.rfc-editor.org/rfc/rfc6587) (TCP framing), and
  [RFC 3164](https://www.rfc-editor.org/rfc/rfc3164) (BSD syslog) — bound the
  ship-target protocol/endpoint posture, while NIST
  [SP 800-92](https://csrc.nist.gov/publications/detail/sp/800-92/final) anchors
  the source → collector → aggregator pipeline shape and NIST
  [SP 800-137](https://csrc.nist.gov/publications/detail/sp/800-137/final) (ISCM)
  frames continuous-monitoring collection as a defining concern.
- **Intel-to-content precedents:**
  [STIX 2.1](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html) /
  [TAXII 2.1](https://docs.oasis-open.org/cti/taxii/v2.1/taxii-v2.1.html), NIST
  [SP 800-150](https://csrc.nist.gov/publications/detail/sp/800-150/final), Bianco's
  [Pyramid of Pain](https://detect-respond.blogspot.com/2013/03/the-pyramid-of-pain.html),
  and MITRE [ATT&CK](https://attack.mitre.org/) frame the `ioc_to_rule`
  intel-sync transform — the API-pull-to-rule-reload shape — that the
  `content_sync` profile makes executable.
- **Forwarder implementation lineage:** Elastic
  [Beats](https://www.elastic.co/beats/) and the
  [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) show the
  recurring source/transform/ship/buffer facts RAES preserves (tailed inputs,
  pipelines, exporters, back-pressure queues). These are implementation lineage,
  not schema authority; enrollment identities carry only their closed
  classification lattice, while forwarding settings use explicit redaction
  classifications rather than name-derived omission.

## Container-Spawn Orchestration-Authority Semantics

The `runtime.orchestration_authorities` surface is the SCN-010 (DSL-137) response
to a gap for the participant-observable authority to *spawn* containers/workloads
through a control interface — a SOAR orchestrator or analyzer engine holding
`docker.sock` read-write. `RuntimeControlInterface` types the docker.sock *shell*
but carries no field for what the holder is authorized to *do*; this surface adds
the spawn contract (engine, scope, spawn templates, lifecycle policy, realized
children) referencing that shell, paired with a `require_profile_for_privilege_class`
guard that makes the host-root privilege-escalation fact executable.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model topology, deployable services/features, and validation/deployment
  concerns. None expose a portable first-class container-spawn authority
  inventory, so RAES adds a typed node-scoped seam referencing the existing
  `runtime.local_control_interfaces` shell rather than duplicating it.
- **Primary runtime and orchestration standards:** The OCI
  [Runtime Spec](https://github.com/opencontainers/runtime-spec) and
  [Image Spec](https://github.com/opencontainers/image-spec) bound the engine /
  spawn-template posture, and the Kubernetes
  [controller pattern](https://kubernetes.io/docs/concepts/architecture/controller/)
  anchors the desired-state spawn-template / realized-children reconciliation
  shape this surface records as observed state.
- **Privilege and hardening precedents:** NIST
  [SP 800-190](https://csrc.nist.gov/publications/detail/sp/800-190/final)
  (container security) and the
  [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker) 5.x control
  family frame the read-write `docker.sock` exposure as a host-root-equivalent
  privilege escalation, and MITRE ATT&CK
  [T1610](https://attack.mitre.org/techniques/T1610/) (Deploy Container) and
  [T1611](https://attack.mitre.org/techniques/T1611/) (Escape to Host) anchor the
  adversary relevance the `host_root_equivalent` profile makes executable.
- **Engine API lineage:** The
  [Docker Engine API](https://docs.docker.com/engine/api/) shows the spawn /
  lifecycle surface (container create/start/stop, image references) RAES records
  as inventory. This is implementation lineage, not schema authority; the spawn
  contract is referenced through `control_interface_ref`, never duplicating the
  control-interface shell.

## File-Sharing And Resource-Access Semantics

The `runtime.file_services` surface is issue #421's response to a gap
observed while encoding the APTL TechVault fileshare container. It is not
a clone of any one file-sharing protocol or ACL vocabulary, and the
expected-but-absent extension to `runtime.filesystem_inventory` follows
the same posture.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and
  CRACK model scenario topology, deployable services/features, and
  validation/deployment concerns. None expose a portable first-class
  share-permission/passdb inventory that RAES could reuse directly, which
  is why RAES introduces a typed node-scoped seam rather than encoding the
  state inside `Node.services` or `runtime.applications`.
- **Primary protocol and filesystem-permission standards:** Microsoft's
  [MS-SMB2](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-smb2/5606ad47-5ee0-437a-817e-70c366052962),
  [SMB/CIFS overview](https://learn.microsoft.com/en-us/windows/win32/fileio/microsoft-smb-protocol-and-cifs-protocol-overview),
  the Samba [`smb.conf`](https://www.samba.org/samba/docs/current/man-html/smb.conf.5.html)
  and [`pdbedit`](https://www.samba.org/samba/docs/current/man-html/pdbedit.8.html)
  references, the Linux [ACL man page](https://man7.org/linux/man-pages/man5/acl.5.html),
  POSIX.1e ACL semantics (Grünbacher,
  [POSIX Access Control Lists on Linux](https://www.usenix.org/legacy/event/usenix03/tech/freenix03/full_papers/gruenbacher/gruenbacher.pdf),
  USENIX ATC 2003), Microsoft's
  [Windows ACL documentation](https://learn.microsoft.com/en-us/windows/win32/secauthz/access-control-lists)
  and [security descriptor string format](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-string-format),
  and [NFSv4.1 (RFC 8881)](https://www.rfc-editor.org/rfc/rfc8881) supply
  terminology for shares/exports, share-level access modes, passdb
  semantics, anonymous and guest subjects, POSIX vs. Windows ACL
  families, and NFSv4 ACEs. RAES adapts their shared concepts (subject, resource,
  action, effect, basis) rather than importing any single vendor ACL
  algebra. The access-control literature already cited above
  (Lampson, Saltzer/Schroeder, RBAC96, NIST ABAC) justifies that
  subject/resource/action/policy/observation split.
- **Resource-relation modeling:** Pang et al.'s
  [Zanzibar: Google's Consistent, Global Authorization System](https://research.google/pubs/zanzibar-googles-consistent-global-authorization-system/)
  (USENIX ATC 2019) is design input for portable relationship-tuple
  authorization. RAES uses it as a cross-check that bounded
  subject/relation/resource records are workable at scale; it is not
  forced into the SDL as a global authorization framework, and RAES does
  not encode share access only as relationship edges.
- **Evidence and downstream consumers:** OCSF, UCO, CASE, STIX, and SBOM
  standards remain evidence/event/concept influences (already discussed
  above). Per-share probe outcomes are recorded as evidence-bearing
  observations under the file-service inventory; they support but do not
  silently replace authored share policy.

`RuntimeFilesystemEntry.presence` is grounded in the same V&V posture as
the identity-authority surface: an inventory model should preserve the
distinction between present-observed state and expected-but-absent state
rather than collapsing both into a single field. Russo/Costa/Armando,
Oberkampf/Roy, and Sargent's V&V sources cited above are the methodological
backing — what a model can or cannot represent must be explicit so
downstream completeness/conformance checks can act on it.

## Mail-Service Logical State Semantics

The `runtime.mail_services` surface is issue #420's response to a gap observed
while encoding the APTL TechVault mailserver container. It is not a clone of
Postfix, Dovecot, Docker Mailserver, or an RFC object tree. It is a portable
node-scoped runtime inventory for mail-service logical facts that surrounding
RAES surfaces cannot own.

RAES relies on prior work in four ways:

- **Scenario-language precedents:** Open Cyber Range SDL, CyRIS, KYPO, VSDL, and CRACK
  model topology, deployable services/features, accounts, tasks, and
  validation/deployment concerns. None expose a portable first-class
  mail-server logical-state inventory, which is why RAES adds a typed
  `Node.runtime` surface rather than encoding SMTP/IMAP state inside
  `Node.services`, `runtime.applications`, filesystem entries, content, or
  generic accounts.
- **Protocol and service concepts:** SMTP transport/delivery, message
  submission, IMAP access, POP3/LMTP/Sieve extension points, TLS/STARTTLS
  posture, mailboxes, aliases, domains, queues, and MTA/MDA configuration
  supply terminology. RAES adapts these as provider-neutral fields for
  listeners, capabilities, auth mechanisms, mailbox state, routing, queues, and
  settings.
- **Evidence and redaction lineage:** Mailserver discovery output, `postconf`
  and `doveconf` command output, compose files, setup scripts, filesystem
  inventory, and participant probes are evidence/provenance sources. They do
  not become raw config dumps in SDL. Secret-bearing settings must omit values,
  and mailbox records carry credential-strength classification rather than
  passwords or hashes.
- **Relationship semantics:** STIX-style typed edges
  ([OASIS STIX 2.1](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html)
  SRO) remain the top-level relationship surface. `RelationshipMailAccess` adds
  mail-specific protocol/auth/TLS/mailbox/domain/listener details to those edges
  without promoting mail relationships into a new root section. Three further
  typed subtypes follow the same discipline (SCN-010 §5.7, ADR-052):
  `RelationshipForwardingEdge` carries a forwarding / intel-sync agent's
  inter-node trust edge (anchored in RFC 5424 / 5425 / 6587 / 3164 syslog
  transport and NIST SP 800-92 source -> collector tiering, reusing the
  manager-side `RuntimeSecurityMonitoringListenerRole` lattice rather than
  forking one); `RelationshipServiceIntegration` carries a platform
  consumer-to-engine integration (anchored in NIST SP 800-92 and RFC 6749
  OAuth 2.0 for the API-key auth principal); and `RelationshipProxyUpstream`
  carries a reverse-proxy / gateway route-to-origin hop (anchored in RFC 9110 /
  RFC 7239, NIST SP 800-44, and the Kubernetes Ingress / Gateway API origin
  model). None of the three promotes its edge into a new root section; cross-ref
  resolution and the two cross-scope agreement guards live in the semantic
  validator (see validation.md).

The result preserves the same V&V posture as database and file-service runtime
surfaces: RAES states which mail concepts are stable enough to compare and
which dynamic queue/log/config details remain evidence or bounded settings.

## Participant Semantics

- [OpenAI Gym](https://arxiv.org/abs/1606.01540),
  [Gymnasium](https://arxiv.org/abs/2407.17032),
  [PettingZoo](https://arxiv.org/abs/2009.14471),
  and [OpenSpiel](https://arxiv.org/abs/1908.09453) inform the agent-facing
  interface vocabulary: actions, observations, rewards, resets, local histories,
  imperfect information, and multi-agent interaction.
- POMDP, Dec-POMDP, POSG, and Markov-game literature — with
  [Bernstein, Givan, Immerman, and Zilberstein's complexity result](https://doi.org/10.1287/moor.27.4.819.297)
  and [Oliehoek and Amato's Dec-POMDP monograph](https://doi.org/10.1007/978-3-319-28929-8)
  as anchors — is the theoretical lineage behind RAES's insistence that
  participant-visible observations are not world truth, and that
  multi-participant behavior cannot be reduced to a single centralized state
  stream. [Mean-field game theory](https://doi.org/10.1007/s11537-007-0657-8)
  covers the population-limit regime RAES records as mean-field nodes.
- Interpreted systems
  ([Fagin, Halpern, Moses, Vardi](https://mitpress.mit.edu/9780262562003/reasoning-about-knowledge/)),
  [dynamic epistemic logic](https://doi.org/10.1007/978-1-4020-5839-4), and
  [Kuhn's extensive-form information sets](https://doi.org/10.1515/9781400881970-012)
  are the formal lineage for participant information states, view transitions,
  and perfect-recall claims.
  [Goguen-Meseguer noninterference](https://doi.org/10.1109/SP.1982.10014) and
  [Sabelfeld-Sands declassification](https://doi.org/10.3233/JCS-2009-0352)
  ground the hidden-truth boundary and disclosure-rule semantics.
- SEM-230 adopts that lineage through RAES-native artifacts rather than source
  syntax or wire compatibility. The normative participant-policy model is
  `specs/formal/participant-semantics/information-flow-control.md`; the
  machine-readable relation is `policy-noninterference` in behavioral taxonomy
  revision `rev8`; and the claim surface is
  `participant-information-flow-policy`. Existing `W`, `V`, qualified `H`,
  `X`, participant action/admission, visibility transition, ordering, marking,
  controller, authority, evidence, and provenance objects remain the mapped
  RAES carriers. No generic participant-message or policy payload is derived
  from either publication.
- The derivation is deliberately compositional. Fagin, Halpern, Moses, and
  Vardi supply participant-local information-state/indistinguishability
  semantics; Goguen and Meseguer supply noninterference and purge; Sabelfeld
  and Sands supply the declassification dimensions; Milner and van Glabbeek
  supply labelled-transition, hidden-action, and relation-separation
  discipline; Clarkson and Schneider distinguish trace properties from
  hyperproperties; and Bohannon et al. supply the reactive strategy-sensitive
  information-flow precedent. Lamport happened-before, Winskel event
  structures, and Mazurkiewicz trace theory enter indirectly through the
  already governed ADR-054 visible-order model. RAES extends those sources
  only with participant/audience, exact-cut policy-decision, participant-memory,
  controller/authority, marking, and evidence/provenance coordinates needed to
  bind existing RAES carriers. It does not fork their settled definitions.
- Delivery status is definition-complete, catalogued, policy-checked, and
  bounded-tested over finite open-loop and adaptive-strategy cases. Evidence
  is the SEM-230 formal specification,
  `contracts/concept-authority/behavioral-relations-v1.json`,
  `tools/check_behavioral_relation_claims.py`, and
  `implementations/python/tests/test_sem_230_information_flow_control.py`.
  Production enforcement, backend realization, and universal proof remain
  undelivered. In particular, equal projected histories and finite leakage
  cases do not establish universal noninterference, trace equivalence,
  simulation, refinement, bisimulation, epistemic indistinguishability, timed
  security, or probabilistic security.
- Issue #810 and SEM-231 adapt the predicate-opacity literature through
  RAES-native possible-point and relation-profile coordinates. Bryans et al.
  supply the predicate/observation kernel; Schoepe and Sabelfeld supply its
  one-sided knowledge characterization, symmetric variant, and exact
  noninterference boundary; Lin and Saboori-Hadjicostis supply current,
  historical, and infinite-step scope distinctions; Badouel et al. and Xie et
  al. expose supervisory visibility and nondeterministic control; Broberg et
  al. supply dynamic release and replay distinctions. The active-intruder work
  of Partovi et al. and the unknown-supervisor work of Cui et al. are explicitly
  preprints used as design criteria, not sole authority.
- The exact issue #810 mapping is
  `specs/formal/participant-semantics/participant-predicate-opacity.md`,
  ADR-099, the `participant-predicate-opacity` relation and
  `participant-opacity` claim surface in
  `contracts/concept-authority/behavioral-relations-v1.json`, the shared
  revisioned relation-parameter profile and assurance-axis binding, the
  literature/current-state/requirement/program artifacts under
  `docs/research/participant-opacity/`, and the four bounded structural cases
  in `test_sem_231_participant_predicate_opacity.py` and
  `test_issue_810_participant_opacity_design.py`.
- RAES keeps opacity distinct from SEM-230 policy noninterference,
  participant-projected-history equality, epistemic indistinguishability,
  trace equivalence, and bisimulation. Issue #961 delivers the closed baseline
  profile and bounded checker. Issue #962 delivers a distinct explicit-state
  checker and a model-check result for one exact complete finite fixture model.
  No mathematical proof, runtime enforcement, supervisor synthesis, backend
  declaration, backend realization, bounded backend conformance,
  probabilistic security, timed security, partial-order security, or
  all-schedule result is delivered. Issues #963 through #965 own those
  remaining independent lanes.
- Issue #811 and SEM-232 adapt van Glabbeek and Weijland's branching
  bisimulation and van Glabbeek, Luttik, and Trčka's explicit-divergence
  treatment to the bounded RAES participant-crossing kernel. The exact mapping
  is ADR-100,
  `specs/formal/participant-semantics/participant-crossing-bisimulation.md`,
  `divergence-preserving-branching-bisimulation` and the
  `participant-crossing-bisimulation` claim surface in behavioral taxonomy
  revision `rev8`, and the theorem/tool/evidence/program records under
  `docs/research/participant-bisimulation/`.
- The selected theorem compares a complete finite abstract SEM-230 crossing
  LTS with an independently derived formal API-423/RUN-319 crossing-kernel
  LTS. It hides only finite validation, cut-resolution, effective-capability,
  record-preparation, and atomic-commit classes under a closed
  participant/audience projection and preserves explicit divergence. Issue
  #811 defines the target but does not run it. Issues #971 through #976 own
  model construction, live-runtime mapping, counterexamples, finite mCRL2
  checking, independent reproduction, and reproduction-gated scientific
  documentation.
- RAES does not derive whole-runtime or backend equivalence, policy
  noninterference, or opacity from this design. Runtime realization and
  backend conformance remain separate axes; noninterference and opacity
  require their own profile-matching preservation theorem.
- ACT-617 applies the already adopted SEM-230/ADR-085 control and ordering
  lineage to authored mixed-control behavior without introducing another
  external derivation. The exact RAES mapping is
  `ParticipantBehaviorSpecification.mixed_control` for the revisioned policy,
  keyed typed controller states for participant/controller, authority, scope,
  validity, revocation, and evidence coordinates, keyed typed control
  transitions for proposal, approval/denial, direction, intervention,
  handoff, override, and cancellation, and nested
  `ParticipantBehaviorSpecificationRuntime.controller_states` /
  `control_transitions` for deterministic compiled addresses and
  dependencies. `SemanticValidator` owns fail-closed identity, authority,
  scope, revision, validity, order, proposal, revocation, and handoff checks;
  module composition rewrites external refs while preserving local state and
  transition identities.
- ACT-617 delivery evidence is the governed SDL schemas and publication
  manifest, the valid/invalid mixed-control fixtures, and
  `implementations/python/tests/test_act_617_mixed_control.py`. This delivers
  authored and compiled policy semantics only. It does not claim portable
  occurrence/wire contracts, action admission, execution, observation,
  runtime mediation or persistence, backend enforcement, distributed/partial
  ordering, policy noninterference, or universal correctness. Because the
  implementation reuses the revision-pinned SEM-230 lineage without changing
  its normative derivation or compatibility claims, the SDL lineage ledger
  and source audit remain unchanged.
- DSL-142 composes the existing orchestration-inject, participant-observation,
  SEM-230 information-flow, ACT-617 mixed-control, shared-time, and evidence
  lineages without introducing another external derivation. The exact RAES
  mapping is
  `ParticipantBehaviorSpecification.participant_inject_deliveries`: one
  participant, the original inject and event/script/story occurrence
  identities, source/result item identities, an observation boundary, a
  revisioned audience/exposure/visibility/disclosure policy, the
  orchestration-occurrence-and-shared-time order basis, temporal and evidence
  bindings, fail-closed disposition, and an optional compatible mixed-control
  transition. Direction/intervention bindings repeat the controller, target
  authority scope, effective order, validity interval, and evidence basis so
  admission can reject disagreement and incompatible time/evidence coverage.
  Module composition rewrites external references while preserving local
  binding and control-transition identities; compilation emits canonical typed
  addresses without copying hidden inject bodies or environment commands into
  participant metadata.
- DSL-142 delivery evidence is the governed SDL schemas and publication
  entries, the valid/invalid participant-inject delivery fixtures, and
  `implementations/python/tests/test_dsl_142_participant_inject_delivery.py`.
  This delivers authoring, composition, semantic and post-instantiation
  validation, deterministic compilation, and schema compatibility. It does not
  claim runtime delivery, wire or receipt contracts, persistence, backend
  realization, proof of observation, or universal information-flow security.
  Because it only binds already governed carriers and does not change their
  normative derivation or compatibility claims, the SDL lineage ledger and
  source audit remain unchanged.
- DSL-437 composes the incumbent participant and time lineages rather than
  introducing a live-activity ontology. CybORG and the Gymnasium, PettingZoo,
  and OpenSpiel family remain precedents for agents, actions, observations,
  episodes, and multi-agent interaction. ADR-090's reviewed ROS 2, FMI, HLA,
  TENA, and OpenSCENARIO sources remain the precedent for shared clock
  authority, progression, lifecycle, and scheduler coordination.
  `ParticipantBehaviorSpecification.autonomous_execution` is RAES-native: it
  binds ordinary participant/action/observation declarations to those existing
  shared-time declarations and participant implementation provenance.
- The exact DSL-437 authority is ADR-092 and
  `specs/formal/participant-semantics/autonomous-execution.md`; implementation
  evidence covers the SDL model, semantic validator, compiler, exact
  fail-closed admission, RuntimeManager shared-clock execution, native binding
  and scheduler-enforced terminal coordinate-bound action outcomes for every
  protocol implementation, exclusive ownership and
  resolved-time policy identity, runtime-owned real-time/dilated cadence
  driving for runtime-authority clocks, manifest-admitted transactional
  clock/participant reset, lifecycle reporting, and durable/API/conformance
  clock/episode/scheduler consistency on both save and load. Externally paced
  autonomous policies remain rejected until RAES governs a portable
  backend-to-runtime transition driver. The
  focused evidence is in `test_dsl_437_benign_participant_execution.py`,
  `test_dsl_437_evaluation_authority.py`, and
  `test_dsl_437_snapshot_durability_conformance.py`. The ledger records exact
  semantic source boundaries for the participant-interface and shared-time
  concerns. The coordinated reset method is an RAES backend transaction
  obligation, not a claim that replacing a local snapshot reverses native
  backend effects.
  RAES does not claim CybORG, Gymnasium, PettingZoo, OpenSpiel, ROS, FMI, HLA,
  TENA, or OpenSCENARIO compatibility and does not derive a source wire schema.
  Historical files remain ordinary initial service state; injects remain
  exercise orchestration; stochastic participant implementations remain
  governed run apparatus.
- Issue #898 extends that same DSL-437 lineage across a remote backend control
  boundary. It keeps authored behavior, participant episodes, scheduler
  continuation, execution-service lifecycle, shared time, native action
  outcome, and control-plane operation status distinct. FMI Scheduled
  Execution, gRPC health checking, Google long-running operations, Kubernetes
  generation-bound conditions, and TOSCA lifecycle interfaces are operational
  design precedents only. RAES retains its own contracts and requires exact
  action-to-target bindings, generation-checked lifecycle/readback, bounded
  RUN-308 concurrency evidence, existing operation receipts/statuses, and
  existing time-state/provenance. It claims no wire, API, lifecycle-token, or
  behavioral compatibility with those sources.
- Issues #811 and #812 define proof-bearing bisimulation and adversarial
  threat-model extensions. Issue #813 and ADR-102 now define the mixed
  cross-backend composition extension. It supports both alternative
  simulation/emulation realization and simultaneous mixed realization, plus
  linked inter-trial and finite pre-admitted within-run changes. SEM-234 and
  ASR-537 remain DRAFT; #1013 through #1019 own semantic, contract, trial,
  runtime, backend, demonstration, and claims work. Revision 1 keeps one
  acting controller and rejects lease, simultaneous scoped-owner, and
  joint/fused-control claims. Issue #810 defines opacity and
  supervisor-visibility architecture only; #961 delivers its bounded checker,
  #962 delivers its exact finite-model checker, and #963 through #965 own the
  proof, runtime, and backend lanes. SEM-230 preserves every extension's
  participant, audience, policy revision, declassification,
  controller/authority, scheduler/environment, timing/probability, order, and
  evidence coordinates; none of these extension seams is evidence of runtime
  or backend realization.
- [STRIPS](https://doi.org/10.1016/0004-3702(71)90010-5),
  [PDDL](https://doi.org/10.2200/S00900ED2V01Y201902AIM042),
  [PDDL2.1](https://doi.org/10.1613/jair.1129), and the probabilistic planning
  languages ([PPDDL](https://doi.org/10.1613/jair.1880),
  [RDDL](https://users.cecs.anu.edu.au/~ssanner/IPPC_2011/RDDL.pdf)) are the
  action-language lineage behind participant precondition/effect contracts.
- [CybORG](https://arxiv.org/abs/2108.09118),
  [CyberBattleSim](https://www.microsoft.com/en-us/research/project/cyberbattlesim/),
  [CyGIL](https://arxiv.org/abs/2109.03331), and CyGIL's
  [unified emulation-simulation training environment](https://arxiv.org/abs/2304.01244)
  are the cyber-agent environment precedents. They show the value of explicit
  action/observation/reward/episode interfaces, and also expose the
  sim-to-emulation gap that RAES must record through realization disclosure and
  evidence provenance.
- The participant interactive-access declaration has a narrower,
  revision-pinned lineage. CyRIS 1.2 explicitly marks an entry guest but infers
  SSH/RDP realization from OS family; CybORG v3.0 places explicit
  host/user/session-type bindings under an agent. RAES adapts explicit
  participant-local binding while rejecting OS inference, established-session
  state, locators, ports, and raw credentials. Exact source boundaries and
  divergences are recorded in the lineage ledger and participant
  interactive-access research note.
- SEM-219's executable tool-affordance binding adopts no new external syntax.
  It maps the existing RAES `scenario-content` reference model
  (`tools-and-artifacts`) to optional tool identity, existing participant
  action contracts to affordance meaning and complete SEM-211 constraints,
  `agents.*` plus behavior-specification refs to participant-local authored
  availability, and observation-boundary/view-rule refs to explicit visibility
  classification. Delivery is implemented for authoring, module composition,
  fail-closed semantic validation, post-instantiation revalidation, canonical
  compiler IR, and the three published SDL schemas. Evidence is
  `ParticipantToolAffordance`, `ParticipantToolAffordanceRuntime`, the SDL
  reference catalog, and the SEM-219 cases in
  `implementations/python/tests/test_sem_208_participant_behavior.py`.
  This mapping does not claim apparatus support, current eligibility,
  invocation admission, realized exposure, runtime execution, persistence,
  or evidence merely from authored presence. The lineage ledger and source
  audit remain unchanged because this implementation adds no normative
  external derivation or compatibility claim.
- SEM-220's executable participant decision surface adopts the existing
  action/observation-interface lineage above without importing a UI, prompt,
  command, or backend-native parameter language. Published v1 retains its
  historical behavior-history-index meaning and remains available through
  `ParticipantDecisionSurfaceModel` and
  `project_participant_decision_surface()`. Issue #909 does not relabel its
  `observation_order`.
- `participant-decision-surface-v2` separates the participant choice
  coordinate `decision_epoch` from the exact derivation `state_cut`. Epoch zero
  is derived from authoritative `episode_running` state while the new
  episode's behavior history is empty. Later epochs are derived from terminal
  participant observations, but retain their complete sequence prefix or
  causal frontier rather than collapsing that cut into the epoch number. RAES
  maps the three portable selection forms to the participant-only view; maps
  governed action meaning to compiled action-contract addresses; maps
  applicability to explicit SEM-211 eligibility; and keeps derivation,
  projection/exposure policy, evidence, provenance, and memory scope in a
  separate assurance plane.
- Projection, disclosure, delivery, selection, admission, attempt, result, and
  outcome are distinct v2 occurrences. An actionable selection binds the
  canonical participant-view digest and authoritative delivery ref. Admission
  re-resolves the exact derivation anchor and delivery record against current
  authority before existing argument-shape, apparatus, SEM-211, and backend
  checks. Reset and restart create a new episode and epoch zero, invalidating
  prior surfaces; they do not claim that a persistent participant forgot
  already delivered information. Evidence is the v2 contract and schema,
  `project_participant_decision_surface_v2()`,
  `deliver_participant_decision_surface_v2()`,
  `bind_participant_decision_surface_selection_v2()`, and the v2 SEM-220
  contract/runtime tests.
- SEM-226 specializes v1 and v2 decision-surface projection without
  adopting another visibility taxonomy, policy language, or participant I/O
  envelope. V1 retains the published order-indexed binding and delivery
  realization. V2 binds every exposed item to participant, episode, audience,
  independent decision epoch, exact state-cut ref, exact projection-policy
  decision, apparatus, exposure policy, markings, provenance, evidence, and
  limitations. Policy and item authorization resolve at that exact cut; a
  maximum scalar order cannot stand in for a causal frontier. Delivery is
  independently authorized and resolved.
- Issue #909 adds formal lineage for the resulting backend and security
  obligations. Abadi-Lamport refinement mappings and Lynch-Vaandrager
  simulations ground the directional concrete-to-abstract obligation.
  Lynch-Tuttle I/O automata and Alur et al. alternating refinement ground
  explicit input/output ownership and availability: projected trace inclusion
  alone permits a backend to refuse a required participant input. Bisimulation
  remains optional and projection-relative, not the default conformance
  relation. Clarkson-Schneider hyperproperties and Bohannon et al. reactive
  noninterference ground adaptive-strategy quantification. The exact mappings,
  divergences, source identities, and nonclaims are recorded in the lineage
  ledger and source audit. Bounded tests may falsify the named finite models;
  they do not prove universal refinement, bisimulation, or noninterference.
- API-409 adopts the existing participant-runtime, ACT-617 mixed-control, and
  SEM-220 decision-surface authorities without introducing a generic external
  message or policy language. RAES maps one proposal, approval, denial,
  external direction, intervention, handoff, override, or cancellation fact
  to the closed `participant-control-occurrence-v1` carrier; preserves the
  unchanged `ParticipantRuntimeBaseEnvelopeModel`; and binds each occurrence
  to its participant/episode, controller state, authority basis, controlled
  scope, behavior specification, mixed-control policy revision, compiled
  declaration, effective order, disposition, evidence, provenance, markings,
  and limitations. `validate_participant_control_occurrence_context()` joins
  those records to compiled ACT-617 declaration coordinates and fails closed
  on unknown or mismatched declarations, authority or policy confusion, stale
  proposal revisions, invalid order, conflicting identity replay, unresolved
  targets, and transformed-proposal identity/provenance/marking violations.
  Delivery is implemented for the Python model, hand-governed schema,
  generated-bundle parity, valid/invalid fixtures, publication accounting,
  and API-409 model/schema/semantic tests in
  `implementations/python/tests/test_api_409_participant_control_occurrences.py`.
  Approval and direction remain distinct from SEM-211 admission; admission,
  execution, result, delivery, observation, audit, runtime mediation,
  persistence, backend support, authentication, UI/transport behavior,
  information-flow proof, and API-423 crossing-policy realization are explicit
  nonclaims. The lineage ledger and source audit remain unchanged because this
  delivery adds no normative external derivation or compatibility claim.
- API-423 composes the already adopted SEM-230/ADR-085 information-flow,
  API-406 participant-runtime, API-409 control-occurrence, SEM-211 action,
  SEM-220/226 decision-surface and exposure, DSL-142 participant-inject,
  experiment-evidence, provenance, marking, and visible-order authorities. The
  exact RAES mapping is the closed
  `participant-crossing-occurrence-v1` family and its unchanged
  `ParticipantRuntimeBaseEnvelopeModel`: each requested, decided, transformed,
  disclosed, delivery-attempted, delivered, observed, or audited fact has its
  own event identity and typed incumbent subject reference. The focused
  occurrence details bind direction and interaction kind, audience,
  actor/controller/authority, exact policy identity/revision/digest and
  effective order, markings, deny-first gate results and disposition,
  transformation/declassification basis, backend posture, evidence,
  provenance, and explicit loss/weakening without copying a carrier payload or
  policy body. `validate_participant_crossing_occurrence_context()` is the
  single resolver-backed join: it fails closed on unknown or mismatched typed
  subjects, stale or future policy revisions, contradictory decisions,
  identity reuse, transformation cycles, marking weakening without explicit
  declassification, missing evidence, invalid predecessor order, and
  realization claims without their owning fact.
- API-423 delivery evidence is the hand-governed
  `participant-crossing-occurrence-v1` schema and publication entry, valid and
  invalid participant-runtime fixtures, the matching `schema_bundle()` output,
  the closed participant-crossing concept vocabularies, and
  `implementations/python/tests/test_api_423_participant_crossing_contracts.py`.
  This delivers portable policy-decision and evidence relations only. It does
  not implement a gateway, transport, policy engine, authentication or
  authorization service, action admission, transformation execution,
  participant delivery or observation, persistence, audit storage, backend
  realization, migration, universal noninterference, trace equivalence,
  refinement, simulation, bisimulation, epistemic equivalence, or proof. The
  lineage ledger and source audit remain unchanged because API-423 reuses the
  recorded SEM-230 derivation and changes no normative external derivation or
  compatibility claim.
- API-407's participant-policy capability extension adopts partial design
  precedents, not source syntax or compatibility. YANG 1.1 features/deviations
  and the YANG Library map to governed feature ids and explicit limitations;
  Vulkan device-feature negotiation maps to fail-closed target admission;
  XACML's deny-first decision/obligation separation maps to the rule that
  capability never grants policy authority; and OGC conformance classes map to
  named finite evidence cases and explicit nonclaims. No one source supplies
  the complete RAES vector.
- The exact RAES mapping is the existing
  `capabilities.participant_runtime.feature_support` entry with
  `unsupported < disclosed_weak < bounded < exact`, separate constraint,
  limitation, disclosure, and evidence references, the six governed ingress,
  egress, declassification, transformation, intervention, and
  participant-directed inject-delivery features, and their API-409/API-423
  required-contract evidence. `resolve_participant_feature_support()` is the
  single strength comparison used by planner admission; an authorized
  downgrade returns the weaker manifest entry unchanged and requires separate
  policy and provenance references.
- Delivery status is contract-, profile-, admission-, fixture-, and
  bounded-conformance-implemented. Evidence is the backend-manifest schema and
  publication entries, controlled vocabulary, stub/reference/libvirt
  declarations, full-remote-control-plane profile, planner and conformance
  integration, and `implementations/python/tests/test_backend_manifest.py`,
  `test_dsl_437_benign_participant_execution.py`, and
  `test_runtime_conformance.py`. The existing backends disclose all six
  features as unsupported; issue #801 does not implement RUN-319 policy
  enforcement. Manifest validity, method presence, finite cases, or adjacent
  API-409/API-423 carriers do not establish authorization, delivery, native
  realization, noninterference, equivalence, bisimulation, model checking, or
  proof. These standards are comparative design precedents only, so this
  change introduces no normative external derivation or compatibility claim
  and the lineage ledger/source audit remain unchanged.
- RUN-310 composes the same participant-interface, append-only event-history,
  mixed-control, information-flow, and access-control lineage into live
  supervisory mediation; it introduces no new external semantic source. The
  exact RAES/RAES SDL mapping is trusted
  `ParticipantBehaviorSpecificationRuntime.controller_states` and
  `control_transitions` for policy authority, closed
  `Participant*ControlIntent` models for caller-owned intent,
  `ControlPlaneIdentity.participant_control_subjects` for the separate
  principal-to-participant/controller binding, `RuntimeControlPlane` and
  `ParticipantControlMixin` for mediation, API-409
  `ParticipantControlOccurrenceModel` for immutable outcomes,
  `RuntimeSnapshot.participant_control_history` for append-only state, and
  `ControlPlaneStore.commit_control_transition()` for the expected-head atomic
  occurrence/receipt/idempotency/audit commit. The existing HTTP request-size,
  authentication, role/target, redacted-error, SEM-211 admission, and API-408
  visibility boundaries remain separate gates.
- RUN-310 delivery evidence is the `runtime-snapshot-v1` schema and publication
  entry, the in-memory and local-store restart/replay implementation, and
  `implementations/python/tests/test_run_310_supervisory_lifecycle.py`, which
  covers every control kind, negative subject binding, stale state, scoped
  idempotency conflict, append-only integrity, atomic failure, restart, closed
  HTTP input, and denial without participant occurrence. This does not claim
  that approval proves admission, execution, delivery, observation, or
  participant visibility; it does not rewrite prior action or controller
  history; and it makes no backend-support, multi-process CAS, distributed or
  partial-order, noninterference, refinement, simulation, bisimulation, UI, or
  participant-internal-reasoning claim. The lineage ledger and source audit
  remain unchanged because RUN-310 adds no normative derivation or
  compatibility claim.
- RUN-319 composes the existing SEM-230/ADR-085 and ADR-095 information-flow
  semantics with API-423 crossing facts, API-407 feature-strength resolution,
  RUN-310 authenticated participant/controller binding and atomic control
  storage, SEM-211 admission, and SEM-226 exposure decisions. The exact runtime
  mapping is the closed `ParticipantCrossingIntent`, a trusted exact-cut
  `ParticipantCrossingPolicyResolver`, separate controller and audience
  bindings on `ControlPlaneIdentity`, deny-first independent API-423 gates,
  `RuntimeSnapshot.participant_crossing_history`, and
  `ControlPlaneStore.commit_participant_transition()`. Configured action and
  supervisory-control ingress cannot dispatch around the shared crossing
  mediator; transformed ingress receives a new typed subject and a fresh full
  admission decision.
- RUN-319 delivery evidence is the evolved
  `participant-crossing-occurrence-v1` exact-cut policy reference, the
  `runtime-snapshot-v1` crossing-history carrier and publication entries, the
  in-memory and local-store atomic restart/replay implementation, and
  `implementations/python/tests/test_run_319_participant_flow_policy.py`.
  The reference backend keeps its six participant-policy features
  `unsupported`; stronger behavior is exercised only with explicit test
  manifests and evidence. This does not claim a new policy engine, participant
  gateway or endpoint family, backend-native enforcement, delivery or
  observation from a decision alone, multi-process CAS, distributed
  linearizability, universal noninterference, refinement, simulation,
  bisimulation, epistemic equivalence, or proof. No normative external
  derivation or compatibility claim changes, so the lineage ledger and source
  audit remain unchanged.
- ASR-535 adopts the falsification-first assurance lineage already cited by the
  participant information-flow work rather than a new external source:
  Goguen and Meseguer's noninterference formulation, Sabelfeld and Sands's
  declassification dimensions and principles, and Clarkson and Schneider's
  hyperproperty separation between a property of one trace and a property of a
  set of traces. The adopted reading is that a security obligation quantified
  over sets of runs cannot be discharged by observing individual runs, so
  executable participant-policy evidence is organized as attempted refutation
  within a declared bound. Backend conformance testing practice contributes the
  separation between a declared capability and an executed probe.
- The exact RAES artifact mapping is the SEM-230 test-local bounded model and
  `policy_noninterference_holds()` for the semantic lane; the shipped RUN-319
  `ParticipantCrossingIntent`, `ParticipantCrossingPolicyResolver`,
  deny-first API-423 gates, `RuntimeSnapshot.participant_crossing_history`, and
  `ControlPlaneStore.commit_participant_transition()` for the runtime lane; the
  existing `run_target_conformance()` runner extended with an injected
  participant-policy probe harness, `ConformanceCaseResult`, and
  `BackendConformanceReport` for the backend lane; and the
  `raes-behavioral-relations` `rev8` catalog with `BehavioralClaimBindingModel`
  for claim identity. The four lanes stay separately statused; none promotes
  another.
- ASR-535 delivery status is bounded-tested and bounded-conformance-implemented.
  Evidence is
  `implementations/python/packages/raes_conformance/conformance/participant_policy_probes.py`,
  the cross-field report validation in
  `implementations/python/packages/raes_conformance/conformance/report.py`, the
  shared conformance diagnostic sanitizer, and
  `implementations/python/tests/test_asr_535_participant_flow_assurance.py`,
  which exhausts a declared finite crossing domain and drives the shipped
  runtime boundary for denial, withholding, redaction, governed
  declassification, transformation, stale or revoked policy, cross-participant
  leakage, participant-directed inject delivery, backend weakening, unsupported
  capability, and adversarial overclaim. A declared API-407 participant-policy
  feature that no harness executed is now recorded as unsupported instead of
  conforming.
- ASR-535 explicitly makes no model-check and no proof claim. The relation
  `policy-noninterference` keeps its deliberately unproved status, and its
  evidence boundary is the finite enumerated domain, the named probe cases, and
  the named target, profile, and execution environment. Exhausting a declared
  bound is not model checking; a passing probe set does not establish universal
  noninterference, trace inclusion or equivalence, simulation, refinement,
  strong or weak bisimulation, epistemic indistinguishability, timed or
  probabilistic security, opacity, or native-backend realization. Issues #810,
  #811, and #812 own opacity, a proof-bearing bisimulation target, and
  adversarial-control evaluation. Issue #813 now defines mixed composition and
  cross-backend realization/transfer evidence; its positive demonstration is
  still owned by #1018. ASR-535 adds evidence rather than a normative
  derivation or compatibility claim, so the lineage ledger and source audit
  remain unchanged.
- Issue #802 applies the already adopted SEM-230/API-423/RUN-319 lineage to
  migration without importing another external model. The exact RAES mapping
  is the legacy/current distinction retained before
  `RuntimeSnapshot.participant_crossing_history` defaults apply; API-407
  feature strength plus backend-profile and trusted-resolver selection for
  opt-in/required adoption; the authenticated API-408 identity and trusted
  `resolve_participant_view_evidence()` adapter path; and append-only API-423
  history, operation, idempotency, and audit persistence.
- Issue #802 delivery evidence is
  `docs/migration/participant-information-flow-control.md`, the paired SDL,
  snapshot, backend-manifest, participant-manifest, and backend-profile
  fixtures, and
  `implementations/python/tests/test_issue_802_participant_control_migration.py`.
  Legacy absence remains unknown or unsupported; v1 decision surfaces require
  authoritative reprojection; participant implementations do not receive the
  API-423 assurance plane; and rollback after governed persistence retains all
  crossing facts. These migration results establish neither native-backend
  realization nor universal noninterference, equivalence, simulation,
  refinement, bisimulation, epistemic, timed, or probabilistic security.
  Because the work adds compatibility evidence without changing normative
  external derivation, the lineage ledger and source audit remain unchanged.
- Issue #803 re-expresses the already adopted SEM-230/API-423/RUN-319 and
  ASR-535 lineage for scenario authors, participant-implementation authors,
  runtime operators, backend implementors, and researchers. It adds no
  external source, semantic rule, contract meaning, runtime behavior,
  compatibility claim, or behavioral-relation definition.
- The exact issue #803 artifact mapping is the hosted
  `docs/public/participant-control.md` role routes and bounded examples,
  `docs/public/index.md` navigation,
  `docs/research/participant-io-control/index.md` adoption status,
  `docs/explain/sdl/scientific-scenario-completeness.md` delivery explanation,
  the issue #803 architecture preflight, and the executable public-guide
  `BehavioralClaimBindingModel` example in
  `implementations/python/tests/test_public_docs_policy.py`. The example
  resolves `bounded-probe-success` against
  `raes-behavioral-relations@rev8`; it does not define a documentation claim
  schema or a second relation catalog.
- Issue #803 delivery status is published explanatory guidance over shipped
  bounded evidence. The reference backend still declares the six
  participant-policy features unsupported. The current runtime does not emit
  a distinct API-423 `withhold` decision, the finite declassification case
  drives projection, and inject delivery does not bind the compiled
  DSL-142/DSL-111 identity end to end. No native-backend realization,
  universal noninterference, projected-history equality, trace inclusion or
  equivalence, simulation, refinement, strong or weak bisimulation,
  model-check, or proof is claimed. The lineage ledger and source audit remain
  unchanged because the documentation adds neither a normative derivation nor
  a compatibility claim.
- CALDERA adversary-emulation research informs the action semantics: cyber
  actions can change foothold, knowledge, observations, detection surface, and
  downstream outcomes under uncertainty.
- RUN-305's runtime snapshot design follows that lineage by making participant
  episode state and behavior history first-class portable records rather than
  backend logs or `metadata`: action attempts, observations, state-transition
  records, and outcome interpretations need stable participant/episode/action
  identity to support review across RL agents, LLM agents, humans, scripts, and
  cyber-range backends. OpenSpiel's information-state separation and the
  cyber-agent sim-to-emulation sources above are the reason the snapshot
  preserves behavior history without claiming hidden world truth, private
  participant internals, benchmark validity, or full replay guarantees from that
  history alone.

## Benchmark And Experiment Lineage

- [Cybench](https://arxiv.org/abs/2408.08926) and
  [AutoPenBench](https://arxiv.org/abs/2410.03225) inform RAES's treatment of
  task descriptions, starter files, evaluators, subtasks, gold steps,
  milestones, human assistance, and repeated runs as experiment artifacts.
  RAES does not adopt flag capture or milestone completion as the complete
  outcome model; those are inputs to explicit interpretation rules.
- [CAIBench](https://arxiv.org/abs/2510.24317) motivates integrated offensive,
  defensive, privacy, and cyber-physical evaluation surfaces. RAES adapts this
  as role-neutral multi-participant semantics and privacy/redaction disclosure,
  not as a bundled meta-benchmark score.
- General agent-evaluation critiques such as
  [AI Agents That Matter](https://arxiv.org/abs/2407.01502) and
  [Benchmarking Practices in LLM-driven Offensive Security](https://arxiv.org/abs/2504.10112)
  motivate holdout discipline, anti-contamination controls, scaffold
  disclosure, baseline disclosure, cost/resource traces, and standardized run
  records. RAES records these as provenance and information-boundary concerns
  so downstream studies can audit what a participant actually could observe.

### Adaptive difficulty, sequential intervention, and simulation experiments

SCE-003 combines the benchmark lineage above with four primary adjacent
sources. Hunicke and Chapman's
[AI for Dynamic Difficulty Adjustment in Games](https://www.cs.northwestern.edu/~hunicke/pubs/Hamlet.pdf)
supplies the inspectable controller shape: observations, policy, trigger,
intervention, and outcome remain separate. Murphy's
[Optimal Dynamic Treatment Regimes (2003)](https://doi.org/10.1111/1467-9868.00389)
supplies the sequential treatment-regime precedent: a history-dependent
decision rule makes the realized path part of treatment. Weiss's
[adaptive-testing work (1982)](https://doi.org/10.1177/014662168200600408)
warns that adaptive selection is not a measurement theory; item/measurement
model, selection, and stopping assumptions determine what can be inferred.
Bengio et al.'s
[Curriculum Learning (2009)](https://doi.org/10.1145/1553374.1553380)
shows that ordering and selection can change learning dynamics, so scaffolding
or difficulty changes cannot be treated as presentation-neutral.

The simulation-experiment lineage supplies the engineering boundary.
MIASE/SED-ML and experimental frames keep the scenario model separate from the
procedure that exercises and observes it. L'Ecuyer's stream/substream work and
Heikes, Montgomery, and Rardin's
[common-random-numbers analysis (1976)](https://doi.org/10.1177/003754977602700301)
make cross-alternative random-stream reuse an explicit design choice rather
than an accidental continuation. Sargent's V&V discipline keeps intended use,
implementation verification, and model/measurement validation distinct.

RAES adopts those lessons as a versioned and digest-bound source definition
plus exact evidence instance; a sealed policy and decision history;
forward-only interventions; distinct fixed/adaptive/scaffolded allocations;
new identity for a changed-scenario follow-up; explicit random-stream
relationships; and analysis/validity disclosures. RAES does not adopt an
item-response model, dynamic-treatment estimator, curriculum optimizer, DDA
controller, or simulation algorithm, and it claims no universal difficulty
scale, competence estimate, causal policy effect, pedagogical benefit, or
policy optimality.
The issue-specific transfer audit is recorded in
[`adaptive-difficulty-lineage-and-validity.md`](../../research/scenario-variation-trial-realization/adaptive-difficulty-lineage-and-validity.md).
These are semantic design precedents, not source-code, schema, or wire-format
derivations, so the normative SDL subject ledger and third-party notice
disposition do not change.

## DSL Evaluation Lineage

- [Do Software Languages Engineers Evaluate their Languages?](https://arxiv.org/abs/1109.6794),
  Mernik, Heering, and Sloane's
  ["When and How to Develop Domain-Specific Languages"](https://doi.org/10.1145/1118890.1118892),
  and Kosar, Bohra, and Mernik's
  ["Domain-Specific Languages: A Systematic Mapping Study"](https://doi.org/10.1016/j.infsof.2015.11.001)
  inform RAES's treatment of language adequacy as an evidence claim. A language
  can be domain-aware and formally specified while still failing on ambiguity,
  usability, effectiveness, maintainability, or domain-expert reviewability.
- Issue #346 tracks this as a dedicated evidence gate. It is related to
  authoring accessibility, formal validation, and participant semantics, but it
  is not discharged by any of those alone.

## Runtime, Time, And Causality

- [TENA](https://www.trmc.osd.mil/tena-about.html) and the current
  [IEEE High Level Architecture framework (IEEE Std 1516-2025)](https://standards.ieee.org/ieee/1516/6687/)
  are the main runtime/federation precedents for distributed exercise services,
  time management, object publication, ownership, and data distribution. The
  2025 family supersedes the 2010 edition cited by the earlier time-model
  survey; claims now pin the exact framework, federate-interface, or OMT part
  and edition.
- [SISO Cyber DEM](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-025-2023_cyberdem.pdf)
  and Cyber FOM are cyber-specific simulation-interoperability precedents.
- Lamport logical clocks, HLA time management, Time Warp, DEVS, SimPy, ROS 2
  time, ns-3 realtime mode, and FMI inform RAES's separation of timestamp,
  ordering, clock authority, pacing, synchronization, and causality.
- [Fidge](https://doi.org/10.1109/ICDCS.1988.12501)/[Mattern](https://www.vs.inf.ethz.ch/publ/papers/VirtTimeGlobStates.pdf)
  vector time and the
  [Schwarz-Mattern causality survey](https://doi.org/10.1007/BF02277859) are
  the basis for vector-clock ordering claims: scalar Lamport clocks respect
  causality one way, vector clocks characterize it.
  [Winskel's event structures](https://doi.org/10.1007/3-540-17906-2_31) and
  [Mazurkiewicz's trace theory](https://doi.org/10.1007/3-540-17906-2_30)
  ground partial-order realized ordering with simultaneity groups.
- [Allen's interval algebra](https://doi.org/10.1145/182.358434),
  [Koymans' metric temporal logic](https://doi.org/10.1007/BF01995674), and
  [Alur-Dill timed automata](https://doi.org/10.1016/0304-3975(94)90010-8)
  are the formal temporal-contract lineage for schedules, deadlines, dwell,
  and windows.
- [Berenson et al.'s ANSI SQL isolation critique](https://doi.org/10.1145/223784.223785)
  and [Adya's generalized isolation theory](https://hdl.handle.net/1721.1/8703)
  anchor the shared-state isolation-guarantee vocabulary.
- Halpern-Pearl structural causality informs RAES's treatment of attribution:
  a participant action followed by an alert is not automatically a causal
  explanation without an evidence basis.
  [Chockler-Halpern responsibility and blame](https://doi.org/10.1613/jair.1391)
  extends this to graded multi-cause attribution.

### Cyber DEM And Cyber FOM: Adopted And Out Of Scope

[SISO Cyber DEM](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-025-2023_cyberdem.pdf)
(SISO-STD-025-2023) and the
[Cyber FOM](https://www.sisostandards.org/news/690125/Publication-of-Cyber-FOM-and-SIRL-Users-Guide.htm)
(SISO-STD-025.3-2024) are distinct artifacts and are treated as distinct here.
Cyber DEM is a runtime data-exchange model: a shared ontology of cyber objects
(Device, System, Service, Network, Data) and typed effect/event types for
exchanging cyber conditions between simulators. The Cyber FOM is the HLA
federation object model derived from it.

- **Adopted as precedent.** Cyber DEM's typed cyber-object and directed
  relationship vocabulary, and its attack/defend/recon effect taxonomy, are
  precedent for RAES treating typed relationships
  ([ADR-052](../../decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md))
  and observed runtime objects as first-class. RAES adopts the *concept* of a
  typed cyber-object vocabulary, not the Cyber DEM object set or its identifiers.
- **Out of scope.** RAES does not adopt Cyber DEM as its scenario model or the
  Cyber FOM as its backend contract. Cyber DEM is consumed at runtime by
  federates; RAES keeps an authored scenario surface separate from any runtime
  exchange model, and does not treat HLA federation conformance as equivalent to
  RAES backend conformance.
- **Where it leads RAES.** Because the Cyber FOM inherits IEEE 1516 HLA time
  management and multi-vendor federation, it is more mature than RAES on
  federated time and standardized interoperability. RAES's time-authoring
  surface is partial and explicitly incomplete. This is detailed in the
  [Related-Work Comparison](related-work-comparison.md).

### Mixed Simulation, Emulation, And Operational Composition

Issue #813 adds an edition-pinned composition lineage:

- [NIST integrated HLA federations](https://www.nist.gov/publications/integrating-multiple-hla-federations-effective-simulation-based-evaluations-cps)
  show why a flat federation can be insufficient for information hiding,
  independent time scales, resource sharing, and organizational boundaries.
  Bridges need explicit message and time translation.
- [NIST UCEF](https://www.nist.gov/ctl/smart-connected-systems-division/iot-devices-and-infrastructures-group/how-does-ucef-work)
  explicitly composes simulators, emulators, equipment, and combinations in
  one HLA federation.
- [ACTING EDL-FG](https://arxiv.org/abs/2605.12170) separates infrastructure,
  screenplay, injects, participant interaction, federation, telemetry, and
  assessment and names hybrid simulated/emulated components. RAES adopts the
  separation, not the recent preprint's schema.
- [FMI 3.0.2](https://fmi-standard.org/docs/3.0.2/) leaves the
  co-simulation algorithm outside the standard, while
  [HELICS](https://docs.helics.org/en/latest/user-guide/fundamental_topics/timing_configuration.html)
  makes time request/grant and dynamic membership explicit. These support
  explicit coordinator, clock/order mapping, and finite pre-admitted phase
  semantics.
- [ISO 23247-6:2026](https://www.iso.org/standard/87426.html) distinguishes
  integrated, unified, and federated digital-twin composition. The topology
  distinction is adopted without treating a simulator, emulator, model,
  shadow, and synchronized twin as synonyms.
- [IEEE 1730.1-2023](https://standards.ieee.org/ieee/1730.1/11140/) and
  [SISO SIRL](https://www.sisostandards.org/page/StandardsProducts) keep
  multi-architecture engineering and interoperability-readiness evidence
  separate from actual interoperability.

The RAES mapping is ADR-102, SEM-234, and ASR-537. Portable SDL remains
backend-neutral. Admitted trial intent allocates stable participant runtime,
controlled-scope, action-family, observation-source, and crossing refs to
apparatus components. Every composition edge binds authority, mapping,
participant/audience policy, clock/order, support strength, loss, failure, and
evidence.

CybORG's published simulation-to-emulation experiment reports 139 successful
evaluations out of 210 and includes simulation-only observation failures.
CyGIL reports one bounded 50-of-50 emulation evaluation while retaining
unknown-transition and heuristic-switching limits. These are empirical
transfer precedents, not equivalence claims. RAES therefore keeps bounded
conformance, interoperability readiness, empirical transfer, trace inclusion,
bisimulation, IFC/noninterference, and backend equivalence distinct.

Revision 1 also separates three overloaded open/closed axes: control-loop
posture, world assumption, and federation membership. Multiple realization
providers do not become multiple acting controllers. Leases, simultaneous
scoped owners, and joint/fused control require a later versioned authority
profile.

## Adversary Emulation And Security Knowledge

- [MITRE ATT&CK](https://www.mitre.org/news-insights/publication/mitre-attck-design-and-philosophy),
  MITRE CALDERA, Atomic Red Team, and OpenC2 are adversary-emulation and
  command/response precedents. RAES treats them as behavior and execution
  sources that scenarios may bind to, not as replacements for the SDL.
  From OpenC2 specifically, RAES borrows the command/response principle — an
  action requested against a target with a status-bearing response — but does
  not adopt OpenC2's action/target/argument payload structures as SDL or
  runtime-contract schema.
- OCSF is the preferred lineage for normalized security event and finding
  structure. RAES uses that style for observations and evidence without making
  raw telemetry equal to participant-visible state.

## What RAES Adds

RAES separates authored scenario meaning, processor/runtime contracts, backend
realization, participant implementations, live state, and archival
evidence/provenance. The participant-semantics design extends that separation:
actions, observations, visibility, causality, temporal behavior, and outcomes
must be portable across human, AI-agent, scripted, simulated, and hybrid
participants without collapsing into any one backend or learning API.

### Shared Time Authority

The RAES shared time model has explicit external lineage but is not a translated
copy of any one framework:

- ROS 2 contributes the separation of system, steady/monotonic, and externally
  controlled semantic time plus explicit pause/jump handling.
- FMI contributes importer-controlled advancement, capability negotiation,
  clock activation, and superdense event coordinates.
- IEEE HLA contributes the separation of time regulation, constrained
  advancement, and ordered delivery from timestamp values.
- TENA contributes the separation between execution-time coordination and the
  persistent range data archive.
- OpenSCENARIO contributes the separation of lifecycle, triggers, actions, and
  simulation-time predicates.

RAES adds backend-neutral authored declarations, exact rational mappings,
ordinary SDL subject references, canonical compilation, and segment-preserving
runtime control. It does not claim ROS, FMI, HLA, TENA, or OpenSCENARIO
conformance through those generic declarations.

### Adversarial Participant Flow And Control

- The older cyber lineage establishes the portable core beneath the recent
  agent-control systems. [Denning's lattice model](https://doi.org/10.1145/360051.360056)
  supplies ordered information classes and conservative joins;
  [decentralized labels](https://www.cs.cornell.edu/andru/papers/sp98/paper.html)
  supply principal-relative ownership and explicit downgrade authority; and
  [robust declassification](https://doi.org/10.3233/JCS-2006-14203) together
  with [nonmalleable IFC](https://www.cs.cornell.edu/andru/papers/nmifc/)
  supplies the separation of confidentiality release from integrity
  endorsement and the need to constrain attacker influence over both.
- [HiStar](https://www.usenix.org/conference/osdi-06/making-information-flow-explicit-histar)
  and [Flume](https://pdos.csail.mit.edu/papers/flume-sosp07.pdf) demonstrate
  decentralized information-flow control in operating-system abstractions.
  [NIST SP 800-53 AC-4](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
  and the [NSA cross-domain program](https://www.nsa.gov/Cybersecurity/Partnership/National-Cross-Domain-Strategy-Management-Office/)
  supply the controlled-interface, complete-mediation, content/metadata
  inspection, default-deny, and lifecycle-assurance precedents for a final
  boundary. RAES adopts their semantic discipline, not a fixed military label
  vocabulary, operating-system API, guard product profile, or accreditation
  claim.
- [TaintDroid](https://www.usenix.org/conference/osdi10/taintdroid-information-flow-tracking-system-realtime-privacy-monitoring)
  demonstrates useful dynamic tracking of explicit flows, while
  [CamFlow](https://arxiv.org/abs/1711.05296) demonstrates whole-system
  provenance capture. Their limits are equally material: tracking may omit
  implicit, native, control, or covert flows, and provenance says where data
  came from rather than whether release, endorsement, or execution is
  authorized.
- [FIDES](https://arxiv.org/abs/2505.23643) supplies the immediate precedent
  for independent confidentiality/integrity labels, conservative propagation,
  and deterministic action policy.
- [CaMeL](https://arxiv.org/abs/2503.18813) supplies the trusted-control and
  untrusted-data separation, quarantine, and capability precedent. RAES keeps
  model topology and prompt separation apparatus-specific.
- [SAMOS](https://research.ibm.com/publications/securing-mcp-based-agent-workflows)
  supplies the session-flow and complete tool-call interception precedent.
  RAES does not require MCP and places portable authority at the final
  external-action or disclosure sink.
- [AgentDojo](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html),
  [AI Control](https://arxiv.org/abs/2312.06942), and
  [ControlArena](https://control-arena.aisi.org.uk/) supply dynamic injection,
  intentional subversion, honest/attack modes, main/side objectives,
  monitoring, audit, editing, deferral, shutdown, safety, usefulness, and
  adaptive evaluation precedents.
- [runtime shielding](https://arxiv.org/abs/1501.02573) supplies the
  property-bound last-moment runtime mediation precedent, while
  [capability-based authority control](https://doi.org/10.4230/LIPIcs.ECOOP.2017.20)
  supplies the least-authority precedent.
- ADR-101 adapts those lessons through SEM-233 and ASR-536 over the existing
  SEM-230, ACT-617, API-409/API-423, RUN-310/RUN-319, API-407, experiment, and
  ASR-535 carriers. It does not import an LLM framework, prompt format, model
  role, MCP gateway, monitor, scorer, or trajectory hierarchy.
- SEM-233 therefore keeps confidentiality and integrity as independent
  coordinates and keeps declassification, endorsement, approval, admission,
  authentication, and authorization as distinct operations. Missing labels,
  ambiguous joins, stale policy cuts, and unexplained cross-participant or
  cross-episode resets fail closed at the final enforceable sink. A scalar
  `trusted`, `sensitivity`, marking, confidence, signature, or monitor score
  cannot stand in for the two coordinates. These rules address the recurring
  failure modes of label/privilege administration, over-powered trusted
  downgrade paths, incomplete mediation, tag laundering, stale provenance,
  and guards that mistake detection or identity for flow authority.
- Issue #1001 publishes `sem-233/rev1` as two closed finite obligation
  powersets ordered by subset with componentwise union joins. Unknown state is
  deny-equivalent; release operations create fresh identities; labels,
  provenance, and possible-influence history survive handoff and replay; and
  the existing SEM-230/API-423 crossing decision gains independent
  confidentiality and integrity predicates at the same exact cut. Its finite
  executable model is bounded falsification evidence, not a portable contract,
  runtime or backend implementation, model check, proof, or covert-flow claim.
- Issue #1002 publishes the portable contract boundary as the immutable
  `participant-boundary-flow-policy-v1@rev1` artifact and the closed
  `participant-flow-control-relation-v1` document. The contract adapts
  [DStar's cross-host DIFC](https://www.usenix.org/conference/nsdi-08/securing-distributed-systems-information-flow-control),
  [SIF's end-to-end confidentiality and integrity](https://www.cs.cornell.edu/andru/papers/usenix07-html/paper.html),
  and [W3C PROV-DM's identified derivation and influence](https://www.w3.org/TR/2013/REC-prov-dm-20130430/)
  into exact reference-only bindings over runtime facts, normalized action
  arguments, API-409 control occurrences, and API-423 crossing occurrences.
  Its trusted resolver validates exact profile revisions, carrier context,
  authority, evidence, history heads, and all final-sink conjuncts. The schema
  alone is structurally valid but explicitly not trusted without that context.
  This delivery adds no runtime store, event stream, policy engine, backend
  enforcement, PROV serialization compatibility, or covert-flow guarantee.
- Issue #812 is design authority. Its DRAFT requirements and program do not
  establish runtime enforcement, backend realization, intentional-subversion
  robustness, model alignment, monitor honesty, private-reasoning safety, or
  control of undeclared covert channels.
