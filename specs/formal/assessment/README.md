# Assessment semantics (SDL scoring chain removed)

[ADR-073](../../../docs/decisions/adrs/adr-073-scoring-reward-language-scope.md)
removed the OCR-inherited SDL scoring/assessment pipeline.
The former chain was `condition bindings -> metrics -> evaluations -> TLOs -> goals`.
It is no longer an SDL authoring surface.
The `metrics`, `evaluations`, `tlos` (Training Learning Objectives), and `goals` sections are removed.
The CybORG `agents.reward_calculator` label is removed too.

## What remains in the SDL

- `conditions` describe executable probe bindings.
  They compile onto runtime `evaluation.condition.*` addresses.
- Backend-neutral `propositions` describe truth claims.
  `assertions` give their role and polarity.
- An objective's `success.assertions` references invariant or postcondition assertions.
- Event triggers and workflow predicates reference precondition assertions.

[ADR-079](../../../docs/decisions/adrs/adr-079-backend-neutral-proposition-and-truth-semantics.md)
replaces the former direct condition references.
The current model rejects `success.conditions`.
See the [objective reference](../objectives/declarative-objective-semantics.md)
and [truth-result algebra](../objectives/proposition-and-assertion-semantics.md).
These corrections apply an existing decision; they add no new scoring or truth semantics.

There is no condition→metric→evaluation→TLO→goal scoring chain, no score
aggregation rule, no per-condition metric-exclusivity rule, and no
scoring-chain ordering/refresh derivation in the SDL.

## Where graded scoring now lives

Graded scoring, cumulative reward, pass/fail evaluation, leaderboard values, and
evaluation outputs live exclusively in the experiment/evaluator plane, never as
authored SDL:

- experiment-core contracts
  ([ADR-055](../../../docs/decisions/adrs/adr-055-experiment-core-contract-boundary.md)):
  `experiment-task-v1` metric definitions, `experiment-study-v1` analysis plans;
- evidence/measure contracts
  ([ADR-064](../../../docs/decisions/adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md)):
  `experiment-evidence-record-v1`, `experiment-derived-measure-v1`;
- the backend **Evaluator**
  ([ADR-069](../../../docs/decisions/adrs/adr-069-cage-2-replication-architecture.md)
  §3), which projects reward, objective, terminal-condition, and scoring facts
  into RAES evaluation results, evidence records, and derived measures.

The governing requirement remains **SEM-206 (Assessment Semantics)**;
[`../../../docs/explain/reference/assessment-semantics.md`](../../../docs/explain/reference/assessment-semantics.md)
carries the implementation-facing reference for the narrowed semantics.
