# Objective Semantics

Implementer-facing reference for the declarative-objective semantics (`SEM-207`),
governed by ADR-016. The formal artifact is
{download}`specs/formal/objectives/declarative-objective-semantics.md <../../../specs/formal/objectives/declarative-objective-semantics.md>`;
this note is the working summary.

## What an objective is

A declarative *objective* binds, in one place:

- an organizational **owner** and/or an **assigned participant**, using `owner`
  (entity) and `assigned_participant` (agent). These are independent relations,
  not realized actor attribution or beneficiary identity. Every `actions` entry
  must name a declared action contract; when assigned, it must also be available
  to that participant;
- zero or more **targets**, resolved through the targetable named-reference
  index (bare or section-qualified; objectives, workflows, and variables are not
  targetable);
- a **success** interpretation — `mode` (`all_of` / `any_of` / `at_least`) over
  referenced invariant or postcondition assertions. Assertions use typed,
  backend-neutral propositions; executable `conditions` only bind probes. The
  OCR scoring surfaces `metrics`, `evaluations`, `tlos`, and `goals` were
  removed by
  [ADR-073](../../decisions/adrs/adr-073-scoring-reward-language-scope.md);
- an optional **window** that constrains when the objective matters (the
  story/script/event/workflow/workflow-step reachability and consistency rules
  live with the window helper — see
  {download}`specs/formal/objectives/window-consistency.md <../../../specs/formal/objectives/window-consistency.md>`);
- a `depends_on` **ordering** relation onto other objectives, which must be
  acyclic.

Objective semantics are declarative SDL meaning. They do not choose participant
implementations, backend probes, evaluator queries, execution adapters, prompts,
credentials, polling loops, or live control-plane behavior.

## Name-level source of truth

`raes.semantics.objective_semantics.analyze_objective_semantics(...)` is the
single name-level analyzer. Given the name-keyed SDL constructs plus the
targetable named-reference index (and an optional `is_unresolved` predicate so
`${var}` placeholders are skipped and re-checked after instantiation), it
returns an `ObjectiveSemanticAnalysis`:

- `references` — normalized `ObjectiveReference` edges (owner, assignment, action constraint, target, success,
  window, dependency), each carrying its `dependency_roles` and a `namespace_path`
  slot used by module/import expansion;
- `issues` — machine-readable consistency problems, per objective in the order
  assignment, owner, action, target, success, window, dependency, then a single global
  `objective.dependency-cycle` issue when the `depends_on` graph cycles. Callers
  translate the codes into their own envelope (the validator renders them as
  authoring-error strings via `_OBJECTIVE_ISSUE_RENDERERS`; the compiler emits
  its own `evaluation.*` diagnostics for the window slice);
- `dependencies` — per-objective derived ordering/refresh dependency *names*;
- `window_analyses` — the per-objective `ObjectiveWindowAnalysis`, so callers
  reuse the window resolution rather than re-running it.

Whether a proposition has a realizable probe binding is a compilation and
backend-admission concern. The compiler emits distinct
`evaluation.proposition.*`, `evaluation.assertion.*`, and bound-condition
diagnostics against the resolved addresses; this analyzer deals only with the
name-level reference graph that is meaningful before binding resolution.

## Dependency roles

Success references and `depends_on` edges carry **both** roles — the objective
is evaluated *after* its inputs (ordering) and re-evaluated *when* an input
changes (refresh). Window edges carry **only** refresh; they impose no
execution-order constraint. Owner, assignment, action-constraint, and target references are normalized for
fail-closed validation and propagated through the analyzer's IR, but they carry
an **empty** role tuple today: the compiler does not compile actor or target
identity into runtime ordering or refresh dependencies, and advertising a role
that never reaches the planner would let the helper claim a propagation that
does not happen. If actor or target identity is compiled into runtime
addresses, the corresponding `REFRESH` or `ORDERING` role constants must change
in lockstep.

That single fact lives in `partition_objective_dependencies` plus the
`OBJECTIVE_SUCCESS_DEPENDENCY_ROLES` / `OBJECTIVE_DEPENDENCY_DEPENDENCY_ROLES` /
`OBJECTIVE_OWNER_DEPENDENCY_ROLES` / `OBJECTIVE_ASSIGNMENT_DEPENDENCY_ROLES` /
`OBJECTIVE_ACTION_CONSTRAINT_DEPENDENCY_ROLES` / `OBJECTIVE_TARGET_DEPENDENCY_ROLES` /
`OBJECTIVE_WINDOW_DEPENDENCY_ROLES` constants — each category is gated by its
own constant so a role change to one category lands in exactly one
place. The validator, the compiler's `ObjectiveRuntime` ordering/refresh
tuples, and the planner's generic reconciliation all derive their behavior from
those constants, so a change to a success assertion (or to a depended-on
objective) propagates as a refresh through `objective -> depends_on -> objective`.

In the analyzer's name-level IR the derived `ordering_names` / `refresh_names`
are kind-qualified (`condition.<n>`, `objective.<n>`, `story.<n>`, `script.<n>`,
`event.<n>`, `workflow.<n>`) so a condition and an objective with the same SDL
name remain distinguishable, mirroring the canonical `evaluation.*` addresses the
compiler builds independently.

## Cross-stage agreement

- **validation** — `SemanticValidator._verify_objectives` calls the analyzer and
  renders every issue as an authoring error;
- **compilation** — `compile_runtime_model()` resolves the success and
  `depends_on` references onto canonical `evaluation.*` addresses, runs the
  window helper for the window diagnostics, and derives `ObjectiveRuntime`'s
  `ordering_dependencies` / `refresh_dependencies` via
  `partition_objective_dependencies`;
- **planning** — `plan()` walks those edges generically (ordering for execution
  order, refresh for change propagation).

`implementations/python/tests/test_fm2_semantics.py` (`TestObjectiveSemanticAgreement`,
`TestObjectiveWindowAgreement`) is the cross-stage agreement suite; the analyzer
itself is unit-tested in `implementations/python/tests/test_semantics_objectives.py`.

## Anti-patterns

- a second objective schema beside `raes.objectives`, or a second reference
  resolver beside `SemanticValidator`'s named-reference index / the compiler's
  canonical address helpers;
- duplicating the window, dependency, or reference-resolution rules in compiler,
  planner, or tests;
- mixing objective actor binding with participant episode lifecycle or apparatus
  realization, or treating objective targets as backend execution targets;
- encoding evaluator query language, probe commands, credentials, or polling
  behavior in objective `success`;
- editing generated schemas under `contracts/schemas/` directly;
- a `SEM-207`-specific exception, logging, persistence, or audit stack.
