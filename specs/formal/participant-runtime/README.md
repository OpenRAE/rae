# Participant Runtime Formal Design

This document is the issue #74 formal design artifact for:

- `RUN-305` - Participant Runtime State And History
- `RUN-306` - Participant Decision And Execution Lifecycle
- `RUN-307` - Shared Operational State Model
- `RUN-308` - Concurrent Participant Execution

It is the normative design artifact for the participant-runtime family. Its
original design status does not mean the family is wholly unimplemented:
bounded per-UID slices now exist in contracts, processor/runtime helpers,
backend capability declarations, conformance checks, and tests. The remaining
boundaries below state what those slices do not establish.

Enum blocks use formal names. Implementation schemas should publish a single
wire spelling and document the mapping; the intended wire spelling is lowercase
snake_case unless an existing RAES contract family requires a different style.

## Current Sufficiency Finding

The existing implementation provides bounded `RUN-305` through `RUN-308`
slices, but is not sufficient for the complete participant-runtime family.

What exists:

- ADR-013 and the participant episode contracts define episode identity,
  initialize, reset, restart, terminate, terminal reason, and append-only
  episode history.
- ADR-022 and `specs/formal/participant-semantics/` define participant action,
  observation, visibility, failure, temporal, attribution, interaction, and
  outcome semantics.
- `ParticipantBehaviorHistoryEvent` records action attempts, state
  transitions, observations, joint action set ids, realized order,
  interaction class, shared-state refs, temporal contexts, attribution edges,
  and outcome interpretations.
- `RuntimeSnapshot` carries participant episode state/history and behavior
  history as plain-data runtime surfaces.
- ADR-041 and the `participant-implementation-manifest-v1` /
  `participant-implementation-provenance-v1` contracts define the apparatus
  identity, selected decision surface, participant contract versions, and
  exposure-policy evidence for participant implementations used in a run.
- Backend manifests can declare participant runtime roles, behavior features,
  interaction features, and required evidence contracts.
- The bounded RUN-305 runtime state/history slice has contract, schema,
  semantic-validator, runtime-adapter, control-plane, and focused integration
  coverage in `test_run_305_participant_runtime_state_history.py`.
- `test_participant_runtime_invariants.py` is separately a closed, test-local
  oracle for selected formal trace predicates; it is not production runtime
  enforcement evidence.

What is missing:

- no complete cross-backend runtime realization, interoperability, or
  conformance proof spanning the full RUN-305 through RUN-308 family;
- no deployed-backend proof that elevates bounded contracts and probes into
  universal concurrency, information-state, benchmark, or reproducibility
  guarantees; or
- no basis to infer mixed-backend delivery from the open #1013 through #1019
  work.

The repository is therefore at partial implementation coverage, not complete
family or deployed-backend conformance coverage.

## Source Alignment And Design Constraints

This design is constrained by the primary sources listed in
`docs/explain/sdl/lineage.md`:

- Gymnasium and OpenAI Gym support an action/observation/reward/episode
  boundary with action spaces, observation spaces, termination, truncation,
  reset, and seeding. RAES follows that boundary, while adding
  multi-participant provenance and shared-state records and without requiring
  access to private policy internals.
- PettingZoo contributes the multi-agent environment API discipline: per-agent
  observations and rewards, local histories, action masks, termination and
  truncation, possible/live/active-agent membership, and the sequential Agent
  Environment Cycle versus parallel API split. OpenSpiel contributes the
  game-theoretic surface PettingZoo does not model: chance nodes,
  information-state discipline, simultaneous-move games, current-player
  semantics, and mean-field game support. RAES therefore separates hidden
  state, participant-visible observations, action-observation histories,
  centralized-training state, reward/return signals, interaction context, and
  review evidence, attributing each requirement to the source family that
  actually defines it rather than treating the two ecosystems as
  interchangeable.
- POMDP, Dec-POMDP, POSG, and Markov-game lineage means a participant's
  observation is not world truth. Strong information-state claims require a
  reconstructible observation history, not just a final state dump.
- Interpreted systems (Fagin, Halpern, Moses, and Vardi), dynamic epistemic
  logic, and Kuhn's extensive-form information sets ground the
  information-state semantics below: a participant's information is defined by
  indistinguishability over its visible local history, view changes are
  explicit events, and perfect recall is an information-partition property
  that runtime claims must witness constructively. Winskel's event structures
  and Mazurkiewicz's trace theory ground the partial-order realized-ordering
  model, and the ANSI SQL isolation critique (Berenson et al.) together with
  Adya's generalized isolation theory grounds the isolation-guarantee
  vocabulary.
- CybORG, CyberBattleSim, CyGIL, CALDERA, OpenC2, CACAO, and ATT&CK show that
  cyber actions carry command, target, session, credential, knowledge,
  detection, foothold, and outcome semantics. RAES records those as portable
  references without adopting any one backend or playbook format as canonical.
- OCSF and STIX establish the event-schema precedent for identity, schema
  versioning, classification, timestamps with distinct meanings, normalized
  status/severity, confidence, source/raw mapping, raw-data integrity,
  markings, granular selectors, and extension rules.
- Lamport clocks, HLA time management, Time Warp, DEVS, FMI, and related
  runtime literature require RAES to separate wall-clock timestamps, logical
  ordering, simulation time, time-advance grants, lookahead, message
  send/receive causality, rollback/anti-message handling, pacing, and
  synchronization. Vector time (Fidge; Mattern) and the Schwarz-Mattern
  causality survey supply the stronger basis the `VectorClock` ordering value
  claims: scalar Lamport clocks respect causality in one direction only, while
  vector clocks characterize the causal partial order, including causal
  independence.
- Cybench, AutoPenBench, CAIBench, AI Agents That Matter, and related agent
  benchmark critiques require run records, scaffold/tool exposure, seeds,
  repeated-run ids, statistical repetition plans, resource/cost traces,
  baseline/evaluator disclosure, metric aggregation and uncertainty procedures,
  cost normalization, evaluator leakage controls, contamination audits,
  immutable artifact evidence, and holdout/canary exposure evidence for
  auditable comparisons.
- W3C PROV, FAIR, RO-Crate, and ACM artifact-review practice require persistent
  identifiers, qualified references, provenance, licensing/access metadata,
  reusable artifact bundles, and explicit artifact availability limits. RAES
  preserves enough runtime and support-graph information for those packages and
  reviews without making issue #74 a full research-object archive exporter.

These sources do not make RAES a compatibility layer for any one project. They
define review constraints: the model must preserve the concepts needed to make
participant behavior, information boundaries, concurrency, and benchmark claims
auditable.

## Formal Methods Classification

This surface is `FM3` under ADR-007 and
`specs/formal/assurance-policy.yaml`: it defines stateful/control semantics,
lifecycle transitions, shared state, ordering, and concurrency.

Required artifacts for future implementation:

- invariant list;
- closed lifecycle, observation, operation, concurrency, marking, and
  capability vocabularies;
- unit tests;
- typed runtime contract coverage;
- property-based or differential tests where they improve coverage;
- abstract state-machine model;
- model-checkable or mechanically testable refinement target for the
  concurrency and information-state subsets.

This document supplies the invariant list, abstract state-machine model,
normalized vocabulary, conformance obligations, and structural examples for the
design issue. Typed contracts, tests, evidence fixtures, and executable models
belong to the spawned implementation issues. Issue #486 delivers a bounded
executable oracle for the named participant-runtime trace predicates listed in
the implementation mapping below.

## V1 Traceability Criteria Matrix

This matrix is the control surface for later implementation work. A row marked
`v1 MUST` is not implementation coverage in this issue; it is a required
enforcement trace for the per-UID implementation issues. A future implementation
may claim v1 conformance for a row only when every enforcement column has a
concrete artifact. If a column is intentionally absent, the row must be
reclassified as `v1 SHOULD` or `future/non-goal`, or the prose claim that depends
on it must be downgraded.

Enforcement columns mean:

- `Contract field` - the runtime/support record field that carries the claim.
- `Schema gate` - JSON Schema or Pydantic shape constraints that can reject the
  invalid shape without whole-trace knowledge.
- `Semantic gate` - Python semantic validation, conformance validation, or an
  executable abstract-model check needed when schema shape is insufficient.
- `Probe` - a negative fixture or adversarial trace that must be rejected or
  forced to downgrade.

| ID | Criterion | Status | Contract field | Schema gate | Semantic gate | Probe |
| --- | --- | --- | --- | --- | --- | --- |
| PRT-01 | Base runtime records carry stable identity, schema version, event type, provenance, source refs, clocks, markings, and extension policy. | v1 MUST | `BaseEnvelope` | required fields, enums, timestamp shape, closed extra fields | `BaseOK`, `RefOK`, schema/model drift check | missing schema version; unknown required extension accepted |
| PRT-02 | Evidence and raw-data claims are digest-bound and cannot point to mismatched bytes or placeholder hashes. | v1 MUST | `source_raw_ref`, `raw_data_integrity`, `evidence_refs`, evidence index digest fields | digest algorithm/pattern pairs, size/truncation requiredness | `RawDataIntegrityOK`, `EvidenceRefIntegrityOK` | event cites evidence A but digest belongs to evidence B |
| PRT-03 | Field-level marking and redaction run before any public record, fixture, schema example, diagnostic, or changelog exposure. | v1 MUST | `marking_definition_refs`, `object_marking_refs`, `granular_markings`, `redaction_policy_ref`, `authorization_scope` | selector shape and marking-ref requiredness | `MarkingOK`, `NoHiddenDisclosure`, redaction publication gate | hidden answer key appears in public observation or fixture |
| PRT-04 | OCSF/STIX-style classification is RAES-native unless an explicit source mapping proves compatibility. | v1 MUST | `event_classification`, `source_status`, `source_pipeline` | nullable only for no-claim records; closed status vocab | classification registry and source-mapping validation | OCSF-looking tuple accepted with no governed OCSF mapping |
| PRT-05 | Observable lifecycle phases do not require participant-internal plans, prompts, chain-of-thought, policy state, or workflow steps. | v1 MUST | `LifecycleEnvelope.phase`, `phase_realization`, `admission_disposition`, `operation_ref` | closed lifecycle/realization/disposition enums | `Transition_k`, lifecycle boundary validator | opaque LLM action rejected because no proposal trace exists |
| PRT-06 | Non-RL cyber, human, script, playbook, and external actions are valid through action contracts and provenance, not action-space membership. | v1 MUST | `action_contract_ref`, `command_ref`, `actor_provenance`, `action_validity_basis_ref` | validity-basis enum and conditional refs | `StepActionValid`, `ActionValidityBasisOK` | human action with no RL action-space ref is rejected despite action contract |
| PRT-07 | Participant-visible observation, hidden truth, scoring state, centralized-training state, evidence, and information state remain separate. | v1 MUST | `ObservationEnvelope`, `VisibleHistory`, `information_guarantee` | required projection/history refs for stronger guarantees | `KernelOK`, `HistoryConsistent`, `PerfectRecall` | hidden state id enters visible history without projection |
| PRT-08 | RL/MARL/game claims preserve action/observation spaces, masks, rewards, returns, termination/truncation, possible/live/active agents, current actor, null cleanup, chance, and mean-field semantics. | v1 MUST when such claims are made | `ParticipantInterface`, `InteractionContextEnvelope`, `StepSignalEnvelope` | conditional refs by `interaction_mode` and `chance_mode` | `InteractionClaimOK`, `AgentSetDisciplineOK`, `ChanceDisclosureOK`, `MeanFieldDisclosureOK` | AEC cleanup null counted as ordinary action-space member; non-acting live agent silently dropped from reward/observation scope |
| PRT-09 | Shared operational state is addressable, revisioned or digest-pinned, provenance-bearing, and separate from metadata/detail maps. | v1 MUST | `SharedStateRecord`, `SharedStateAccess` | address/kind/revision/digest conditional fields | `RevisionDiscipline`, state-ref validator | shared-state claim stored only in `RuntimeSnapshot.metadata` |
| PRT-10 | Concurrency and time claims use explicit order, isolation, conflict, clock, lookahead, rollback, and supersession records. | v1 MUST when concurrency/time claims are made | `JointActionRecord`, `TimeManagementContext` | order/isolation/conflict/time enums and conditional refs | `OrderDiscipline`, `ConflictOK`, `TimeManagementOK` | simultaneity inferred from near-equal wall-clock timestamps |
| PRT-11 | Capability is a component-wise vector; weak adapter, clock, observer, redaction, evidence-store, replay, or benchmark support downgrades the claim. | v1 MUST | `capability_guarantee_vector`, component capability declarations | concern/applicability/strength vocabularies | `CapabilityOK`, meet/satisfaction validator | scalar "supported=true" accepted for exact concurrency claim |
| PRT-12 | Cyber command/action mappings preserve command, target, actuator, session, credential refs, knowledge/foothold/visibility/detection deltas, and source-tool identity. | v1 MUST when cyber action claims are made | `CyberActionEnvelope` | conditional refs for OpenC2/CACAO/CALDERA mappings | command/source mapping validator | raw credential value appears in `credential_ref` |
| PRT-13 | Comparative, causal-treatment, superiority, equivalence, non-inferiority, or assignment-dependent benchmark claims disclose treatment assignment, assignment unit, randomization/blocking, baseline cohort, scaffold/tool/model exposure, and assistance. | v1 MUST for those claim scopes | `RunContext`, `BenchmarkValidityClaim`, `TreatmentAssignment` | required refs when conclusion scope depends on assignment | `TreatmentAssignmentOK`, `BaselineComparabilityOK`, context-linkage validator | baseline comparison with no assignment mechanism or baseline cohort |
| PRT-14 | Metric, aggregation, denominator, missingness, replicate, unit-of-analysis, uncertainty, effect, margin, and cost-normalization claims are validated, not just listed. | v1 MUST for result-analysis claims | `MetricSpec`, `AggregationPlan`, `ReplicateSet`, `StatisticalPlan`, `CostNormalizationPolicy` | required fields and closed uncertainty/cost vocabularies | `MetricsOK`, `ReplicationOK`, `UncertaintyOK`, `CostOK` | cost-normalized superiority claim using `descriptive_only` plan |
| PRT-15 | Validity threats and residual limits are explicit for benchmark conclusions and V&V/correspondence claims. | v1 MUST for benchmark validity claims | `validity_threat_refs`, `validity_threat_mitigation_refs`, `unsupported_or_unknown_limits` | threat category and affected-claim requiredness | `ValidityThreatsOK`, `CorrespondenceEvidenceOK` | claim omits construct/internal/external/statistical threat disclosure |
| PRT-16 | Evaluator leakage, non-contamination, holdout/canary, public/private material labels, and participant knowledge cutoffs are governed support records. | v1 MUST for leakage or non-contamination claims | `EvaluatorLeakageModel`, `ExposureAuditProcedure`, cutoff refs | conditional refs by conclusion scope | `EvaluatorLeakageOK`, `ExposureOK` | holdout non-exposure claimed with no holdout digest or audit method |
| PRT-17 | Artifact immutability is graph-derived from every consumed run/support record and maps each required role to a pinned artifact. | v1 MUST for benchmark claims | `ArtifactImmutabilityEvidence`, `artifact_role_assignments`, `required_role_policy_ref` | non-empty artifacts, digest refs, role assignment shape | `ArtifactImmutabilityOK`, `RequiredArtifactCoverageOK` | unrelated pinned artifact satisfies missing evaluator artifact |
| PRT-18 | PROV/FAIR/RO-Crate alignment is preserved without requiring issue #74 to emit an archive package. | v1 SHOULD; exporter future/non-goal | persistent ids, qualified refs, artifact roles, license/access/provenance refs, optional `research_object_manifest_ref` | URI/ref shape where present | artifact graph to PROV/RO-Crate crosswalk check | RO-Crate conformance claimed with no metadata descriptor/root entity mapping |
| PRT-19 | Schema, model, documentation, fixture, and validator surfaces cannot diverge silently. | v1 MUST for implementation issues | generated schema ids, model version, criterion id test markers | generated-schema drift checks and closed schemas | traceability audit from criterion id to tests/fixtures | docs claim a MUST with no schema/model/semantic/test/probe row |

The minimum adversarial fixture/probe set for v1 is the union of the `Probe`
column for every `v1 MUST` row. Positive fixtures are necessary but not
sufficient: a row is not covered unless at least one invalid shape is rejected
or downgraded by the declared enforcement point.

## Terms

`Participant`
: A scenario participant identified at runtime by stable
  `participant_address`. The concrete implementation may be a human, LLM agent,
  RL policy, script, playbook, simulator, external service, or hybrid apparatus.

`Episode`
: A bounded execution instance for one participant, identified by `episode_id`.
  Each participant episode owns a monotonic behavior sequence.

`Observable lifecycle envelope`
: The runtime boundary record for proposal or intent observation, selection or
  admission, execution attempt, observation emission, and state update.

`Lifecycle phase`
: One of the portable runtime points: intent/proposal, selection/admission,
  execution attempt, observation emission, or state update commit.

`Phase realization`
: A normalized claim about how a lifecycle phase is realized: observed,
  runtime-mediated, externally supplied, opaque, unknown, not applicable, or
  unsupported.

`Admission disposition`
: A normalized claim about whether a selection/admission phase allowed the
  attempted action to proceed: admitted, rejected, withheld, unknown, or not
  applicable.

`Operation state`
: A normalized state for long-running or asynchronous execution: submitted,
  acknowledged, running, blocked, completed, partial, failed, timed out,
  cancelled, unknown, or unsupported.

`Opaque participant`
: A participant implementation that does not expose one or more internal
  decision phases. Opaqueness is permitted, but the runtime must still record
  observable attempts, observations, and state updates.

`Shared operational state`
: Portable runtime state that participant actions can read, write, disclose,
  conceal, or use as evidence. It is distinct from world truth,
  participant-visible projection, participant belief/history, and archival
  evidence.

`Action-observation history`
: The participant-visible history of prior action attempts, emitted
  observations, and disclosed lifecycle facts for one participant episode. It
  is a sequence only when a participant-local delivery order is recorded; under
  concurrent or simultaneous semantics it may be a visible partial order with
  simultaneity groups.

`Information state`
: The participant information state RAES claims at an order point. It may be
  only the emitted observation, a history-consistent reconstruction, a
  perfect-recall history, a lossy projection, unknown, or unsupported.

`Decision epoch`
: A zero-based participant choice opportunity within one episode. It is not a
  lifecycle-history index, behavior-history index, policy order, delivery
  order, or backend scheduler step.

`Decision state cut`
: The exact total-order prefix or downward-closed causal frontier from which a
  participant decision view is derived. A sequence cut and a causal cut are
  distinct order models; a maximum scalar index cannot resolve an incomparable
  causal frontier.

`Participant decision view`
: The participant-available context, action entries, affordances, form, and
  semantic limitations for one participant, episode, and decision epoch. The
  view excludes trusted derivation, policy, evidence, provenance, and delivery
  material.

`Participant decision assurance`
: The trusted derivation anchor, exact-cut projection/exposure decisions,
  canonical view digest, evidence, provenance, and participant-memory scope for
  one decision view.

`Participant memory scope`
: Either `episode_local_reset`, which requires an authoritative reset of every
  participant-visible memory channel, or `persistent_across_episodes`. Episode
  reset/restart alone changes episode identity and restarts decision epoch; it
  does not prove forgetting.

`Step signal`
: A participant-visible or evaluator-visible signal produced at an action step:
  observation, reward, return, action mask, termination, truncation, or
  auxiliary info. Step signals are runtime records, not participant internals.

`Action mask`
: A participant-scoped legal-action projection at an order point. It is valid
  only for the declared action space, visibility projection, and state revision
  context that produced it.

`Possible agent set`
: The participant addresses that may appear in the interaction surface for the
  environment, game, or episode scope.

`Live agent set`
: The participant addresses that are currently live for the interaction scope:
  they have not been removed, or marked terminated/truncated for claims that
  depend on live membership. A cleanup turn for a terminated or truncated
  participant cites its terminal/truncation basis instead of treating the
  participant as live.

`Active agent set`
: The participant addresses with an action-admission slot at a game or
  environment order point. Ordinary non-null action slots must be live. AEC
  cleanup slots may contain a terminated or truncated participant only for a
  governed null action. Sequential/AEC surfaces have one current actor;
  simultaneous and parallel surfaces may have more than one; chance and
  mean-field nodes have no participant action unless explicitly wrapped by a
  scenario participant. The full possible-agent set, live-agent membership, and
  non-acting signal policy must use separate refs or disclosures when a claim
  depends on them.

`Chance node`
: A runtime order point where stochastic environment/nature behavior, not a
  participant decision, selects an outcome. Portable claims require the chance
  mode, distribution or sampled-outcome disclosure, seed/randomization context,
  and ordering basis.

`Mean-field node`
: A runtime order point where the environment updates or consumes a population
  distribution rather than accepting an ordinary participant action. Portable
  claims require the distribution reference, update rule, and affected
  participant population scope.

`Conflict policy`
: The explicit rule or disclosure used when concurrent attempts touch the same
  shared operational state, resource, visibility surface, evidence stream, or
  action-contract interference relation.

`Capability guarantee`
: A backend's declared strength for a specific runtime concern. Capability is a
  vector over concerns and runtime components, not one scalar level.

`Time-management context`
: The declared time domain, clock authority, advancement, lookahead,
  message-causality, pacing, rollback, or step-negotiation basis for a
  distributed or simulated runtime claim.

`Benchmark validity claim`
: A bounded claim that a runtime record supports reproducibility, comparison,
  non-contamination, or cost-normalized evaluation. It is separate from the raw
  run context and must cite a statistical/evaluation procedure when used for
  comparative conclusions.

`Marking`
: A security, sensitivity, sharing, or redaction label attached to a record or
  field. Markings govern disclosure; they are not prose warnings.

`Refinement`
: A relation showing that concrete backend traces project to valid RAES traces
  while preserving required identity, order, visibility, provenance, and
  capability guarantees.

## Abstract State Machine

The participant runtime model is a transition system over append-only records.

### State Tuple

Let abstract runtime state be:

```text
RuntimeState =
  participants
  episodes
  behavior_history
  lifecycle_events
  operation_records
  observations
  participant_interfaces
  interaction_contexts
  step_signals
  action_observation_histories
  information_states
  shared_state
  joint_actions
  time_management_contexts
  evidence_index
  run_context
  benchmark_claims
  capability_declarations
  capability_components
  marking_policies
  logical_order
```

Where:

- `participants` is the set of participant addresses.
- `episodes[p]` is the ordered episode set for participant `p`.
- `behavior_history[p,e]` is the append-only behavior history for participant
  `p` in episode `e`.
- `lifecycle_events` is the append-only set of lifecycle envelopes.
- `operation_records` is the append-only set of long-running operation records.
- `observations[p,e]` is the emitted participant-visible observation stream.
- `participant_interfaces[p,e,t]` records action/observation spaces and
  legal-action or mask surfaces visible at order point `t`.
- `interaction_contexts[t]` records possible/live/active-agent, chance,
  simultaneous, and mean-field node semantics for game/RL/MARL surfaces.
- `step_signals[p,e,t]` records reward, return, termination, truncation,
  action-mask, observation, and auxiliary-info signals when exposed.
- `action_observation_histories[p,e,t]` is the prefix or lower set of visible
  actions and observations available to participant `p` at order point `t`,
  depending on whether the visible delivery claim is total or partial.
- `information_states[p,e,t]` is the information state RAES claims for
  participant `p` at order point `t`.
- `shared_state[address]` is the version chain for a shared operational state
  address.
- `joint_actions[id]` records coordination intervals and concurrent attempts.
- `time_management_contexts[id]` records simulation/distributed time semantics
  used by joint action, operation, or state-update records.
- `evidence_index` maps safe evidence references to evidence contracts and
  redaction policies.
- `run_context` contains reproducibility and benchmark context.
- `benchmark_claims[id]` records the explicit validity procedure for any
  reproducibility, comparison, non-contamination, or cost-normalized claim.
- `capability_declarations[backend, concern]` is the backend's declared
  contribution to the effective guarantee vector.
- `capability_components[component, concern]` records adapter, backend,
  evidence-store, redaction, clock, observer, and coordinator contributions to
  the effective guarantee vector.
- `marking_policies` contains field-level authorization and redaction rules.
- `logical_order` is the recorded total or partial order relation over events.

### Base Envelope

Every portable record that can support a runtime claim carries:

```text
BaseEnvelope =
  event_id
  schema_name
  schema_version
  event_type
  extension_policy
  event_classification
  source_status
  participant_address
  episode_id
  sequence_number
  occurred_at
  recorded_at
  ingested_at
  clock_authority
  temporal_context
  ordering_basis
  logical_order_ref
  predecessor_event_refs
  actor_ref
  producer_ref
  source_system_ref
  source_record_ref
  source_raw_ref
  source_pipeline
  raw_data_integrity
  confidence
  provenance_refs
  evidence_refs
  marking_definition_refs
  object_marking_refs
  markings
  granular_markings
  redaction_policy_ref
  authorization_scope
```

Rules:

- `event_id` is globally stable within the run.
- `schema_name` and `schema_version` identify the RAES contract projection, not
  the backend's native object.
- `event_classification` and `source_status` are nullable only when the record
  makes no normalized event-status, severity, or security-telemetry claim.
  When populated they use the structures below.
- `participant_address`, `episode_id`, and `sequence_number` may be null only
  for run-scoped records, such as a joint action record, that carry
  per-participant linkage through member event references.
- `occurred_at`, `recorded_at`, and `ingested_at` must not be collapsed. If a
  backend cannot distinguish them, it must disclose that with `clock_authority`
  or capability weakening.
- `ordering_basis` and `logical_order_ref` carry ordering claims. Wall-clock
  timestamps alone do not establish causality.
- `source_raw_ref` points to controlled evidence; it does not inline raw
  sensitive data into the portable envelope.
- `raw_data_integrity` records hash, size, truncation, and untruncated-size
  facts for raw data that supports a runtime claim.
- `source_pipeline` records source product/version, original event identity,
  processed/logged/transmitted times, correlation, and sequence information
  when a source telemetry or command system is mapped into RAES.
- `markings` and `granular_markings` are enforceable field-level disclosure
  labels.

Event classification, source status, source pipeline metadata, raw-data
integrity, and marking selectors follow the OCSF/STIX design pattern while
remaining RAES-native:

```text
EventClassification =
  category_uid
  category_name
  class_uid
  class_name
  activity_id
  activity_name
  type_uid
  type_name
  severity_id
  severity
```

`EventClassification` is not an implicit OCSF event. The tuple
`(category_uid, class_uid, activity_id, type_uid)` is governed by the RAES
classification registry for the record's `schema_name` and `schema_version`.
RAES-native examples may use the OCSF-style composite identifier pattern, but
that does not assert that OCSF category, class, activity, or profile values are
being emitted. If a record claims OCSF compatibility, it must cite a governed
source-classification mapping and the mapped values must validate against the
referenced OCSF schema/profile version.

```text
SourceStatus =
  status_id
  status
  status_code
  status_detail
  source_status_label
  source_status_mapping
```

```text
SourcePipeline =
  product_ref
  product_version
  log_provider
  log_source
  log_name
  original_event_uid
  original_time
  processed_time
  logged_time
  transmit_time
  correlation_uid
  sequence
```

```text
RawDataIntegrity =
  raw_data_hash
  raw_data_hash_algorithm
  raw_data_size
  raw_data_is_truncated
  raw_data_untruncated_size
```

```text
GranularMarking =
  selectors
  marking_ref
  marking_scope
```

### State Sets

Participant episode state is inherited from ADR-013:

```text
EpisodeState =
  Initializing
  Running
  Terminated
```

Observable action lifecycle phase is:

```text
LifecyclePhase =
  IntentOrProposal
  SelectionOrAdmission
  ExecutionAttempt
  ObservationEmission
  StateUpdateCommit
```

Phase realization is:

```text
PhaseRealization =
  Observed
  RuntimeMediated
  ExternallySupplied
  Opaque
  Unknown
  NotApplicable
  Unsupported
```

Admission disposition is:

```text
AdmissionDisposition =
  Admitted
  Rejected
  Withheld
  Unknown
  NotApplicable
```

Operation state is:

```text
OperationState =
  Submitted
  Acknowledged
  Running
  Blocked
  Completed
  Partial
  Failed
  TimedOut
  Cancelled
  Unknown
  Unsupported
```

`Opaque`, `Unknown`, `NotApplicable`, and `Unsupported` are intentionally
distinct:

- `Opaque` means the participant may have an internal counterpart, but the
  apparatus boundary does not expose it.
- `Unknown` means the phase might be relevant, but the adapter cannot determine
  what happened.
- `NotApplicable` means the phase has no semantic counterpart for this action
  or participant.
- `Unsupported` means the backend or adapter cannot provide a portable
  guarantee.

`Rejected` and `Withheld` are admission dispositions, not phase realizations.
`Completed`, `Failed`, `TimedOut`, and `Cancelled` are operation states, not
episode terminal reasons.

Lifecycle envelopes carry:

```text
LifecycleEnvelope =
  BaseEnvelope
  phase
  phase_realization
  admission_disposition
  operation_ref
  action_ref
  action_contract_ref
  command_ref
  actor_provenance
  action_validity_basis_ref
  observation_refs
  shared_state_read_refs
  shared_state_write_refs
  emitted_state_update_refs
  attribution_edge_refs
  outcome_interpretation_refs
  joint_action_set_ref
  source_status_label
  mapping_loss
  mapping_loss_detail
```

`attribution_edge_refs` and `outcome_interpretation_refs` link the boundary
record to the evidence-labeled attribution edges (`SEM-212`) and outcome
interpretation records (`SEM-215`) defined in
`specs/formal/participant-semantics/`. This document binds where those records
attach in the runtime trace — the lifecycle envelope for the event they
qualify — while their internal semantics remain owned by the
participant-semantics design. They are how the behavior-history overview claim
that runtime records carry attribution and outcome interpretation is realized
at the envelope level; without these fields that claim has no contract carrier.

Mapping loss is a closed vocabulary:

```text
MappingLoss =
  None
  PrivateApparatusDetail
  SourceFieldsOmitted
  SemanticsApproximated
  RedactedByPolicy
  TemporalDetailCollapsed
  Unknown
  Unsupported
```

- `None`: the portable record carries the source semantics relevant to its
  claims without loss.
- `PrivateApparatusDetail`: an internal apparatus counterpart (prompt, policy
  trace, private selection or plan) exists or may exist but is not exposed
  across the apparatus boundary.
- `SourceFieldsOmitted`: source-record fields with no portable counterpart
  were dropped.
- `SemanticsApproximated`: source semantics were mapped to a broader,
  narrower, or approximate portable meaning.
- `RedactedByPolicy`: content was removed, tokenized, or summarized by a
  marking or redaction policy.
- `TemporalDetailCollapsed`: source timing or ordering detail could not be
  preserved distinctly.
- `Unknown` and `Unsupported` keep their standard meanings.

`mapping_loss` is nullable only when the record makes no source-mapping claim.
A record projected from a source system declares its loss explicitly, `None`
included. `mapping_loss_detail` is optional free text for review context; like
source labels, it does not define semantics.

Observation information guarantees are:

```text
InformationGuarantee =
  ObservationOnly
  HistoryConsistent
  PerfectRecall
  LossyProjection
  Unknown
  Unsupported
```

Interaction mode is:

```text
InteractionMode =
  SingleAgent
  SequentialTurn
  AgentEnvironmentCycle
  Parallel
  Simultaneous
  Chance
  MeanField
  BackendSerialized
  Terminal
  Unknown
  Unsupported
```

Chance mode is:

```text
ChanceMode =
  NotApplicable
  Deterministic
  ExplicitStochastic
  SampledStochastic
  Unknown
  Unsupported
```

Observation envelopes carry:

```text
ObservationEnvelope =
  BaseEnvelope
  observation_ref
  phase_ref
  visibility_projection_ref
  information_guarantee
  delivery_basis
  delivery_point_ref
  delivered_at
  action_observation_history_ref
  information_state_ref
  hidden_state_refs
  centralized_state_refs
  loss_descriptor
  stochastic_context
  noise_model_ref
  reconstruction_algorithm_ref
  reconstruction_proof_ref
  belief_support_ref
  redacted_field_refs
```

Delivery basis is a closed vocabulary:

```text
DeliveryBasis =
  EmissionIsDelivery
  RuntimeDelivery
  ParticipantAcknowledgement
  ExternalDelivery
  Unknown
  Unsupported
```

The declared delivery point of an observation is the order point recorded by
`delivery_point_ref`, interpreted under `delivery_basis`, with `delivered_at`
as an optional wall-clock fact that never substitutes for the order point.
`EmissionIsDelivery` declares that the runtime treats emission as delivery and
`delivery_point_ref` equals the emission order point. `RuntimeDelivery` cites
a runtime delivery event distinct from emission. `ParticipantAcknowledgement`
cites a participant acknowledgement record. `ExternalDelivery` cites an
external channel's delivery record. `Unknown` and `Unsupported` keep their
standard meanings; under either, participant-visible history membership for
the observation has no portable delivery order, and dependent claims must
downgrade.

Participant interface and step-signal records carry the RL/MARL-facing pieces
that Gymnasium, PettingZoo, and OpenSpiel make first-class, without making them
the RAES protocol:

```text
ParticipantInterface =
  BaseEnvelope
  participant_address
  episode_id
  interaction_mode
  possible_agent_set_ref
  live_agent_set_ref
  active_agent_set_ref
  current_actor_ref
  action_space_ref
  action_space_schema_ref
  observation_space_ref
  observation_space_schema_ref
  legal_action_policy_ref
  action_mask_policy_ref
  action_mask_location
  null_action_policy_ref
  chance_policy_ref
  mean_field_policy_ref
  space_version
  applicability
```

```text
InteractionContextEnvelope =
  BaseEnvelope
  interaction_context_id
  interaction_mode
  order_point
  possible_agent_set_ref
  live_agent_set_ref
  active_agent_set
  current_actor_ref
  simultaneous_group_ref
  nonacting_agent_policy_ref
  legal_action_snapshot_refs
  chance_mode
  chance_distribution_ref
  chance_distribution_digest
  sampled_chance_outcome_ref
  chance_seed_ref
  chance_visibility
  mean_field_population_scope_ref
  mean_field_population_refs
  mean_field_state_support_ref
  mean_field_distribution_ref
  mean_field_distribution_digest
  mean_field_update_rule_ref
  mean_field_update_ref
  terminal_node
  unsupported_interaction_disclosure
```

```text
ActionMaskEnvelope =
  BaseEnvelope
  participant_address
  episode_id
  interaction_context_ref
  action_space_ref
  mask_ref
  legal_action_refs
  illegal_action_refs
  mask_encoding
  valid_for_order_point
  valid_for_state_revision_refs
  visibility_projection_ref
  stochastic_context
```

```text
RewardEnvelope =
  BaseEnvelope
  participant_address
  episode_id
  reward_ref
  reward_value_ref
  reward_units
  reward_range_ref
  reward_model
  reward_visibility
  reward_timing
  source_outcome_refs
  scoring_refs
```

```text
ReturnEnvelope =
  BaseEnvelope
  participant_address
  episode_id
  return_ref
  cumulative_return_value_ref
  return_horizon
  return_discount_ref
  reward_ref_prefix
  terminal_basis_ref
```

```text
TerminationEnvelope =
  BaseEnvelope
  participant_address
  episode_id
  terminated
  truncated
  termination_reason_ref
  truncation_reason_ref
  terminal_observation_ref
  episode_terminal_reason_ref
  local_only
```

```text
StepSignalEnvelope =
  BaseEnvelope
  participant_address
  episode_id
  interaction_context_ref
  live_agent_set_ref
  active_agent_set_ref
  current_actor_ref
  action_ref
  observation_ref
  action_mask_ref
  reward_ref
  return_ref
  termination_ref
  info_refs
  centralized_state_refs
```

Shared operational state records carry:

```text
SharedStateRecord =
  BaseEnvelope
  state_address
  state_scope
  state_kind
  revision
  digest
  predecessor_revision_refs
  ordering_basis
  logical_order_ref
  conflict_policy
  visibility_projection_basis
  provenance
  value_ref
  markings
  granular_markings
```

Shared-state accesses carry:

```text
SharedStateAccess =
  state_address
  access_kind
  read_revision
  write_revision
  read_digest
  write_digest
  snapshot_ref
  access_purpose
  atomic_group_ref
  evidence_refs
```

Joint action records carry:

```text
JointActionRecord =
  BaseEnvelope
  joint_action_set_id
  coordination_interval
  member_event_refs
  ordering_basis
  realized_order_relation
  clock_context
  time_management_context_ref
  snapshot_basis
  isolation_guarantee
  atomicity_scope
  read_set
  write_set
  exclusive_resource_claims
  conflict_class
  conflict_policy
  retry_policy_ref
  rollback_refs
  capability_guarantee_vector
  participant_observation_refs
```

Time-management contexts carry:

```text
TimeManagementContext =
  BaseEnvelope
  time_context_id
  time_domain
  time_management_mode
  logical_time
  simulation_time
  wall_clock_interval
  lookahead
  time_regulating
  time_constrained
  time_advance_request_ref
  time_advance_grant_ref
  next_event_request_ref
  message_send_refs
  message_receive_refs
  pacing_policy_ref
  step_size_ref
  rollback_window_ref
  rollback_refs
  anti_message_refs
  compensation_refs
  superseded_event_refs
  transition_basis
```

Ordering basis is normalized:

```text
OrderingBasis =
  TotalOrder
  PartialOrder
  Simultaneous
  SerializedBackendOrder
  SimulationTick
  ControlPlaneOrder
  LogicalClock
  VectorClock
  WallClockOnly
  Unknown
  Unsupported
```

Time-management mode is normalized:

```text
TimeManagementMode =
  None
  WallClockRealtime
  ConservativeLogicalTime
  HlaTimeManaged
  OptimisticRollback
  DevsDiscreteEvent
  FmiCoSimulation
  BackendSerialized
  Unknown
  Unsupported
```

Isolation guarantee is normalized:

```text
IsolationGuarantee =
  Serializable
  Snapshot
  Causal
  ReadCommitted
  BestEffort
  Unknown
  Unsupported
```

Conflict policies are normalized:

```text
ConflictPolicy =
  Coordinate
  Serialize
  Reject
  Retry
  Withhold
  Merge
  Rollback
  DiscloseWeakGuarantee
  Unsupported
```

Capability concerns are:

```text
CapabilityConcern =
  lifecycle_phase
  admission_disposition
  operation_state
  observation_information_state
  participant_interface
  interaction_context
  action_mask
  reward_signal
  return_signal
  termination_signal
  shared_state_revision
  ordering
  time_management
  rollback
  isolation
  conflict_detection
  conflict_resolution
  provenance
  redaction
  replay
  benchmark_reproducibility
  benchmark_validity
```

Guarantee strength per concern is:

```text
GuaranteeStrength =
  unsupported
  disclosed_weak
  bounded
  exact
```

Capability applicability is explicit:

```text
CapabilityApplicability =
  required
  optional
  not_applicable
```

```text
CapabilityValue =
  not_applicable
  unsupported
  disclosed_weak
  bounded
  exact
```

`not_applicable` is outside the guarantee-strength order. It may appear only
when the contract and claim both state that the concern has no semantic role.
Omitting a required concern is not equivalent to `not_applicable`; it is a
capability validation failure.

## Normative Core Model

This section is the reviewable abstract model. Concrete schemas and backend
adapters refine it by mapping native records to these domains and predicates.

### Domains

Let:

```text
P  = participant addresses
E  = episode ids
A  = action attempt ids
Op = operation ids
Obs = observation ids
S  = shared-state addresses
R  = shared-state revisions
J  = joint-action ids
Ev = runtime event ids
T  = logical order points
C  = capability concerns
M  = markings and marking definitions
K  = interaction-context ids
BC = benchmark-claim ids
```

The model uses these additional carrier sets. They are explicit so that the
abstract model is not relying on implicit prose symbols:

```text
Component =
  participant_adapter
  runtime_coordinator
  backend_engine
  observation_apparatus
  evidence_store
  redaction_policy
  clock_authority
  replay_engine
  benchmark_harness

Consumer =
  participant
  runtime_operator
  evaluator
  auditor
  backend_adapter
  public_artifact

Digest       = algorithm-tagged immutable digest values
StateSpace   = abstract runtime states reachable by valid traces
MeasurableSpace[X] = governed value space plus measurable subsets or schema-equivalent sigma algebra
VisibleEvent = participant-visible projected event-occurrence records
VisibleHistory = participant-visible occurrence collection plus visible order metadata
InformationState = governed information-state records or digests
ObservationValue = governed observation values or references
ActionBasisValue = governed participant action attempt values or references
JointActionValue = governed participant-addressed joint action maps
ChanceOutcomeValue = governed environment chance outcomes or references
MeanFieldStateValue = governed population-state support values or references
MeanFieldDistribution = governed probability measure over MeasurableSpace[MeanFieldStateValue]
ObservationBasis = governed transition basis for participant observation
Probability = real values in [0, 1]
ProbabilityMeasure[X] = governed probability measure over MeasurableSpace[X]
Maybe[X] = X union {none}
Result[X] = X union {Unknown, Unsupported, Lossy}
```

Only symbols defined in this document are normative. A future executable model
may refine the carrier sets, but it must preserve the predicates and downgrade
rules below.

The abstract functions are partial unless stated otherwise:

```text
episode_state: P x E -> EpisodeState
seq: P x E -> Nat
event: Ev -> BaseEnvelope
phase: Ev -> LifecyclePhase
realization: Ev -> PhaseRealization
admission: Ev -> AdmissionDisposition
operation_state: Op x T -> OperationState
visible_history: P x E x T -> VisibleHistory
observation: Obs -> ObservationEnvelope
information_claim: P x E x T -> InformationGuarantee
state_revision: S x T -> R
state_digest: S x R -> Digest
order_relation: T -> Relation(Ev, Ev)
capability: Component x C -> CapabilityValue
effective_capability: C -> CapabilityValue
authorized: Consumer x BaseEnvelope -> Bool
interaction_context: K -> InteractionContextEnvelope
interaction_context_at: T -> Maybe[K]
possible_agents: K -> Set(P)
live_agents: K -> Set(P)
active_agents: K -> Set(P)
current_actor: K -> Maybe[P]
transition_basis: K -> Result[ObservationBasis]
chance_distribution: K -> Result[ProbabilityMeasure[ChanceOutcomeValue]]
sampled_chance_outcome: K -> Result[ChanceOutcomeValue]
mean_field_distribution: K -> Result[MeanFieldDistribution]
benchmark_claim: BC -> BenchmarkValidityClaim
```

Trace helpers are defined as follows:

```text
prefix(tr, i) =
  <ev_1, ..., ev_i> when tr = <ev_1, ..., ev_n> and 0 <= i <= n

prefix_state(tr, i) =
  fold_apply(initial_state(tr), prefix(tr, i))

fold_apply(s, <>) = s
fold_apply(s, <ev_1, ..., ev_n>) =
  Reject if Apply(s, ev_1) = Reject
  else fold_apply(Apply(s, ev_1), <ev_2, ..., ev_n>)
```

`initial_state(tr)` is the declared run initialization state containing
participants, admitted episodes, run context, capability components, marking
policies, and controlled vocabulary versions. If that declaration is missing,
`InitOK` is false.

`CapabilityValue` is `not_applicable` or a `GuaranteeStrength`. The strength
order is:

```text
unsupported < disclosed_weak < bounded < exact
```

### Valid Trace Predicate

A published runtime trace `tr = <ev_1, ..., ev_n>` is valid iff all of the
following hold. The empty sequence is admissible only as a prefix used while
defining `prefix_state`; it is not a published trace that can support a runtime
claim.

```text
ValidTrace(tr) =
  n >= 1
  /\ InitOK(initial_state(tr))
  /\ Unique(event_id, tr)
  /\ forall i in 1..n:
       BaseOK(ev_i)
       /\ MarkingOK(ev_i)
       /\ CapabilityOK(ev_i)
       /\ RefOK(ev_i, prefix(tr, i - 1), initial_state(tr))
       /\ Apply(prefix_state(tr, i - 1), ev_i) != Reject
  /\ AppendOnly(tr)
  /\ MonotoneSequence(tr)
  /\ RevisionDiscipline(tr)
  /\ OrderDiscipline(tr)
  /\ forall j in JointActionRecords(tr): ConflictOK(j, tr)
  /\ forall tm in TimeManagementContexts(tr): TimeManagementOK(tm, tr)
```

Where:

- `InitOK(s0)` requires declared participants, admitted episode namespace,
  run identity/provenance context, component capability declarations, marking
  policies, redaction policies, clock authorities, and vocabulary/registry
  versions. If any of these runtime-init records are absent, no exact runtime,
  information-state, or concurrency claim may be made. A full `RunContext`
  is additionally required before a benchmark, reproducibility, comparison, or
  publication claim may be made.
- `BaseOK(ev)` is true iff `event(ev)` has a stable `event_id`, known
  `schema_name`/`schema_version`, permitted `event_type`, permitted
  `extension_policy`, distinct `occurred_at`/`recorded_at`/`ingested_at`
  meanings or an explicit clock downgrade, governed source/raw references, and:
  `EventClassificationOK(ev)`, `SourceStatusOK(ev)`, `SourcePipelineOK(ev)`,
  `RawDataIntegrityOK(ev)`, and `EvidenceRefIntegrityOK(ev)`.
- `EventClassificationOK(ev)` is true when `event_classification` is null and
  `ClassificationClaim(ev)` is false, or when the classification tuple is
  present in the RAES classification registry for the record schema version.
  OCSF compatibility is true only with a cited OCSF mapping and
  OCSF-schema-valid values.
- `ClassificationClaim(ev)` defines "makes a claim" for classification, status,
  severity, and security-telemetry purposes. It is true exactly when at least
  one of the following holds: the RAES classification registry marks the
  record's `(schema_name, schema_version, event_type)` as
  classification-bearing; the record populates `event_classification` or maps
  `source_status` into a normalized status/severity vocabulary; another record
  in the trace cites this record as the basis for a normalized status,
  severity, detection, finding, or security-telemetry conclusion; or the
  record's source mapping declares OCSF/STIX compatibility. When all of these
  are false the record makes no claim, and `event_classification` and the
  normalized `source_status` pair must be null rather than populated with
  unregistered values. A consumer that wants to draw a classification-dependent
  conclusion from a no-claim record must first upgrade the record, not
  reinterpret it.
- `SourceStatusOK(ev)` is true when `source_status` is null and the record
  makes no status claim, or when the normalized `status_id`/`status` pair is in
  the governed status vocabulary and source labels are preserved separately.
- `SourcePipelineOK(ev)` is true when absent source-pipeline fields are
  semantically not applicable or explicitly unknown, and when any populated
  source product/version, original event id, time, correlation id, or sequence
  field maps to the cited source record.
- `RawDataIntegrityOK(ev)` is true when raw bytes are not claimed, or when hash,
  algorithm, size, truncation, and untruncated-size fields are all consistent
  with controlled evidence bytes. Explicit null or unknown integrity fields
  can satisfy only no-raw-data, weak, unknown, or unsupported raw-evidence
  claims; they cannot support exact provenance, replay, or benchmark-evidence
  claims. A placeholder hash is never evidence for an exact provenance claim.
- `EvidenceRefIntegrityOK(ev)` is true when every `source_raw_ref` and
  `evidence_refs` member resolves through `evidence_index` to an immutable
  evidence record with digest, size, storage/registry location, marking, and
  redaction policy metadata appropriate for the claim, and when the referenced
  digest matches the controlled evidence bytes. Reusing a ref for different
  bytes, citing a digest from another artifact, or citing an unverified
  placeholder ref cannot support an exact provenance or benchmark claim.
- `MarkingOK(ev)` checks that every object marking and granular selector
  resolves to a marking definition, selectors refer to existing fields under
  the schema projection, no marked field is exposed to an unauthorized consumer,
  and redaction tokens replace hidden values before publication.
- `CapabilityOK(ev)` checks every claim in `ev` against the effective
  component-wise capability vector. The claim must be no stronger than the meet
  of backend, adapter, evidence-store, redaction, clock, observer, replay, and
  benchmark-harness support for the relevant concerns.
- `RefOK(ev, prefix, s0)` checks that every referenced participant, episode,
  action, operation, observation, state revision, interaction context, joint
  action, evidence item, run context, benchmark claim, source mapping, marking
  policy, redaction policy, clock authority, and vocabulary/registry version
  either exists in the initial declaration `s0`, exists in `prefix`, or is
  introduced by the current transition with a stable identity and declared
  namespace. Initial declarations are immutable inputs to the trace; later
  transitions may supersede runtime state, but they do not mutate `s0`.
- `AppendOnly(tr)` forbids deletion or mutation of prior history records;
  rollback, compensation, and correction create superseding records.
- `MonotoneSequence(tr)` requires participant-scoped `sequence_number` to
  increase strictly within each `(participant_address, episode_id)` stream. Null
  sequence numbers are permitted only on run-scoped records.
- `RevisionDiscipline(tr)` requires every shared-state write to cite known
  prior revisions or disclose unknown/unsupported revision support, and every
  write either produces a new revision/digest or records an unsupported update.
- `OrderDiscipline(tr)` requires every ordering claim to be backed by a
  declared order basis. Wall-clock-only order can support display order but not
  causality, simultaneity, serializability, or time-management claims.
- `ConflictOK(j, tr)` is defined in the concurrency section. It validates the
  conflict predicate, conflict policy, isolation, atomicity, rollback, retry,
  and weak/unsupported disclosure claims for each joint-action record.
- `TimeManagementOK(tm, tr)` is defined in the concurrency section. It
  validates mode-specific clock, lookahead, time-advance, pacing, rollback,
  DEVS, FMI, and backend-serialized time-management claims.

### Transition Schema

Each transition is a predicate over pre-state `s`, event `ev`, and post-state
`s'`:

```text
Transition_k(s, ev, s') =
  Pre_k(s, ev)
  /\ s' = Update_k(s, ev)
  /\ Post_k(s, ev, s')
```

`Apply(s, ev)` returns `Reject` unless exactly one transition predicate matches
the event type and all shared invariants hold. If multiple transitions could
match, the event is invalid because its portable semantics are ambiguous.

Shared transition obligations:

```text
HistoryAppend(s, ev, s')
OrderAppend(s, ev, s')
NoHiddenDisclosure(s, ev, s')
NoCapabilityUpgrade(s, ev, s')
NoUnauthorizedField(s, ev, s')
```

These obligations are part of every transition, including records that are
externally supplied or opaque.

### Transition Relation

The abstract transition relation is:

```text
Apply(RuntimeState, RuntimeEvent) -> RuntimeState | Reject
```

A trace is valid when:

1. it starts from an initial state with declared participants, run context,
   capability declarations, and marking policies;
2. every event has a unique `event_id` and satisfies the `BaseEnvelope` rules;
3. every participant-scoped event references an existing participant and an
   existing or explicitly admitted episode; run-scoped records, such as joint
   action records, carry per-participant linkage through member event refs;
4. every event passes field-level marking and redaction policy checks before it
   enters any public runtime surface;
5. every transition preserves append-only history, monotonic participant
   sequence numbers, state revision discipline, and declared ordering;
6. every runtime claim is no stronger than the effective component-wise
   capability vector and the evidence actually recorded.

The state machine rejects an event when accepting it would require hidden truth
to appear as participant-visible observation, infer ordering from wall clock
alone, rewrite history, skip a required redaction, invent participant internals,
or claim a capability stronger than the effective declared support.

### Transitions

`ObserveIntent`
: Records an intent/proposal/trigger when the runtime can observe it.
  Participants that do not expose intent may enter the lifecycle at
  `SelectionOrAdmission`, `ExecutionAttempt`, or a lifecycle envelope with
  `Opaque`, `Unknown`, `NotApplicable`, or `Unsupported` phase realization.

`RecordAdmission`
: Records admission, rejection, withholding, external supply, unknown
  admission, or not-applicable admission. Rejection and withholding terminate
  the attempted action unless a later retry path is explicitly recorded.

`SubmitOperation`
: Creates an operation record for asynchronous or long-running execution.
  Synchronous attempts may skip this transition when the execution attempt and
  result are recorded atomically.

`RecordExecutionAttempt`
: Records the action attempt, action contract, command mapping, actor
  provenance, temporal context, precondition/failure basis, shared-state access
  plan, and optional joint action set.

`AdvanceOperation`
: Advances a long-running operation through submitted, acknowledged, running,
  blocked, partial, completed, failed, timed out, cancelled, unknown, or
  unsupported states. Each advancement is append-only and references the
  predecessor operation record.

`EmitObservation`
: Emits a participant-visible observation through an observation boundary. This
  transition may update the participant-visible projection, but it does not
  expose hidden truth unless an explicit visibility rule permits it.

`EmitStepSignal`
: Emits an RL/MARL/game-style step signal such as action mask, reward, return,
  termination, truncation, or auxiliary info. This transition is optional for
  non-RL participants and must not fabricate signals when the backend does not
  expose them.

`RecordInteractionContext`
: Records the game/environment node semantics for an order point: active agent
  set, current actor, simultaneous group, chance mode and distribution or
  sampled outcome, mean-field distribution update, terminal node, or unsupported
  disclosure. This transition is required before a runtime claim uses AEC,
  simultaneous, chance, or mean-field semantics.

`CommitStateUpdate`
: Writes participant-local, shared operational, visibility, evidence-facing, or
  outcome-facing state records with revision, digest, ordering, provenance,
  markings, and conflict semantics.

`RecordTimeAdvance`
: Records a time-management event such as lookahead declaration,
  time-advance request/grant, step negotiation, message delivery, pacing, or
  unsupported time-management disclosure.

`RecordRollbackOrCompensation`
: Records an optimistic rollback, anti-message, compensation, or supersession
  relation. It never deletes earlier records.

`ResolveConflict`
: Applies a declared conflict policy for a joint action set. The policy may
  coordinate, serialize, reject, retry, withhold, merge, roll back, mark
  unsupported, or record a disclosed weaker guarantee.

`CloseEpisode`
: Uses ADR-013 terminal semantics. It does not rewrite behavior history,
  operation history, observation history, or shared-state history.

### Transition Preconditions And Postconditions

  `ObserveIntent`
: Precondition: episode state is `Running`, or the event is explicitly attached
  to an external trigger admitted before episode start. Postcondition: an
  `IntentOrProposal` envelope exists with phase realization in
  `{Observed, ExternallySupplied, Opaque, Unknown, NotApplicable, Unsupported}`
  and a provenance basis.

`RecordAdmission`
: Precondition: an intent/proposal envelope exists, or admission is the first
  observable boundary for this participant. Postcondition: a
  `SelectionOrAdmission` envelope records phase realization and, when
  applicable, `AdmissionDisposition`. Rejection and withholding prevent an
  execution attempt unless the action contract declares retry, override, or
  deferred-release semantics.

`SubmitOperation`
: Precondition: an admitted action attempt exists, or the operation is an
  externally supplied backend operation with an explicit action contract or
  unsupported-action disclosure. Postcondition: an operation record exists with
  `Submitted` or `Acknowledged` state, idempotency or correlation reference when
  available, timeout policy, cancellation policy, and evidence/provenance basis.

`RecordExecutionAttempt`
: Precondition: the action contract exists or the attempt is labeled as an
  external or unsupported action. Postcondition: an `ExecutionAttempt` envelope
  records action reference, command mapping when available, actor provenance,
  temporal context, read set, possible write set, failure/support basis, and
  operation reference when execution is asynchronous. An attempt may be recorded
  even when proposal or selection is opaque.

`AdvanceOperation`
: Precondition: an operation record exists. Postcondition: the new operation
  state references its predecessor and records progress, partial outputs,
  terminal result, timeout, cancellation, retry, unsupported-state disclosure, or
  error evidence without rewriting earlier operation records.

`EmitObservation`
: Precondition: an execution attempt, operation advancement, state update,
  external event, or scenario rule produces participant-visible information.
  Postcondition: the participant-visible projection is updated only through a
  declared visibility projection, and the envelope declares an
  `InformationGuarantee`.

`EmitStepSignal`
: Precondition: an execution attempt, observation, operation advancement,
  scenario rule, or backend step produces a participant-visible or
  evaluator-visible action mask, reward, return, termination, truncation, or
  auxiliary info signal. Postcondition: the signal references its space,
  visibility projection, order point, state revision basis, and marking policy;
  termination and truncation are represented separately; and no hidden state is
  exposed through `info_refs` unless a visibility rule authorizes it.

`RecordInteractionContext`
: Precondition: a step, joint action, observation, reward, terminal signal, or
  state update makes a claim about turn order, possible/live/active agents,
  simultaneous actors, chance, mean-field, terminal-node, or backend-serialized
  game semantics. Postcondition: an `InteractionContextEnvelope` exists for the
  order point; possible/live/active agent sets, `current_actor`, chance
  disclosure, and mean-field disclosure satisfy `InteractionClaimOK`; and
  related step-signal or joint-action records cite the context.

`CommitStateUpdate`
: Precondition: the update has a stable state address, declared state kind,
  marking policy, and conflict policy or unsupported-concurrency disclosure.
  Postcondition: the written state has a new revision or digest, the read/write
  access record references prior revisions when known, and the event is linked
  to behavior history.

`RecordTimeAdvance`
: Precondition: a joint action, operation, state update, or external
  simulation/federation event depends on time-management semantics stronger
  than wall-clock display order. Postcondition: the time-management context
  records the time domain, mode, logical/simulation time, lookahead,
  request/grant or step-negotiation refs, message send/receive refs, and any
  unsupported disclosure needed for the ordering claim.

`RecordRollbackOrCompensation`
: Precondition: a backend performs or reports optimistic rollback,
  anti-message cancellation, compensation, or supersession. Postcondition: the
  rollback or compensation record references the affected prior events,
  produces superseding records when claims change, preserves append-only
  history, and downgrades replay/order guarantees unless the rollback evidence
  supports the stronger claim.

`ResolveConflict`
: Precondition: two or more attempts in the same joint action set have
  intersecting semantic read/write sets, exclusive resource claims, visibility
  effects, evidence streams, or declared interference. Postcondition: the joint
  action record contains conflict class, conflict policy, realized order or
  unsupported ordering, isolation guarantee, atomicity scope, and
  per-participant observations.

`CloseEpisode`
: Precondition: ADR-013 terminal criteria are met. Postcondition: episode state
  is terminal, behavior history remains append-only, shared-state history is not
  rewritten, and unfinished operations are completed, cancelled, timed out, or
  explicitly marked unsupported/unknown.

### Minimal Observable Trace For Opaque Participants

Opaqueness is bounded; this section resolves what I2 requires of a participant
implementation that exposes nothing voluntarily.

- For an action attempt to support any portable claim, the trace must contain
  at least one lifecycle envelope for it whose phase is `ExecutionAttempt` or
  `StateUpdateCommit`, or an operation record that reaches a terminal
  operation state. Proposal and selection may be opaque or absent, but a fully
  unobservable execution is not a recordable action attempt.
- The minimal valid trace for a fully opaque participant action is therefore
  one `ExecutionAttempt` envelope (or terminal operation record) with a
  declared action-validity basis, plus whatever observations and state updates
  were actually observed. Intent and admission envelopes with `Opaque`
  realization are permitted disclosures, not requirements.
- World or shared-state change with no admissible execution boundary must not
  be presented as a participant action attempt. It may enter the trace only as
  state updates or observations whose `actor_provenance` disclosure records
  the unattributed or external basis; attributing it to a participant then
  requires `SEM-212` attribution evidence, not narrative convenience.
- A silent participant is valid. An episode whose behavior history is empty is
  a valid trace — I2 requires recording observable attempts, not inventing
  them — but it supports only episode lifecycle facts. Behavior,
  information-state, interaction, and outcome claims about that participant
  are unsupported for that episode, and capability or benchmark claims that
  quantify over participant behavior must disclose the silent episode rather
  than dropping it from denominators.

## Observation And Information-State Semantics

The runtime may emit an observation without claiming a complete information
state. Stronger claims require stronger records.

All information-state judgments are relative to a valid trace `tr`, an
effective visibility/redaction policy `policy`, and the schema/projection
version in force at order point `t`. Formulas below therefore use the qualified
history symbol `H_{tr,policy}`. An implementation may use a shorter local name
only after binding `tr` and `policy` explicitly.

The visible-history projection is typed:

```text
Project_p,policy : Ev x P -> Maybe[VisibleEvent]

For a valid trace `tr`:

H_{tr,policy}(p,e,t) =
  VisibleHistory(
    occurrences =
      occurrence_collection(
        Project_p,policy(ev, p)
        for ev in tr whose declared order point is at or before t
        and whose episode scope is e or run-scope-visible-to e
        where Project_p,policy(ev, p) != none),
    visible_order =
      participant-visible restriction of the declared order relation,
    simultaneity_groups =
      participant-visible simultaneity groups,
    delivery_linearization =
      sequence only when a participant-local total delivery order is claimed)
```

A `VisibleEvent` contains only:

```text
VisibleEvent =
  visible_occurrence_id
  visible_event_token
  visible_event_kind
  delivered_order
  visible_payload_ref_or_digest
  visible_action_ref_or_digest
  visible_observation_ref_or_digest
  visible_field_selectors
  marking_projection_digest
  redaction_token_refs
  stochastic_disclosure_ref
  source_projection_version
```

Hidden field values are never members of `VisibleEvent`; redacted values appear
only as stable redaction tokens or omission markers governed by the referenced
redaction policy.

`visible_occurrence_id` is a participant-scoped projected occurrence identifier
generated by `Project_p,policy`. It is unique for each visible occurrence within
the declared participant, episode, visibility policy, and projection version,
including repeated identical or fully redacted observations. `visible_event_token`
is the projected source-event token, stable redaction token, or omission marker
that the participant may see. Multiple occurrences may intentionally share the
same `visible_event_token`; they must not share the same `visible_occurrence_id`.
The global `BaseEnvelope.event_id` is not part of participant-visible history
unless the visibility policy explicitly projects it; otherwise the review/audit
mapping from `visible_occurrence_id` back to the global event is held in
controlled evidence, not in `VisibleHistory`.

Stable redaction tokens are scoped, and the scope is declared, not implied. A
redaction policy that emits stable tokens must declare its token scope — at
minimum the `(participant, episode, redaction policy version, projection
version)` tuple within which token stability holds. Within one scope, the same
hidden value projects to the same token, and token equality may support
reconstruction and information-state claims. Across scopes, token equality
means nothing: reuse of a token string across participants, episodes, or
policy/projection versions must not be readable as identity of the hidden
values, and no claim may rely on cross-scope token equality. Token-to-value
mappings are controlled evidence, never part of `VisibleHistory`. A redaction
policy that cannot declare its token scope, or that cannot keep tokens stable
within it, downgrades dependent information-state claims to `LossyProjection`,
`Unknown`, or `Unsupported`. `visible_occurrence_id` uniqueness is unaffected
by token reuse: distinct deliveries of identically redacted payloads remain
distinct occurrences within their declared scope.

`VisibleHistory.occurrences` is an occurrence-preserving finite collection, not
a mathematical set of payloads. Equal projected payloads, equal redaction tokens,
or repeated no-op observations remain distinct visible occurrences when they
were distinct deliveries to the participant. `VisibleHistory` is not
automatically a total sequence. When the runtime claims only partial order or
simultaneity, the visible history carries the visible partial order and
simultaneity groups. A sequence-valued history is valid only when the runtime
records a participant-local delivery order. If a reconstruction algorithm needs
a sequence but no delivery order is supportable, it must either prove invariance
across all linear extensions of the visible partial order or downgrade the
information guarantee to `LossyProjection`, `Unknown`, or `Unsupported`.
`VisibleEvent.delivered_order` is populated only for events with a claimed
participant-local delivery position; partial-order and simultaneity evidence
belongs to `VisibleHistory.visible_order` and
`VisibleHistory.simultaneity_groups`. Both relations are over
`visible_occurrence_id` values, not global event ids or reusable redaction
tokens.
`visible_payload_ref_or_digest`, `visible_action_ref_or_digest`, and
`visible_observation_ref_or_digest` are also projected identifiers. They must
not expose hidden global record ids, storage keys, source ids, or correlation
handles unless the visibility policy explicitly authorizes that exposure.

Let:

- `O_p,projection,t(s, a?)` map abstract runtime state `s` and optional action
  `a?` to a participant-visible observation envelope, a lossy result, unknown,
  or unsupported.
- `ObsValue(obs)` be the governed observation value or digest carried by an
  observation envelope after visibility projection and redaction.
- `I_tr(p,e,t)` be the `InformationState` RAES claim for participant `p` at
  order point `t`.
- `h1 ~_{p,policy} h2` mean two visible histories are indistinguishable to
  participant `p` under the declared visibility projection, markings, delivery
  timing, stochastic disclosure, noise model, and redaction rules.
- `C_{tr,policy}(p,e,t)` be the bound reconstruction context:
  projection version, redaction policy, visible order relation, simultaneity
  groups, delivery linearization if present, stochastic context, and
  reconstruction algorithm/proof refs in force for `(tr, policy, p, e, t)`.

The indistinguishability relation is defined by visible projection, not by
backend state equality:

```text
h1 ~_{p,policy} h2 iff
  VisiblePayloads(p, h1) = VisiblePayloads(p, h2)
  /\ VisibleActions(p, h1) = VisibleActions(p, h2)
  /\ VisibleObservations(p, h1) = VisibleObservations(p, h2)
  /\ VisibleSelectors(p, h1) = VisibleSelectors(p, h2)
  /\ VisibleMarkingDigests(p, h1) = VisibleMarkingDigests(p, h2)
  /\ VisibleOrderRelation(p, h1) = VisibleOrderRelation(p, h2)
  /\ VisibleSimultaneityGroups(p, h1) =
     VisibleSimultaneityGroups(p, h2)
  /\ VisibleStochasticDisclosures(p, h1) =
     VisibleStochasticDisclosures(p, h2)
```

`~_{p,policy}` must be reflexive, symmetric, and transitive for the recorded
projection version. If redaction or lossy projection prevents stable equality,
the claim must downgrade to `LossyProjection`, `Unknown`, or `Unsupported`.

The observation kernel is:

```text
Z_p,C : StateSpace x ObservationBasis -> ProbabilityMeasure[ObservationValue]

Z_p,C(s, b)(B) =
  probability assigned to measurable projected observation set B
  from abstract runtime state s after governed transition basis b
  under context C
```

The kernel is valid only when:

```text
KernelOK(p,e,t,s,b,tr,policy) =
  let C = C_{tr,policy}(p,e,t) in
  let D = Z_p,C(s, b) in
  ValidTrace(tr)
  /\ VisibilityPolicyOK(policy,tr,p,e,t)
  /\ ObservationBasisOK(b,C,tr,p,e,t)
  /\ ObservationMeasureOK(D,p,e,t,C)
  /\ C.stochastic_context cites a seed/generator, probability model,
     noise model, or downgrade
```

`ObservationValueOK(o,p,e,t)` means `o` is either the value/digest of an
`ObservationEnvelope` satisfying `BaseOK`, `MarkingOK`, visibility projection,
and schema constraints for `(p,e,t)`, or a governed lossy/unknown/unsupported
sentinel allowed by the information guarantee. The kernel ranges over projected
observation values, not over hidden world states.

`ObservationBasisOK(b,C,tr,p,e,t)` validates the cause of the observation
projection without making that cause itself a participant observation. The basis
may be `NoAction`, a single participant action value, a governed joint-action
map, a sampled or deterministic chance outcome, a mean-field distribution
update, or a backend transition basis with a disclosed weaker guarantee. A
`ChanceOutcomeValue` or `MeanFieldDistribution` may change abstract runtime
state and later induce observations, rewards, returns, terminations, or
auxiliary info, but it is not an `ObservationValue` unless a visibility policy
explicitly projects a participant-visible disclosure of that outcome. If the
runtime cannot bind the observation to one of these bases, the observation
claim must downgrade to `LossyProjection`, `Unknown`, or `Unsupported`.

`ObservationMeasureOK(D,p,e,t,C)` validates the distribution family rather than
assuming finite support. For finite discrete observations, `D` may be a
probability mass function with nonnegative probabilities summing to `1` over
support values satisfying `ObservationValueOK`. For continuous or mixed
observation spaces, `D` must cite a governed measurable
observation-space/schema reference, measure or density family, reference/base
measure where a density is used, parameter refs, sampler/probability-model refs,
and projection/redaction basis; the total measure over the governed observation
space must be `1`, and every measurable emitted value must satisfy
`ObservationValueOK` after projection. A sampler is evidence for an exact kernel
only when the governed distribution, sampler algorithm/version, random-source or
seed policy, and audit evidence are all linked. If a continuous or mixed
distribution is represented by samples, bins, quantiles, or another finite
approximation, the approximation method and error bound must be disclosed, and
exact kernel claims downgrade to a bounded capability claim, `LossyProjection`,
`Unknown`, or `Unsupported` as appropriate. Infinite or continuous support is
therefore not itself a reason to downgrade; lack of a governed measurable space,
measure/density basis, sampler audit basis, or approximation bound is.

`VisibilityPolicyOK(policy,tr,p,e,t)` means the policy resolves to governed
visibility and redaction rules for the trace, participant, episode, and order
point, and those rules are the same rules used by `Project_p,policy`,
`H_{tr,policy}`, and `C_{tr,policy}`. If the policy cannot be resolved or
audited, stronger information-state claims downgrade.

Deterministic observations are the degenerate case where the support has one
observation with probability `1`. If the distribution cannot be reconstructed
or bounded, the observation may still be recorded, but the guarantee must
downgrade to `LossyProjection`, `Unknown`, or `Unsupported`.

The reconstructed information state is:

```text
Reconstruct_p :
  VisibleHistory
  x ReconstructionContext
  -> Result[InformationState]

Reconstruct_p(H, C) =
  reconstruct_history_p(initial_information_state_p, H, C)
```

`reconstruct_history_p` is a governed algorithm referenced by
`C.reconstruction_algorithm_ref`; the algorithm version and test/proof artifact
must be stable for the schema version making the claim. If `H` has a total
delivery order, the algorithm may fold over that order. If `H` has only a
partial order or simultaneity groups, the algorithm must state whether it is
order-invariant across all visible linear extensions, consumes the partial
order directly, or downgrades. If no governed algorithm or proof reference
exists, `Reconstruct_p` returns `Unsupported`. If the algorithm reaches a lossy
redaction, aggregation, delayed delivery, unsupported ordering, or unknown
stochastic branch that cannot prove equality with the claimed information
state, it returns `Lossy` or `Unknown`.

Reconstruction algorithms and proofs are registry entries, not prose refs.
`reconstruction_algorithm_ref` and `reconstruction_proof_ref` must resolve
through a versioned reconstruction registry keyed by
`(algorithm_id, algorithm_version, schema_version, projection_version)`. A
registry entry declares: the executable algorithm or normative specification;
its determinism basis; its input contract (total delivery order consumed,
partial order consumed directly, or order-invariance across all visible linear
extensions, with the proof obligation for the invariance case); the fixture
format its conformance tests use; and the proof-artifact format that
`reconstruction_proof_ref` entries must satisfy. A ref that does not resolve
to a registry entry, or whose entry's tests or proof cannot be executed or
audited for the schema/projection version making the claim, makes
`Reconstruct_p` return `Unsupported` and downgrades dependent
history-consistency and perfect-recall claims. Like capability concerns,
reconstruction algorithms cannot be introduced by prose in an adapter
manifest; they are added to the governed registry or they do not exist for
conformance purposes.

`HistoryConsistent` requires:

```text
HistoryConsistent_{p,tr,policy}(e,t) =
  let H = H_{tr,policy}(p,e,t) in
  let C = C_{tr,policy}(p,e,t) in
  Reconstruct_p(H, C)
    = I_tr(p,e,t)
  /\ forall tr1,tr2:
       ValidTrace(tr1) /\ ValidTrace(tr2)
       /\ ReconstructionContextEquivalent(
            C_{tr1,policy}(p,e,t),
            C_{tr2,policy}(p,e,t))
       /\ H_{tr1,policy}(p,e,t) ~_{p,policy} H_{tr2,policy}(p,e,t)
       => I_tr1(p,e,t) = I_tr2(p,e,t)
```

after applying the same redaction tokens and declared lossy transforms used in
the observation envelope. The second conjunct is the review obligation that
visible-history equivalence, not backend-state equality, determines the claimed
information state.

`ReconstructionContextEquivalent(C1, C2)` requires equality or governed
equivalence of every context dimension that can affect reconstruction:
projection version, source projection version, redaction policy, visible order
relation, simultaneity groups, delivery-linearization policy, stochastic/noise
context, reconstruction algorithm ref, reconstruction proof ref, and downgrade
rules. If any dimension is unknown, unsupported, or incomparable, a
history-consistent or perfect-recall claim must downgrade.

`PerfectRecall` additionally requires:

```text
PerfectRecall_{p,tr,policy}(e,t) =
  HistoryConsistent_{p,tr,policy}(e,t)
  /\ forall t' in VisiblePrefixOrderPoints_{tr,policy}(p,e,t):
       PrefixEmbedded(H_{tr,policy}(p,e,t'), H_{tr,policy}(p,e,t))
       /\ forall visible action or observation occurrence x in
            occurrences(H_{tr,policy}(p,e,t')):
            StableVisibleIdentity(x, H_{tr,policy}(p,e,t))
            /\ StableVisibleOrderRelation(x, H_{tr,policy}(p,e,t))
```

`PrefixEmbedded(h_old, h_new)` allows governed compaction only when
`reconstruction_proof_ref` can reproduce the earlier visible prefix or prove
that the compact representation is information-state equivalent. Stable visible
identity includes `visible_occurrence_id`, `visible_event_token`, visible
action/observation reference or digest, and the participant-visible order
relation. Occurrence identity, not token equality, is what prevents repeated
identical or redacted events from collapsing.
`StableVisibleOrderRelation` means that every visible predecessor, successor,
and simultaneity relation involving `x` remains present or is reproduced by the
cited reconstruction proof.
`VisiblePrefixOrderPoints_{tr,policy}(p,e,t)` is the set of order points whose
participant-visible histories are prefixes or lower sets of
`H_{tr,policy}(p,e,t)` under the recorded visible order relation.
Forgetting prior participant-visible actions while keeping only current
observation is therefore not a perfect-recall claim.

`PerfectRecall_{p,tr,policy}` is a constructive witness, not a restatement of
the game-theoretic definition. Perfect recall in Kuhn's sense is a condition on
a participant's information partition — every information set remembers the
participant's prior actions and information sets. The predicate above is a
checkable sufficient condition for that property relative to the recorded
visible projection: prefix embedding plus stable visible identity and order
witnesses that the partition induced by `~_{p,policy}` refines correctly over
time. A conforming implementation claims the witness, and reviewers judge the
partition property through it; asserting the partition property without the
witness is not a valid `PerfectRecall` claim.

For belief-state consumers, RAES may record a belief support:

```text
B_p,t = { s in StateSpace |
          ModelHistory(s, policy, p, e, t)
            ~_{p,policy} H_{tr,policy}(p,e,t) }
```

`ModelHistory` is the visible history generated by a candidate abstract state
trajectory under the same projection and redaction policy; it is not a backend
dump of hidden world truth.

RAES does not require a participant to maintain this belief. It only records
enough visibility, ordering, and stochastic evidence for downstream reviewers
to know whether such a belief or information-state claim is supportable.

Guarantee meanings:

- `ObservationOnly`: only the emitted observation envelope is portable. RAES
  does not claim that `I_tr(p,e,t)` is reconstructible from history.
- `HistoryConsistent`: `HistoryConsistent_{p,tr,policy}(e,t)` holds.
- `PerfectRecall`: `PerfectRecall_{p,tr,policy}(e,t)` holds.
- `LossyProjection`: the observation is sampled, aggregated, delayed, noisy,
  redacted, filtered, or partially unavailable. The envelope records the loss
  descriptor and the claim cannot be stronger than that descriptor supports.
- `Unknown`: the adapter cannot determine the guarantee.
- `Unsupported`: the backend cannot provide the guarantee.

Rules:

- Hidden world truth, scoring state, centralized-training state, backend debug
  state, and archival evidence are not participant-visible observations unless
  an explicit visibility rule projects them to `p`.
- Observation emission, delivery, consumption, and acknowledgement are distinct
  when the backend can observe them. A participant-visible history may include
  an observation only at or after its declared delivery point — the order point
  recorded by `delivery_point_ref` under the declared `delivery_basis` — not
  merely because the backend generated the observation. For observation
  emissions, the declared order point used by the `H_{tr,policy}` projection is
  therefore the delivery point, not the emission point, whenever the two
  differ. If the delivery basis is `Unknown` or `Unsupported`, the observation
  has no portable position in the visible delivery order, and
  history-consistency and perfect-recall claims that depend on delivery order
  must downgrade.
- Rollback, anti-message, compensation, and supersession never rewrite
  participant-visible history. A visible occurrence delivered before a rollback
  remains in `H_{tr,policy}(p,e,t)` at its original order point with its
  original `visible_occurrence_id`. The effect of a rollback on a participant's
  view is expressed only by appending: either a superseding disclosure
  projected as a new visible occurrence, or no participant-visible effect plus
  an evidence-only supersession record. An information-state claim at an order
  point after a rollback must either incorporate the participant-visible
  rollback disclosure into the visible history or downgrade to
  `LossyProjection`, `Unknown`, or `Unsupported`; it must never be computed
  against a retroactively edited history.
- Redacted fields remain part of the record shape as redacted tokens or omitted
  marked fields; the raw hidden value is not part of `H_{tr,policy}(p,e,t)`.
- Stochastic or noisy observations must either disclose a reproducible generator
  reference, seed/randomization context, or noise model reference, or downgrade
  to `LossyProjection`, `Unknown`, or `Unsupported`.
- A history-consistent or perfect-recall claim is invalid if the action,
  observation, projection version, redaction policy, or order context needed to
  reconstruct the information state is missing, or if
  `reconstruction_algorithm_ref` cannot be executed or audited for the relevant
  schema/projection version.
- A centralized-training/global-state view may be recorded as evidence or
  apparatus state, but it must use a distinct scope and marking from
  participant-visible observation.
- An action mask is participant-visible only when projected through the same
  information boundary as the observation or through an explicitly linked
  action-mask envelope.

## RL And Multi-Agent Step Signal Semantics

RAES does not adopt Gymnasium, PettingZoo, or OpenSpiel as wire protocols, but
it preserves the concepts that make RL/MARL results reviewable.

Rules:

- `InteractionContextEnvelope` is required whenever a step claim depends on
  turn order, possible/live/active agent membership, an AEC current actor,
  simultaneous actors, a chance outcome, a mean-field population update, or
  backend serialization. Without it, RAES can record observations but cannot
  claim MARL/game-node semantics.
- In `SequentialTurn` and `AgentEnvironmentCycle` modes, `current_actor_ref`
  must be exactly one participant in `active_agent_set`. Ordinary non-null
  action attempts require that participant to also be in `live_agent_set`.
  Non-acting live participants may receive observations or reward updates only
  when the interaction context records the non-acting-agent policy. AEC cleanup
  turns for terminated or truncated participants may admit only a governed null
  action; that null action is protocol cleanup, not a member of the ordinary
  action space, and the terminal/truncation record must explain why the
  participant is not live.
- In `Parallel` and `Simultaneous` modes, `active_agent_set` is the set of
  participants whose action slots are admitted for that order point. Ordinary
  non-null action slots must be a subset of `live_agent_set`; governed cleanup
  null slots cite their terminal/truncation basis. A joint action or step
  signal must cite the same set or disclose the mismatch.
- In `Chance` mode, participant `action_ref` is null unless a scenario
  explicitly models nature as a participant. The record must cite
  `chance_mode`, a distribution or sampled-outcome disclosure,
  seed/randomization context when available, and the visibility policy that
  determines which participants can observe the chance event.
- In `MeanField` mode, no ordinary participant action is consumed at the node.
  The record must cite the population scope, governed population ids, governed
  population-state support, mean-field distribution ref and digest, update
  rule, update record, and affected observations/rewards or disclose
  unsupported mean-field semantics.
- `action_space_ref` and `observation_space_ref` identify governed space
  definitions. They are required for claims that an action, observation, or
  policy trace is valid relative to an RL/game environment space.
- Action masks are time- and participant-scoped. A mask emitted at `t` cannot
  justify an action at a different order point unless its validity interval,
  state revision basis, and projection rule say so.
- `RewardEnvelope` records participant-visible or evaluator-visible reward.
  Reward is not the same as local action status, objective success, scoring
  state, or episode terminal reason.
- `ReturnEnvelope` records cumulative return over an explicit reward prefix,
  horizon, and discount basis. It cannot be reconstructed from final objective
  success unless an interpretation rule defines that mapping.
- `TerminationEnvelope.terminated` means the task's MDP/game/scenario terminal
  condition has been reached for that participant or environment scope.
  `TerminationEnvelope.truncated` means an external bound, timeout, safety
  limit, or administrative condition ended the step/episode before task
  terminal semantics. These fields must remain separate.
- Per-participant termination/truncation may differ from global episode
  closure. RAES episode closure follows ADR-013 and references the local
  termination/truncation signals when they contributed to closure.
- `info_refs` may preserve auxiliary metrics or debug data, but marked hidden
  state inside an info object is not participant-visible unless a visibility
  projection explicitly exposes it.
- Single-agent, AEC/turn-based, parallel, simultaneous, mean-field, and
  backend-serialized multi-agent surfaces are valid only when their ordering
  and participant-local signal projections are recorded.
- Ordinary lifecycle action records that do not claim RL/MARL/game-node
  semantics do not require an `InteractionContextEnvelope`. The context is
  required exactly when the portable claim depends on step interaction,
  possible/live/active-agent membership, current-actor, chance, mean-field,
  simultaneous, or backend serialization semantics.
- Ordinary lifecycle, cyber-command, human, LLM-tool, playbook, and
  externally supplied actions do not require an RL/game action space. Their
  validity comes from a governed action contract, command/source mapping,
  admission record, actor/capability basis, and evidence/provenance disclosure.
  An `ActionSpace` membership check is required only when the record makes an
  RL/game action-validity claim.

Conformance obligations:

```text
StepInteractionRequired(p,e,t) iff
  any claim at (p,e,t) cites interaction_mode, active_agent_set,
  possible_agent_set, live_agent_set, current_actor_ref,
  simultaneous_group_ref, chance fields, mean-field fields,
  backend-serialized order, termination/truncation-dependent cleanup, or
  RL/MARL/game-node validity

StepActionClaim(a,p,e,t) iff
  the action record claims validity relative to an RL/game action space,
  action mask, legal-action surface, step signal, or game-node transition

ActionAttemptRecordOK(p,e,a,t) =>
  ActionRecordBaseOK(a,p,e,t)
  /\ ActionValidityBasisOK(a,p,e,t)
  /\ (StepActionClaim(a,p,e,t) => StepActionValid(p,e,a,t))

PortableActionValidityClaimOK(a,p,e,t) =>
  ActionAttemptRecordOK(p,e,a,t)
  /\ not UnsupportedOrUnknownActionValidityDisclosed(a,p,e,t)

ActionValidityBasisOK(a,p,e,t) =
  ActionContractValid(a,p,e,t)
  \/ CommandMappingValid(a,p,e,t)
  \/ ExternalTriggerValid(a,p,e,t)
  \/ HumanOrOpaqueAttemptDisclosed(a,p,e,t)
  \/ UnsupportedOrUnknownActionValidityDisclosed(a,p,e,t)

StepActionValid(p,e,a,t) =>
  exists k = interaction_context_at(t):
    StepActorOK(p,k)
    /\ AgentSetDisciplineOK(k)
    /\ ActionContextLinkOK(a,k)
    /\ StepActionKindOK(a,p,e,t)
    /\ (NonNullStepAction(a,p,e,t) =>
         a in ActionSpace(p,e,t)
         /\ (MaskPresent(p,e,t) => MaskAllows(p,e,a,t)))
    /\ (NullStepAction(a,p,e,t) =>
         NullStepActionOK(a,p,e,t,k))

StepActorOK(p,k) =
  (interaction_context(k).interaction_mode = SingleAgent =>
     active_agents(k) = {p}
     /\ (current_actor(k) = none \/ current_actor(k) = p))
  /\ (interaction_context(k).interaction_mode in
        {SequentialTurn, AgentEnvironmentCycle} =>
     active_agents(k) = {p}
     /\ current_actor(k) = p)
  /\ (interaction_context(k).interaction_mode in
        {Parallel, Simultaneous, BackendSerialized} =>
     p in active_agents(k))
  /\ (interaction_context(k).interaction_mode in {Chance, MeanField} =>
     false)

RewardClaimOK(p,e,t) =>
  RewardEnvelope(p,e,t) has reward model, visibility, timing, and source basis

TerminationClaimOK(p,e,t) =>
  terminated and truncated are separate booleans
  /\ terminal observation, if any, is emitted through the observation boundary

InteractionClaimOK(k) =>
  AgentSetDisciplineOK(k)
  /\ (interaction_context(k).interaction_mode = SingleAgent =>
     |active_agents(k)| = 1
     /\ (current_actor(k) = none \/ current_actor(k) in active_agents(k)))
  /\ (interaction_context(k).interaction_mode in
     {SequentialTurn, AgentEnvironmentCycle} =>
     current_actor(k) in active_agents(k) /\ |active_agents(k)| = 1)
  /\ (interaction_context(k).interaction_mode in
        {Parallel, Simultaneous, BackendSerialized} =>
     |active_agents(k)| >= 1 /\ JointActionLinkageOK(k))
  /\ (interaction_context(k).interaction_mode = Chance =>
     active_agents(k) = {}
     /\ ChanceDisclosureOK(k))
  /\ (interaction_context(k).interaction_mode = MeanField =>
     active_agents(k) = {}
     /\ MeanFieldDisclosureOK(k))
```

`AgentSetDisciplineOK(k)` requires `possible_agents(k)`,
`live_agents(k)`, and `active_agents(k)` to resolve to governed participant
sets for the same interaction scope. `live_agents(k)` and `active_agents(k)`
must be subsets of `possible_agents(k)`. An ordinary non-null action slot in
`active_agents(k)` must also be in `live_agents(k)`. A participant outside
`live_agents(k)` may appear in `active_agents(k)` only when the order point is
a governed cleanup slot and `CleanupNullSlotOK(p,k)` cites a matching
termination or truncation record. Any observation, reward, return, action mask,
termination, truncation, or auxiliary-info signal for a live non-acting
participant must either cite the same `live_agent_set_ref` and
`nonacting_agent_policy_ref`, or disclose why the signal is absent,
withheld, unknown, or unsupported.

`ActionContextLinkOK(a,k)` requires the action attempt, action mask, reward,
termination/truncation, and observation records that make a step claim to cite
the same `interaction_context_ref` or to disclose the mismatch. For ordinary
non-step lifecycle actions, `ActionContextLinkOK` is not evaluated.

`StepActionKindOK(a,p,e,t)` requires exactly one of `NonNullStepAction` or
`NullStepAction` to hold for the attempt at that order point. An omitted,
dropped, withheld, externally supplied, unknown, or unsupported action is
recorded through its own admission/realization/support field and must not be
silently treated as a null action.

`NullStepActionOK(a,p,e,t,k)` is true only when the action attempt is a governed
null-action value admitted by `null_action_policy_ref` for the same order point.
It may satisfy an AEC cleanup turn for a participant whose local
termination/truncation record is already true, or a backend-declared no-op slot
in a simultaneous/parallel joint action. It must cite the terminal/truncation
or no-op basis, carry no command/effect payload, and must not be counted as
membership in `ActionSpace(p,e,t)` or as evidence that the participant selected
an ordinary environment action. If a runtime cannot distinguish a protocol null
action from an omitted, dropped, withheld, or unsupported action, the step
validity claim must downgrade.

`CleanupNullSlotOK(p,k)` is true only when the interaction context, null action
policy, and local termination/truncation record agree that `p` is being stepped
solely to complete protocol cleanup. It does not make `p` live, does not
authorize an ordinary action, and does not satisfy legal-action or action-mask
claims except through the governed null-action policy.

`ActionContractValid`, `CommandMappingValid`, `ExternalTriggerValid`, and
`HumanOrOpaqueAttemptDisclosed` are mutually non-exclusive validity bases.
They validate the governed action contract, OpenC2/CACAO/CALDERA/CybORG or
backend source mapping, external-event authority, human/operator provenance,
or opaque adapter disclosure for the action. They do not imply an
`ActionSpace` unless the record also makes `StepActionClaim`.
`UnsupportedOrUnknownActionValidityDisclosed` preserves an observed attempt but
cannot support a stronger validity, legality, or benchmark-comparison claim.
`ActionAttemptRecordOK` is therefore weaker than
`PortableActionValidityClaimOK`: the former says the attempt is recorded with a
declared support basis; the latter says RAES can make a portable validity claim
for it.

`JointActionLinkageOK(k)` requires a governed joint-action record or step-signal
record whose member event refs define a stable map from participant address to
action attempt, null action, withheld action, or unsupported disclosure. The
domain of that map must equal `active_agents(k)` unless the record discloses
added, removed, dropped, or serialized agents. The record must also define the
joint-action tuple/map encoding used for replay and comparison.

`ChanceDisclosureOK(k)` requires a chance mode and either a deterministic
outcome, an explicit probability measure with digest, a sampled-outcome record
with seed/randomization context, or an `Unknown`/`Unsupported` downgrade. When
the mode is `ExplicitStochastic`, the chance distribution must satisfy
`ChanceMeasureOK`: finite discrete distributions must have nonnegative
probabilities summing to one over governed chance outcomes; continuous or mixed
distributions must cite the governed measurable chance-outcome space,
transition-effect schema, measure or density family, reference/base measure
where a density is used, parameter refs, sampler/probability-model refs, and any
participant-visible projection/redaction basis needed to audit how the outcome
is disclosed. Finite approximations to continuous or mixed chance distributions
must disclose the approximation method, support truncation, and error bound.
When the mode is `SampledStochastic`, the sampled outcome must cite the selected
`ChanceOutcomeValue`, transition/effect refs, sampler algorithm/version, and
generator/seed context when available or downgrade the reconstructability claim.
Chance outcomes are environment transition causes; observations induced by them
are emitted through `ObservationEnvelope` records.

`MeanFieldDisclosureOK(k)` requires population scope, governed population ids,
governed population-state support, `MeanFieldDistributionOK`, distribution
digest, update rule, affected observation/reward refs, and update record, or an
`Unknown`/`Unsupported` downgrade. `MeanFieldDistributionOK` validates the
population scope, every governed population id in scope, support membership for
each population, nonnegative weights or density, reference/base measure where a
density is used, parameter or sampler/probability-model refs where applicable,
normalization for the declared single-population or multi-population measure,
approximation method and error bound when finite support is an approximation,
and consistency with the cited update rule. The support may span multiple
populations when rewards or dynamics depend on the whole population
distribution. The mean-field distribution is an
environment state over population support, not a hidden participant action
unless the scenario explicitly models a population process as a participant.

## Concurrency And Conflict Semantics

For attempts `a` and `b` in joint action set `J`, RAES records a conflict when
any of the following hold:

- `write_set(a)` intersects `read_set(b)` or `write_set(b)`;
- `write_set(b)` intersects `read_set(a)` or `write_set(a)`;
- the attempts claim the same exclusive resource, account, channel, tool,
  budget, route, authority, session, or actuator;
- one action contract declares that it can affect the other's preconditions,
  observations, effects, visibility, evidence stream, outcome, or provenance;
- the backend reports contention, dropped work, serialization, rollback, retry,
  rejection, throttling, starvation, or unsupported simultaneity.

### Ordering

The realized order relation is a directed acyclic relation over event ids plus
optional simultaneity groups. It may be total, partial, or explicitly
unsupported. This is the event-structure/trace-theory model of concurrency
(Winskel; Mazurkiewicz): independence and simultaneity are recorded structure,
not an artifact of missing timestamps, and a backend-chosen interleaving is not
ground truth about concurrency.

Rules:

- `before(a,b)` means `a` is ordered before `b` by the declared order basis.
- `simultaneous(a,b)` means the contract treats `a` and `b` as the same
  coordination instant and no order is claimed between them.
- `wall_clock_only` never proves `before(a,b)` by itself. It can support
  display or weak evidence only when the capability vector discloses the weaker
  guarantee.
- Logical-clock and vector-clock contexts are evidence for happens-before
  claims only when the clock authority and update rules are declared.
- `LogicalClock` and `VectorClock` are different claim strengths. A
  `VectorClock` basis claims the Fidge/Mattern characterization: vector
  comparison decides both ordering and causal independence. A scalar
  `LogicalClock` basis is one-directional; it can support `before(a,b)`
  evidence but can never prove that two events are causally unrelated, so
  causal-independence or simultaneity claims from scalar clocks must
  downgrade.
- Simulation tick order, control-plane order, and serialized backend order are
  different claims and must not be collapsed.

### Time Management

Time-management claims are separate from ordering claims. A record may have
valid ordering evidence without supporting real-time pacing, HLA time
management, optimistic rollback, DEVS transition semantics, or FMI
co-simulation semantics.

Rules:

- `WallClockRealtime` supports pacing and display claims only. It does not
  prove causality or simultaneity.
- `ConservativeLogicalTime` requires a declared safe-delivery rule. If
  lookahead is used, a message with timestamp `ts` may be delivered only when
  the receiver's grant and lookahead make earlier conflicting messages
  impossible under the declared clock authority.
- `HlaTimeManaged` requires explicit time-regulating/time-constrained
  disclosure, lookahead where relevant, time-advance request/grant refs, and
  message send/receive refs for causality claims.
- `OptimisticRollback` requires rollback refs, anti-message or compensation
  refs when messages are cancelled, superseded event refs, and a disclosure of
  which prior observations or state updates remain participant-visible after
  rollback.
- `DevsDiscreteEvent` requires an internal, external, or confluent transition
  basis and a time-advance function or unsupported disclosure for the modeled
  component.
- `FmiCoSimulation` requires step-size or step-negotiation refs, exchanged
  input/output variable refs, rollback support or no-rollback disclosure, and
  clock-domain mapping.
- `BackendSerialized` is a weaker realization. It supports review of realized
  order but not a claim that participants acted simultaneously unless a
  separate simultaneity proof exists.

Append-only rollback discipline:

```text
RollbackOK(r) =
  affected_events(r) subset prior_events
  /\ superseding_events(r) are appended after r
  /\ no prior event is deleted or mutated
  /\ every downstream claim cites either prior or superseding lineage
```

### Isolation And Atomicity

The isolation vocabulary is anchored in the transaction-isolation literature:
Berenson et al.'s critique of the ANSI SQL isolation levels defines the anomaly
taxonomy and snapshot isolation, and Adya's generalized isolation theory gives
the implementation-independent serialization-graph definitions that make these
levels portable claims rather than vendor labels. RAES uses those meanings;
`Causal` follows the causal-consistency usage in the distributed-systems
literature rather than an ANSI level.

Every joint action that reads or writes shared operational state declares:

- `snapshot_basis`: the state revisions each attempt read;
- `isolation_guarantee`: serializable, snapshot, causal, read-committed,
  best-effort, unknown, or unsupported;
- `atomicity_scope`: single-state, multi-state, per-participant, per-action,
  joint-action, backend-transaction, or unsupported;
- `rollback_refs` when the backend rolled back or compensated state.

Multi-object updates are portable only when the atomicity scope and all affected
state revisions are recorded. Snapshot claims are invalid without the read
revision set. Serializable claims are invalid without a realized order or proof
obligation showing equivalence to a serial order.

### Conflict Policy

Policy meanings:

- `Coordinate`: the runtime or backend coordinates attempts before execution.
- `Serialize`: the runtime or backend chooses a realized order. Portable only
  with realized order and read/write revisions.
- `Reject`: at least one attempt is denied and records an admission disposition
  or operation failure.
- `Retry`: at least one attempt is retried with retry bound, new predecessor
  refs, and updated read revisions.
- `Withhold`: an attempt is intentionally not released.
- `Merge`: concurrent effects are merged. Portable only when the action
  contract declares commutativity or an explicit merge rule.
- `Rollback`: an attempted effect is undone or compensated with rollback refs.
- `DiscloseWeakGuarantee`: the backend can report what happened but cannot
  satisfy the stronger required semantics.
- `Unsupported`: the backend cannot supply a portable conflict semantics.

Fairness and liveness claims are bounded claims. If RAES says a retry policy is
fair or starvation-free, the retry bound, scheduler basis, or proof obligation
must be present. Otherwise the claim must be limited to observed outcome facts.

Named semantic gates for PRT-10:

```text
ConflictOK(j, tr) =
  JointActionRecordBaseOK(j, tr)
  /\ ConflictPredicateConsistent(j, tr)
  /\ IsolationAtomicityOK(j, tr)
  /\ ConflictPolicyOK(j, tr)
  /\ RollbackRetryOK(j, tr)
  /\ NoUnsupportedConcurrencyOverclaim(j, tr)

TimeManagementOK(tm, tr) =
  TimeManagementContextBaseOK(tm, tr)
  /\ TimeModeEvidenceOK(tm, tr)
  /\ TimeClaimStrengthOK(tm, tr)
  /\ RollbackTimeLineageOK(tm, tr)
  /\ NoUnsupportedTimeOverclaim(tm, tr)
```

`JointActionRecordBaseOK(j, tr)` requires every member event, participant,
state revision, clock authority, time-management context, capability vector,
retry policy, rollback ref, and participant observation ref in `j` to resolve in
`tr` or in immutable run initialization. The record's
`realized_order_relation`, `snapshot_basis`, read/write sets,
exclusive-resource claims, `conflict_class`, and `conflict_policy` are
interpreted only under those resolved refs.

`ConflictPredicateConsistent(j, tr)` requires the declared conflict class to
cover every conflict implied by read/write intersections, exclusive-resource
claims, action-contract interference, and backend-reported contention,
serialization, rollback, retry, rejection, throttling, starvation, or
unsupported simultaneity. If any member's read/write set or resource claim is
unknown, the record may report observed outcomes, but exact no-conflict,
serializable, or simultaneity claims must downgrade.

`IsolationAtomicityOK(j, tr)` requires snapshot claims to cite the read revision
set, serializable claims to cite a realized serial order or proof obligation,
and multi-object atomicity claims to cite all affected state revisions and the
declared atomicity scope. `best_effort`, `unknown`, and `unsupported` isolation
values are valid disclosures, but they cannot support stronger isolation or
benchmark-comparison claims.

`ConflictPolicyOK(j, tr)` validates policy-specific evidence: `Serialize`
requires realized order and read/write revisions; `Reject` requires admission
or operation-failure evidence for the denied attempts; `Retry` requires retry
policy, retry bound, predecessor refs, and updated read revisions; `Withhold`
requires withholding disposition; `Merge` requires a governed commutativity or
merge rule; `Rollback` requires rollback or compensation refs satisfying
`RollbackOK`; `DiscloseWeakGuarantee` and `Unsupported` require an explicit
downgrade and forbid exact simultaneity, serializability, or conflict-resolution
claims.

`RollbackRetryOK(j, tr)` requires every rollback, anti-message, compensation, or
retry record cited by `j` to be append-only, to cite affected prior events, to
name superseding events when effects are replaced, and to preserve or downgrade
participant-visible observation and replay claims after the correction.
Fairness, starvation-free, and eventual-retry claims additionally require a
scheduler basis, retry bound, or proof obligation.

`NoUnsupportedConcurrencyOverclaim(j, tr)` requires the effective capability
vector for ordering, isolation, rollback, conflict resolution, observer,
redaction, and replay concerns to satisfy the claim. A weak backend coordinator
or adapter limits the portable claim even when the native backend can execute a
stronger operation internally.

`TimeManagementContextBaseOK(tm, tr)` requires the time context id, time domain,
mode, clock authority, logical/simulation/wall-clock fields, lookahead,
time-advance refs, message refs, pacing policy, step-size refs, rollback refs,
anti-message or compensation refs, superseded-event refs, and transition basis
needed by the asserted time claim to resolve in `tr` or immutable run
initialization.

`TimeModeEvidenceOK(tm, tr)` validates the selected mode: `WallClockRealtime`
supports pacing/display only; `ConservativeLogicalTime` requires a safe-delivery
rule and lookahead/grant evidence where used; `HlaTimeManaged` requires
time-regulating/time-constrained disclosure, time-advance request/grant refs,
lookahead when relevant, and send/receive refs for causality claims;
`OptimisticRollback` requires rollback, anti-message or compensation, and
supersession evidence; `DevsDiscreteEvent` requires internal, external, or
confluent transition basis plus time-advance support or unsupported disclosure;
`FmiCoSimulation` requires step-size or step-negotiation refs, exchanged
input/output variable evidence in the cited step-negotiation record, rollback
support or no-rollback disclosure, and clock-domain mapping; `BackendSerialized`
supports realized-order review but not simultaneity without a separate proof.

`TimeClaimStrengthOK(tm, tr)` ensures time-management claims stay separate from
ordering claims. Ordering evidence may support happens-before, but it does not
by itself support pacing, HLA time management, optimistic rollback, DEVS
transition semantics, FMI co-simulation, or true simultaneity. Wall-clock-only
data cannot support causality or simultaneity.

`RollbackTimeLineageOK(tm, tr)` requires rollback and anti-message claims to
satisfy `RollbackOK`, identify affected prior messages or events, append
superseding events after the rollback record, and disclose which prior
participant-visible observations or state updates remain visible after
rollback.

`NoUnsupportedTimeOverclaim(tm, tr)` requires the effective capability vector
for clock authority, lookahead, pacing, synchronization, rollback,
step-negotiation, observer, redaction, and replay concerns to satisfy the
asserted time-management claim. Unknown or unsupported mode-specific evidence
must downgrade the claim rather than silently falling back to timestamp order.

## Capability Guarantee Vectors

A capability guarantee is a component-wise partial order over concern vectors.
The effective runtime capability for a claim is the meet of the declared
capabilities for every component that can weaken that claim.

Runtime components are:

```text
CapabilityComponent =
  participant_adapter
  runtime_coordinator
  backend_engine
  observation_apparatus
  evidence_store
  redaction_policy
  clock_authority
  replay_engine
  benchmark_harness
```

Let `G_component` be a component vector and `R_claim` be the required vector for
a claim. Effective guarantee is:

```text
effective_capability[concern] =
  meet({ G_component[concern] | component affects concern })
```

The meet operator uses the guarantee order:

```text
unsupported < disclosed_weak < bounded < exact
```

Rules:

- `meet(exact, bounded) = bounded`.
- `meet(x, unsupported) = unsupported`.
- `meet(x, disclosed_weak) <= disclosed_weak` unless all weakening components
  are marked `not_applicable` for that concern.
- `not_applicable` is neutral only when the contract states that the concern
  has no semantic role for the claim.
- Missing value for a required concern is `Reject`, not `not_applicable`.
- The meet for a concern ranges over every component that affects that
  concern, not only over the components that chose to declare it. A component
  that affects a concern but declares no value contributes `unsupported` to
  the meet; silence is never neutral. This is distinct from the rule above:
  when the concern is required by the claim, the undeclared value is a
  capability validation failure (`Reject`) before any meet is computed; when
  the concern is optional for the claim, the undeclared component still drags
  the effective value to `unsupported` rather than being skipped.
- `not_applicable` must be declared, never inferred from absence. Only a
  declared `not_applicable` — with the contract stating the concern has no
  semantic role for that component — is removed from the meet.

`G` satisfies `R` only when every required concern appears in the effective
vector with strength greater than or equal to the required strength:

```text
satisfies(G, R) =
  for all concern in required(R):
    concern in domain(G)
    /\ G[concern] != not_applicable
    /\ G[concern] >= R[concern]
```

Two vectors are incomparable when each is stronger on at least one required
concern and weaker on another. Implementations must not collapse vectors to one
scalar minimum unless the claim being made explicitly requires all dimensions
and the minimum is reported as a conservative summary, not as the backend's full
capability.

Examples:

- A backend with exact ordering and weak redaction does not satisfy a claim that
  requires bounded ordering and bounded redaction.
- A backend with exact observation history and unsupported conflict resolution
  can support a single-agent information-state claim, but it cannot support a
  concurrent shared-state comparison claim.
- A backend with serialized backend order can support a review claim about the
  realized order, but it cannot claim true simultaneity.
- A backend with exact replay but an evidence store that truncates raw
  observations without hashes has bounded or weak provenance, not exact
  provenance.
- A clock authority with unsupported lookahead makes HLA-style time-management
  claims unsupported even if the backend records event order exactly.

Every downgrade is recorded as a capability disclosure linked to the event or
joint action it affects. Diagnostics may repeat the downgrade, but diagnostics
are not the portable semantics.

Capability registries are versioned. A concern cannot be introduced by prose in
an adapter manifest; it must be added to the governed concern registry with
applicability, ordering, required evidence, and downgrade behavior.

## Security Markings And Redaction

Runtime records that can carry sensitive data must have field-level policy.

Rules:

- Markings apply to records and to individual fields through
  `granular_markings`.
- `marking_definition_refs` identify governed marking definitions. Free-text
  labels may be preserved as source labels, but they do not define disclosure
  semantics.
- `object_marking_refs` apply to the complete record; `granular_markings`
  apply to selector paths inside the record. Selectors must be stable under the
  published schema version.
- A redaction policy states which fields are omitted, replaced by stable
  redaction tokens, summarized, hashed, or moved to controlled evidence.
- Authorization checks apply before data enters public runtime envelopes,
  diagnostics, audit details, snapshots, fixtures, generated schemas, or
  changelog fragments.
- Raw credential values, bearer tokens, hidden answer keys, private prompts,
  chain-of-thought, model activations, private memory, backend exceptions, and
  unredacted command output must not appear in portable runtime records unless a
  specific evidence contract defines a safe representation.
- Redaction must preserve enough stable identity to support provenance and
  replay claims. If it cannot, the affected claim must be downgraded.
- Marking enforcement and visibility projection compose by intersection,
  deny-first. A field value is participant-visible only when the visibility
  projection projects it and the marking/authorization policy authorizes that
  participant as a consumer. Neither surface can widen the other: a visibility
  rule that purports to expose a field a marking denies does not win — the
  trace is invalid (`MarkingOK` fails) — and a marking authorization alone
  never makes a field participant-visible without a projecting visibility
  rule. Redaction policy is evaluated after this intersection and determines
  representation (omission, stable token, summary, hash), never authorization.

## Asynchronous And Long-Running Operations

Cyber actions often start, block, stream observations, partially succeed, time
out, or complete after later state changes. RAES models these with operation
records rather than by inventing participant-internal lifecycle phases.

Operation records carry:

```text
OperationRecord =
  BaseEnvelope
  operation_id
  action_ref
  action_contract_ref
  command_ref
  state
  predecessor_operation_ref
  idempotency_ref
  correlation_ref
  progress_refs
  streamed_observation_refs
  partial_result_refs
  timeout_policy_ref
  cancellation_policy_ref
  retry_policy_ref
  terminal_result_ref
```

Rules:

- A long-running action starts with `SubmitOperation` or
  `RecordExecutionAttempt`.
- Each operation advancement is append-only and references its predecessor.
- Partial progress can emit observations and state updates before terminal
  completion.
- Timeout and cancellation are operation states, not episode terminal reasons.
- Retries create new lifecycle/operation records linked by predecessor refs.
- A backend that can only report start and final status must declare a weaker
  operation-state guarantee.

## Cyber Action Semantics

Portable cyber action envelopes carry:

```text
CyberActionEnvelope =
  BaseEnvelope
  action_ref
  action_contract_ref
  command_ref
  command_family
  action_verb
  target_ref
  argument_refs
  openc2_profile_ref
  openc2_command_id
  openc2_request_id
  openc2_action
  openc2_target_ref
  openc2_args_ref
  openc2_actuator_ref
  openc2_response_ref
  openc2_response_status
  openc2_response_status_text
  openc2_response_results_ref
  cacao_playbook_ref
  cacao_workflow_step_ref
  cacao_workflow_step_type
  cacao_command_refs
  cacao_agent_refs
  cacao_target_refs
  cacao_variable_refs
  cacao_authentication_ref
  cacao_on_completion_ref
  cacao_on_success_ref
  cacao_on_failure_ref
  cacao_external_refs
  caldera_operation_ref
  caldera_adversary_ref
  caldera_planner_ref
  caldera_ability_ref
  caldera_link_ref
  caldera_fact_refs
  caldera_agent_ref
  actuator_ref
  executor_ref
  session_ref
  authority_ref
  privilege_context_ref
  credential_ref
  tool_ref
  playbook_step_ref
  attack_technique_refs
  knowledge_delta_refs
  foothold_delta_refs
  visibility_delta_refs
  detection_surface_refs
  response_refs
  observation_refs
  outcome_refs
```

Rules:

- `credential_ref` points to a redacted or controlled evidence/state reference,
  never a raw credential value.
- OpenC2 mappings preserve command/response correlation through
  `openc2_command_id`, `openc2_request_id`, and response refs. RAES lifecycle
  success or failure is not inferred from source response text without a
  normalized status mapping.
- CACAO mappings preserve playbook/workflow-step identity, commands,
  agents/targets, variables, authentication references, external references,
  and success/failure routing when those facts support behavior or outcome
  claims.
- CALDERA mappings preserve operation/adversary/planner/ability/link/fact/agent
  identity when those facts support behavior, knowledge, foothold, detection,
  or provenance claims.
- Command mappings may cite OpenC2 actions/targets, CACAO playbook steps,
  CALDERA abilities/links/facts, ATT&CK techniques, CybORG actions, or
  backend-native commands as source mappings. Those mappings do not define RAES
  semantics by themselves.
- Knowledge, foothold, visibility, and detection deltas must be state records or
  evidence references when used to support outcome or attribution claims.
- Backend-native success or failure strings are source labels until normalized
  into RAES lifecycle, operation, observation, state, and outcome records.

## Benchmark And Reproducibility Context

Participant-runtime records are not a full experiment-management system, but
benchmark claims require an auditable runtime context:

```text
RunContext =
  run_id
  study_id
  trial_id
  repeat_id
  replicate_id
  replicate_count
  replicate_policy_ref
  scenario_ref
  scenario_version
  contract_bundle_digest
  backend_manifest_digest
  backend_version_ref
  participant_implementation_refs
  participant_adapter_refs
  participant_scaffold_refs
  model_or_policy_version_refs
  tool_version_refs
  seed_refs
  randomization_policy_ref
  treatment_assignment_ref
  assignment_policy_ref
  assignment_unit_ref
  blocking_factor_refs
  blinding_or_masking_ref
  run_config_digest
  evaluator_refs
  evaluator_version_refs
  evaluator_leakage_model_ref
  scoring_refs
  result_metric_refs
  aggregation_plan_ref
  confidence_interval_policy_ref
  statistical_test_policy_ref
  effect_size_policy_ref
  power_or_precision_target_ref
  baseline_refs
  baseline_version_refs
  baseline_eligibility_policy_ref
  comparison_cohort_ref
  paired_run_group_ref
  statistical_plan_ref
  preregistration_ref
  assistance_disclosures
  scaffold_exposure_matrix_ref
  holdout_exposure_labels
  holdout_asset_digest_refs
  canary_exposure_labels
  canary_policy_ref
  contamination_audit_refs
  contamination_audit_procedure_ref
  training_corpus_disclosure_refs
  dataset_split_ref
  training_data_cutoff_ref
  participant_knowledge_cutoff_ref
  cost_trace_refs
  cost_normalization_policy_ref
  resource_trace_refs
  hardware_profile_refs
  software_profile_refs
  timeout_budget_refs
  retry_policy_ref
  exclusion_policy_ref
  exclusion_decision_refs
  artifact_immutability_refs
  evidence_manifest_ref
  research_object_manifest_ref
  license_or_access_policy_refs
  environment_build_refs
```

Explicit benchmark validity claims carry:

```text
BenchmarkValidityClaim =
  BaseEnvelope
  claim_id
  claim_type
  run_context_ref
  population_scope_ref
  metric_refs
  aggregation_plan_ref
  replicate_set_ref
  unit_of_analysis_ref
  confidence_interval_ref
  statistical_test_ref
  effect_size_ref
  minimum_effect_or_margin_ref
  baseline_refs
  baseline_eligibility_policy_ref
  comparison_cohort_ref
  paired_run_group_ref
  treatment_assignment_ref
  assignment_policy_ref
  assignment_unit_ref
  statistical_plan_ref
  preregistration_ref
  evaluator_version_refs
  evaluator_leakage_model_ref
  exclusion_policy_ref
  exclusion_decision_refs
  retry_policy_ref
  cost_normalization_policy_ref
  contamination_audit_refs
  contamination_audit_procedure_ref
  holdout_non_exposure_evidence_refs
  canary_evidence_refs
  scaffold_exposure_matrix_ref
  artifact_immutability_refs
  validity_threat_refs
  validity_threat_mitigation_refs
  correspondence_evidence_refs
  conclusion_scope
  unsupported_or_unknown_limits
```

The referenced benchmark support records have minimum contents. A ref that
points only to prose, a dashboard, or a final score is insufficient for a
portable comparative claim:

```text
MetricSpec =
  metric_id
  outcome_mapping_ref
  measurement_procedure_ref
  unit
  direction
  denominator
  missingness_policy_ref
  evaluator_visibility_scope

AggregationPlan =
  aggregation_id
  metric_refs
  unit_of_analysis_ref
  grouping_or_blocking_refs
  weighting_policy_ref
  missingness_policy_ref
  outlier_policy_ref
  summary_statistics

ReplicateSet =
  replicate_set_id
  run_refs
  replicate_count
  repeat_identity_policy_ref
  randomization_block_refs
  paired_run_group_refs
  exclusion_decision_refs

StatisticalPlan =
  statistical_plan_id
  estimand
  unit_of_analysis_ref
  analysis_design
  comparison_design
  paired_or_blocked_model
  clustering_basis_ref
  uncertainty_method
  interval_level
  statistical_test_family
  effect_size_definition
  equivalence_or_noninferiority_margin
  multiple_comparison_policy_ref
  power_or_precision_target_ref
  preregistration_ref

EvaluatorLeakageModel =
  leakage_model_id
  evaluator_refs
  evaluator_version_refs
  public_material_labels
  private_material_labels
  allowed_evaluator_inputs
  forbidden_evaluator_inputs
  oracle_or_gold_access_policy_ref
  audit_evidence_refs

ExposureAuditProcedure =
  exposure_audit_id
  scaffold_exposure_matrix_ref
  holdout_asset_digest_refs
  canary_policy_ref
  canary_evidence_refs
  training_corpus_disclosure_refs
  participant_knowledge_cutoff_ref
  audit_method
  audit_limitations

CostNormalizationPolicy =
  cost_policy_id
  cost_dimensions
  normalization_unit
  included_resources
  excluded_resources
  hardware_profile_refs
  software_profile_refs
  timeout_budget_refs
  retry_cost_policy_ref

TreatmentAssignment =
  treatment_assignment_id
  assigned_unit_refs
  treatment_refs
  assignment_mechanism
  assignment_unit_ref
  assignment_time
  assignment_policy_ref
  randomization_block_refs
  blocking_factor_refs
  seed_or_rng_ref
  allocation_concealment_ref
  blinding_or_masking_ref
  deviation_refs

ValidityThreatDisclosure =
  validity_threat_id
  validity_dimension
  affected_claim_refs
  threat_statement_ref
  evidence_refs
  mitigation_refs
  residual_limit_ref

CorrespondenceEvidence =
  correspondence_ref
  conceptual_model_ref
  realized_testbed_ref
  requirement_refs
  observation_or_measurement_refs
  comparison_method_ref
  acceptance_criterion_ref
  residual_gap_refs

ArtifactImmutabilityEvidence =
  artifact_set_id
  artifact_refs
  artifact_role_assignments
  required_role_policy_ref
  digest_refs
  registry_or_storage_refs
  version_refs
  build_environment_refs
  retrieval_time
```

`uncertainty_method` is a governed value such as `frequentist`, `bootstrap`,
`bayesian`, `exact`, or `descriptive_only`. `descriptive_only` cannot support a
portable superiority, equivalence, non-inferiority, comparative score/effect,
cost-normalized comparative score/effect, confidence/credible interval,
statistical test, effect-size, margin, or statistical non-contamination-rate
conclusion. A descriptive cost-normalized metric, such as a score per declared
cost unit or success rate under a fixed budget, may use `descriptive_only` when
the conclusion scope excludes comparative/effect claims and `CostOK` validates
the cost/resource basis. A non-contamination or evaluator-leakage conclusion
may be audit-only and governed by exposure and leakage evidence rather than
metric-analysis evidence; if it also reports a score, rate, effect, interval,
or test, the conclusion scope must include the corresponding result-analysis
tag and satisfy the metric, replication, and uncertainty predicates for that
result.

Rules:

- Repeated runs must have distinct `repeat_id` or equivalent identity.
- Comparative claims require a statistical plan, replicate identity and count,
  baseline version, evaluator version, comparison cohort, retry/exclusion
  policy, cost/resource normalization policy, and at least one governed
  baseline member. An empty baseline set cannot support a comparative,
  superiority, equivalence, or non-inferiority conclusion.
- Comparative, causal-treatment, superiority, equivalence, non-inferiority, and
  other assignment-dependent claims require a governed treatment-assignment
  record or an explicit downgrade. The assignment record names the assignment
  unit, treatment arms, assignment mechanism, randomization or blocking basis,
  allocation-concealment/blinding status when applicable, seed or RNG basis when
  randomization is claimed, and deviations from the assignment policy.
- Benchmark-validity claims must disclose validity threats at the conclusion
  scope they assert. At minimum the disclosure distinguishes construct,
  internal, external, statistical-conclusion, and cyber-range/testbed
  correspondence threats, links each threat to affected claims, cites mitigation
  evidence when mitigation is claimed, and records residual limits.
- Statistical plans must define the unit of analysis, metric aggregation,
  uncertainty interval, effect-size or equivalence margin when relevant, and
  how paired or clustered runs are handled. A final score without these fields
  is a descriptive result, not a portable comparative claim.
- Benchmark validity claims are graph-scoped to one run context. For
  result-analysis conclusions, the metrics, aggregation plan, statistical plan,
  and replicate set cited by the claim must be scoped to that run context or to
  an explicitly declared comparison cohort that includes it. For audit-only
  evaluator-leakage or non-contamination conclusions, those metric-analysis
  refs may be governed not-applicable records, but evaluator, exposure,
  exclusion/retry, cost when applicable, and artifact refs still must be scoped
  to the run context. Mixing support records from unrelated runs is invalid.
- Metric and analysis support records must validate their declared denominator,
  aggregation grouping/blocking, weighting, randomization blocks, statistical
  test family, effect-size or equivalence margin, and power/precision target.
  A field listed in a support record is not merely documentary.
- Exclusions and retries must be interpreted through the preregistered or
  otherwise disclosed policy and recorded as decision refs. Dropped failed
  attempts, evaluator crashes, manual interventions, or timeout retries cannot
  be hidden inside aggregate metrics.
- Baselines are comparable only when their participant implementation,
  scaffold/tool exposure, evaluator, scenario, cost/resource normalization, and
  allowed assistance satisfy the same eligibility policy or the mismatch is
  disclosed in the claim limits.
- Evaluator leakage claims require an evaluator leakage model, evaluator
  version refs, public/private material labels, and contamination-audit
  procedure refs. Runtime records alone do not prove that an evaluator, scaffold,
  or agent could not access hidden material.
- Artifacts used in a comparative claim must cite immutable digests or
  equivalent registry/version evidence for scenario, contract bundle, evaluator,
  baseline, scaffold, participant implementation, and backend manifest.
- Seed/randomization claims require seed refs or an unsupported/unknown
  disclosure.
- Scaffold, tool, model, policy, and human assistance exposure must be disclosed
  when used for benchmark comparison.
- Cost/resource traces may be summarized or redacted, but the loss must be
  disclosed when it affects comparison.
- Holdout and canary labels must not reveal hidden answers to participants.
  Claims about non-exposure require holdout asset digests, canary policy,
  scaffold exposure matrix, and contamination-audit evidence or a disclosed
  unsupported claim.
- Runtime records alone do not prove benchmark validity. They preserve the
  evidence needed for an external study design to make a valid comparison.

Benchmark conformance predicates:

```text
BenchmarkClaimOK(claim) =
  ConclusionScopeOK(claim.conclusion_scope)
  /\ RunContextOK(claim.run_context_ref, claim.conclusion_scope)
  /\ BenchmarkContextLinkageOK(claim)
  /\ MetricsOK(claim.metric_refs,
               claim.aggregation_plan_ref,
               claim.conclusion_scope)
  /\ ReplicationOK(claim.replicate_set_ref,
                   claim.unit_of_analysis_ref,
                   claim.paired_run_group_ref,
                   claim.conclusion_scope)
  /\ UncertaintyOK(claim.statistical_plan_ref,
                   claim.preregistration_ref,
                   claim.confidence_interval_ref,
                   claim.statistical_test_ref,
                   claim.effect_size_ref,
                   claim.minimum_effect_or_margin_ref,
                   claim.conclusion_scope)
  /\ BaselineComparabilityOK(claim.baseline_refs,
                             claim.comparison_cohort_ref,
                             claim.baseline_eligibility_policy_ref,
                             claim.conclusion_scope)
  /\ TreatmentAssignmentOK(claim.treatment_assignment_ref,
                           claim.assignment_policy_ref,
                           claim.assignment_unit_ref,
                           claim.conclusion_scope)
  /\ EvaluatorLeakageOK(claim.evaluator_leakage_model_ref,
                        claim.conclusion_scope)
  /\ ExposureOK(claim.scaffold_exposure_matrix_ref,
                claim.holdout_non_exposure_evidence_refs,
                claim.canary_evidence_refs,
                claim.contamination_audit_refs,
                claim.conclusion_scope)
  /\ ExclusionRetryOK(claim.exclusion_policy_ref,
                      claim.exclusion_decision_refs,
                      claim.retry_policy_ref,
                      claim.conclusion_scope)
  /\ CostOK(claim.cost_normalization_policy_ref, claim.conclusion_scope)
  /\ ValidityThreatsOK(claim.validity_threat_refs,
                       claim.validity_threat_mitigation_refs,
                       claim.correspondence_evidence_refs,
                       claim.conclusion_scope)
  /\ ArtifactImmutabilityOK(claim.artifact_immutability_refs, claim)
```

The predicates above are defined as follows:

Primitive helper predicates used below are schema validators, not informal
placeholders. `Present(x, ...)` means each argument is non-null and resolves to
a governed record of the expected type; `NonEmpty(x)` means a resolved sequence
has at least one member; `DigestPinned`, `VersionPinnedOrDigestOnly`, and
`RegistryOrStorageOK` validate the corresponding immutability evidence. Other
`*OK` helpers resolve and validate the support-record type named in the helper.
If a future implementation cannot provide such a validator, the parent
predicate returns `Unknown` or `Unsupported`.

```text
RunContextOK(run_context_ref, conclusion_scope) =
  exists ctx = RunContext(run_context_ref):
    Present(ctx.run_id, ctx.study_id, ctx.trial_id)
    /\ Present(ctx.scenario_ref, ctx.scenario_version)
    /\ Present(ctx.contract_bundle_digest, ctx.backend_manifest_digest)
    /\ Present(ctx.run_config_digest)
    /\ Present(ctx.participant_implementation_refs)
    /\ Present(ctx.participant_adapter_refs)
    /\ ParticipantApparatusOK(ctx.participant_scaffold_refs,
                              ctx.model_or_policy_version_refs,
                              ctx.tool_version_refs)
    /\ Present(ctx.evaluator_refs, ctx.evaluator_version_refs)
    /\ EvaluatorAndScoringOK(ctx.evaluator_refs,
                             ctx.evaluator_version_refs,
                             ctx.scoring_refs)
    /\ AssistanceDisclosureOK(ctx.assistance_disclosures)
    /\ (Present(ctx.seed_refs)
        \/ RandomizationPolicyDisclosesNoSeed(ctx.randomization_policy_ref))
    /\ BenchmarkPolicyRefsOK(ctx.retry_policy_ref,
                             ctx.exclusion_policy_ref,
                             ctx.exclusion_decision_refs)
    /\ (ResultAnalysisConclusion(conclusion_scope) =>
        Present(ctx.result_metric_refs,
                ctx.aggregation_plan_ref,
                ctx.statistical_plan_ref,
                ctx.replicate_policy_ref)
        /\ ctx.replicate_count >= 1)
    /\ (ComparativeConclusion(conclusion_scope) =>
        Present(ctx.statistical_plan_ref,
                ctx.baseline_refs,
                ctx.baseline_version_refs,
                ctx.baseline_eligibility_policy_ref,
                ctx.comparison_cohort_ref,
                ctx.treatment_assignment_ref,
                ctx.assignment_policy_ref,
                ctx.assignment_unit_ref))
    /\ (TreatmentAssignmentConclusion(conclusion_scope) =>
        Present(ctx.treatment_assignment_ref,
                ctx.assignment_policy_ref,
                ctx.assignment_unit_ref))
    /\ (NonContaminationConclusion(conclusion_scope) =>
        Present(ctx.scaffold_exposure_matrix_ref,
                ctx.holdout_exposure_labels,
                ctx.holdout_asset_digest_refs,
                ctx.canary_exposure_labels,
                ctx.canary_policy_ref,
                ctx.contamination_audit_refs,
                ctx.contamination_audit_procedure_ref,
                ctx.training_corpus_disclosure_refs,
                ctx.participant_knowledge_cutoff_ref))
    /\ ((ComparativeConclusion(conclusion_scope)
         \/ CostNormalizedConclusion(conclusion_scope)) =>
        Present(ctx.cost_trace_refs,
                ctx.resource_trace_refs,
                ctx.hardware_profile_refs,
                ctx.software_profile_refs,
                ctx.timeout_budget_refs,
                ctx.cost_normalization_policy_ref))
    /\ ImmutableOrDisclosed(ctx.environment_build_refs)

BenchmarkContextLinkageOK(claim) =
  exists ctx = RunContext(claim.run_context_ref):
    ClaimSupportRefsScopedToRunContext(claim, ctx)
    /\ PopulationScopeMatchesContext(claim.population_scope_ref, ctx)
    /\ ResultAnalysisSupportMatchesContext(claim, ctx)
    /\ SameSupportSetOrScopedNotApplicable(
         claim.baseline_refs,
         ctx.baseline_refs,
         claim.conclusion_scope,
         BaselineComparability)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.baseline_eligibility_policy_ref,
         ctx.baseline_eligibility_policy_ref,
         claim.conclusion_scope,
         BaselineComparability)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.comparison_cohort_ref,
         ctx.comparison_cohort_ref,
         claim.conclusion_scope,
         BaselineComparability)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.paired_run_group_ref,
         ctx.paired_run_group_ref,
         claim.conclusion_scope,
         BaselineComparability)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.treatment_assignment_ref,
         ctx.treatment_assignment_ref,
         claim.conclusion_scope,
         TreatmentAssignment)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.assignment_policy_ref,
         ctx.assignment_policy_ref,
         claim.conclusion_scope,
         TreatmentAssignment)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.assignment_unit_ref,
         ctx.assignment_unit_ref,
         claim.conclusion_scope,
         TreatmentAssignment)
    /\ SameSupportSet(claim.evaluator_version_refs,
                      ctx.evaluator_version_refs)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.evaluator_leakage_model_ref,
         ctx.evaluator_leakage_model_ref,
         claim.conclusion_scope,
         EvaluatorLeakage)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.scaffold_exposure_matrix_ref,
         ctx.scaffold_exposure_matrix_ref,
         claim.conclusion_scope,
         Exposure)
    /\ SameSupportSetOrScopedNotApplicable(
         claim.contamination_audit_refs,
         ctx.contamination_audit_refs,
         claim.conclusion_scope,
         Exposure)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.contamination_audit_procedure_ref,
         ctx.contamination_audit_procedure_ref,
         claim.conclusion_scope,
         Exposure)
    /\ ExposureEvidenceMatchesContext(
         claim.holdout_non_exposure_evidence_refs,
         claim.canary_evidence_refs,
         ctx.holdout_asset_digest_refs,
         ctx.canary_policy_ref,
         claim.conclusion_scope)
    /\ SameSupportRef(claim.exclusion_policy_ref, ctx.exclusion_policy_ref)
    /\ SameSupportSet(claim.exclusion_decision_refs,
                      ctx.exclusion_decision_refs)
    /\ SameSupportRef(claim.retry_policy_ref, ctx.retry_policy_ref)
    /\ SameSupportRefOrScopedNotApplicable(
         claim.cost_normalization_policy_ref,
         ctx.cost_normalization_policy_ref,
         claim.conclusion_scope,
         CostNormalization)
    /\ SameSupportSet(claim.artifact_immutability_refs,
                      ctx.artifact_immutability_refs)

ResultAnalysisSupportMatchesContext(claim, ctx) =
  (not ResultAnalysisConclusion(claim.conclusion_scope)
   /\ ResultAnalysisNotApplicableSupportOK(claim, ctx))
  \/ (ResultAnalysisConclusion(claim.conclusion_scope)
      /\ SameSupportSet(claim.metric_refs, ctx.result_metric_refs)
      /\ SameSupportRef(claim.aggregation_plan_ref,
                        ctx.aggregation_plan_ref)
      /\ ReplicateSetMatchesContext(claim.replicate_set_ref, ctx)
      /\ UnitOfAnalysisConsistent(claim.unit_of_analysis_ref,
                                  claim.aggregation_plan_ref,
                                  claim.statistical_plan_ref,
                                  claim.replicate_set_ref)
      /\ SameSupportRef(claim.statistical_plan_ref,
                        ctx.statistical_plan_ref)
      /\ SameSupportRef(claim.preregistration_ref,
                        ctx.preregistration_ref)
      /\ UncertaintyPoliciesMatchContext(
           claim.confidence_interval_ref,
           claim.statistical_test_ref,
           claim.effect_size_ref,
           claim.minimum_effect_or_margin_ref,
           ctx.confidence_interval_policy_ref,
           ctx.statistical_test_policy_ref,
           ctx.effect_size_policy_ref,
           ctx.power_or_precision_target_ref))

ResultAnalysisNotApplicableSupportOK(claim, ctx) =
  SameSupportSetOrScopedNotApplicable(
    claim.metric_refs, ctx.result_metric_refs,
    claim.conclusion_scope, ResultAnalysis)
  /\ SameSupportRefOrScopedNotApplicable(
       claim.aggregation_plan_ref, ctx.aggregation_plan_ref,
       claim.conclusion_scope, ResultAnalysis)
  /\ SameSupportRefOrScopedNotApplicable(
       claim.statistical_plan_ref, ctx.statistical_plan_ref,
       claim.conclusion_scope, ResultAnalysis)
  /\ SameSupportRefOrScopedNotApplicable(
       claim.preregistration_ref, ctx.preregistration_ref,
       claim.conclusion_scope, ResultAnalysis)
  /\ ReplicateSetOrScopedNotApplicable(
       claim.replicate_set_ref, ctx,
       claim.conclusion_scope, ResultAnalysis)
  /\ UnitOfAnalysisOrScopedNotApplicable(
       claim.unit_of_analysis_ref,
       claim.conclusion_scope, ResultAnalysis)
  /\ UncertaintyPoliciesOrScopedNotApplicable(
       claim.confidence_interval_ref,
       claim.statistical_test_ref,
       claim.effect_size_ref,
       claim.minimum_effect_or_margin_ref,
       ctx.confidence_interval_policy_ref,
       ctx.statistical_test_policy_ref,
       ctx.effect_size_policy_ref,
       ctx.power_or_precision_target_ref,
       claim.conclusion_scope, ResultAnalysis)

MetricsOK(metric_refs, aggregation_plan_ref, conclusion_scope) =
  (NotApplicableMetricAnalysisSupport(metric_refs,
                                      aggregation_plan_ref,
                                      conclusion_scope)
   /\ not ResultAnalysisConclusion(conclusion_scope))
  \/ (ResultAnalysisConclusion(conclusion_scope)
      /\ NonEmpty(metric_refs)
      /\ forall m in metric_refs: MetricSpecOK(m, conclusion_scope)
      /\ AggregationPlanOK(aggregation_plan_ref,
                           metric_refs,
                           conclusion_scope))

MetricSpecOK(m, conclusion_scope) =
  Present(m.outcome_mapping_ref, m.measurement_procedure_ref, m.unit)
  /\ m.direction in {higher_is_better, lower_is_better, target_is_better,
                    descriptive}
  /\ DenominatorOK(m.denominator, m.unit, m.direction, conclusion_scope)
  /\ MissingnessPolicyOK(m.missingness_policy_ref)
  /\ EvaluatorVisibilityOK(m.evaluator_visibility_scope)

AggregationPlanOK(aggregation_plan_ref, metric_refs, conclusion_scope) =
  exists a = AggregationPlan(aggregation_plan_ref):
    Present(a.unit_of_analysis_ref)
    /\ NonEmpty(a.metric_refs)
    /\ SameSupportSet(a.metric_refs, metric_refs)
    /\ GroupingOrBlockingOK(a.grouping_or_blocking_refs,
                            a.unit_of_analysis_ref,
                            conclusion_scope)
    /\ WeightingPolicyOK(a.weighting_policy_ref,
                         a.metric_refs,
                         conclusion_scope)
    /\ Present(a.summary_statistics)
    /\ SummaryStatisticsOK(a.summary_statistics,
                           a.metric_refs,
                           conclusion_scope)
    /\ MissingnessPolicyOK(a.missingness_policy_ref)
    /\ OutlierPolicyOK(a.outlier_policy_ref)

ReplicationOK(replicate_set_ref,
              unit_of_analysis_ref,
              paired_run_group_ref,
              conclusion_scope) =
  (NotApplicableReplicationSupport(replicate_set_ref,
                                   unit_of_analysis_ref,
                                   paired_run_group_ref,
                                   conclusion_scope)
   /\ not ResultAnalysisConclusion(conclusion_scope))
  \/ (ResultAnalysisConclusion(conclusion_scope)
      /\ exists r = ReplicateSet(replicate_set_ref):
        r.replicate_count = count(r.run_refs)
        /\ r.replicate_count >= RequiredReplicates(unit_of_analysis_ref)
        /\ Present(r.repeat_identity_policy_ref)
        /\ Unique(repeat_id, r.run_refs)
        /\ RandomizationBlocksOK(r.randomization_block_refs,
                                 r.run_refs,
                                 conclusion_scope)
        /\ PairedGroupsOK(r.paired_run_group_refs, r.run_refs)
        /\ ClaimPairedGroupOK(paired_run_group_ref,
                              r.paired_run_group_refs,
                              conclusion_scope)
        /\ ExclusionsCited(r.exclusion_decision_refs))

UncertaintyOK(statistical_plan_ref,
              preregistration_ref,
              confidence_interval_ref,
              statistical_test_ref,
              effect_size_ref,
              minimum_effect_or_margin_ref,
              conclusion_scope) =
  (NotApplicableUncertaintySupport(statistical_plan_ref,
                                   preregistration_ref,
                                   confidence_interval_ref,
                                   statistical_test_ref,
                                   effect_size_ref,
                                   minimum_effect_or_margin_ref,
                                   conclusion_scope)
   /\ not ResultAnalysisConclusion(conclusion_scope))
  \/ (DescriptiveResultConclusion(conclusion_scope)
      /\ not InferentialResultConclusion(conclusion_scope)
      /\ exists plan = StatisticalPlan(statistical_plan_ref):
        Present(plan.estimand,
                plan.unit_of_analysis_ref,
                plan.analysis_design)
        /\ StatisticalPlanScopeOK(plan, conclusion_scope)
        /\ SameSupportRef(plan.preregistration_ref, preregistration_ref)
        /\ plan.uncertainty_method = descriptive_only
        /\ DescriptiveSummaryPlanOK(plan, conclusion_scope)
        /\ DescriptiveInferenceSupportNotApplicable(
             confidence_interval_ref,
             statistical_test_ref,
             effect_size_ref,
             minimum_effect_or_margin_ref,
             conclusion_scope)
        /\ PreregistrationOrDisclosureOK(plan.preregistration_ref,
                                         plan.analysis_design)
        /\ MultipleComparisonOrNotApplicableOK(
             plan.multiple_comparison_policy_ref,
             conclusion_scope)
        /\ PairedOrClusteredOK(plan.paired_or_blocked_model,
                              plan.clustering_basis_ref))
  \/ (InferentialResultConclusion(conclusion_scope)
      /\ exists plan = StatisticalPlan(statistical_plan_ref):
        Present(plan.estimand, plan.unit_of_analysis_ref)
        /\ Present(plan.comparison_design)
        /\ StatisticalPlanScopeOK(plan, conclusion_scope)
        /\ SameSupportRef(plan.preregistration_ref, preregistration_ref)
        /\ plan.uncertainty_method in
           {frequentist, bootstrap, bayesian, exact}
        /\ Present(plan.interval_level)
        /\ Present(plan.effect_size_definition)
        /\ ConfidenceIntervalOK(confidence_interval_ref,
                                plan,
                                conclusion_scope)
        /\ StatisticalTestOK(statistical_test_ref, plan, conclusion_scope)
        /\ EffectSizeOK(effect_size_ref, plan, conclusion_scope)
        /\ MinimumEffectOrMarginOK(minimum_effect_or_margin_ref,
                                   plan,
                                   conclusion_scope)
        /\ StatisticalTestFamilyOK(plan.statistical_test_family,
                                   plan.comparison_design,
                                   conclusion_scope)
        /\ EquivalenceOrNoninferiorityMarginOK(
             plan.equivalence_or_noninferiority_margin,
             conclusion_scope)
        /\ PowerOrPrecisionTargetOK(plan.power_or_precision_target_ref,
                                    conclusion_scope)
        /\ PreregistrationOrDisclosureOK(plan.preregistration_ref,
                                         plan.comparison_design)
        /\ MultipleComparisonOK(plan.multiple_comparison_policy_ref)
        /\ PairedOrClusteredOK(plan.paired_or_blocked_model,
                              plan.clustering_basis_ref))

ExclusionRetryOK(exclusion_policy_ref,
                 exclusion_decision_refs,
                 retry_policy_ref,
                 conclusion_scope) =
  exists policy = ExclusionPolicy(exclusion_policy_ref):
    RetryPolicyOK(retry_policy_ref, policy, conclusion_scope)
    /\ ExclusionPolicyOK(policy, conclusion_scope)
    /\ forall decision in exclusion_decision_refs:
         ExclusionDecisionOK(decision, policy, retry_policy_ref)
    /\ ExclusionDecisionsCompleteOrDisclosed(exclusion_decision_refs,
                                             policy,
                                             conclusion_scope)

BaselineComparabilityOK(baseline_refs, comparison_cohort_ref,
                        baseline_eligibility_policy_ref, conclusion_scope) =
  (NotApplicableSupport(baseline_eligibility_policy_ref,
                        BaselineComparability)
   /\ not ComparativeConclusion(conclusion_scope))
  \/ (ComparativeConclusion(conclusion_scope)
      /\ NonEmpty(baseline_refs)
      /\ Present(comparison_cohort_ref)
      /\ BaselineEligibilityPolicyOK(baseline_eligibility_policy_ref)
      /\ ComparisonCohortIncludesBaselines(comparison_cohort_ref,
                                           baseline_refs)
      /\ forall b in baseline_refs:
           BaselineVersionPinned(b)
           /\ SameEligibilityOrDisclosed(b, comparison_cohort_ref,
                                         baseline_eligibility_policy_ref))

TreatmentAssignmentOK(treatment_assignment_ref,
                      assignment_policy_ref,
                      assignment_unit_ref,
                      conclusion_scope) =
  (NotApplicableSupport(treatment_assignment_ref, TreatmentAssignment)
   /\ not ComparativeConclusion(conclusion_scope)
   /\ not TreatmentAssignmentConclusion(conclusion_scope))
  \/ ((ComparativeConclusion(conclusion_scope)
       \/ TreatmentAssignmentConclusion(conclusion_scope))
      /\ exists ta = TreatmentAssignment(treatment_assignment_ref):
        Present(ta.assigned_unit_refs, ta.treatment_refs)
        /\ Present(ta.assignment_mechanism,
                   ta.assignment_policy_ref,
                   ta.assignment_unit_ref)
        /\ SameSupportRef(ta.assignment_policy_ref, assignment_policy_ref)
        /\ SameSupportRef(ta.assignment_unit_ref, assignment_unit_ref)
        /\ AssignmentUnitsMatchPopulation(ta.assigned_unit_refs,
                                          assignment_unit_ref,
                                          conclusion_scope)
        /\ TreatmentArmsMatchComparison(ta.treatment_refs,
                                        conclusion_scope)
        /\ RandomizationOrDisclosureOK(ta.assignment_mechanism,
                                       ta.seed_or_rng_ref,
                                       ta.randomization_block_refs)
        /\ BlockingFactorsOK(ta.blocking_factor_refs,
                             conclusion_scope)
        /\ AllocationConcealmentOrDisclosureOK(
             ta.allocation_concealment_ref,
             conclusion_scope)
        /\ BlindingOrMaskingOrDisclosureOK(ta.blinding_or_masking_ref,
                                           conclusion_scope)
        /\ AssignmentDeviationsDisclosed(ta.deviation_refs,
                                         conclusion_scope))

ExposureOK(scaffold_exposure_matrix_ref,
           holdout_non_exposure_evidence_refs,
           canary_evidence_refs,
           contamination_audit_refs,
           conclusion_scope) =
  (NotApplicableExposureSupport(scaffold_exposure_matrix_ref,
                                holdout_non_exposure_evidence_refs,
                                canary_evidence_refs,
                                contamination_audit_refs)
   /\ not NonContaminationConclusion(conclusion_scope))
  \/ (NonContaminationConclusion(conclusion_scope)
      /\ exists proc = ExposureAuditProcedureFor(contamination_audit_refs):
        Present(proc.scaffold_exposure_matrix_ref)
        /\ scaffold_exposure_matrix_ref = proc.scaffold_exposure_matrix_ref
        /\ HoldoutEvidenceOK(holdout_non_exposure_evidence_refs,
                             proc.holdout_asset_digest_refs)
        /\ CanaryEvidenceOK(canary_evidence_refs, proc.canary_policy_ref)
        /\ TrainingCorpusDisclosureOK(proc.training_corpus_disclosure_refs)
        /\ KnowledgeCutoffOK(proc.participant_knowledge_cutoff_ref)
        /\ Present(proc.audit_method)
        /\ ContaminationAuditOK(contamination_audit_refs, proc.audit_method)
        /\ AuditLimitationsDisclosed(proc.audit_limitations))

EvaluatorLeakageOK(evaluator_leakage_model_ref, conclusion_scope) =
  (NotApplicableSupport(evaluator_leakage_model_ref, EvaluatorLeakage)
   /\ not EvaluatorLeakageConclusion(conclusion_scope)
   /\ not NonContaminationConclusion(conclusion_scope))
  \/ (exists model = EvaluatorLeakageModel(evaluator_leakage_model_ref):
        Present(model.evaluator_refs, model.evaluator_version_refs)
        /\ Present(model.public_material_labels,
                   model.private_material_labels)
        /\ PublicPrivateMaterialLabelsOK(model.public_material_labels,
                                         model.private_material_labels)
        /\ Present(model.allowed_evaluator_inputs)
        /\ Present(model.forbidden_evaluator_inputs)
        /\ EvaluatorInputBoundaryOK(model.allowed_evaluator_inputs,
                                    model.forbidden_evaluator_inputs,
                                    model.public_material_labels,
                                    model.private_material_labels)
        /\ OracleAccessOK(model.oracle_or_gold_access_policy_ref)
        /\ AuditEvidenceOK(model.audit_evidence_refs))

ValidityThreatsOK(validity_threat_refs,
                  validity_threat_mitigation_refs,
                  correspondence_evidence_refs,
                  conclusion_scope) =
  (NotApplicableSupport(validity_threat_refs, ValidityThreats)
   /\ not BenchmarkValidityConclusion(conclusion_scope))
  \/ (BenchmarkValidityConclusion(conclusion_scope)
      /\ NonEmpty(validity_threat_refs)
      /\ ThreatDimensionsCovered(validity_threat_refs,
                                 {construct,
                                  internal,
                                  external,
                                  statistical_conclusion,
                                  cyber_range_correspondence})
      /\ forall threat in validity_threat_refs:
           ValidityThreatDisclosureOK(threat,
                                      validity_threat_mitigation_refs,
                                      conclusion_scope)
      /\ CorrespondenceEvidenceOK(correspondence_evidence_refs,
                                  validity_threat_refs,
                                  conclusion_scope))

CorrespondenceEvidenceOK(correspondence_evidence_refs,
                         validity_threat_refs,
                         conclusion_scope) =
  (CorrespondenceThreatNotApplicable(validity_threat_refs,
                                     conclusion_scope)
   /\ NotApplicableSupport(correspondence_evidence_refs,
                           CorrespondenceEvidence))
  \/ (BenchmarkValidityConclusion(conclusion_scope)
      /\ NonEmpty(correspondence_evidence_refs)
      /\ forall c in correspondence_evidence_refs:
           Present(c.conceptual_model_ref,
                   c.realized_testbed_ref,
                   c.requirement_refs,
                   c.observation_or_measurement_refs,
                   c.comparison_method_ref,
                   c.acceptance_criterion_ref)
           /\ ScenarioModelVersionPinned(c.conceptual_model_ref)
           /\ RealizedTestbedBuildPinned(c.realized_testbed_ref)
           /\ CorrespondenceRequirementsOK(c.requirement_refs,
                                           conclusion_scope)
           /\ MeasurementsTraceToRunContext(c.observation_or_measurement_refs)
           /\ ComparisonMethodOK(c.comparison_method_ref,
                                 c.requirement_refs,
                                 conclusion_scope)
           /\ AcceptanceCriterionOK(c.acceptance_criterion_ref,
                                    c.comparison_method_ref)
           /\ ResidualGapsDisclosed(c.residual_gap_refs,
                                    validity_threat_refs,
                                    conclusion_scope))

CostOK(cost_normalization_policy_ref, conclusion_scope) =
  (NotApplicableSupport(cost_normalization_policy_ref, CostNormalization)
   /\ not ComparativeConclusion(conclusion_scope)
   /\ not CostNormalizedConclusion(conclusion_scope))
  \/ ((ComparativeConclusion(conclusion_scope)
       \/ CostNormalizedConclusion(conclusion_scope))
      /\ exists c = CostNormalizationPolicy(cost_normalization_policy_ref):
        Present(c.cost_dimensions, c.normalization_unit)
        /\ Present(c.included_resources)
        /\ Present(c.excluded_resources)
        /\ Present(c.timeout_budget_refs)
        /\ IncludedExcludedResourcesOK(c.included_resources,
                                       c.excluded_resources)
        /\ HardwareSoftwareProfilesOK(c.hardware_profile_refs,
                                      c.software_profile_refs)
        /\ TimeoutBudgetsOK(c.timeout_budget_refs)
        /\ RetryCostPolicyOK(c.retry_cost_policy_ref))

ArtifactImmutabilityOK(artifact_immutability_refs, claim) =
  exists a = ArtifactImmutabilityEvidenceSet(artifact_immutability_refs),
         ctx = RunContext(claim.run_context_ref):
    NonEmpty(a.artifact_refs)
    /\ NonEmpty(artifact_immutability_refs)
    /\ forall bundle in artifact_immutability_refs:
         ArtifactImmutabilityEvidenceOK(bundle, ctx)
    /\ Present(a.retrieval_time)
    /\ ImmutableOrDisclosed(a.build_environment_refs)
    /\ ArtifactEvidenceScopedToRunContext(a, ctx)
    /\ RequiredRolePolicyOK(a.required_role_policy_ref,
                            claim.conclusion_scope,
                            ctx)
    /\ RequiredArtifactCoverageOK(a, claim, ctx)
    /\ forall artifact in a.artifact_refs:
         DigestPinned(artifact, a.digest_refs)
         /\ VersionPinnedOrDigestOnly(artifact, a.version_refs)
         /\ RegistryOrStorageOK(artifact, a.registry_or_storage_refs)

RequiredArtifactCoverageOK(a, claim, ctx) =
  let roles = RequiredArtifactRoles(claim, ctx) in
  let support_refs = ClaimBearingSupportRefs(claim, ctx) in
    NonEmpty(roles)
    /\ RoleSetGeneratedFromClaimScope(roles, claim.conclusion_scope, ctx)
    /\ forall role in roles: RoleCoverageOK(a, ctx, role)
    /\ forall ref in support_refs:
         SupportRefMappedToRole(a, ref, roles)
         /\ ArtifactForSupportRefOK(a, ref)
```

`ConclusionScopeOK(scope)` validates a governed set of conclusion tags. At
minimum, the scope distinguishes descriptive-result, comparative, superiority,
equivalence, non-inferiority, evaluator-leakage, non-contamination, and
cost-normalized conclusions. `ResultAnalysisConclusion` is true when the claim
asserts a metric, score, rate, effect, interval, test, descriptive result,
comparative result, or cost-normalized result. It is false for audit-only
evaluator-leakage or non-contamination claims that assert provenance,
exposure, or boundary compliance without a score/rate/effect result.
`DescriptiveResultConclusion` is true for a metric, summary result, or
descriptive cost-normalized metric that does not assert a comparison, interval,
test, effect, margin, superiority, equivalence, non-inferiority,
cost-normalized comparative effect, or statistical non-contamination rate.
`InferentialResultConclusion` is true for those stronger result claims and for
any conclusion that reports a confidence or credible interval, test,
effect-size, practical-effect margin, equivalence or non-inferiority margin,
cost-normalized comparative effect, or statistical non-contamination rate.
`ComparativeConclusion`, `EvaluatorLeakageConclusion`,
`NonContaminationConclusion`, and `CostNormalizedConclusion` are true exactly
when the conclusion scope includes the corresponding governed tag or a stronger
tag that depends on it. `BenchmarkValidityConclusion` is true for every claim
that asserts reproducibility, comparison, result-analysis support,
non-contamination, evaluator-leakage, cost-normalized interpretation,
cyber-range/testbed correspondence, or another benchmark-validity conclusion
over runtime records. `TreatmentAssignmentConclusion` is true for comparative,
causal-treatment-effect, superiority, equivalence, non-inferiority, or other
conclusion tags whose interpretation depends on assignment of participants,
runs, scenarios, scaffolds, models, tools, or assistance conditions to
treatment arms. A one-sample descriptive or interval estimate does not become a
treatment-assignment claim merely because it is inferential.

`NotApplicableSupport(ref, concern)` resolves to a governed support record
stating that `concern` is outside the claim's conclusion scope, why it is not
applicable, and which stronger conclusions are excluded. It is not a missing
value. `NotApplicableExposureSupport(...)` is the same rule for the exposure
support bundle: every populated exposure ref must resolve to the same governed
not-applicable bundle, and no non-contamination conclusion may be made from it.
`NotApplicableMetricAnalysisSupport`, `NotApplicableReplicationSupport`, and
`NotApplicableUncertaintySupport` apply the same rule to metric-analysis
bundles: all populated metric, aggregation, replicate, unit-of-analysis,
statistical-plan, interval, test, effect, and margin refs must resolve to a
single governed not-applicable reason, scoped to the run context, and the
claim must exclude result-analysis conclusions.

`ClaimSupportRefsScopedToRunContext(claim, ctx)` resolves every support record
cited by `claim` and requires the support record to carry either
`claim.run_context_ref`, the same `(study_id, trial_id, run_id)` tuple as `ctx`,
or a governed comparison-cohort membership that includes `ctx.run_id`. Support
records spanning multiple runs, such as replicate sets, paired groups,
baselines, or comparison cohorts, must list their member run refs and the
eligibility rule that admits each member. A support record from an unrelated
run, scenario version, backend manifest, contract bundle, evaluator version, or
study cannot satisfy `BenchmarkContextLinkageOK`.

`SameSupportRef` and `SameSupportSet` compare resolved support records after
version and digest normalization, not raw string spelling. The
`*OrScopedNotApplicable` variants permit a governed `NotApplicable` bundle only
when the conclusion scope excludes that concern and both the claim and run
context resolve to the same not-applicable reason.
`UncertaintyPoliciesMatchContext` requires the confidence interval,
statistical test, effect-size, and minimum effect or margin records to
implement the policy refs declared in the run context; the
`UncertaintyPoliciesOrScopedNotApplicable` variant permits only the governed
not-applicable result-analysis bundle described above. `PopulationScopeMatchesContext`,
`ReplicateSetMatchesContext`, `UnitOfAnalysisConsistent`, and
`ExposureEvidenceMatchesContext` are graph validators: they reject support
records whose scope, member runs, unit of analysis, holdout assets, canary
policy, or exposure evidence cannot be traced back to the same run context and
conclusion scope.

`DenominatorOK` validates the population, attempt, task, time, cost, or resource
denominator used by a metric and requires it to be compatible with the metric
unit and direction. `GroupingOrBlockingOK`, `WeightingPolicyOK`, and
`SummaryStatisticsOK` validate how per-run or per-participant measurements are
aggregated, including empty cells, missing values, outliers, and whether
weights are equal, design-based, cost-normalized, or explicitly disclosed.
`RandomizationBlocksOK` validates the randomization/blocking basis for repeated
or comparative runs. `StatisticalTestFamilyOK`,
`EquivalenceOrNoninferiorityMarginOK`, `MinimumEffectOrMarginOK`, and
`PowerOrPrecisionTargetOK` require statistical claims to cite the test family,
effect definition, practical-effect or equivalence margin, and power or
precision target needed by the conclusion scope. Descriptive-only plans are not
an implicit escape hatch: they take the explicit
descriptive branch of `UncertaintyOK`, where interval, test, effect, and margin
refs must resolve through `DescriptiveInferenceSupportNotApplicable` unless the
claim scope is upgraded to an inferential result. Audit-only non-contamination
claims do not pass through the inferential branch of `UncertaintyOK`; they are
validated by `ExposureOK` and `EvaluatorLeakageOK`.

`ParticipantApparatusOK` validates scaffold refs, model or policy version refs,
tool version refs, and explicit no-scaffold/no-tool declarations. `RunContextOK`
therefore rejects a benchmark context that silently omits participant scaffold,
model/policy, or tool exposure. `EvaluatorAndScoringOK`,
`AssistanceDisclosureOK`, `BenchmarkPolicyRefsOK`, and the other helper
predicates above are governed schema validators with explicit unknown,
unsupported, or not-applicable outcomes.

`TreatmentAssignmentOK` is the guard against opaque assignment. It rejects
comparative, causal-treatment, superiority, equivalence, non-inferiority, and
other assignment-dependent claims when the assignment unit, assignment policy,
treatment arms, randomization or blocking basis, blinding/masking or concealment
status, and assignment deviations cannot be traced to governed support records.
Nonrandom assignment is allowed only when the assignment mechanism and resulting
validity limits are disclosed; it cannot silently support a randomized-experiment
claim.

`ValidityThreatsOK` is the guard against under-specified study claims. Threat
records must cover the conclusion's construct, internal, external,
statistical-conclusion, and cyber-range/testbed correspondence dimensions or
explain why a dimension is not applicable. A mitigation ref is evidence only
when it resolves to a governed support record; otherwise the threat remains a
residual limit. `CorrespondenceEvidenceOK` validates claims that the authored
scenario, conceptual model, realized testbed, measurements, and acceptance
criteria correspond closely enough for the asserted conclusion. If that evidence
is absent, the claim may still report runtime facts, but must downgrade the
benchmark-validity or V&V conclusion.

`ArtifactImmutabilityEvidenceSet` is the normalized union of all cited
immutability evidence bundles after each bundle passes
`ArtifactImmutabilityEvidenceOK`. `ArtifactEvidenceScopedToRunContext`,
`RequiredRolePolicyOK`, and `RoleCoverageOK` make artifact immutability coverage
graph-derived rather than existential or checklist-based.
`RequiredArtifactRoles(claim, ctx)` is generated from the conclusion scope and
every run-context or support record that
`BenchmarkClaimOK` consumes. `ClaimBearingSupportRefs(claim, ctx)` includes
populated governed refs and governed not-applicable bundles for scenario,
contract bundle, backend manifest/version, run configuration, environment
build, participant implementation/adapter/scaffold/model/tool apparatus,
assistance disclosures, seeds and randomization policies, evaluator/scoring,
retry/exclusion policies and decisions, metric definitions and measurement
procedures, aggregation and missingness/outlier/weighting policies,
replicate/randomization-block records, statistical plans, preregistrations,
interval/test/effect/margin policies when applicable, baselines and comparison
cohorts, treatment-assignment and assignment-policy records,
validity-threat disclosures and mitigations, correspondence evidence,
cost/resource/hardware/software/timeout records, evaluator-leakage models,
public/private material labels, exposure matrices, holdout/canary assets and
policies, contamination audits and procedures, training-corpus disclosures,
dataset splits, training-data cutoffs, participant knowledge cutoffs,
evidence-manifest records, and research-object manifest records when the claim
depends on them. Each required role must map to at least one governed artifact in
`artifact_refs` through `artifact_role_assignments`; each consumed support ref
must map to a role and pinned artifact. The mapped artifact must be digest
pinned, version pinned or digest-only, and retrievable from governed storage.
Explicit no-scaffold, no-tool, or unavailable-artifact declarations are
accepted only through the corresponding apparatus or unsupported/downgrade
record; they cannot be satisfied by an unrelated pinned artifact.

Claims that do not make result-analysis, comparative, evaluator-leakage,
non-contamination, or cost-normalized conclusions may satisfy the corresponding
predicate with a governed `NotApplicable` support record. Comparative
conclusions still require cost/resource support even when they do not use a
separate `cost_normalized` label. If a claim omits one of those predicates
entirely, its `conclusion_scope` must explicitly exclude that conclusion and
any stronger conclusion that depends on it.

If any predicate is `Unknown` or `Unsupported`, the claim must either downgrade
to the supported conclusion scope or explicitly record
`unsupported_or_unknown_limits`.

## Refinement And Conformance Obligations

The intended universal soundness relation includes `trace-inclusion`: under
the named participant observation projection, every admitted concrete backend
trace must map to a valid abstract RAES trace. Actionable participant
realization additionally requires `io-alternating-refinement`: participant and
environment inputs, participant-facing outputs, action ownership, availability,
fairness, exact-cut derivation, and delivery must satisfy their declared
alternating obligations. Trace inclusion alone is insufficient because a
backend that refuses every participant input can have a trivially included
trace set.

This section defines those obligations; it does not establish them. Current
executable evidence is bounded to named fixtures, target probes, and finite
counterexamples, so no universal simulation, data-refinement, alternating
refinement, trace-equivalence, or bisimulation claim follows. Bisimulation is
optional and projection-relative when separately claimed; it is not the
default backend-conformance relation. The evidence boundary for each executed
check must be carried by its conformance report.

Required preservation properties:

- participant, episode, action, operation, observation, state, joint-action, and
  evidence identity;
- decision epoch independent of its derivation state cut, with epoch zero
  grounded in authoritative `episode_running` state and empty current-episode
  behavior history;
- participant-view, assurance, projection, disclosure, delivery, selection,
  admission, attempt, result, and outcome separation;
- exact-cut policy and authorization resolution plus delivery-before-selection;
- declared participant-memory scope across reset and restart;
- append-only history and monotonic participant sequence numbers;
- lifecycle phase, phase realization, admission disposition, and operation
  state vocabulary;
- observation function, visibility projection, action-observation history, and
  information-state guarantee;
- action/observation space, action mask, reward, return, termination,
  truncation, and auxiliary-info boundaries when the concrete backend exposes
  RL/MARL/game step signals;
- shared-state address, revision/digest, marking, and provenance discipline;
- realized order, clock basis, isolation guarantee, atomicity scope, conflict
  predicate, and conflict policy;
- time-management mode, lookahead, time-advance request/grant, message
  causality, step negotiation, rollback, anti-message, and supersession
  discipline when the concrete backend makes such claims;
- component-wise capability guarantee vectors and explicit downgrades;
- redaction and authorization policy before public disclosure;
- run context needed for reproducibility, benchmark, and comparative claims.

Safety properties:

- no hidden state as participant-visible observation without a visibility rule;
- no inference of causality from wall clock alone;
- no history rewrite after append;
- no unmarked sensitive field in public runtime records;
- no capability claim stronger than backend declaration and evidence;
- no conflation of opaque, unknown, not applicable, and unsupported.
- no inferred reward, return, termination, truncation, or action mask from
  hidden objective/scorer/backend internals;
- no deletion or mutation of prior records during rollback or compensation;
- no benchmark comparison claim without repetition, baseline, evaluator,
  treatment-assignment, validity-threat, cost-normalization, and exposure
  evidence required by the claim.

Liveness properties are bounded and contract-specific:

- admitted synchronous attempts either record an execution result, failure,
  rejection, or unsupported disclosure within the contract's timeout bound;
- admitted long-running operations eventually record progress, terminal state,
  timeout, cancellation, unknown, or unsupported disclosure within the declared
  operation policy;
- retry, fairness, and starvation-free claims require declared scheduler,
  retry, and bound evidence.

Future implementation issues should turn the normative core above into an
executable model or mechanically checked test harness. The minimum executable
surface is: valid trace predicate, `Apply` transition predicates, observation
reconstruction, capability meet/satisfaction, shared-state revision discipline,
interaction-context validity, benchmark-validity predicates, `ConflictOK`,
`TimeManagementOK`, and the related concurrency/time-management rules.
TLA+/PlusCal, Alloy, state-machine property tests, or differential tests against
backend traces are acceptable realizations only if they cover those predicates
rather than rechecking schema shape alone.

## Invariants

### I1 - Role-Neutral Runtime Boundary

The runtime lifecycle applies to humans, LLM agents, RL policies, scripts,
playbooks, simulators, and external services. Participant implementation type
is apparatus metadata, not a different runtime semantics.

### I2 - Observable, Not Internal, Lifecycle

`RUN-306` phases are runtime-observable or runtime-mediated boundary events.
They must not be interpreted as a requirement to expose participant internal
plans, chain-of-thought, prompt content, model activations, reward traces, or
workflow steps.

### I3 - Episode Identity Preservation

Every participant runtime record that belongs to an episode carries stable
`participant_address`, per-episode `episode_id`, and the relevant
`sequence_number`. Reset and restart create new episode instances; they do not
mutate prior histories.

### I4 - Episode Lifecycle Separation

Episode status, control actions, and terminal reasons remain separate from
action lifecycle phases, action outcomes, objective outcomes, evaluator
results, workflow state, and operation state.

### I5 - Plain-Data Contract Boundary

Portable participant runtime state and history are JSON-like, schema-shaped,
versioned contract records. Backend-native objects, logs, DB rows, cache keys,
process ids, raw tool output, and private participant memory are not portable
state unless projected into a governed contract.

### I6 - No Metadata State Model

`RuntimeSnapshot.metadata`, history `details`, and diagnostic details are not
the shared operational state model. They may carry auxiliary information only
when no portable claim depends on it.

### I7 - Shared-State Addressability

Every shared operational state record has a stable address and state kind.
Behavior events that read or write shared state reference those addresses,
rather than relying on prose or backend-local names.

### I8 - Revision And Digest Discipline

State updates that affect shared operational state carry a revision, digest, or
equivalent version marker. Consumers must not infer equality, conflict, or
ordering from timestamps alone.

### I9 - Explicit Ordering Basis

Every action attempt or state update that participates in a joint action set
declares an ordering basis: total order, partial order, simultaneity,
serialized backend order, simulation order, control-plane order, logical/vector
clock order, or unsupported/unknown ordering.

### I10 - Conflict Policy Disclosure

Concurrent attempts that touch the same shared operational state, exclusive
resource, visibility surface, evidence stream, or action-contract interference
relation declare their conflict class and policy. Implicit last-writer-wins is
not a valid portable semantics.

### I11 - Observation Projection Boundary

Observation emission may update participant-visible state, but it must not
collapse world truth, shared operational state, participant belief/history,
centralized-training state, scoring state, and archival evidence.

### I12 - Provenance Preservation

State and history records distinguish author-declared, processor-derived,
backend-realized, participant-observed, and externally supplied values when
that distinction affects interpretation.

### I13 - Secrets And Internal Traces Stay Out

Credentials, bearer tokens, hidden answer keys, prompts, private model traces,
raw backend exceptions, and sensitive state values must not appear in public
runtime envelopes, diagnostics, audit details, snapshots, fixtures, or
changelog fragments unless an explicit evidence contract defines a safe redacted
representation.

### I14 - Backend Capability Honesty

Backends claim participant runtime support through manifest capabilities and
published evidence contracts. A backend that cannot preserve a lifecycle,
admission, operation, observation, step-signal, shared-state, ordering,
time-management, rollback, isolation, conflict, redaction, provenance, replay,
or benchmark guarantee must reject or disclose the weaker realization.

### I15 - Replay Compatibility

Behavior history, operation history, shared-state revisions, ordering,
observations, and evidence references must be sufficient to explain what the
runtime claimed happened. Replay may be approximate, but the lost or unsupported
guarantees must be visible.

### I16 - Closed Vocabulary Semantics

Lifecycle phase, phase realization, admission disposition, operation state,
information guarantee, ordering basis, isolation guarantee, conflict policy,
mapping loss, delivery basis, and capability strength values are closed at the
portable contract layer. Source labels may be preserved, but source labels do
not define RAES semantics.

### I17 - Missingness Distinctions

`Opaque`, `Unknown`, `NotApplicable`, and `Unsupported` must remain
distinguishable. They express apparatus boundary, epistemic gap, semantic
absence, and backend capability limit respectively.

### I18 - Information-State Claim Strength

An observation may be portable without a portable information-state claim.
Whenever RAES claims history consistency or perfect recall, the
action-observation history, visibility projection, markings, stochastic/noise
context, and order relation must be sufficient for that claim.

### I19 - Semantic Conflict Detection

Conflict detection is based on semantic read/write sets, exclusive resource
claims, visibility effects, evidence streams, action-contract interference,
sessions, authorities, and actuators. It is not limited to object identity or
physical storage collisions.

### I20 - Capability Vector Monotonicity

A runtime claim cannot be stronger than the required effective capability
vector for lifecycle, admission, operation, observation, shared-state revision,
step signals, ordering, time management, rollback, isolation, conflict,
redaction, provenance, replay, and benchmark concerns. Downgrades are records,
not diagnostics-only warnings.

### I21 - Capability Incomparability

Guarantee vectors that are stronger on different concerns are incomparable
unless the claim explicitly ignores the weaker concern. Implementations must not
silently collapse incomparable vectors to one scalar.

### I22 - Marking And Redaction Enforcement

Security markings and redaction policies are enforced before data is published
through runtime envelopes, diagnostics, audit details, snapshots, fixtures,
schemas, or changelog fragments.

### I23 - Operation State Append-Only

Long-running operation state advances by appending operation records. Timeout,
cancellation, partial progress, and failure do not rewrite prior lifecycle,
operation, observation, or state records.

### I24 - Cyber Command Context

Cyber actions that support portable behavior or outcome claims preserve command,
target, actuator, executor, session, authority, privilege, credential reference,
knowledge delta, visibility delta, response, and evidence context as governed
references.

### I25 - Benchmark Provenance

Benchmark comparison claims require run context for scenario version, contract
bundle, backend manifest, participant implementation, adapter/scaffold/tool
exposure, seeds/randomization, treatment assignment, evaluator/scoring,
resource/cost traces, validity-threat disclosure, and holdout/canary exposure
labels as applicable.

### I26 - Concrete Envelope Compatibility

Every conforming implementation must be able to represent opaque LLM/RL
participants, externally supplied human actions, asynchronous cyber actions,
simultaneous joint actions, backend-serialized weak concurrency, and redacted
evidence without changing the portable semantics.

### I27 - RL Step Signal Separation

Action spaces, observation spaces, action masks, rewards, returns,
termination, truncation, and auxiliary info are portable only when represented
as governed step signals. They must not be inferred from objective success,
scoring state, hidden world state, backend debug fields, or participant private
policy state.

### I28 - Termination And Truncation Separation

Task terminal semantics and external truncation semantics remain separate.
Neither field is equivalent to ADR-013 episode terminal reason unless an
explicit closure record relates them.

### I29 - Information-State Reconstructability

History-consistent and perfect-recall claims require a reconstructability
procedure over visible action-observation history, projection version,
redaction policy, visible order relation, simultaneity groups, optional
delivery linearization, stochastic/noise context, projected visible
identifiers, and proof artifacts. If that procedure is missing, lossy,
incomparable, or unsupported, the claim must be downgraded.

### I30 - Time-Management Honesty

Claims about HLA-style time management, conservative logical time, optimistic
rollback, DEVS transitions, FMI co-simulation, or true simultaneity require the
corresponding lookahead, time-advance, message-causality, rollback, transition,
or step-negotiation evidence. Otherwise the backend may claim only the weaker
realized order it can prove.

### I31 - Capability Composition

Effective capability is the meet across all components that can weaken a
claim. A strong backend engine cannot hide a weak adapter, clock authority,
redaction policy, evidence store, observation apparatus, replay engine, or
benchmark harness.

### I32 - Benchmark Comparison Evidence

Runtime provenance is necessary but not sufficient for benchmark comparison.
Comparative claims require repetition, statistical plan, treatment assignment,
baseline/evaluator version, validity-threat disclosure, cost normalization,
retry/exclusion policy, scaffold exposure, holdout/canary non-exposure evidence,
and contamination-audit records as applicable.

### I33 - Agent-Set And Chance Discipline

Sequential, AEC, simultaneous, parallel, chance, and mean-field step claims
require an interaction context. Step participant actions are valid only for the
recorded possible/live/active agent sets, current actor, and cleanup-null
policy; ordinary lifecycle actions that do not make a game-node claim are
outside this interaction-context requirement. Chance and mean-field nodes cannot
be silently represented as participant choices.

### I34 - Benchmark Validity Procedure

Run context is evidence, not a conclusion. A comparative or
non-contamination claim must cite a benchmark validity claim with metric,
aggregation, uncertainty, baseline comparability, evaluator leakage, exposure,
exclusion, retry, cost-normalization, and artifact-immutability procedures, or
downgrade the conclusion scope.

## Canonical Structural Examples

The examples use snake_case wire-style values and complete structural fields
for the surface being exercised. Conditional source-alignment subobjects appear
when relevant; concrete schemas may make non-applicable subobjects explicit
nulls or omit them under a published extension policy. Raw payloads are
represented by governed refs, not omitted secrets.

These examples are not evidence fixtures. Repeated-character hash values such
as `sha256:1111...` demonstrate field placement only; they do not support exact
raw-data integrity or provenance claims. A reviewable fixture must either cite
an evidence fixture manifest whose bytes hash to the recorded digest, or set
the raw-data hash fields to null/unknown and downgrade provenance accordingly.
Likewise, event-classification tuples in these examples are RAES-native
registry examples. They are not OCSF events unless a governed OCSF mapping ref
and OCSF-valid class/profile values are supplied.

### Opaque LLM Agent Action

```yaml
lifecycle_envelope:
  event_id: evt-llm-17-exec
  schema_name: raes.participant_runtime.lifecycle
  schema_version: 1.0.0
  event_type: execution_attempt
  extension_policy: reject_unknown_required
  event_classification: null
  source_status:
    status_id: 1
    status: success
    status_code: tool_call_completed
    status_detail: tool gateway accepted and completed the command
    source_status_label: tool_call_completed
    source_status_mapping: raes.lifecycle.operation_state.completed
  participant_address: participants.red.llm
  episode_id: ep-red-004
  sequence_number: 17
  occurred_at: 2026-05-26T10:15:01Z
  recorded_at: 2026-05-26T10:15:02Z
  ingested_at: 2026-05-26T10:15:03Z
  clock_authority: backend.logical_clock.red-range
  temporal_context: tick-118
  ordering_basis: logical_clock
  logical_order_ref: order.red.118.17
  predecessor_event_refs:
    - evt-llm-16-selection
  actor_ref: participants.red.llm
  producer_ref: adapters.llm-tool-runtime.v2
  source_system_ref: tool-gateway.red
  source_record_ref: gateway-call-992
  source_raw_ref: evidence.raw.tool-call-992
  source_pipeline:
    product_ref: products.tool-gateway.red
    product_version: 2.4.1
    log_provider: tool-gateway
    log_source: tool-gateway.red
    log_name: tool-invocation
    original_event_uid: gateway-call-992
    original_time: 2026-05-26T10:15:01Z
    processed_time: 2026-05-26T10:15:02Z
    logged_time: 2026-05-26T10:15:02Z
    transmit_time: 2026-05-26T10:15:03Z
    correlation_uid: corr-tool-call-992
    sequence: 992
  raw_data_integrity:
    raw_data_hash: sha256:1111111111111111111111111111111111111111111111111111111111111111
    raw_data_hash_algorithm: sha256
    raw_data_size: 4096
    raw_data_is_truncated: false
    raw_data_untruncated_size: 4096
  confidence: 0.82
  provenance_refs:
    - provenance.participant_observed
  evidence_refs:
    - evidence.tool-call-992-redacted
  marking_definition_refs:
    - markings.internal.v1
    - markings.restricted_evidence.v1
  object_marking_refs:
    - markings.internal.v1
  markings:
    - internal
  granular_markings:
    /source_raw_ref:
      - restricted_evidence
  redaction_policy_ref: redaction.no-prompts-or-secrets.v1
  authorization_scope: runtime_review
  phase: execution_attempt
  phase_realization: observed
  admission_disposition: admitted
  operation_ref: null
  action_ref: actions.exfiltrate_file
  action_contract_ref: contracts.file_access.v1
  command_ref: commands.tool.invoke-992
  actor_provenance: participant_observed
  observation_refs:
    - obs-red-17
  shared_state_read_refs:
    - hosts.web01.files.secret-plan@rev3
  shared_state_write_refs:
    - evidence.collection.red@rev9
  emitted_state_update_refs:
    - state-update-red-17
  attribution_edge_refs: []
  outcome_interpretation_refs: []
  joint_action_set_ref: null
  source_status_label: tool_call_completed
  mapping_loss: private_apparatus_detail
  mapping_loss_detail: selection_private_to_model
selection_envelope:
  event_id: evt-llm-16-selection
  schema_name: raes.participant_runtime.lifecycle
  schema_version: 1.0.0
  event_type: selection_or_admission
  extension_policy: reject_unknown_required
  event_classification: null
  source_status:
    status_id: 0
    status: unknown
    status_code: model_private_choice
    status_detail: selection existed inside opaque model apparatus
    source_status_label: model_private_choice
    source_status_mapping: raes.lifecycle.phase_realization.opaque
  participant_address: participants.red.llm
  episode_id: ep-red-004
  sequence_number: 16
  occurred_at: 2026-05-26T10:15:00Z
  recorded_at: 2026-05-26T10:15:02Z
  ingested_at: 2026-05-26T10:15:03Z
  clock_authority: backend.logical_clock.red-range
  temporal_context: tick-118
  ordering_basis: logical_clock
  logical_order_ref: order.red.118.16
  predecessor_event_refs: []
  actor_ref: participants.red.llm
  producer_ref: adapters.llm-tool-runtime.v2
  source_system_ref: llm-agent.red
  source_record_ref: null
  source_raw_ref: null
  source_pipeline:
    product_ref: products.llm-agent.red
    product_version: 2.4.1
    log_provider: null
    log_source: null
    log_name: null
    original_event_uid: null
    original_time: null
    processed_time: null
    logged_time: null
    transmit_time: 2026-05-26T10:15:03Z
    correlation_uid: corr-tool-call-992
    sequence: 16
  raw_data_integrity:
    raw_data_hash: null
    raw_data_hash_algorithm: null
    raw_data_size: null
    raw_data_is_truncated: null
    raw_data_untruncated_size: null
  confidence: null
  provenance_refs:
    - provenance.apparatus_boundary
  evidence_refs: []
  marking_definition_refs:
    - markings.internal.v1
  object_marking_refs:
    - markings.internal.v1
  markings:
    - internal
  granular_markings: {}
  redaction_policy_ref: redaction.no-prompts-or-secrets.v1
  authorization_scope: runtime_review
  phase: selection_or_admission
  phase_realization: opaque
  admission_disposition: unknown
  operation_ref: null
  action_ref: actions.exfiltrate_file
  action_contract_ref: contracts.file_access.v1
  command_ref: null
  actor_provenance: apparatus_opaque
  observation_refs: []
  shared_state_read_refs: []
  shared_state_write_refs: []
  emitted_state_update_refs: []
  attribution_edge_refs: []
  outcome_interpretation_refs: []
  joint_action_set_ref: null
  source_status_label: model_private_choice
  mapping_loss: private_apparatus_detail
  mapping_loss_detail: private_policy_trace_not_exposed
```

The runtime records the observable action attempt. It does not require prompt
content, chain-of-thought, policy logits, tool reasoning, or private memory.

### RL Policy Step With Observation-Only Guarantee

```yaml
interaction_context_envelope:
  event_id: interaction-cyborg-tick42
  schema_name: raes.participant_runtime.interaction_context
  schema_version: 1.0.0
  event_type: interaction_context
  extension_policy: reject_unknown_required
  event_classification: null
  source_status:
    status_id: 1
    status: success
    status_code: aec_current_actor
    status_detail: AEC step exposes blue as the current actor at tick 42
    source_status_label: cyborg_aec_current_actor
    source_status_mapping: raes.interaction_mode.agent_environment_cycle
  participant_address: null
  episode_id: null
  sequence_number: null
  occurred_at: 2026-05-26T10:20:10Z
  recorded_at: 2026-05-26T10:20:10Z
  ingested_at: 2026-05-26T10:20:11Z
  clock_authority: sim.tick
  temporal_context: tick-42
  ordering_basis: simulation_tick
  logical_order_ref: order.sim.42.interaction
  predecessor_event_refs:
    - interaction-cyborg-tick41
  actor_ref: runtime.scheduler
  producer_ref: adapters.cyborg-blue.v1
  source_system_ref: cyborg.sim
  source_record_ref: cyborg.interaction.42
  source_raw_ref: evidence.raw.cyborg.interaction.42
  source_pipeline:
    product_ref: products.cyborg.sim
    product_version: 1.0.0
    log_provider: cyborg
    log_source: cyborg.sim
    log_name: interaction-context
    original_event_uid: cyborg.interaction.42
    original_time: 2026-05-26T10:20:10Z
    processed_time: 2026-05-26T10:20:10Z
    logged_time: 2026-05-26T10:20:10Z
    transmit_time: 2026-05-26T10:20:11Z
    correlation_uid: cyborg.tick42
    sequence: 42
  raw_data_integrity:
    raw_data_hash: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    raw_data_hash_algorithm: sha256
    raw_data_size: 1024
    raw_data_is_truncated: false
    raw_data_untruncated_size: 1024
  confidence: 1.0
  provenance_refs:
    - provenance.backend_realized
  evidence_refs:
    - evidence.interaction-cyborg-tick42
  marking_definition_refs:
    - markings.internal.v1
  object_marking_refs:
    - markings.internal.v1
  markings:
    - internal
  granular_markings: {}
  redaction_policy_ref: redaction.blue-step-signal.v1
  authorization_scope: runtime_review
  interaction_context_id: interaction.cyborg.tick42
  interaction_mode: agent_environment_cycle
  order_point: order.sim.42.interaction
  possible_agent_set_ref: agents.cyborg.possible
  live_agent_set_ref: agents.cyborg.live.tick42
  active_agent_set:
    - participants.blue.rl
  current_actor_ref: participants.blue.rl
  simultaneous_group_ref: null
  nonacting_agent_policy_ref: policies.cyborg.nonacting-observe-only
  legal_action_snapshot_refs:
    participants.blue.rl: masks.blue.tick42
  chance_mode: not_applicable
  chance_distribution_ref: null
  chance_distribution_digest: null
  sampled_chance_outcome_ref: null
  chance_seed_ref: seeds.run-778-blue
  chance_visibility: not_applicable
  mean_field_population_scope_ref: null
  mean_field_population_refs: []
  mean_field_state_support_ref: null
  mean_field_distribution_ref: null
  mean_field_distribution_digest: null
  mean_field_update_rule_ref: null
  mean_field_update_ref: null
  terminal_node: false
  unsupported_interaction_disclosure: null
observation_envelope:
  event_id: obs-blue-43
  schema_name: raes.participant_runtime.observation
  schema_version: 1.0.0
  event_type: observation_emission
  extension_policy: reject_unknown_required
  event_classification:
    category_uid: 4
    category_name: findings
    class_uid: 4001
    class_name: detection_finding
    activity_id: 1
    activity_name: telemetry_observed
    type_uid: 800101
    type_name: blue telemetry observation emitted
    severity_id: 1
    severity: informational
  source_status:
    status_id: 1
    status: success
    status_code: observation_emitted
    status_detail: simulator emitted the blue local telemetry observation
    source_status_label: cyborg_observation
    source_status_mapping: raes.observation.emitted
  participant_address: participants.blue.rl
  episode_id: ep-blue-002
  sequence_number: 43
  occurred_at: 2026-05-26T10:20:10Z
  recorded_at: 2026-05-26T10:20:10Z
  ingested_at: 2026-05-26T10:20:11Z
  clock_authority: sim.tick
  temporal_context: tick-42
  ordering_basis: simulation_tick
  logical_order_ref: order.sim.42.blue.obs43
  predecessor_event_refs:
    - evt-rl-42-exec
  actor_ref: participants.blue.rl
  producer_ref: adapters.cyborg-blue.v1
  source_system_ref: cyborg.sim
  source_record_ref: cyborg.obs.42.blue
  source_raw_ref: evidence.raw.cyborg.obs.42.blue
  source_pipeline:
    product_ref: products.cyborg.sim
    product_version: 1.0.0
    log_provider: cyborg
    log_source: cyborg.sim
    log_name: observation-step
    original_event_uid: cyborg.obs.42.blue
    original_time: 2026-05-26T10:20:10Z
    processed_time: 2026-05-26T10:20:10Z
    logged_time: 2026-05-26T10:20:10Z
    transmit_time: 2026-05-26T10:20:11Z
    correlation_uid: cyborg.tick42.blue
    sequence: 42
  raw_data_integrity:
    raw_data_hash: sha256:2222222222222222222222222222222222222222222222222222222222222222
    raw_data_hash_algorithm: sha256
    raw_data_size: 2048
    raw_data_is_truncated: false
    raw_data_untruncated_size: 2048
  confidence: 1.0
  provenance_refs:
    - provenance.backend_realized
  evidence_refs:
    - evidence.obs-blue-43-redacted
  marking_definition_refs:
    - markings.participant_visible.v1
    - markings.restricted_evidence.v1
  object_marking_refs:
    - markings.participant_visible.v1
  markings:
    - participant_visible
  granular_markings:
    /hidden_state_refs:
      - restricted_evidence
  redaction_policy_ref: redaction.blue-observation.v1
  authorization_scope: participant:participants.blue.rl
  observation_ref: observations.blue.local.telemetry.43
  phase_ref: evt-rl-42-exec
  visibility_projection_ref: projections.blue.local.telemetry.v1
  information_guarantee: observation_only
  delivery_basis: emission_is_delivery
  delivery_point_ref: order.sim.42.blue.obs43
  delivered_at: 2026-05-26T10:20:10Z
  action_observation_history_ref: history.blue.ep002.prefix43
  information_state_ref: null
  hidden_state_refs:
    - evidence.hidden-world-state.tick42
  centralized_state_refs:
    - evidence.global-training-state.tick42
  loss_descriptor:
    kind: partial_projection
    fields_redacted:
      - attacker.intent
  stochastic_context:
    seed_ref: seeds.run-778-blue
    randomization_policy_ref: randomization.cyborg.default.v1
  noise_model_ref: null
  reconstruction_algorithm_ref: null
  reconstruction_proof_ref: null
  belief_support_ref: null
  redacted_field_refs:
    - /hidden_state_refs
step_signal_envelope:
  event_id: step-blue-43
  schema_name: raes.participant_runtime.step_signal
  schema_version: 1.0.0
  event_type: participant_step_signal
  extension_policy: reject_unknown_required
  event_classification: null
  source_status:
    status_id: 1
    status: success
    status_code: step_signal_emitted
    status_detail: simulator exposed governed step signal refs
    source_status_label: cyborg_step
    source_status_mapping: raes.step_signal.emitted
  participant_address: participants.blue.rl
  episode_id: ep-blue-002
  sequence_number: 43
  occurred_at: 2026-05-26T10:20:10Z
  recorded_at: 2026-05-26T10:20:10Z
  ingested_at: 2026-05-26T10:20:11Z
  clock_authority: sim.tick
  temporal_context: tick-42
  ordering_basis: simulation_tick
  logical_order_ref: order.sim.42.blue.step43
  predecessor_event_refs:
    - evt-rl-42-exec
  actor_ref: participants.blue.rl
  producer_ref: adapters.cyborg-blue.v1
  source_system_ref: cyborg.sim
  source_record_ref: cyborg.step.42.blue
  source_raw_ref: evidence.raw.cyborg.step.42.blue
  source_pipeline:
    product_ref: products.cyborg.sim
    product_version: 1.0.0
    log_provider: cyborg
    log_source: cyborg.sim
    log_name: step-signal
    original_event_uid: cyborg.step.42.blue
    original_time: 2026-05-26T10:20:10Z
    processed_time: 2026-05-26T10:20:10Z
    logged_time: 2026-05-26T10:20:10Z
    transmit_time: 2026-05-26T10:20:11Z
    correlation_uid: cyborg.tick42.blue
    sequence: 42
  raw_data_integrity:
    raw_data_hash: sha256:3333333333333333333333333333333333333333333333333333333333333333
    raw_data_hash_algorithm: sha256
    raw_data_size: 1536
    raw_data_is_truncated: false
    raw_data_untruncated_size: 1536
  confidence: 1.0
  provenance_refs:
    - provenance.backend_realized
  evidence_refs:
    - evidence.step-blue-43-redacted
  marking_definition_refs:
    - markings.participant_visible.v1
    - markings.restricted_evidence.v1
  object_marking_refs:
    - markings.participant_visible.v1
  markings:
    - participant_visible
  granular_markings:
    /centralized_state_refs:
      - restricted_evidence
  redaction_policy_ref: redaction.blue-step-signal.v1
  authorization_scope: participant:participants.blue.rl
  interaction_context_ref: interaction.cyborg.tick42
  live_agent_set_ref: agents.cyborg.live.tick42
  active_agent_set_ref: active-agents.cyborg.tick42
  current_actor_ref: participants.blue.rl
  action_ref: actions.blue.isolate_host
  observation_ref: observations.blue.local.telemetry.43
  action_mask_ref: masks.blue.tick42
  reward_ref: rewards.blue.tick42
  return_ref: returns.blue.prefix42
  termination_ref: termination.blue.tick42
  info_refs:
    - info.blue.step42.redacted
  centralized_state_refs:
    - evidence.global-training-state.tick42
```

The action mask, reward, return, and termination refs resolve to governed
step-signal records. Policy updates, optimizer state, and model state remain
apparatus internals unless an explicit evidence contract exposes a redacted
representation.

Chance and mean-field order points use the same interaction-context envelope
with an empty `active_agent_set`; their distribution, sampled outcome, update
rule, or unsupported disclosure is recorded there rather than represented as a
participant action.

### Human-Supplied Action

```yaml
lifecycle_envelope:
  event_id: evt-human-09-admission
  schema_name: raes.participant_runtime.lifecycle
  schema_version: 1.0.0
  event_type: selection_or_admission
  extension_policy: reject_unknown_required
  event_classification: null
  source_status:
    status_id: 1
    status: success
    status_code: submitted_by_operator
    status_detail: operator submitted an admitted containment command
    source_status_label: submitted_by_operator
    source_status_mapping: raes.lifecycle.admission.admitted
  participant_address: participants.gold.operator
  episode_id: ep-gold-001
  sequence_number: 9
  occurred_at: 2026-05-26T10:30:00Z
  recorded_at: 2026-05-26T10:30:02Z
  ingested_at: 2026-05-26T10:30:02Z
  clock_authority: control_plane.audit_clock
  temporal_context: wallclock-window-30
  ordering_basis: control_plane_order
  logical_order_ref: audit.gold.09
  predecessor_event_refs:
    - evt-human-08-observation
  actor_ref: users.operator-7
  producer_ref: control-plane.operator-console.v1
  source_system_ref: operator-console
  source_record_ref: command-form-9
  source_raw_ref: evidence.operator-command-9
  source_pipeline:
    product_ref: products.operator-console
    product_version: 1.8.0
    log_provider: control-plane
    log_source: operator-console
    log_name: operator-command
    original_event_uid: command-form-9
    original_time: 2026-05-26T10:30:00Z
    processed_time: 2026-05-26T10:30:02Z
    logged_time: 2026-05-26T10:30:02Z
    transmit_time: 2026-05-26T10:30:02Z
    correlation_uid: operator-command-9
    sequence: 9
  raw_data_integrity:
    raw_data_hash: sha256:4444444444444444444444444444444444444444444444444444444444444444
    raw_data_hash_algorithm: sha256
    raw_data_size: 1024
    raw_data_is_truncated: false
    raw_data_untruncated_size: 1024
  confidence: 1.0
  provenance_refs:
    - provenance.externally_supplied
  evidence_refs:
    - evidence.operator-command-9-redacted
  marking_definition_refs:
    - markings.internal.v1
  object_marking_refs:
    - markings.internal.v1
  markings:
    - internal
  granular_markings: {}
  redaction_policy_ref: redaction.operator-command.v1
  authorization_scope: runtime_review
  phase: selection_or_admission
  phase_realization: externally_supplied
  admission_disposition: admitted
  operation_ref: null
  action_ref: actions.approve_containment
  action_contract_ref: contracts.defense.approve-containment.v1
  command_ref: null
  actor_provenance: human_operator
  observation_refs: []
  shared_state_read_refs:
    - incident.queue.web01@rev12
  shared_state_write_refs: []
  emitted_state_update_refs: []
  attribution_edge_refs: []
  outcome_interpretation_refs: []
  joint_action_set_ref: null
  source_status_label: submitted_by_operator
  mapping_loss: none
  mapping_loss_detail: null
```

The human operator is represented through the same participant runtime boundary
as an automated agent; the source of selection is external, not opaque.

### Asynchronous Cyber Action

```yaml
operation_record:
  event_id: op-red-55-running
  schema_name: raes.participant_runtime.operation
  schema_version: 1.0.0
  event_type: operation_advance
  extension_policy: reject_unknown_required
  event_classification: null
  source_status:
    status_id: 2
    status: in_progress
    status_code: running
    status_detail: caldera link is running
    source_status_label: running
    source_status_mapping: raes.operation_state.running
  participant_address: participants.red.playbook
  episode_id: ep-red-006
  sequence_number: 55
  occurred_at: 2026-05-26T10:40:30Z
  recorded_at: 2026-05-26T10:40:31Z
  ingested_at: 2026-05-26T10:40:32Z
  clock_authority: backend.logical_clock.caldera
  temporal_context: operation-window-55
  ordering_basis: logical_clock
  logical_order_ref: caldera.order.55
  predecessor_event_refs:
    - op-red-55-ack
  actor_ref: participants.red.playbook
  producer_ref: adapters.caldera.v1
  source_system_ref: caldera.operation.abc
  source_record_ref: link.1234
  source_raw_ref: evidence.raw.caldera.link.1234
  source_pipeline:
    product_ref: products.caldera
    product_version: 5.1.0
    log_provider: caldera
    log_source: caldera.operation.abc
    log_name: link-state
    original_event_uid: link.1234
    original_time: 2026-05-26T10:40:30Z
    processed_time: 2026-05-26T10:40:31Z
    logged_time: 2026-05-26T10:40:31Z
    transmit_time: 2026-05-26T10:40:32Z
    correlation_uid: caldera.operation.abc.link.1234
    sequence: 55
  raw_data_integrity:
    raw_data_hash: sha256:5555555555555555555555555555555555555555555555555555555555555555
    raw_data_hash_algorithm: sha256
    raw_data_size: 8192
    raw_data_is_truncated: true
    raw_data_untruncated_size: 23142
  confidence: 0.9
  provenance_refs:
    - provenance.backend_realized
  evidence_refs:
    - evidence.caldera.link.1234-redacted
  marking_definition_refs:
    - markings.internal.v1
    - markings.restricted_evidence.v1
  object_marking_refs:
    - markings.internal.v1
  markings:
    - internal
  granular_markings:
    /source_raw_ref:
      - restricted_evidence
  redaction_policy_ref: redaction.cyber-action.v1
  authorization_scope: runtime_review
  operation_id: op-red-55
  action_ref: actions.credential_dump
  action_contract_ref: contracts.attack.credential-dump.v1
  command_ref: commands.caldera.link.1234
  state: running
  predecessor_operation_ref: op-red-55-ack
  idempotency_ref: idem.red.credential-dump.55
  correlation_ref: caldera.operation.abc.link.1234
  progress_refs:
    - progress.red.55.started
  streamed_observation_refs:
    - obs-red-55-stdout-1
  partial_result_refs: []
  timeout_policy_ref: timeout.operation.5m
  cancellation_policy_ref: cancellation.best-effort.v1
  retry_policy_ref: retry.none
  terminal_result_ref: null
cyber_action_envelope:
  event_id: cyber-red-55
  schema_name: raes.participant_runtime.cyber_action
  schema_version: 1.0.0
  event_type: cyber_action_context
  extension_policy: reject_unknown_required
  event_classification:
    category_uid: 6
    category_name: application_activity
    class_uid: 6003
    class_name: api_activity
    activity_id: 1
    activity_name: command_execution
    type_uid: 1200301
    type_name: caldera command execution context
    severity_id: 2
    severity: low
  source_status:
    status_id: 2
    status: in_progress
    status_code: running
    status_detail: caldera command context recorded while link is running
    source_status_label: running
    source_status_mapping: raes.operation_state.running
  participant_address: participants.red.playbook
  episode_id: ep-red-006
  sequence_number: 55
  occurred_at: 2026-05-26T10:40:30Z
  recorded_at: 2026-05-26T10:40:31Z
  ingested_at: 2026-05-26T10:40:32Z
  clock_authority: backend.logical_clock.caldera
  temporal_context: operation-window-55
  ordering_basis: logical_clock
  logical_order_ref: caldera.order.55
  predecessor_event_refs:
    - evt-red-55-exec
  actor_ref: participants.red.playbook
  producer_ref: adapters.caldera.v1
  source_system_ref: caldera.operation.abc
  source_record_ref: ability.cred-dump.link.1234
  source_raw_ref: evidence.raw.caldera.link.1234
  source_pipeline:
    product_ref: products.caldera
    product_version: 5.1.0
    log_provider: caldera
    log_source: caldera.operation.abc
    log_name: ability-link
    original_event_uid: ability.cred-dump.link.1234
    original_time: 2026-05-26T10:40:30Z
    processed_time: 2026-05-26T10:40:31Z
    logged_time: 2026-05-26T10:40:31Z
    transmit_time: 2026-05-26T10:40:32Z
    correlation_uid: caldera.operation.abc.link.1234
    sequence: 55
  raw_data_integrity:
    raw_data_hash: sha256:6666666666666666666666666666666666666666666666666666666666666666
    raw_data_hash_algorithm: sha256
    raw_data_size: 8192
    raw_data_is_truncated: true
    raw_data_untruncated_size: 23142
  confidence: 0.9
  provenance_refs:
    - provenance.backend_realized
  evidence_refs:
    - evidence.caldera.link.1234-redacted
  marking_definition_refs:
    - markings.internal.v1
    - markings.secret_ref.v1
  object_marking_refs:
    - markings.internal.v1
  markings:
    - internal
  granular_markings:
    /credential_ref:
      - secret_ref
  redaction_policy_ref: redaction.cyber-action.v1
  authorization_scope: runtime_review
  action_ref: actions.credential_dump
  action_contract_ref: contracts.attack.credential-dump.v1
  command_ref: commands.caldera.link.1234
  command_family: caldera
  action_verb: execute
  target_ref: hosts.workstation01
  argument_refs:
    - args.cred-dump.safe-summary
  openc2_profile_ref: null
  openc2_command_id: null
  openc2_request_id: null
  openc2_action: null
  openc2_target_ref: null
  openc2_args_ref: null
  openc2_actuator_ref: null
  openc2_response_ref: null
  openc2_response_status: null
  openc2_response_status_text: null
  openc2_response_results_ref: null
  cacao_playbook_ref: playbooks.red.credential-access
  cacao_workflow_step_ref: cacao.step.credential-access.4
  cacao_workflow_step_type: command
  cacao_command_refs:
    - commands.caldera.link.1234
  cacao_agent_refs:
    - agents.caldera.red.01
  cacao_target_refs:
    - hosts.workstation01
  cacao_variable_refs:
    - variables.target_host.redacted
  cacao_authentication_ref: auth_refs.redacted.caldera-agent
  cacao_on_completion_ref: cacao.step.credential-access.5
  cacao_on_success_ref: cacao.step.credential-access.5
  cacao_on_failure_ref: cacao.step.cleanup.1
  cacao_external_refs:
    - attack.T1003
  caldera_operation_ref: caldera.operation.abc
  caldera_adversary_ref: caldera.adversary.red
  caldera_planner_ref: caldera.planner.atomic
  caldera_ability_ref: caldera.ability.cred-dump
  caldera_link_ref: caldera.link.1234
  caldera_fact_refs:
    - caldera.fact.credential-cache
  caldera_agent_ref: agents.caldera.red.01
  actuator_ref: agents.caldera.red.01
  executor_ref: processes.agent-01
  session_ref: sessions.red.workstation01.user
  authority_ref: authorities.domain.local
  privilege_context_ref: privileges.user
  credential_ref: credentials.redacted.cred-77
  tool_ref: tools.mimikatz.redacted-profile
  playbook_step_ref: cacao.step.credential-access.4
  attack_technique_refs:
    - attack.T1003
  knowledge_delta_refs:
    - knowledge.red.discovered-credential@rev2
  foothold_delta_refs: []
  visibility_delta_refs:
    - visibility.blue.edr-alert@rev5
  detection_surface_refs:
    - detections.edr.credential-access
  response_refs: []
  observation_refs:
    - obs-red-55-stdout-1
  outcome_refs: []
```

The action can stream observations and update state before completion. Raw
credential values and unredacted command output remain controlled evidence.

### Simultaneous Conflict Over Shared State

```yaml
joint_action_record:
  event_id: joint-13
  schema_name: raes.participant_runtime.joint_action
  schema_version: 1.0.0
  event_type: concurrent_attempt
  extension_policy: reject_unknown_required
  event_classification: null
  source_status:
    status_id: 1
    status: success
    status_code: conflict_rejected
    status_detail: runtime detected simultaneous shared-state conflict
    source_status_label: conflict_rejected
    source_status_mapping: raes.conflict_policy.reject
  participant_address: null
  episode_id: null
  sequence_number: null
  occurred_at: 2026-05-26T10:50:00Z
  recorded_at: 2026-05-26T10:50:01Z
  ingested_at: 2026-05-26T10:50:01Z
  clock_authority: sim.tick
  temporal_context: tick-88
  ordering_basis: simultaneous
  logical_order_ref: sim.tick.88
  predecessor_event_refs:
    - joint-12
  actor_ref: runtime.scheduler
  producer_ref: backend.cyborg-adapter.v1
  source_system_ref: cyborg.sim
  source_record_ref: sim.tick.88.joint
  source_raw_ref: evidence.raw.sim.tick88
  source_pipeline:
    product_ref: products.cyborg.sim
    product_version: 1.0.0
    log_provider: cyborg
    log_source: cyborg.sim
    log_name: joint-action
    original_event_uid: sim.tick.88.joint
    original_time: 2026-05-26T10:50:00Z
    processed_time: 2026-05-26T10:50:01Z
    logged_time: 2026-05-26T10:50:01Z
    transmit_time: 2026-05-26T10:50:01Z
    correlation_uid: sim.tick.88
    sequence: 88
  raw_data_integrity:
    raw_data_hash: sha256:7777777777777777777777777777777777777777777777777777777777777777
    raw_data_hash_algorithm: sha256
    raw_data_size: 3072
    raw_data_is_truncated: false
    raw_data_untruncated_size: 3072
  confidence: 1.0
  provenance_refs:
    - provenance.backend_realized
  evidence_refs:
    - evidence.sim.tick88.joint
  marking_definition_refs:
    - markings.internal.v1
  object_marking_refs:
    - markings.internal.v1
  markings:
    - internal
  granular_markings: {}
  redaction_policy_ref: redaction.shared-state.v1
  authorization_scope: runtime_review
  joint_action_set_id: joint-13
  coordination_interval: tick-88
  member_event_refs:
    - evt-red-88
    - evt-blue-88
  realized_order_relation:
    simultaneous_groups:
      - [evt-red-88, evt-blue-88]
    before: []
  clock_context:
    simulation_tick: 88
  time_management_context_ref: time.sim.tick88
  snapshot_basis:
    hosts.web01.service.http: rev7
  isolation_guarantee: snapshot
  atomicity_scope: joint_action
  read_set:
    evt-red-88:
      - hosts.web01.service.http@rev7
    evt-blue-88:
      - hosts.web01.service.http@rev7
  write_set:
    evt-red-88:
      - hosts.web01.service.http@rev8-red
    evt-blue-88:
      - hosts.web01.service.http@rev8-blue
  exclusive_resource_claims:
    - hosts.web01.service.http
  conflict_class: interference
  conflict_policy: reject
  retry_policy_ref: retry.none
  rollback_refs: []
  capability_guarantee_vector:
    ordering: exact
    isolation: bounded
    conflict_detection: exact
    conflict_resolution: bounded
    shared_state_revision: exact
    provenance: bounded
  participant_observation_refs:
    participants.red: obs-red-88-conflict
    participants.blue: obs-blue-88-conflict
time_management_context:
  event_id: time-sim-88
  schema_name: raes.participant_runtime.time_management
  schema_version: 1.0.0
  event_type: time_management_context
  extension_policy: reject_unknown_required
  event_classification: null
  source_status:
    status_id: 1
    status: success
    status_code: time_grant_recorded
    status_detail: logical time advance evidence recorded for tick 88
    source_status_label: time_grant_recorded
    source_status_mapping: raes.time_management.devs_discrete_event
  participant_address: null
  episode_id: null
  sequence_number: null
  occurred_at: 2026-05-26T10:50:00Z
  recorded_at: 2026-05-26T10:50:01Z
  ingested_at: 2026-05-26T10:50:01Z
  clock_authority: sim.tick
  temporal_context: tick-88
  ordering_basis: simulation_tick
  logical_order_ref: sim.tick.88
  predecessor_event_refs:
    - joint-12
  actor_ref: runtime.scheduler
  producer_ref: backend.cyborg-adapter.v1
  source_system_ref: cyborg.sim
  source_record_ref: sim.tick.88.time
  source_raw_ref: evidence.raw.sim.tick88
  source_pipeline:
    product_ref: products.cyborg.sim
    product_version: 1.0.0
    log_provider: cyborg
    log_source: cyborg.sim
    log_name: time-management
    original_event_uid: sim.tick.88.time
    original_time: 2026-05-26T10:50:00Z
    processed_time: 2026-05-26T10:50:01Z
    logged_time: 2026-05-26T10:50:01Z
    transmit_time: 2026-05-26T10:50:01Z
    correlation_uid: sim.tick.88
    sequence: 88
  raw_data_integrity:
    raw_data_hash: sha256:8888888888888888888888888888888888888888888888888888888888888888
    raw_data_hash_algorithm: sha256
    raw_data_size: 3072
    raw_data_is_truncated: false
    raw_data_untruncated_size: 3072
  confidence: 1.0
  provenance_refs:
    - provenance.backend_realized
  evidence_refs:
    - evidence.sim.tick88.time
  marking_definition_refs:
    - markings.internal.v1
  object_marking_refs:
    - markings.internal.v1
  markings:
    - internal
  granular_markings: {}
  redaction_policy_ref: redaction.shared-state.v1
  authorization_scope: runtime_review
  time_context_id: time.sim.tick88
  time_domain: simulation_tick
  time_management_mode: devs_discrete_event
  logical_time: 88
  simulation_time: tick-88
  wall_clock_interval: null
  lookahead: 1_tick
  time_regulating: true
  time_constrained: true
  time_advance_request_ref: time-request.tick88
  time_advance_grant_ref: time-grant.tick88
  next_event_request_ref: null
  message_send_refs:
    - msg.red.88.action
    - msg.blue.88.action
  message_receive_refs:
    - msg.runtime.88.conflict-result
  pacing_policy_ref: sim.pacing.logical
  step_size_ref: step.tick.1
  rollback_window_ref: null
  rollback_refs: []
  anti_message_refs: []
  compensation_refs: []
  superseded_event_refs: []
  transition_basis: confluent
```

The conflict is portable because read/write revisions, simultaneous grouping,
isolation, conflict class, policy, and per-participant observations are
explicit.

### Backend-Serialized Weak Concurrency

```yaml
joint_action_record:
  event_id: joint-21
  schema_name: raes.participant_runtime.joint_action
  schema_version: 1.0.0
  event_type: backend_serialized_attempt
  extension_policy: reject_unknown_required
  event_classification: null
  source_status:
    status_id: 2
    status: weak_guarantee
    status_code: backend_serialized
    status_detail: backend serialized the attempts and cannot prove simultaneity
    source_status_label: backend_serialized
    source_status_mapping: raes.conflict_policy.disclose_weak_guarantee
  participant_address: null
  episode_id: null
  sequence_number: null
  occurred_at: 2026-05-26T11:00:00Z
  recorded_at: 2026-05-26T11:00:02Z
  ingested_at: 2026-05-26T11:00:03Z
  clock_authority: backend.scheduler.log
  temporal_context: wallclock-window-21
  ordering_basis: serialized_backend_order
  logical_order_ref: scheduler.window.21
  predecessor_event_refs:
    - joint-20
  actor_ref: backend.scheduler
  producer_ref: backend.adapter.v1
  source_system_ref: backend.scheduler
  source_record_ref: scheduler.log.21
  source_raw_ref: evidence.raw.scheduler.log.21
  source_pipeline:
    product_ref: products.backend.scheduler
    product_version: 3.2.0
    log_provider: backend
    log_source: backend.scheduler
    log_name: scheduler-order
    original_event_uid: scheduler.log.21
    original_time: 2026-05-26T11:00:00Z
    processed_time: 2026-05-26T11:00:02Z
    logged_time: 2026-05-26T11:00:02Z
    transmit_time: 2026-05-26T11:00:03Z
    correlation_uid: scheduler.window.21
    sequence: 21
  raw_data_integrity:
    raw_data_hash: sha256:9999999999999999999999999999999999999999999999999999999999999999
    raw_data_hash_algorithm: sha256
    raw_data_size: 6144
    raw_data_is_truncated: false
    raw_data_untruncated_size: 6144
  confidence: 0.7
  provenance_refs:
    - provenance.backend_realized
  evidence_refs:
    - evidence.backend-scheduler-log-21
  marking_definition_refs:
    - markings.internal.v1
  object_marking_refs:
    - markings.internal.v1
  markings:
    - internal
  granular_markings: {}
  redaction_policy_ref: redaction.scheduler-log.v1
  authorization_scope: runtime_review
  joint_action_set_id: joint-21
  coordination_interval: wallclock-window-21
  member_event_refs:
    - evt-a
    - evt-b
  realized_order_relation:
    before:
      - [evt-a, evt-b]
    simultaneous_groups: []
  clock_context:
    scheduler_sequence:
      evt-a: 1201
      evt-b: 1202
  time_management_context_ref: time.backend.window21
  snapshot_basis:
    shared.queue: rev44
  isolation_guarantee: best_effort
  atomicity_scope: backend_transaction
  read_set:
    evt-a:
      - shared.queue@rev44
    evt-b:
      - shared.queue@rev45
  write_set:
    evt-a:
      - shared.queue@rev45
    evt-b:
      - shared.queue@rev46
  exclusive_resource_claims:
    - shared.queue
  conflict_class: serialization
  conflict_policy: disclose_weak_guarantee
  retry_policy_ref: retry.unsupported
  rollback_refs: []
  capability_guarantee_vector:
    ordering: disclosed_weak
    isolation: disclosed_weak
    conflict_detection: bounded
    conflict_resolution: disclosed_weak
    shared_state_revision: bounded
    provenance: bounded
  participant_observation_refs:
    participants.a: obs-a-21
    participants.b: obs-b-21
```

This record can support review of what happened. It cannot support a claim that
the backend executed true simultaneity or serializable isolation.

## RUN-305 - Participant Runtime State And History

`RUN-305` requires portable state and history for participants, including
actions, observations, state changes, and outcomes.

Design commitments:

- participant runtime history is append-only and keyed by participant and
  episode identity;
- behavior history links action attempts, observations, state updates,
  temporal context, attribution, and outcome interpretation;
- operation history links long-running actions, progress, partial results,
  terminal states, timeouts, and cancellation;
- shared operational state is recorded through versioned state records, not
  metadata;
- history distinguishes participant-local state, shared state, visibility,
  evidence, outcomes, scoring state, and centralized-training state;
- RL/MARL step signals are recorded as action/observation space, action-mask,
  reward, return, termination, truncation, and auxiliary-info records when a
  backend exposes them;
- RL/MARL/game interaction context records preserve possible/live/active-agent,
  current-actor, simultaneous, chance-node, and mean-field update semantics when
  claims depend on them;
- information-state claim strength is explicit for each participant-visible
  observation;
- opaque participant phases are recorded honestly as unknown or not exposed
  rather than fabricated;
- benchmark run context is present when runtime records support comparison or
  reproducibility claims;
- explicit benchmark validity claims are present when runtime records are used
  for comparative, non-contamination, cost-normalized, or V&V/correspondence
  conclusions.

Issue #192 implements the bounded `RUN-305` runtime state/history trace for
portable participant episode state and behavior history. The implementation
claim is intentionally limited to the fields and validators below; stronger
claims such as full benchmark validity, shared-state revision discipline,
RL/MARL step-signal support, RO-Crate export, or distributed-concurrency
semantics require the separate contract rows named in the traceability matrix.

Implemented enforcement surfaces:

- contract fields: `RuntimeSnapshot.participant_episode_results`,
  `RuntimeSnapshot.participant_episode_history`, and
  `RuntimeSnapshot.participant_behavior_history`;
- public/persistence parity: `ControlPlaneStore` persists the three fields and
  the HTTP `/snapshot` DTO publishes the same participant behavior history
  field instead of dropping it;
- schema gates: `RuntimeSnapshotEnvelopeModel.participant_behavior_history`
  uses `ParticipantBehaviorHistoryEventModel`; common event identity fields are
  non-empty, `event_type` and `observation_status` use closed portable
  vocabularies, `realized_order` is non-negative when present, and generated
  schema drift is checked by the contract-schema parity tests;
- semantic gates: `iter_participant_behavior_snapshot_violations` rejects
  malformed behavior-history maps, non-list histories, non-mapping events,
  missing common identity fields, unknown event types, outer-key /
  `participant_address` mismatches, invalid optional-field shape, duplicate
  `shared_state_refs`, metadata/detail-map smuggling of participant runtime
  state, and behavior events that reference an episode absent from the
  participant episode state/history surfaces when those episode surfaces are
  present;
- transition gates:
  `iter_participant_runtime_history_transition_violations` rejects backend
  apply results that delete, shrink, or rewrite existing participant episode or
  behavior history prefixes;
- runtime apply gate:
  `participant_runtime_state_contract_diagnostics` combines RUN-311 episode
  snapshot invariants with the RUN-305 behavior-history snapshot validator; the
  backend apply path then applies the append-only transition validator before
  persisting returned snapshots, comparing against a defensive baseline rather
  than a backend-mutable snapshot object, and rejects invalid snapshots with
  `runtime.backend-contract-invalid` diagnostics;
- SEM gates: the existing participant-semantics conformance validators remain
  authoritative for deeper SEM-208/211/213/215 action, observation, temporal,
  attribution, visibility, and outcome checks; the RUN-305 runtime gate does not
  duplicate that semantic layer;
- probes: `test_run_305_participant_runtime_state_history.py` covers public
  `/snapshot` parity, backend-apply rejection, outer/inner participant mismatch,
  unknown episode anchoring when episode surfaces exist, metadata state
  smuggling, append-only history rewrite/deletion rejection, and model/schema
  rejection of unsupported behavior event types.

Remaining artifacts not claimed by issue #192:

- separate base participant runtime event envelopes beyond the existing
  `runtime-snapshot/v1` publication;
- base envelope fields for schema version, event type, source refs, markings,
  and temporal context;
- operation record model for asynchronous actions;
- step-signal contract models for action masks, rewards, returns,
  termination/truncation, and auxiliary info;
- full validation that behavior history references known action, operation,
  observation, and shared-state addresses beyond the episode anchoring and
  SEM-conformance checks already available when those compiled surfaces are
  supplied;
- validation that hidden truth, scoring state, and centralized-training state
  are not exposed as participant-visible observations without projection rules;
- validation that rewards, returns, action masks, and terminal/truncation
  signals cannot be inferred from hidden scorer/backend state;
- validation that comparative benchmark conclusions cite metric aggregation,
  uncertainty, treatment assignment, validity threats, baseline comparability,
  evaluator leakage, exposure, exclusion, retry, cost-normalization, and
  artifact-immutability procedures;
- tests proving reset/restart do not rewrite history;
- fixtures for opaque participants that expose attempts and observations
  without internal planning traces;
- fixtures proving marked/redacted evidence cannot leak through public runtime
  records;
- fixtures proving mismatched evidence digests and unsupported validity-threat
  omissions are rejected or downgraded.

## Executable Invariant Oracle - Participant Runtime Trace Predicates

Issue #486 delivers an executable abstract oracle for the participant-runtime
trace predicates named by `ValidTrace(tr)`. The artifact is intentionally an
assurance/test model for `ASR-505` and ADR-054 evidence; it does not implement
the full RUN-306 lifecycle, RUN-307 shared-state model, or RUN-308 concurrent
execution runtime surfaces.

Implementation artifact:

- `implementations/python/tests/test_participant_runtime_invariants.py`

Bidirectional predicate mapping:

| Spec predicate | Spec anchor | Oracle/test coverage |
| --- | --- | --- |
| `ValidTrace(tr)` | `Valid Trace Predicate` | `valid_trace`, `test_valid_trace_accepts_generated_valid_traces`, `test_valid_trace_rejects_targeted_mutations` |
| `MonotoneSequence(tr)` | `Valid Trace Predicate` / predicate bullet | `monotone_sequence`, `test_monotone_sequence_accepts_generated_valid_traces`, `test_monotone_sequence_rejects_sequence_regression` |
| `RevisionDiscipline(tr)` | `Valid Trace Predicate` / predicate bullet | `revision_discipline`, `test_revision_discipline_accepts_generated_valid_traces`, `test_revision_discipline_accepts_known_unknown_and_unsupported_write_support`, `test_revision_discipline_rejects_unknown_prior_revision`, `test_revision_discipline_rejects_invalid_disclosure_specific_writes` |
| `OrderDiscipline(tr)` | `Valid Trace Predicate` / predicate bullet | `order_discipline`, `test_order_discipline_accepts_generated_valid_traces`, `test_order_discipline_accepts_supported_order_claim_strengths`, `test_order_discipline_rejects_wall_clock_causality`, `test_order_discipline_rejects_claim_without_declared_basis` |
| `ConflictOK(j, tr)` | `Concurrent Participant Execution` conflict predicates | `conflict_ok`, `test_conflict_ok_accepts_generated_valid_traces`, `test_conflict_ok_accepts_supported_conflict_policy_variants`, `test_conflict_ok_rejects_undisclosed_concurrent_write_conflict`, `test_conflict_ok_rejects_invalid_policy_specific_records`, `test_conflict_ok_rejects_joint_action_witnesses_that_are_not_exact_permutations` |
| `TimeManagementOK(tm, tr)` | `Concurrent Participant Execution` time-management predicates | `time_management_ok`, `test_time_management_ok_accepts_generated_valid_traces`, `test_time_management_ok_accepts_supported_time_mode_variants`, `test_time_management_ok_rejects_wall_clock_exact_time_claim`, `test_time_management_ok_rejects_invalid_mode_specific_contexts` |

The test module maps back to these spec anchors in its module docstring and
predicate docstrings. Its Hypothesis generator varies valid abstract traces
across revision-support disclosures, order-claim strengths, conflict policies,
and time-management modes. Its mutation helpers isolate sequence regression,
revision violation, order violation, invalid conflict witnesses/policies, and
time-domain violations as negative evidence.

## RUN-306 - Participant Decision And Execution Lifecycle

`RUN-306` requires a portable lifecycle for action proposal, selection,
execution, observation, and state update.

Design commitments:

- lifecycle phases are observable runtime event points;
- phase realization, admission disposition, and operation state use separate
  closed vocabularies;
- proposal and selection may be opaque, externally supplied, unknown, not
  applicable, or unsupported;
- admission may be admitted, rejected, withheld, unknown, or not applicable;
- execution attempts remain tied to governed action contracts, command context,
  actor provenance, and operation records when asynchronous;
- observations are emitted through participant observation boundaries;
- state updates commit through participant-local and shared-state records;
- step signals preserve RL/game-facing rewards, returns, masks,
  termination/truncation, and info without requiring participant internals;
- AEC/current-actor, possible/live/active-agent, chance, and mean-field node
  semantics are separate interaction-context records, not inferred from final
  observations or action lists;
- the lifecycle is separate from episode lifecycle, workflow state, evaluator
  state, control-plane operation status, and participant internals.

Future implementation artifacts:

- lifecycle phase, phase-realization, admission-disposition, and operation-state
  vocabulary;
- runtime event envelope linking lifecycle phase, action contract, participant,
  episode, temporal context, operation, observation, and state update;
- runtime step-signal envelope linking action attempts, observations, action
  masks, rewards, returns, termination, truncation, and info refs when present;
- interaction-context envelope for sequential/AEC, simultaneous, chance, and
  mean-field order points;
- fixtures for `Opaque`, `Unknown`, `NotApplicable`, and `Unsupported` values
  that prove they are not collapsed;
- fixtures for `Rejected`, `Withheld`, `TimedOut`, `Cancelled`, `Partial`, and
  `Failed` values showing they are not phase-realization modes;
- validation that hidden participant internals are not required or leaked;
- negative fixtures showing LLM/RL/human/script participants can satisfy the
  boundary without exposing internal planning loops.

## RUN-307 - Shared Operational State Model

`RUN-307` requires a portable shared operational state model for evolving
participant and environment state.

Design commitments:

- shared operational state is a typed runtime contract surface;
- records carry state address, kind, revision/digest, predecessor revisions,
  ordering basis, conflict policy, visibility projection, provenance, markings,
  and evidence refs;
- read/write access records carry prior and written revisions when known;
- state updates are explicit behavior-history events;
- shared state remains separate from hidden world state, participant-visible
  projection, participant belief/history, centralized-training state, scoring
  state, and archival evidence;
- backend-native stores may realize the state internally but do not define the
  portable semantics;
- cyber action knowledge, foothold, visibility, detection, and outcome deltas
  are shared-state or evidence references when used for portable claims.

Future implementation artifacts:

- shared state record/envelope model;
- compiler/runtime address convention for state records;
- validation of state refs from action contracts and behavior history;
- conformance checks rejecting metadata-only shared state;
- tests for revision, digest, read/write access, markings, redaction, and
  visibility-projection rules;
- tests proving hidden/scoring/centralized-training state cannot be confused
  with participant-visible state.

## RUN-308 - Concurrent Participant Execution

`RUN-308` requires concurrent participant execution and interaction over shared
scenario state.

Design commitments:

- concurrency is modeled through joint action sets, realized order relations,
  logical clock context, isolation guarantees, atomicity scope, revisions, and
  conflict policy;
- distributed-simulation concurrency additionally records time-management mode,
  lookahead, time-advance grants, message causality, rollback/anti-message or
  step-negotiation semantics when those claims are made;
- coordination, contention, interference, serialization, rollback, retry,
  rejection, weak guarantee, and unsupported simultaneity remain explicit
  interaction classes;
- conflicts are detected over semantic read/write sets, exclusive resource
  claims, visibility effects, evidence streams, sessions, authorities,
  actuators, and contract interference;
- authored participant interactions declare portable composition with either
  `commutative: true` or a governed `merge_rule_ref`; absence of both keeps
  overlapping interaction footprints serialized, and the declarations do not
  authorize implicit same-revision last-writer-wins;
- concurrent state updates record read/write revisions and realized ordering;
- participant-local observations may differ even when they refer to the same
  shared event;
- backends that serialize, reject, drop, roll back, retry, or weaken
  concurrency guarantees must disclose that realization;
- capability support is evaluated with guarantee vectors, not a scalar minimum.

Future implementation artifacts:

- joint action / shared-state conflict validation;
- capability guarantee validation across lifecycle, admission, operation,
  observation, step-signal, shared-state, ordering, time-management, rollback,
  isolation, conflict, redaction, provenance, replay, and benchmark concerns;
- property or differential tests for serialized versus simultaneous conflicting
  attempts;
- model-checkable or executable state-machine tests for ordering/isolation,
  rollback, and time-management claims;
- model-checkable or property tests for possible/live/active-agent,
  current-actor, chance, and mean-field claim validity where those surfaces are
  implemented;
- conformance checks for missing order/revision/conflict/isolation metadata;
- backend capability evidence for supported concurrency guarantees.

## Primary Reference Surface

This design should be reviewed against the source map in
`docs/explain/sdl/lineage.md` and, at minimum, these primary reference
families:

- Gymnasium/OpenAI Gym, PettingZoo, and OpenSpiel for action spaces,
  observation spaces, rewards, returns, termination/truncation, action masks,
  per-agent histories, possible/live/active-agent and current-actor state,
  chance nodes, mean-field updates, simultaneous moves, and information-state
  discipline.
- POMDP, Dec-POMDP, POSG, and Markov-game literature for partial observability
  and multi-agent information boundaries, with Oliehoek and Amato's Dec-POMDP
  monograph as the consolidated vocabulary reference.
- Interpreted systems (Fagin, Halpern, Moses, Vardi), dynamic epistemic logic
  (Baltag-Moss-Solecki; van Ditmarsch, van der Hoek, Kooi), and Kuhn's
  extensive-form information sets and perfect recall for information-state,
  indistinguishability, and history semantics.
- Fidge/Mattern vector time and the Schwarz-Mattern causality survey for the
  `VectorClock` ordering basis; Winskel event structures and Mazurkiewicz trace
  theory for partial-order realized ordering with simultaneity groups.
- Berenson et al.'s ANSI SQL isolation critique and Adya's generalized
  isolation theory for the isolation-guarantee vocabulary.
- Mean-field game theory (Huang, Caines, Malhamé; Lasry and Lions; Yang et al.)
  for mean-field node and population-distribution semantics.
- CybORG, CyberBattleSim, CyGIL, CALDERA, ATT&CK, OpenC2, and CACAO for cyber
  action, sensing, command/response, playbook, knowledge, foothold, detection,
  and sim-to-emulation realization disclosure.
- OCSF and STIX for event classification, normalized status/severity, schema
  versioning, source/raw mapping, confidence, markings, granular selectors, and
  extension discipline.
- Lamport clocks, IEEE HLA time management, Time Warp, DEVS, FMI, and related
  distributed-simulation work for order, time advance, lookahead, rollback,
  pacing, and synchronization.
- Cybench, AutoPenBench, CAIBench, AI Agents That Matter, and offensive
  security benchmark-methodology work for run records, repeated trials,
  baseline/evaluator disclosure, cost normalization, scaffold exposure,
  contamination audits, and holdout/canary discipline.
- W3C PROV, FAIR, RO-Crate, ACM artifact review, and cyber-range/simulation V&V
  literature for provenance entities/activities/agents, persistent identifiers,
  qualified artifact references, machine-actionable metadata, reusable research
  packages, artifact availability limits, validity threats, and testbed
  correspondence evidence.

## Non-Goals

- Defining new SDL participant syntax.
- Implementing participant runtime contracts or backends in this issue.
- Requiring participants to reveal chain-of-thought, prompts, policy internals,
  private/internal reward updates, private memory, or tool traces.
- Treating backend-native stores, logs, timestamps, or scheduler order as the
  portable runtime semantics.
- Treating hidden reward calculators, policy optimizer state,
  centralized-training state, model internals, or scorer state as participant
  runtime semantics. Participant-visible reward and return signals are portable
  only through governed step-signal records.
- Defining a solver, policy optimizer, reward-learning API, centralized-training
  protocol, or training framework API.
- Redesigning full archival study management beyond the runtime fields needed
  to preserve participant history, shared-state evidence, and reproducibility
  claims.
