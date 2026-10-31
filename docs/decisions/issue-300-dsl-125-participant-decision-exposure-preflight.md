# Issue 300: Participant decision exposure preflight

Date: 2026-10-31. Requirement: DSL-125 (DRAFT). Inspected revision: `34afe9696`.

This is architecture guidance, not an implementation plan or evidence of
fulfillment. The remaining work is the checked connection from authored choices
to participant content. No new ADR is needed: ADR-083/085/095 own exposure and
decision semantics; ACT-620 owns control-context assets; ADR-110 owns reusable
control occurrences. Read the [#299 preflight](issue-299-dsl-118-control-context-references-preflight.md),
[control-context migration](../explain/sdl/control-context-migration.md), and
[current control reference](../explain/reference/revised-control-semantics.md)
together with this note. Older preflights describing API-423/RUN-319 as future
work do not describe the current runtime.

## Existing support and remaining joins

Paths below are relative to `implementations/python/packages/` unless stated
otherwise. These are implementation boundaries, not permission to duplicate
their internals in a new exposure service.

| Existing owner | What already exists; remaining obligation |
| --- | --- |
| `raes/participant_control_context.py`; `raes_processor/compiler/participant_behaviors.py` | Direct and reusable `control_context` slots already carry exact ACT-620 pins and `selected`/`withheld` intent. `resolve_authored_control_context()` checks resolution, applicability and conflicting participant slots. Compiled `ParticipantBehaviorRuntime` and `ParticipantBehaviorSpecificationRuntime` retain `ResolvedControlContextSelection`. Consume both applicable paths, plus admitted trial configuration selections; do not add competing syntax for the same choice. |
| `raes/participant_behavior/_view_boundaries.py`; processor `compiler/participant_contracts.py`, `compiler/view_relations.py` | Observation boundaries already classify instructions, scaffolds, hidden truth, answer keys, holdouts, adjudication and archival evidence, with view rules and transitions. Compilation retains canonicalized refs and `view_relation_timeline`. Reuse this visibility relation; asset kind is not another visibility taxonomy. |
| Processor `models/decision_surface_v2.py`, `models/participant_exposure_v2.py` | The projector validates scope, trusted anchors, visibility and exact-cut exposure. It takes `visible_context_refs` and assessments from its caller; it does not derive them from compiled `control_context`. The authored-selection-to-candidate-item join must be explicit and exercised at this consumer. |
| `raes_contracts/participant_control_context.py` | `validate_control_context_asset()` and `validate_control_context_record()` already check content commitments, lifecycle, selection authority, cut order, applicability, context-view/source/transformation agreement, exposure and delivery. Use these checks with trusted validation context; a valid descriptor or authored selection is not an authorized record. |
| `raes_contracts/participant_decision_surface_delivery.py`; runtime `participant_decision_surface_control_v2.py` | Delivery binds an authoritative occurrence and validates coordinates/digest; selection re-resolves delivery and the current anchor before ordinary action admission. The delivery helper does **not** resolve policy at the delivery cut: its trusted producer/resolver must establish that fact. A nonempty authorization or policy ref is not sufficient evidence. |
| Runtime `participant_crossing_mediation.py`, `participant_crossing_egress.py`, `participant_crossing_commit.py` | API-423/RUN-319 already own exact-cut crossing decisions, transformations, final egress gates, retained results, history-head checks and atomic commits. Reuse `prepare_participant_crossing()`, `serialize_participant_view()` and `commit_prepared_crossing()` through their owning runtime interfaces; do not infer an installed surface transport from their existence or build a second workflow. |

Two reference pitfalls need explicit treatment. Observation-boundary semantic
checks bind view rules to the boundary's declared lists; that alone does not
resolve an ACT-620 asset. The compiler's visibility alias index covers
runtime-addressable declarations and leaves unmatched strings unchanged.
Control-context declarations are support declarations, not runtime resources.
The new join must resolve them through #299's declaration/pin authority and
retain an unambiguous correspondence to the exposure item. Do not broaden every
reference purpose, relabel assets as resources, or accept an unknown asset just
because its string appears in `observable_refs`.

## Authored choice versus runtime authority

| Concern | SDL responsibility | Apparatus/live authority responsibility |
| --- | --- | --- |
| Observations and ordinary context | Participant/behavior scope, observation boundaries, view dispositions and transitions | Exact history/cut, source resolution, permitted representation and actual observation |
| Control-context assets | Existing immutable reference and selection slot, including explicit withholding | Selected implementation/configuration, trusted role applicability, lifecycle/content validation and independent disclosure/delivery |
| Hidden, evaluator and benchmark-only material | Existing sensitive boundary classes; hidden or evidence-only intent, explicit disclosure rule when exposure is authored | Deny by default; resolve marking, transformation and declassification authority where applicable. Benchmark origin is not permission to expose. |
| Role-specific context | Existing `Agent.effective_role()` and `select_participants()` scope | Authenticated participant/audience binding and role authority at the relevant cut; a controller, affiliation or deployment tenant is not a participant role |
| Exposure policy | Only the minimum missing typed authored reference/choice, if incumbents cannot express it | Pinned `ParticipantImplementationSelectionModel.exposure_policy`, policy-at-cut decisions, item authorizations, backend support and realized occurrences |

`selected` means eligible selection intent, not visible. Authored withholding
must survive compilation and consumption; a permissive apparatus cannot erase
it. `ParticipantExposurePolicyModel.withheld_refs` already wins over its allow
lists. Absence of permission also denies release, but it is not evidence of an
explicit withholding occurrence. Conflicting direct/reusable/factor selections
must use the existing conflict rules, not last-write-wins or declaration order.

Keep the selected exposure-policy id/version/digest separate from the SEM-230
projection-policy revision/decision, an ACT-620 asset whose kind is `policy`,
and an ADR-110 mixed-control policy. Policy `constraints`, behavior extensions,
snapshot metadata and arbitrary dictionaries are not executable policy stores.
SDL never authors trusted authorization outcomes, live cuts, delivery receipts
or caller entitlements.

## Exact content, cuts and evidence

The required trace is one real declaration through its compiled participant
slot and boundary, exact resolved asset/source, authorized context result,
v2 exposure binding, canonical participant-view digest, trusted delivery and
provenance. A manually constructed projection fixture that bypasses compilation
does not demonstrate this trace.

ACT-620 already requires an exposure binding's source to be
`"urn:" + asset_digest`, a matching `participant_control_context_asset` source
layer, and the context view's transformation/source join. It checks the context
view's `payload_ref == record.item_ref`. Do not assume an arbitrary multi-asset
bundle satisfies that single-payload join; use existing governed result
identities, or govern a necessary contract change explicitly. Imported local
names may change; immutable descriptor pins must not. A locator or view ref is
not a content commitment, and hashing a reference does not hash dereferenced
bytes. Reuse ACT-620's associated-artifact checksum/size validation and preserve
the exact source-to-result commitment through any approved content reader.

Use `project_participant_decision_surface_v2()` with
`ParticipantDecisionSurfaceProjectionInputV2` and `ParticipantExposureResolversV2`.
Epoch zero comes from `episode_running`, the complete lifecycle prefix and empty
current-episode behavior history. Later epochs use the exact current terminal
observation prefix and `participant_observation_effective_relation()`. A
decision epoch, history index, generation, policy revision and state cut are
different coordinates. The reference projector rejects unsupported causal
frontiers; do not silently linearize them.

At delivery, independently resolve current authority for the exact delivery
cut, recipient, audience, policy and immutable content. A policy or role change
after projection can refuse delivery even within the same epoch. Reuse runtime
mutation reservations, revision/history-head validation and actor-scoped
idempotency; recheck after external resolver calls through existing control-plane
boundaries. Never update an old surface's digest in place to accommodate changed
content. A changed view requires a new governed projection. Retry and recovery
must use retained outcomes without silently reauthorizing changed bytes or
claiming an external delivery happened twice.

The participant payload is the authorized participant view and its authorized
content, not the full v2 carrier. Assurance-only cuts, authorization records,
evidence and provenance stay outside that payload unless independently exposed.
The existing exposure coverage validator covers visible context refs, actions
and affordances; it is not a blanket authorization of `context_view_ref`, form
values, information-state ids, limitation text, headers or dereferenced content.
The final serializer/content consumer must cover those channels as well as
action presence/order, error detail and refresh behavior. Derived results retain
source markings/provenance unless governed declassification changes them.
Redaction does not grant access; a ref or digest can itself disclose information.

Projection, authorization, disclosure, delivery, observation, selection and
admission remain separate facts. Preserve `delivery_basis` and its limits;
`emission_is_delivery` requires an explicit supported boundary. Revocation,
reset and restart do not erase participant knowledge or historical evidence.
V1 retains historical `observation_order` meaning and is not actionable via v2;
migration requires trusted reprojection, not a rename or synthesized history.

## Cross-cutting gates

| Layer and canonical incumbent | Required treatment |
| --- | --- |
| Ingress/config shape: `raes/parser.py`, `_yaml_loader.py`, `_source_validation.py`, `_mapping_scopes.py`, `_base.py`; `raes_contracts/json_ingress.py`, `contracts/base.py` | Preserve bounded safe parsing, duplicate/normalized-key collision rejection, literal declaration keys and closed models. Reuse schema/key classification and reject malformed or non-finite values. No second loader or permissive policy bag. |
| References/imports/instantiation: `raes/_declarations.py`, `_reference_targetability.py`, `_language_metadata.py`, `composition/`, `validator/`, `instantiate.py`, `phase_contracts.py`, `canonical.py` | Navigation, composition, semantic checks and compilation must resolve the same identity. Retain module confinement/trust/pins, post-substitution and direct-artifact revalidation. No generic string substitution into immutable descriptors or trust in validation flags/unchecked model copies. Preserve legacy canonical bytes when new choices are absent. |
| Trial configuration: `raes_contracts/participant_configuration.py`, `contracts/experiment_bindings.py`; processor `trial_compiler/bindings.py` | Consume #299's typed `control_context_selection` from the admitted configuration with its owner validator, manifest/configuration pins and provenance. Do not recompute it from current defaults or invent another binding plane, env binding or scalar-encoded JSON object. |
| Asset/content: `raes_contracts/participant_control_context.py`, `associated_artifacts.py`, `uri_safety.py` | Resolve exact id/version/digest; check lifecycle and applicability at use, trusted cut ordering, content checksum/size and selection/disclosure/delivery authority. URI syntax safety is not fetch authorization. No network/file acquisition during static validation; reuse confined bounded readers. |
| Authentication and authorization: runtime `control_plane_security.py`, `control_plane_api/_auth.py`, `participant_crossing_policy.py` | Keep strict security defaults, target/run identity, request limits and `ParticipantAudienceSubjectBinding`. An administrative read role is not participant release authority. `control_plane_api_participant_retrieval.py` without a crossing resolver remains administrative only. Authored audience strings cannot replace trusted subject bindings. |
| Information flow: `ParticipantContextViewModel`, v2 exposure contracts/resolvers, runtime `participant_crossing_egress.py`, `participant_flow_sink.py`, `participant_control_orchestration.py` | Preserve SEM-214 source and SEM-216 archival mediation, exact-cut visibility/marking/transformation checks, API-423 contextual validation, SEM-233 final sinks and configured control/opacity gates. Missing required owner or unsupported capability fails closed; independent passing capabilities do not prove a supported combined installation. |
| Persistence: runtime `control_plane_store.py`, `control_plane_store_local_codec.py`, `control_plane_store_records.py`, `participant_crossing_commit.py` | Use existing snapshots, records, evidence refs, retained governed result and atomic commit/replay. Preserve distinct decision and realization records and revalidation on load. Store only authorized content in each owning carrier; no exposure database, sidecar journal, metadata cache or raw hidden content in audit. |
| Errors and logging: `raes/_errors.py`, `_model_diagnostics.py`; `raes_contracts/diagnostics.py`, `errors.py`, `operational_logging.py`; runtime `control_plane_api/_responses.py` | Reuse collected SDL diagnostics, `Diagnostic`, operation receipts and ADR-116 categories. Value-object validators retain `ValueError`; new domain failures use the shared categories. Isolate trusted-host calls through existing `resolve_from_host()`/`isolated_host_call()` paths. Do not broadly catch programming errors as policy denial. Return coarse safe refusal codes, never raw projector/Pydantic error text containing item refs or rejected inputs. Use value-free logging once at the owning boundary; hosts must also format ASGI/worker logs safely. Logs/audit do not prove delivery. |
| Secrets/environment/OS: `raes/runtime_environment.py`, `runtime_configuration.py`, `runtime_generated_value.py`, `runtime_values.py`; `raes_contracts/secret_references.py` | This join requires no new env variable, credential, process or transport. If an existing adapter consumes content, preserve unique env names, literal/`value_from` exclusion, sensitivity/provenance and generated-output checks. Private context is not a secret-reference identity. Keep content, tokens, locators and hidden identifiers out of argv, shell strings, environment dumps, public temp files, stdout/stderr and exception chains. Do not resolve operator credentials during compilation. |
| Package/publication/workflow: ADR-117, repository `tools/policy/import_contracts.toml`, `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `tools/check_repo_policy.py` | Authored semantics stay in `raes`; compilation/projection in `raes_processor`; portable contracts in `raes_contracts`; live authorization/store/transport ownership in `raes_runtime`; checks in `raes_conformance`. Use public interfaces rather than new cross-package private imports. Normative language stays in `specs/`; published schema changes require ADR-009/061 governance, `schema_bundle()` parity, valid/invalid fixtures and `last_change` hashes in manifest-routed publication entries. Use targeted local checks with `RAES_REQUIREMENT_UID=DSL-125`; full suites stay in CI. |

## Extensibility and acceptance boundaries

The extension seam is the existing compiled selection plus injected exact-cut
apparatus, policy, authorization, content and delivery owners. Parameterize by
immutable asset/item identity, participant, episode/generation, audience/role,
source layer, cut/order model and selected policy pins. A second role, new asset
version or later disclosure must use those coordinates rather than another
asset-kind branch, global catalog, boolean allow flag or controller workflow.
Any necessary new typed binding belongs to the existing owner and must be
consumed and validated, not merely stored in a `spec` dictionary.

Required evidence belongs in existing test/fixture homes:
`test_dsl_118_control_context.py`, `test_dsl_118_trial_control_context.py`,
`test_act_620_control_context_*.py`, `test_sem_226_participant_exposure.py`,
`test_sem_220_participant_decision_surface_v2*.py`,
`test_issue_301_projection_boundaries.py`, and the crossing, authorization,
diagnostic and schema-publication suites. Demonstrate the compiled-to-delivered
trace above for initial/later decisions and distinct roles, plus withholding,
unknown or conflicting assets, wrong participant/episode/generation, stale or
incomparable cuts, policy/role change before delivery, transformed content,
assurance-only data, missing owners, altered bytes, replay/reset and safe errors.
This is an acceptance boundary, not a prescription to run whole suites locally.

Non-goals: a new policy language, visibility taxonomy, asset registry, universal
exposure DTO, exception hierarchy, logger, endpoint, backend transport or
scheduler; redesigning ACT-620 lifecycle or ADR-110 control; automatically
granting declassification; rewriting historical v1 records; and claiming
universal noninterference, backend certification or participant understanding
from bounded tests. Update migration/examples and actual IMPLEMENTS/TESTS links
when support ships. This preflight neither activates DSL-125 nor claims its
acceptance criteria are already met.
