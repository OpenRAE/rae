# Participant identity migration inventory

This record describes the fixture changes in issue #1338.
Its counts apply to that delivery. They are not current repository counts.
Use [migrate identity and assignment](../../migration/participant-identity.md) for current conversion.
The helper does not infer the example authors' decisions recorded here.

## Repository fixture disposition

The preflight found 21 active documents.
Each held structured data.
They contained 28 `Agent.entity` bindings.
They held 20 `Objective.agent` objectives and seven `Objective.entity` objectives.
Deterministic fields use the [migration mappings](../../migration/participant-identity.md#choose-meaning-before-rewriting).

All seven `Objective.entity` objectives had no action constraints.
Their explicit disposition was **owner-only**.
This kept the organization's intent.
It did not infer a participant.
These objectives occurred in the formal-semantic-validation valid/invalid corpus.
They also occurred in the hospital, port-authority, reconciliation v1/v2, and satcom scenarios.
The hospital's two `ransom-crew` participants remained distinct.

The remaining documents included six templates:

- The minimal scenario.
- The single-objective task.
- The parallel-objective workflow.
- The observational study.
- The timed-run.
- The action-contract library.

The inventory also included the enterprise participant scenario.
It included the external-concept autonomous subject fixture.
It covered valid and invalid mixed-control, participant-inject, and participant-relationship fixtures.
Inline tests changed with those documents.

Historical audit specimens stayed unchanged.
They remain evidence of the model that was audited.
The two original formal-validation fixtures also stayed byte-for-byte unchanged.
The current corpus uses separately versioned `participant-identity-v2` successors.
Those successors declare ownership explicitly.
The positive fixture also uses canonical `compute` spelling.
New evidence releases replay the successors.
They do not rewrite historical snapshots, analyses, or release pins.

The hospital, port, and satcom examples kept their existing action intent.
They now express it as portable abstract action contracts.
Each contract has explicit independent-authorization preconditions.
It also has intended-effect subjects.
Authors made these example edits explicitly.
The migration rules do not make those choices automatically.
The migrator still refuses actions that are not declared.
The contracts claim no backend procedure, successful effect, or authority.
