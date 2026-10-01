# ADR-066: Observability and Evidence Plane Separation

## Status

accepted

## Date

2026-06-23

## Classification

Classification: FM2
Required artifacts: ADR, formal spec, SDL authoring catalog, clause matrix
Waivers: Executable contracts, fixtures, and tests are owned by the spawned
implementation issues #334, #335, #336, and #337.

## Context

Issue #127 is the joint design surface for:

- SEM-224, observability plane separation semantics;
- SEM-225, processor/backend realization augmentation semantics;
- DSL-123, scenario-native observability and telemetry systems; and
- DSL-124, authored data and evidence requirements.

Existing ACES artifacts already define adjacent boundaries:

- ADR-022 and ADR-054 separate participant-visible observations from hidden
  truth, scoring state, centralized-training state, archival evidence, and
  participant action-observation history.
- ADR-055, ADR-064, and ADR-065 separate experiment tasks, apparatus contexts,
  capture specifications, raw evidence records, derived measures, run
  traceability, and realized-form disclosures.
- `specs/sdl/runtime-inventory.md` defines node-scoped runtime-family
  inventory as the SDL pattern for in-world logical services.
- ADR-056 and ADR-057 define redaction and observed-value boundaries for
  runtime facts that can carry secrets.

The missing design is the cross-plane rule set. Authors need in-world
observability systems to be scenario elements. Experiment designers need
capture requirements that say what data must be collected. Processors and
backends need operational telemetry and may add instrumentation. Runs need raw
evidence records and derived analysis outputs. Those are related but not
interchangeable.

Without an explicit split, implementers can accidentally treat backend logs as
participant observations, treat the presence of raw capture as satisfaction of
an authored evidence requirement, leak hidden adjudication assets through
analysis outputs, or make an environment-visible augmentation without
disclosing its effect on comparability.

## Decision

Define five named planes and one cross-cutting augmentation classification.

### 1. Scenario-native observability plane

Scenario-native observability systems are in-world systems that the authored
scenario makes part of the environment: telemetry systems, logs, tracing
backends, monitoring dashboards, sensors, detection engines, SIEM-like managers,
or comparable resources that participants or scenario relationships may depend
on, interact with, or target.

They belong in SDL authoring space. Implementations must prefer the existing
runtime-family model under `nodes.<node>.runtime.*`. A new runtime family is
appropriate only when the system has a distinct, product-neutral logical
service identity that cannot fit existing families without distorting their
meaning. This decision does not add a universal top-level `observability`
section.

### 2. Authored evidence-requirement plane

An authored evidence requirement records what data, evidence, output, or
capture product must exist from a declared source, scope, window, channel, or
boundary. It is independent of participant objectives and distinct from
scenario-native observability systems.

Evidence requirements are authoring obligations. They are not proof that
capture occurred and they are not raw captured payloads. When an executable
artifact is needed, the requirement maps to experiment-core capture
specification concepts such as source refs, capture windows, capture
requirements, sensitivity, integrity, retention, and loss disclosure.

### 3. Processor/backend operational observability plane

Processor and backend operational observability covers apparatus logs,
diagnostics, traces, audit records, setup attestations, health checks,
measurement-channel facts, and capability disclosures used to operate or verify
the apparatus.

These facts are not participant-visible observations and are not authored
scenario meaning unless an explicit SDL or runtime contract projects them into
that plane. They must use existing diagnostics, manifests, control-plane
security, audit, idempotency, request-size, and redacted-error patterns.

### 4. Captured evidence plane

Captured evidence is a concrete raw evidence artifact or record produced for a
run. It must carry provenance, source refs, capture time or window, raw-content
reference or bounded summary, sensitivity, redaction state, checksum or
integrity metadata where applicable, and the authored requirement or capture
specification it claims to satisfy.

Captured evidence does not carry metric values, scores, or evaluation
decisions. Those belong to derived analysis.

### 5. Derived analysis plane

Derived analysis outputs are interpreted outputs over evidence: derived
measures, result summaries, outcome interpretations, studies, reports, exports,
analysis artifacts, and claims.

Derived analysis must cite its source evidence. It must not stand in for raw
evidence, and it must not reveal hidden state, hidden answer keys, private
traces, or adjudication assets unless an explicit marking, redaction, and
authorization boundary permits that disclosure.

### 6. Realization augmentation classification

Processor/backend augmentation is apparatus-added behavior or instrumentation
used to satisfy evidence, evaluation, operational, or comparability needs. An
augmentation may carry one or more of these classifications:

- `apparatus_only`: visible only to the processor, backend, operator, or
  control apparatus;
- `environment_visible`: changes or adds behavior inside the realized
  environment;
- `participant_visible`: can affect what a participant sees, receives, or can
  infer through a visibility projection; and
- `comparability_relevant`: can affect whether runs, participants, backends, or
  conditions can be compared.

Participant-visible augmentation must pass the participant visibility,
marking, and redaction gates from ADR-022 and ADR-054. Environment-visible or
comparability-relevant augmentation must be represented through first-class
runtime, evidence, or provenance carriers. It must not hide in
`RuntimeSnapshot.metadata`, evaluator details, diagnostics, audit blobs,
backend DTOs, or raw logs.

Issue #1242 adds an independent author-permission boundary in
[`augmentation_scope`](../../../specs/sdl/augmentation-scope.md). Omission means
open. A closed default would require authors to anticipate and authorize every
backend addition, imposing a large, unexpected burden; restrictions are therefore
explicit opt-ins, also preserving compatibility. Node/concern closures may not
be widened by realization delegation, observation demand, import composition,
or a later attestation. A producer that needs a forbidden in-world effect to
satisfy a requirement must refuse before materialization, identifying the
requirement and effect. Permission does not replace any visibility,
comparability, or evidence obligation above.

### 7. Forwarding-agent ownership does not collapse the planes

A forwarding agent marked `system_under_test` remains scenario-native
observability. A forwarding agent marked `measurement_apparatus` remains an
authored inventory declaration for experiment apparatus; it does not become
captured evidence merely by existing. The ownership role is not an execution
or visibility claim.

The authored evidence-requirement plane owns the binding direction. An
apparatus-class `EvidenceRequirement` names the measurement forwarding agent
in `source_refs`; the agent does not name evidence records, capture locations,
or storage credentials. Environment-visible or comparability-relevant
apparatus still requires the existing run-level augmentation disclosure.
Operational delivery or failure claims remain proposition/probe/truth/evidence
claims rather than fields on the inventory or realization observation.

## Required Boundaries

- A backend log is not a participant observation unless a participant
  observation envelope or SDL visibility rule projects it.
- A capture specification or authored evidence requirement is not proof that
  evidence was captured.
- A raw evidence record is not a metric, score, result summary, or derived
  analysis output.
- A scenario-native observability system may be a source for evidence capture,
  but its existence does not satisfy the capture requirement by itself.
- Processor/backend operational telemetry may support apparatus audit or
  setup evidence, but it is not authored scenario meaning.
- Hidden adjudication assets, evaluator state, answer keys, private traces,
  prompts, and secrets remain outside portable public surfaces unless a
  governed disclosure rule, marking, redaction policy, and authorization scope
  apply.
- Loss, redaction, latency, observer effects, and weaker capability guarantees
  must be explicit when a claim depends on them.

## Implementation Mapping

This ADR is design coverage for issue #127. The spawned implementation issues
own executable work:

- #334 / SEM-224: plane classifier, validation, and traceability over the five
  named planes.
- #335 / SEM-225: augmentation disclosure carriers and validators.
- #336 / DSL-123: scenario-native observability authoring surfaces, using the
  runtime-family extension model.
- #337 / DSL-124: authored evidence-requirement authoring surfaces and their
  mapping to experiment-core capture concepts.

The formal criteria and source-to-contract-to-test matrix live in
`specs/formal/observability-evidence-plane.md`. The SDL authoring rules live in
`specs/sdl/observability-and-evidence.md`.

## Alternatives Considered

### Add one generic observability model

Rejected. A single catch-all model would collapse in-world observability
systems, backend diagnostics, evidence requirements, raw evidence, and analysis
outputs. It would also bypass the existing runtime-family, experiment-core,
participant-runtime, and control-plane seams.

### Put authored evidence requirements only in experiment-core contracts

Rejected. Experiment-core capture specifications are the portable capture
contract boundary, but DSL-124 asks for an authored language surface. The SDL
surface can map to capture specifications, but the authored obligation must not
be replaced by archival run artifacts.

### Treat backend operational telemetry as the canonical evidence surface

Rejected. Backend telemetry is apparatus operational data. It can support
audit, setup, or capture claims when projected through the right contracts, but
it cannot become participant-visible state or requirement satisfaction by
existence.

### Model all augmentation through SEM-218 explicitness

Rejected. SEM-218 distinguishes authored binding from processor/backend
realization. SEM-225 needs a more specific disclosure classification for
instrumentation and apparatus behavior that can be environment-visible,
participant-visible, or comparability-relevant.

## Consequences

### Positive

- The four requirements have one shared vocabulary for plane separation.
- Future SDL and contract work can add executable surfaces without inventing
  parallel schema, validation, persistence, diagnostic, or audit stacks.
- Reviewers can reject cross-plane mistakes with concrete criteria instead of
  relying on prose intuition.
- Augmentation effects that can change participant visibility or comparability
  become explicit review objects.

### Negative / costs

- Implementers must classify plane ownership and augmentation visibility before
  adding executable surfaces.
- Some follow-on issues must touch multiple roots together: SDL specs,
  contracts, schema manifests, fixtures, validation helpers, and tests.

### Risks

- If future implementation skips the classifier and matrix, the same words
  (`logs`, `telemetry`, `evidence`, `observation`) can drift across planes.
- If augmentation is treated as apparatus-only by default, environment-visible
  or comparability-relevant changes can become invisible to reviewers.
- If captured evidence and derived analysis are not linked by explicit source
  refs, result claims can float free of the raw evidence they interpret.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-06-23 | #335 | Implemented SEM-225 run-level augmentation disclosures in `experiment-run-v1`, including separate environment-visible, participant-visible, and comparability-relevant validation. |
| 2026-08-01 | #1043 | Separated forwarding-agent ownership, realization corroboration, evidence binding, and operational behavior claims. |
| 2026-09-16 | #1242 | Added binding open-by-default augmentation scope, explicit author restrictions, pre-materialization refusal, and the author-burden rationale. |
