# Issue #1368 — Directed inject occurrence integration preflight

Updated: 2026-10-21. Inspected base: `ae2bc6f14ec72cfccd7186fc4e86242a66971f7e`.
Contract: the supplied DSL-142 amendment and issue #1368 acceptance criteria,
building on #1364 and #1367. Existing working-tree implementation is draft
context, not conformance evidence. This is architecture guidance, not an
implementation plan. No runtime behavior or support claim changes here.

## Authority and boundaries

Retain [ADR-112](adrs/adr-112-external-inject-triggering-and-execution.md),
[ADR-110](adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md),
[MC-09](../../specs/formal/participant-semantics/reusable-mixed-control.md#mc-09--participant-directed-injects),
[ADR-104](adrs/adr-104-runtime-control-plane-architecture.md) and
[ADR-095](adrs/adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md).
The [#1367](issue-1367-external-inject-execution-preflight.md) and
[#1364](issue-1364-repeatable-control-cancellation-preflight.md) preflights cover
the incumbent execution and control owners. No new ADR or conceptual primitive
is needed. The issue's historical diagnosis was inspected from local Git at
`077f7d04:docs/research/runtime-refactor/environment-inject-diagnosis.md`;
that file is absent from the current tree. Its environment/participant
separation remains binding; its pre-implementation runtime observations are
historical.

| Authored meaning | Required runtime relation |
| --- | --- |
| General inject | Existing DSL-111 world admission/execution/outcome. No participant, episode, audience, controller or participant-runtime component is required. Affecting a participant does not itself change control authority. |
| Disclosure binding | Explicit recipient, episode, authored occurrence anchor, governed source/result, observation boundary, delivery policy, time and evidence. No API-409 authority or control fields. Disclosure of an existing item need not invent a new world effect. |
| External direction or intervention | The disclosure/delivery relation plus the exact accepted API-409 application of the authored transition, with kind, target, source controller, narrowed authority, policy pin, cut and validity agreement. A reusable permitted edge is not that application. |

Python paths below are relative to `implementations/python/packages/`.

## Incumbents and integration gaps

- `raes/participant_inject_delivery.py`,
  `validator/_participant_inject_deliveries.py` and
  `validator/_participant_inject_delivery_control.py` already own closed
  variants, reference/policy/evidence agreement and legacy-flat versus reusable
  nested-control exclusivity. `raes_processor/compiler/participant_inject_deliveries.py`
  and `compiler/_mixed_control_policy.py` own canonical addresses and typed
  projections. Reuse them; do not reinterpret raw `spec` dictionaries or copy
  hidden inject content into participant metadata. Current DSL-142 anchors
  require event/script/story: general independent/event placement does not
  silently create a compatible participant binding.
- `raes_runtime/control_plane_injects.py::submit_inject`, `inject_execution.py`,
  `inject_claims.py` and `inject_outcomes.py` own the world path. Build on
  `raes_contracts/contracts/inject_occurrence*.py` and their invocation,
  outcome and correlation validators. The world occurrence, operation,
  invocation, outcome digest and produced result must resolve from committed,
  authorized owner records. `get_inject_correlation()` only yields a successful
  produced-result join; absent, failed, partial or indeterminate world outcomes
  cannot be relabeled successful correlations. Retain their actual evidence
  without dispatching a success-dependent delivery.
- `participant_control_mediation.py`, `participant_control_request.py`,
  `participant_control_occurrences.py` and the mixed-control runtime owners
  supply application acceptance, actor-bound retry and state/history commits.
  `contracts/participant_control_validation.py` dispatches to the owning
  lineage validator, including `participant_control_occurrence_v2_validation.py`.
  Reuse that relation rather than a new direction/intervention interpreter.
- At the inspected base, `control_plane_configuration.py::_has_controlled_delivery()`
  rejects the reusable controlled-delivery composition.
  `contracts/participant_control_resolution.py::_validate_inject()` explicitly
  rejects a nested reusable control binding, including through v2 consumers.
  These are intentional unsupported-path guards. Narrow them only for the
  composition that can establish all joins and final-sink guarantees; retain
  refusal for unsupported backends, profiles, consumers and mixed-runtime paths.
  Compiler/planner admission, configuration, API-424 contextual validation and
  advertised feature support must agree; removing one refusal is insufficient.
  Installing a result-delivery owner does not by itself admit API-424-generated
  inject effects or every reusable-control plan. Keep installation conditional
  on the authored variant; general injects and control-only plans must not gain
  unrelated participant-delivery dependencies.
- `participant_retrieval.py::deliver_participant_directed_view()` is a public
  governed delivery of an already projected status carrier. It does not check
  a DSL-111 world occurrence or prove participant consumption. Merely calling
  it after world success does not satisfy #1368. Reuse its RUN-319 egress owner,
  `participant_crossing_mediation.py`, `participant_crossing_egress.py`,
  `participant_flow_sink.py` and `participant_control_orchestration.py` for the
  actual disclosed subject and audience. A status view cannot substitute for
  authored result content. Existing opacity egress stage synthesis is scoped
  to its own observation basis; it cannot prove arbitrary external observation.

## Joins, ordering and failure guardrails

Retain independently retrievable links among the pinned world occurrence and
outcome/result, compiled authored delivery and digest, disclosed projection,
recipient/episode, exact control event/revision when applicable, delivery
attempt/delivery and observed occurrence when evidenced. Keep delivery-policy
and control-policy pins independent; equal version strings prove no agreement.
Resolve authored references through compiler indexes before contextual joins;
namespaced addresses cannot be matched by suffix or guessed from dotted names.

For reusable direction/intervention, join the accepted occurrence's identity,
revision, policy/edge, participant/episode, source controller, scope, target,
evaluated state/history cut and validity evidence. Resolve canonical `self`
through the existing owner. Rejected, superseded, stale or wrong-episode facts
cannot authorize delivery. Never choose the latest event for an edge. Preserve
legacy fixed anchors and their original finite meaning; do not convert them
implicitly or mix occurrence lineages within an episode.

MC-09 consumes each `(control occurrence, participant binding)` at most once
for logical delivery. Reserve/consume it atomically through the existing store
and history-head CAS, with retained request commitment and result linkage.
An in-memory set, lookup-then-write or transport idempotency key alone cannot
enforce this across competitors, new keys and restart. Exact authorized retries
return the same retained identity; changed content conflicts. Fresh cycles use
fresh applications, never a replayed event schedule or refired world effect.
Explicit fan-out bindings are admitted and accounted for separately.
The pair constraint is independent of actor, client key, world operation,
snapshot revision and projection identity: changing any of these cannot consume
the same control application/binding again. Reuse `inject_claims.py` and the
store claim/restore validators for authoritative uniqueness, alongside
`participant_crossing_commit.py` and history CAS for delivery facts. A new
field on an operation record must survive codecs, migration/reconstruction,
lost-ack readback and every admitted store, including non-success reservations.

Use the admitted total-effective-order authority and shared-time owner. Order,
clock domain/segment/tick/microstep, history head, controller-state revision,
store revision and execution generation are separate coordinates. Reuse
`participant_control_validity_bounds()` and existing temporal resolution;
intersect applicable windows and revalidate delivery at its own live cut.
Stale requests refuse without rebasing. Recheck authority, episode, IFC,
audience, markings, transformation, capability and expiry at the final sink,
including after callbacks and parent resumption. Unknown truth fails closed.

World success, control acceptance, disclosure permission, delivery attempt,
acknowledged emission and observation each retain their own facts and failures.
Follow authored dependency ordering and API-424 predecessor rules; do not impose
one universal sequence or transactional rollback across external effects.
Required predecessor delivery keeps its parent withheld until evidenced and
revalidated. A failed delivery cannot erase accepted control or an applied world
effect; a failed control cannot manufacture a successful direction from world
success. Attempt/timeout/disconnect and successful serialization do not establish
external consumption. Record observation only at an explicitly supported
observation boundary with owner evidence. Unknown effects/cessation remain
indeterminate with retained exclusions; later evidence appends linkage and never
rewrites history or grants redispatch. Keep world terminal settlement separate
from later participant/control operations and their atomic commits.

Required delivery is an obligation of the composed operation and its dependents,
not a reason to relabel the settled world outcome. Reuse
`participant_control_orchestration.py`, `participant_control_effects.py`,
`participant_control_receipts.py` and `participant_control_causal_state.py` for
predecessor blockers, owner claims, originating authority and retained budgets.
A standalone delivery endpoint plus a successful world receipt does not connect
that obligation to dependent progress. Required-predecessor effects withhold
their parent; they are not ordinary subsequent effects dispatched by a drain.

For schedule-free composition, the compatibility contract requires an explicit
versioned join and reader/capability agreement. Supporting general independent
world triggers while refusing their participant join is a valid refusal, but
does not satisfy that part of DSL-142. Neither matching legacy anchors nor a new
delivery DTO alone supplies the missing occurrence semantics. Retain legacy
anchor validation until the separately discriminated join is admitted.

## Cross-cutting admission surface

| Layer and canonical incumbents | Required satisfaction |
| --- | --- |
| Authoring and compiled intent | `raes/parser.py`, `_yaml_loader.py`, reference-purpose validators, DSL-142 validators and compiler indexes retain bounded safe YAML, duplicate checks, closed fields and scoped references. Revalidate direct/model inputs; source text and raw dictionaries confer no execution authority. Preserve flat/nested exclusivity and disclosure-only absence of control fields. |
| Wire, schemas and contextual validation | `raes_contracts/json_ingress.py::parse_bounded_json_object`, `OperationContractModel`, `ParticipantRuntimeBaseEnvelopeModel` and shared strict control coordinates own bounds and shape. Count HTTP bytes before decoding; reject duplicate keys, nonfinite values, excess depth, unknown fields and bool/string integer coordinates where strict coordinates apply. Apply owning model and cross-record validators to HTTP, direct calls, resolved artifacts and restored records. Use the intersection of selected consumers' reference/range limits: API-424 counts cap at 1,000,000, and control-subject bindings reject `:` even though `ControlRef` permits it. JSON Schema and `x-raes-invariants` alone do not execute contextual joins. |
| Authentication, authorization and disclosure | `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, composition seals and target/run-bound admission remain authoritative. World operator authority, `ParticipantControlSubjectBinding` and `ParticipantAudienceSubjectBinding` are independent permissions. Check current receipt/readback authorization before retry/conflict lookup or result/artifact disclosure; unknown/unauthorized readback stays indistinguishable. An exact receipt read does not reevaluate historical acceptance at today's cut or authorize fresh emission. Fresh/pending emission requires live semantic authority and disclosure gates. P0/P1 trust the embedder; never launder participant work through `identity=None` or a drain identity. |
| Configuration and support | `ControlPlaneOptions`, `ControlPlaneConfiguration`, `OperationSupervisionConfiguration`, profile selection, `MixedControlRuntimeBinding`, compiler-context equality, resolver/provider call-shape checks, `manifest_authority.py` and `participant_crossing_policy.py` own installation and capability admission. Retain normalized run scopes, finite bounded budgets and unsupported-path guards. Backend declarations, installed methods, willingness and evidenced realization are separate. No new registry or implicit feature upgrade; P0 is process-local, P1/P2 durability depends on the admitted store. |
| Artifact, secret and environment shapes | Reuse admitted artifact/provenance resolution, `OperationEvidenceResolver`, `raes_contracts/secret_references.py`, `runtime_fact_binding_policy.py`, `raes/runtime_generated_value.py` and `raes/runtime_values.py::enforce_observed_value_redaction`. A content digest proves neither trust nor disclosure permission. Disclose only the governed result, never source body, hidden world readback or arbitrary evidence. Embedded correlation references, application coordinates and digests also pass the disclosure projection; internal correlation does not authorize their publication. `Inject.environment` stays a string list; `raes/runtime_environment.py::RuntimeEnvironmentVariable` retains name checks, literal/`value_from` exclusivity, provenance and redacted/operator-secret omission. Existing account redaction does not sanitize arbitrary inject content or commitments. |
| Mutation, execution and persistence | `RuntimeMutationAuthority`, `external_call()`, `LocalExecutionAdapter`, `InvocationLedger`, `ControlPlaneStore`, `control_plane_durability.py`, crossing/control commit helpers and strict record/snapshot codecs retain one writer, bounded capacity/deadlines, one-use dispatch, generation fences, append-only history and atomic actor-bound state/audit/claim publication. Resolver/provider calls run outside state permits, subordinate locks and transactions; compare the complete cut on return. Extend existing memory/SQLite/PostgreSQL owners consistently where affected, including reopen/migrations, lost-ack poisoning and replay. Never hide authoritative correlation or consumption in unvalidated `result_payload`/metadata or a side store. |
| Final results and participants | World invocation/outcome/correlation validators and existing native result admission remain intact; #1367 currently admits artifact-only inject results and refuses native residual snapshots. Participant delivery additionally passes API-423 crossing, SEM-230/233 IFC, API-424 composition and ADR-095/SEM-226 final-sink/time checks. Use the trusted non-wire `ParticipantControlValidationContext.inject_deliveries` seam with original authored-binding digest and owner-resolved canonical coordinates/cut/projection. Reuse decision-surface delivery resolution where that carrier applies; do not coerce unrelated results into it. |
| Capture and observation evidence | `observation_admission.py`, `observation_execution.py`, `observation_results.py` and `raes_contracts/observation_lifecycle.py` own admitted apparatus capture and retention. Capture obligations come from effective authored demand, not merely the existence of an inject or delivery binding. World readback, successful capture/retention, governed emission and participant observation have separate subjects and evidence. Check the configured `observation_boundary_ref` and evidence requirements through those owners; copying required reference names or synthesizing crossing stages proves neither acknowledgement nor consumption. Returning a carrier can establish only its explicitly admitted local boundary. |
| Errors, audit and observability | Reuse `Diagnostic`, `portable_diagnostic_payload()`, terminal diagnostics, `AuditEvent`, `control_plane_audit.py` closed detail keys and `control_plane_api/_responses.py` redacted conflict/validation/internal envelopes. Preserve bounded denial audit, fixed logger labels, disclosure-safe errors and `Cache-Control: no-store`. No raw exception/Pydantic input echoes, payloads, native stdout/stderr or provider locators in errors/logs/audit. ADR-066 separates operational telemetry, participant disclosure and experiment evidence. No duplicate exception or logging hierarchy. |
| Host/OS and transports | Preserve the existing P2 host/service boundary: TLS/proxy trust, stripped identity headers, counted bodies, bounded offload/control capacity, worker/profile checks, leases and private database/sidecar ownership/permissions. Native adapters own target lookup, argv/environment validation including NUL rejection, fixed executables, bounded output and protected secret channels. Portable IDs are not paths, shell fragments or resource selectors. No credentials or sensitive inject content in argv, URLs, shell interpolation, environment dumps or engine history. No new subprocess, transport, credential loader, hosting or external processing is needed. |
| Publication and workflow | ADR-009/061/075, `schema_bundle()`, `tools/check_generated_schemas.py`, `tools/check_schema_publication.py`, `tools/check_schema_coverage.py`, `contracts/schema-publication/entries/`, facade/corpus packaging, `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/` and canonical nox lanes govern affected artifacts. Evolve an owning closed/versioned carrier only where necessary; align embedded snapshot definitions, codecs, fixtures and per-contract content hashes. An exported DTO, generated OpenAPI schema or `schema_bundle()` entry alone is not publication. Preserve historical readers and unknown-lineage refusal. Set `RAES_REQUIREMENT_UID=DSL-142` on this branch, which lacks a requirement UID. No accepted-ADR edits, release-owned version/changelog edits or new workflow machinery. |

## Extension seam, evidence bar and non-goals

The seam is the existing trusted owner resolution parameterized by compiled
delivery binding/digest, world occurrence/outcome pin, participant/episode,
optional exact control application and live cut. Repeated cycles change those
occurrence coordinates, not the policy or interpreter. Backends vary through
installed typed resolvers/providers and admitted capabilities; fan-out varies
through explicit bindings. Observation basis, supported content projection and
scheduled versus schedule-free joins belong to their owning versioned contracts
and installed capability seams; do not hardwire them to HTTP return, plain text,
clock segment zero or one backend. Unsupported variations refuse explicitly;
they do not relax existing time or evidence gates. Missing portable data evolves
its owning versioned contract rather than adding an open metadata/context bag,
second DTO or copied validation switch. Do not require API-424 provider installation for every
ordinary authored disclosure when its incumbent gates suffice.

Implementation evidence must exercise the public runtime using the existing
`test_issue_1367_{inject_execution,inject_claims,inject_http}.py`,
`test_issue_1364_{reusable_runtime,control_history,http}.py`,
`test_dsl_142_participant_inject_delivery.py`, API-423 crossing and API-424 effect
fixtures as incumbents. Cover ordinary disclosure without control, repeated
direction/intervention, exact retry and competing consumption, independent
policy revisions, namespaced anchors, stale/wrong-kind/episode/target bindings,
unauthorized audience versus controller, expired windows, participant-free
triggers and each partial-failure boundary. Reopen and lost-ack cases must prove
retained joins without redispatch or invented observation. HTTP tests must
exercise strict ingress, errors and authorized readback. Parser/model fixtures,
accepted provider requests and returned status views alone cannot prove these
outcomes. Include competing actors/keys/world occurrences for one control pair,
capture failure after an applied effect, required-delivery dependent withholding,
post-transformation disclosure checks, reset/unmapped clock refusal, and explicit
schedule-free reader support or its documented coverage gap. Local checks stay
targeted; full/integration/fuzz suites belong in CI.

Non-goals: implementation in this preflight; a new arrival/registration protocol,
controller type, delivery service, workflow engine, policy language, clock,
generic outcome enum, universal rollback or exactly-once external effects.
Do not require participants for world execution, equate an inject sender with
the acting controller, treat direction as approval, expand artifact-only native
execution silently, unroll reusable edges, select latest events, or bypass IFC,
capability refusals, immutable history and ownership boundaries to make a path
appear supported.
