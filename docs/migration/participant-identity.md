<a id="migrating-participant-identity-and-objective-assignment"></a>

# Migrate participant identity and objective assignment

## Versions and purpose

Source: `Pre-1338 authoring with Agent.entity and Objective.agent/entity`.
Target: `Current affiliations, owner, and assigned_participant fields`.

## Before you start

Use RAES 11.0.2 and retain the exact legacy source bytes.
Inventory every organizational objective before creating its source-bound decisions.
Obtain the author's decision about ownership and assignment.
Affiliation cannot supply that decision.
Convert source modules separately. Imported and materialized artifacts are not supported inputs.
The helper returns a new in-memory artifact.
It does not change source files or runtime state.

Issue #1338 removes the ambiguous canonical fields `Agent.entity` and
`Objective.agent/entity`. The `agents` section remains; its map key is identity.
See the [current contract](../../specs/sdl/participant-identity.md) and
[ADR-109](../decisions/adrs/adr-109-participant-identity-and-objective-assignment.md).

## Choose meaning before rewriting

| Legacy source | New source | Required decision |
| --- | --- | --- |
| `agents.P.entity: E` | `agents.P.affiliations: [E]` | Deterministic; single-affiliation role fallback preserves the prior role. |
| `objectives.O.agent: P` | `objectives.O.assigned_participant: P` | Deterministic; no owner is invented. |
| `objectives.O.entity: E` | `objectives.O.owner: E` | Explicit owner-only decision, or add an explicitly selected `assigned_participant`. Never choose from affiliated participants automatically. |

Actions now always reference declared action contracts. Assigned objectives
additionally constrain actions to those available to the selected participant.
Do not create a dummy participant or action declaration merely to pass migration.
An invalid legacy label needs an authoring correction and a new source digest.

## Explicit Python migration

```python
from raes.participant_migration import (
    ParticipantIdentityMigrationContext,
    migrate_participant_identity,
)
from raes.semantic_revisions import source_byte_digest

# source is the unchanged legacy YAML text. This map records author decisions.
context = ParticipantIdentityMigrationContext(
    source_digest=source_byte_digest(source),
    entity_objectives={"/objectives/restore-service": None},  # owner only
    # Use a declared participant name instead of None for explicit assignment.
)
result = migrate_participant_identity(source, context=context)
if result.succeeded:
    canonical = result.output
else:
    diagnostics = result.report.diagnostics  # bounded codes and pointers
```

Decision keys are JSON pointers.
Escape `~` as `~0` and `/` as `~1`. Every legacy
entity objective needs exactly one decision. Deterministic-only sources need no
context. The report binds source bytes and decision policy.
It also binds canonical target digests. Preserve that report with the new published artifact.
The function does not overwrite source files. Publish under a new artifact/version binding.

The following failures produce no partial output:

- Missing or stale decisions.
- Unknown or conflicting fields.
- Unresolved participant relation variables.
- Dangling references or invalid action constraints.
 Imports and materialized
artifacts are refused: migrate source modules separately, then explicitly update
their version/digest bindings. Rebind linked external-concept bindings to the new source/target digest through their existing admission workflow.
This function does not migrate linked artifacts. Historical compiled snapshots,
participant episodes, action histories, and stored evidence retain their original
schema identifiers and coordinates.

The explicit reader supports the pre-1338 authoring lineage without a scheduled end.
A separately reviewed deprecation notice must establish any removal window. This is
not a promise that canonical parsing accepts legacy fields. The
[deprecation record](../../specs/evolution/deprecation-records.yaml) records
field removal eligibility and source-reader retention.

## Author-task walkthrough and checks

Declare `agents: {harness: {}}` for one composite subject.
No organization or component inventory is required. Declare two keys with `affiliations: [team]`
to retain two identities. Add `role: blue` to override the single-affiliation
fallback; two affiliations without direct role yield no effective role.

An objective with `owner: team` and valid success assertions is organizational
intent. Add `assigned_participant: harness` only when that subject is designated
to pursue it. A global action contract is required even before assignment;
assignment adds the participant action-subset check. Relationship and autonomous
evaluation references follow this explicit assignment, not `owner`.

The tests `test_issue_1338_participant_identity.py`,
`test_issue_1338_identity_stages.py`, `test_issue_1338_identity_authority.py`, and
`test_issue_1338_identity_migration.py` exercise these author tasks and their
negative cases. From `implementations/python`, run `.venv/bin/python -m pytest`
with those four `tests/` paths. These checks cover declarations and compilation. They do not prove live effects.
Only a runtime action record identifies who actually acted.
An owner or assignee alone supplies no such evidence.

## Repository fixture disposition

Read the [issue 1338 fixture inventory](../explain/reference/participant-identity-migration-history.md).
It retains the delivery's counts, example decisions, and preserved historical fixtures.
Those decisions are not automatic conversion rules.

## Check the result and recover

Success returns a validated artifact and a report binding the source, decisions, and target digest.
On refusal, read the bounded diagnostic and pointer.
Correct the source or decisions.
Create a fresh context.
Keep the original source and linked evidence. Rebind sidecars through their owning admission workflow.
Save successful output under a new artifact/version binding.
No backend cleanup is needed for the helper.
Read [participant identity semantics](../../specs/sdl/participant-identity.md)
and [participant-control explanation](../public/participant-control-explanation.md).
