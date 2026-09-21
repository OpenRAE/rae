# ACT-618 participant outcome architecture preflight

Issue: #218. Date: 2026-09-21. Scope: design guidance, not implementation or
an implementation plan. The supplied requirement and issue are sufficient.

## Existing coverage and the actual gap

ADRs 020/022/054/067 own participant identity, semantics, runtime history, and
the behavior aggregate. SEM-215 owns interpretation between meaning layers;
SEM-216 owns state/evidence/view separation. ADR-073 owns reward language.
These authorities suffice; no new ADR or parallel participant subsystem is
needed. Paths below are relative to `implementations/python/packages/` unless
otherwise stated.

| ACT-618 clause | Incumbent and producer/consumer | Remaining boundary |
| --- | --- | --- |
| Explicit participant-local meaning | `raes/participant_outcome_semantics.py`, `raes_processor/models/outcome.py`; compiler `participant_contracts.py` produces rule resources, history/conformance consumes interpretation records | Sources/targets have free-form observed/interpreted values, not a governed local category/state contract. Source/target layers classify semantic layers, not outcome categories. |
| Role-neutral categories | `raes_contracts.participant_behavior.ParticipantActionResultStatus` already includes succeeded, failed, partial_success, unknown, rejected, withheld, accepted | These describe actions. Reusing their spelling does not establish participant outcome meaning. Episode status and lifecycle operation status are also distinct. |
| Outcome identity and reporting | `raes_contracts/contracts/participant_views.py:ParticipantOutcomeReportModel` (API-411), published `participant-outcome-report-v1` | Has `outcome_id`, rule/source refs and downstream relationships, but no category or evolving state. Shape acceptance does not resolve refs or prove grounding. |
| Evolving local state | `BaseParticipantRuntime`, `participant_binding_events.py`, `RuntimeSnapshot`, RUN-305/311 history and episode validators | Existing producers record action and episode history; inspection found no dedicated local-outcome state producer/reducer. Add missing behavior through these owners; do not count test-created interpretation records as a production producer. |
| Independence from scenario evaluation | SEM-215 explicit mappings and I10 outcome-layer separation | Rules/interpretation records currently require targets; API-411 requires downstream state relationships. Do not fabricate an objective/evaluation target merely to express a local outcome. |

The existing SEM-215 tests demonstrate source/target agreement, action/evidence/
terminal-episode grounding, provenance, and wrong-participant rejection.
They establish useful reuse, not completion of ACT-618. The implementation's
clause account must distinguish existing coverage from newly demonstrated
category, transition, and runtime-producer behavior.

## Decisions and semantic guardrails

- Extend the existing participant outcome/interpretation and report family.
  Local meaning must be representable without a downstream result. Any changed
  target cardinality or added local surface needs an explicit versioned contract
  decision; do not silently relax old SEM-215 invariants. Do not invent a second
  rule engine, outcome database, or generic event bus.
- Separate **category** (what participant-local condition is described),
  **state** (its current resolution/progress), and **knowledge/freshness** (what
  the evidence supports at a specified observation point). Neither actor role
  nor action success determines these. For example, a category describing
  completion of a participant's declared task can cover an offensive transfer,
  defensive containment, and ordinary-service delivery under their respective
  local criteria. This is a semantic example, not a new enum declaration:
  all three must use the same governed category and state rules.
- Outcome identity must distinguish the stable local outcome from each report,
  interpretation, action attempt, and state revision. Bind it to canonical
  participant identity and an exact episode within the enclosing run/snapshot
  scope. Multiple local outcomes per participant and multiple observations per
  outcome must be possible. Never key by role, display name, timestamp, or list
  position. Rule/model revision is part of the interpretation basis; changing it
  must not silently reinterpret an old record.
- Define admissible transitions, predecessor/revision checks, and correction
  behavior in the owning contract. Partial attainment is not missing knowledge;
  unknown, contradictory, withheld/redacted, stale, absent, and failed are not
  synonyms. Preserve contradictory evidence and its basis without promoting it
  to success or resolving it by arrival-order last-write-wins. Declare any
  resolution precedence explicitly. Reject malformed or misbound evidence;
  represent legitimate uncertainty without turning it into a transport error.
- Order updates using existing causal/sequence and shared-time authorities,
  including clock segments/state cuts where applicable. Freshness must refer to
  a declared observation point or validity rule, not wall-clock arrival alone.
  Duplicate delivery is idempotent; changed payload under the same update
  identity, stale predecessor, and an update for another live episode cannot
  overwrite current state. Corrections append provenance-bearing history.
- Initialize a new episode without inheriting achieved state accidentally.
  Reset/restart follow RUN-311 and retain old episode history; explicit transfer,
  if supported, cites its source and governing rule. Termination, truncation,
  timeout, and interruption do not imply achieved or failed local meaning.
  Late evidence for a closed episode must be rejected or recorded as an explicit
  historical correction under the declared policy, never applied to the new one.
- Keep current state a deterministic projection of validated history. Any
  materialized head must agree with that history after reload/replay. Persist
  head, history and revision through existing atomic snapshot/store commits;
  invalid input and commit failure must not leave caches ahead of durable state.
- Action completion, participant outcome, objective result, evaluation and reward
  remain separate. Cross-layer effects require explicit SEM-215 bindings and
  reward governance; an interpretation/report reference asserts a relationship,
  not authority to mutate the referenced objective or evaluator. Local state
  must work when no evaluator or reward producer is present.

## Cross-cutting layers the implementation must pass

| Layer and canonical incumbents | Required treatment |
| --- | --- |
| Authored decoding/shape: safe SDL parser, `SDLModel`, portable identifiers, `raes/scenario.py` | Use closed typed fields in the existing owner. Follow ADR-105 partial-description boundaries: a declaration is not evidence or an automatic collection request; abstract local meaning must not require invented backend detail. |
| Whole-scenario validation/composition: `SemanticValidator`, `raes/semantics/participant_outcome.py`, declaration indexes, `raes/composition/_behavior.py`, `_language_metadata.py`, `_module_symbols.py` | Resolve every supplied participant/rule/action/objective ref, rewrite it under composition, validate after instantiation. No executable meaning hidden in arbitrary metadata. |
| Compilation: `raes_processor/compiler/participant_contracts.py`, `participant_behaviors.py`, `addresses.py`, `alias_index.py`, `RuntimeModel` | Preserve deterministic addresses, declared dependencies and semantic revision. Reuse behavior specification rule refs instead of copying rules into each participant. |
| Wire/runtime shapes: `ContractModel`, `participant_runtime.py`, `participant_views.py`, `ParticipantRuntimeBaseEnvelopeModel`, processor `models/outcome.py` and `history_event.py` | Share semantic checks between existing dataclass and Pydantic representations. An outcome needing scope must require exact participant/episode bindings even though base-envelope scope fields are optional. Preserve timestamps, ordering, provenance, markings and source status; add no competing envelope. |
| Grounding/conformance: `models/outcome_interpretation_validation.py`, `behavior_grounding_checks.py`, `behavior_history_violations.py`, `raes_conformance/conformance/snapshot_semantics.py` | Reuse rule agreement and evidence/episode grounding. Wire the applicable compiled rules and prior state into real callers; a helper with optional context is not proof that each production path enforces it. Historical evidence aggregation needs explicit references and checks, since incumbent SEM-215 grounding is event-local. |
| Runtime admission/commit: `raes_backend_protocols/participant_runtime_base.py`, `participant_action_commit.py`, reference/libvirt runtimes, `raes_runtime/participant_action_validation.py`, `participant_result_contracts.py`, `backend_snapshot_contracts.py` | Validate producer updates before publication, including direct backend results, scheduler commits and replay/load. Reuse append-only history and ownership checks. Do not let backend output rewrite unrelated participant or scheduler state. |
| Persistence/concurrency: `RuntimeSnapshot`, `ControlPlaneStore`, `control_plane_store_revision.py`, terminal commits, `control_plane_durability.py`, shared participant reset helpers | Use existing snapshot revision/CAS, serialization, atomic commit and cache recovery. Concurrent actions cannot lose outcome updates. Do not store local state in free-form snapshot metadata or a second journal. |
| Observation/authorization: SEM-214/216, participant crossing/flow/opacity policy, `participant_retrieval.py`, `ParticipantHistoryViewModel`, `control_plane_api_participant_retrieval.py` | Participant-local does not mean participant-visible. Project under existing audience, evidence, marking and redaction rules; bind nested refs to the same participant/episode. Category, uncertainty, timing and diagnostic metadata can themselves disclose hidden truth. Refs are not permission to retrieve evidence. |
| HTTP, if a view or mutation is exposed: `ControlPlaneSecurityConfig`, `control_plane_api/_auth.py`, `_operation_routes.py`, P1/P2 profiles | Preserve strict authentication, target and participant subject/audience binding, bounded request/admission, mutation authorization, idempotency fingerprints, revision checks and audit. An authored offensive/defensive role grants no API authority. No new HTTP route is inherently required. |
| Errors/observability: SDL error types, `Diagnostic`/`Severity`, `portable_diagnostic_payload`, `_responses._conflict_detail`, request exception handlers | Use stable bounded diagnostic codes/refs and existing audits/operation receipts. Portable diagnostics require bounded messages and JSON-Pointer addresses; do not pass raw Pydantic input, evidence, exception text or backend output to logs/HTTP. Preserve redacted validation/conflict/500 envelopes. No ACT-618 exception hierarchy or logger stack. |
| Configuration/secrets/host exposure: `participant_configuration.py`, `contracts/experiment_bindings.py`, `secret_references.py`, existing execution/launcher owners | The outcome design needs no new environment binding, credential, process, socket or filesystem store. If a selected producer consumes configuration, retain declared target/type checks and literal versus secret-reference identity. Evidence uses refs, never secret values, environment dumps or private answer keys. Do not add tokens to argv, ad hoc env injection, shell evaluation, or outcome-driven file paths; retain existing host execution and store-permission boundaries. |

The native autonomous commit path intentionally accepts only terminal action
statuses and excludes `unknown`, although the action enum contains it. Unknown
participant outcome knowledge must not weaken that action gate. Similarly,
current behavior history attaches interpretations only to `observation_emitted`
events, and episode-status sources require matching terminal episode history.
Do not invent fake action attempts to carry episode/evidence-only updates or
bypass these rules with a dictionary; any required extension belongs in the
existing lifecycle contract with explicit compatibility semantics.

## Extensibility, publication and verification boundaries

The extension seam is the existing outcome/interpretation definition selected
by stable reference and semantic revision, parameterized by governed category,
local criterion/evidence basis, transition/conflict policy and freshness basis.
Keep those rules independent of participant role and backend. A second category,
new evidence source, or another participant with the same category should reuse
the same state/history machinery. Use ADR-012/062 concept authority for governed
terms/extensions; no arbitrary Python callbacks, user-supplied expressions or
unvalidated strings as an extension mechanism. This does not require a new
profile registry or prescribe new public fields.

Repository-wide publication owners are `contracts/schemas/`, `schema_bundle()`,
`tools/generate_contract_schemas.py`, `tools/check_generated_schemas.py`,
`tools/check_schema_publication.py`, and the manifest's current per-contract
entries under `contracts/schema-publication/entries/`. API-411 is currently
draft; that permits ledgered schema evolution, not silent historical data
reinterpretation. Apply ADR-061 and ADR-096 plus
`specs/evolution/versioning-deprecation-and-migration.md`: preserve old records,
identify reader/writer versions, and provide explicit migration/unsupported
behavior. Never backfill achieved state from old action success or treat an
absent historical field as a recorded unknown observation. Stable breaking
changes require a new contract version and the existing deprecation process.

Changed contracts require matching governed schemas, publication hashes and
`last_change`, fixtures, formal guidance, SDL section/reference catalogs where
applicable, installed schema corpus and real IMPLEMENTS/TESTS traceability.
Use `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, schema/catalog/
concept/authority policy checks and existing nox verification lanes; no new
issue-local workflow. CI owns full verification. This note does not claim
requirement satisfaction or create implementation/test links.

Behavioral evidence must exercise actual producers and rejection paths, reusing
`test_sem_215_participant_outcome_interpretation.py`, RUN-305/311 tests,
participant backend-contract and runtime-invariant tests. Required cases include
the same category across all three roles, local success with objective failure,
local uncertainty after action completion, partial/conflicting/stale evidence,
wrong participant/episode/rule binding, retries and concurrent updates, reset
with retained history, persistence/replay, and historical migration. Test hidden
evidence leakage through views and error envelopes, not just JSON Schema shape.

## Non-goals and anti-patterns

No requirement implementation, schema/code/fixture changes or implementation
plan in this preflight. ACT-618 does not own holdings lifecycle (#217), identity,
action execution, a new evaluator/reward system, controller workflow, observation
collection, or backend infrastructure. Reference holdings through their owner.
Avoid role-specific outcome schemas, Boolean success propagation, parallel
validation/resolution/exception/store stacks, unconditional evidence collection,
implicit reset carryover, mutable historical records, and claiming that schema
or fixture acceptance demonstrates production state behavior.
