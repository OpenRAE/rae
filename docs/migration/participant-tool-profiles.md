# Participant tool profiles migration

Issue #301 (ACT-619) lets one behavior specification act as a reusable tool
profile. Each `tool_affordances` binding may now narrow the specification's
participants with `participant_refs` and `participant_role_refs`. The
[tool-profile decision](../decisions/issue-301-participant-tool-profiles.md)
records the design.

## What changes for existing documents

- Nothing changes for authoring documents without binding selectors. A binding
  without selectors still applies to every participant its specification
  selects, and every existing check is unchanged.
- New instantiated, snapshot, materialized, and satisfiability-evidence
  documents carry the two keys on every tool-affordance binding, empty when
  unused. Older readers that reject unknown keys reject those documents. The
  first `tool_affordances` default had the same effect.
- Authoring documents that use selectors fail closed in older parsers.
- `participant-decision-surface-v1` refuses a specification with a scoped
  binding. Use `participant-decision-surface-v2` for such specifications.

There is no automatic migrator.

## Folding per-role specifications into one profile

You may fold specifications that differ only in their bindings and selection
into one specification whose bindings carry selectors. Fold them only when
they share `behavior_mode`, `autonomous_execution`, `mixed_control`, and
`realization_profile_ref`. Those fields apply to every participant a
specification selects.

1. Combine the specification selectors, actions, and observation boundaries.
2. Give each former per-role binding its own key, and move the old
   specification's selector onto the binding.
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

Bump `semantic_version` whenever a profile changes, as a convention. Nothing
checks it, for imported or local profiles. ADR-053 pins a module's version. It
pins the module bytes only under an import digest, a lockfile digest, or a
`locked:` or OCI source, and it never reads a profile's `semantic_version`.
Evidence pins a profile's content through the instantiated-snapshot digest.
