# Participant Backend-Facing Contracts

This document is the issue #76 formal design artifact for the joint
backend-facing participant contract surface:

- `API-405` - Participant Capability Declaration (ACTIVE; ratified here)
- `API-406` - Backend-Facing Participant Plain-Data Contracts
- `API-407` - Participant Feature Support And Constraint Declaration
- `API-408` - Participant Observation And Retrieval Contracts
- `API-411` - Participant Outcome Reporting Contracts

It is governed by ADR-060. Field *meanings* are defined by
`specs/formal/participant-semantics/` (ADR-022) and
`specs/formal/participant-runtime/` (ADR-054); this document binds shapes,
requiredness, and vocabularies. The research basis is
`docs/research/participant-backend-contracts/`.

Scope: this design publishes contract shapes. Runtime emission, endpoint
wiring, semantic validation beyond shape and vocabulary, conformance
execution, and tests against live traces belong to the per-UID implementation
issues (#200-#203). A schema published here is a settled shape, not a claim
that any backend produces it.

## Shared Base Envelope

Every carrier in the `participant-runtime` family embeds one shared base
envelope, defined once, with the ADR-054 `BaseEnvelope` fields: identity
(`event_id`, `schema_name`, `schema_version`, `event_type`,
`extension_policy`), optional classification and status
(`event_classification`, `source_status` — nullable only under the
`ClassificationClaim` rule in the participant-runtime spec), scoping
(`participant_address`, `episode_id`, `sequence_number` — null only for
run-scoped records), the three distinct timestamps (`occurred_at`,
`recorded_at`, `ingested_at`) with `clock_authority` and `temporal_context`,
ordering (`ordering_basis` from the closed `OrderingBasis` vocabulary,
`logical_order_ref`, `predecessor_event_refs`), actors and sources
(`actor_ref`, `producer_ref`, `source_system_ref`, `source_record_ref`,
`source_raw_ref`, `source_pipeline`, `raw_data_integrity`), confidence,
provenance and evidence references, and the marking surface
(`marking_definition_refs`, `object_marking_refs`, `markings`,
`granular_markings`, `redaction_policy_ref`, `authorization_scope`).

No carrier defines local identity, versioning, marking, or extension
semantics. All models are closed-world: unknown fields are rejected.

## API-406 - Plain-Data Carriers

| Contract id | Carries | Spec basis |
| --- | --- | --- |
| `participant-lifecycle-event-v1` | Action attempts and lifecycle boundary records: phase, phase realization, admission disposition, action/contract/command refs, actor provenance, action-validity basis, shared-state read/write refs, attribution-edge refs, outcome-interpretation refs, mapping loss (+ detail) | ADR-054 `LifecycleEnvelope`; SEM-208/211/212/215 |
| `participant-observation-envelope-v1` | Participant-visible observations: visibility projection, information guarantee, declared delivery point (`delivery_basis`, `delivery_point_ref`, `delivered_at`), evidence-scoped hidden/centralized state refs, loss descriptor, stochastic context, reconstruction refs | ADR-054 `ObservationEnvelope`; SEM-210 |
| `participant-shared-state-record-v1` | State-change reports: state address/scope/kind, revision, digest, predecessor revisions, conflict policy, visibility projection basis, provenance, value ref, embedded access records | ADR-054 `SharedStateRecord` + `SharedStateAccess`; RUN-307 |

State snapshots and histories are already carried by `runtime-snapshot-v1`,
`participant-episode-state-envelope-v1`, and the participant episode/behavior
history event streams; those carriers are ratified as the `API-406` snapshot
and history surface and are unchanged by this design. Operation records, step
signals, interaction contexts, joint actions, and time-management contexts
remain ADR-054 surfaces owned by the `RUN-30x` implementation issues; the
carriers above reference them and do not absorb them.

All enumerated fields use the closed vocabularies of the participant-runtime
spec exactly: `LifecyclePhase`, `PhaseRealization`, `AdmissionDisposition`,
`InformationGuarantee`, `OrderingBasis`, `ConflictPolicy`, `MappingLoss`,
`DeliveryBasis`. Divergence between a schema enum and the spec vocabulary is
a defect (PRT-19).

Invariants the carriers must keep expressible — and whose violation must not
be expressible as valid data:

- hidden world truth, scoring state, and centralized-training state appear
  only as evidence-scoped references, never as participant-visible payload
  (I2, SEM-210);
- values travel by reference or digest; credentials, prompts, hidden answer
  keys, and raw command output never appear inline (runtime-spec marking
  rules);
- a below-`exact` claim path always exists: every vocabulary carries its
  `unknown`/`unsupported` downgrades.

## API-405 - Capability Declaration (Ratified)

The `backend-manifest/v2` `capabilities.participant_runtime` block shipped by
PR #405 is the participant capability declaration surface: governed
participant roles, behavior features, and interaction features from
`controlled-vocabularies-v1`, the `x-<owner>:<term>` governed extension rule,
and the term-level evidence criteria in
`raes_backend_protocols.capabilities.PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS`.
This design ratifies that surface without amendment. See the API-405 section
of `specs/formal/runtime-contracts/README.md`.

### Portable autonomous execution services

Issue #898 extends only the `autonomous_execution` portion of the ratified
participant capability block. Autonomous support now includes relational
`execution_bindings`, the complete generation-fenced lifecycle action set,
bounded-concurrency support, and finite service/action capacity. The three
published carriers are:

| Contract id | Carries |
| --- | --- |
| `participant-execution-binding-v1` | Exact action contract, native target-service addresses, selected implementation, constraints/evidence, and finite execution policy |
| `participant-execution-control-v1` | Expected-generation `start`, `pause`, `resume`, bounded `drain`, `reset`, and `teardown` request |
| `participant-execution-service-state-v1` | Lifecycle, generation, health, readiness, admission/capacity, quiescence/resource release, shared-time provenance, pacing deviations, and evidence |

Control mutations reuse `operation-receipt-v1` and `operation-status-v1`; state
is embedded in `runtime-snapshot-v1.participant_execution_services`. These
carriers do not merge participant episode lifecycle, scheduler continuation,
or shared-clock state. Conditional live conformance is required because
schema-valid declarations cannot establish native action behavior. The shared
runtime does not manufacture lifecycle transitions: a backend-owned control
operation must coordinate those incumbent surfaces, and changed typed
readback plus new evidence must validate each successful operation.

## API-407 - Feature Support And Constraint Declaration

`capabilities.participant_runtime.feature_support` is a list of per-feature
support declarations:

```text
ParticipantFeatureSupport =
  feature
  support_level
  constraint_refs
  limitation_refs
  disclosure_refs
  evidence_refs
```

Rules:

- `feature` resolves to a governed behavior or interaction feature term, or a
  governed `x-<owner>:<term>` extension.
- `support_level` uses the ADR-054 guarantee-strength scale —
  `unsupported < disclosed_weak < bounded < exact` — published as the
  `participant-runtime-feature-support-levels` controlled vocabulary. No
  second support vocabulary exists.
- Absence of an entry makes no strength claim; it neither implies `exact` nor
  counts as `not_applicable`. Consumers needing a strength claim require an
  entry.
- A feature listed in the API-405 supported lists must not be declared
  `unsupported`; the contradiction fails validation.
- Any `support_level` below `exact` requires at least one disclosure
  reference; `constraint_refs` carry the constraint statements for
  `constrained`/partial realizations.
- Feature-support declarations cover the participant feature surface only.
  SEM-218 explicitness/realization declarations cover cross-domain
  realization handling; the manifest carries both, and they are never merged
  or inferred from one another.
- Evidence-required features include the six participant-policy features,
  `participant_predicate_opacity`, and the five issue #1004 adversarial-control
  apparatus/backend terms below. A positive declaration requires evidence;
  bounded support also requires constraints, limitations, and disclosures plus
  every contract in that feature's required-contract map. Opacity and the five
  adversarial-control terms are not policy operations and are deliberately
  absent from `PARTICIPANT_RUNTIME_POLICY_FEATURES`: they carry the full
  evidence discipline without claiming runtime enforcement, which the RUN-319
  final-sink boundary owns.

### Effective mixed support (issue #1355)

For a mixed participant action or staged transfer, a manifest strength entry
is a declaration to be joined with the admitted provider-local feature and
time capabilities, exact profile edge or transition, current authority and
final-sink policy, and installed executable services. The bridge, mapper,
time coordinator, and destination or participant readback must execute their
named obligations under the owning operation. A support entry, service method,
mapping reference, timestamp, or backend success flag alone cannot establish
delivery, observation, governed order, or native handoff. Missing bindings or
contradictory pre-effect support refuse before an external effect; missing
post-effect readback leaves the operation indeterminate without claiming the
unconfirmed stage.

The existing four support levels and separate constraint, limitation,
disclosure, and evidence references retain their meanings. A weaker admitted
mapping records its authorized loss and evidence only after correlated
execution; unknown or partial effects use the shared operation lifecycle,
not a new manifest support level. Shared time capabilities govern the named
clock mapping and comparison without requiring one physical clock or a
physical-OT timing guarantee. Installed bindings are trusted runtime inputs
against the sealed `sem-234/rev1` profile; this rule adds no manifest field,
support vocabulary term, or published carrier revision.

### Adversarial-control apparatus and backend support (issue #1004)

The following governed `participant-runtime-behavior-features` terms let a
backend or experiment apparatus declare bounded adversarial-control posture on
the single existing API-407 `feature_support` surface. Each maps to the exact
backend-facing published contract that carries its realized evidence; SEM-233
relation/profile authoring ids are never smuggled into backend support lists.

| Feature term | Declares | Required contract(s) |
| --- | --- | --- |
| `participant_boundary_flow_resolution` | SEM-233 two-coordinate boundary flow-label resolution and conservative provenance-preserving propagation | `participant-flow-control-relation-v1`, `participant-crossing-occurrence-v1` |
| `participant_final_sink_mediation` | RUN-319 fail-closed exact-cut permit immediately before an RAES-controlled external effect | `participant-flow-control-relation-v1`, `participant-crossing-occurrence-v1` |
| `participant_quarantined_processing` | bounded quarantine of unknown or untrusted source material | `participant-flow-control-relation-v1`, `participant-crossing-occurrence-v1` |
| `participant_processing_role_trust` | trusted/untrusted processing-role declaration bound to controller and authority state | `participant-control-occurrence-v1`, `participant-crossing-occurrence-v1` |
| `participant_monitor_topology` | monitor topology as bounded apparatus evidence | `experiment-evidence-record-v1` |

Each term requires the contract that *owns* its claimed realization — the
SEM-233 `participant-flow-control-relation-v1` (resolved by the RUN-319 runtime
at the final sink) for the flow, final-sink, and quarantine terms — not merely a
generic occurrence carrier. Supporting only `participant-crossing-occurrence-v1`
therefore cannot make an effective exact flow or sink claim. The authored
boundary-flow-policy profile stays out of backend support lists.

A declaration is never proof of realization, isolation, monitor independence,
non-collusion, flow propagation, or sink enforcement. Missing, contradictory,
or evidence-free declarations are deny-equivalent; a weakened claim never
retains the stronger effective level without an explicitly authorized downgrade
(policy plus provenance references). Distinct model or process identities are
not independence evidence, and a quarantine, gateway, sanitizer, or monitor is
never the sole enforcement point — the RUN-319 final-sink boundary must still
permit the exact effect. Backend realization of these terms remains
`not-established` in the ASR-536 evaluation program until conformance evidence
is bound to the exact `sem-233/rev1` profile.

## API-408 - Retrieval Projections

Retrieval contracts are read-shapes over recorded carriers — projections,
never a second source of truth. They live in the `control-plane` family:

| Contract id | Projects | Notes |
| --- | --- | --- |
| `participant-status-view-v1` | Episode state and lifecycle facts for one participant (+ open operation refs) | embeds the scope-projected episode-state shape |
| `participant-history-view-v1` | Episode and behavior history retrieval | carries `completeness` (`complete`/`truncated`/`filtered`) with a required basis when not complete |
| `participant-context-view-v1` | Derived operational context views | reference carrier plus SEM-214 meaning/comparability envelope; see below |

Views are one-participant projections, and the contract makes that structural:
`participant_address` and `episode_id` are carried exactly once, at the view
level, and the embedded episode-state and history-event records are
scope-projected variants of the recorded contracts with those fields removed.
A nested record scoped to another participant or episode is therefore
unrepresentable in a valid view payload — closed-world validation rejects any
embedded record that restates scope — rather than merely forbidden by prose.
The projected record shapes must track their recorded source contracts
field-for-field apart from the removed scope fields; divergence is a defect
(PRT-19).

The scope binding is recursive. Behavior events cite recorded semantic
records — action results and their precondition results, attribution edges,
outcome interpretations — that legitimately carry their own
`participant_address`/`episode_id` because they are recorded contracts, not
view projections. A valid history view requires every such nested scope field
to equal the view scope; a one-participant view cannot smuggle another
participant's or episode's records through nested semantic payloads. This is
a semantic-gate obligation (model-level validation with negative tests), not
a schema-shape rule.

Rules:

- every view names its `source_snapshot_ref`, `visibility_projection_ref`,
  and marking surface; visibility projection and marking/redaction
  enforcement run before publication (deny-first intersection per the
  participant-runtime spec);
- views carry no retrieval-only state: every field is derivable from recorded
  contracts;
- `participant-context-view-v1` carries the governed `view_ref`, the
  `derived_from_refs` provenance, an optional `payload_ref`, and the SEM-214
  meaning/comparability envelope. A context view must declare its
  `meaning_ref`, participant-local scope, audience scope, observation point,
  consumed source layers, transformation rule, evidence/provenance basis,
  semantic limitations, and comparability class/basis. Hidden/global source
  layers, future-state sources, participant-local state presented as
  audience-neutral, and weakened backend comparability claims without a
  disclosure are invalid;
- endpoint binding, authentication, role checks, request limits, audit
  recording, and error envelopes reuse the existing control-plane contract
  (API-403/404) and are implementation scope (#202).

## API-411 - Outcome Reports

`participant-outcome-report-v1` is a SEM-215 interpretation record:

```text
ParticipantOutcomeReport =
  BaseEnvelope
  outcome_id
  interpretation_rule_ref
  outcome_sources       # >= 1 of {source_kind: action_result |
                        #   episode_status | evidence, source_ref}
  state_relationships   # {relationship_kind: scenario_state |
                        #   workflow_state | objective_window |
                        #   evaluation_input, target_ref,
                        #   relationship_basis: declared | interpretation_rule}
```

Rules:

- every outcome grounds in its sources: an action result, a terminal
  participant-episode status, or evidence — matching the SEM-215 grounding
  discipline;
- the interpretation rule is named, always;
- relationships to scenario, workflow, objective, and evaluation state are
  explicit references with a declared basis; the report asserts the
  relationship, not the downstream result;
- the carrier has no score, reward, or objective-success field. Reward and
  return remain ADR-054 step signals; objective and evaluation results remain
  their own surfaces (I10).

## Publication, Generation, And Authority Obligations

- Carriers are generated from contract models (`raes_contracts`) into
  `contracts/schemas/participant-runtime/` and
  `contracts/schemas/control-plane/`; generated output is never hand-edited.
- `tools/generate_contract_schemas.py` routes the family explicitly; no
  contract id reaches a directory by fallthrough.
- Every contract id is registered in `schema_bundle()`,
  `contracts/schema-publication-manifest.json`, and — where claimable by a
  backend — `BACKEND_SUPPORTED_CONTRACT_IDS`. Re-binding the API-405
  term-level evidence sets to the new carriers is #201 scope.
- Every contract id has at least one valid and one invalid fixture under
  `contracts/fixtures/`.
- New declarable terms enter through `controlled-vocabularies-v1` (ADR-012);
  this design adds `participant-runtime-feature-support-levels`.

## Conformance Obligations For #200-#203

The per-UID implementation issues must, for their requirement's carriers:
emit them at the ADR-054 boundary points, validate them semantically (not
just shape), bind the API-405/407 evidence criteria to them, add negative
fixtures per the PRT probe rows, and prove the I2/I10/marking invariants with
leakage and separation tests. This document deliberately stops at the shape
boundary.
