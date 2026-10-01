# Participant Decision Surface V2 Migration

This note is the implementation-facing migration guide for ADR-095 and issue
#909. The normative semantics are in ADR-095 and the participant formal
specification.

## Compatibility Rule

`participant-decision-surface-v1` keeps its historical meaning:
`observation_order` selects an occurrence in a supplied time-indexed behavior
history. Do not reinterpret it as a participant decision ordinal.

`participant-decision-surface-v2` is the actionable runtime path. Migration is
reprojection, not field renaming. A historical v1 record remains valid
historical evidence under its published schema, but copying
`observation_order` into `decision_epoch` does not create a valid v2 surface.

## Producer Migration

For each participant choice:

1. Resolve the current authoritative participant episode. It must be running.
2. Resolve the derivation state cut.
   - For decision epoch zero, use the current `episode_running` lifecycle head
     and require empty behavior history for the new episode.
   - For a later epoch, use the exact current terminal
     `observation_emitted` occurrence and the complete current-episode behavior
     prefix.
   - Use a typed causal frontier when the backend claims partial-order
     realization; do not substitute a maximum scalar order.
3. Derive `decision_epoch` independently. Callers do not author it.
4. Resolve apparatus, projection policy, and every item authorization at the
   exact state cut. Persist the exact policy-decision and authorization refs.
5. Construct only participant-available material in `participant_view`.
6. Construct trusted anchor, policy, exposure, evidence, provenance, canonical
   view digest, and participant-memory scope in `assurance`.
7. Emit the surface in `projected` state.
8. Resolve an authoritative delivery occurrence for that exact view and
   transition to `delivered`.
9. Accept a selection only when it binds surface id, decision epoch, canonical
   participant-view digest, and delivery ref.
10. At admission, re-resolve the derivation anchor, delivery record, apparatus,
    and existing participant-action constraints before writing behavior. Pass
    the authenticated caller identity and, for governed ingress, the caller's
    crossing evidence to the v2 admission method. The selection and delivery
    record do not supply either authority or ingress evidence.

The reference entry points are:

- `resolve_participant_episode_readiness_anchor_v2()`;
- `resolve_participant_behavior_projection_anchor_v2()`;
- `project_participant_decision_surface_v2()`;
- `deliver_participant_decision_surface_v2()`; and
- `admit_participant_decision_surface_selection_v2()`.

## Consumer And Apparatus Migration

A participant implementation that consumes v2 must declare
`participant-decision-surface-v2` in both manifest
`supported_contract_versions` and
`capabilities.supported_participant_contracts`. The selected apparatus record
must also include it in `participant_contract_versions`. Admission fails closed
when that declaration is absent.

Serialize `participant_view` to the participant. Do not serialize the
assurance plane as if it were part of the participant observation. Evidence or
provenance may enter a participant view only through an independent exposure
decision.

## Reset, Restart, Replay, And Memory

Reset and restart create a new episode identity and decision epoch zero. A
surface from the prior episode is stale and cannot be replayed. These lifecycle
operations do not establish that a human, agent process, external controller,
or shared memory forgot a prior delivery.

Every v2 assurance declares one memory scope:

- `persistent_across_episodes`, with no reset-authority claim; or
- `episode_local_reset`, with a `memory_reset_authority_ref` that covers every
  participant-visible memory channel.

## Evidence Boundary

The v2 contract, runtime path, fixtures, and finite transition/information-flow
tests establish executable bounded evidence for the covered cases. They do not
prove universal trace inclusion, alternating refinement, bisimulation, or
reactive noninterference. Those claims require their separately declared
relations, quantifier scopes, and proof evidence.
