# Replacing failed or invalid experimental trials

An experiment can explicitly authorize additional trials for an original
allocation slot. Add this optional choice inside its existing `run_plan`:

```yaml
replacement_policy:
  schema_version: trial-replacement-policy/v1
  max_replacements: 2
  replace_on: [failed, invalidated]
```

The choice works with `target_run_count` or condition-based `allocation`.
The limit counts additional admitted trials per original slot, excluding the
original. A failed replacement consumes this same budget. The supported limit
is 0–1000, subject to aggregate compilation work/byte ceilings. Booleans, strings
and fractions are rejected. Triggers must be unique. Select only `invalidated`
when failed scientific outcomes should remain included.

Omission authorizes no replacement. Explicitly disable with
`{max_replacements: 0, replace_on: []}`. Existing documents need no migration;
omitted new fields preserve their serialization, commitments and identity
vectors. `replication_policy` and `stopping_rule` stay descriptive. Backend
retries, persistence, replay and operation recovery never supply permission.
SCE-007 retries keep their entry/run identities and independent attempt budget.

## Explicit allocation and execution

`raes_processor.trial_compiler.compile_replacement_trial` consumes the original
`TrialCompilationRequest`, original sealed plan and slot id, a qualifying
`failed_run`, complete cleanup receipts, and the coordinator's complete
`previous_allocations` prefix for that slot. Its `TrialReplacementResult` contains
one separately sealed single-entry child plan and a supersession version of the
parent, or safe diagnostics and no allocation. Original plans and run versions
are immutable. Changed policy or other original inputs require a new admission.

The child has new plan, entry, coordinate, cleanup-plan and archival identities.
Use ordinary `realize_admitted_trial_entry` and execution admission for fresh
scenario, workflow, participant, time and credential-resolution state. Never
copy a failed snapshot, credential cache or history. The first child archival
version is `1`, reserved by the parent's exact `superseded_by` reference.

Condition and block remain unchanged. Deterministic selection retains its
original row; sampled policies use the new coordinate through the existing
random-stream engine, so a replacement may sample a different variation.
Existing streams remain unchanged. Mixed children retain the slot's exact
apparatus profile; incompatible fresh selection is refused without rebinding.

Reuse requires matching terminal-attempt cleanup evidence with successful
required obligations and a clean-state claim covering every affected boundary.
Failed, partial, unverified or missing cleanup blocks reuse.
`fresh-range-required` is refused here; different resources require separate
admitted isolation evidence. Changed ids, directories or leases are insufficient.
Portable validation does not prove backend truth: the allocator must establish
cessation, actual clean state, live ownership, authorization and current backend
willingness before effects.

## Coordinator persistence and duplicates

This pure compiler seam adds no store, service or automatic failure handler.
The embedding experiment coordinator must serialize its allocation decision and
atomically persist the ordinal, child plan and archival supersession before
dispatch, using its established ownership/CAS and scoped idempotency boundary.
Durable execution requires durable artifacts and authoritative readback after
uncertain commit acknowledgement. An embedding without that boundary cannot
claim restart-safe experiment execution.

Duplicate/concurrent compilation of a slot and ordinal returns the same child
identity. Replaying a committed decision with exact history returns that decision
without another debit; it does not authorize executing twice. After restart or
uncertain commit, read the committed prefix before allocating. An empty cache
is not evidence of empty history. Conflicting evidence, gaps, forks, edited
policy and excessive histories are refused. Rejected compilation consumes no
allocation; every committed child does, including undispatched children.

#1361's SDL `new-trial` response and `fresh_trial_limit` request a native failure
response; they do not replace experiment authority. Unbound operation-level
requests still fail admission with `trial-allocation-authority-required`.
This API does not bypass that guard or enable universal backend recovery.

## Retention, analysis and exhaustion

Keep the exact parent version named in child lineage and the returned
supersession version. The latter preserves timestamps, outcome, results,
invalidation reason and evidence; it adds predecessor/successor references and
changes archival status/version. Supersession records admission, not success.
Version-bound evidence relations and validation disclosures stay on the exact
referenced original version. The status-only supersession version does not
relabel their authority or claim the old validation applies to a new artifact.

`reconcile_replacement_trials` joins original/child plans, retained run versions
and cleanup evidence. It returns at most one eligible leaf per original slot,
shortfalls and exhausted slots. Failed scientific results remain eligible when
their trial status was not selected for replacement; selected failed leaves
remain shortfalls at exhaustion. Invalidated, superseded and not-evaluated
leaves are excluded. Do not
select the best descendant or delete negative results.

Call `validate_admitted_trial_study` with `replacement_plans`, `cleanup_receipts`
and full retained run history. Evaluation membership names eligible leaves;
parents need no calibration membership. Task, condition, stochastic-control,
content-backed evidence, metric and target-coverage checks remain enforced.
Original slots remain the scientific target. Membership counting a replaced
parent is rejected. Retained evidence stays in the existing archival graph.

Exhaustion returns `trial-compiler.replacement-limit-exhausted` without a child
or supersession update. Cleanup refusal preserves the independent primary and
cleanup failures. Retain shortfalls and disclose missing runs and replacement
bias in study validity notes; do not increase the target or claim completion.
