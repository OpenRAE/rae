# Scenario- and product-shaped SDL semantics audit

Issue [#959](https://github.com/OpenRAE/rae/issues/959), reviewed 2026-09-16
against `2ed2d97cee641419912dfd2e4e2e4b0c9c61f35e`.
This is the current semantic supplement to the existing
[scope inventory](scope-inventory.md), not another runtime-family registry.

The review found three local defects: service-manager naming, HTTP method
identity and partial listener completeness. Their focused corrections shipped in
[#1297](https://github.com/OpenRAE/rae/issues/1297),
[#1298](https://github.com/OpenRAE/rae/issues/1298) and
[#1299](https://github.com/OpenRAE/rae/issues/1299), and the integrated
conformance evidence in #1211 consumes those corrected boundaries. It also
corrects current
explanatory prose that still described guards removed by #1207. The original
platform-application defect was corrected by
[#956](https://github.com/OpenRAE/rae/issues/956); that correction remains intact.

Completion of this audit is not a claim that every runtime field supports every
product, every partial observation, or every backend. Integrated lifecycle
acceptance and prevention remain owned by
[#1211](https://github.com/OpenRAE/rae/issues/1211). The distinction matters:
catalog acceptance alone does not prove a portable surrounding shape.

## Method and evidence boundaries

1. Start with the 17 families in the
   [normative runtime index](../../../specs/sdl/runtime-inventory.md) and its
   existing Python registry. Add service-manager units because the #1206
   inventory explicitly identifies their systemd-shaped state. Review the
   adjacent surfaces listed below against their existing owners.
2. Trace each family to its motivating capture, owning ADR and
   [lineage](../../explain/sdl/lineage.md). The historical
   [SCN-010 report](../../raes/inventory/scn010-expressivity-gap-analysis.md)
   explains why the datastore, platform, authorization, cadence, forwarding and
   orchestration surfaces exist. Its specimen-derived mandatory-profile rules
   are historical evidence, not current authoring requirements.
3. Inspect model fields, declared defaults, registered model validators and
   cross-reference consumers. Read the corresponding definitions in the
   published authoring/instantiated/snapshot schemas. Test actual acceptance:
   an optional schema property can still be compulsory in a model validator.
4. Classify the primary semantic owner of every selected field in the
   [field ledger](product-semantics-fields.md). Its 115 models and 899 fields
   include every recursively reachable child and inherited field. Reuse
   #1206's term-level vocabulary dispositions; inspect non-enum restrictions
   such as HTTP methods and native name validators separately.
5. Apply the issue rubric to each row: meaning independent of a product;
   legitimate second/private implementation; mandatory shape justified by the
   selected contract; independent content/capability/binding/policy/evidence
   owners; bounded native data; explicit version/support semantics; and no
   conflation of validity with completeness or conformance.
6. Check inherited open scope, exact descendants, conditional optional presence,
   omitted/empty/unknown distinctions, abstraction-level completeness and
   independently requested observation. Missing backend choices require no
   per-field waiver, core catalog entry or replacement extension catalog.
7. Reproduce candidate failures before labeling them defects. Compare confirmed
   cases with primary sources and existing lineage. Record a focused issue with
   affected contracts, compatibility/migration and test impact. Record retained
   exceptions with the same care.

The existing `audit.py census` is a discovery aid. At this baseline it reports
278 authoring enums, 144 with `other` or `unknown`; these are candidate counts.
The 2026-09-04 probes and counts in the scope inventory remain historical.
This pass does not relabel them as current failures or execute their old API
assumptions as a new conformance suite. Current evidence uses model inspection,
the counterexamples below and the named current tests.

### Shared schema and consumer trace

All selected family models appear under the `RuntimeConfiguration` graph in
the published SDL [authoring schema](../../../contracts/schemas/sdl/sdl-authoring-input-v1.json),
[instantiated schema](../../../contracts/schemas/sdl/instantiated-scenario-v1.json)
and [snapshot schema](../../../contracts/schemas/sdl/instantiated-scenario-snapshot-v1.json).
The field ledger links each model to its current defining source. The owning
ADRs below define semantics; published schemas remain hand-governed contract
authority with reference-generator parity, per ADR-009.

Common consumers are the safe YAML/source pipeline, `SDLModel`, variable
instantiation, the collect-all semantic validator, runtime reference traversal
and module composition, compiler recursive constraints, canonical serialization,
runtime concern projection and snapshot/description codecs. Selected-operation
admission is a separate planner/backend boundary. These consumers are why a
follow-up must migrate source, schemas, comparison and round trips together.

The [#1206 implementation dispositions](scope-inventory.md#issue-1206-implementation-dispositions-2026-09-12)
name the shared vocabulary owner for each enum definition. Native names, wire
tokens, provider IDs, digests and data payloads remain in their owning fields;
they are not all converted to `x-owner:` identifiers. New operational meaning
uses existing pinned domain-profile admission, not an audit-local interpreter.

## Registered-family dispositions

“Sound” means sound for the bounded contract examined here. It does not certify
every optional child profile as universal or claim backend execution. All rows
inherit the shared schema/consumer trace above and the field ledger. A field
without a listed exception retains its typed owner; a product-specific field
does not become portable merely because the surrounding family is sound.

| Family | Specimen and authority | Guard, example and disposition |
| --- | --- | --- |
| `service_listeners` | MISP/nginx/supervisord binds, #431; [ADR-043](../../decisions/adrs/adr-043-runtime-service-listener-surface.md); osquery, Nmap, socket and publication lineage | **Local semantic defect**, F3 below. `validate_listener_shape` requires complete network/Unix endpoints even when choices are unmentioned. Keep known scope/address-family contradictions and reference checks. `test_runtime_service_listeners.py` covers complete MISP binds and negative controls; it does not establish partiality. |
| `applications` | Participant-visible HTTP routes, #367; [ADR-026](../../decisions/adrs/adr-026-application-http-surface-inventory.md), extended by [ADR-052](../../decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md) for Shuffle/nginx upstreams | **Local semantic defect**, F2. `normalize_methods` imposes nine methods and uppercase identity. Keep local route IDs, duplicate bindings, response bounds, disclosure controls and proxy agreement. HTTP/HTTPS-only upstreams are an explicitly narrow profile, not a universal application transport. Parser/model/validator suites contain the route examples. |
| `database_services` | PostgreSQL #388 and SCN-010 MariaDB confirmation; [ADR-029](../../decisions/adrs/adr-029-database-logical-state-runtime-surface.md); relational/SQL lineage | **Sound as a relational inventory.** `validate_service` preserves unique objects/grants and supplied engine/protocol consistency; #1207 permits missing protocol knowledge. Database/schema/table structure is deliberately relational, not a substitute for Redis or Cassandra. Keep database roles distinct from local/directory identities. #1207 partial-description tests cover omitted protocol and exact state. |
| `dns_services` | DNS inventory #426; [ADR-039](../../decisions/adrs/adr-039-dns-service-runtime-inventory.md); RFC 1035/2181/3597 and IANA identity | **Sound within the typed DNS profile.** Zone/RRset validators enforce identity and typed RDATA consistency; a present RRset describes records, not proof of complete zone capture. `other` plus numeric `type_code` preserves exact unknown-type identity. #1206 consumer/schema tests protect this exception. An omitted zone collection does not assert a complete empty DNS server. |
| `identity_authorities` | TechVault Active Directory #401; [ADR-032](../../decisions/adrs/adr-032-directory-domain-identity-runtime-surface.md); LDAP, Kerberos, SCIM, SAML/OIDC and RBAC/ABAC | **Sound corrective precedent.** Authority/subject/policy/relationship records use stable local IDs, shared uniqueness and resolved references. SID, DN, issuer and principal names remain native data. No AD domain/controller/group recipe is mandatory. Exact private identities and optional inventories use #1206 coverage; attributes alone claim no executable extension support. |
| `file_services` | TechVault Samba/fileshare #421; [ADR-037](../../decisions/adrs/adr-037-runtime-file-service-and-filesystem-presence-semantics.md); file-sharing and access-control lineage | **Sound within its declared share/access profile.** Service, share, principal, access-rule and access-observation owners are separate. Supplied references and protection classes stay checked; a share is not proof that a probe succeeded. SMB-shaped options such as `browseable` remain optional named configuration, not universal identity or an NFS export model. Existing parser/validator and observed-value tests exercise this boundary. |
| `mail_services` | TechVault Postfix/Dovecot #420; [ADR-038](../../decisions/adrs/adr-038-runtime-mail-service-logical-state.md); SMTP/IMAP and mail-service lineage | **Sound within the mail profile.** `validate_service` checks supplied child identities and references. Components, listener capabilities, routing policy, mailbox identities, queues and settings are distinct. No queue count or Postfix setting is mandatory; credential posture has no raw-password slot. `test_runtime_mail_service.py` and #1206 vocabulary/round-trip cases retain this shape. |
| `network_sensors` | NSM/IDS capture #429; [ADR-042](../../decisions/adrs/adr-042-network-sensor-runtime-monitoring.md) | **Sound inventory boundary.** `validate_unique_refs` checks declared scope/evidence references; implementation and capture-mode identities are extensible. Passive/inline posture and capture interfaces are configuration, not proof that packets were collected. `test_runtime_network_sensor.py` plus independent demand tests protect that distinction. |
| `network_detection_engines` | Suricata #430 and SCN-010 confirmation; [ADR-044](../../decisions/adrs/adr-044-network-detection-engine-runtime-inventory.md); Suricata/Snort/Zeek, Sigma/YARA/STIX lineage | **Sound bounded manifest.** `validate_engine` checks uniqueness, not compulsory rule sources or reload controls. Native rule format and optional control capabilities do not import a rule interpreter. Keep sensor, engine, output and evidence ownership separate. `test_runtime_network_detection.py` and #1206 tests cover portable/private identities. |
| `security_monitoring_managers` | Wazuh #428 and parsed definition captures; [ADR-040](../../decisions/adrs/adr-040-security-monitoring-manager-runtime-inventory.md), [ADR-045](../../decisions/adrs/adr-045-security-monitoring-detection-definition-semantics.md); NIST log management, Sigma/OCSF lineage | **Sound as bounded inventory, with retained native detail.** `validate_manager` checks identity; definition validation checks digest pairs and source ranges, not mandatory Wazuh components/agents. Optional decoder/SID/ATT&CK fields are captured native content, not universal detection semantics or authored concept-binding authority. `test_runtime_observed_values.py`, family invariants and #1206 cases cover the boundary. |
| `ssh_servers` | TechVault sshd policy; [ADR-031](../../decisions/adrs/adr-031-ssh-server-configuration-surface.md) | **Sound as an explicitly bound SSH daemon-policy profile.** The required same-node `service` is explicit in ADR-031; match and forced-command semantics are deliberately SSH-scoped. This is not a generic remote-access model. `test_runtime_ssh_server.py` covers redaction and match rules. #1299 separately requests a decision on authoring partial SSH knowledge without that binding; this audit does not claim it is already supported. |
| `app_authorizations` | SCN-010 OpenSearch/Redis/Cassandra/dashboard/app stores; [ADR-046](../../decisions/adrs/adr-046-app-authorization-runtime-inventory.md); RBAC96 and NIST ABAC | **Naming/documentation debt, corrected in current guidance.** #1207 removed compulsory grants/profile coverage. `validate_app_authorization` retains identities and role/mapping references; deny-only and empty state are legitimate. `cql_resource`/`redis_acl` are external vocabulary identities, not mandatory grant catalogs. Closed grant effects and credential classes remain policy. `test_runtime_app_authorization.py` and #1207 regressions cover this. |
| `scheduled_jobs` | SCN-010 MISP/IOC-sync cadence; [ADR-047](../../decisions/adrs/adr-047-scheduled-job-runtime-inventory.md); POSIX crontab/RFC 5545 | **Sound bounded cadence profile.** Optional schedule and run-state do not require a systemd timer. Interval/cron/calendar name supported grammar families; they are not a product catalog or proof that `spec` is executable. Payload/target ownership stays with forwarding or workflow contracts. `test_runtime_scheduled_job.py` covers the cadence-only boundary. |
| `datastore_services` | SCN-010 OpenSearch/Elasticsearch, Cassandra, Redis; [ADR-048](../../decisions/adrs/adr-048-datastore-service-runtime-inventory.md), node provenance [ADR-058](../../decisions/adrs/adr-058-datastore-node-engine-provenance-and-endpoints.md) | **Naming/documentation debt, corrected in current guidance.** #1207 removed mandatory geometry/mappings/replication/persistence. `validate_datastore_service` keeps supplied partition contradictions, local IDs and manifest refs. Optional RDB/AOF data remains native compatibility detail, not universal persistence semantics. `test_runtime_datastore.py` and #1207 cases cover nonpersistent cache and partial search/wide-column descriptions. |
| `platform_applications` | SCN-010 MISP, dashboards, TheHive, Cortex, Shuffle; [ADR-049](../../decisions/adrs/adr-049-platform-application-runtime-inventory.md); ADR-032, STIX/TAXII/CACAO separations | **Sound after #956 for the audited boundary.** `validate_platform_application` checks local identities. Zero or multiple capabilities are independent of optional content, bindings, policy, authorization and evidence. Deprecated `platform_kind` and bounded `content_objects` stay compatibility data. `test_runtime_platform_application.py` preserves empty/default and multi-role cases. No MISP corpus is mandatory. |
| `forwarding_agents` | SCN-010 Wazuh sidecars and MISP-to-Suricata sync; [ADR-050](../../decisions/adrs/adr-050-forwarding-agent-runtime-inventory.md); syslog, OpenTelemetry Collector and content-sync lineage | **Naming/documentation debt, corrected in current guidance.** #1207 permits composed/partial pipelines; `validate_forwarding_agent` retains local identity. A synchronizer need not use IOC conversion, API pull, enrollment, buffering or reload. Supplied relationship/target agreement remains checked. Ownership role does not prove successful forwarding. `test_runtime_forwarding_agent.py` and #1207 non-IOC cases are executable evidence. |
| `orchestration_authorities` | SCN-010 Shuffle/Cortex/control-interface holders; [ADR-051](../../decisions/adrs/adr-051-orchestration-authority-runtime-inventory.md); OCI, Kubernetes controller and Docker API lineage | **Naming/documentation debt, corrected in current guidance.** #1207 permits unknown interface knowledge; supplied same-node refs still resolve. `validate_orchestration_authority` keeps child identity. `host_root_equivalent` is a declared privilege fact, not authorization; a filename ending in `docker.sock` proves neither. `test_runtime_orchestration.py` and selected-admission tests retain authority checks. |

## Adjacent surfaces and retained exceptions

| Surface and evidence owner | Disposition and rationale |
| --- | --- |
| Service-manager units, workstation #418 / aptl#334; [ADR-035](../../decisions/adrs/adr-035-service-manager-unit-state-runtime-surface.md) | **Local semantic defect**, F1. Included in the field ledger. Optional systemd state is useful, but its native naming rule is unconditional. |
| Packages, repositories, software, images; ADR-023/034 and [software requirements](../../../specs/sdl/software-requirements.md) | **Sound within the corrected #1205 boundary.** Required software identity, optional acquisition and resulting state have separate owners. Purls, hashes, build instructions and image references are bounded native data. They do not force a package manager or repository for an abstract node. #1206 extends descriptive identity; it does not turn labels into installers. |
| Local identity, filesystem presence, mounts and control interfaces; ADR-024/037/056/057 | **Sound as explicitly scoped host-state profiles.** UID/GID, Unix paths and sudo facts describe that platform; they are not prerequisites for all nodes. Explicit absence, unknown knowledge and redaction remain distinct. Directory principals, app grants and authored accounts retain separate owners. No generic credential/configuration bag is introduced. |
| Container networking, init/reaper, capabilities and limits; ADR-025/027 and `runtime_container*` | **Sound as named platform profiles.** Linux capabilities, OCI/container options and Dockerfile observations have bounded native meanings. Their availability does not force concrete infrastructure or give host privileges. Actual OS/runtime support stays with admission. |
| Node OS/architecture/substrate; #1076/#1077 and #1206 | **Sound corrected identity seam.** Open abstract nodes need no fabricated OS/image choice. Exact supplied identities stay binding; private identity does not establish implementation support. |
| Generated artifacts, content materialization, enterprise identity/access and participant resource profiles; #1208 | **Architectural redesign required at the historical baseline; delivered by the existing #1208 owner.** Its shared typed profile selections replace closed product/implementation menus while preserving output, sensitivity, unit, ownership and admission semantics. This audit does not create another profile host or claim every private operation is implemented. |
| Classification bindings and retained native detection/marking data; #989 and GOV-922 | **Sound separated ownership, with a documentation qualification.** #989 is closed; old scope-inventory statements that it is pending are historical. Authored classifications use generic bindings. A captured detection rule's native tags and a platform's marking policy are not automatically those bindings. Bounded TLP/PAP compatibility records do not claim arbitrary marking-scheme execution or enforcement. |
| Typed forwarding, service-integration and proxy relationships; ADR-052 | **Sound composition boundary.** Scenario edges carry trust/integration relationships and reference the inventory owner. Where endpoint facts overlap, semantic agreement checks retain one meaning. No new relationship or duplicate ship-target owner is needed. |
| Recursive realization, descriptions and observation demand; #1202/#1203/#1204/#1209/#1212 | **Architectural redesign required at the historical baseline; corrections delivered by these existing owners.** Recursive authority preserves exact siblings under open parents. Descriptions carry missing/unknown coverage without inventing values. Detail and observation demand remain independent. #1211 owns integrated acceptance; no whole-language success claim follows from these bounded tests. |
| Grammar operators, grant effects, protection classes, schema versions, solver bounds and backend driver modes | **Sound retained closed boundaries.** Each token selects defined semantics or an implementation mode. Arbitrary strings must not become an operation, a permission, a successful observation or a formal guarantee. These are false positives for a catalog census. |

Retained native manifests deserve explicit limits. Redis RDB/AOF options, Wazuh
decoder/SID relations, platform legacy content attributes and systemd states
are optional data under their containing versioned contract. They do not supply
a universal persistence, detection, application-content or service-manager
semantic model. Their shape is not a substitute for a pinned typed extension
when a new executable meaning is required. An arbitrary attribute bag is never
evidence that a previously absent portable concept has been modeled.

## Confirmed findings and correction contracts

### F1 — Generic manager identity still requires systemd names

`ServiceManagerUnit` with `unit_id=web`, `manager_kind=x-openrc:openrc` and
`unit_name=nginx` fails `_validate_unit_name` with the unit-type-suffix error.
The manager token is accepted; the surrounding shape is not portable. Omitted
manager identity also materializes the systemd default.

The [OpenRC service guide](https://github.com/OpenRC/openrc/blob/master/service-script-guide.md)
uses unsuffixed native service names. [#1297](https://github.com/OpenRAE/rae/issues/1297)
owns separating native identity and platform state profiles, preserving explicit
systemd records and resolving legacy omitted-manager compatibility. Its tests
must cover exact names, duplicates, redaction, source/schema parity and lifecycle
round trips. Appending a fake `.service` suffix is not a migration.

### F2 — An observed HTTP method is treated as a closed operation catalog

The original defect made `RuntimeApplicationRoute` reject `methods=[PROPFIND]`
and normalize every accepted spelling as though the field were a nine-member
operation catalog. [RFC 9110 §9.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.1)
defines case-sensitive method tokens; [RFC 4918 §9.1](https://www.rfc-editor.org/rfc/rfc4918.html#section-9.1)
defines PROPFIND. These are protocol identities in an inventory, not permission
to invoke a backend operation.

[#1298](https://github.com/OpenRAE/rae/issues/1298) delivered the wire-token
grammar, exact extension identity and explicit compatibility for normalized
built-ins. Its migration preserves serialized uppercase methods and reconciles
duplicates, variables, schemas and comparison. Focused and #1211 integrated
tests cover private case-sensitive tokens, WebDAV, malformed/control characters
and unchanged execution authorization.

### F3 — Listener knowledge is forced into a complete endpoint

`RuntimeServiceListener` with `service_listener_id=web`, `protocol=tcp` and
`port=80` fails because it lacks `address` or `bind_interface`. An explicit
unknown transport with only a local ID fails because all non-Unix values enter
the network endpoint branch. An inherited open parent cannot delegate an
omitted bind choice before that model guard runs.

[Nmap's port-state documentation](https://nmap.org/book/man-port-scanning-basics.html)
and ADR-043's own lineage distinguish remote observations from in-node bind
knowledge. [#1299](https://github.com/OpenRAE/rae/issues/1299) owns conditional
partiality and selected complete-endpoint admission. Existing complete records,
port bounds, supplied address-family/scope contradictions and reference checks
remain valid. Its migration must preserve missing/unknown/empty distinctions
and exact children, without manufactured wildcard binds or automatic telemetry.
The explicitly required SSH service binding is an adjacent review question,
not a claim that SSH's stated daemon-policy profile is already defective.

### F4 — Current guidance repeats removed specimen guards

The validation, limitations and lineage guides still described mandatory
datastore geometry/persistence, the IOC-to-rule/reload recipe and the
read-write Docker-socket suffix test. Current model source, accepted #1207 ADR
amendments and the runtime index disagree with that prose. This audit corrects
those current guides and replaces the required-profile recommendation with
the review checklist below. The historical SCN-010 report and dated #1198
research remain evidence of the original reasoning; they are not rewritten.

## Recurrence prevention and ownership

The [runtime semantic review checklist](../../explain/sdl/validation.md#runtime-semantic-review-checklist)
requires an owner, a reason for any closed set, a distinct implementation/private
case, a partial case, optional-presence behavior, compatibility and selected
admission rules. It explicitly checks backend recipes becoming compulsory
author detail, replacement catalogs and unconditional evidence obligations.

The new coverage test follows the existing runtime registry and Pydantic graph.
It rejects missing models/fields, duplicate classifications and stale source
links in the field ledger. It is a candidate-coverage guard, not a semantic
oracle. The existing `test_runtime_family_invariants.py` checks structural
consistency; its required-profile detector only checks wiring where a model's
documentation explicitly declares such a guard. Passing it does not justify
inventing a guard or establish the portable correctness of one.

#1211 consumes this audit and its three focused corrections when reconciling
the complete candidate ledger. #1167 remains the broader status-prose owner;
this delivery resolves the concrete stale guidance inspected here. #989,
#1206, #1207, #1208, #1209 and #1212 are closed as of this review; that is an
ownership/status fact, not a substitute for the bounded implementation evidence.

## Verification and acceptance map

The first coverage test run failed because the field ledger was absent. After
the ledger was populated, the coverage and negative-mutation cases passed.
The three defect inputs above retain their historical finding context. The
focused corrections have now shipped, and #1211 replays their private and
partial cases through the integrated lifecycle without reopening their runtime
ownership.

Relevant existing executable evidence includes:

- `test_issue_1206_vocabulary_families.py`, `test_issue_1206_vocabulary_schema.py`
  and `test_issue_1206_vocabulary_roundtrips.py`: exact private identity, finite
  operations, schema agreement and abstract/no-inventory cases.
- `test_issue_1207_partial_descriptions.py`, `test_issue_1207_recursive_inventory.py`
  and `test_issue_1207_profile_admission.py`: partial descriptions, explicit empty
  state, exact descendants, nonpersistent caches, non-IOC synchronization and
  independently selected prerequisites/authority.
- `test_runtime_platform_application.py`: #956 capability/content separation.
- `test_issue_1209_description_lifecycle.py` and
  `test_issue_1212_observation_demand.py`: abstraction and observation-demand
  separation. Required capture continues through #1112's admission tests.

Repository completion, policy, review, CI and Sonar results belong to the
issue's durable workflow records. These model tests are not deployed-product
or live-backend evidence.

| Acceptance criterion | Evidence |
| --- | --- |
| Method, selected-family inventory and lineage | Method, shared trace and all 17 family rows above; 115-model field ledger; existing #1206 vocabulary inventory. |
| Evidence-backed disposition for every reviewed surface | Registered and adjacent tables; field-owner classifications with inherited dispositions and explicit exceptions. |
| Focused defects with migration and test impact | F1–F3 and #1297/#1298/#1299. F4 is corrected by this delivery. |
| Retained false positives/product-specific extensions | Adjacent table and native-manifest limits; closed security/grammar/profile rationale. |
| Practical prevention rule/check | Validation checklist and registry-derived field-coverage test; #1211 integration ownership. |
| #956 stays the focused delivered platform correction | Platform row, F4 scope and existing capability regressions. |
| Open parent, binding exact descendants, optional presence | Method steps 5–6; per-family guard analysis; #1206/#1207 recursive tests and F3. |
| Complete abstract models without invented infrastructure | Shared consumer boundaries, adjacent OS/software rows and abstract round-trip tests. |
| Independent representation, reporting, collection, retention/export | Sensor/engine/forwarder rows and #1209/#1212 evidence; no observation request follows from precise inventory. |
| No compulsory core or replacement catalog | Method step 6, vocabulary seam and retained native-data distinctions; private identity is not admitted execution. |
| GOV-922 stable comparison and governed extensions | Existing catalog and `runtime_vocabulary.py`, #1206 schema/private-identity tests, field ledger and this bounded audit of surrounding shapes. |
