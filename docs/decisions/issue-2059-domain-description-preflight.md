# Issue 2059: Domain description architecture preflight

Date: 2026-11-15. Inspected revision: `1f4d05ed50d2bcca151bbf8318fd0e01b4de7ba7`.
Contract: the supplied title, intent and acceptance criteria for issue #2059.
This note guides the later design review. It is not the issue's design deliverable or an implementation plan.
It changes no SDL syntax, schema, runtime behavior or accepted decision.

The existing recursive contract covers records, collections and graph references.
The open question is where authors can attach domain data and name its subjects.
Do not infer a missing realization semantic from missing equipment vocabulary.
A shared profile DTO does not add an SDL field. Nor does it make equipment a named SDL subject.

## Existing boundaries

- [ADR-105](adrs/adr-105-recursive-partial-description-semantics.md) and SEM-218 keep author-selected detail and permitted backend choices.
  Open parents retain exact children. Local closure names its universe and revision.
  Omission, explicit null, unknown, redacted, optional presence and delegation remain distinct.
- [Recursive constraints](../../specs/sdl/recursive-realization-constraints.md) already own conjunction, stable collection identity, bounded outcomes and graph references.
  Graph edges are governed identities, not recursive schema expansion or automatic SDL references.
  Physical links can form a valid cycle. Schema definitions cannot form cycles.
- [Domain profiles](../explain/reference/domain-profiles.md) already separate definition, binding, trust provenance, local resolution context and operation support.
  Standard and private profiles use the same contracts.
- [Plan profiles](../../specs/sdl/plan-realization-profiles.md) attach to existing, authenticated, non-delete provisioning operations.
  They cannot create resource membership, dependencies or participant affordances.
  The `portable-resource-labels` handler supports labels. It does not run domain models.
- [Typed selections](../../specs/sdl/profile-selections.md) have specific hosts.
  [ADR-120](adrs/adr-120-owned-and-admitted-typed-descriptor-profiles.md) covers five identity/access descriptor fields, not equipment generally.
  A later host needs the same checks: owner, compiled form and target admission.
- `NodeType` has `compute` and `switch`; these are structural resource kinds.
  `Entity` means an organization, team or person.
  `Feature` means software, config or an artifact deployed on a compute node.
  None is a general physical-equipment declaration.

Parts remain backend implementations of how requirements are realized.
An OPC UA component or CIM equipment class does not thereby become a Part.
The same holds for a SOSA system or navigation function.
Authors need not list internal backend choices.

## Standards comparison guardrails

These bounds guide the later design. They are not final mappings or claims of standards conformance.

| Small case | Existing SDL facts to examine first | Distinction the design must demonstrate |
| --- | --- | --- |
| Controller with one sensor and one actuator | `nodes.<id>.type: compute` for a compute endpoint. Named `services`. Software/firmware in `runtime.software_components`. Native relationships and propositions where their contracts apply. | OPC UA device structure differs from SOSA roles. A sensor's identity, measured property, unit and result are not a software row. |
| Navigation computer using position data | A compute node. Selected software, named service endpoints and content. Native dependency edges. | A navigation task is a function. It does not impose a computer or sensor inventory. Keep the function, its deployment and its performance claim separate. |
| Power equipment with connection points | A compute node for its digital controller, separate from the controlled equipment. Shared profiles and recursive graph constraints for candidate domain data. | CIM equipment is not an SDL compute node. Its electrical links are not network links. Establish a valid host and subject address before claiming support. |

The public sources have different scopes:

- [OPC UA Devices, device model](https://reference.opcfoundation.org/specs/OPC-10000-100/4), viewed as version 1.05.0, describes device structure and identification.
  [TopologyElementType](https://reference.opcfoundation.org/specs/OPC-10000-100/4.3) organizes parameters, methods and functional groups.
  Its model grants no right to call methods. It does not impose a full nameplate on every SDL author.
- [W3C SSN/SOSA](https://www.w3.org/TR/vocab-ssn/) distinguishes sensors, actuators, observations, results, procedures and features of interest.
  Here SOSA means Sensor, Observation, Sample, and Actuator, not another architecture with the same acronym.
  A domain observation is not by itself RAES evidence. Nor does it permit collection.
- [IMO's resolution index](https://www.imo.org/en/knowledgecentre/indexofimoresolutions/pages/msc-2007-09.aspx) identifies MSC.252(83) as the integrated-navigation performance standard.
  [MSC.1/Circ.1575](https://wwwcdn.imo.org/localresources/en/OurWork/Safety/Documents/IMO%20Documents%20related%20to/MSC.1-Circ.1575.pdf), Appendix A, names navigation tasks and references MSC.252(83).
  It also separates PNT functions from their hardware/software deployment.
  The MSC.252(83) PDF could not be fetched. Detailed clause alignment remains for the design review.
- [IEC 61970-301:2020's public abstract](https://webstore.iec.ch/en/publication/62698) describes CIM as utility objects, attributes and relationships.
  The linked edition names model `IEC61970CIM17v38`. Do not mix editions. A distribution profile need not have the same scope.
  The full standard was not inspected. Detailed class, cardinality and unit mappings need authorized primary evidence.

Use exact editions, namespaces and source coordinates in the later comparison.
Name each gap: vocabulary, attachment, addressability, semantic support or backend integration.
Mark any unverified mapping. Do not replace a concept with an approximate native term and call it equivalent.
Do not vendor standards, install packages or acquire licensed material merely to complete a table.

## Attachment and addressability decision boundary

External classifications already use `external-concept-bindings/v1` and `admit_external_concept_bindings()`.
Use `raes.external_concept_subjects.external_concept_subjects()` for exact subjects. Bind their digests at the correct lifecycle phase.

The external scheme remains an authored assertion, not an executable constraint or proof of capability.
Without local scheme context, an assertion stays inactive. This does not permit a URL fetch.

Typed domain values instead use `DomainProfileBindingModel` and `admit_domain_profile_bindings()`.
A binding needs a real host and allowed context. It also needs an owner, phase, use, provenance and required operations.

A plan resource may host a binding through the existing API. The plan contract's limits still apply.
This does not prove that SDL can host equipment data. Nor does it let authors name each child as a core subject.

Native references use `DeclarationIndex`, `build_declaration_index()` and the reference-purpose policy.
The index does not list arbitrary JSON profile leaves.
Native declaration addresses differ from JSON Pointers and compiled resource addresses.
Profile-local identities and external concept identifiers differ too.

Do not construct one by concatenating strings from another.
Core composition rewrites governed owners and references. It does not rewrite arbitrary strings in private profile values.

Any proposed host must handle repeated imports and name qualification.
It must also handle collisions, stable child identity and dangling references.

Reference eligibility never grants targetability, participation, visibility or execution authority.
If equipment needs its own address, record that narrow gap. Do not silently create another resource lifecycle.

The seam for future domains is `DomainProfileResolutionContextModel`. It is immutable. Pass the host context and required semantic operations too.
Definitions pin authority, namespace, revision, digest, schema and semantic contract.
The admitted definition owns domain identities, units and reference rules. Its installed semantic owner checks their meaning.

The next domain should supply another definition and context. It should not need a new core enum, resolver or validator.
Do not select new host syntax in this preflight.

Keep domain profiles distinct from stack semantic profiles and evidence validation profiles.
Identity-domain selections, artifact-mechanism profiles and structural reference models also retain their own roles.

## Cross-cutting layers and canonical owners

Package paths below are relative to `implementations/python/packages/`.
The design-only delivery changes none of these execution layers.
A proposed host must account for each row that applies. Check direct submission paths too.

| Layer and incumbents | Required treatment |
| --- | --- |
| SDL ingress: `raes/_yaml_loader.py`, `_source_validation.py`, `_mapping_key_analyzer.py`, `_source_profile.py`; `raes_contracts.sdl_model.SDLModel` | Keep safe YAML and duplicate-key checks. Retain source limits, variable rules and closed core fields. Direct model construction needs the same checks. |
| Portable ingress and config: `raes_contracts.json_ingress`, `domain_profiles`, contract models; `raes_runtime/backend_profiles.py` | Reuse bounded JSON and exact definition sealing. Check namespace trust and manifest context digests. Bound depth, nodes, bytes, references, work and diagnostics. No ambient environment lookup or global registry. |
| Schema admission: shared domain-profile validation and `_domain_profile_schema_registry.py` | Use the existing safe Draft 2020-12 subset and no-retrieval registry. Local references must resolve. Schema identities and dialects stay at the root. Regex/custom keywords and recursive definitions cannot bypass keyword or work limits. |
| Semantic admission: `admit_domain_profile_bindings()`, `raes_contracts.realization_profiles`, `raes/descriptor_profiles.py` | Schema checks and support rows do not implement semantic checks. Installed semantics must check the whole core/profile conjunction. Refuse unsupported required meaning before mutation. Opaque exchange cannot satisfy a constraint. |
| Identity and composition: `raes_contracts.identifiers`; `raes/_declarations.py`, `_reference_targetability.py`, `composition/`; `external_concept_subjects()` | Reuse canonical parsing and reference-purpose rules. Keep collisions and source-phase digests. Keep exact owners when imports gain qualified names or a canonical form. No second equipment alias index. |
| Compiler and planner: `raes_processor/compiler/`, `planner/realization_profiles.py`; `raes_contracts.realization_structure` | Preserve recursive constraints, author/default origins and native resource ownership. Conjoin core and profile requirements. No new leaf registry or domain solver duplicating the shared relation. |
| Auth: `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_plan_authorization.py` | Check principal, target, route and planner-artifact authority. Profile trust is separate. A digest, equipment address or installed profile grants no access or operation. This review needs no new API route. |
| Runtime config: `control_plane_configuration.py`, `control_plane_submission.py`, `manager_plan_admission.py`, `backend_profiles.py` | Keep constructor shape checks and target-context binding. Planning and direct runtime admission must agree. Profiles cannot bypass preparation or ordinary backend checks. Keep entitlement, dependency and operation-scope checks too. |
| Secrets and environment: `raes/runtime_environment.py`; `raes_contracts.secret_references`, `runtime_values`, generated-artifact contracts | Public profile data must contain no credentials or operator-secret references. Keep literal values and value sources mutually exclusive. Keep redaction rules. Do not add new token, secret or environment-binding shapes inside domain data. |
| URI and host/OS exposure: `raes_contracts.uri_safety`, profile identity checks, existing artifact/module admission | Locators stay inert and credential-free. Parsing cannot fetch data, discover files, load handlers or run processes. Keep domain payloads, schemas, tokens and locators out of shell text and process argv. Any separately authorized fetch uses existing trust and bounded acquisition controls. |
| Errors and observability: `raes/_errors.py`; `raes_contracts.errors`, `diagnostics`, `operational_logging`; API `_responses.py` | Reuse `SDLError` and the shared `RaesError` categories. Bound `Diagnostic` results and use value-free logging. Keep fixed HTTP refusal envelopes. Redact validation and unexpected failures. Never return native exception text. Do not log rejected values, schemas, endpoints or credentials. |
| Results and stores: runtime result admission, `realization_snapshot_sanitization.py`, `control_plane_store_snapshots.py`, existing `ControlPlaneStore` implementations | Check selected and delivered bindings before publication. Keep exact coordinates and safe codecs. Reconcile changes and clean up deleted state. Retain the trusted predecessor on rejected delivery. Reuse atomic terminal commits and revision checks. No equipment database, cache or sidecar. |
| Evidence and disclosure: ADR-064/066, observation demand, participant information-flow and artifact sensitivity owners | Keep author intent and backend selection separate from observed state and experimental evidence. Apply collection prohibitions before observation. A profile, report request or SOSA event grants no capture, retention or export right. Participant disclosure needs its own grant too. |

The current API response helper already hides raw conflict text.
The older #1202 preflight warned about exposed `str(ValueError)` text. That warning does not describe this revision.
ADR-116 now owns shared exceptions and operational logging; ADR-117 owns structural module checks.
The private modules named here are inspection evidence. Use the public package interfaces in code.

## Review evidence and workflow boundaries

The eventual design needs positive and refusal examples, not only diagrams or schema-shaped JSON.
Compare sparse and refined descriptions. Check local closure, reordered keyed members and missing target semantics.
Also examine repeated imports, stale external subjects, dangling domain edges, cyclic topology, unit mismatch and forbidden observation.
Label examples as current syntax, programmatic contracts or proposals; never publish candidate notation as supported SDL.

Existing focused verification owners include `test_issue_1202_domain_profiles.py`, `test_issue_1203_recursive_normal_form.py`, and `test_issue_1204_profile_carrier.py`.
Also reuse `test_issue_1204_profile_offline.py`, `test_issue_298_descriptor_profiles.py`, external-concept and identifier/reference tests when those boundaries change.
Run code examples through the existing parser/conformance path. Do not build a validator for one example.
This note changes no production behavior. It needs no new behavioral tests or mutation tests.

Workflow owners are `.ground-control.yaml`, `.gc/plan-rules.md`, `CONTRIBUTING.md`, `noxfile.py`, `tools/nox_support/`, `Makefile` and `.pre-commit-config.yaml`.
Use the requirement-free route. Do not invent a UID or close #2059 with this preflight.
Run changed-path documentation and file-local policy checks locally. Full policy and test suites remain in CI.

A later public schema change needs its governed authority and generator parity.
It also needs its publication record and conformance fixtures.
Keep release-please ownership, ADR pins, historical evidence and ADR-036/117 package boundaries.
Any later formal research captures follow `docs/develop/research-captures.md`. Do not edit published capture history.

### Checks observed in this preflight

The file-local policy check passed before and after the edit.
The explicit-path `docs-prose` check passed both Vale and shared STE checks.
Four focused cases passed on Python 3.14.7:

- `test_support_rows_without_a_profile_semantic_implementation_are_not_permission`;
- `test_installed_profile_semantics_must_accept_the_complete_selected_plan`; and
- both cases of `test_profile_validator_disables_retrieval_even_if_preflight_misses_a_reference`.

The descriptor test `test_runtime_rechecks_descriptor_admission_after_plan_diagnostics_are_removed` timed out at 120 seconds.
An isolated retry also timed out at 20 seconds.
Its stack stopped in `RuntimeManager` construction, at `LocalExecutionAdapter`'s AnyIO portal call, before profile admission.
The first run needed interruption after the timeout. The isolated run exited with status 1.

The cause remains unresolved. This inspection does not establish that runtime check's result.
No runtime source or test was changed.

## Non-goals and anti-patterns

This preflight does not deliver the comparison/design PR. It does not approve host syntax, amend ADR-105 or implement domain adapters.
It grants no right to actuate equipment or discover devices.
It adds no standards import, protocol client, simulator, Part or backend change.
It adds no compulsory equipment inventory, realization semantics, observation duty, database or service.

Avoid sector-specific node enums, treating an electrical switch as a network switch, or using organizational entities as equipment placeholders.
Do not repurpose `runtime.software_components` merely because its vocabulary contains `device`.
Software refinements have acquisition/version/repository purposes; they are not a general equipment-profile host.
Do not hide enforced topology, units or safety claims in descriptions, `Relationship.properties`, labels or arbitrary snapshot payloads.
Generic `connects_to` relationships do not establish electrical laws, navigation performance or protocol behavior.
Keep backend choice, universal capability, a selected witness and independent observation separate.
