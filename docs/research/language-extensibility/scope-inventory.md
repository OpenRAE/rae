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
