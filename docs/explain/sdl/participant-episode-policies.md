# Participant episode policies

Put `episode_policy` on a behavior specification to declare how its participants' episodes should run.
It is a closed record of intent.
It names existing assertions, action contracts, temporal constraints, evidence requirements, and an optional reset authority.
It adds no expression language, counter, or backend callback.

The required profile is `participant-episode-policy/v1`.
A policy must have at least one structure element with data.
It can be the specification's only behavior surface.
Null records and empty condition maps do not satisfy the structure requirement.

## Declare episode structure

This example uses existing declarations from the
[complete valid fixture](../../../contracts/fixtures/sdl/participant-episode-policy-v1/valid/analyst-shift-episode.yaml).

```yaml
episode_policy:
  profile: participant-episode-policy/v1
  initialization:
    assertion_refs: [console-ready]
  interaction_structure:
    order_basis: decision-epoch
    action_contract_refs: [triage-alert]
  terminal_conditions:
    ticket-closed:
      terminal_reason: completed
      assertion_refs: [ticket-closed]
      evidence_requirement_refs: [ticket-evidence]
    shift-ended:
      terminal_reason: timed_out
      temporal_constraint_ref: shift-deadline
      evidence_requirement_refs: [shift-clock-evidence]
  truncation_conditions:
    queue-stalled:
      assertion_refs: [queue-stalled]
      evidence_requirement_refs: [queue-evidence]
  reset_policy:
    control_actions: [reset, restart]
    participant_memory_scope: persistent_across_episodes
    evidence_requirement_refs: [reset-evidence]
```

Use `precondition` assertions for `initialization`.
Use `invariant` or `postcondition` assertions for completion and truncation.
A turn's action contracts must belong to the owning specification and every selected participant.
A timeout names a deadline, window, or duration constraint that binds the specification or every selected participant.
Each condition maps to exactly one reason: `completed`, `timed_out`, or `truncated`.
The external `interrupted` reason cannot be authored.

Condition keys are local identifiers.
Module composition keeps these keys and rewrites the external refs.
A participant has at most one episode policy.
A second policy selecting that participant by name or role is rejected.

A condition holds only when every named assertion holds.
To express alternatives, declare one condition per assertion.
A truncation condition cannot reuse a completion condition's exact assertion set.
The condition's evidence requirements together back the change of state.
The checks require each named requirement to exist.
They do not check which record it captures.

## Declare reset intent

The example names `persistent_across_episodes` memory scope, so it claims no reset authority.
An `episode_local_reset` scope requires `memory_reset_authority_ref`.
That authority resets the participant implementation and all memory the participant can see.
ADR-095 assurance and information-state contracts require the same pairing.
The authored policy does not supply those contracts' values.

The reference must name exactly one declared `targetable` element.
Examples include `agents.analyst` and `nodes.siem.services.console`.
A name that is absent or matches more than one element is rejected.
Each imported unit must resolve the name on its own.
The name is then placed in the import's namespace.
The compiler records its canonical address, such as `sdl.agents.analyst`.

## Keep intent separate from observations

The policy rejects realized fields such as `episode_id`, `status`, `initialized_at`, and `decision_epoch`.
The diagnostic points to the ADR-013 participant episode contracts.
A `terminal_reason` is permitted only on a terminal condition.
For a truncation condition, the diagnostic explains that truncation already fixes the reason.

The compiler emits `participant.episode-policy.<name>`.
This record holds resolved assertion, action, time, evidence, and reset-authority addresses.
It names selected participants through their `participant.behavior.<agent>` addresses.
These addresses also key realized episode state.
These records do not execute episodes, evaluate conditions, or handle resets.
They do not capture evidence or realize a backend.

## Sources and verification

DSL-120 uses the existing `episodes` concept-family lineage recorded in
[reference models](../../../specs/concept-authority/reference-models.md), including Gymnasium and OpenAI Gym episode concepts.
It combines existing proposition/assertion, shared-time, action-contract, and evidence lineages.
Termination and truncation stay distinct: a task's own dynamics can end an episode, while an imposed limit can stop it early.
An external stop remains outside authored intent.

The governed SDL schemas, their publication entries, and the valid and invalid fixtures provide verification evidence.
So do the [episode policy tests](../../../implementations/python/tests/test_issue_307_dsl_120_participant_episode_policy.py).
They cover authoring, composition, semantic checks, checks after instantiation, compilation, and schema compatibility.
They do not establish Gymnasium API compatibility or runtime adoption.
The SDL lineage ledger and source audit remain unchanged.
This surface reuses existing carriers without changing their normative derivation or compatibility claims.

The normative rules are in the
[section contract](../../../specs/sdl/sections.md#participant-episode-structure) and
[episode model](../../../specs/formal/participant-episode-model/README.md).
