# Participant tool profiles migration

Issue #301 (ACT-619) adds shared tool profiles.
Each behavior specification can serve as one profile.
Its `tool_affordances` bindings can select fewer participants.
Use `participant_refs` and `participant_role_refs` for this selection. The
[tool-profile decision](../decisions/issue-301-participant-tool-profiles.md)
records the design.

## What changes for existing documents

- Nothing changes for authoring documents without binding selectors. A binding
  without selectors applies to every selected participant. Existing checks remain.
- New instantiated, snapshot, materialized, and satisfiability-evidence
  documents carry both keys on each binding. Unused keys contain empty lists.
  Older closed readers reject these documents. The
  first `tool_affordances` default had the same effect.
- Authoring documents that use selectors fail closed in older parsers.
- `participant-decision-surface-v1` refuses a specification with a scoped
  binding. Use `participant-decision-surface-v2` for such specifications.

There is no automatic migrator.

## Folding per-role specifications into one profile

One profile can replace profiles that differ only in bindings and selectors.
All other profile fields must match.
These include `behavior_mode`, `autonomous_execution`, `mixed_control`, and `realization_profile_ref`.
These fields apply to every selected participant.

1. Combine the specification selectors, actions, and observation boundaries.
2. Give each former per-role binding its own key.
   Move its old profile selector onto the binding.
3. If the specification selects explicit participants, use explicit
   `participant_refs` on its bindings. A binding role selector reaches every
   participant with that role in the scenario. It fails when one of them is
   outside the specification.
4. Merge bindings that now have the same tool, actions, and boundaries into one
   binding with the combined selector. Selectors do not make two bindings
   different.
5. Update exposure policies, workflow steps, and other references that named a
   binding address under an old specification name.

## Versions and content pins

Bump `semantic_version` when a profile changes.
This is a convention, with no check for local or imported profiles.
ADR-053 pins a module's version.
A content pin requires an import digest, lockfile digest, `locked:` source, or OCI source.
Module imports do not check a profile's `semantic_version`.
The instantiated-snapshot digest pins profile content in evidence.

## Projection and private-reference corrections

New compilation resolves authored visibility references to canonical runtime addresses.
Use declared action names and qualified binding references in observation boundaries.
Remove duplicate runtime-address classifications for those same declarations.
Equal classifications combine into one item.
Conflicting classifications and ambiguous references are rejected.
Unknown information references retain their authored values.
Apply the same names to visibility transitions.
Prefer compiled addresses for known items in new runtime history.
Authored aliases receive the same visibility and evidence checks.
This includes action results, attribution, and outcome provenance.
Ambiguous aliases are rejected.
Stored historical evidence remains unchanged.

Each projected action and boundary must belong to the projected participant.
A shared specification cannot expand that participant's declarations.
A binding applies only at its declared observation boundaries.
A hidden binding at a matching boundary still prevents projection.

Authored participant and nested binding references cannot contain `__private` segments.
Reference exported declarations through their public module names.
Composition-generated private references remain valid inside the imported module.
Parameter values cannot create new private references.
