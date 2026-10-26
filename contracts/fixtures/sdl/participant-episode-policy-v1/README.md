# Participant episode policy fixtures

These fixtures exercise the DSL-120 authored participant episode surface,
`behavior_specifications.*.episode_policy`.

- `valid/analyst-shift-episode.yaml` declares initialization, decision-epoch
  turn structure, a completion and a timeout terminal condition, a truncation
  condition, and a reset policy for a non-autonomous participant. It must pass
  strict source decoding and semantic validation, and it compiles to the
  `participant.episode-policy.analyst-triage` record keyed to the participant's
  `participant.behavior.analyst` episode address.
- `invalid/realized-episode-state.yaml` is the same document with a policy that
  asserts realized episode state (lifecycle status, initialization time,
  decision epoch, and terminal reason). Decoding must reject it, because the
  authored policy declares intent only and realized episode state belongs to
  the ADR-013 participant episode contracts.

Neither fixture represents an executed episode, a reset, or an observed
terminal condition.
