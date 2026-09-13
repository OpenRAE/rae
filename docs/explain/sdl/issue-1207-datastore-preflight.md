# Issue 1207: Datastore Description and Admission Boundaries

Architecture preflight for DSL-132 at `d36608e8` on
`1207-partial-profile-descriptions`. Guidance only: no implementation, plan or
claim that validation has changed. The supplied corrective issue governs the
upcoming change; its intent corrects the historical unconditional
required-profile wording in DSL-132 and ADR-048.

## Decision

The typed node-scoped datastore surface already exists. Reuse
`RuntimeDatastoreService` and its children; preserve the boundaries established
by [ADR-048](../../decisions/adrs/adr-048-datastore-service-runtime-inventory.md) and
[ADR-058](../../decisions/adrs/adr-058-datastore-node-engine-provenance-and-endpoints.md).
Datastore topology and logical partitions do not belong in relational database
objects, transport listeners, software identity, filesystem evidence or prose
relationships. Application RBAC remains a referenced `app_authorizations`
inventory. Node-local typed plugins/endpoints remain authoritative; do not
resurrect the removed service-level plugin list or ambiguous node address.

Base validity checks supplied facts. Required completeness belongs to an
actually selected execution/verification contract, with prerequisites justified
by that operation. A data-model or engine identity does not select an
installation recipe, authorize execution or request evidence. Removing base
guards without preserving admission of selected operations is insufficient.

Reuse [ADR-105](../../decisions/adrs/adr-105-recursive-partial-description-semantics.md): inherited
openness delegates unspecified descendants while exact children remain binding.
A backend-resolvable prerequisite within that authority need not be authored.
A complete abstract model and an incomplete observation are distinct valid
cases. Omitted, unknown, withheld, explicitly empty, zero and false must survive
parsing, composition, compilation and readback distinctly. Defaults are not
observations; `unknown`/`other` are not permission to select a replacement.

## Findings and adjacent-family disposition

Package paths below are relative to `implementations/python/packages/`.

| Current owner / finding | Guardrail for the correction |
| --- | --- |
| `raes/runtime_datastore.py::require_profile_for_data_model` requires search partitions, shard/replica counts and mappings; wide-column keyspaces and replication; key-value persistence. | Admit partial descriptions and legitimate empty configured collections. Preserve value types/bounds, duplicates and supplied local manifest refs. A selected profile must justify geometry per relevant partition, including per-DC replication rather than universally copying a scalar-factor recipe. |
| The same datastore guard rejects key-value keyspace/column-family partitions. | Separate explicit data-model incompatibility from missing detail. Retain the typed-family boundary; deleting the whole validator must not admit contradictory supplied state. |
| `RuntimeDatastorePersistence` admits `aof: false` with explicit `rdb_save_points: []`; omission of the object fails. | A nonpersistent posture differs from unknown persistence. Do not manufacture an empty posture to pass parsing. These Redis-style fields also do not prove all possible engine persistence mechanisms disabled. |
| `runtime_forwarding_agent.py` requires buffer/ingestion for log forwarding and API-pull/IOC conversion/reload for content sync; it also forbids combinations by category. | Review positive and negative recipe restrictions. Preserve valid composed pipelines, endpoint shapes, ownership, references and enrollment classification. The shared class serves scenario-level and node-local forwarders; both ingress paths matter. |
| `runtime_orchestration.py` requires an interface; `validator/_runtime_orchestration.py` also requires a read-write Unix socket ending in `docker.sock`. | Relaxing only the model misses a second gate. Keep supplied same-node reference resolution. Incomplete interface knowledge is not permission. Docker-specific prerequisites belong to a selected Docker operation; filenames do not prove authority and other privileged engines must remain representable. |
| `runtime_app_authorization.py::_require_grants_for_resource_vocabulary` rejects a known vocabulary with no matching grant. | Include this adjacent completeness guard: empty configured grants and unobserved grants require no fabricated grant. Preserve explicit effects, role/principal/mapping refs and credential posture. Inventory does not grant runtime authority. |
| `runtime_platform_application*.py` | Preserve #956's capability/configuration/content separation and compatibility. Do not reopen the MISP sharing-group guard. |

Read-only constructor probes confirmed rejection of partial search/wide-column,
key-value without persistence, partial content sync, host-root without interface,
and `index_pattern` authorization with empty grants. Explicit disabled key-value
persistence was accepted. These establish baseline behavior, not future
execution conformance or independent SCN-010 capture evidence.

Use the [existing #959 audit inventory](../../research/language-extensibility/scope-inventory.md):
separate identity, capability, configuration, content, binding, policy and evidence
before classifying a guard. Relational database, directory identity, mail,
monitoring/detection, scheduled jobs and control interfaces retain their existing
owners and typed integrity checks. `runtime_dns_records.py` illustrates why
blanket relaxation is wrong: supplied RR payload/type-code consistency and an
asserted RRset's nonempty-member contract do not imply every service needs
configured records. Further family changes need an owner-specific legitimate
counterexample; this preflight does not close the repository's broader #959 audit.

## Cross-cutting layers to reuse

Package paths below are relative to `implementations/python/packages/`.

| Layer and canonical incumbent | Required treatment |
| --- | --- |
| Parser/model: `raes/parser.py`, `_yaml_loader.py`, `_source_profile.py`, `_base.py::SDLModel`, `runtime_values.py`, `runtime_vocabulary.py`, `_runtime_datastore_support.py`, `runtime_datastore_nodes.py`; contract `ContractModel` | Keep safe bounded ingress, closed keys, stable IDs, enum/variable parsing, numeric/port bounds, heap ordering, duplicates and redaction. Reuse helpers. No partial DTO mirror, arbitrary dictionaries, `model_construct` escape or global validation-disable switch. Mapping/template manifests stay bounded rather than embedding raw engine responses. |
| Reference graph: `raes/validator/_runtime_platform.py`, `_runtime_orchestration.py`, `_runtime_service_family_registry.py`, generic relationships and module imports | Preserve same-node service/authorization/interface refs, datastore manifest links, service-wide nested IDs and namespacing. Keep forwarder global identity and scenario-level qualified targets. Missing knowledge does not legalize supplied dangling refs. No second family registry. |
| Authorization: `runtime_app_authorization.py`, `RelationshipForwardingEdge`, runtime API `_auth.py`, `control_plane_plan_authorization.py`, `manager_plan_admission.py` | Keep observed application RBAC, forwarding trust, experiment ownership and operator/planner authority separate. Partial records cannot authorize apply, host privilege, traffic or port publication. Required execution authority must be admitted before mutation, including direct submission and prepared nodes. |
| Secrets/environment/config: `runtime_values.py::enforce_observed_value_redaction`, `runtime_environment.py`, `runtime_generated_value.py`, `raes_contracts/secret_references.py`, `participant_configuration.py`, `contracts/experiment_bindings.py::BindingValue` | Preserve explicit redaction, literal/secret-reference discrimination, environment-name uniqueness, literal/`value_from` exclusivity, generated-output entitlement and producer-private exclusion. Generated secrets are not operator secrets. Owner normalization preserves targets, types, provenance and reference identity. Profile payloads cannot bypass these shapes; parsing never resolves secrets. Name heuristics remain advisory under ADR-056/057. |
| Compilation/comparison: processor `semantics/realization_runtime_concern_profiles.py`, `realization_typed_runtime_projection.py`, `realization_concern_observations.py`, recursive realization structure | Consumers revalidate through the same SDL types; parser-only acceptance is insufficient. Preserve source presence/origin, keyed identities, exact siblings and value commitments. Excluded datastore counts/status and orchestration realized children must not become configuration obligations. Default-filled readback does not prove observation. |
| Selected profile/preparation: `raes_contracts/domain_profiles.py`, `realization_profiles.py`, processor `planner/realization_profiles.py`, `realization_preparation.py`, `prepared_node_admission.py`, manifest/runtime admission | Reuse pinned definitions, bounded no-retrieval schema admission, owner/context binding, exact supported operations and authenticated host policy. Admit a supported completion under negotiated preparation, then verify delivery. Opaque exchange/shape validity is not execution support. Preserve legacy universal-envelope behavior where preparation is not negotiated. Generic profile machinery alone does not implement datastore execution checks. |
| Reports/evidence: `raes_contracts/contracts/realization_descriptions.py`, description projection/reporting, processor `capture_admission.py`, runtime observation admission | Reuse #1209 fact states, coverage, basis and provenance. Backend-selected detail is not independently observed evidence. Keep #1112 required-capture capability and emitted-byte checks and #1212 independent collection/retention/export policy. Neither inventory detail nor a digest automatically requires or supplies experimental evidence. |
| Host/process boundary: backend execution, `Node.services`, `runtime.service_listeners`, `runtime.network`, local control interfaces | Inventory endpoints are not OS listeners, published ports or ACLs. Parsing/admission introduces no socket probe, datastore CLI, remote schema fetch or host service. If an admitted operation needs credentials, use its existing delivery channel; never put tokens in process argv, shell text, URLs or captured native output. |
| Errors/observability: `raes/_errors.py`, `_model_diagnostics.py`, `raes_contracts/diagnostics.py`, `OperationReceipt`/`OperationStatus`, API request guards, libvirt `_observability.py::record_suppressed_failure` | Reuse structured bounded diagnostics and redacted API envelopes. Distinguish invalid description, unsupported profile and execution refusal. No new exception hierarchy/logger. Message bounding does not redact interpolated values: new validator messages must be value-free. Never serialize Pydantic inputs, raw exceptions or tracebacks. Operational audit is not experimental capture. |
| Persistence: `raes_runtime/control_plane_store_*`, snapshot codecs and observation lifecycle | Datastore persistence posture describes the modeled service, not the control-plane database. Reuse transactions, revisions, safe store paths and retention/protection. No new inventory repository/cache or raw-response retention. Recovered/profile-bound state still passes current ownership/admission; defaults must not rewrite historical observations. |
| Contracts/workflow: `contracts/schemas/`, publication manifest/entries, `.ground-control.yaml`, `.gc/plan-rules.md`, canonical policy/schema tools | Published schemas are normative under ADR-009; retain generated-bundle equality and ledger actual schema changes. Python after-validator acceptance can change without a schema diff: verify both and do not create cosmetic schema churn. Preserve traceability, file-size governance and existing workflow commands. |

## Extensibility, acceptance and non-goals

Use the existing versioned, owner-bound profile and **required operation** seam
in `plan-realization-profiles-v1`, negotiated with preparation and exact backend
support. Parameterize genuinely necessary capabilities/constraints there so a
nonpersistent cache, non-IOC synchronizer or non-Docker authority needs no new
core product recipe. The current carrier is programmatic: do not silently add
per-service SDL profile syntax. Definitions cannot self-assert operator authority
or installed semantic support. Validation-strength catalogs, runtime comparison
projections and executable domain profiles are different concepts despite the
shared word “profile.”

Future acceptance must join `test_runtime_datastore.py` and adjacent family
suites with semantic/reference, import, parser/schema and lifecycle tests.
Preserve complete fixtures and security-negative cases while correcting obsolete
universal rejection expectations. Reuse #1201/#1204/#1209 tests for omitted versus
empty/false/zero, unknown versus delegation, open versus closed descendants,
unsupported/untrusted profiles, pre-mutation refusal and delivered constraints.
Include a supported backend-selected prerequisite inside open scope and refusal
of the same selection when it conflicts with an exact child. Keep #1043 forwarding
ownership/corroboration and #1112 required-capture regressions. Schema-only success
or deleting rejection tests is insufficient.

Implementation must reconcile ADR-048/050/051, adjacent ADR-046, runtime-index
§3.4, docstrings and tests with the corrective semantics. Follow
[ADR-059](../../decisions/adrs/adr-059-adr-amendment-policy-and-pin-gate.md) for accepted-ADR
amendments and pins; this preflight leaves accepted content intact. ADR-048's
historical schema-generation wording cannot override ADR-009 and publication
governance. The [existing follow-ups](../../research/language-extensibility/adr-follow-ups.md)
already distinguish target semantics from shipped guards.

Non-goals: new runtime families, merging relational/RBAC/transport schemas,
provisioning engines or migrations, core product catalogs, raw config payloads,
new policy languages, automatic evidence, wider privileges, or reimplementing
#956/#1201/#1204/#1209/#1212. This local preflight does not establish remote native
blocker status or authorize implementation, merge, deployment or capture.
