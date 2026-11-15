# Shared connections architecture preflight

## Recommendation and scope

Issue [#2060](https://github.com/OpenRAE/rae/issues/2060) calls for a design PR, with no formal requirement attached.
Reuse native relationships, reference policy and recursive profiles first.
Keep application links, network attachment and electrical topology separate.
Deployment order and causal claims have their own rules.
The shared concept does not need to become a shared executable graph.

This preflight sets bounds for that work. It does not select syntax or change language authority.
No new ADR is needed: ADR-052, ADR-105 and ADR-121 already govern these boundaries.
The [#2059 design](issue-2059-domain-description-design.md) supplies the domain-description context.
Its proposed profile host is not an implemented SDL field.

Inspection revision: `3eb5790183b3f757a7fcdada9167c488fa5c9f5e`.
The issue pins `33c09e9dfe9e26699489745809699a43e42d7630`.
Both have the same `references.md` and `recursive-realization-constraints.md` contents.
Module names below are relative to `implementations/python/packages/`.
Private modules identify current owners. Later code must use the owning package's public interface.

## Existing owners and important limits

| Concern | Canonical owner | Boundary the design must preserve |
| --- | --- | --- |
| Declared connection | `raes.relationships.Relationship`, `RelationshipType.CONNECTS_TO` | A named, directed pair of eligible declarations. String properties add no domain checks. |
| Application detail | `RelationshipServiceIntegration`, database/mail access, forwarding edges and `RelationshipProxyUpstream` | Reuse the relevant typed detail and scenario checks. These records do not execute a connection. |
| Network attachment | `raes.infrastructure.InfraNode.links`, `raes.validator._nodes_infra_network` | Targets must be switch-backed infrastructure entries. They cannot stand for arbitrary equipment wiring. |
| Network detail | `RuntimeNetworkEndpoint`, `RuntimePublishedPort`, `ServicePort` | Attachment, host publication and node-local transport identity have distinct contracts. A service grants no traffic access. |
| Public references | `DeclarationIndex`, `build_declaration_index()`, `raes._reference_targetability`, `_relationship_endpoint_policy` | Keep exact identity and purpose-specific eligibility. Reject ambiguous names. Each new kind or detail needs an explicit policy decision. |
| Partial descriptions | `raes_contracts.realization_structure` and [recursive constraints](../../specs/sdl/recursive-realization-constraints.md) | Reuse presence, knowledge and keyed identity. Keep local closure, conjunction, refinement and bounded outcomes. |
| Domain meaning | `raes_contracts.domain_profiles`, [typed profiles](../explain/reference/domain-profiles.md) | Exact definitions and installed semantics own domain rules. The generic profile contract adds no public SDL host. |
| Deployment graph | `raes_processor.compiler.provisioning`, planner and prepared-node admission | Infrastructure links create provisioning dependencies. Physical topology must not enter that path by analogy. |
| Claims and evidence | ADR-079/081 and ADR-064/066 | A connection proves no causality or reachability. Nor does it prove delivery, live state or observed evidence. |

The compiler's `_metadata_specs()` preserves relationships as metadata.
`_compile_node_runtimes()` includes both infrastructure dependencies and links in resource dependency addresses.
`planner/prepared_node_admission.py` also checks those required addresses.
A model or compiler change alone cannot safely change this meaning.

`RuntimeNetworkRealization` permits only one endpoint record per network.
It supplies no general interface identity.
Do not claim it already covers several distinct OPC UA connection points on the same network.
Likewise, service-integration lookup uses local application IDs. It is not a general cross-domain address contract.

The core graph-reference evaluator checks the scalar against its governed identity domain.
It does not perform whole-graph topology checks.
The owning graph profile checks its cycle prohibition.
Definition references must remain acyclic under every topology policy.
Do not reuse a dependency-cycle check for an electrical loop.

## Comparison boundaries

These cases bound the review. They do not settle the mapping or syntax.

| Comparison case | Existing surfaces to assess | Meaning that must survive |
| --- | --- | --- |
| Consumer application connects to an engine or upstream service | Native relationship with integration, database or proxy detail. Existing application and service references. | Preserve roles, protocol and any constrained authentication. Neither endpoint needs an invented socket. |
| Device interface attaches to a network | Existing infrastructure links and runtime endpoint detail, within their deployment scope. OPC UA connection points as comparison evidence. | Keep interface ownership, network membership and communication-profile compatibility. These differ from a TCP port, cable or application link. |
| Equipment terminals meet at an electrical junction | Profile-owned records, keyed terminal identities and governed graph references. | Preserve equipment ownership, junction identity and electrical constraints. None is a compute node, IP subnet or deployment dependency. |

[OPC UA Devices 1.05.0, section 5.4](https://reference.opcfoundation.org/specs/OPC-10000-100/5.4)
models a device's network interface and protocol-specific connection-point subtypes.
[Section 4.7](https://reference.opcfoundation.org/specs/OPC-10000-100/4.7) makes connection-point declarations optional in the device structure.
An OPC UA connection point is not an electrical terminal.
These models do not require each SDL endpoint to declare a connection point.

For public CIM comparison evidence, the
[ENTSO-E CIM14 profile, revised 10 June 2014](https://eepublicdownloads.entsoe.eu/clean-documents/CIM_documents/Grid_Model_CIM/140610_ENTSO-E_CIM_Profile_v1_UpdateIOP2013.pdf),
section 6.3.33, distinguishes equipment terminals and connectivity nodes.
This source uses CIM14. It does not describe the IEC 61970-301:2020 model discussed in #2059.
Do not combine their cardinalities or claim current IEC conformance.

The #2059 RCP 2.3.1 PDF could not be retrieved here.
Its detailed clauses were not reverified.

The minimum common candidate is a typed connection between identified subjects.
Endpoint roles or refinements apply where their domain needs them.
This shared concept alone does not justify a new base class, schema or ontology.
The investigation must separate gaps in terms, public attachment, addressability and semantic support.

Native application and deployment-network fields already cover part of the problem.
Physical equipment lacks a general public declaration host. A dotted string cannot supply one.

## Invariants for any candidate design

- An endpoint can name a whole declared subject. Ports, interfaces and terminals remain optional refinements unless explicitly constrained.
  Existing `ServicePort` requires a port; do not fabricate a port to use it as a universal endpoint.
- If an endpoint names a child, its owner and kind must agree with the connection domain.
  Build its allowed identity universe from admitted subjects, not an unverified list of authored strings.
- Keep containment separate from connectivity. A terminal belongs to equipment and may connect at a junction.
  Several terminals can share that junction. Keep its identity rather than all possible pairwise edges.
- Keep stored edge order, application flow direction and electrical flow convention distinct.
  A directed `source`/`target` pair does not establish power-flow direction or causal influence.
- Preserve parallel connection identities where different links join the same subjects.
  Do not deduplicate solely by endpoint pair. An indirect path is not a direct connection.
  Self-connections and permitted cycles need domain-specific rules, not a global assumption.
- Keep omitted detail, optional presence and forbidden presence distinct.
  Unknown knowledge, empty collections and explicit null also have separate meanings.
  `RelationshipServiceIntegration.direction` defaults to bidirectional. Omission there cannot silently become unconstrained in a projection.
- Local closure binds the named collection or record only. An open parent cannot replace an exact child.
  Adding or reordering permitted keyed members must preserve identity and authored constraints.
- A connection type and every supplied typed detail must agree about endpoint eligibility.
  Reuse ADR-052's cross-scope agreement approach when the same fact appears on a route, endpoint or relationship.
- A shared label or number does not prove protocol or electrical compatibility.
  Domain rules must preserve units and the selected model edition. Do not add a global implicit conversion rule.
- Keep native addresses and JSON Pointers distinct.
  Profile-local identities, external standard identifiers and compiled resource addresses also have separate roles.
  Reference visibility grants no deployment, action, observation or access authority.
- Composition must keep owners distinct across repeated imports. Reject collisions and resolve variables again after instantiation.
  `_rewrite_relationship_sections()` handles selected governed fields. It does not traverse all profile values or nested runtime identifiers.
  In particular, do not assume `service_integration` local references already receive namespace rewriting.

The extension seam uses immutable `DomainProfileResolutionContextModel` and an exact semantic-contract coordinate.
The host context must be explicit too.
Domain definitions own roles, member identity, compatibility, units, multiplicity and topology policy.
Required operations remain explicit through `DomainProfileAdmissionPolicyModel`.
A further domain should supply a definition and installed semantics through these seams.
It should need no new core resolver or equipment enum.

## Cross-cutting boundaries

The design PR changes no executing layer.
Any later executable change must keep these owners and controls.
The [#2059 preflight](issue-2059-domain-description-preflight.md#cross-cutting-layers-and-canonical-owners)
gives the broader domain boundary inventory; the connection-specific obligations follow.

| Layer and canonical incumbents | Required treatment |
| --- | --- |
| SDL ingress: `raes._yaml_loader`, `_source_validation`, `_mapping_key_analyzer`, `SDLModel`; portable ingress: `raes_contracts.json_ingress` | Keep safe YAML and reject duplicate keys. Keep closed fields and bounds on bytes, depth and work. Direct construction and artifact admission need shape checks too. |
| Profile/schema admission: `domain_profiles`, `_domain_profile_schema_registry`, shared `ContractModel` | Keep exact coordinates, namespace trust and schema sealing. Use the safe Draft 2020-12 subset. Reject remote retrieval and unsupported keywords. Bound graph and diagnostic work. Reuse the shared validator. |
| Semantic and config admission: `admit_domain_profile_bindings()`, `realization_profiles`, runtime `backend_profiles`, `control_plane_configuration`, `manager_plan_admission` | Check complete constraints before mutation. Require explicit host and operation support. Support rows and schema validity alone cannot implement semantics. Direct runtime submissions need the same checks. |
| Identity and composition: `identifiers`, declaration index, reference-purpose policy, `raes.composition`, language service | Reuse canonical parsing, collision checks and purpose rules. Completion, navigation and validation must agree. Keep profile-local subjects local unless they need a reviewed public address. |
| Auth: `control_plane_security`, API `_auth`, `control_plane_plan_authorization` | Keep principal, target, route and authenticated-plan checks. Profile trust does not grant caller authority. Topology grants no device access or network permission. This work needs no new route. |
| Secrets/environment: `raes.runtime_environment`, `raes_contracts.secret_references`, `runtime_values`, generated-artifact contracts | Keep classification and redaction. Keep literal values and value sources mutually exclusive. Add no environment map or credential resolver to endpoints. Keep operator credentials outside public connection data. |
| URI and host/OS: `raes_contracts.uri_safety`, profile identity checks, existing artifact/module admission | Keep locators inert and credential-free. Parsing must not access networks, discover devices or files, or load handlers. Never put payloads, tokens or connection strings in shell commands or process argv. |
| Errors and logs: `raes._errors`, `raes_contracts.errors`, `diagnostics`, `operational_logging`, API `_responses` | Use `Diagnostic` for expected findings. Reuse error categories and fixed HTTP refusal envelopes. Value-object checks raise `ValueError`. The owning boundary translates failures once. Log bounded safe metadata once. Exclude payloads and connection strings. |
| Persistence and results: existing `ControlPlaneStore`, `control_plane_store_snapshots`, `realization_snapshot_sanitization`, backend result admission | Keep safe codecs, exact owners, revision checks and atomic state transitions. Check delivered refinements before publication. Add no connection database, sidecar, cache or second lifecycle. |
| Observation and evidence: observation demand, participant information-flow controls, ADR-064/066 | Keep author intent, backend choices and observations distinct. A connection proves no live reachability or energized circuit. Collection, retention, export and participant disclosure need their existing authority. |
| Publication and package policy: `specs/`, `contracts/schemas/`, `contracts/schema-publication/`, `raes_schemas.schema_bundle()`, ADR-117/121 | A later language change needs governed schema authority. It also needs generator parity and conformance cases. Keep contracts below SDL, processor and runtime. Add no reverse imports or compatibility wrappers. |
| Workflow: `.ground-control.yaml`, `.gc/plan-rules.md`, `CONTRIBUTING.md`, `noxfile.py`, `tools/nox_support/`, `.pre-commit-config.yaml` | Use the requirement-free route and targeted local checks. Keep full CI gates, release-please ownership and ADR pins. Formal evidence captures use the existing content-addressed workflow. |

The trust path remains author data → bounded parsing → typed references and offline admission → admitted description.
Execution needs a separate request and installed support.
It then requires an authenticated plan and ordinary backend admission.
Endpoint locators never select code or grant execution authority along that path.

## Review evidence and non-goals

The eventual design needs positive and rejected examples.
Cover both sparse and refined connections.
Include an omitted port and a dangling or wrong-kind endpoint.
Also include incompatible domain refinements and conflicting duplicate facts.

Include a shared junction, an allowed electrical loop and parallel links.
Keep a separate example of a deployment dependency cycle.
Cover repeated imports, keyed reordering and additions to a closed collection.
Include an exact child under an open parent too.

Unsupported domain semantics must remain unsupported. Opaque carriage cannot establish conformance.
Label examples as supported SDL, programmatic contracts or proposals. Use their actual entry point to choose the label.

Reuse the existing endpoint/candidate-parity, runtime integration, recursive-normal-form and profile admission tests.
Focused inspection probes passed 15 cases across these owners:
`test_issue_1339_relationship_candidate_parity.py`, `test_runtime_platform_application.py` and `test_issue_1203_recursive_normal_form.py`.
They check existing behavior only.
They do not prove the proposed model or standards conformance.
This prose-only preflight needs no new behavior or mutation tests.

Non-goals include a universal ontology or required terminal inventory.
Do not add dependency semantics or replace the realization algebra.
Public syntax and schema changes are outside this preflight.
So are protocol clients, network publication, equipment actuation, simulators, Parts and new persistence.

Do not hide enforced meaning in `Relationship.properties`, descriptions, labels or arbitrary backend payloads.
Do not remodel a CIM connectivity node as a compute node or network switch.
Do not infer connectivity from dependency, causality from connectivity, or safe operation from a valid description.
Do not add a second schema, validator, exception family or workflow for connections.
The later design PR must complete the comparison and choose the smallest compatible extension, if any.
