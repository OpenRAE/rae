# ADR-109: Participant Identity, Affiliation, and Objective Assignment

## Status

accepted

## Date

2026-09-21

## Classification

Classification: FM2

Required artifacts: the [normative contract and clause matrix](../../../specs/sdl/participant-identity.md),
closed published SDL schemas, cross-stage differential tests, and the
[explicit migration guide](../../migration/participant-identity.md).
No artifacts are waived.

## Context

Issue #1338 implements the identity/assignment slice of the
[participant audit](../../research/participant-identity/audit.md). Mandatory
`Agent.entity` conflated identity and affiliation; `Objective.agent/entity`
conflated participant assignment and organizational ownership. Entity objectives
also bypassed action-contract validation. The [preflight](../issue-1338-participant-identity-assignment-preflight.md)
records the inventory, rejected alternatives, security gates, and boundaries.

## Decision

The key in `agents` identifies one author-designated autonomous subject. It
may denote a composite system without declaring its components. RAES neither
tests an autonomy threshold nor derives identity from organization, role,
implementation, executable process, or runtime episode.

Optional `affiliations` reference organizations; optional participant `role`
overrides inherited role. Only a single affiliation supplies a fallback role.
Shared affiliation never merges participants or supplies assignment, authority,
observation access, or attribution.

Objectives have independent optional `owner` (entity) and
`assigned_participant` (participant) references, with at least one required.
Both may be present. Actions always reference global action contracts and, when
assigned, must also occur in the participant's declared action set. An unassigned
objective remains organizational intent, not runtime work. Beneficiary is not
introduced and must not be inferred from owner, target, or success subject.

Relationship objective references and autonomous objective evaluation follow
explicit assignment only. Effective-role consumers share one resolver.
Compiled projections label affiliation, role, owner, and assignment separately;
the overloaded objective actor projection is removed. Runtime actor attribution
remains in action/episode/history contracts and is not manufactured from intent.

This decision amends the identity/role clauses of ADR-020 and the exclusive
objective-actor clause of ADR-002, with in-band #1338 amendment records and
updated acceptance-content pins under ADR-059. Unaffected decisions, including
ADR-022 and ADR-067, remain unchanged. The current field-level rules are
specified by the linked normative contract. ACT-613 is not activated by this
requirement-free delivery slice. The decision and amendments ship together with
the implementation in the reviewed delivery PR.

## Compatibility and consequences

Canonical parsing rejects legacy fields with migration guidance, never hidden
aliases. The explicit, source-preserving migrator maps deterministic relations
and requires digest-bound author decisions for organizational objectives.
Published draft schema lineages retain their identifiers and record their
changed hashes; historical compiled snapshots and runtime evidence are not
rewritten. The deprecation ledger states the source-reader support window.

This deliberately breaks obsolete authoring and internal compiler projections.
Authors gain unaffiliated/composite participants and owned-but-unassigned
objectives. Multiple affiliations without direct role have no inferred role.
No new beneficiary ontology, participant component graph, persistence store,
control-plane permission, runtime action, or implementation binding is added.

## Verification

The normative clause matrix names executable positive and negative checks for
parsing, schema shape, role resolution, action constraints, imports, variable
instantiation, editor navigation, compilation, authority, and migration.
Existing episode/history contracts remain authoritative for realized action
coordinates. A declaration of intent alone never constitutes evidence of action.
