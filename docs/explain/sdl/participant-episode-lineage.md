# Participant episode lineage

DSL-120 composes the existing `episodes` concept-family lineage with the proposition/assertion, shared-time, action-contract, and evidence lineages.
The episode lineage records Gymnasium and OpenAI Gym in `specs/concept-authority/reference-models.md`.
The exact RAES mapping is `ParticipantBehaviorSpecification.episode_policy`.
It is a versioned record of authored intent.

Initialization uses assertions. Turns use the decision epoch.
Completion and timeout terminal conditions remain distinct from truncation conditions.
The reset policy names admitted control actions and an ADR-095 participant-memory scope.
An episode-local reset also names its reset authority.

Each participant has at most one policy.
Each condition maps to exactly one ADR-013 terminal reason.
It names the evidence requirements that back the transition.
Termination and truncation stay distinct.
The lineage separates an end reached by the task's own dynamics from an imposed early stop.
Interruption is never authored.

The policy rejects realized episode coordinates.
Those coordinates remain on the ADR-013 participant episode contracts.
The [episode structure guide](participant-episode-structure.md) explains the declarations and runtime binding.

## Delivery evidence

DSL-120 evidence comprises governed SDL schemas and publication entries, valid and invalid policy fixtures, and authoring tests.
The test module is `implementations/python/tests/test_issue_307_dsl_120_participant_episode_policy.py`.
It covers authoring, composition, semantic and post-instantiation validation, deterministic compilation, and schema compatibility.
The compilation target is `participant.episode-policy.<name>`.

This authoring surface claims no episode execution, condition evaluation, reset handling, evidence capture, backend realization, or Gymnasium API compatibility.
It only binds existing governed carriers.
It changes neither their normative derivation nor their compatibility claims.
Thus, the SDL lineage ledger and source audit remain unchanged.

## First-class attachment

ACT-623 makes this policy a first-class member of the behavior specification aggregate for every participant kind.
It checks recorded ADR-013 episode history against the policy in `raes_conformance`.
Its evidence comprises the standalone and autonomous-profile fixtures and `implementations/python/tests/test_issue_309_act_623_participant_episode_structure.py`.
It introduces no external derivation, so the ledger remains unchanged.
