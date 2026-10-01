# Participant-local outcome reporting

Local outcomes describe declared participant tasks/effects independently of an
objective, evaluator or reward producer. Action success alone does not establish
attainment: declared effect criteria need recorded evidence.

Declare `local_outcome` on a SEM-215 rule with `semantic_version: 2.0.0` and local
`model_version: 1.0.0`. Select `task_completion` or `effect_realization`, explain
the criterion basis, and bind each criterion to a declared action source/effect.
The policies are `retain_until_explicit_correction`, `exact_observation_cut` and
`reset_without_transfer`. These opted-in rules support empty downstream targets.

Bind the rule through a behavior specification’s
`outcome_interpretation_rule_refs`, selecting the participant with
`participant_refs` or its entity role with `participant_role_refs`. Sharing an
action contract alone does not authorize a rule.

Supply the compiled model as
`RuntimeControlPlane(..., participant_outcome_model=model)`. Submit a typed
`ParticipantOutcomeUpdateRequest` through `record_participant_outcome`, with an
authenticated operator identity bound to the target and participant. Requests
name participant, episode, outcome, report event and rule, plus expected outcome
and snapshot revisions. The runtime computes attainment from recorded history.
Supply a `ControlPlaneStore` and read its existing `load_snapshot_state()` result
to obtain the snapshot and its revision together.

The receipt identifies the durable operation/audit. Exact retries are idempotent;
changed reuse of an event ID fails. After a revision conflict, refresh the cut
and use a new event identity. Corrections append a report with explicit excluded
observation references and a correction basis; retain prior exclusions.

`current_participant_outcome(snapshot, participant_address, outcome_id)` returns
the current episode's report and `current`, `stale` or `absent`. Partial attainment
can coexist with unknown knowledge. Contradictory evidence does not resolve by
arrival order. Reset selects no previous-episode report and retains history.

These are embedded operator surfaces. Participant retrieval views do not
automatically expose outcome criteria, references or knowledge. The generic
HTTP snapshot response also omits private outcome history. No new HTTP
route is introduced, and evidence references grant no evidence access.

For historical reports, use `decode_participant_outcome_report` in
`raes_contracts.contracts.participant_outcomes`. Unsupported versions fail.
Existing v1 reports retain their original meaning; adoption requires a new v2
report from grounded history while preserving the original artifact.

The [normative semantics](../../../specs/formal/participant-semantics/local-outcomes.md)
define category, evidence, transition, freshness and compatibility rules.
