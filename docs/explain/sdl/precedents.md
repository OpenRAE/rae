# SDL Design Precedents

## Design-intent correction in progress

The runtime inventory precedents below describe existing surfaces, not a
requirement that every author specify or capture their full contents.
[#1201](https://github.com/OpenRAE/rae/issues/1201) deliberately corrects the
tendency to promote backend recipes and captured specimens into mandatory SDL
detail or core catalogs. Open scopes delegate unspecified descendants to the
backend while explicit constraints stay binding; abstract models can already
be complete; observation/reporting demand is independent of scenario detail.
Required-profile guards in the historical tables are remediation candidates,
not universal authoring guidance. See [clarified design intent](../../research/language-extensibility/design-intent.md)
and [scope inventory](../../research/language-extensibility/scope-inventory.md).
Current syntax and validation are not changed by this note.

## Sources and interpretation

RAES combines externally influenced and RAES-native language families. This
document summarizes design influences and comparisons; the revision-pinned,
machine-readable provenance record is
[`contracts/provenance/sdl-lineage-ledger-v1.json`](../../../contracts/provenance/sdl-lineage-ledger-v1.json).
Only the ledger classifies provenance, artifact/code derivation, compatibility,
and notice obligations. A source named here may explain a design concern
without being a source from which RAES adopted syntax, semantics, or code.

The SDL does not borrow every concern from the same place. In practice:

- the **section layout and author-facing YAML surface** start from Open Cyber
  Range SDL
- **exercise intent, variables, and workflow graph shape** draw primarily from
  CACAO
- **cross-object reference style** draws from STIX
- **control-flow semantics** are tightened using mature workflow and
  state-machine systems such as AWS Step Functions, Argo Workflows, and W3C
  SCXML
- **portable runtime/result contracts** follow the language-neutral boundary
  style used by systems such as Kubernetes, Temporal, and OpenC2

The tables below are design-rationale summaries: they identify the plane on
which a source informed comparison or adaptation. They are not a parallel
provenance registry.

Each source table adds an **Influence plane** column: *syntax* means the
author-facing shape was compared or adapted, *semantics* means the source
informed meaning or behavior, and *both* means both kinds of design work. These
labels do not assert copying, conformance, or compatibility. The ledger's claim
plane, classification, exact source boundary, and divergence are authoritative.
The "Deliberate Omissions" table carries no influence-plane column.

## Core Structure (from Open Cyber Range SDL)

The base sections have syntax and translated-model ancestry in
[OCR SDL v0.21.2](https://github.com/Open-Cyber-Range/SDL-parser/tree/fe83e8281fc4b954967fbaa5a0d099007ddcb06c),
pinned to revision `fe83e8281fc4b954967fbaa5a0d099007ddcb06c`.
The ledger names exact Rust and RAES artifact boundaries and records partial
syntax compatibility only. RAES does not claim drop-in parser, schema,
validation, or runtime compatibility. Per ADR-073, the OCR scoring pipeline
(metrics/evaluations/TLOs/goals) was removed from authored SDL and lives in the
experiment/evaluator plane. OCR SDL was developed by CR14 / the Norwegian
Cyber Range.


| SDL Element | OCR Source | Influence plane | Changes |
| -------------------------- | ------------------------- | --- | --------------------------------------------------- |
| Scenario | `Scenario` struct | Syntax | Added SDL extension fields |
| Node (VM/Switch) | `Node`, `VM`, `Switch` | Syntax | Added `os`, `os_version`, `services`, `asset_value` |
| Resources | `Resources` | Syntax | Human-readable RAM parsing via Python |
| Role | `Role` | Syntax | OCR-adapted syntax and translated model structure; partial syntax compatibility at the pinned revision |
| InfraNode | `InfraNode` | Syntax | Added `acls`, `internal` flag |
| Feature | `Feature` | Syntax | OCR-adapted syntax and translated model structure; partial syntax compatibility at the pinned revision |
| Condition | `Condition` | Both | Added `timeout`, `retries`, `start_period` |
| Vulnerability | `Vulnerability` | Syntax | OCR-adapted syntax and translated model structure; partial syntax compatibility at the pinned revision |
| Metric/Evaluation/TLO/Goal | OCR scoring pipeline | Not adopted | Removed from the SDL per ADR-073; graded scoring/reward lives in the experiment/evaluator plane (ADR-055/064/069) |
| Entity | `Entity` + OCR entity surface | Both | OCR-adapted syntax and translated model structure, including fact-map ancestry; current semantics are RAES-governed |
| Inject/Event/Script/Story | OCR orchestration | Both | OCR-adapted syntax and translated model structure; current orchestration semantics are RAES-governed |
| Source | `Source` (name + version) | Syntax | Made provider-neutral |


## Extensions by Source

### From CybORG CAGE Challenge


| SDL Element | CybORG Source | Influence plane | What We Adapted |
| ----------------------- | ------------------------------------------- | --- | --------------------------------------------- |
| `Agent` | `Agents:` section (Scenario YAML) | Both | Actions, starting sessions, reward calculator |
| `InitialKnowledge` | `INT:` (Initial Network Topology) | Semantics | Known hosts and subnets at start |
| `Agent.allowed_subnets` | `AllowedSubnets:` | Both | Network scope constraints |
| `AssetValue` | `ConfidentialityValue`, `AvailabilityValue` | Semantics | Extended to CIA triad |
| `ACLRule` | `Subnets.NACLs` | Both | Simplified from nested dict to flat rule list |
| `Objective.agent/actions` | Agent identity + action space | Semantics | Objective actor binding and optional action subset validation |
| `Agent.interactive_access` | `Agents.*.starting_sessions[]` in CybORG v3.0 | Semantics | Adapted participant-local explicit host/channel association; RAES uses stable authored ids and references, not established simulator sessions, usernames, or copied syntax |


### From Newer Participant And Benchmark Ecosystems

These sources inform the newer participant-, benchmark-, and exposure-related
ecosystem surfaces. In many cases they are precedents for concerns the
requirements recognize even when the current SDL syntax does not expose the
full shape directly.

| Concern | Primary Sources | Influence plane | What We Adapted |
| ------- | --------------- | --- | --------------- |
| Participant decision surfaces and role-scoped observations | OpenRange episode/runtime model | Semantics | Participant-visible decision context is treated as a first-class concern distinct from hidden truth assets and internal apparatus state |
| Control-context assets (instructions, directives, policies) | OpenRange prompt modes, agent-oriented benchmark/task systems | Semantics | Execution-guiding context is modeled as a participant concern without binding the ecosystem to one prompting or policy framework |
| Trajectories, replay assets, and demonstration corpora | OpenRange training data, Open Thoughts Agent, Open Trajectory Gym | Semantics | Stepwise participant interaction records are first-class experiment artifacts rather than incidental logs |
| Benchmark protocols, judges, verifiers, and rewards | OpenBench, Open Trajectory Gym, agent benchmark systems | Semantics | Tasks, protocols, and evaluation components are treated as distinct experiment objects rather than hidden harness details |
| Hidden truth assets and adjudication surfaces | OpenRange private references, benchmark hidden tests/gold standards | Semantics | Public task statements are kept distinct from hidden benchmark assets and adjudication material |
| Swappable participant implementations | Agent benchmark stacks, provider/model-selectable eval systems | Semantics | Concrete agent/policy/script/human-control implementations are treated as apparatus surfaces distinct from SDL roles, processors, and backends |


### Participant Semantics Theory

Issue #71 adds a formal participant-semantics design in
`specs/formal/participant-semantics/` and ADR-022. These precedents inform that
design without becoming the RAES runtime API or authoring syntax.

| Concern | Primary Sources | Influence plane | What We Adapted |
| ------- | --------------- | --- | --------------- |
| Single-agent episode interface | [OpenAI Gym](https://arxiv.org/abs/1606.01540), [Gymnasium](https://arxiv.org/abs/2407.17032) | Semantics | Actions, observations, rewards, reset, termination, and truncation are explicit semantic concepts rather than incidental adapter methods |
| Multi-agent environment ordering | [PettingZoo](https://arxiv.org/abs/2009.14471), [OpenSpiel](https://arxiv.org/abs/1908.09453), Markov-game literature | Semantics | Per-participant histories and information structure are first-class; joint behavior is not collapsed into one global action stream |
| Partial observability and local history | POMDP, Dec-POMDP, POSG, and imperfect-information game literature | Semantics | Participant-visible state is a projection with history, uncertainty, latency, and disclosure basis, not world truth |
| Cyber-specific action/observation discipline | [CybORG](https://arxiv.org/abs/2108.09118), [CyberBattleSim](https://www.microsoft.com/en-us/research/project/cyberbattlesim/), [CyGIL](https://arxiv.org/abs/2304.01244) | Semantics | Action/effect/observation semantics must disclose simulation, emulation, and realization assumptions instead of assuming transfer across fidelity modes |
| Adversary behavior under uncertainty | [CALDERA planning and acting](https://www.mitre.org/sites/default/files/2021-11/prs-18-0944-1-automated-adversary-emulation-planning-acting.pdf), [MITRE ATT&CK design](https://www.mitre.org/news-insights/publication/mitre-attck-design-and-philosophy) | Semantics | Cyber actions may change foothold, knowledge, detection surface, and downstream outcomes; technique labels do not replace action contracts |
| Causality and temporal ordering | [Lamport ordering](https://systems.cs.columbia.edu/ds2-class/papers/lamport-time.pdf), [Halpern-Pearl structural causality](https://arxiv.org/abs/cs/0011012), HLA time management | Semantics | Attribution edges require explicit ordering and evidence support; timestamp adjacency is not a causal claim |
| Directional backend refinement | [Abadi-Lamport refinement mappings](https://doi.org/10.1016/0304-3975(91)90224-P), [Lynch-Vaandrager simulations](https://doi.org/10.1006/inco.1995.1134) | Semantics | A concrete backend must preserve the abstract participant semantics in the declared direction; finite conformance runs are not a universal simulation proof |
| Participant input/output availability | [Lynch-Tuttle I/O automata](https://groups.csail.mit.edu/tds/papers/Lynch/CWI89.html), [Alur et al. alternating refinement](https://doi.org/10.1007/BFb0055622) | Semantics | Participant/environment inputs and participant-facing outputs retain declared ownership and availability obligations; trace inclusion alone is insufficient |
| Reactive information flow | [Clarkson-Schneider hyperproperties](https://doi.org/10.3233/JCS-2009-0393), [Bohannon et al. reactive noninterference](https://doi.org/10.1145/1653662.1653673) | Semantics | Information-flow claims quantify over adaptive participant strategies, exact-cut policies, and explicit memory scope rather than comparing only fixed open-loop traces |
| Checkable scenario semantics | [VSDL](https://arxiv.org/abs/2001.06681), [CRACK](https://iris.imtlucca.it/handle/20.500.11771/15672), [CyRIS](https://www.jaist.ac.jp/~razvan/publications/cyris_facilitating_training.pdf) | Semantics | Participant semantics inherit the requirement for executable contracts and conformance tests, while staying separate from topology/deployment generation |
| Agent benchmark task structure | [Cybench](https://arxiv.org/abs/2408.08926), [AutoPenBench](https://arxiv.org/abs/2410.03225) | Semantics | Task descriptions, starter files, evaluators, subtasks, gold steps, and milestones are treated as participant-view and outcome-interpretation inputs rather than hidden harness details |
| Integrated adversarial evaluation | [CAIBench](https://arxiv.org/abs/2510.24317) | Semantics | Offensive, defensive, privacy, and cyber-physical capabilities require role-neutral multi-participant semantics and outcome layers richer than final score |
| Benchmark validity and overfitting controls | [AI Agents That Matter](https://arxiv.org/abs/2407.01502), [Benchmarking Practices in LLM-driven Offensive Security](https://arxiv.org/abs/2504.10112) | Semantics | Run/study provenance, holdout discipline, scaffold disclosure, hidden assets, baselines, and cost/resource traces are experimental-instrumentation concerns |
| DSL language adequacy and evaluation | [Do Software Languages Engineers Evaluate their Languages?](https://arxiv.org/abs/1109.6794), [When and How to Develop Domain-Specific Languages](https://doi.org/10.1145/1118890.1118892), [Domain-Specific Languages: A Systematic Mapping Study](https://doi.org/10.1016/j.infsof.2015.11.001) | Semantics | Issue #346 treats expressiveness, usability, effectiveness, maintainability, ambiguity, and domain-expert reviewability as evidence-gated language claims |

For the `SEM-209` implementation slice, RAES represents framework-neutral
joint-action declarations and realized-order provenance. PettingZoo/OpenSpiel
inform participant-local histories and joint behavior, Lamport informs ordering
without causal overclaim, and cyber-agent systems motivate explicit target and
shared-state references without making framework/tool APIs the SDL authority.


### From CyRIS


| SDL Element | CyRIS Source | Influence plane | What We Adapted |
| ----------- | ----------------------------------------- | --- | ------------------------------------------------- |
| `Content` | `copy_content`, `emulate_traffic_capture` | Semantics | Generalized to file/dataset/directory types |
| `Account` | `add_account`, `modify_account` | Semantics | Preserved host account-placement lineage; RAES-specific account metadata such as groups, password strength, SPN, and auth method are extensions, not CyRIS-derived directory semantics |
| `Agent.interactive_access` | `guest_settings[].entry_point` and tunnel selection in CyRIS 1.2 | Semantics | Adapted explicit entry-host eligibility but rejected OS-to-channel inference, tunnel/port mechanics, and generated credentials |


### From Identity, Directory, And Access-Control Sources

The `runtime.identity_authorities` surface is a neutral runtime inventory
surface. It borrows concepts from standards and literature, but does not adopt
one provider schema as the SDL schema.

| SDL Element | Source Class | Influence plane | What We Adapted |
| ----------- | ------------ | --- | --------------- |
| `RuntimeIdentityAuthority` | LDAP/X.500 naming contexts, Kerberos realms, SAML/OIDC issuers, SCIM/IAM tenants, NIST SP 800-63C-4 federation guidance | Semantics | An authority boundary with stable RAES id plus observed namespace facts such as domain, realm, issuer, tenant, and base DN; all authority-local stable ids share one namespace |
| `RuntimeIdentityService` | LDAP/Kerberos/SAML/OIDC/SCIM/IAM protocol endpoints and same-node `Node.services` transport bindings | Semantics | Protocol/API endpoint inventory without treating the endpoint as the directory contents |
| `RuntimeIdentitySubject` | LDAP entries, SCIM Users/Groups, AD users/groups/computers/service principals, SAML/OIDC subjects/clients, IAM roles/applications | Semantics | Identity-bearing subjects with stable RAES ids, observed names/principals, provider identifiers as data, and bounded attributes |
| `RuntimeIdentityPolicy` | NIST SP 800-162 ABAC, RBAC, group policy, Kerberos/domain policy, conditional-access/MFA policy concepts | Semantics | Portable policy records with `applies_to_refs` rather than provider-specific policy-object cloning |
| `RuntimeIdentityRelationship` | Access matrix/RBAC relationship concepts, directory membership, trust/federation/delegation/sync/ownership relations, BloodHound/OpenGraph node-edge analysis | Semantics | Typed local authority edges with stable ids, usable by top-level relationship/objective refs and later attack-graph translation |
| Attribute and setting value classification | OCSF/UCO sensitivity/evidence posture, repository runtime sensitivity vocabulary | Semantics | Secret-bearing identity values are redacted/classified rather than copied into SDL fixtures or diagnostics |

This surface depends on industry standards for protocol/object terminology and
on academic/security literature for the subject-policy-authority separation.
BloodHound/OpenGraph, OCSF, UCO, CASE, LDAP dumps, Graph API payloads, and
backend inspect output are treated as downstream/evidence sources, not as the
canonical authored SDL shape.

The `runtime.app_authorizations` surface is the application-internal RBAC
counterpart: it models the in-app authorization store of search clusters,
key-value stores, dashboards, and platforms, distinct from the wire-protocol
directory above and from database engine GRANTs.

| SDL Element | Source Class | Influence plane | What We Adapted |
| ----------- | ------------ | --- | --------------- |
| `RuntimeAppAuthorization` | Ferraiolo/Kuhn RBAC, Sandhu et al. RBAC96, ANSI INCITS 359 | Semantics | An application-internal authorization store with a stable RAES id and an open `resource_vocabulary` spine discriminator; tier placement is derived from the referencing spine, not declared |
| `RuntimeAppAuthorizationPrincipal` | OpenSearch/Elasticsearch security users, Cassandra `system_auth`, Redis ACL users, dashboard/platform accounts | Semantics | Users, service accounts, API keys, and backend roles with reserved/hidden flags and a `credential_classification` only — no raw bcrypt hash, API key, or password |
| `RuntimeAppAuthorizationGrant` | RBAC96 / ANSI INCITS 359 permission-assignment, NIST SP 800-162 ABAC resource-scoping | Semantics | The defining resource-scoped grant: role reference → actions → resource patterns with an allow/deny effect and a `resource_kind` that is the single author-settable resource vocabulary |
| `RuntimeAppAuthorizationRoleMapping` | OpenSearch backend-role mappings, directory-to-local role bindings | Semantics | Bindings of backend roles, users, or hosts onto a local role |
| `RuntimeAppAuthorizationTenant` | OpenSearch/Kibana tenants, platform namespace scopes | Semantics | Namespace/tenancy scopes within the authorization store |

This surface depends on the RBAC/ABAC standards for the role-permission-subject
spine and on product RBAC implementations for recurring facts; it does not adopt
any one product's security configuration as the canonical authored SDL shape.


### From STIX 2.1


| SDL Element | STIX Source | Influence plane | What We Adapted |
| -------------------------- | --------------------------------------- | --- | ------------------------------------------ |
| `Relationship` | Relationship SRO (typed directed edges) | Both | Simplified to 7 relationship types |
| Cross-reference validation | STIX object referencing model | Semantics | Source/target resolve to any named element |
| `RelationshipForwardingEdge` / `RelationshipServiceIntegration` / `RelationshipProxyUpstream` | Relationship SRO typed-detail pattern | Both | Domain access detail on an edge (syslog enrollment per RFC 5424/5425, API auth per RFC 6749, reverse-proxy upstream per RFC 9110/7239) without re-typing referenced families |


### From CACAO v2.0


| SDL Element | CACAO Source | Influence plane | What We Adapted |
| --------------------- | ---------------------------------- | --- | ---------------------------------------------------------------------- |
| `Variable` | `playbook_variables` | Syntax | Types, defaults, allowed_values |
| `${var}` substitution | CACAO variable substitution syntax | Both (syntax borrowed; resolution semantics deferred to instantiation) | Deferred to instantiation time |
| `Objective` | agent/target/workflow context | Semantics | Declarative actor-target-window-success binding without runtime probes |
| `Workflow` | workflow-step graph patterns | Syntax (graph shape; execution semantics from the workflow-systems table) | Branching/parallel objective composition with SDL-only step types |


### Control-Flow Semantics from Mature Workflow Systems

These sources do not define the YAML keys directly, but they strongly inform
how the runtime interprets workflow behavior after parsing.

| Concern | Primary Sources | Influence plane | What We Adapted |
| ------- | --------------- | --- | --------------- |
| Conditional branching over declared predicates | AWS Step Functions `Choice`, CACAO conditional steps | Semantics | Explicit decision nodes with typed predicate dependencies instead of backend-local branching rules |
| Parallel branch execution and convergence | AWS Step Functions `Parallel`, W3C SCXML `parallel`, Argo DAG fan-out/fan-in patterns | Semantics | Parallel branches are explicit, joins are explicit barriers, and foreign entry into a join is rejected |
| Retry and terminal outcome meaning | AWS Step Functions `Retry`/`Catch`, Argo retry strategy | Semantics | Retry behavior is part of workflow semantics rather than a hidden adapter loop |
| Observable step state | Step Functions execution-visible state, SCXML completion semantics | Semantics | Only selected step kinds expose portable lifecycle/outcome state for predicates and backend results |
| Workflow semantics as a first-class assurance surface | SCXML state-machine model, Kepler FM guidance for workflows/state machines | Semantics | Workflow changes are treated as `FM3` state-machine work, not just parser changes |


### Runtime Boundary and Contract Precedents

These sources inform the runtime/result contract rather than the SDL YAML
surface.

| Concern | Primary Sources | Influence plane | What We Adapted |
| ------- | --------------- | --- | --------------- |
| Language-neutral backend boundary | Kubernetes API objects, Temporal payload/history model, OpenC2 abstract model + JSON serialization | Semantics | Backends exchange plain-data, versioned workflow result envelopes rather than Python object identity |
| Explicit compiled contract between definition and execution | Kubernetes versioned object schemas, Temporal workflow definition vs event-history separation | Semantics | Compiler emits a dedicated `result_contract` instead of forcing the manager to infer semantics from incidental planner payloads |
| Internal typed adapters behind a plain-data boundary | Temporal SDK data conversion, Kubernetes typed models over portable representations | Semantics | Python typed workflow result models are internal normalization helpers, not the backend protocol |
| Distinct apparatus declaration surfaces | OpenRange episode/runtime split, OpenBench model/provider configuration, benchmark registries | Semantics | Processor, backend, and participant-implementation declaration surfaces remain distinct so the same scenario can be run under different apparatus honestly |


### From Time, Simulation, and Co-Simulation Systems

These sources inform the emerging time-model requirements. They are not a
claim that RAES adopts one simulator's worldview wholesale. They are precedents
for the recurring architectural concerns that show up once scenarios must run
honestly across simulation, emulation, and live infrastructure.

The primary research set for this area is curated in
`research/primary/literature/time-and-simulation/`.

| Concern | Primary Sources | Influence plane | What We Adapted |
| ------- | --------------- | --- | --------------- |
| Distinct time domains and clock authority | [ROS 2 Clock and Time](https://design.ros2.org/articles/clock_and_time.html), [FMI 3.0.2](https://fmi-standard.org/docs/3.0.2/) | Semantics | Authored temporal intent and realized clocks cannot be treated as the same thing; multiple clocks and explicit clock authority are first-class concerns |
| Event-driven, logical, and virtual time progression | [SimPy Time and Scheduling](https://simpy.readthedocs.io/en/4.0.2/topical_guides/time_and_scheduling.html), Misra virtual-time work, DEVS literature | Semantics | Time advancement policy is part of system meaning, not just a backend optimization |
| Real-time pacing and synchronization | [ns-3 realtime execution](https://www.nsnam.org/docs/manual/html/realtime.html), adaptive time-dilation work for integrated simulation/emulation | Semantics | Synchronization policy, pacing, and dilation are apparatus properties that affect experiment validity and comparability |
| Simultaneous mixed realization | [NIST UCEF](https://www.nist.gov/ctl/smart-connected-systems-division/iot-devices-and-infrastructures-group/how-does-ucef-work), [ACTING EDL-FG](https://arxiv.org/abs/2605.12170), [HELICS dynamic federations](https://docs.helics.org/en/latest/user-guide/advanced_topics/dynamic_federations.html) | Semantics | A trial may admit simulated, emulated/operational, and hardware components together, but every allocation, topology edge, authority, clock mapping, loss, and failure remains explicit |
| Component composition topology | [NIST integrated HLA federations](https://www.nist.gov/publications/integrating-multiple-hla-federations-effective-simulation-based-evaluations-cps), [ISO 23247-6:2026](https://www.iso.org/standard/87426.html) | Semantics | Integrated, unified, and bridged/federated composition are distinct topology profiles; topology does not imply policy or compatibility |
| Ordering and causality beyond raw timestamps | Time Warp, DEVS, distributed-simulation time-management literature | Semantics | Event order, causality guarantees, and temporal windows/deadlines must be modeled separately from the existence of timestamps |
| Reset, replay, and episode-local temporal semantics | OpenRange episode model, benchmark/task systems, simulation literature | Semantics | Episode boundaries, reset semantics, and replayability are temporal concerns, not just lifecycle bookkeeping |
| Inter-trial and phase-bounded realization changes | [CyGIL](https://arxiv.org/abs/2304.01244), [HELICS dynamic federations](https://docs.helics.org/en/latest/user-guide/advanced_topics/dynamic_federations.html) | Semantics | Cross-trial changes use new linked plan/run identities; within-run membership changes are finite and admitted before execution |
| Interface parity versus transfer evidence | [CybORG](https://arxiv.org/abs/2108.09118), [CyGIL](https://arxiv.org/abs/2304.01244) | Evidence | A common action/observation seam does not establish equivalence; retain simulation-only observations, unrealizable actions, unknown transitions, and bounded transfer results |
| Realized-time disclosure and provenance | OpenRange run/training-data records, co-simulation timing literature | Semantics | Runs need explicit disclosure of the realized time model when results are compared across backends or replayed |


### From OCSF


| SDL Element | OCSF Source | Influence plane | What We Adapted |
| --------------- | ------------------- | --- | -------------------------------- |
| `OSFamily` enum | `Device.os.type_id` | Both | Vocabulary for OS classification |
| `ServicePort` | `NetworkEndpoint` | Both | Simplified port/protocol/name; named bindings become first-class refs |


### From Docker / Deployment Patterns


| SDL Element | Source | Influence plane | What We Adapted |
| ---------------------------------------- | ------------------------------- | --- | ---------------------------- |
| `SimpleProperties.internal` | Docker Compose `internal: true` | Both | Network egress blocking flag |
| `Condition.timeout/retries/start_period` | Docker health check fields | Both | Direct mapping |


## Deliberate Omissions

These concerns have been considered against the scenario/delivery boundary.
The current rule is semantic, not syntax-based: state that exists on a realized
range node and can be invoked, observed, depended on, or affected by
participants is scenario/runtime state even when Docker, Compose, a harness, or
another backend exposes the evidence. The delivery layer is the orchestrator,
host kernel, container runtime, backend adapter, control plane, build executor,
and host-local machinery that creates or controls the range. See
[ADR-033](../../decisions/adrs/adr-033-scenario-delivery-boundary-for-runtime-node-state.md).

This table is checked against the current RAES runtime/source models and the
downstream [Brad-Edwards/aptl#339](https://github.com/Brad-Edwards/aptl/issues/339)
Kali inventory evidence class: Compose service slices, Docker inspect output,
runtime mount/network/capability observations, and image provenance are evidence
to classify, not schema authority. The APTL inventory is motivating downstream
evidence; it is not a claim that all APTL artifacts already satisfy the RAES
redaction contract. The table is a current RAES disposition, not a complete
taxonomy of container, orchestrator, or host-security concerns.


| Concept                                 | Current Disposition                | Where It Belongs                       |
| --------------------------------------- | ---------------------------------- | -------------------------------------- |
| Port mappings (host:container)          | Host publication is runtime/host exposure when observed; the backend decision to publish remains delivery machinery | Container-side listeners remain `Node.services`; observed host bindings belong in `Node.runtime.network.published_ports`; see ADR-025 and ADR-033 |
| Generic process listener bind state (address/interface, protocol, port, scope, owner, readiness evidence) | Observed in-node runtime state, distinct from authored service identity and host publication | `Node.runtime.service_listeners` when observed; same-node service refs remain in `Node.services`, host bindings remain in `runtime.network.published_ports`; see ADR-043 |
| Volume mounts                           | Guest-visible filesystem attachments are runtime node state; host source paths and orchestration choices remain delivery/evidence concerns | `Node.runtime.mounts` and `runtime.filesystem_inventory` when observed; authored file placement remains `Content`; mount `source` and `options` carry sensitivity classification, and `redacted` / `operator_secret` values omit raw host-local details |
| Linux capabilities (NET_RAW, SYS_ADMIN) | Participant-relevant capability posture is runtime node security state, not a raw Compose security field | `Node.runtime.linux_capabilities`, including scoped `process_overrides`; see ADR-030 |
| Docker Compose profiles                 | Backend packaging/selection groups are delivery mechanics unless promoted to an RAES scenario/profile composition surface | Backend implementation layer today; realized node set is represented by SDL `nodes`, not raw Compose profile labels |
| Dockerfile/build execution              | Build executor mechanics are delivery/packaging; observable image/source provenance is an artifact-boundary fact | Backend implementation layer for execution mechanics; `Source.build` provenance when observed; see ADR-023 |
| Observable container image build provenance | Artifact provenance, not deployment authoring | SDL source-artifact surface; see ADR-023 |
| Runtime-effective container entrypoints | Backend/runtime state              | `Node.runtime.container` when observed |
| Runtime software component identity below package-manager rows | Runtime-observed state, not deployment authoring, process execution, or HTTP/API inventory | `Node.runtime.software_components` when observed; see ADR-034 |
| Local identity database (`/etc/passwd`, `/etc/group`, sudoers) | Runtime-observed state, not deployment authoring | `Node.runtime.local_identity` when observed; see ADR-024 |
| Container network realization (aliases, DNS names, endpoint metadata, host-published bindings) | Runtime-observed state, not topology authoring | `Node.runtime.network` when observed; see ADR-025 |
| Network-sensor monitoring posture (NSM/IDS packet observation of declared networks) | Runtime-observed node state, not connectivity, node roles, or manager inventory | `Node.runtime.network_sensors` when observed; monitored networks resolve to declared switch-backed infrastructure; see ADR-042 |
| IDS/NDR detection-engine runtime inventory (enabled parsers, rule sources, zoning/address-set variables, outputs, reload controls) | Detection-engine runtime state, not passive sensor posture, SIEM manager inventory, software component identity, raw config, or alert telemetry | `Node.runtime.network_detection_engines` when observed; engine and child refs may be targeted through qualified runtime refs; see ADR-044 |
| Application HTTP route/API/UI surface (routes, methods, request inputs, responses, route-specific weakness placement) | Participant-observable application state, not transport-service or vulnerability authoring | `Node.runtime.applications` when observed; see ADR-026 |
| Mail service logical state (SMTP/submission/IMAP listeners, capabilities, mailboxes, aliases, routing, queues, settings) | Participant-observable mail-service state, not HTTP routes, filesystem evidence, or generic account authoring | `Node.runtime.mail_services` when observed; same-node transport refs remain in `Node.services`; see ADR-038 |
| DNS authoritative/recursive service logical state (zones, RRsets, resolver policy, DNSSEC posture, dynamic-update posture, settings, evidence refs) | Protocol runtime inventory, not transport bindings, container resolver options, raw zone files, or HTTP application state | `Node.runtime.dns_services` when observed; service/zone/RRset refs may be targeted through qualified runtime refs; see ADR-039 |
| SIEM/security-monitoring manager runtime inventory (manager modules, listeners, enrolled agents/groups, detection content sets, parsed detection definitions, bounded settings, API/control-plane posture) | Log-management/security-monitoring runtime inventory and loaded-definition manifests, not transport bindings, process/unit state, raw config, raw events, alert telemetry, or rule-engine execution | `Node.runtime.security_monitoring_managers` when observed; manager, content-set, and detection-definition refs may be targeted through qualified runtime refs; see ADR-040 and ADR-045 |
| Application-internal RBAC store (principals, roles, resource-scoped permission grants, role mappings, tenants) | Application-internal authorization runtime state, not a wire-protocol directory or database engine GRANT surface | `Node.runtime.app_authorizations` when observed; the resource-scoped `permission_grant` is the defining addition; raw credentials are never stored; see ADR-046 |
| Recurring scheduled-job cadence and run-state | Product-neutral cadence runtime state, not systemd unit lifecycle or forwarder input/output authoring | `Node.runtime.scheduled_jobs` when observed; cadence + run-state only; systemd lifecycle remains `runtime.service_manager_units`; see ADR-047 |
| Non-relational datastore logical state (search clusters, structured index mapping/template manifests, wide-column stores, key-value stores, partitions, replication geometry, persistence posture, transport security, settings) plus per-node engine provenance (version/build hash/build type), JVM/process memory posture (heap byte bounds, mlockall), a typed per-node engine-plugin inventory with per-plugin version, and a product-neutral client/peer node-endpoint inventory | Participant-observable non-relational datastore runtime state, not the relational engine/GRANT surface, transport bindings, raw backend mapping/template bodies, or software component identity; node endpoints are engine-published topology, not OS-bind or host-publication proof | `Node.runtime.datastore_services` when observed; the open `data_model` discriminator drives a required-profile guard; mappings/templates are bounded manifests with refs, counts, summaries, digests, and evidence refs; service and child refs (including nested node plugins/endpoints) may be targeted through qualified runtime refs; node plugin/endpoint ids join the service-wide stable-id namespace; internal RBAC is delegated via `authorization_ref`; explicit redaction classifications omit raw setting values; see ADR-048 (amended by ADR-058) and ADR-057 |
| Platform-application runtime inventory with composable functional capabilities | Declared application identity and provider-neutral roles, not a product taxonomy, configuration-completeness claim, HTTP route surface, raw content body, distribution policy, or playbook execution semantics | `Node.runtime.platform_applications`; one application may declare several stable, targetable capabilities. TOSCA/CAMP separation of capability, requirement, artifact, and configuration and ADR-032's provider-neutral identity design are precedents only. `platform_kind` and `content_objects` remain deprecated compatible input; initial content remains under top-level `content`/service materialization; internal RBAC remains delegated via `authorization_ref`; see ADR-049 and ADR-088 |
| Forwarding / intel-sync agent runtime inventory (sources, transforms, ship targets, buffer policy, reload channels, settings for log forwarders and intel-sync co-processes) | Participant-observable agent-side shipping state, not SIEM manager inventory, detection-engine consumer state, scheduled-job cadence, systemd lifecycle, or a fake scenario node for an infrastructure-only sidecar | `Node.runtime.forwarding_agents` when the agent is node-hosted; top-level `forwarding_agents` when the forwarder is off-node infrastructure realization; the open `agent_kind` discriminator drives a required-profile guard; ship-target node/service refs resolve at scenario scope; enrollment identities use a closed classification lattice and settings use explicit redaction classifications; the inter-node trust edge is a relationship forwarding edge; see ADR-050 and ADR-057 |
| Container-spawn orchestration-authority runtime inventory (engine, scope, spawn templates, lifecycle policy, realized children, privilege class referencing a control-interface shell) | Participant-observable container-spawn authority state, not the control-interface shell itself, software component identity, or workflow execution semantics | `Node.runtime.orchestration_authorities` when observed; the open `privilege_class` discriminator drives a required-profile guard; `control_interface_ref` resolves to a same-node `RuntimeControlInterface` (host-root-equivalent requires a read-write docker socket); the control-interface shell is referenced, never duplicated; see ADR-051 |
| Vendor-specific AD DS/LDAP/SCIM/IAM/SAML/OIDC schema clone | Provider coupling and false portability | Neutral `Node.runtime.identity_authorities` inventory when observed; provider identifiers remain data; see ADR-032 |
| Service-manager unit state (systemd unit load/enable/active/sub/result) | Realized lifecycle state, distinct from installed software, transport services, live processes, container init, restart policy, and authored conditions | `Node.runtime.service_manager_units` when observed; raw `systemctl`/`journalctl`/unit-file output remains evidence rather than schema; see ADR-035 |
| Framework-specific participant APIs | Framework coupling | Integration adapters outside the core SDL/runtime |
| Terraform module composition            | Import, version, namespace, parameter, locking, and packaging patterns | Implemented as deterministic SDL module/import expansion with OCI packaging, lockfiles, and trust policy |
| Full CACAO workflow surface             | Current SDL covers decisions, switch/case routing, reusable workflow calls, retries, explicit joins, cancel/timeout lifecycle contracts, and explicit compensation targets/order | Not implemented: richer exception control and compensation-of-compensation semantics |
| Full Step Functions / SCXML execution model | Current SDL adopts only the parts needed for objective-centric branching, retry, and explicit joins | Not implemented: richer workflow/event semantics beyond the current SDL scope |
| VSDL SMT verification                   | Too heavyweight for broad default use today | Outside the current default verification scope |
