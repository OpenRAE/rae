# Migrating Participant Identity and Objective Assignment

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

Decision keys are JSON pointers (escape `~` as `~0` and `/` as `~1`). Every legacy
entity objective needs exactly one decision. Deterministic-only sources need no
context. The report binds source bytes, decision policy, and canonical target
digests. Preserve that report with the newly published artifact; the function
does not overwrite source files. Publish under a new artifact/version binding.

Missing or stale decisions, unknown or conflicting fields, unresolved participant
relation variables, dangling references,
and invalid action constraints produce no partial output. Imports and materialized
artifacts are refused: migrate source modules separately, then explicitly update
their version/digest bindings. Linked external-concept bindings need rebinding
to the new source/target digest through their existing admission workflow; this
function does not migrate linked artifacts. Historical compiled snapshots,
participant episodes, action histories, and stored evidence retain their original
schema identifiers and coordinates.

The explicit reader supports the pre-1338 authoring lineage indefinitely until
a separately reviewed deprecation notice establishes a removal window. This is
not a promise that canonical parsing accepts legacy fields. The
[deprecation record](../../specs/evolution/deprecation-records.yaml) records
field removal eligibility and source-reader retention.

## Author-task walkthrough and checks

Declare `agents: {harness: {}}` for one composite subject: no organization or
component inventory is required. Declare two keys with `affiliations: [team]`
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
with those four `tests/` paths. These are declaration/compiler checks, not proof
of live effects. Only a runtime action record identifies who actually acted;
an owner or assignee alone supplies no such evidence.

## Repository fixture disposition

The preflight inventories 21 active structured documents: 28 participant entity
bindings, 20 agent objectives, and seven entity objectives. Deterministic fields
use the mappings above. All seven entity objectives carry no action constraints;
their disposition is explicitly **owner-only**, preserving organizational intent
without inferring a participant. They occur in the formal-semantic-validation
valid/invalid corpus and the hospital, port-authority, reconciliation v1/v2,
and satcom scenarios. The hospital's two `ransom-crew` participants stay distinct.

The remaining documents are the minimal scenario, single-objective task,
parallel-objective workflow, observational study, timed-run, and action-contract
library templates; the enterprise participant scenario; the external-concept
autonomous subject fixture; and valid/invalid mixed-control, participant-inject,
and participant-relationship fixtures. Inline tests are migrated alongside them.
Historical audit specimens remain unchanged as evidence of the audited model.
The two original formal-validation fixtures also remain byte-for-byte historical
inputs. The current corpus uses separately versioned `participant-identity-v2`
successors with explicit ownership; the positive fixture also uses canonical
`compute` spelling. New evidence releases replay those successors without
rewriting historical snapshots, analyses, or release pins.

The hospital, port, and satcom examples now declare their existing action intent
as portable abstract action contracts, with explicit independent-authorization
preconditions and intended-effect subjects. This is an authored example update,
not an automatic migration rule: the migrator still refuses undeclared actions.
These contracts claim no backend procedure, successful effect, or authority.
