# Author-controlled retries and scoped defaults

Design adopted by [ADR-113](../../decisions/adrs/adr-113-reusable-execution-machinery.md)
for #1350. This is a semantic integration design, not published SDL syntax or a
new executable retry contract. Extend the existing owning contracts before
claiming support. No engine-specific retry fields enter the authored language.
Retry is one part of a contextual failure-response policy, not a universal
failure handler shared indiscriminately by experiments, twins, OT and IT.

## Context determines the permitted response

The common operation lifecycle records facts; it does not impose the same
recovery action or validity meaning on every world. Resolve policy against the
authored purpose, effect contract, operating mode, time/fidelity requirements,
and actual backend guarantees. The following are examples of selectable
policies, not automatic rules inferred from an `IT` or `OT` label:

| Context | Example response and required evidence |
| --- | --- |
| Controlled experiment | Mark this trial failed/invalid under the experiment contract, retain every attempt and observation, then request a separately admitted fresh trial if allowed. An idempotent retry may still bias results and is not automatically permitted. |
| Discrete or continuous digital twin | Hold advancement at a supported boundary, invalidate or qualify the affected state/time interval, and reconcile model/plant state before continuation. Re-reading a sensor, rewinding time or restoring a model checkpoint may change the experiment or break coupling; none is an ordinary transport retry. |
| Live OT or hardware-in-the-loop | Request the backend's admitted safe-hold/controlled-stop procedure, or a specified continuing mode where stopping is unsafe. Require process-state, interlock and operator authorization evidence where the authored contract demands it. Reissuing an actuator command, rebooting a controller or restoring an IT snapshot is not a generic recovery strategy. |
| Disposable IT test/CTF | An author may allow rebuilding a VM, restoring a known snapshot, then retrying after verified clean-state admission. That policy is inappropriate for resources the scenario is required to preserve. |
| Stateful IT/product or disaster recovery | Reconcile transactions, external services, data consistency and recovery objectives before selective retry/restore. IT is not inherently reversible or idempotent; externally visible effects may be as non-repeatable as OT actions. |
| Mixed IT/OT scenario | Apply each scope's effect and failure policy while preserving cross-scope dependencies, shared resources and time coupling. Restarting an IT gateway must not silently authorize another plant action or invalidate a twin's admitted state. |

Failure handling must distinguish infrastructure/delivery failure, backend
refusal, operation failure, deliberate in-world faults, loss of fidelity/time
continuity, and invalid experimental evidence. Do not let an infrastructure
reconciler repair an intentionally injected outage, or let a cleanup failure
disappear behind a primary success. RAE selects only the permitted response
using the canonical workflow/time/trial owners; the backend establishes whether
the concrete response is possible and what it actually did.

Convenience defaults can select reusable context policies and narrower scopes
can choose different ones. At admission, validate their interactions: one
scope's reset can affect another scope's equipment, data or clock. An
incompatible composition is refused, not resolved by whichever scope retries
first. No backend or engine supplies an unrecorded domain policy.

## Choices and identities

Idempotency describes an effect's repeat behavior; permission describes whether
the author wants repetition. Both must hold where required. An idempotent call
can still invalidate an experiment through repeated observations, elapsed time,
cost or participant exposure. RAE must support these distinct authored choices:

| Author choice | Meaning |
| --- | --- |
| Never repeat | At most one effect invocation for this admitted occurrence. A failed or uncertain invocation cannot cause another effect merely through retry/recovery. |
| Bounded retry in this trial | Retry only for selected failure/effect classes, within attempt and time budgets, after the declared safety and cleanup conditions hold. This can require verified absence, scoped backend idempotency, reset or compensation. |
| End this trial; request a fresh trial | Preserve the failed/invalid trial and its evidence. Admit a new trial through the experiment authority, with a new run identity, declared initialization/variation and verified isolation/cleanup. Do not increment a workflow retry counter and relabel the old trial as successful. |

Fresh-trial policy applies only where a trial context exists and its owning
experiment plan permits allocation; reject it on an ordinary operation lacking
that authority. Authors can allow bounded retries followed by a fresh trial on
exhaustion, or choose a fresh trial immediately. The trial allocation budget is
independent of within-trial attempts; neither can be unbounded by omission.

Keep four identities separate: engine delivery/task attempt; one permitted
backend invocation; authored workflow/execution attempt; experimental trial.
Redelivering a reference to the same invocation never allocates another one.
An explicitly admitted retry gets its own invocation/attempt identity and
provenance; a fresh trial gets its own run identity. Engine reset, restart and
Continue-As-New are not any of those author decisions.

## Scope resolution

Use the existing [lexical scope principle](../../../specs/sdl/recursive-realization-constraints.md#2-records-scopes-and-closure):
scenario default, enclosing scope defaults, then the most-specific explicit
operation/occurrence policy. Reuse canonical semantic addresses and bounded
reference resolution. This reuses scope mechanics, not the open/closed value
vocabulary: closure does not imply a retry policy.

1. A missing local policy inherits. An explicit never-repeat policy is a value,
   not omission; a locally stricter or more permissive default affects only that
   subtree. A concrete child choice can override a convenience default, subject
   to binding requirements and admission. Siblings keep their inherited policy.
2. Resolve a **complete policy** at the nearest defining scope. Do not combine
   unrelated fields from different levels into an accidental policy, such as a
   child's reset mode with a parent's idempotency assumptions. Reusable named
   policies provide concise authoring; any later partial-overlay syntax must
   normalize to the same complete, validated value with field provenance.
3. Duplicate definitions at the same semantic scope, ambiguous targets, cycles,
   unsupported versions and conflicting binding constraints are admission
   errors. Import order, list order and engine defaults never break a tie.
   Reusable definitions retain lexical binding; execution at a call site cannot
   silently change them. An explicit application-site policy is validated as a
   new local choice before the compiled plan is admitted.
4. Defaults are convenience, not a way to weaken a required guarantee, bypass
   backend policy or grant authority. Resolve the author's desired policy, then
   validate the entire composition. Refuse incompatibility instead of silently
   clamping to fewer retries or substituting a new trial.
5. If no scope supplies permission to repeat, permit no second effect. This is
   a specified conservative fallback, not an implementation library's default.
   The author remains free to select a different scenario-wide default.
6. Materialize the resolved policy and defining scope/reference/version into the
   admitted plan and operation commitment. Record changes as new admissions;
   editing a scenario default cannot retroactively alter an active invocation,
   a restored operation or historical evidence.

Conceptual examples, **not YAML syntax**:

| Scenario default | Nearer scope or local choice | Effective result |
| --- | --- | --- |
| Never repeat | Setup scope: at most three total attempts, admitted idempotency required | Setup may retry only under that condition; other operations remain one-shot. |
| Setup policy above | One actuator operation: never repeat | That operation remains one-shot, including after worker loss. |
| Bounded idempotent retry | Measurement scope: end this trial and request a fresh trial | Measurements never repeat within the same trial, even if technically idempotent. |
| Never repeat | No local choice | Inherit never repeat; no annotations are needed on every operation. |

## Effective policy and runtime admission

The normalized contract must identify its context/profile and revision,
failure classification, validity consequences, permitted response (for example
abort, hold, reconcile, continue at a verified boundary, retry or fresh trial),
and required operator/backend evidence. It must also identify the retry unit,
permitted effect-knowledge classes, total-attempt limit including the first attempt,
delay/backoff and clock basis, total budget, required safety/cleanup evidence,
and exhaustion disposition. Fresh-trial selection additionally binds trial
allocation authority and limits. Reuse `ExecutionRetryPolicyModel`'s existing
`max_attempts` and `after_effect_policy` meanings (`disallow`, `idempotent`,
`reset`, `compensate`) where applicable. Do not infer never-repeat solely from
`after_effect_policy=disallow`: that field addresses after-effect repetition,
while verified absence can have different admitted semantics.

Current SCE-007 cleanup policies do not provide general lexical inheritance,
failure-class/backoff selection or fresh-trial policy. These need governed
extensions under DSL-113/SEM-203 and SCE-002/006/007/EXP-706, not a free-form
metadata dictionary or a second workflow interpreter. Existing explicit workflow
retry bounds remain binding; nested policies must account for every actual
effect and must not multiply hidden retries at transport, activity and workflow
layers. Exhausted budgets do not reset on process restart or scope inheritance.

Before each permitted invocation, RAE rechecks current scope authorization,
policy identity, remaining budgets, backend capability/willingness, reservation
conflicts and required evidence. Backend idempotency needs a defined key, scope,
retention interval and behavior under duplicate/concurrent requests; an author
label is insufficient. Known absence is not cessation if an old caller can
still act later. Concurrent repetition requires explicit proven-safe semantics;
sequential attempts remain the default. Unknown effect state never becomes
safe merely because a worker disappeared.

Reset, compensation and fresh-trial initialization are effects with their own
admission, failure, observation and cleanup obligations. A requested reset does
not establish clean state. An unreconciled old trial cannot share resources with
a new trial unless admitted isolation actually separates their effects. Preserve
the old failure, cleanup result, lineage and any experiment validity decision.

## Engine mapping and verification obligations

Use Temporal's bounded scheduling and retry facilities when they can enforce
the effective policy through current RAE admission on every dispatch. Otherwise
schedule separately admitted single-attempt activities. Never turn engine retry
numbers into the author-visible attempt history. Bookkeeping retry and workflow
replay must not invoke an effect again. Observation can itself affect a system,
so classify it by its admitted effect contract rather than assuming all reads
are harmless.

The public-contract and implementation deliveries must test scenario defaults,
nested overrides, sibling isolation, explicit never-repeat, duplicate scopes,
definition/call-site binding, bounded normalization, incompatible guarantees,
scope reordering, missing policy, policy edits during recovery, budget exhaustion,
and no retry multiplication. Exercise different failure responses for the same
technical exception under experiment, twin, OT and IT policies, plus conflicting
responses across mixed scopes and preservation of intentional faults.
Exercise the same idempotent backend under both
retry-allowed and retry-forbidden policies, plus fresh-trial allocation and
cleanup failure. Those are behavioral gates for the later executable surface;
this design does not claim they pass today.
