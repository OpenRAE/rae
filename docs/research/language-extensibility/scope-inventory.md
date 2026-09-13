# Issue 1198 scope and disposition inventory

Baseline: `384e8b19`; findings F1–F6 refer to the [design review](design-review.md).
This inventory separates confirmed mechanisms, affected domain families, retained
closed sets, existing fixes, and follow-up checks. It is not a claim that every
field in an affected family is defective.

The 2026-09-05 [design-intent clarification](design-intent.md) applies to every
row: representability is not mandatory authoring or collection; open scopes
delegate descendants; exact children stay binding; abstract models need no
invented concrete infrastructure. The [consistency review](consistency-review.md)
records document/ADR and backlog follow-through. The baseline census and probes
below are unchanged; the clarification is not a claim of new runtime fixes.

## Reproducible census

From the repository root:

```console
implementations/python/.venv/bin/python docs/research/language-extensibility/audit.py census
implementations/python/.venv/bin/python docs/research/language-extensibility/audit.py probes
```

The census includes source paths, line numbers, enum values, Literal sites and
the governed-vocabulary policies. Rerun at the baseline for identical counts;
future revisions will change the inventory. It does not execute scanned source.
Computed enum expressions are not evaluated. Python alias annotations and
custom validators require semantic inspection; `Enum | str` is not evidence
that arbitrary strings are accepted.

The committed [probe results](probe-results.json) record the baseline observations.
The runtime counterexample has an exact-mode negative control; it exercises a
single registered-concern evaluator, not a deployed backend or all admission
gates. The existing package-repository, realization-designation and runtime-
concern regression suites pass (55 tests). Their success does not cover the new
counterexamples or establish that the whole language is conformant.

| Baseline measure | Count |
|---|---:|
| Python package files scanned | 801 |
| Enum definitions, all packages | 425 |
| Enum definitions in authoring package `raes` | 277 |
| Authoring enums containing `other` or `unknown` | 144 |
| Literal annotation sites, all packages | 700 |
| Published JSON schemas scanned | 105 |
| Schema `enum` occurrences | 1,899 |
| Schema `const` occurrences | 964 |
| Schema discriminator occurrences | 73 |
| Schema `additionalProperties: false` occurrences | 2,166 |

Schema counts include repeated embedded definitions, not distinct concepts or
defects. Closed envelopes, statuses and language operators account for much of
this total. No issue count should be derived mechanically from it.

## All indexed runtime families

Paths below are relative to `implementations/python/packages/raes/`. Family
ownership and child identity are checked against
[`specs/sdl/runtime-inventory.md`](../../../specs/sdl/runtime-inventory.md).
All families also participate in the F3/F6 concern/projection review.

| Family and source | Disposition and evidence |
|---|---|
| `service_listeners` — `runtime_listeners.py` | F2: protocol, provenance and scope taxonomies; capture `unknown` must not delegate listener choices. Keep typed address and port validation. |
| `applications` — `runtime_application.py` | F2: protocol and parameter-location taxonomies. HTTP/HTTPS-only route upstream is an explicitly narrow feature; provide extension/composition if another upstream is scenario-significant, not universal arbitrary strings. |
| `database_services` — `runtime_database.py`, `runtime_database_vocab.py` | F2/F3 reproduced: private engine rejected; exact service ID becomes part of an open collection. Keep valid engine/protocol compatibility checks inside owned profiles. |
| `dns_services` — `runtime_dns*.py` | F2 for implementation/role/transport; **qualified exception** for unknown RR types: `other` + `type_code` preserves numeric identity and `rdata` preserves data. Its sentinel still incorrectly affects explicitness. Typed SOA/MX/SRV checks are legitimate. |
| `identity_authorities` — `runtime_directory_identity.py` | F2 for protocols/subject/policy classes. Stable local IDs versus provider IDs is a sound ADR-032 boundary. Attributes do not supply a general executable extension contract. |
| `file_services` — `runtime_file_service.py` | F2 for protocol/principal/action classifications and unknown observations. Preserve separation of configured access from `access_observations`, including explicit denial. |
| `mail_services` — `runtime_mail*.py` | F2 for protocols/auth mechanisms/store kinds and observation statuses. Partial message/queue knowledge must not become realization permission; excluded message counts are a useful existing boundary. |
| `network_sensors` — `runtime_network_sensor.py` | F2: product/capture-mode catalogs. Preserve portable monitoring posture and evidence references; do not claim traffic capture from inventory presence. |
| `network_detection_engines` — `runtime_network_detection.py` | F2: engine, protocol, rule format/source, output format and control catalogs. Keep typed control capabilities; unknown engine identity is not permission to replace its known configuration. |
| `security_monitoring_managers` — `runtime_security_monitoring/`, `runtime_security_monitoring_definitions.py` | F2: implementation/content format/definition vocabularies. Keep identity, service references and actual status separate; product-specific rule languages become profiles, not universal operators. |
| `ssh_servers` — `runtime_ssh_server.py` | Retain explicitly SSH-scoped structure and command classifications. It is not a claim to model every remote-access protocol. F3/F6 still apply to partial policy/capture and nested scopes. |
| `app_authorizations` — `runtime_app_authorization.py` | F2: resource/principal vocabularies mix product shapes (`cql_resource`, `redis_acl`). Retain closed grant effect (`allow`, `deny`) and credential-classification rules. |
| `scheduled_jobs` — `runtime_scheduled_job.py` | Retain the interval/cron/calendar grammar as supported schedule variants; new temporal semantics require a defined profile, not a sentinel. F2 affects last-result knowledge; F3 affects partial descriptions. |
| `datastore_services` — `runtime_datastore*.py` | F2: engines, roles, eviction and replication catalogs. F4 confirmed: data-model guards require geometry/mappings/persistence and reject partial captures. Preserve typed profiles and explicit state constraints. |
| `platform_applications` — `runtime_platform_application*.py` | The #956 mandatory MISP-shaped profile is already corrected. Remaining F2: kind/content/marking vocabularies. `attributes: dict[str, Any]` is not a typed semantic extension system; keep legacy data but qualify comparison/support. |
| `forwarding_agents` — `runtime_forwarding_agent*.py` | F2: product/format/transform/protocol catalogs. F4 confirmed: log-forwarder/content-sync profile guards reject incomplete knowledge and overfit the motivating pipeline. Preserve ownership, enrolled identity and service targets. |
| `orchestration_authorities` — `runtime_orchestration.py` | F2: engine catalog. F4: partial host-root-equivalent knowledge requires a concrete interface. Keep the stronger requirement at execution admission; a partial capture must not grant orchestration authority. |

## Other authoring and runtime surfaces

| Surface | Disposition |
|---|---|
| Packages/repositories — `runtime_packages.py` | F1/F3: APT-only profile, mandatory manager/version, acquisition versus final state, collection authority. Private APT URI is already representable; arbitrary private profile is not. |
| Service units — `runtime_service_units.py` | F2: systemd/other/unknown and systemd-shaped states. Preserve systemd as a precise profile; ordinary service state should not require systemd semantics. |
| Filesystem, mounts, local identity, network — `runtime_filesystem.py`, `runtime_mounts.py`, `runtime_identity.py`, `runtime_network.py` | F2/F3: unknown presence, source kinds, network drivers and provenance. Explicit absence and redaction must remain facts. Existing sensitive-value protections remain binding. |
| Container/process/security — `runtime_configuration.py`, `runtime_container*.py`, `runtime_capabilities.py`, `runtime_resource_limits.py` | Concrete container options and Linux capability sets are legitimate within explicit platform profiles. Keep declared limits, permissions and security posture binding. CPU/memory/resource taxonomies and `other`/`unknown` participate in partiality/extension review; do not infer universal host implementation from these options. |
| Software, dependency manifests, image provenance — `runtime_software.py`, `image_provenance.py` | Useful identity/provenance and adjacent F2 classifications. Product names, purls, hashes and artifact coordinates already act as data. They do not by themselves grant a source label acquisition semantics. |
| Node OS/architecture/substrate — `nodes.py`, `architectures.py`, `operating_systems.py`, `realization_designation.py` | Architecture/distribution and substrate support governed extensions; #1076/#1077 are positive precedents. OS-family authoring still uses its enum parser while the capability vocabulary allows extensions: reconcile. `compute`/`switch` are structural language kinds, not a VM/container catalog. |
| Generated artifacts — `stateful_resources.py`, `raes_contracts/vocabulary.py` | F5: only three generator kinds. Retain their precise output/sensitivity/ownership invariants; provide independent typed generation profiles. |
| Content materialization — `content.py` | F5: two closed interface profiles versus an extensible backend profile vocabulary. Base file/dataset/directory classification is a bounded current language abstraction; unfamiliar domain content needs an explicit extension owner. |
| Accounts — `accounts.py` | Authentication-method and credential-purpose normalizers already accept governed extensions; retain. Credential source discriminators and raw-value boundaries are intentional closed semantics. |
| Enterprise domains/facades/access — `identity_domains.py`, `enterprise_identity.py`, `agents.py` | F5: AD domain, OIDC facade, bounded federation and SSH/RDP access selection. Keep existing profiles exact; permit additional profiles under shared identity/admission rules. Direction and authorization values are not product catalogs. |
| Roles/classifications — `entities.py`, `vulnerabilities.py`, participant classification fields | Existing #989 owns migration to generic concept bindings; avoid a second issue per external scheme. Researcher intent must not be reduced to cyber team colors or an intrinsic weakness label. |
| Participant resources — `participant_resource_budgets.py` and contract equivalents | Resource kinds are extensibility candidates (tokens/images/accelerators are not the universe of resources). Preserve closed accounting/reset operations; include units, ownership, enforcement and evidence in any new resource profile. |
| Relationships and references | Preserve direction, local identity, resolved endpoints and core operational relations. Additional domain relations need typed extension semantics when operational, or generic bindings when classificatory; not arbitrary executable relation strings. |

## Cross-layer and retained finite boundaries

| Surface | Disposition |
|---|---|
| `explicitness.py`; compiler concern explicitness/posture/requirements | F2/F3 confirmed. Prioritize loss of exact sibling authority. Default/variable provenance already exists and must survive the replacement. |
| SEM-218/219 concern registry and bounded domains | Existing reusable authority; whole-collection registration and shallow finite domain kinds limit composition. Extend a shared relation rather than register every leaf manually. Preserve declared complexity bounds. |
| Backend manifests and controlled vocabularies | Positive existing governed extensions; some authoring/capability mismatches. Domain/kind strings that are merely compared as opaque strings are not validated executable semantics. |
| Runtime snapshot/projection/evidence contracts | F6: SDL TypeAdapter/defaults constrain capture; preserve provenance, scope, redaction, commitments and incompatible/missing evidence. Arbitrary JSON retention alone is not semantic support. |
| Canonical serialization, formatting, composition, migration and semantic comparison | Cross-cutting acceptance obligations: preserve missing/empty/unknown, extensions, stable identities and exact leaves through round trips. Do not claim a new independent defect in each tool without a probe. |
| Delegated-choice admission versus universal envelope conformance | ADR-070/formal R4 define subset coverage; `raes_processor/semantics/realization.py` calls subsumption for open demand. #1201/#1204 must identify each quantifier and permit a supported chosen completion where intended. This is a source-backed alignment concern, not a new full-run counterexample. |
| Abstraction level and observation/reporting demand | A complete abstract model must not require a concrete OS/package model. #1212 owns scoped demand independent of scenario detail; #1209 applies it to reports/captures, and #1112 continues to enforce genuinely required evidence. No blanket inventory/trace/provenance obligation. |
| Workflow operators, truth outcomes, comparison outcomes, lifecycle states, grant effects and control-plane decisions | Retain closed sets where each value has defined operational meaning. Unknown/new execution operations should require a semantic extension/revision; accepting arbitrary strings is unsafe. |
| Contract IDs, schema versions, crypto formats within named profiles | Retain exact discriminators. Version negotiation and extensible containing envelopes are separate from validating one version. |
| Reference/libvirt backend driver modes and CLI output formats | Implementation capability limits, not universal language catalogs. Not F1/F2 by themselves. Actual backend omissions remain honestly unsupported; extraction work belongs to #967. |
| Experiment selection, bounded proof/solver fragments, timing and variation operators | Retain defined mathematical operators and bounded evaluators. A finite implementation is not proof that the language can describe every phenomenon, but extension must not fabricate formal guarantees. |

## Existing work to reconcile

- [#959](https://github.com/OpenRAE/rae/issues/959): product-shaped SDL audit;
  use these findings as evidence and account for all confirmed families.
- [#956](https://github.com/OpenRAE/rae/issues/956): fixed platform profile;
  retain it as a regression example, not an open defect.
- [#989](https://github.com/OpenRAE/rae/issues/989): classification migration;
  generic binding contract #986 is already delivered.
- [#1112](https://github.com/OpenRAE/rae/issues/1112): backend capture capability
  admission; coordinate with the capture/partiality work.
- [#1068–1072](https://github.com/OpenRAE/rae/issues/1068): modular participant
  control and extensible IFC; retain their ownership and security semantics.
- [#1168](https://github.com/OpenRAE/rae/issues/1168): developer artifact tooling;
  related offline/integrity concerns, but not the owner of scenario repository
  semantics or backend acquisition choices.
- [#1167](https://github.com/OpenRAE/rae/issues/1167): stale status prose;
  reconcile claims of complete SEM-218 enforcement with the bounded findings.

This audit does not close existing implementation issues or reopen completed
corrections. The milestone tracks the shared redesign and concrete remediation,
with links to existing owners rather than duplicated backlogs. Audit #1198 can
close when its documentation is published; implementation exit criteria remain
with the milestone and its follow-ups.


## Issue 1206 implementation dispositions (2026-09-12)

The baseline census above remains historical. This disposition pass covers every
runtime enum in that census, including finite sets without sentinels, plus the
adjacent authoring candidates below. The owning Python definition identifies the
shared published SDL type; all fields using it receive the same disposition.
The catalog's `sdl.definitions.<EnumName>` scope names that shared definition,
not a new family registry. Existing family/child identities remain in the runtime
index. No private product is added to a catalog by these conformance examples.

RAE owns semantics, contracts and conformance, per
[OpenRAE/hub#3](https://github.com/OpenRAE/hub/issues/3). The motivating scenario
and backend are context. Packs own scenario content and backends own concrete
realization/operations; this migration introduces neither recipes nor backend
implementations.

Every row was checked against these four independent obligations:

- **Inheritance:** an omitted field follows its enclosing realization scope;
  none of these dispositions requires a product, profile or catalog membership
  for a backend-internal choice. Existing typed-profile guards remain scoped to
  explicit supported profiles; #1207 owns their partial-description correction.
- **Exact descendants:** an authored identity, numeric DNS type, finite state or
  policy remains binding. Knowledge sentinels cannot weaken siblings or become
  a finite choice among core products. Shared recursive constraints carry these
  distinctions; typed operational extensions require admitted meaning.
- **Abstraction:** these fields apply only to a declared host surface. Their
  representability adds no OS/package/runtime inventory to an abstract model.
- **Observation:** identity, availability, selected configuration, provenance and
  verification are distinct. No row creates collection, retention or export
  demand; #1212/#1112 and the #1209 reporting integration remain the owners.

**Governed identity** means the external namespace owner owns a private term;
RAE owns its host field and exact token comparison. Core aliases retain their
existing normalization; private tokens are never slugged or case-folded. The
shared vocabulary validator, SDL field adapter, typed projections, canonical
codecs and recursive relation are its consumers. The existing core terms are
compatibility shorthand, not a compulsory catalog. Typed semantic operations
continue through the shared domain-profile contract, not token spelling.

**Retained semantics** means RAE or the explicitly selected named profile owns
the finite operation/state/shape. New tokens require defined semantics rather
than silently selecting an operation. Legacy knowledge spellings are preserved
without becoming permission. Native IDs, units and values remain data in their
existing typed fields.

| Shared type | Owning definition | Disposition and semantic reason |
| --- | --- | --- |
| `RuntimeAppAuthorizationResourceVocabulary` | [`runtime_app_authorization.py`](../../../implementations/python/packages/raes/runtime_app_authorization.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeAppAuthorizationPrincipalKind` | [`runtime_app_authorization.py`](../../../implementations/python/packages/raes/runtime_app_authorization.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeAppAuthorizationCredentialClassification` | [`runtime_app_authorization.py`](../../../implementations/python/packages/raes/runtime_app_authorization.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeAppAuthorizationGrantEffect` | [`runtime_app_authorization.py`](../../../implementations/python/packages/raes/runtime_app_authorization.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeApplicationProtocol` | [`runtime_application.py`](../../../implementations/python/packages/raes/runtime_application.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeApplicationParameterLocation` | [`runtime_application.py`](../../../implementations/python/packages/raes/runtime_application.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeApplicationRouteUpstreamScheme` | [`runtime_application.py`](../../../implementations/python/packages/raes/runtime_application.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeProcessRole` | [`runtime_capabilities.py`](../../../implementations/python/packages/raes/runtime_capabilities.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeCapabilityOverrideScope` | [`runtime_capabilities.py`](../../../implementations/python/packages/raes/runtime_capabilities.py) | Retained semantics: finite operation/relation meaning; another operation needs a typed semantic contract. |
| `RuntimeRestartPolicy` | [`runtime_configuration.py`](../../../implementations/python/packages/raes/runtime_configuration.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `DatabaseEngine` | [`runtime_database_vocab.py`](../../../implementations/python/packages/raes/runtime_database_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DatabaseProtocol` | [`runtime_database_vocab.py`](../../../implementations/python/packages/raes/runtime_database_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DatabaseObjectOrigin` | [`runtime_database_vocab.py`](../../../implementations/python/packages/raes/runtime_database_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DatabaseRoleType` | [`runtime_database_vocab.py`](../../../implementations/python/packages/raes/runtime_database_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DatabaseSettingProvenance` | [`runtime_database_vocab.py`](../../../implementations/python/packages/raes/runtime_database_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DatabaseObjectType` | [`runtime_database_vocab.py`](../../../implementations/python/packages/raes/runtime_database_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `DatabaseAuthMethod` | [`runtime_database_vocab.py`](../../../implementations/python/packages/raes/runtime_database_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeDatastoreEngine` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeDatastoreDataModel` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeDatastorePartitionKind` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeDatastoreNodeRole` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeDatastoreNodeEndpointRole` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeDatastoreEvictionPolicy` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeDatastoreReplicationStrategy` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeDatastoreTransportSecurityMode` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeDatastoreSettingScope` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeDatastoreSettingProvenance` | [`runtime_datastore_vocab.py`](../../../implementations/python/packages/raes/runtime_datastore_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeIdentityAuthorityKind` | [`runtime_directory_identity.py`](../../../implementations/python/packages/raes/runtime_directory_identity.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeIdentityAuthorityProtocol` | [`runtime_directory_identity.py`](../../../implementations/python/packages/raes/runtime_directory_identity.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeIdentitySubjectKind` | [`runtime_directory_identity.py`](../../../implementations/python/packages/raes/runtime_directory_identity.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeIdentityRelationshipKind` | [`runtime_directory_identity.py`](../../../implementations/python/packages/raes/runtime_directory_identity.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeIdentityPolicyKind` | [`runtime_directory_identity.py`](../../../implementations/python/packages/raes/runtime_directory_identity.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeIdentityRecordOrigin` | [`runtime_directory_identity.py`](../../../implementations/python/packages/raes/runtime_directory_identity.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DnsServerImplementation` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DnsServiceRole` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DnsZoneKind` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DnsZonePurpose` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DnsRecordClass` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Retain the precise DNS wire-class profile; another class needs numeric/profile semantics, not an invented textual wire code. |
| `DnsRecordType` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Already corrected numeric extension: retain type_code + RDATA and typed RR validation; distinct uint16 codes remain exact. |
| `DnsRecordProvenance` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DnsForwarderTransport` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `DnsForwardingPolicy` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `DnssecValidationMode` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `DnsSettingProvenance` | [`runtime_dns_vocab.py`](../../../implementations/python/packages/raes/runtime_dns_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeEnvironmentValueClassification` | [`runtime_environment.py`](../../../implementations/python/packages/raes/runtime_environment.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeEnvironmentVariableProvenance` | [`runtime_environment.py`](../../../implementations/python/packages/raes/runtime_environment.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeFileServiceProtocol` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeFileShareKind` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeFileServicePrincipalKind` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeFileServicePrincipalStatus` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `RuntimeFileServicePrincipalOrigin` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeFileServiceCredentialClassification` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeFileServiceAccessAction` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Retained semantics: finite operation/relation meaning; another operation needs a typed semantic contract. |
| `RuntimeFileServiceAccessEffect` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeFileServiceAccessBasis` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeFileServiceAccessOutcome` | [`runtime_file_service.py`](../../../implementations/python/packages/raes/runtime_file_service.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeMountPropagation` | [`runtime_filesystem.py`](../../../implementations/python/packages/raes/runtime_filesystem.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeFilesystemEntryType` | [`runtime_filesystem.py`](../../../implementations/python/packages/raes/runtime_filesystem.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeFilesystemPresence` | [`runtime_filesystem.py`](../../../implementations/python/packages/raes/runtime_filesystem.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `RuntimeFilesystemStability` | [`runtime_filesystem.py`](../../../implementations/python/packages/raes/runtime_filesystem.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSensitivityClassification` | [`runtime_filesystem.py`](../../../implementations/python/packages/raes/runtime_filesystem.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeForwardingAgentImplementation` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeForwardingAgentKind` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeForwardingAgentOwnershipRole` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeForwardingSourceKind` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeForwardingParseFormat` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeForwardingTransformKind` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Retained semantics: finite operation/relation meaning; another operation needs a typed semantic contract. |
| `RuntimeForwardingProtocol` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeForwardingBufferCrypto` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeForwardingReloadChannelKind` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeForwardingSettingProvenance` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeForwardingEnrollmentClassification` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeForwardingSettingClassification` | [`runtime_forwarding_agent_vocab.py`](../../../implementations/python/packages/raes/runtime_forwarding_agent_vocab.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeIdentityProvenance` | [`runtime_identity.py`](../../../implementations/python/packages/raes/runtime_identity.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSudoPrincipalKind` | [`runtime_identity.py`](../../../implementations/python/packages/raes/runtime_identity.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeListenerProtocol` | [`runtime_listeners.py`](../../../implementations/python/packages/raes/runtime_listeners.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeListenerAddressFamily` | [`runtime_listeners.py`](../../../implementations/python/packages/raes/runtime_listeners.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeListenerScope` | [`runtime_listeners.py`](../../../implementations/python/packages/raes/runtime_listeners.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeListenerProvenance` | [`runtime_listeners.py`](../../../implementations/python/packages/raes/runtime_listeners.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMailProtocol` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMailListenerRole` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMailTlsMode` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeMailAuthMechanism` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMailComponentKind` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMailDomainRole` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMailMailboxStoreKind` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMailMailboxRole` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMailMailboxStatus` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `RuntimeMailCredentialClassification` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeMailRoutingKind` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeMailQueueKind` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMailQueueStability` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `RuntimeMailSettingProvenance` | [`runtime_mail_vocab.py`](../../../implementations/python/packages/raes/runtime_mail_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeMountSourceKind` | [`runtime_mounts.py`](../../../implementations/python/packages/raes/runtime_mounts.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeControlInterfaceKind` | [`runtime_mounts.py`](../../../implementations/python/packages/raes/runtime_mounts.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeControlInterfaceAccess` | [`runtime_mounts.py`](../../../implementations/python/packages/raes/runtime_mounts.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeNetworkDriver` | [`runtime_network.py`](../../../implementations/python/packages/raes/runtime_network.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionEngineImplementation` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionEngineKind` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionAppProtocol` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionRuleSourceKind` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionRuleFormat` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionNetworkSetKind` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionOutputFormat` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionEventType` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionControlChannelKind` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkDetectionControlCapability` | [`runtime_network_detection.py`](../../../implementations/python/packages/raes/runtime_network_detection.py) | Retained semantics: finite operation/relation meaning; another operation needs a typed semantic contract. |
| `RuntimeNetworkSensorImplementation` | [`runtime_network_sensor.py`](../../../implementations/python/packages/raes/runtime_network_sensor.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkSensorKind` | [`runtime_network_sensor.py`](../../../implementations/python/packages/raes/runtime_network_sensor.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeNetworkSensorMonitoringPosture` | [`runtime_network_sensor.py`](../../../implementations/python/packages/raes/runtime_network_sensor.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeNetworkSensorCaptureMode` | [`runtime_network_sensor.py`](../../../implementations/python/packages/raes/runtime_network_sensor.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeOrchestrationEngine` | [`runtime_orchestration.py`](../../../implementations/python/packages/raes/runtime_orchestration.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeOrchestrationPrivilegeClass` | [`runtime_orchestration.py`](../../../implementations/python/packages/raes/runtime_orchestration.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RelationshipServiceIntegrationKind` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RelationshipServiceIntegrationDirection` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Retained semantics: finite operation/relation meaning; another operation needs a typed semantic contract. |
| `RuntimePlatformApplicationKind` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimePlatformApplicationCapabilityKind` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Retained semantics: finite operation/relation meaning; another operation needs a typed semantic contract. |
| `RuntimePlatformApplicationContentObjectKind` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimePlatformApplicationMarkingScheme` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimePlatformApplicationUpstreamBindingRole` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimePlatformApplicationConnectorKind` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimePlatformApplicationSettingProvenance` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimePlatformApplicationSettingClassification` | [`runtime_platform_application_vocab.py`](../../../implementations/python/packages/raes/runtime_platform_application_vocab.py) | Retained semantics: defined protection, permission or authentication state; extensions cannot weaken egress or authority. |
| `RuntimeScheduledJobScheduleKind` | [`runtime_scheduled_job.py`](../../../implementations/python/packages/raes/runtime_scheduled_job.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeScheduledJobLastResult` | [`runtime_scheduled_job.py`](../../../implementations/python/packages/raes/runtime_scheduled_job.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `RuntimeSecurityMonitoringImplementation` | [`runtime_security_monitoring/_enums.py`](../../../implementations/python/packages/raes/runtime_security_monitoring/_enums.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSecurityMonitoringManagerKind` | [`runtime_security_monitoring/_enums.py`](../../../implementations/python/packages/raes/runtime_security_monitoring/_enums.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSecurityMonitoringListenerRole` | [`runtime_security_monitoring/_enums.py`](../../../implementations/python/packages/raes/runtime_security_monitoring/_enums.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSecurityMonitoringComponentKind` | [`runtime_security_monitoring/_enums.py`](../../../implementations/python/packages/raes/runtime_security_monitoring/_enums.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSecurityMonitoringComponentStatus` | [`runtime_security_monitoring/_enums.py`](../../../implementations/python/packages/raes/runtime_security_monitoring/_enums.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `RuntimeSecurityMonitoringAgentStatus` | [`runtime_security_monitoring/_enums.py`](../../../implementations/python/packages/raes/runtime_security_monitoring/_enums.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `RuntimeSecurityMonitoringContentKind` | [`runtime_security_monitoring/_enums.py`](../../../implementations/python/packages/raes/runtime_security_monitoring/_enums.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSecurityMonitoringContentFormat` | [`runtime_security_monitoring/_enums.py`](../../../implementations/python/packages/raes/runtime_security_monitoring/_enums.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSecurityMonitoringSettingProvenance` | [`runtime_security_monitoring/_enums.py`](../../../implementations/python/packages/raes/runtime_security_monitoring/_enums.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSecurityMonitoringDetectionEngine` | [`runtime_security_monitoring_definitions.py`](../../../implementations/python/packages/raes/runtime_security_monitoring_definitions.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSecurityMonitoringDetectionDefinitionKind` | [`runtime_security_monitoring_definitions.py`](../../../implementations/python/packages/raes/runtime_security_monitoring_definitions.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSecurityMonitoringFieldPredicateOperator` | [`runtime_security_monitoring_definitions.py`](../../../implementations/python/packages/raes/runtime_security_monitoring_definitions.py) | Retained semantics: finite operation/relation meaning; another operation needs a typed semantic contract. |
| `ServiceManagerKind` | [`runtime_service_units.py`](../../../implementations/python/packages/raes/runtime_service_units.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `ServiceUnitKind` | [`runtime_service_units.py`](../../../implementations/python/packages/raes/runtime_service_units.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `ServiceUnitLoadState` | [`runtime_service_units.py`](../../../implementations/python/packages/raes/runtime_service_units.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `ServiceUnitActiveState` | [`runtime_service_units.py`](../../../implementations/python/packages/raes/runtime_service_units.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `ServiceUnitEnabledState` | [`runtime_service_units.py`](../../../implementations/python/packages/raes/runtime_service_units.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `ServiceUnitResult` | [`runtime_service_units.py`](../../../implementations/python/packages/raes/runtime_service_units.py) | Retained semantics: defined state/knowledge outcomes; a novel spelling cannot count as successful execution or permission. |
| `ServiceUnitExecStartKind` | [`runtime_service_units.py`](../../../implementations/python/packages/raes/runtime_service_units.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `RuntimeSoftwareComponentType` | [`runtime_software.py`](../../../implementations/python/packages/raes/runtime_software.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `RuntimeSoftwareComponentProvenance` | [`runtime_software.py`](../../../implementations/python/packages/raes/runtime_software.py) | Governed identity; external product/protocol/format, provenance or descriptive class; exact comparison grants no executable support. |
| `SshForcedCommandKind` | [`runtime_ssh_server.py`](../../../implementations/python/packages/raes/runtime_ssh_server.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |
| `SshMatchCriterionKind` | [`runtime_ssh_server.py`](../../../implementations/python/packages/raes/runtime_ssh_server.py) | Retained semantics: precise structural/grammar or named platform profile; new shapes require typed semantics and existing admission. |

### Adjacent candidates and coordinated owners

| Candidate surface/types | Disposition and owner |
| --- | --- |
| `OSFamily` | Governed identity using the existing `provisioner-os-families` policy, now shared by authoring and capability consumers. Core node types remain structural. |
| `ImageAttestationType` | Governed format identity; `status` and `verification` stay independent. A private format does not claim a verifier exists. |
| `DockerfileInstructionKind` | Retain the precise Dockerfile observation grammar. Other generation/materialization semantics belong to the shared profile migration in #1208, not another recipe in RAE. |
| `ImageAttestationStatus`, `ImageVerificationStatus` | Retain finite availability/verification outcomes, including the prohibition on verified-but-absent attestations. |
| `EvidenceRequirementSourceClass`, `EvidenceRequirementChannel` | Existing requested-observation host vocabulary; typed capture/report extensions are coordinated with #1209/#1212/#1112, not inferred from a runtime identity token. |
| `EvidenceRedactionExpectation`, `EvidenceIntegrityExpectation`, `EvidenceRetentionExpectation`, `EvidenceLossDisclosureExpectation` | Retain explicit evidence-policy operations and limitations. Unknown mechanisms do not authorize collection or establish achieved integrity. |
| `ParticipantFailureClass`, `TruthValue` | Retain finite execution and logical outcomes. Unresolved/unsupported cannot become success by adding a token. |
| `RuntimePackage.manager`, repository profiles | Existing string identity and precise repository profiles; #1205 owns acquisition versus final state. Package coordinates remain exact data. No package installation implementation is added here. |
| Architecture, OS distribution, substrate; account authentication and credential purpose | Retain existing governed extensions and exact/native field ownership; no second extension syntax or arbitrary credential-source discriminator. |
| Participant resource kind, meter/profile refs, unit, accounting/reset; operational relations | #1208 owns typed resource/profile extension. Preserve unit/ownership/enforcement conjunction, finite accounting operations and endpoints. |
| Generated artifact kinds, content profiles, identity domains/facades/access | #1208 owns shared typed generation/materialization and adjacent profile migration. Preserve explicit output/sensitivity and exact versioned profiles. |
| Roles, vulnerabilities, markings and participant classifications | #989 owns existing external concept-binding migration; #959 remains the audit owner. `RuntimePlatformApplicationMarkingScheme` retains its current explicit marking profile until migrated by that owner. |
| Runtime filesystem/network/container native strings, software coordinates, purls, hashes, provider IDs | Already identity-preserving data under their own shape contracts. Do not translate native punctuation/case to governed tokens or infer acquisition/support from a label. |
| CLI output modes, backend driver modes, contract versions, crypto formats, bounded solver/timing/workflow operators | Retain precise implementation/contract/mathematical semantics; they are not universal product vocabularies. Backend extraction remains #967. |

### Executable evidence

`test_issue_1206_vocabulary_families.py` exercises every migrated runtime enum
with distinct private terms and malformed/variable controls.
`test_issue_1206_vocabulary_schema.py` walks actual model fields and checks both
identity extension and finite-operation rejection through Python and JSON Schema.
`test_issue_1206_runtime_vocabularies.py` checks inherited scope, exact descendants,
unknown knowledge, OS-family parity, grant agreement and engine/protocol pairing.
`test_issue_1206_vocabulary_consumers.py` covers numeric DNS identity, forwarding
agreement and image-attestation knowledge. `test_issue_1206_vocabulary_roundtrips.py`
covers family projections, module composition, instantiated/canonical snapshots,
legacy conversion and an abstract model with no invented inventory or observation
demand. Shared #1202/#1203/#1204/#1212 suites remain the support/admission and
scoped-demand regression authorities; none of these probes claims live product
or backend support.
