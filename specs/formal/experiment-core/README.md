# Experiment Core Formal Specification

This domain specifies the EXP-701 through EXP-705 experiment-core contract
boundary plus the EXP-706 trial/replication interpretation, the EXP-707,
EXP-708, EXP-709, and EXP-715 evidence/measure extension, the EXP-710,
EXP-720, and EXP-722 run provenance extension, and the EXP-712
reproducibility/replay claim-support interpretation:

- `experiment-task-v1`
- `experiment-apparatus-context-v1`
- `experiment-run-v1`
- `experiment-study-v1`
- `experiment-capture-spec-v1`
- `experiment-evidence-record-v1`
- `experiment-derived-measure-v1`
- `experiment-authoring-input-v1` (pre-run authoring input; ADR-074)
- optional `backend-manifest-v2` `capabilities.observation`
- canonical run traceability and realized-form disclosures inside
  `experiment-run-v1`

The contracts describe cyber range experiment artifacts. They do not implement
execution, storage, scheduling, APIs, or analysis engines.

`experiment-authoring-input-v1` (ADR-074) is the one input contract in this
domain: the pre-run experiment *specification* that binds a task to a run plan
before execution. It is the authoring counterpart to the archival run, study,
and apparatus-context outputs, analogous to how `sdl-authoring-input-v1` is the
authored counterpart to `instantiated-scenario-v1`.

## FM Classification

Classification: FM2, Semantic Graph / Constraint.

Rationale:

- The design is not only local schema shape. It defines cross-artifact
  relationships between scenarios, tasks, apparatus contexts, runs, results, and
  studies.
- The required properties include type separation, provenance links,
  uniqueness, validity framing, apparatus/run distinction, and study membership
  constraints.
- The implementation evidence for this design is closed-world contract models,
  generated JSON Schemas, fixtures, and unit tests. It does not introduce an
  FM3 runtime state machine.

## Authoritative Artifacts

- Normative prose: this directory.
- Architecture decisions:
  `docs/decisions/adrs/adr-055-experiment-core-contract-boundary.md` and
  `docs/decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md`,
  and
  `docs/decisions/adrs/adr-065-experiment-run-provenance-contract-boundary.md`,
  and
  `docs/decisions/adrs/adr-068-experiment-trials-replication-and-replay-claims.md`,
  and
  `docs/decisions/adrs/adr-074-experiment-authoring-input-contract-boundary.md`.
- Machine-readable schemas: `contracts/schemas/experiment-core/`.
- Contract source: `implementations/python/packages/raes_contracts/contracts/`.
- Schema generation: `tools/generate_contract_schemas.py`.
- Fixture corpus: `contracts/fixtures/experiment-core/`.

Published JSON Schemas are the portable structural contract. They declare draft
2020-12 schema identity explicitly. Semantic graph constraints that standard
JSON Schema cannot portably enforce are declared under the RAES semantic-
invariant profile through `x-raes-semantic-profile` and `x-raes-invariants`
metadata. Each invariant records a stable id, severity, validator, and input
contract/path set; the annotation shape is published as
`raes-semantic-invariants-v1` and is validated during schema generation.
Examples include metric key equality, task/run protocol binding, run time
ordering, result-evidence reference resolution, capture-requirement key
resolution, raw evidence content disclosure, derived-measure source evidence
requirements, run provenance traceability, realized-form disclosure, study
metric grounding, and manifest-selection and manifest-payload consistency.

## Definitions

### Scenario

An SDL scenario is the authored cyber range environment and behavior meaning.
It may include nodes, infrastructure, content, scoring, objectives, workflows,
participants, runtime declarations, and other scenario-local semantics.

A scenario is not an EXP task, run, apparatus context, or study.

### Task

An experiment task is the evaluation problem over a scenario or scenario
snapshot. It binds:

- a scenario reference;
- an evaluation protocol;
- task intent and intended use;
- metric definitions keyed by metric id, with the same metric id and a metric
  version embedded in each definition;
- population or construct;
- split/leakage controls or risk disclosures;
- apparatus constraints or explicit apparatus disclosure notes;
- at least one validity note and at least one supporting artifact reference.

One scenario may be used by many tasks. One task may be executed by many runs.

Tasks may carry `observation_demands` using the shared
`observation-demand-v1` contract. This is demand policy, not captured evidence
and not a realization constraint.

### Apparatus Context

Execution apparatus context is the instrument setup for a run. It captures or
references:

- a canonical `processor` component with processor identity and manifest;
- a canonical `backend` component with backend identity and manifest;
- participant implementation identity and manifest refs where relevant;
- compatibility declarations;
- selected manifests and profiles;
- configuration parameters;
- stochastic controls;
- clock context;
- measurement channels;
- observed setup evidence;
- known limitations.

Apparatus context belongs with run provenance. It is not authored scenario
meaning and is not a result value.

Apparatus components are keyed by component id so duplicate component keys
cannot be represented in conforming JSON records. Component identity remains an
explicit field. Claim-bearing apparatus records reserve the `processor` and
`backend` component keys for the primary processor and backend used to
interpret the run.

### Run

An experiment run is an archival record of a specific execution of a declared
task. It binds:

- task reference;
- scenario snapshot reference;
- apparatus context;
- participant implementation provenance when participant implementation
  apparatus is present;
- parameter set;
- stochastic controls;
- start/end and clock context;
- run status and outcome status;
- evidence artifacts;
- result summaries keyed by result id;
- deviations and invalidation details;
- lineage references.

A run may reference live observation artifacts captured at a seal point. It
must not be reconstructed from mutable live control-plane state.

The pre-run `run_plan.observation_demands` carrier refines requested
collection, retention, export, and reporting basis independently. It does not
turn operational control data into archival run evidence.
Task, run-plan, and capture-specification demand carriers remain declarative;
their presence is not a live capture/export executor. Those integrations are
owned by #1112/#1209. The current control plane rejects requested export and
mandatory observation combined with backend mutation without a compensating
owner. Nonretained backend-selected descriptions are immediate manager results,
not archival evidence or recoverable control-plane bodies.

For EXP-706, one trial is one archival run record. Repeated runs of the same
task are represented by multiple run records with distinct `run_id` values, a
shared `task_ref`, and a compatible `scenario_snapshot_ref`. A repeated run
MUST NOT be represented by mutating one run record, by a tag, or by a backend
operation/workflow/episode identifier.

Archival run records require a completed time interval, clock context, at least
one evidence artifact, and at least one result summary. Reported result
summaries must identify the metric, carry a value, and link to evidence. Every
result-summary evidence reference must resolve to an artifact id in the same
run's `evidence_artifacts` set. Cross-artifact task/run validation also checks
that run apparatus satisfies task apparatus constraints, that run result metric
ids are declared by the task evaluation protocol, and that concrete run
evidence artifacts satisfy the task and metric evidence requirements, either by
artifact id or by an artifact `satisfies_refs` entry. If a task or metric
evidence requirement carries digest or path metadata, the matching run artifact
MUST satisfy those fields with its concrete checksum and URI/path.

### Run Traceability

Run traceability is the EXP-710 path from the run to the evidence and claims
that interpret it. The `experiment-run-v1` `traceability` block binds:

- capture specification refs;
- raw evidence-record refs;
- derived-measure refs;
- claim, result, report, or analysis refs;
- optional notes for human review.

Traceability belongs in the run because the run is the record that knows the
task, scenario snapshot, apparatus, evidence, result summaries, and generated
artifacts together. It is not a separate graph service and not an alternative
run schema.

For EXP-712, run traceability is the support surface for reproducibility and
replay claims. It records what capture specifications, raw evidence records,
derived measures, claim/report artifacts, disclosures, and lineage refs are
available for review. It does not guarantee executable replay, artifact
dereference, hidden backend-state reconstruction, or derived-result
recomputation.

### Realized Form Disclosure

Realized-form disclosure is the EXP-722 record of concrete forms chosen for
concerns left open by the authored scenario, task, or apparatus declaration.
Each disclosure binds:

- a stable concern id and concern kind;
- the realization basis, such as processor-realized or backend-realized;
- the processor, backend, operator, or observation reference that made or
  recorded the realization;
- the authored reference when one exists;
- either a realized reference or a realized value summary;
- disclosure prose and optional evidence-record refs.

Realized-form disclosures are part of run provenance. They are not authored
scenario meaning, are not raw evidence records, and are not derived measures or
results.

Runtime realization-description observations project into this canonical
disclosure model. The projection preserves the concern, truthful achieved
basis, backend identity, bounded value summary, integrity statement, and
evidence-record references. It does not expose an internal protected-value
carrier as a second public disclosure contract.

### Capture Specification

Each capture requirement may carry the same scoped `observation_demand` rule.
The capture requirement still owns its source, window, channel, sensitivity,
redaction, integrity, retention, and loss disclosure; the demand rule controls
whether and where that work is selected. A demand is never proof of capture.

An experiment capture specification is the declarative EXP-707 statement of
what evidence should be captured for an experiment scope. It binds:

- task, run, apparatus, or adjacent scope references;
- capture windows;
- capture requirements keyed by requirement id;
- measurement channel references;
- expected media types and artifact roles;
- sensitivity, redaction, integrity, retention, and loss-disclosure
  expectations;
- validity notes and supporting artifacts.

A capture specification is not proof that capture occurred. It is an intent and
review surface that raw evidence records can cite.

### Evidence Record

An experiment evidence record is the raw EXP-708 evidence surface. It binds:

- a capture specification reference;
- a capture requirement reference;
- a run reference, plus optional task and apparatus context references;
- source references and evidence kind;
- capture timestamp and capture window reference;
- raw content as an artifact reference, content URI with checksum, or bounded
  payload summary;
- sensitivity, redaction state, loss disclosure when needed, and provenance.

Evidence records MUST NOT carry metric ids, computed values, scores, or
evaluation decisions. Those belong in derived measures or run summaries.

### Derived Measure

An experiment derived measure is the EXP-709 interpreted output surface. It
binds:

- a metric or evaluation reference;
- derivation method id, version, parameters, and description;
- one or more source evidence-record references;
- generation timestamp;
- value status and value when reported;
- uncertainty, limitations, and provenance.

Derived measures MUST NOT stand in for raw observations. Their reviewability
depends on following `source_evidence_refs` back to evidence records.

### Backend Observation Capability

The optional EXP-715 `backend-manifest-v2` `capabilities.observation` block
declares whether a backend can support observation/evidence collection
surfaces. It binds supported capture kinds, source channel kinds, evidence
contracts, media types, sealing modes, redaction support, loss-disclosure
support, chain-of-custody support, and constraints.

Observation capability is not orchestrator, evaluator, or participant-runtime
capability. It is a backend apparatus claim that must be backed by published
experiment evidence contracts and governed concept bindings.
Runtime implementations refine that portable claim into stable selector-family
patterns (data kind, supported names, scope/component family, window, and
bounded coverage). Admission binds a compiled scenario selector to one
unambiguous most-specific pattern; adapter registration does not depend on a
scenario-specific serialized selector key.

### Study Or Collection

A study groups tasks, runs, results, evidence, reports, and analysis artifacts
for comparison, benchmarking, replication, or collection management. A
collection is represented by `study_kind: collection` in the same contract.

Studies carry accountable analysis context:

- owner;
- purpose and research questions;
- inclusion criteria;
- membership roles keyed by member id;
- factors and treatments keyed by factor id;
- structured run allocation plan;
- analysis plan with metric, primary metric, statistical-method,
  uncertainty-method, multiple-comparison, and missing-data policy records;
- validity notes;
- report and export artifact refs.

For EXP-706, replications, cohorts, benchmarks, comparisons, and controlled
variation are study allocation semantics. They are expressed through
evaluation-run membership groupings, declared factors and factor levels,
blocking factors, condition assignments, `target_runs_per_condition`,
`replication_policy`, `stopping_rule`, and the analysis plan. Condition
assignment evidence must be grounded in auditable run-level facts such as
participant implementation provenance, processor/backend identity, apparatus
context, selected manifests, capability declarations, measurement channels,
task/scenario snapshot identity, non-opaque parameters, and stochastic
controls.

### Experiment Authoring Input

An experiment authoring input is the pre-run *specification* of an experiment,
distinct from the archival run/study/apparatus-context records it will later
produce. It binds:

- a `task_ref` to a separately authored `experiment-task-v1`, and optionally an
  `intended_scenario_ref` to a scenario snapshot;
- declared apparatus intent (the input-shaped apparatus constraints), distinct
  from the run-scoped observed apparatus context;
- a run plan: optional stochastic controls, an episode control (turn order,
  logical step count, termination), either a condition `allocation` plan or a
  scalar `target_run_count`, a closed keyed selection-policy registry,
  red-variant selections keyed by variant id, and an optional clock intent;
- study factors keyed by factor id;
- capture-specification references, validity notes, and supporting artifacts.

An authoring input is not a run, study, or apparatus-context record. It carries
no execution provenance, results, or observed evidence. It reuses the archival
family's input-shaped value models (apparatus constraints, run allocation,
stochastic controls, factors, clock context) by reference or embedding and does
not re-declare task, scenario, or capture-specification meaning. The reused run-
allocation model annotates its semantic invariant against `experiment-study-v1`
even when embedded here; that annotation is descriptive only — the RAES model
validator runs regardless of the embedding contract.

## Invariants

### Separation

1. A task reference to scenario material MUST use `scenario` or
   `scenario-snapshot` as the reference kind.
2. A run MUST reference exactly one task and one scenario snapshot. If the task
   references a generic scenario rather than a snapshot, the run snapshot MUST
   still use the same scenario identity. Generic scenario references are id-only;
   version, digest, or path binding requires `scenario-snapshot`.
   For composed SDL scenarios, the `scenario-snapshot` digest identifies the
   expanded canonical scenario after import resolution, namespace rewriting, and
   full-scenario semantic validation. Module source paths, module ids/namespaces,
   lock records, and fragment digests are preserved as evidence/audit metadata,
   not as alternate runtime identities.
3. A run MUST carry apparatus context; apparatus context MUST NOT be represented
   only by free-form metadata or backend-private logs.
4. A study MUST group typed artifact references; it MUST NOT redefine the task,
   run, apparatus, result, or evidence payloads it references.
5. SDL objectives MUST remain scenario-local objectives and MUST NOT be treated
   as EXP task records.
6. Metric definitions, apparatus components, run result summaries, study
   memberships, and study factors MUST use object keys as their stable local
   identifiers when uniqueness is a contract invariant. Metric definition keys
   MUST match their embedded `metric_id` values.
7. Manifest-specific fields, including required task manifests, component
   manifests, and selected apparatus manifests, MUST use `manifest` as their
   reference kind.
8. Processor and backend constraint fields MUST use processor- and
   backend-constrained references rather than generic artifact references.
   Processor/backend identity references MUST NOT carry digest or path
   qualifiers; digest-bound apparatus evidence MUST be expressed through
   canonical processor/backend manifest references or evidence requirements
   that can be validated against concrete payloads.
9. Run task references and study task/run membership references MUST NOT carry
   digest or path qualifiers unless a future validator binds those fields to
   concrete task/run payload artifacts.
10. Study membership roles MUST constrain the referenced artifact kind: task
   roles reference tasks, run roles reference runs, result roles reference
   results, evidence roles reference evidence, and analysis roles reference
   analysis artifacts.
11. Processor and backend identity constraints MUST resolve to required
    manifest references with matching identity ids and manifest schema
    versions. For processor/backend manifests, the manifest `ref_id` MUST match
    the `subject_ref.ref_id`. Manifest references for apparatus identity MUST carry a
    `subject_ref` that identifies the processor or backend identity and version
    described by the manifest. Manifest references MUST NOT carry path
    qualifiers; digest-qualified manifest references MUST identify a processor
    or backend subject and the supported processor/backend manifest schema
    version.
12. Required task apparatus capabilities MUST resolve to capability references
    in the run apparatus compatibility declarations or component compatibility
    references.
13. Capture specifications, evidence records, and derived measures MUST use
    distinct reference kinds: `capture-spec`, `evidence-record`, and
    `derived-measure`.
14. Capture specification `capture_requirements` keys MUST match embedded
    `requirement_id` values, and requirement `window_refs` MUST resolve to
    declared capture windows.
15. Evidence records MUST cite a capture specification and requirement, carry
    raw content, and MUST NOT include metric ids or derived values.
16. Derived measures MUST cite at least one evidence record and MUST NOT be
    treated as raw evidence.
17. Backends that declare `capabilities.observation` MUST declare the published
    experiment evidence contracts that make the observation claim inspectable.
18. `experiment-run-v1` is the canonical run provenance record. RAES MUST NOT
    publish a parallel run-provenance root schema for the same archival run
    facts unless a later ADR supersedes this boundary.
19. Run traceability MUST link at least one capture specification and at least
    one evidence record. Claim refs MUST be grounded by derived-measure refs.
20. Realized-form disclosures MUST carry a realized reference or a realized
    value summary. Processor-realized disclosures MUST be attributed to a
    processor reference, and backend-realized disclosures MUST be attributed to
    a backend reference.
21. `experiment-run-v1` is the trial record for the current model. RAES MUST
    NOT publish a parallel trial root schema for the same task execution facts
    unless a later ADR supersedes this boundary.
22. Repeated executions of the same task MUST be represented by distinct run
    records with distinct `run_id` values, a shared `task_ref`, and compatible
    scenario snapshot identity. Operation ids, workflow ids, runtime snapshot
    ids, participant episode ids, backend-native execution ids, tags, and
    mutable run statuses MUST NOT stand in for repeated-run identity.
23. Reproducibility and replay claims MUST use the run traceability chain from
    run context to capture specs, evidence records, derived measures, and
    claim/report refs. RAES MUST NOT publish parallel replay-run,
    reproducibility-claim, replay-claim, or provenance-graph root schemas for
    the same facts unless a later ADR supersedes this boundary.
24. An experiment authoring input MUST reference its task with a `task`
    reference and MUST NOT embed or re-declare task, scenario, or
    capture-specification meaning; scenario intent uses `scenario` or
    `scenario-snapshot` references and capture intent uses `capture-spec`
    references.
25. An experiment authoring input run plan MUST declare exactly one run-count
    source: either a condition `allocation` plan or a scalar `target_run_count`.
    Red-variant selection map keys MUST match their embedded `variant_id`, and
    declared allocation blocking factors MUST resolve to declared spec factors.
26. An experiment authoring input is an input artifact. It MUST NOT be treated
    as, or substituted for, an `experiment-run-v1`, `experiment-study-v1`, or
    `experiment-apparatus-context-v1` record. Its declared apparatus intent uses
    the input-shaped apparatus constraints, not the run-scoped observed
    apparatus context.
27. Selection-policy map keys MUST match their embedded `policy_id`. Every
    policy MUST declare one of the closed purposes `controlled-factor`,
    `nuisance-variation`, or `fixed-configuration` as admitted by its policy
    kind, and its `output_bound` MUST be positive, finite, and no greater than
    the declared run count.
28. Version 1 selection policy kinds are `fixed`, `enumerate`, `product`,
    `stratified`, and `sample`. Products MUST reference at least two declared
    policies, form an acyclic graph, and declare the exact checked product
    bound. Equal stratification MUST join every compared allocation condition
    to one declared factor level with the allocation's exact per-condition run
    count.
29. Deterministic selection policies MUST NOT require a synthetic seed.
    `sample` MUST use uniform sampling with replacement, declare a sample count
    equal to the run allocation, and resolve exactly one executable sampling or
    randomization control whose accepted profile supplies bounded-integer
    transform version 1. Weighted, without-replacement, permutation, and t-way
    policies fail closed until their exact accepted transform semantics exist.
30. Policy point references and outcomes MUST be admitted against a trusted,
    semantically validated expanded scenario family. Fixed outcomes MUST be
    members of their declared scalar, governed-reference, alternative, subset,
    order, or logical-timing domain. Exhaustive and sampled populations MUST be
    finite and exactly bounded.

### Provenance

1. Experiment artifacts MUST have stable identifiers and schema versions.
2. Evidence-bearing artifact references MUST include media type, URI, checksum,
   byte size, creation time, source, and sensitivity metadata.
3. RFC 3339 date-times, including the standard's lower-case `t`/`z`
   allowance and only known valid UTC leap-second instants, MUST be used for
   experiment-core archival times.
4. Checksums and reference digests MUST identify their digest algorithm and use
   algorithm-appropriate hex digest lengths.
5. Run evidence and result summaries MUST be linkable back to the run that
   generated or recorded them. Run result `evidence_refs` are artifact-id links
   within the same run and MUST NOT carry version, digest, or path qualifiers;
   artifact `satisfies_refs` MAY carry evidence concept versions but MUST NOT
   carry digest or path qualifiers because concrete checksum/URI metadata belongs
   on the artifact record.
6. Invalidation MUST be explicit when a run is marked `invalidated`.
7. Apparatus context MUST identify selected manifests, compatibility
   declarations, configuration parameters, stochastic controls, clocks,
   measurement channels, observed setup evidence, and known limitations.
8. Completed run intervals MUST not end before they start.
9. Canonical apparatus processor and backend component manifests MUST appear in
   the same record's selected manifests with matching reference identity,
   digest metadata, and `subject_ref` values that match the component
   identities. Manifest path qualifiers are not part of the v1 apparatus
   contract. Selected manifests MUST NOT contain multiple refs for the same
   subject identity and manifest schema version. Digest-qualified selected
   manifests MUST be the canonical processor/backend component manifests.
   Compatibility declarations, component compatibility refs, and measurement
   channel refs MUST NOT carry digest or path qualifiers unless a future
   validator binds those fields to concrete profile, capability, or measurement
   payload artifacts.
10. Study and benchmark records MUST carry research questions, run allocation,
    validity notes, and an analysis plan with at least one metric, a primary
    metric, and structured statistical, uncertainty, multiple-comparison, and
    missing-data policies.
11. RAES semantic validation MUST be able to resolve canonical processor and
    backend manifest references to concrete manifest payloads with matching
    identities, schema versions, optional digest evidence, and mutual
    processor/backend compatibility declarations.
12. Study analysis metrics MUST be grounded in the metric definitions of the
    included task protocols and represented by result summaries, including
    explicit missing/withheld statuses, in included evaluation runs before the
    study can support comparison claims.
13. Study run-allocation `compared_conditions` MUST have matching
    `condition_assignments` that reference declared study factor levels and
    auditable run-level criteria such as participant implementation,
    processor, backend, apparatus context, manifest, capability, measurement
    channel, task/scenario snapshot identity, or non-opaque parameter values.
    Opaque catch-all references and `other` parameter kinds MUST NOT be used as
    condition-assignment evidence. Participant implementation condition
    references MUST resolve through run-level participant implementation
    provenance, not only through an apparatus component identity. Condition-assignment
    references MUST NOT carry digest or path qualifiers; digest/path evidence
    binding belongs to task evidence requirements and canonical processor/backend
    manifest payload validation. Compared conditions MUST NOT share identical factor-level
    combinations or identical run-level criteria.
14. Included evaluation-run membership groupings MUST reference declared
    `compared_conditions`, a single run MUST NOT be counted in multiple
    conditions, each included run MUST satisfy exactly one condition
    assignment, invalidated/superseded/not-evaluated runs MUST NOT satisfy a
    declared run allocation, and every condition MUST meet the predeclared
    `target_runs_per_condition` when run allocation is declared and before the
    study can support analysis or comparison claims. Analysis-bearing
    collection/cohort records without
    `run_allocation` MUST still exclude invalidated, superseded, and
    not-evaluated evaluation runs.
15. Run-allocation `blocking_factors` MUST reference declared blocking,
    stratification, apparatus, or control study factors with declared levels.
16. Capture windows MUST declare a start, end, or trigger, and an interval with
    both start and end MUST NOT end before it starts.
17. Evidence records MUST use valid RFC 3339 `captured_at` timestamps.
    Redacted or withheld evidence records MUST disclose the loss in
    `raw_content.loss_disclosure`.
18. Derived measures MUST use valid RFC 3339 `generated_at` timestamps.
    Reported measures MUST include a value; missing, withheld, and
    not-applicable measures MUST NOT include a value.
19. Observation capability terms MUST be validated through the governed
    concept-authority scopes for capture kinds, channel kinds, and sealing
    modes.
20. Realized-form disclosure evidence refs MUST be present in the containing
    run's traceability evidence-record refs.
21. Replication, cohort, benchmark, comparison, and controlled-variation claims
    MUST be grounded in study membership and run allocation. Study membership
    and allocation MUST NOT be replaced by tags, folders, evaluator detail,
    runtime metadata, audit details, diagnostics, backend-private logs, or
    free-form notes.
22. Replay and reproducibility claim strength MUST be limited by the preserved
    run context, evidence availability, redaction, loss disclosure, observer
    effects, unsupported runtime surfaces, external artifact availability, and
    apparatus limitations recorded in the relevant run, evidence, derived
    measure, disclosure, and study artifacts.

### Closed-World Contracts

1. Published contracts MUST be closed-world Pydantic `ContractModel` shapes.
2. JSON Schemas MUST be generated through `schema_bundle()` and
   `tools/generate_contract_schemas.py`.
3. `contracts/schemas/` MUST NOT be edited by hand.
4. Valid fixtures MUST validate against their published schemas. Invalid
   fixtures for schema-expressible invariants MUST fail both the published JSON
   Schema and the Python contract model.
5. Consumers that use only generic JSON Schema can validate portable structure
   but MUST NOT claim full RAES experiment-core conformance until the RAES
   semantic validators named by `x-raes-invariants` have been applied.

### Security And Redaction

1. Experiment-core records are not a credential, traceback, process-argument, or
   raw backend-inspect transport. v1 automated enforcement covers the
   closed-world field set, checked-in artifact secret scanning, artifact
   sensitivity metadata, and redaction-aware parameter validators; it does not
   claim complete semantic detection of every sensitive string a producer could
   place in free-text fields.
2. Artifact references that point at restricted or redacted evidence MUST carry
   sensitivity metadata.
3. Structured experiment parameters marked `redacted` or `withheld` MUST NOT
   include concrete values.
4. Later API exposure MUST reuse existing control-plane identity, role,
   request-size, audit, idempotency, response-model, and redacted-error
   patterns.

## Literature-Based Criteria

The research notes in `docs/research/experiment-core/` provide the evidence
base. The most load-bearing criteria are:

- ML reproducibility: task protocols, metric definitions, data/split/leakage
  controls, repeated runs, stochastic controls, and uncertainty/analysis plans.
- Experiment databases: separable task, run, evaluation, and collection
  records.
- Provenance and FAIR packaging: stable identifiers, artifact roles, lineage,
  and exportable evidence bundles.
- Cyber range/testbed research: apparatus configuration, fidelity, host/VM
  context, and cross-testbed reproduction are part of result validity.
- Empirical software engineering and simulation V&V: validity threats,
  treatments, controls, replication, calibration, and uncertainty context.

## Non-Goals

- Runtime execution.
- Run persistence.
- Study management services.
- Statistical analysis engines.
- HTTP APIs.
- New SDL authoring syntax.
- PROV, RO-Crate, OpenML, or MLflow as the internal RAES schema.
- Runtime evidence capture, artifact storage, retention jobs, or capture
  schedulers.
- Backend-native packet/log/trace parsers.
- Processor logic that computes derived measures from evidence records.
- New trial, replay-run, reproducibility-claim, replay-claim, or provenance
  graph root schemas for facts already carried by experiment-core contracts.
- Runtime replay execution, replay scheduling, artifact dereference APIs,
  retention storage, or query services.
- Orchestration or execution of authored experiment specifications, or
  producing archival run/study records from an `experiment-authoring-input-v1`.
