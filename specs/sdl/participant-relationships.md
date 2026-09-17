# Participant Relationships

Status: normative. Requirement: ACT-612. This specification extends the existing
SDL `relationships` graph under ADR-020/022/052/067 and the sparse-description
principles of ADR-105. It defines authored relationships, not runtime occurrences.

## Shape and meaning

A participant relationship MUST use `type: participant` and a closed
`participant` detail containing `kind`. Its map key supplies stable identity.
`source` and `target` MUST resolve unambiguously to distinct `agents` declarations.
Bare and `agents.<name>` references use the existing declaration index; ambiguous
bare names require qualification. Entities, roles, accounts and implementation
identities MUST NOT substitute for participant endpoints.

| Kind | Meaning from source to target |
| --- | --- |
| `coordination` | Intent to synchronize actions or state with the target. |
| `delegation` | Assignment of responsibility for work to the target. |
| `cooperation` | Intent to pursue aligned work or outcomes with the target. |
| `competition` | Intent to pursue competing work or outcomes with the target. |
| `supervision` | Intent to oversee the target's work. |

These five terms are semantic operators, not backend implementation identities.
The graph remains directed for every kind. A reciprocal declaration MUST be
explicit. Cycles and multiple kinds between the same participants are permitted;
the relationship graph is not an execution dependency graph.

The detail and `type: participant` MUST occur together. A participant edge MUST
NOT carry nonempty generic `properties` or another typed relationship detail.
Unknown detail fields and kinds MUST be rejected. Existing nonparticipant edges
retain their meanings and endpoint rules.

## Sparse descriptions and refinements

Kind and endpoints are sufficient for a complete abstract relationship.
Implementations MUST NOT require machine descriptions, action implementations,
control policies, evidence, validity intervals, or observations merely because
a relationship is declared. Omitted refinements make no additional statement.
They are not assertions that all actions, goals, scopes or observations apply.

Authors MAY refine a relationship through the following reference lists.
All supplied references MUST resolve in their owning sections. Lists MUST
contain nonblank unique strings and MUST reject duplicate canonical references
written with different aliases, including authority and scope references.

| Field | Refinement and agreement rule |
| --- | --- |
| `source_action_refs` | Declared action contracts available to the source participant. |
| `target_action_refs` | Declared action contracts available to the target participant. |
| `objective_refs` | Declared objectives owned by an endpoint participant or its entity. The relation kind states the author's alignment/competition intent; this is not a proof of objective equivalence or opposition. |
| `behavior_specification_refs` | Existing behavior aggregates including at least one endpoint, directly or through its role. Outcome, realization and evidence refinements remain in those aggregates. |
| `authority_basis_refs` | Existing authority anchors of the source. A relationship cannot create an authority anchor by naming it. |
| `scope_refs` | Existing operating-scope elements within both endpoints' declared scopes. |
| `observation_boundary_refs` | Existing observation boundaries already available to the source; no new visibility is granted. |

When both action lists refine coordination, every source action MUST have
SEM-209 coordination interactions covering the listed target actions. An
interaction explicitly targeting a participant MUST target the relationship's
target. Resource-targeted coordination remains permitted: authors need not
invent a participant target for a shared-resource interaction. Cooperation and
competition MUST NOT be rewritten as coordination, contention or interference.

Reference variables MAY remain unresolved in authoring. Instantiation MUST
resolve them and repeat semantic validation. An unresolved reference cannot
authorize compilation or weaken an explicitly supplied constraint.

## Optional control binding

Delegation and supervision MAY name `control_specification_ref`, a reference to
an existing behavior specification with an ACT-617 `mixed_control` declaration.
Other relationship kinds MUST NOT use this field. The selected policy MUST
agree with direction and include an active controller state:

- Supervision: the target is the controlled participant and the source is its
  controller.
- Delegation: the source is the controlled participant and the target is its
  delegate controller.

If `scope_refs` also refines the relationship, the selected scope MUST be
covered by the policy's active states for that controller. A participant's
broader operating scope cannot enlarge the selected control policy.

This binding describes the policy relevant to the relationship. It does not
activate a controller state, hand off control, approve a proposal, copy a
credential, widen authority or bypass a runtime check. Policy validity,
authority/scope, ordering, evidence and transition rules remain governed by
ACT-617. A policy reference also does not claim that a transition occurred.

Without this refinement, delegation describes responsibility and supervision
describes oversight intent. Neither implies operational controller authority.
Supervision is independent of the `human-supervised` decision mode. Participant
delegation is independent of backend materialization delegation.

## Composition, compilation and evidence

Module composition MUST rewrite endpoint and refinement references through
the existing symbol maps. Imported action interaction targets, related actions
and shared-state references MUST retain the same namespace. Instantiation and
compilation MUST preserve each validated relationship's identity, direction,
kind and selected refinements.

Relationship declarations MUST NOT create actions, backend resources, control
operations, observation demand, collection, retention or export obligations.
Realized claims use the existing action, joint-action, shared-state, control,
observation and outcome contracts with their selected evidence requirements.
An authored edge, schema pass or capability declaration is not evidence that a
relationship was realized.

## Reference implementation evidence

The Python reference implementation checks shape in `Relationship` and
`ParticipantRelationship`, and semantic agreement in `SemanticValidator`.
Compilation preserves declarations in the existing `RuntimeModel.relationship_specs`
metadata. Those dictionaries are not executable authority or a second runtime
graph. No new scheduler, control API, occurrence family or persistence store is
introduced by this contract.

The `test_act_612_participant_relationships.py` and
`test_act_612_relationship_integration.py` suites exercise sparse declarations,
selected refinements, rejection boundaries, composition, instantiation,
compilation and schema shape. They establish declarative support, not a claim
of realized cooperation, fair competition or successful control transfer.
