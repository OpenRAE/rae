# SDL Limitations

## Known Expressiveness Gaps

These are known current gaps identified through repository tests, examples,
and stress testing against 19 scenarios from 8 platforms. The list is evidence
from the current corpus, not a completeness proof.

### Deployment Authoring Boundaries (by design)

The SDL distinguishes authored deployment intent from observed runtime facts
using the semantic boundary in
[ADR-033](../../decisions/adrs/adr-033-scenario-delivery-boundary-for-runtime-node-state.md).
Backends own deployment-specific mechanics such as Docker Compose profiles,
decisions to publish host ports, image build execution, and engine realization.
The node `runtime` surface can record observed runtime facts for analysis and
parity, including mounts, Linux capabilities, namespace modes, entrypoints,
image commands, extra hosts, DNS options, security flags, resource limits,
health status/logs, filesystem inventory, the local identity
database (`/etc/passwd` users, `/etc/group` groups, and sudo/sudoers grants),
software component identity below package-manager row granularity
([ADR-034](../../decisions/adrs/adr-034-runtime-software-component-inventory.md)),
container network realization (per-network aliases and DNS names,
hostname/domain identity, endpoint MAC/IP/prefix/gateway, backend network and
endpoint identifiers with stability classification, host-published port
bindings, and observable backend driver/IPAM detail —
[ADR-025](../../decisions/adrs/adr-025-container-network-realization-surface.md)),
and the application HTTP route/API/UI surface (route paths and methods, owning
service, auth/session requirements, typed request inputs, responses,
template/static associations, route-specific vulnerability placement, exposed
fixture secrets or diagnostic disclosures, and redirect/error behavior —
[ADR-026](../../decisions/adrs/adr-026-application-http-surface-inventory.md)),
database logical state (databases, schemas, tables, database-local roles,
grants, listeners, settings, and database-access bindings -
[ADR-029](../../decisions/adrs/adr-029-database-logical-state-runtime-surface.md)),
DNS service logical state (authoritative zones, RRsets, typed common RDATA,
resolver policy, forwarders, DNSSEC posture, dynamic-update posture, logging
posture, settings, and evidence refs -
[ADR-039](../../decisions/adrs/adr-039-dns-service-runtime-inventory.md)),
network-sensor monitoring posture (passive or inline NSM/IDS sensor identity,
capture mode/interfaces, monitored network refs, and evidence refs -
[ADR-042](../../decisions/adrs/adr-042-network-sensor-runtime-monitoring.md)),
network detection-engine runtime inventory (app-layer parsers, rule sources,
network zoning/address-set variables, output streams, control channels, and
evidence refs -
[ADR-044](../../decisions/adrs/adr-044-network-detection-engine-runtime-inventory.md)),
application-internal RBAC stores (principals with credential classification,
roles, resource-scoped permission grants, role mappings, and tenants -
[ADR-046](../../decisions/adrs/adr-046-app-authorization-runtime-inventory.md)),
recurring scheduled-job cadence and run-state (closed interval/cron/calendar
recurrence plus observed last/next run and last result, cadence-only -
[ADR-047](../../decisions/adrs/adr-047-scheduled-job-runtime-inventory.md)),
non-relational datastore logical state (search/wide-column/key-value clusters,
structured index mapping/template manifests, partitions with shard/replica or
replication geometry, key-value persistence posture, transport security, and
settings, plus per-node engine provenance — version/
build hash/build type, heap byte bounds, mlockall, a typed per-plugin-versioned
plugin inventory, and a product-neutral client/peer endpoint inventory (published
topology, not OS-bind or host-publication proof) - with partial descriptions,
supplied-state integrity and internal RBAC delegated via `authorization_ref` -
[ADR-048](../../decisions/adrs/adr-048-datastore-service-runtime-inventory.md),
[ADR-058](../../decisions/adrs/adr-058-datastore-node-engine-provenance-and-endpoints.md)),
security-platform application runtime inventory (composable provider-neutral
capabilities, product metadata, markings, upstream bindings, connectors, and
settings; legacy product categories and bounded content-object manifests remain
accepted but deprecated and do not imply completeness -
[ADR-049](../../decisions/adrs/adr-049-platform-application-runtime-inventory.md)),
forwarding / intel-sync agent runtime inventory (sources, transforms, ship
targets, buffer policy, reload channels, and settings for log forwarders and
intel-sync co-processes, with optional composed pipelines and
ship-target node/service refs that resolve at scenario scope -
[ADR-050](../../decisions/adrs/adr-050-forwarding-agent-runtime-inventory.md)),
container-spawn orchestration-authority runtime inventory (engine, scope, spawn
templates, lifecycle policy, realized children, and a privilege class that
may reference a same-node control-interface shell; selected operations require
independent support, prerequisites and authorization -
[ADR-051](../../decisions/adrs/adr-051-orchestration-authority-runtime-inventory.md)),
SIEM/security-monitoring manager runtime inventory (manager identity, listeners,
components, enrolled agents, agent groups, detection-content sets, parsed
detection definitions, and settings -
[ADR-040](../../decisions/adrs/adr-040-security-monitoring-manager-runtime-inventory.md),
[ADR-045](../../decisions/adrs/adr-045-security-monitoring-detection-definition-semantics.md)),
mail-service logical state (listeners, domains, mailbox stores, mailboxes,
aliases, routing rules, queues, and settings -
[ADR-038](../../decisions/adrs/adr-038-runtime-mail-service-logical-state.md)),
file-sharing and resource-access state (shares, principals, access rules, and
access observations -
[ADR-037](../../decisions/adrs/adr-037-runtime-file-service-and-filesystem-presence-semantics.md)),
generic observed service listeners (bind endpoint, transport, address family,
scope, owner, and readiness evidence -
[ADR-043](../../decisions/adrs/adr-043-runtime-service-listener-surface.md)),
and directory/domain/realm/IdP/IAM/federation identity-authority state
(authority namespaces, services, subjects, policies, and typed relationships -
[ADR-032](../../decisions/adrs/adr-032-directory-domain-identity-runtime-surface.md)).
Inter-element access detail is carried by typed relationship subtypes on the
top-level edge - database, mail, forwarding, service-integration, and
reverse-proxy-upstream access
([ADR-052](../../decisions/adrs/adr-052-typed-runtime-relationship-subtypes.md)) -
rather than as untyped relationship properties.
Deliberate non-gaps are recorded as confirmation-folds rather than new surfaces:
a standalone Suricata IDS node is the existing `network_detection_engines` +
`network_sensors` surfaces, a relational database is `database_services`,
OS-local users/groups/sudo are `runtime.local_identity`, and transport/TLS
exposure is `service_listeners` + `applications` + `runtime.network`. The
SCN-010 expressivity gap analysis
([scn010-expressivity-gap-analysis](../../raes/inventory/scn010-expressivity-gap-analysis.md))
records each fold field-for-field, so the observable-parity gate is shown to cut
against over-building as well as under-coverage.
Container image build
provenance is a separate source-artifact expressivity surface tracked by issue
#364 and [ADR-023](../../decisions/adrs/adr-023-container-image-build-provenance-surface.md);
recording either surface in SDL does not make Docker, Compose, or any specific
container engine the normative deployment model.

### Specification-Layer Gaps

These are current SDL expressiveness gaps:

| Gap | Description | Candidate Precedent |
|-----|-------------|-------------------|
| **Hosted registry operations / ecosystem distribution** | OCI-backed module resolution, lockfiles, trust policy, and publishable image-layout packaging exist, but this repository does not operate a shared registry service, signer distribution, or ecosystem-wide discovery policy | Terraform registry, OCI artifact delivery |
| **Manual compensation APIs / advanced rollback patterns** | SDL workflows support explicit automatic compensation targets, reverse-completion rollback ordering, and cancel/timeout/failure compensation observation, but not manual rollback triggers, nested compensation-of-compensation, or richer exception-style recovery surfaces | CACAO v2.0 workflow types, saga compensation patterns |
| **Temporal operators** | STIX-style FOLLOWEDBY/WITHIN for time-ordered event assertions | STIX Patterning Language |
| **Full time and clock model** | The SDL currently exposes timelines, timeouts, and budget-like controls, but it does not provide a full authoring surface for time domains, clock authority, pacing/dilation policy, synchronization mode, or explicit ordering/deadline semantics across different realizations | Time-and-simulation primary references under `research/`, ROS 2 Clock and Time, FMI, ns-3 realtime, DEVS/time-management literature |
| **Full solver-backed verification** | Global proof-style verification that attack paths are reachable and defenses are consistent is not implemented; the repository uses lightweight semantic modeling, invariants, typed contracts, and selective property/state-machine methods | VSDL SMT solver, CRACK Datalog |
| **Full participant behavior surface** | The current `agents` section under-expresses richer role-neutral behavior concerns such as tool/affordance declarations, control-context assets, decision-surface exposure policies, episode structure, and benchmark-oriented participant assets | CybORG, OpenRange, Open Trajectory Gym |
| **Materialized evidence capture and provenance** | SDL has implemented `evidence_requirements` syntax, a published schema, fixtures, and fail-closed validation for portable capture intent. It does not itself materialize captures, prove collection, calculate integrity, retain artifacts, or supply complete run-level provenance and loss reporting; those are processor/backend and experiment-evidence responsibilities | OpenRange, OCSF-informed telemetry models |
| **Multi-tenancy** | Multiple independent exercises sharing infrastructure | Locked Shields team-per-subnet model |

### Ecosystem-Layer Gaps (outside pure SDL syntax)

Some current requirement work is intentionally broader than SDL syntax alone.
These concerns are first-class ecosystem requirements, but they are
not fully materialized as published contracts and implementations:

- participant-implementation manifests for agents, policies, scripts, and
  human-control proxies
- participant-implementation provenance and exposure disclosure in run records
- fully materialized evidence-capture, augmentation-disclosure, and
  participant-exposure contract surfaces

These are not examples of backend leakage into the SDL. They are ecosystem
surfaces that sit alongside the SDL and must remain distinct from authored
scenario meaning.

### Variable Resolution

Variables (`${var_name}`) are stored as literal strings in the model. They are **not** resolved at parse time. This means:

- The validator can confirm that a full-value `${var}` reference has a matching variable definition
- Cross-reference rules that depend on a placeholder's final concrete value are deferred to the repo-owned instantiation phase
- Selected leaf enum-backed property fields are parameterizable, but discriminant/schema-shaping enums and user-defined mapping keys remain concrete
- Type checking of substituted runtime values happens during repo-owned instantiation, before compilation/runtime planning

This is a deliberate design choice (matching CACAO's model), but substitution
semantics are owned by the repo rather than left to backend-specific
interpretation.

## What Has Been Validated

The SDL has been tested against 19 scenarios from 8 platforms. This establishes
coverage over the listed examples; it does not establish general domain
completeness or usability for all cyber-range designs.

| # | Scenario | Source | Nodes | Services | Vulns |
|---|----------|--------|-------|----------|-------|
| 1 | OCR Full Exercise | OCR test suite | 3 | - | 1 |
| 2 | CybORG CAGE-1 | CAGE Challenge 1 | 7 | - | 2 |
| 3 | CybORG CAGE-2 (13-host) | CAGE Challenge 2 | 16 | - | 5 |
| 4 | CALDERA Ransack | CALDERA adversary | 0 | - | 0 |
| 5 | Atomic Red Team T1003 | Atomic tests | 0 | - | 0 |
| 6 | CyRIS DMZ | CyRIS | 7 | 3 | 2 |
| 7 | KYPO CTF | KYPO | 3 | - | 3 |
| 8 | HTB Machine | Hack The Box | 2 | 3 | 2 |
| 9 | Enterprise AD | Multi-domain lab | 10 | - | 6 |
| 10 | Cloud Hybrid | AWS VPC + on-prem | 9 | - | 3 |
| 11 | Exchange + data | SDL extended | 5 | 3 | 1 |
| 12 | CybORG with agents | CAGE-2 + agents | 9 | - | 1 |
| 13 | AD trust + federation | Multi-domain + vars | 6 | - | 2 |
| 14 | Incalmo Equifax | MHBench | 6 | 7 | 2 |
| 15 | NICE Challenge 17 | NICE/NIST | 6 | 9 | 3 |
| 16 | CCDC 2007 | Competition packet | 5 | 11 | 0 |
| 17 | HTB Offshore-style | ProLab | 6 | 11 | 6 |
| 18 | Metasploitable 2 | Classic lab | 2 | 23 | 11 |
| 19 | Locked Shields IT/OT | NATO exercise | 7 | 13 | 0 |

Additionally, a 28-node enterprise lab topology (4 networks, 17 health checks, 17 vulnerabilities) has been described in SDL and validated.

The directory/domain identity surface was added after the older Enterprise AD
and AD trust/federation corpus entries. It is now covered by targeted parser
and model tests plus the hospital ransomware scenario's AD/ADFS
`runtime.identity_authorities` example. That coverage validates RAES's neutral
reference and redaction mechanics; it is not a claim that RAES mirrors full
AD DS, LDAP, Kerberos, SCIM, SAML, OIDC, cloud IAM, or BloodHound schemas.

The DNS runtime surface is covered by targeted parser, model, validator, and
module-composition tests. That coverage validates RAES's neutral RRset,
resolver-policy, evidence-ref, and reference mechanics; it is not a claim that
RAES mirrors full BIND, CoreDNS, PowerDNS, NSD, Knot, provider API, passive
DNS, or telemetry schemas.

Property-based fuzz testing (Hypothesis) has run 1,050+ random inputs through the parser with zero unhandled crashes.

## Research Corpus and Verification Scope

The SDL lineage and precedent documents cite external work at two distinct
evidence levels, and the distinction is load-bearing:

- **Primary-source-verified** — standards, specifications, peer-reviewed papers,
  and technical reports cited by a resolvable DOI or maintainer URL that a
  reader can check directly. These carry lineage and terminology weight.
- **Secondary or current-research** — preprints, surveys-in-progress, vendor
  pages, and project manuals. These may explain terminology or motivate a
  concern but are **not** treated as settled normative authority, and they are
  labelled as such at the point of citation (for example, the TechRxiv
  cyber-range scenario survey cited in [lineage.md](lineage.md) is identified as
  a preprint).

The project's working citation corpus lives in a local, gitignored `research/`
tree — the non-normative `research_notes` root in
[`authority-boundary.yaml`](../../../specs/authority/authority-boundary.yaml) —
so it is not part of the published repository. References that would otherwise
be verifiable only from that private corpus or a private Zotero library are
snapshotted as repo-tracked citation metadata under
[`docs/research/primary/`](../../research/primary/index.md), so every cited
claim is checkable from the repository alone. The experiment-core research log
applies the same discipline — published sources only, preprints excluded as
primary evidence (see its "Source Rule" in
[`2026-05-26-search-log.md`](../../research/experiment-core/2026-05-26-search-log.md)).
