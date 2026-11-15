# Participant episode runtime binding

ACT-623 makes `episode_policy` a first-class member of the behavior specification aggregate.
The [episode policy reference](participant-episode-policies.md) explains how to write a policy (DSL-120).
This page explains how a policy attaches to participants, how the runtime keeps its bounds, and what conformance checks.

## Attach a policy to any participant kind

A policy attaches to a behavior specification with any `behavior_mode`, or with no `behavior_mode`.
It can be the only behavior surface of the specification.
The [standalone fixture](../../../contracts/fixtures/sdl/participant-episode-policy-v1/valid/standalone-episode-structure.yaml) shows this case.

The autonomous execution profile cannot contain a policy.
The [autonomous-profile fixture](../../../contracts/fixtures/sdl/participant-episode-policy-v1/invalid/autonomous-profile-episode-structure.yaml) shows the refusal.
Put the policy on the behavior specification instead.

The compiled aggregate names its policy through `episode_policy_address`.
The value is `participant.episode-policy.<name>`, or empty when the specification has no policy.

## Install the binding

Create a `ParticipantEpisodeRuntimeBinding` from the compiled model.
Give it one `ParticipantEpisodeImplementationBinding` for each governed participant.
Each selection must agree with its manifest identity, manifest digest, and decision mode.
It must also declare the episode state and history contracts.
A missing, duplicate, or unsupported selection fails before any backend call.

Pass the binding to the control plane as the `participant_episode` option.
The control plane refuses behavior specifications with a policy when no binding is installed.
It applies, authorizes, or admits a plan with policies only when the binding holds the exact compiled model of that plan.

## Runtime bounds

Before dispatch, the runtime checks each episode request against the policy:

- A reset or restart must be one of the `reset_policy.control_actions`.
  A policy without a `reset_policy` admits all resets and restarts.
- A terminal reason must come from an authored condition.
  An `interrupted` stop is always admitted.

These checks apply to operator and participant requests, mixed-control lifecycle requests, and autonomous clock resets.
A clock reset that would reset a governed participant against its policy is refused before the time runtime is called.

After dispatch, the runtime checks the returned episode history.
This applies to participant actions, mixed-control lifecycle results, and composed time and scheduler results.
A result that violates the policy is not accepted, and the operation needs reconciliation.
The control plane also refuses a stored snapshot whose history violates the policy.

The binding does not evaluate conditions, run initialization assertions, run turns, or realize memory resets.
Those responsibilities stay with their existing owners.

## Read the conformance result

`run_target_conformance` reports a `participant-episode-structure` case.
It uses `participant_episode_model` when you supply it.
Otherwise it uses the binding model, or the model that the probe scenario compiled to.
Supply recorded history as `participant_episode_snapshot`.

| Outcome | Meaning |
| --- | --- |
| `passed` | The recorded history agrees with the compiled policy. |
| `failed` | The history violates the policy, fails snapshot integrity, or misses a governed participant. |
| `unsupported` | No recorded snapshot was supplied. |
| `not-applicable` | The target has no episode capability, or the model has no policy. |

A `not-applicable` case does not count as a pass.
`participant_episode_structure_conformance_diagnostics` is also exported from `raes_conformance`.
The case inspects recorded history only.
It does not show native execution or condition evaluation.
