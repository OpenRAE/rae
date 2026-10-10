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

- `valid/standalone-episode-structure.yaml` (ACT-623) gives a participant a
  behavior specification whose only behavior surface is its episode policy.
  It must pass strict decoding and semantic validation, and the compiled
  aggregate names `participant.episode-policy.replay-episodes`.
- `invalid/autonomous-profile-episode-structure.yaml` (ACT-623) nests the same
  policy inside the autonomous execution profile. Decoding must reject it,
  because episode structure belongs to the behavior specification for every
  participant kind and is not an autonomous-profile option.

None of these fixtures represents an executed episode, a reset, or an observed
terminal condition.
