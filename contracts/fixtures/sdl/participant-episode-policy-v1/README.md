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

These fixtures do not show episode execution, reset, or an observed terminal condition.
The [episode policy reference](../../../../docs/explain/sdl/participant-episode-policies.md) explains the fields and their limits.
