# Issue #2010 trace satisfaction preflight

Issue #2010 is the contract for this requirement-free work. No requirement UID applies.
This note sets design guardrails. It leaves the definitions and implementation plan to later work.
Inspection baseline: `1cb8f78946214fa20da0d185335bffed256debdf`.

## Authority and scope

The change belongs in the existing [shared time specification](../../specs/formal/time-model/README.md)
and [assertion specification](../../specs/formal/objectives/proposition-and-assertion-semantics.md).
ADR-090 and ADR-091 already own time, capability, readback, and provenance boundaries.
[ADR-079](adrs/adr-079-backend-neutral-proposition-and-truth-semantics.md) already owns assertion roles, polarity, truth, and evidence admission.
No new ADR or parallel semantics authority is needed.

Separate trace satisfaction from proof through captured evidence.
A valid trace can violate a constraint.
Assertion truth, scope applicability, and evaluator status also differ.
The finite-domain [scenario satisfiability profile](../../specs/formal/scenario-satisfiability/README.md) analyzes authoring choices; it does not decide temporal trace satisfaction.
One trace cannot prove a claim about all traces.
It cannot prove backend equivalence or native support.

## Existing boundaries to preserve

| Concern | Canonical incumbent and required reuse |
| --- | --- |
| Trace validity and state | `specs/formal/participant-runtime/README.md`: `ValidTrace`, `prefix`, `prefix_state`, order, capability and marking rules. Reuse these within participant scope. State the projection for other ordinary SDL subjects. |
| World and observation | `specs/formal/participant-semantics/README.md`: `W_t`, `V_p,t`, `H_p,t`, `R_t`, and `X_t`. World state, visible history, realized order, and evidence remain distinct. |
| Authored time | `raes.time_model.TemporalConstraint`, `TimeCoordinate`, and `raes.validator._time_model`. Keep the five kinds and existing fields. Reuse subject lookup and declared clock ownership. |
| Compiled and portable identity | `raes_processor.compiler.time_model`, `raes_processor.models.time_model`, and `raes_contracts.contracts.time_model`. Keep subject order for precedence. Preserve canonical addresses, exact units, and declaration identity. |
| Clock lifecycle and readback | `raes_runtime.time_coordinator`, `time_control`, and `validate_time_runtime_state` / `validate_time_runtime_transition`. Clock transitions are apparatus records, not subject occurrences or proposition observations. |
| Assertion algebra | `raes.propositions`, `raes.semantics.propositions`, and `raes.validator._propositions`. Reuse polarity and finite subject quantification. Keep role admission and existing composition tables. |
| Owner scope | `raes.semantics.objectives.analyze_objective_window`, `objective_semantics`, and `specs/formal/workflows/state-machine.md`. Reuse owner boundary rules. Objective membership windows alone do not supply clock intervals. |
| Truth-result admission | `PropositionTruthResultModel` in `raes_contracts/contracts/execution_state.py` and `raes_runtime.proposition_truth_contracts`. Preserve evidence, basis, assertion identity, and polarity. Keep loss bounds and snapshot joins. |
| Realization and storage | `time_model_capability_gaps`, planner `manifest_validation`, `raes_conformance.time_semantics`, and run-scoped realized-time provenance. Reuse snapshots, append-only histories, and experiment evidence refs. No new store or service is needed. |

Python module names above refer to `implementations/python/packages/`.
The [evidence-plane specification](../../specs/formal/observability-evidence-plane.md) governs capture intent, captured evidence, apparatus telemetry, and derived judgments.
Operational logs and backend scheduler order cannot substitute for semantic observations.

## Definition obligations and gotchas

State which context gives a trace its meaning.
Name its run, subject occurrences, owner scope, and clock/domain/segment.
Name its admitted order, boundary selection, and coverage assumptions.
Reuse existing occurrence and event-point identities where available.
An SDL resource address alone is not an occurrence.

Ordinary SDL subjects need not become participants or expose private state.
The participant-runtime empty prefix helps reconstruct state.
It cannot support a published runtime claim.

| Kind or role | Questions the definitions must settle explicitly |
| --- | --- |
| Precedence | Which occurrence of the first subject precedes which occurrence of the second? Is order strict? How are ties, concurrency, repetitions, and absent occurrences treated? |
| Duration | Which start/end events pair for each occurrence? Does the bound mean exact, minimum, or maximum duration? What happens to unfinished occurrences? |
| Window | Which occurrence points or activity intervals must be inside it? Which endpoints are included? Is mere overlap sufficient? |
| Deadline | Which event must occur by `end`? Is equality allowed? How do a pending prefix, closed scope, and late observation differ? |
| Cadence | Which repeated occurrences count, over what horizon and anchor? Is `cadence_ticks` exact spacing or a bound? How do zero/one occurrences and terminal gaps behave? |
| Precondition | Which owner entry cut supplies the state, before which effects? Keep applicability distinct when the outcome is false, unknown, or unsupported. |
| Invariant | Which owner interval and state points are covered? What does a counterexample or a coverage gap establish? Isolated samples cannot prove an interval. |
| Postcondition | Which owner exit cut supplies the state? Address incomplete, cancelled, or failed scopes without treating command completion as proof. |

The later specification change must answer these questions.
Cover every admitted shape or state a clear limit.
Current kind validators require some fields.
They do not forbid every unused optional field.
Do not infer meaning from such extra fields.
Do not silently tighten their admission during a prose change.

Do not invent missing occurrence selectors, tolerances, scope fields, or wire encodings in examples.

Keep comparisons within an admitted clock context and segment.
Only an explicit governed relation can permit more.
Segment order records discontinuity.
It does not define elapsed time across resets.

Authored `TimeCoordinate` has tick/microstep only.
Portable `TimeCoordinateModel` also carries a segment, defaulting to zero.
The compiler retains authored tick/microstep bounds without a segment field.
Do not claim authors select arbitrary segments.
Do not assume segment zero applies forever after replay.

Microsteps order points within a tick.
They have no declared SI duration.
Use exact integers and rational mappings.
Conversion may produce fractional ticks.
Mappings connect domains.
They do not imply links between arbitrary clock authorities, epochs, or reset segments.

Pacing, pause, drift disclosures, jumps, and replay must preserve the declared bound.
They must not silently merge separate occurrences.
Temporal precedence establishes no causal attribution.

Keep ideal satisfaction separate from portable outcomes: `true`, `false`, `unknown`, and `unsupported`.
An incomplete trace can contain a decisive witness or leave a claim unresolved.
State vacuity and completion assumptions.
Missing observations do not prove absence.
Negation preserves unknown and unsupported.
State how polarity applies when aggregating results over time.

Preserve ADR-079's evidence admission and algebra.
Do not create another temporal truth table.

`PropositionTemporalContextModel` carries boundary, domain, and authority strings only.
It has no coordinates, segment, or interval-coverage proof.
The v1 `scenario_time` projection states an evaluator capability requirement.
It does not resolve a shared clock or imply a mapping.
A string or valid truth envelope cannot prove trace completeness or coverage.
State unsupported serialization or realization explicitly.

A richer authored time binding needs a governed language/profile change.

## Cross-cutting security and workflow gates

| Layer | How this specification change respects the existing gate |
| --- | --- |
| Authority and schemas | Retain `specs/authority/authority-boundary.yaml` and ADR-009 ownership. Published schemas under `contracts/schemas/` govern shapes. `schema_bundle()` preserves generator parity. No duplicate trace DTO or schema. |
| Parser and validation | Keep `load_sdl_yaml`, `SDLModel(extra="forbid")`, instantiation/revalidation, named-reference lookup, and portable `ContractModel` validators. Math notation is inert. It creates no alternate parser or execution path. |
| Config and environment | No config, environment binding, or CLI fields are needed. Examples must use admitted fields. Existing variable and runtime-environment shapes still apply. Keep clock and coverage policy out of free-form metadata. |
| Authentication and visibility | No endpoint or authorization change. Runtime access uses `control_plane_security.py` and `control_plane_api/_auth.py`. Keep marking, redaction, and observation-boundary checks on participant projections. Evaluator access does not authorize participant disclosure. |
| Secrets and host exposure | No credentials, probe execution, provisioning, or data transfer is needed. Use synthetic examples and secret refs. Keep existing environment redaction. Never put tokens in process arguments or raw evidence in logs. |
| Errors and observability | Reuse SDL errors, `Diagnostic`, `portable_diagnostic_payload`, `raes_contracts.errors`, `operational_logging`, and API `_responses.py`. Malformed input remains a validation error. Keep insufficient evidence distinct from missing capability. No exception hierarchy or logger is needed. |
| Evidence and storage | Preserve basis/provenance joins, evidence refs, integrity, loss bounds, and append-only segment history. No raw hidden evidence in snapshots, diagnostic details, or a new satisfaction database. |
| Documentation and delivery | Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, the documentation style guide, locked doc-tools, `.vale.ini`, and explicit-path policy/prose checks. Keep pre-commit secret checks and full CI gates. No hosting or publication is part of this work. |

The existing conformance checker joins capabilities, clock readback, and run provenance.
It does not evaluate subject-trace satisfaction for all five constraint kinds.
Likewise, existing truth-result validation does not monitor all assertion roles over intervals.
Do not promote either check into evidence for behavior it does not exercise.

## Extension seam and non-goals

The extension seam is the context that gives the trace its meaning.
It supplies occurrence projection, owner boundaries, admitted clock/segment, and coverage assumptions.
State these dependencies in the definitions.
Do not hard-code a backend, participant event family, or `scenario_time` string.
Another subject family or governed clock binding can then reuse the core relations.
This math context does not authorize a new runtime abstraction, public parameter, or plugin registry.

This work adds no SDL syntax, schemas, temporal operators, or capability terms.
It adds no evaluator, scheduler, monitor, store, API, migration, or mechanized proof.
Do not change legacy SEM-213 contracts or infer shared clocks from matching strings.
Do not duplicate objective-window resolution, participant trace validity, truth algebra, validation, or workflow lifecycle logic.
Keep accepted ADRs and pinned research evidence intact.

Review all five kinds and all three roles against these obligations.
Include counterexamples and boundary cases.
Existing evidence includes `test_sem_227_shared_time_model.py`, `test_api_421_time_contracts.py`, `test_proposition_semantics.py`, and `test_runtime_proposition_truth.py`.
Those tests cover current carriers and admission, not the missing definitions.

Keep assurance classes and coverage claims accurate.
Prose and sample traces do not prove runtime enforcement.
Use targeted checks locally.
Full test, integration, fuzz, and proof suites remain CI/CD work.

This guidance-only change has no executable behavior to mutation-test.
