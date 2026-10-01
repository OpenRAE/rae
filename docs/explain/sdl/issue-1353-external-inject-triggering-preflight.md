# Issue #1353 — External inject triggering architecture preflight

Date: 2026-09-22. Inspection baseline: `c3a9154b9be85f4cf60688df9c384385baae03cd`.

Scope: DSL-111 and the amended DSL-142 requirement at the issue #1353 boundary.
The supplied requirement and issue payloads are sufficient; no re-fetch is needed.
This note is preflight guidance, not the issue's accepted semantic decision,
a requirement amendment, an implementation plan, or a claim of runtime support.
The referenced diagnosis and environment/inject diagnosis were inspected from
this repository's Git objects at `077f7d04`; they are absent from this working
tree. No other repository was inspected.

## Boundary to preserve

An authorized external request may instantiate authored orchestration intent
without declaring its caller, affected users, or environment as participants.
Keep the following facts separately identified and evidenced:

| Fact | Existing owner and boundary |
| --- | --- |
| Authored inject and narrative placement | DSL-111: `Inject`, `Event`, `Script`, `Story`, `Node.injects`, compiler `InjectRuntime` and orchestration `InjectBinding`. Declaration or plan installation does not establish execution. |
| Accepted external request and operation | API-404/ADR-104: authenticated actor, admitted target/run, immutable request commitment, operation lifecycle and scoped retry claim. Acceptance is not an effect. |
| Actual world-effect occurrence | General orchestration must bind the authored intent to a fresh occurrence, concrete target selection and validated backend outcome. The missing portable trigger contract belongs at this boundary. |
| Optional participant disclosure, delivery and observation | DSL-142, SEM-226/230/233 and API-423/RUN-319 retain their separate policies, occurrences and evidence. World effects do not grant disclosure permission. |
| Actual direction/intervention | ACT-617/API-409/RUN-310 and ADR-110 retain exact control-application authority. Affecting a participant's environment does not by itself change participant control. |

Reuse the existing inject authoring. `Inject.from_entity`/`to_entities` name
entities, not authenticated principals, runtime nodes or participant controllers;
both endpoints may be absent. A researcher's input that changes an authored
approval condition can be a world effect. It is not automatically API-409
approval of a participant proposal. Conversely, labeling a real participant
direction as an environment inject must not evade its control/flow gates.
ADR-109 likewise keeps entity affiliation, participant identity and objective
assignment separate; entity endpoints do not select a participant audience.

Use the current normative `specs/sdl/sections.md`, `references.md` and
`document-model.md` alongside the published schemas. Some explanatory examples
still use `from-entity`/`start-time`, and the validation summary still calls
event preconditions conditions. Strict source syntax uses `from_entity` and
`start_time`; `Event.assertions` references precondition assertions and rejects
legacy `conditions`. Reuse `orchestration/_durations.py` (including its rounding
to whole seconds) and existing window analysis. Neither compiler dependencies
nor plan `startup_order` establishes live occurrence order or a new clock.

### Confirmed gaps that constrain the decision

Package paths below are relative to `implementations/python/packages/`.

- `raes_backend_protocols/protocols.py::Orchestrator` exposes plan
  start/status/results/history/stop, not a portable per-inject invocation.
  `raes_reference_backend/orchestrator.py::start` marks inject resources bound
  and narrative resources queued. Its successful `ApplyResult` establishes
  that boundary only. Neither `supports_inject_bindings` nor a supported
  `injects` section establishes external execution support.
- `raes_runtime/participant_control_effects.py::_submit` sends an API-424
  inject effect to `deliver_participant_directed_view`. Its owner binding
  compares participant/episode/view/cut/projection coordinates; it does not
  execute the authored source or establish a new world occurrence.
  `ControlInjectEffectModel` is deliberately participant-specific. Making
  participant fields optional would not repair the missing general path.
- `ParticipantInjectOccurrenceAnchor` currently requires event, script and
  story references. Those identify a narrative placement, not successive live
  firings. General events can exist without scripts/stories. The decision must
  explain an external occurrence with no schedule and its optional delivery
  join; do not fabricate a story or silently reinterpret the old anchor.
- [ADR-110](../../decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md)
  and [MC-09](../../../specs/formal/participant-semantics/reusable-mixed-control.md#mc-09--participant-directed-injects)
  define reusable control/delivery joins, while current models retain the
  legacy fixed-coordinate form. The new decision must compose that accepted
  semantic boundary and explicitly identify executable adoption still needed.
- `control_plane_execution.py::_commit_operation_result` currently maps the
  backend's success boolean to `SUCCEEDED`/`FAILED`; backend exception and
  contract-failure helpers return unsuccessful results with the predecessor
  snapshot. Reusing that path alone cannot distinguish an absent effect from
  an unknown one. Carry the invocation/evidence distinction through the shared
  lifecycle owner under ADR-104; do not infer safe retry from `FAILED`.
- `control_plane_operation_context.py::_value_free_request_payload` and
  `control_plane_store_payloads.py::_entry_payloads` currently special-case
  account-placement credentials. Their names do not promise generic inject
  payload redaction. A new carrier must be safe by construction or explicitly
  covered at the existing commitment, snapshot, diagnostic and retry owners;
  a raw-payload digest is not a safe substitute for a secret reference.

### DSL-142 adoption boundary

The [original #797 preflight](../../decisions/issue-797-dsl-142-participant-inject-delivery-preflight.md)
describes the shipped fixed-coordinate form. Its equal policy-revision,
destination-controller and fixed-order guidance must not be applied to the
ADR-110 form. Retain those checks for legacy readers; the
[migration contract](../../migration/reusable-mixed-control.md) requires an
explicit interpretation boundary, not deletion of inconvenient validators.
No additional ADR is needed to re-decide these accepted participant semantics.
Issue #1353 still needs its own accepted external-execution decision.

| Inspected incumbent | Constraint on adoption |
| --- | --- |
| `raes/participant_inject_delivery.py::ParticipantInjectDelivery` and `raes_processor/compiler/participant_inject_deliveries.py` carry declaration-time control coordinates. | Keep the participant-local binding and typed compiler metadata; reusable edge constraints cannot substitute for an actual accepted occurrence identity/revision, exact typed target or episode. A compiler dependency is not a runtime permission. |
| `raes/validator/_participant_inject_deliveries.py::_verify_delivery_control_identity` requires equal control/delivery revision strings and the destination-state controller/scope. | For the explicit new form, independently pin both policies and resolve the acting source controller and non-widening scope against the accepted application. Only a separately authorized handoff changes controller identity. Preserve legacy equality/destination rules under their old interpretation. |
| `_verify_delivery_control_time` compares `(control_effective_order, 0)` directly with temporal ticks. | The new form must use the admitted shared-time mapping, clock/domain/segment and actual cut, with a separately valid delivery window. Matching integers do not establish a mapping. |
| `raes_contracts/contracts/participant_control_validation.py::_declaration_agrees` still matches fixed occurrence coordinates to a declaration. | Adoption crosses ACT-617/API-409/RUN-310 as well as DSL-142. An SDL-only relaxation cannot make repeated applications valid at the portable occurrence and runtime readers. Keep exact contextual occurrence validation in its existing owner. |
| `raes_contracts/contracts/participant_control_resolution.py::_validate_inject` checks the authored-binding digest and directly compares reference strings, including `participant_address` against `participant_ref`. | Reuse the trusted non-wire `inject_deliveries` context, but explicitly resolve authored refs through compiler indexes before canonical joins. Neither a field name nor a binding digest proves an exact accepted control occurrence or one-time delivery consumption. Preserve the authored digest and compiled-address association; do not rewrite refs inside the hashed source object to make strings equal. |

The new directed-application join must retain independently named control-state,
control-occurrence, target, policy and snapshot/history revisions. Do not copy
one counter into another. Direction targets proposal/action/control; intervention
targets action/control/attempt, constrained by the permitted edge. A rejected,
future, stale, self-referential, cross-participant or cross-episode occurrence
cannot authorize delivery. Resolve eligibility from trusted owner state, never
from a client-supplied accepted flag, target index or latest matching edge.

Delivery uniqueness is an additional invariant to operation-key deduplication:
claim the exact occurrence/binding pair through the existing authoritative store
and atomic crossing/history/receipt boundaries. Different caller keys and
concurrent workers must not obtain two logical deliveries. Specify reservation,
emission and evidence settlement so a lost acknowledgment or crash cannot free
an uncertain claim for blind redispatch. An exact receipt retry is an authorized
historical lookup; any still-pending emission must pass current delivery gates.
No retry advances control state, renews authority, or re-executes the world effect.

## Questions the accepted contract must settle

These are semantic obligations, not a sequence of implementation tasks.

**Binding and payload.** Bind the exact admitted scenario/plan revision,
canonical inject address, run, target and selected concrete binding(s).
Authored roles and entity names are not unique physical targets: node counts,
module aliases and reuse can yield multiple realizations. Specify whether a
request selects one binding, an explicit set, or a declared fan-out; unresolved,
ambiguous, stale and cross-run bindings fail closed. An external caller may
select only within admitted intent, not replace source artifacts, overwrite
the plan, expand target scope or upload executable SDL through a trigger.
Define whether an event is invoked as a whole or an inject is selected within
it, including which event assertions and schedule constraints remain binding.
Reuse proposition/assertion evaluation; unknown or unsupported preconditions
cannot be promoted to true, and an inject selector cannot bypass them.
`Inject.source` is optional and a source selector may use version `*`.
Preserve that authoring compatibility while requiring an admitted realization
and its resolved artifact/input commitment for execution. A descriptive inject
with no executable realization must be explicitly unsupported, never a successful
no-op; retry must not re-resolve a floating selector to different content.

Separate static `Source` identity, runtime input, derived result and optional
disclosed item. State the allowed input shape, size, media/schema version,
integrity/provenance and binding to author-permitted parameters. Prefer existing
artifact and typed reference carriers where sufficient. An artifact name or
digest alone is neither permission to execute nor proof that its contents were
used. Do not add an untyped payload/config bag or silently assign shell/env
semantics to `Inject.environment: list[str]`. Reference resolution must be
trusted and scoped; a caller-supplied path, URL or callback address must not
become arbitrary file access, credential forwarding or network access.

**Occurrence, retry and order.** Keep authored identity, narrative placement,
logical effect occurrence, operation, backend attempt, participant delivery
and observation identities distinct. A repeat is a fresh admitted occurrence;
a retry preserves the existing occurrence and request commitment. Use
`control_plane_store.py::require_idempotency_key` and
`idempotency_claim_identity`: the existing key is `(actor, operation kind,
client key)` within one target/run store. Changed bindings, payload or intent
under a retained key conflict. Define occurrence uniqueness independently so
changing a retry key cannot execute an already claimed occurrence again.
Authenticate and authorize receipt access before resolving an exact retry;
receipt retrieval must not demand that the original effect be newly admissible.
Keep conflicting callers from claiming or inspecting another actor's work.

Specify the trusted ordering authority, ordering scope, expected state/cut,
predecessors and admission/dispatch boundary. External and scheduled firings
need one explicit relationship; neither arrival time, UUID sorting, list order
nor lock acquisition implicitly defines narrative order. Use existing shared
time domains, clocks, segments, ticks/microsteps and mappings for temporal
constraints. Order counters are not clocks. Define late/out-of-order inputs,
expired requests and competing firings without silently rebasing stale inputs,
resetting budgets or selecting the latest matching declaration. Disambiguate
one logical occurrence with several targets from several occurrences; define
per-target evidence and partial outcomes without promising atomic world effects.

**Admission, refusal and settlement.** Follow
[ADR-104](../../decisions/adrs/adr-104-runtime-control-plane-architecture.md) and its
[supervision contract](../../../specs/formal/runtime-control-plane/supervision.md).
Requirements, declared capability, installed invokable protocol, contextual
backend willingness and outcome evidence are different checks. Revalidate
authority, target/state revisions, preconditions, budgets and willingness after
queueing and before dispatch. Explicitly distinguish pre-claim denial,
withdrawal before dispatch, backend refusal, execution failure, known partial
effects and unknown effects, using the existing operation-state vocabulary
and stable diagnostics. Unsupported backends must refuse honestly; no fallback
to status-view delivery, successful no-op or weaker semantics.

Retain the existing claim/write-ahead-running/atomic-terminal-commit boundaries.
The store owns authoritative state and append-only history, with derived indexes
reconstructible at a known revision. Reuse lease ownership, revision CAS,
immutable actor context and scoped recovery; add no inject receipt database.
Success needs an outcome tied to the exact occurrence, admitted target and
payload/source commitment, backend invocation and required observation/readback
basis. Queued status, a boolean, a control acceptance or a nonempty evidence ref
is insufficient. Preserve required evidence versus produced evidence, and
operational outcome evidence versus selected archival experiment capture.

Rejected backend results protect portable state but do not prove the world
was unchanged. A disconnect, timeout, exception or crash after dispatch may
leave an indeterminate effect; recovery observes/reconciles without blindly
reinvoking it. Preserve immutable terminal results and link later evidence or
resolution. Local deduplication/CAS does not provide exactly-once remote effects.
Current external calls still hold the logical mutation permit: realization must
honor the accepted supervision separation of short state mutation from retained
effect reservation, bounded control capacity and execution-generation checks.
Neither a thread nor deadline expiry proves cessation or permits a conflicting
effect. Reuse this shared design; do not solve supervision inside an inject-only
worker or claim the accepted design is already implemented.

**Participant joins.** No-participant runs must succeed through general
orchestration without an episode or participant runtime. Explicit disclosure
adds participant/episode/audience and policy requirements only at its boundary.
Direction/intervention additionally joins the exact accepted API-409 occurrence,
acting source controller, permitted typed target, authority scope and validity
under ADR-110. A policy edge or latest matching event is insufficient; operator
authentication is not controller authority. Delivery/control policy pins remain
independent; disclosure/flow/time are revalidated at the delivery cut.

Use `ParticipantControlValidationContext.inject_deliveries`, authored-binding
identity/digest, API-423 crossing stages and realized exposure/evidence owners.
MC-09 allows at most one logical delivery per control-occurrence/binding pair,
with independent fan-out bindings. API-424 inject effects require a fresh
orchestration occurrence and produced result; ordinary disclosure may preserve
source/result identity where already allowed. Neither rule proves world effect
execution. Define causal prerequisites and outcomes separately: optional failed
delivery cannot erase an applied world effect, while required predecessor
delivery must withhold dependent progress. Retrying delivery must not refire
the world effect, and emission/delivery must not assert participant observation.
An applied world effect cannot make a failed required delivery count as success
of the composed operation; retain both outcomes.

Reuse `participant_retrieval.py::deliver_participant_directed_view`,
`participant_crossing_egress.py` and `participant_flow_sink.py` only for their
existing delivery/projection responsibilities. Select participant/episode and
the final sink explicitly; do not silently use the current episode for an old
binding. Initial authoring checks are not live disclosure authorization:
`_verify_delivery_observation` checks an allowed disposition and matching policy
basis separately over overlapping rules. At the effective cut, visibility and
its basis must agree for the same resolved item and permitted operation; aliases
or overlapping rules cannot combine unrelated permissions. Preserve deny-first
flow, transformation/provenance and authenticated audience checks at final egress.

## Cross-cutting layers and canonical incumbents

These are gates the intended design must pass, including in-process and stored
readers; a validated HTTP DTO alone is insufficient.

| Layer / incumbent | Required use and guardrail |
| --- | --- |
| SDL ingress: `raes/_yaml_loader.py`, `_source_profile.py`, `_source_validation.py`, `SDLModel`, `instantiate_scenario`, `admit_instantiated_scenario` | Preserve bounded inert YAML, duplicate/canonical-key, alias/depth/tag and closed-shape checks. Do not dereference trigger payloads or execute injects during parsing/instantiation; existing governed module resolution keeps its own boundary. Reuse existing phase boundaries. |
| Normative contracts: `specs/authority/authority-boundary.yaml`, `contracts/schemas/`, `raes_contracts`, `schema_bundle()` | Published schemas and specs own portable meaning; Python consumes it. Reuse existing scenario, plan, operation and snapshot carriers rather than HTTP-only copies. `ContractModel` forbids extra fields but does not make integer fields strict or provide ingress depth limits: select those constraints explicitly. A new operation kind must agree with `operation_lifecycle.py`, audit, stored readers, recovery and published consumers. |
| Reference semantics and compilation: `raes/validator/_sections.py`, `_participant_inject_deliveries.py`, `raes/composition/_behavior.py`, `_language_metadata.py`, `build_declaration_index()`, `raes_processor/compiler/orchestration.py`, `addresses.py`, `participant_inject_deliveries.py` | Resolve existing canonical identities, source/destination pairing, narrative membership, concrete bindings and participant-local policy refs through their owners. Rewrite every new nested ref during composition and re-admit after variable substitution. Local models check shape; contextual validators check graph/cut agreement; transport handlers must not duplicate either. |
| Request ingress: `raes_contracts/json_ingress.py::parse_bounded_json_object`, `ContractModel`, `control_plane_api_guards.py`, API `_offload.py` | Use byte/depth limits and duplicate-member/nonfinite rejection before parsing loses ambiguity; closed typed shapes, exact integer coordinates and bounded queues. Apply the same semantic validation to HTTP, embedder calls, backend replies and persistence reads. Do not bypass this with a permissive FastAPI body model. |
| Authentication and authorization: `ControlPlaneSecurityConfig`, API `_auth.py`, `control_plane_operation_context.py`, `control_plane_plan_authorization.py` | Preserve fail-closed bearer/proxy behavior, immutable principal, mutation roles, exact target/run and admitted-plan binding. P0/P1 embedders provide trusted actor context; P2 derives it from authentication. Add no public unscoped trigger route. Trusted proxies strip caller identity headers and deployments protect credentials in transit. Receipt access is separately authorized; audit-only roles cannot trigger. |
| Participant security, when selected: `participant_crossing_policy.py`, `participant_crossing_boundary.py`, `participant_control_mediation.py` and final-sink flow validation | Keep control-subject and audience bindings independent, exact episode/control/cut checks, deny-first projection, markings/provenance and final egress gates. Do not expose administrative snapshots/status to a participant-only client. General orchestration does not inherit participant authority. |
| Configuration and capabilities: `ControlPlaneConfiguration`, `ControlPlaneProfile`, `RuntimeTarget`, `registry.py`/`registry_target_validation.py`, `OrchestratorCapabilities`, backend manifest models and `planner/manifest_validation.py` | Preserve normalized run scope, profile/store agreement, supported-contract/vocabulary validation and invokable method signatures. New trigger support must agree across manifest, installed protocol and admission, rather than borrowing the old inject-binding boolean. Retain an optional participant component. |
| Artifact, secret and environment inputs: `raes/_source.py`, associated-artifact/trust contracts, `raes_contracts/secret_references.py`, `raes/runtime_environment.py`, `_stateful_resource_references.py`, `compiler/stateful_resources.py` | Reuse governed artifact identity/trust and safe logical secret refs. Operator secret values stay out of SDL, request commitments, snapshots and evidence. Actual runtime env bindings use `RuntimeEnvironmentVariable`/`RuntimeEnvironmentFile`, unique names, classification/redaction and `value`/`value_from` exclusions, not a second env-map grammar or the inject's opaque string list. |
| Host/process boundary: e.g. `raes_reference_backend/drivers/oci.py::_invoke` | Backend realization owns process invocation and containment. Reuse the injected runner, fixed argv, bounded timeout and coarse native-error translation pattern; it is not itself an inject executor or a secret transport. Existing source/env declarations grant no shell execution. Keep credentials and sensitive payloads out of argv, URLs, shell interpolation, process/env dumps and temporary artifacts; use admitted backend secret/input mechanisms with least-privilege target access. No new token CLI flag or portable shell runner is needed for this decision. |
| Backend boundary: `backend_input_contracts.py`, `backend_calls.py`, `backend_apply_results.py`, `backend_result_diagnostics.py` and ASR-532 result admission | Preserve isolated inputs/trusted predecessor, scope and identity checks, native contract/realization validation and safe egress before publication. Reuse validators at their owning boundary; extend only the absent trigger-specific relation. An invalid snapshot cannot certify effect absence. |
| Persistence and recovery: `control_plane_store.py`, `control_plane_execution.py`, `control_plane_durability.py`, local store/lease/path/codec/migration modules, `control_plane_recovery.py` | Keep one target/run per store, authoritative claims before effects, atomic terminal snapshot/record/actor audit, CAS and append-only history. Retain strict migration and replay checks and value-free versus ephemeral exact-retry commitments; do not persist secret hashes as a shortcut. P0 persistence and P3 coordination guarantees must not be implied. |
| Errors, audit and observability: existing `SDLParseError`/`SDLValidationError`/`SDLInstantiationError`, `Diagnostic`, `portable_diagnostic_payload`, API `_responses.py`/`_operation_routes.py`, `control_plane_audit.py` | Reuse stable redacted 4xx/5xx/conflict envelopes and bounded denial audit. Never return native exception text, Pydantic input echoes, payloads, paths or credentials. Audit detail keys, identifier grammar and numeric/size bounds are closed; extend the owning allowlist deliberately if necessary, rather than dumping a request into `details`. Reuse current logging/operation correlation and keep RUN-316 telemetry distinct from participant observations and experiment evidence. |
| Package and workflow boundaries: ADR-036, `tools/policy/adr_policy.yaml`, `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `.pre-commit-config.yaml` | Keep authoring in `raes`, compile/admission in `raes_processor`, orchestration/lifecycle in `raes_runtime`, portable DTOs in `raes_contracts`, and backend interfaces in `raes_backend_protocols`. Do not import runtime into SDL, processor or MCP, or concrete backends into shared runtime. CLI runtime access remains the explicit offline-maintenance exception. Reuse policy and verification commands, not an inject-specific workflow script. |

All identifiers/ranges must fit their consumers, including operation context,
audit, stored codecs and, only where joined, API-424 `ControlRef`/`ControlCount`.
Do not truncate identities, coerce booleans to revisions, wrap counters or loosen
an unrelated validator to make the new design fit. References/digests are not
automatically safe to disclose, and redacting a payload does not remove the need
to distinguish changed secret-bearing intent on retry.

## Publication, compatibility and extension seam

The issue's eventual decision belongs in the existing ADR/spec/requirement
authority surfaces. Publish an explicit disposition for
[DSL-111](../../requirements/DSL-111/requirement.md) and
[DSL-142](../../requirements/DSL-142/requirement.md), with narrative sections and
references kept consistent. Review API-402/403/404 and RUN-300/304 for portable
execution/history ownership; retain or amend ACT-617/API-409/RUN-310,
API-423/RUN-319 and SEM-235/API-424/RUN-320 explicitly at their joins. Reuse
shared-time API-421, backend-result ASR-532, and evidence/observability owners.
A design note must not become a duplicate requirement catalog or upgrade
existing ACTIVE status into proof of executable support.

Keep legacy declarations, fixed-coordinate participant bindings, queued/bound
snapshots and old receipts under their original meanings. Absence of a
participant binding stays environment-only; old receipts acquire no inferred
world-effect or observation evidence. Do not weaken current mandatory anchors
or add defaults that turn legacy plan installation into live triggering.
Any new semantic form needs explicit version/reader/capability admission and
historical migration rules; unsupported readers fail closed. Use ADR-009/061
schema authority, `schema_bundle()`, publication entries/change ledger and
`tools/check_generated_schemas.py` if executable carriers later change. Existing
ADRs remain governed by ADR-059 amendment/pin rules.
Discover all containing schemas, not just the two supplied traceability links:
at this baseline `Inject` also appears in `instantiated-scenario-snapshot-v1`,
`materialized-scenario-v1` and `scenario-satisfiability-evidence-v1`. Keep affected
publications, independent fixtures and generator parity consistent. A schema's
lineage suffix, publication stability and semantic revision are separate;
consult publication entries instead of assuming that `v1` means stable.

The extension seam is the **admitted authored binding to a versioned portable
invocation/outcome contract**, realized through the existing orchestrator/backend
boundary. Keep payload contract, selected target bindings, evidence requirements
and capability version explicit there. A second backend, repeated occurrence
or another optional audience should supply new admitted bindings/data, not
require a new inject syntax, provider-name switch or control-plane workflow.
Scheduling and external requests must share occurrence/admission semantics;
participant delivery composes by exact occurrence identity. Do not turn this
seam into an arbitrary plugin registry, scripting language or metadata policy.

For DSL-142 the corresponding seam is the existing keyed participant binding
plus a separately resolved application: semantic pin, edge constraint,
independent disclosure-policy pin, exact control occurrence/typed target,
participant/episode, audience, validity and evidence requirements. A second
cycle supplies fresh application coordinates; a second audience uses another
explicit binding. Neither variation edits the canonical inject or creates a
synthetic policy edge, new delivery service or alternate control workflow.

## Assurance and non-goals

The eventual stateful trigger/retry/outcome decision is FM3 under ADR-007:
require explicit invariants and an abstract state relation, with typed contract
and bounded property/differential evidence appropriate to the delivery scope.
Distinguish design witnesses from installed backend conformance. Reuse the
patterns in `test_sdl_models.py`, `test_sdl_validator.py`, `test_runtime_models.py`,
`test_runtime_planner.py`, `test_runtime_manager.py`, `test_sdl_realworld.py`,
`test_dsl_142_participant_inject_delivery.py`,
`test_issue_1351_mixed_control_design.py`, the `test_issue_1187_control_plane_*`
modules and `test_issue_1186_control_plane_recovery_operations.py`.
Use `test_api_409_participant_control_occurrences.py`,
`test_api_424_control_resolution.py` and
`test_issue_1069_participant_control_effects.py` for the existing contextual-join,
trusted-resolution, origin-principal and logical-effect deduplication patterns;
retain `test_sdl_catalog_parity.py` and the unchanged legacy delivery fixtures.
`test_runtime_orchestration.py` covers runtime orchestration-authority inventory;
it is not evidence of narrative inject execution.

Required counterexamples include no participants, researcher input without
control transfer, stale/ambiguous targets, unmet/unknown assertions, malformed
or secret-bearing payloads, exact retry versus changed input, two retry keys for
one occurrence, concurrent/scheduled firing, multi-target partial results,
refusal before/after claim, crash after effect before commit, late completion,
delivery denial after world success and observation without evidence. Contract
coverage must cross HTTP/core/store/backend boundaries, including unauthorized
receipt reads and error/audit leakage; a fabricated status view is no effect
probe. Enforce admitted work/history/payload bounds without truncating authority.
For directed delivery, include repeated use of one edge with distinct accepted
occurrences, unequal but valid policy revisions, source/destination controller
disagreement, unmapped order/time, duplicate occurrence/binding claims under
different operation keys, disclosure revoked before pending emission, overlapping
view rules, and old receipt lookup after episode termination. These must reach
the actual contextual validators and final sink, beyond the bounded #1351 model.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, repo policy,
requirement governance, semantic coverage and affected schema/catalog checks.
Set `RAES_REQUIREMENT_UID=DSL-142` for this participant-delivery preflight;
use DSL-111 for its orchestration-owned work and the governed scope for a joint
delivery. Keep requirement amendments and changed implementation/test traceability
explicit.
`tools/policy/requirement_order.yaml` permits this note under `docs/explain/sdl`
but gives neither DSL UID general ownership of shared runtime/store code. An
eventual delivery crossing those owners must use the existing governed
[multi-requirement scope](../../governance/requirement-scopes/README.md), with
the affected owners and exact file coverage; do not evade the gate by calling
all runtime work an SDL change or widening the phase wholesale.
Scope membership does not expand an owner's allowed roots; uncovered paths
still need an explicit governed ownership disposition.
Run only targeted local checks; full/integration/fuzz suites belong to CI.
Release automation owns changelog/version files.

Non-goals: implementing the trigger or backend, participant arrival/registration,
new controller kinds, mandatory participants, a second scheduler/workflow engine,
duplicate schemas or exception hierarchies, multi-tenant/P3 coordination,
automatic replay/resumption, universal rollback or exactly-once external effects.
Concrete backend artifact execution, credentials, cancellation/cessation and
readback remain backend responsibilities driven and admitted by the shared
runtime; this preflight does not move orchestration out of RAE.
