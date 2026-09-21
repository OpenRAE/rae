# Participant Identity, Affiliation, and Objective Assignment

Status: **normative**. Decision: [ADR-109](../../docs/decisions/adrs/adr-109-participant-identity-and-objective-assignment.md).
Issue #1338; no requirement status transition is implied.

## Contract

PI-01. An `agents` map key MUST identify one author-designated autonomous
subject. It MAY represent a composite system. No component list, organization,
node, service, implementation selection, or measured autonomy threshold is
required. Distinct keys MUST remain distinct participants even when affiliated
with the same organization. Participant identity is not operating-system or
control-plane identity.

PI-02. `affiliations` is an optional list (default empty) of distinct declared,
flattened entity names. Affiliation MUST NOT imply objective assignment,
authority, shared knowledge, a beneficiary, or a component relation. A direct
optional `role` uses the existing `ExerciseRole` vocabulary. Whole-field
variables remain legal before instantiation and are revalidated afterward.

PI-03. All effective-role consumers MUST use the same rule. For participant P,
affiliations A, and entity-role function R:

```text
effective_role(P) = P.role                       if explicitly supplied
                  = R(the sole member of A)    if |A| = 1
                  = absent                     otherwise
```

No first-member selection, role union, or inference from actions/ownership is
permitted. A consumer requiring a role MUST fail closed on an absent or
unresolved role. Role selection is not an authority grant.

PI-04. An objective MUST have at least one nonempty `owner` or
`assigned_participant`; both MAY be supplied. Owner references a flattened
entity name and means organizational responsibility. Assignment references an
`agents` key and means authored intent to pursue. Neither denotes the actor of
an observed event. Beneficiary has no field in this contract and MUST NOT be
inferred from either relation, targets, or success subjects.

PI-05. Every objective action MUST reference a declared `action_contracts` key.
If assigned to P, objective actions MUST be a subset of P.actions. Without
assignment, declared constraints remain valid organizational intent: they do
not create a participant, evaluation authority, or action occurrence.

PI-06. A participant relationship's `objective_refs` MUST name objectives
explicitly assigned to a relationship endpoint. Common affiliation or ownership
is insufficient. Autonomous declared-objective evaluation MUST name an objective
assigned to a selected participant. Non-evaluating participant modes MUST NOT
receive objective assignments. Incumbent action, evaluation, target, backend,
and control-plane admission gates still apply. A participant MUST NOT be owned
by multiple autonomous behavior specifications, including overlaps introduced
by role selectors; conflict validation and compilation use the same selection.

PI-07. Imports MUST namespace affiliation, owner, assignment, and action
constraints through their respective section maps. Variation slots are
`objectives.owner` and `objectives.assigned_participant`; old slots are rejected.
Parser, instantiation, editor references, validation, and compiler projections
MUST agree. Normalized AFFILIATION, OWNER, ASSIGNMENT, and ACTION_CONSTRAINT
references retain distinct meanings; none adds a planner dependency role.

PI-08. Compilation MUST preserve participant name/address independently of
affiliation. Objective projection carries `owner_name`,
`assigned_participant_name`, and `assigned_participant_address`, never overloaded
`actor_type/actor_name`. Realized actor attribution remains governed by existing
participant action/episode/history records. Assignment MUST NOT be copied into
such a record as proof of action; observed actions MUST NOT rewrite assignment.

PI-09. Canonical readers MUST reject `Agent.entity`, `Objective.agent`, and
`Objective.entity` with migration guidance. The [migration](../../docs/migration/participant-identity.md)
creates a new artifact or refuses atomically. It MUST NOT guess assignment from
affiliation, drop conflicting fields, or rewrite stored historical evidence.

## Conformance and clause-to-test matrix

Paths below are relative to `implementations/python/tests/`. Parameterized tests
include positive and negative cases; model/schema and parser/compiler comparisons
are differential evidence, not claims of live backend execution.

| Clauses | Executable evidence |
| --- | --- |
| PI-01, PI-02, PI-03 | `test_issue_1338_participant_identity.py`: composite declaration, shared affiliation, direct/inherited/multiple-affiliation roles, duplicate/dangling refs, role-selected compiler projection |
| PI-04, PI-05 | Same file: model/schema differential relation shape; assigned/unassigned objectives; dangling owner/assignment; global and participant-local action checks |
| PI-06 | `test_issue_1338_identity_authority.py`, including `test_autonomous_ownership_conflicts_include_role_selected_participants`; relationship endpoint tests in `test_issue_1338_participant_identity.py` |
| PI-07 | `test_issue_1338_identity_stages.py`: namespaced imports, variable revalidation, editor completion/navigation; `test_sdl_variation_points.py` |
| PI-08 | Compiler assertions in `test_issue_1338_participant_identity.py`; unchanged action/episode boundary covered by `test_runtime_control_plane.py` |
| PI-09 | `test_issue_1338_identity_migration.py`: deterministic migration, explicit owner/assignment decisions, stale/missing context, conflicts, invalid actions, imports, idempotence |

`test_issue_1338_identity_evidence.py` locks the accepted decision amendments and
historical fixture retention; `test_issue_1338_identity_examples.py` checks the
published scenarios' declared action constraints and honest abstract contracts.

The human reference catalog and machine parity expectations enumerate the exact
reference fields. Published schemas under `contracts/schemas/` govern portable
shape; semantic constraints above are not replaced by schema acceptance.
