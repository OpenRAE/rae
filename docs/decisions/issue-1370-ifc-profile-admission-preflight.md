# Issue #1370 — IFC representation and admission preflight

Date: 2026-10-16. Inspection baseline: `e5cb3497`.
The supplied issue is the delivery contract. API-424 was subsequently added
to its authoritative Requirements section for this contract delivery.
This is architecture guidance, not an implementation plan or support claim.
[ADR-114](adrs/adr-114-ifc-profile-variability-and-publication.md),
[IFC-01–07](../../specs/formal/participant-semantics/ifc-profile-variability.md),
[CA-01–09](../../specs/formal/participant-semantics/control-applicability-and-evaluation.md)
and their migration contracts already decide the semantics. No new ADR is needed.
Package paths below are relative to `implementations/python/packages/`.
Python paths beginning `contracts/` denote `raes_contracts/contracts/`;
bare Python filenames in a module list retain the preceding directory.

## Representation and authority boundaries

Use the accepted **governed closed finite publication** for additional owner
distinctions. Publish the concrete finite owner/clause universe, its source and
default resolution, sink relations, releases, memory scope, bounds and limits.
Preserve the original security profile's bytes, digest and interpretation.
Its `restricted`, `unknown` and `endorsed` tokens cannot acquire new owner
meanings. No owner-parameter syntax, arbitrary labels, policy interpreter or
SDL authoring expansion follows from this decision. Existing exact governed
references can supply author intent; operator bindings realize that meaning.

Confidentiality and integrity remain independent coordinates. Their security
join unions obligations, which conjoins audience restrictions; it does not
union allowed readers. Independently releasable clauses stay distinct even
when their current audiences coincide. Endorsement never releases confidentiality
or removes possible-writer provenance. Unknown source/coverage is unresolved,
never known untrusted input, an empty input set or bottom. Opaque derivation,
control dependence, memory, shared state and handoff retain every possible input
unless published non-influence evidence justifies exclusion. Preserve other
SEM-235 domains' general conservative join contract without imposing security's
powerset representation on them.

Two contract gaps must be settled explicitly in the owner-aware publication:

- `ParticipantFlowReleaseAuthorityCoordinate` in
  `raes_contracts/contracts/participant_flow_control_context.py` scopes kind,
  authority and sink/destination/audience, but has no discharged-obligation
  scope. Its membership check in `participant_flow_control_profile_validation.py`
  cannot alone establish A's authority over each removed/replaced clause.
  Extend the incumbent trusted relation with exact per-obligation authority;
  bind it to the source/result, profile, policy/cut and destination. Portable
  claims, known authority references, authenticated roles and token prefixes
  cannot supply this authorization. A grant over A must never release B.
- `ParticipantFlowEndorsementModel` requires nonempty token replacements;
  `participant_flow_control_relation_validation.py` checks their exact delta.
  IFC-03's semantic discharge needs an explicit, validated correspondence to
  that carrier or a distinct governed carrier. Merely replacing all owners'
  tokens with the historical `integrity:endorsed` loses the required distinction.
  Retain other owners' obligations, fresh result identity and immutable lineage.

The extension seam is the **exact published profile binding plus trusted
principal/source/sink/authority resolution**, consumed by existing contract
validators and API-424. Keep concrete principals and sinks as typed admitted
bindings only where the published relation permits variation. A further owner
outside the finite universe requires another governed publication; repeated
deployment needs may justify a separately decided bounded parameter contract.
Do not encode owner semantics in backend names or create a parallel registry.
The SDL `raes_contracts/domain_profiles.py` extension/admission family, backend
profiles and P1/P2 control-plane profiles have different owners and meanings;
their admission does not register a participant IFC profile or release grant.

## Incumbents and current integration limits

| Canonical incumbent | Guardrail for this delivery |
| --- | --- |
| `raes_contracts/participant_flow_policy_profiles.py`; `contracts/participant_flow_control_semantics.py` | Loader allowlist, model literal identities, exact artifact digest and semantic authority currently admit only security rev1. Its array limit of 128 is a shape bound, not permission to add tokens. Extend coherent published support rather than relaxing the digest or accepting arbitrary JSON. Rule references describe meaning; they neither execute it nor prove realization. |
| `contracts/participant_control_profiles.py`, `participant_control_results.py`, `participant_control_composition.py::_validate_ifc_result` | Both v1 and inherited v2 bindings use the closed profile validator. Security facts and domain-to-profile dispatch still select the legacy security profile; v2 publication did not make them extensible. Reuse the typed security relation/label reference and owning validator where its meaning fits, with explicit supported dispatch. Do not duplicate labels or infer that every non-teaching domain is legacy security. |
| `contracts/participant_control_applicability.py`, `participant_control_support_v2.py`, `participant_control_composition_v2.py`, `participant_control_resolution.py` | API-424 v2 already owns complete apparatus B, exact-cut coverage A(B,K), required dependency closure, per-obligation/input strength and constraints, composition and independent trusted resolution. Bind IFC obligations into these carriers; do not filter B or introduce a second coverage/satisfaction engine. An API-424 evaluation obligation and an IFC label clause are related but distinct identities. |
| `raes_backend_protocols/participant_feature_admission.py`, `participant_control_admission.py`; `raes_contracts/manifest_authority.py` | API-407 owns declaration strength, required contracts and evidence; API-424 joins exact installed/effective support. `participant_modular_control` alone proves no owner-aware source, control-flow, memory, release or final-sink coverage. Keep the authored profile distinct from backend-facing supported contract IDs. A positive v2 support-relation string requires the trusted resolver's evidence and constraint comparison. |
| `raes_runtime/participant_control_binding.py`, `participant_control_evaluation_v2.py`, `participant_control_orchestration.py`, `participant_flow_sink.py`, `control_plane_composition.py` | Explicit v2 bindings pin both selection/evaluation schema-content digests and installed providers/stages. Runtime evaluation already fences callbacks, detaches inputs and uses supervision/CAS. Legacy final-sink IFC is separately selected by `enforce_final_sink_flow_control`; a mandatory IFC promise must not run through an unselected or legacy-only substitute. Reuse the existing sink-facing admission path and owning validators. |
| `raes_runtime/participant_control_effects.py`, `participant_control_receipts.py`, `participant_effect_authority.py` | V2 effect drain currently reports executable effects unsupported with zero dispatch. IFC label release remains a flow-relation operation; it is not automatically an executable world effect. Where realization requires such an effect, a profile artifact, eligible composition or request cannot prove application. Admit only realizable release operations. Reuse existing typed effects, authority, prerequisites and receipts for necessary world effects; no new dispatcher. |

Keep unsupported **expression**, unsupported **realization**, supported policy
denial and loss of an **admitted promise** distinguishable in existing safe
status/reason/evidence carriers. V2 can admit evidenced bounded support when
the authored constraints permit it; legacy v1's all-exact behavior is unchanged.
Compare execution with the guarantee actually admitted, including extra promises,
not just the earlier minimum. Losing coverage, authority, freshness or evidence
blocks affected mandatory release even if the minimum would still be met.
Downgrade permission does not prove satisfaction. A different promise requires
a separately authorized binding at a new cut, preserving every other owner.
Optional advice cannot fill required coverage or authorize a mandatory release.

The legacy profile model is mutable and its loaders cache shared instances.
Protect published authority from mutation and validate detached canonical data
at trust boundaries; `model_validate(existing_instance)` alone need not rerun
validators. Freezing an outer wrapper does not freeze nested data or its cache.

## Cross-cutting gates the design must pass

| Layer and canonical owner | Required satisfaction |
| --- | --- |
| Portable ingress: `raes_contracts/json_ingress.py`, `_base.py`/`contracts/base.py`, `contracts/participant_control_coordinates.py`, `participant_control_evaluation_v2.py` | Reuse bounded, duplicate-rejecting JSON parsing and closed models. Supply explicit depth and collection/graph bounds; bound file reads before decode. Base `ContractModel` forbids extra fields but does not make every scalar strict or every object immutable. Check direct Python ingress too; reject coercion, unknown tokens/variants, duplicates, cycles and oversized relations. Detach nested values and revalidate provider/resolver projections. No `model_construct` or unchecked copy/update bypass at trust boundaries. |
| Publication/configuration: `raes_contracts/participant_flow_policy_profiles.py`, `corpus.py`, `participant_configuration.py`, `contracts/experiment_bindings.py` | Resolve allowlisted exact profile/revision/digest and independently pinned implementation/configuration. Use the packaged corpus in installed distributions. No scenario-selected filesystem root, URL fetch, import, executable selector or latest fallback. Where participant implementation configuration is involved, reuse its target registry, declared value validation, complete canonical target set, owner-preserving normalization and configuration digest. Configuration cannot introduce new profile meaning. |
| Semantic trust: `contracts/participant_flow_control_validation.py`, `participant_flow_control_profile_validation.py`, `participant_flow_control_relation_validation.py`, `participant_flow_control_incumbent_validation.py`; API-424 `participant_control_resolution.py` | Structural shape and a digest do not establish authority. Independently resolve source labels, possible writers, policy/cut, owner grants, known sinks, admitted coverage/support and safe evidence. Conjoin incumbent runtime-fact, validated action argument/admission, API-409 control, API-423 crossing, capability and history-head gates. Preserve the typed carrier relation: a derived IFC argument subject need not be the enclosing crossing subject. Missing or stale joins prevent release. |
| HTTP/auth and effect authority: `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_api_guards.py`, `participant_effect_authority.py` | No new route is needed. Existing consumers retain strict defaults, bearer/verified-proxy identity, target/role/actor scope, sealed route composition and bounded bodies. P2 transport identities are privileged administrative service identities; they are not IFC owners, participant-limited credentials or release grants. Participant/controller/audience projection and each effect owner's current authorization remain separate conjuncts. |
| Secrets, environment and host: `raes_contracts/secret_references.py`, `participant_configuration.py`; `raes/runtime_environment.py`, `runtime_values.py`; runtime execution adapter/supervision | Portable profiles, state, predecessor inputs, evidence, diagnostics and fixtures carry bounded disclosure-authorized values/references, never operator credentials or private provider payloads. Preserve literal versus secret-reference disposition and secret-reference identity during normalization. Any environment binding must pass name, `value`/`value_from` exclusivity, classification and observed-redaction checks; generated values cannot claim `operator_secret`. Secret-name heuristics do not establish IFC labels or release authority. No new launcher is required; never put sensitive material in argv, shell text, temporary names or logs. Host process/network isolation remains backend-owned; timeout fences are not a sandbox or hard cancellation. |
| Errors/observation: `raes_contracts/diagnostics.py`; `raes_conformance/conformance/diagnostics.py`; `raes_runtime/backend_result_diagnostics.py`, `participant_control_diagnostics.py`, `control_plane_audit.py`, `control_plane_api/_responses.py`, `_operation_routes.py`; `raes/observability_plane_semantics.py` | Reuse existing exceptions at their boundaries, stable bounded reasons, diagnostic/receipt envelopes, logging and audited transitions. Sanitize before constructing diagnostics, including attacker-controlled field names/paths/refs; `portable_diagnostic_payload` validates shape, not redaction. Retain redacted HTTP errors and no-store responses. Audit detail keys, identifiers and disposition enums must pass the existing closed validators. Classify new carriers and apply audience projection to owner identities, denied-flow existence and support/evidence details; operational storage is not permission for participant disclosure. |
| Persistence/recovery: `raes_contracts/participant_control_evaluation_history.py`; `raes_runtime/participant_control_records.py`, `participant_control_provider_state.py`, `participant_control_causal_state.py`, `control_plane_store.py`, `control_plane_store_record_migration.py` | Keep immutable evaluation/profile/configuration interpretation, accepted state, intents, causal budgets, operation and audit in the existing expected-head/snapshot-CAS transition. Memory, local SQLite and PostgreSQL store adapters share this boundary. A failed/uncertain commit permits no downstream call/disclosure. Use supported reader/migration negotiation if persisted meaning changes; no second store or snapshot metadata side channel. Retention and commit do not imply resumability, exactly-once effects or permission to dispatch again. |

Shared structural and algebraic validation belongs in `raes_contracts`; trusted
joins belong in its existing context validators and operator resolvers. Routes,
runtime, conformance and backends consume those decisions rather than copy them.
`raes_backend_protocols` must remain neutral and cannot import runtime, concrete
backends or conformance sanitizers. Preserve the layering/file-size rules in
`tools/policy/adr_policy.yaml` and `tools/policy/repo_policy.py`.

## Publication, migration and evidence limits

Publish the complete changed contract closure: normative `contracts/schemas/`,
matching `contracts/bundle_runtime.py`/exports and `schema_bundle()`, explicit
`tools/generate_contract_schemas.py` routing, fixtures, allowlisted profile and
fact readers, `manifest_authority.py`, `contracts/schema_invariants.py`/
`x-raes-invariants`, and `raes_conformance/conformance/validators.py`.
Schema-only conformance must continue to require trusted context where needed.
Reuse the build hook and corpus packaging in `implementations/python/pyproject.toml`
and `implementations/python/hatch_build.py`; a checkout-only artifact is incomplete
publication. Use `tools/check_generated_schemas.py` and
`tools/check_schema_publication.py` for the existing parity/ledger gates.

The live schema ledger is **manifest v2**: per-contract records with hashes and
`last_change` in `contracts/schema-publication/entries/`, and governed tombstones
in `contracts/schema-publication/tombstones/` for removals. Do not revive the old
embedded manifest layout. ADR-061 permits recorded draft edits but never silent
historical reinterpretation; stable breaking edits require a new contract ID.
Distinguish profile/semantic pins, RFC 8785 artifact/binding digests and the
publication checker's schema-content hash projection. Reuse their canonical
helpers and prescribed sorted set arrays, not another hash implementation.
The incumbents are `raes_contracts/canonical.py`, `_canonical.py`, API-424's
`control_digest` and the publication checker's own hash helper.

Apply [IFC migration](../migration/ifc-profile-variability.md) together with
[API-424 migration](../migration/control-applicability-and-evaluation.md).
Old/new readers select exact recorded interpretations; unknown profiles and
mixed unsupported revisions fail closed. Coarse historical labels cannot
reconstruct owners. Any conversion needs an authorized published mapping,
explicit loss and a fresh derived identity. Preserve retained memory, possible
writers, original releases, pending effect identities, receipts, consumed budgets
and indeterminate outcomes; re-admit at a new cut before further release.

The incumbent evidence patterns are `test_sem_233_flow_control_contracts.py`,
`test_api_424_security_profile.py`, `test_issue_1365_applicable_contracts.py`,
`test_issue_1003_final_sink_flow_enforcement.py` and
`test_issue_1069_provider_evaluation_v2.py`. Extend real parser/context/admission
and sink-facing witnesses, keeping schema-invalid cases separate from
shape-valid but untrusted/unpublished cases. The #1354 finite model supplies
semantic examples, not production profile or backend support.

Required separating evidence includes equal-audience independent owners;
A/B audience intersection and A-only selective release; A-only endorsement
with B still required at an action sink; permissive observation retaining B's
influence; opaque/memory/handoff propagation; unknown owner/token/profile and
foreign/stale grants; expressible but unrealizable coverage; precise bounded
admission versus later weakening; and old/new history with pending work.
Denied live paths need zero prohibited calls/disclosures and truthful outcomes,
including failed commits. Refusing everything is not evidence of required
selective sharing. New assurance claims need the existing probe/catalog and
source-bound research-capture workflow, not upgraded synthetic evidence.

Workflow owners remain `.ground-control.yaml`, `.gc/plan-rules.md`,
`tools/policy/requirement_order.yaml`, `tools/requirement_context.py`,
`noxfile.py`, `tools/nox_support/`, pre-push hooks and CI. Preserve authority,
concept, publication and lineage checks. This run uses API-424, explicitly attached to issue #1370 through the scope
writer after the initial inspection. Exact changed-path ownership/scope and
RAES_REQUIREMENT_UID=API-424 resolve the earlier requirement-context concern;
this does not authorize runtime-source ownership or weaken governance checks. Local checks remain targeted; CI owns full suites.

Non-goals: a general policy/plugin language, dynamic owner discovery, a new
credential/configuration framework, duplicate schemas/validators, exception
hierarchy, logger, store, scheduler or effect dispatcher; arbitrary cross-profile
joins or automatic conversion; rewriting historical authority; and claims of
universal noninterference, covert-channel control, opaque-internal mediation,
model trust or backend equivalence. This preflight changes guidance only.

Inspection checks: 110 focused cases passed across
`test_issue_1354_ifc_profile_variability.py`, `test_sem_233_flow_control_contracts.py`,
`test_api_424_security_profile.py` and `test_issue_1365_applicable_contracts.py`.
File-local repo policy passed before and after adding this note. An additional
run of the final-sink and v2 runtime modules timed out in the runtime execution
portal and was stopped; it supplies no runtime pass claim.
