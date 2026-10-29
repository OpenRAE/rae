# Converting legacy mixed control to a finite script

Issue #1363 adds the reusable mixed-control form of
[ADR-110](../decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md)
and [MC-01 to MC-09](../../specs/formal/participant-semantics/reusable-mixed-control.md).
This record covers one explicit authoring conversion. The
[adoption contract](reusable-mixed-control.md) stays the producer and reader
boundary, and nothing here changes it.

## Lineages and transformation

| Field | Value |
| --- | --- |
| Source lineage | Legacy `MixedControlParticipantOperation` (no `semantics`) under `sdl-authoring-input-v1` |
| Target lineage | `mixed-control-policy-occurrence/rev1` with `form: finite-script`, under the same authoring contract |
| Transformation type | Assisted: the converter is deterministic, and the author publishes the output |
| Operation profile | `convert-mixed-control-finite-script/v1` |
| Rollback | None needed: the source is never edited and stays valid under its original meaning |

Converting to a `reusable-policy` always changes the permitted trace set. It
needs an explicit author decision, so no converter offers it.

## Python entry point

```python
from raes.mixed_control_migration import migrate_mixed_control_to_finite_script

result = migrate_mixed_control_to_finite_script(source)  # unchanged legacy YAML text
if result.succeeded:
    converted = result.output  # validated rev1 scenario; publish it as a new artifact
else:
    diagnostics = result.report.diagnostics  # every refusal code with its JSON pointer
```

The function accepts only source that passes legacy semantic validation. It
never edits the source and never emits partial output. A source with no legacy
declaration, including rev1 input, comes back unchanged.

## Preservation rules

Each legacy transition becomes one permitted transition with the same id, kind,
states, window, and evidence, plus one script step in effective-order order.
The step pins the exact expected state revision and the window `[e, e]` of the
legacy effective order `e`. A step whose transition named a proposal points
`target_step_ref` at that proposal's step. A cancellation of a proposal also
narrows its step with `target_kind: proposal`. A direction edge gets
`target_kinds: [proposal]`, because legacy direction always names a proposal.
Intervention, override, and cancellation edges keep their full MC-05 target
set, which equals what the legacy form admitted. Controller states, policy
revision, order strategy, dispositions, and the initial state are copied.

Legacy validation makes a linked transition the next accepted application
after its proposal. So each converted link resolves a live, unresolved
proposal, and the script admits exactly the legacy trace. The
[bounded differential test](../../implementations/python/tests/test_issue_1363_mixed_control_migration.py)
checks this for every attempt sequence up to one step past each fixture's
script.

## Ambiguous and lossy cases

The converter reports every applicable refusal, each with its JSON pointer.

| Migration-contract case | Code | Trigger |
| --- | --- | --- |
| Approval or direction changes controller | `controller-change-requires-handoff` | A non-handoff transition whose resolved controllers differ |
| Same rule, converse | `handoff-without-controller-change` | A handoff whose states differ only as raw strings, such as `self` and the participant's own agent id |
| Acting-source and destination-authority joins disagree | `source-destination-authority-disagreement` | A control-bearing delivery whose source and destination states differ in controller or scope |
| Order treated as a tick | `order-time-mapping-required` | Any control-bearing delivery; the legacy form compares order with ticks directly |
| Target or sequence intent ambiguous | `branching-sequence` | Two transitions share one expected state and revision, so more than one sequence can execute |
| Same case | `proposal-target-outside-kind-set` | `proposal_ref` on an intervention, handoff, or override |
| Policy identity conflated | `policy-revision-conflated` | Any control-bearing delivery; the legacy form requires equal revision strings |
| Not a valid source or result | `source-or-target-invalid` | Source that fails legacy validation, or output that fails rev1 validation, such as a transition into revoked authority |

Legacy `proposal_revision` always equals a state revision. The converted
policy binds proposal and decision revisions to 1 instead. The report lists
each source `proposal_revision` pointer under `affected_identities` rather than
copying the value.

## Validation

Run `raes semantic validate` on the published output. Keep the report, which
binds the source digest and the canonical target digest. Historical v1
occurrences, compiled snapshots, and runtime evidence keep their original
lineage and are never rewritten.
