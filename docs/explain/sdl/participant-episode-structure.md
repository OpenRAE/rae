# Participant episode structure

`episode_policy` is an optional, closed record of participant episode intent
(DSL-120). It names existing assertions, action contracts, temporal
constraints, and evidence requirements, and, for an episode-local reset, a
declared reset authority. It never carries a new expression, counter, or
backend callback.

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

Initialization assertions must be preconditions. Completion and truncation
assertions must be invariants or postconditions. A turn's action contracts must
belong to the owning specification and to every participant it selects. A
timeout must name a deadline, window, or duration constraint that binds the
specification or every participant it selects. Each condition maps to exactly
one terminal reason: `completed`, `timed_out`, or `truncated`. `interrupted`
stays an external stop and cannot be authored.

Condition keys are local
identifiers that module composition preserves while it rewrites the external
refs. A participant may be governed by one episode policy at most. A second
policy that selects the same participant, by name or by role, is rejected.

A condition holds only when every assertion it names holds. To end the episode
when any one of several assertions holds, declare one condition per assertion.
A truncation condition cannot reuse the exact assertion set of a completion
condition. The evidence requirements a condition names together back its
transition; validation checks that each one is declared, not which record it
captures.

The example declares `persistent_across_episodes`, so it names no reset
authority. An `episode_local_reset` scope must add a
`memory_reset_authority_ref` that names the authority resetting the
participant implementation and its participant-visible memory. ADR-095's
assurance and information-state contracts require the same pairing; the policy
does not supply their values. The reference must resolve to exactly one
declared targetable element, for example `agents.analyst` or
`nodes.siem.services.console`. A dangling or ambiguous reference is rejected.
An imported unit must resolve it on its own, before module composition
namespaces it, and compilation records the element's canonical address, such as
`sdl.agents.analyst`.

The policy is intent, not an execution record. Fields such as `episode_id`,
`status`, `initialized_at`, or `decision_epoch` are rejected with a diagnostic
that points to the ADR-013 participant episode contracts. So is a
`terminal_reason` anywhere except a terminal condition; on a truncation
condition the diagnostic says that truncation already fixes the reason.

Compilation emits
`participant.episode-policy.<name>` with the resolved assertion, action,
time, evidence, and reset-authority addresses. It keys the policy to the
selected participants' `participant.behavior.<agent>` addresses, which also
key realized episode state. The full fixture at
`contracts/fixtures/sdl/participant-episode-policy-v1/valid/analyst-shift-episode.yaml`
shows the complete document. Episode execution, condition evaluation, reset
handling, and evidence capture remain runtime surfaces; this surface claims no
executable or runtime adoption.

The episode policy is a first-class member of the behavior specification, not
an option of one participant kind. It works the same way for autonomous,
scripted, replayed, policy-directed, human-supervised, human-control-proxy, and
mixed-control participants, and a specification may declare only an episode
policy. The fixture
`contracts/fixtures/sdl/participant-episode-policy-v1/valid/standalone-episode-structure.yaml`
shows such a specification. The autonomous execution profile rejects an
episode policy, so the behavior specification stays its only home.

`participant_episode_structure_conformance_diagnostics()` in
`raes_conformance.conformance` checks recorded episode history against the
compiled policies. It reports a terminal reason that no authored condition
produces, other than `interrupted`, and a reset or restart that the reset
policy does not admit. For a policy without a `reset_policy`, it admits any
reset or restart. It reads history only and does not evaluate conditions.

The runtime control plane accepts a `ParticipantEpisodeRuntimeBinding` through its `participant_episode` option.
The binding retains the compiled model and one admitted manifest selection per governed participant.
It checks implementation identity, manifest digest, decision mode, and support for the episode state and history contracts.
Missing or duplicate selections fail before a backend call.
The binding checks reset actions and terminal reasons before dispatch through the existing ADR-013 lifecycle.
It also checks restored history and successful backend results against the authored bounds.

Initialization assertions, turn execution, condition evaluation, and memory-reset realization remain their existing owners' responsibilities.

`run_target_conformance` accepts `participant_episode_model` and `participant_episode_snapshot` as recorded evidence inputs.
The report includes episode-policy and snapshot-integrity findings and fails when a governed participant lacks recorded history.
A target without the matching episode contracts receives a `not-applicable` result, not a passing episode case.
The same applies when no authored episode policy is selected.
The report keeps recorded-history inspection separate from native execution claims.
The diagnostics function is also exported from `raes_conformance`.

The legacy runtime manager does not install this binding and rejects authored episode-policy plans before execution.
Use the control plane with the exact compiled binding for these plans.

