# Participant episode policy fixtures

These fixtures check `behavior_specifications.*.episode_policy` for DSL-120.

The [valid fixture](valid/analyst-shift-episode.yaml) uses a participant that is not autonomous.
Its policy has start checks, decision-epoch turns, completion, timeout, truncation, and reset intent.
It must pass strict source decoding.
It must also pass semantic validation.
The compiler emits `participant.episode-policy.analyst-triage`.
This record uses the participant's `participant.behavior.analyst` episode address.

The [invalid fixture](invalid/realized-episode-state.yaml) uses the same scenario.
Its policy asserts lifecycle status, initialization time, decision epoch, and terminal reason.
Source decoding must reject it.
An authored policy declares intent only.
Realized episode state stays with the ADR-013 participant episode contracts.

The [standalone fixture](valid/standalone-episode-structure.yaml) is for ACT-623.
Its behavior specification has an episode policy as its only behavior surface.
It must pass strict source decoding and semantic validation.
The compiled aggregate names `participant.episode-policy.replay-episodes`.

The [autonomous-profile fixture](invalid/autonomous-profile-episode-structure.yaml) is also for ACT-623.
It puts the same policy inside the autonomous execution profile.
Source decoding must reject it.
An episode policy belongs to the behavior specification for all participant kinds.

These fixtures do not show episode execution, reset, or an observed terminal condition.
The [episode policy reference](../../../../docs/explain/sdl/participant-episode-policies.md) explains the fields and their limits.
The [episode runtime binding guide](../../../../docs/explain/sdl/participant-episode-runtime-binding.md) explains the ACT-623 attachment and runtime checks.
