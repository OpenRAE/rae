# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the ACES SDL
ecosystem. ADRs capture significant architectural decisions along with their
context, rationale, and consequences.

## Format

We use [MADR](https://adr.github.io/madr/) (Markdown Any Decision Records).
Each ADR includes:

- **Status**: `proposed`, `accepted`, `deprecated`, or `superseded by ADR-XXX`
- **Context**: The problem or situation driving the decision
- **Decision**: What we chose and why
- **Alternatives Considered**: Credible rejected options and why they were not
  chosen
- **Consequences**: Trade-offs (positive, negative, risks)

Use [`TEMPLATE.md`](TEMPLATE.md) when drafting a new ADR.

## Principles

- An **accepted** ADR's content is **pinned** and citable. Its acceptance (or
  last-amendment) content hash is recorded in
  [`adr-index.yaml`](adr-index.yaml) and enforced by the `policy` nox session
  (`tools/check_adr_immutability.py`). A substantive change to an accepted ADR
  is legitimate only as a new **superseding** ADR, or as a recorded **amendment**
  (a `## Amendments` row plus an updated pin, in the same change). Editorial-only
  fixes (typos, formatting) also record a one-line amendment row — the gate
  cannot tell editorial from substantive, so every canonical-content change is
  recorded. See
  [ADR-059](adr-059-adr-amendment-policy-and-pin-gate.md) for the full policy.
- `proposed` ADRs are still being decided and may change freely;
  `superseded`/`deprecated` ADRs leave the pinned set (the citable decision has
  moved to the replacing ADR).
- ADRs are **numbered sequentially** in landing order and never reused. The ADR
  date records when the decision was made; it may differ from the landing order
  when a decision is backfilled or merged later.
- ADRs are **versioned with code** and live in the repo.

## Index

```{toctree}
:hidden:

TEMPLATE
adr-000-use-adrs
adr-001-scenario-description-language
adr-002-declarative-sdl-objectives
adr-003-workflows-targetable-subobjects-and-enum-variables
adr-004-sdl-runtime-layer
adr-005-control-flow-primitives
adr-006-workflow-control-language-redesign
adr-007-lightweight-formal-methods-policy
adr-008-processor-layer-and-execution-artifact-boundaries
adr-009-normative-artifact-authority-and-repository-structure
adr-010-repository-realignment-order-and-compatibility-policy
adr-011-narrow-end-to-end-mvp-validation
adr-012-shared-concept-authority-and-aces-extension-discipline
adr-013-participant-episode-lifecycle-boundaries
adr-014-nox-as-canonical-verification-graph
adr-015-sdl-processor-layering-and-source-file-size-cap
adr-016-semantic-layer-scope-and-coverage-model
adr-017-conversation-surface-hardening
adr-018-classification-based-assurance-policy
adr-019-normative-authority-boundary-manifest
adr-020-declarative-participant-framing-boundaries
adr-021-falsification-first-claim-evidence-gate
adr-022-participant-behavior-and-interaction-semantics
adr-023-container-image-build-provenance-surface
adr-024-local-identity-inventory-surface
adr-025-container-network-realization-surface
adr-026-application-http-surface-inventory
adr-027-container-init-reaper-runtime-surface
adr-028-container-seccomp-security-options-surface
adr-029-database-logical-state-runtime-surface
adr-030-process-scoped-linux-capability-policy
adr-031-ssh-server-configuration-surface
adr-032-directory-domain-identity-runtime-surface
adr-033-scenario-delivery-boundary-for-runtime-node-state
adr-034-runtime-software-component-inventory
adr-035-service-manager-unit-state-runtime-surface
adr-036-sdl-processor-runtime-module-boundaries
adr-037-runtime-file-service-and-filesystem-presence-semantics
adr-038-runtime-mail-service-logical-state
adr-039-dns-service-runtime-inventory
adr-040-security-monitoring-manager-runtime-inventory
adr-041-participant-implementation-manifest-and-provenance
adr-042-network-sensor-runtime-monitoring
adr-043-runtime-service-listener-surface
adr-044-network-detection-engine-runtime-inventory
adr-045-security-monitoring-detection-definition-semantics
adr-046-app-authorization-runtime-inventory
adr-047-scheduled-job-runtime-inventory
adr-048-datastore-service-runtime-inventory
adr-049-platform-application-runtime-inventory
adr-050-forwarding-agent-runtime-inventory
adr-051-orchestration-authority-runtime-inventory
adr-052-typed-runtime-relationship-subtypes
adr-053-sdl-module-composition-for-inventory-backed-scenarios
adr-054-participant-runtime-observable-lifecycle
adr-055-experiment-core-contract-boundary
adr-056-runtime-observed-values-and-credential-posture
adr-057-runtime-secret-name-classifier-boundaries
adr-058-datastore-node-engine-provenance-and-endpoints
adr-059-adr-amendment-policy-and-pin-gate
adr-060-participant-backend-facing-contract-surface
adr-061-published-schema-evolution-policy
adr-062-concept-authority-catalog-governance-gate
adr-063-reference-emulation-backend
adr-064-experiment-evidence-and-measure-contract-boundary
adr-065-experiment-run-provenance-contract-boundary
adr-066-observability-evidence-plane-separation
adr-067-participant-behavior-model
adr-068-experiment-trials-replication-and-replay-claims
adr-069-cage-2-replication-architecture
adr-070-realization-envelope-semantics
adr-071-reusable-asset-trust-and-integrity-policy
adr-072-validation-and-admission-profiles
adr-073-scoring-reward-language-scope
adr-074-experiment-authoring-input-contract-boundary
adr-075-ecosystem-versioning-deprecation-and-migration-governance
adr-076-portable-sdl-identifiers-and-canonical-addresses
adr-077-associated-artifact-manifest-boundary
adr-078-closed-sdl-phase-contracts-and-portable-derivation-evidence
adr-079-backend-neutral-proposition-and-truth-semantics
adr-080-revision-pinned-sdl-lineage-and-provenance-ledger
adr-081-behavioral-relation-taxonomy-and-claim-discipline
adr-082-authored-identity-domain-topology
adr-083-participant-tool-decision-surface-and-exposure-semantics
adr-084-scenario-variation-and-deterministic-trial-realization
adr-085-participant-information-flow-and-control
adr-086-governed-whole-scenario-satisfiability
adr-087-enterprise-identity-and-deployment-tenancy-authoring
adr-088-initial-service-state-and-native-materialization
adr-090-shared-time-domain-clock-and-progression-authority
adr-091-portable-time-capability-control-and-provenance-contracts
adr-092-autonomous-benign-participants-under-shared-time
adr-093-raes-rename-and-compatibility-boundaries
adr-094-authoritative-cross-plane-experiment-bindings
adr-095-participant-decision-epoch-state-cut-and-delivery-semantics
adr-096-identity-cutover-and-historical-record-boundary
adr-097-scoped-participant-resource-budgets-and-shared-service-fairness
adr-098-portable-artifact-requirement-satisfaction
adr-099-participant-relative-predicate-opacity
adr-100-participant-crossing-bisimulation
adr-101-adversarial-participant-flow-control
adr-105-recursive-partial-description-semantics
adr-106-developer-package-and-artifact-management
adr-107-artifact-promotion-and-release-admission
adr-108-modular-participant-control-and-governed-effects
```

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [000](adr-000-use-adrs.md) | Use Architecture Decision Records | accepted | 2026-03-20 |
| [001](adr-001-scenario-description-language.md) | Scenario Description Language (SDL) | accepted | 2026-03-29 |
| [002](adr-002-declarative-sdl-objectives.md) | Declarative Experiment Objectives in the SDL | accepted | 2026-03-29 |
| [003](adr-003-workflows-targetable-subobjects-and-enum-variables.md) | Workflows, Targetable Sub-Objects, and Leaf Enum Variables in the SDL | accepted | 2026-03-29 |
| [004](adr-004-sdl-runtime-layer.md) | SDL Runtime Layer | accepted | 2026-03-30 |
| [005](adr-005-control-flow-primitives.md) | Control Flow Primitives in the SDL | superseded by ADR-006 | 2026-04-01 |
| [006](adr-006-workflow-control-language-redesign.md) | Workflow Control-Language Redesign | accepted | 2026-04-01 |
| [007](adr-007-lightweight-formal-methods-policy.md) | Lightweight Formal Methods Policy for Semantic Systems | accepted | 2026-04-01 |
| [008](adr-008-processor-layer-and-execution-artifact-boundaries.md) | Processor Layer and Execution Artifact Boundaries | accepted | 2026-04-04 |
| [009](adr-009-normative-artifact-authority-and-repository-structure.md) | Normative Artifact Authority and Repository Structure | accepted | 2026-04-04 |
| [010](adr-010-repository-realignment-order-and-compatibility-policy.md) | Repository Realignment Order and Compatibility Policy | accepted | 2026-04-04 |
| [011](adr-011-narrow-end-to-end-mvp-validation.md) | Narrow End-to-End MVP Validation | accepted | 2026-04-04 |
| [012](adr-012-shared-concept-authority-and-aces-extension-discipline.md) | Shared Concept Authority and ACES Extension Discipline | accepted | 2026-04-05 |
| [013](adr-013-participant-episode-lifecycle-boundaries.md) | Participant Episode Lifecycle Boundaries | accepted | 2026-04-11 |
| [014](adr-014-nox-as-canonical-verification-graph.md) | nox as the Canonical Verification Graph | accepted | 2026-05-09 |
| [015](adr-015-sdl-processor-layering-and-source-file-size-cap.md) | SDL-Processor Layering and Source-File Size Cap | accepted | 2026-05-10 |
| [016](adr-016-semantic-layer-scope-and-coverage-model.md) | Semantic Layer Scope and Coverage Model (SEM-200) | accepted | 2026-05-10 |
| [017](adr-017-conversation-surface-hardening.md) | Conversation Surface Hardening | accepted | 2026-05-17 |
| [018](adr-018-classification-based-assurance-policy.md) | Canonical Mapping for the Classification-Based Assurance Policy | accepted | 2026-05-17 |
| [019](adr-019-normative-authority-boundary-manifest.md) | Canonical Manifest for the Normative Artifact Authority Boundary | accepted | 2026-05-17 |
| [020](adr-020-declarative-participant-framing-boundaries.md) | Declarative Participant Framing Boundaries | accepted | 2026-05-18 |
| [021](adr-021-falsification-first-claim-evidence-gate.md) | Falsification-First Claim Evidence Gate | accepted | 2026-05-18 |
| [022](adr-022-participant-behavior-and-interaction-semantics.md) | Participant Behavior and Interaction Semantics | accepted | 2026-05-18 |
| [023](adr-023-container-image-build-provenance-surface.md) | Container Image Build Provenance Surface | accepted | 2026-05-21 |
| [024](adr-024-local-identity-inventory-surface.md) | Local Identity Inventory Surface | accepted | 2026-05-21 |
| [025](adr-025-container-network-realization-surface.md) | Container Network Realization Surface | accepted | 2026-05-21 |
| [026](adr-026-application-http-surface-inventory.md) | Application HTTP Surface Inventory | accepted | 2026-05-22 |
| [027](adr-027-container-init-reaper-runtime-surface.md) | Container Init/Reaper Runtime Surface | accepted | 2026-05-22 |
| [028](adr-028-container-seccomp-security-options-surface.md) | Container Seccomp and Security Options Surface | accepted | 2026-05-22 |
| [029](adr-029-database-logical-state-runtime-surface.md) | Database Logical-State Runtime Surface | accepted | 2026-05-22 |
| [030](adr-030-process-scoped-linux-capability-policy.md) | Process-Scoped Linux Capability Policy | accepted | 2026-05-23 |
| [031](adr-031-ssh-server-configuration-surface.md) | SSH Server Configuration Surface | accepted | 2026-05-23 |
| [032](adr-032-directory-domain-identity-runtime-surface.md) | Directory and Domain Identity Runtime Surface | accepted | 2026-05-24 |
| [033](adr-033-scenario-delivery-boundary-for-runtime-node-state.md) | Scenario/Delivery Boundary for Runtime Node State | accepted | 2026-05-24 |
| [034](adr-034-runtime-software-component-inventory.md) | Runtime Software Component Inventory | accepted | 2026-05-25 |
| [035](adr-035-service-manager-unit-state-runtime-surface.md) | Service-Manager Unit State Runtime Surface | accepted | 2026-05-26 |
| [036](adr-036-sdl-processor-runtime-module-boundaries.md) | SDL, Processor, Runtime Module Boundaries | accepted | 2026-05-26 |
| [037](adr-037-runtime-file-service-and-filesystem-presence-semantics.md) | Runtime File-Service and Filesystem Presence Semantics | accepted | 2026-05-26 |
| [038](adr-038-runtime-mail-service-logical-state.md) | Runtime Mail-Service Logical State | accepted | 2026-05-28 |
| [039](adr-039-dns-service-runtime-inventory.md) | DNS Service Runtime Inventory | accepted | 2026-05-28 |
| [040](adr-040-security-monitoring-manager-runtime-inventory.md) | Security-Monitoring Manager Runtime Inventory | accepted | 2026-05-29 |
| [041](adr-041-participant-implementation-manifest-and-provenance.md) | Participant Implementation Manifest and Provenance Surface | accepted | 2026-05-29 |
| [042](adr-042-network-sensor-runtime-monitoring.md) | Network Sensor Runtime Monitoring Posture | accepted | 2026-05-29 |
| [043](adr-043-runtime-service-listener-surface.md) | Generic Runtime Service Listener Surface | accepted | 2026-05-29 |
| [044](adr-044-network-detection-engine-runtime-inventory.md) | Network Detection Engine Runtime Inventory | accepted | 2026-05-29 |
| [045](adr-045-security-monitoring-detection-definition-semantics.md) | Security-Monitoring Detection Definition Semantics | accepted | 2026-05-29 |
| [046](adr-046-app-authorization-runtime-inventory.md) | Application-Internal Authorization Runtime Inventory | accepted | 2026-05-30 |
| [047](adr-047-scheduled-job-runtime-inventory.md) | Scheduled-Job Runtime Inventory | accepted | 2026-05-30 |
| [048](adr-048-datastore-service-runtime-inventory.md) | Datastore Service Runtime Inventory | accepted | 2026-05-30 |
| [049](adr-049-platform-application-runtime-inventory.md) | Platform Application Runtime Inventory | accepted | 2026-05-30 |
| [050](adr-050-forwarding-agent-runtime-inventory.md) | Forwarding Agent Runtime Inventory | accepted | 2026-05-30 |
| [051](adr-051-orchestration-authority-runtime-inventory.md) | Orchestration Authority Runtime Inventory | accepted | 2026-05-30 |
| [052](adr-052-typed-runtime-relationship-subtypes.md) | Typed Runtime Relationship Subtypes | accepted | 2026-05-30 |
| [053](adr-053-sdl-module-composition-for-inventory-backed-scenarios.md) | SDL Module Composition for Inventory-Backed Scenarios | accepted | 2026-06-03 |
| [054](adr-054-participant-runtime-observable-lifecycle.md) | Participant Runtime Observable Lifecycle | accepted | 2026-06-05 |
| [055](adr-055-experiment-core-contract-boundary.md) | Experiment Core Contract Boundary | accepted | 2026-05-26 |
| [056](adr-056-runtime-observed-values-and-credential-posture.md) | Runtime Observed Values and Credential Posture | accepted | 2026-06-05 |
| [057](adr-057-runtime-secret-name-classifier-boundaries.md) | Runtime Scenario Value Realizability and Explicit Redaction | accepted | 2026-06-06 |
| [058](adr-058-datastore-node-engine-provenance-and-endpoints.md) | Datastore Node Engine Provenance and Endpoints | accepted | 2026-06-07 |
| [059](adr-059-adr-amendment-policy-and-pin-gate.md) | ADR Amendment Policy and Acceptance-Content Pin Gate | accepted | 2026-06-10 |
| [060](adr-060-participant-backend-facing-contract-surface.md) | Participant Backend-Facing Contract Surface | proposed | 2026-06-11 |
| [061](adr-061-published-schema-evolution-policy.md) | Published Schema Evolution Policy | accepted | 2026-06-14 |
| [062](adr-062-concept-authority-catalog-governance-gate.md) | Concept-Authority Catalog Governance Gate | accepted | 2026-06-14 |
| [063](adr-063-reference-emulation-backend.md) | Reference Emulation Backend | accepted | 2026-06-20 |
| [064](adr-064-experiment-evidence-and-measure-contract-boundary.md) | Experiment Evidence and Measure Contract Boundary | accepted | 2026-06-21 |
| [065](adr-065-experiment-run-provenance-contract-boundary.md) | Experiment Run Provenance Contract Boundary | accepted | 2026-06-22 |
| [066](adr-066-observability-evidence-plane-separation.md) | Observability and Evidence Plane Separation | accepted | 2026-06-23 |
| [067](adr-067-participant-behavior-model.md) | Participant Behavior Model | proposed | 2026-06-23 |
| [068](adr-068-experiment-trials-replication-and-replay-claims.md) | Experiment Trials, Replication, and Replay Claims | accepted | 2026-06-25 |
| [069](adr-069-cage-2-replication-architecture.md) | CAGE-2 Replication Architecture | accepted | 2026-07-01 |
| [070](adr-070-realization-envelope-semantics.md) | Realization Envelope Semantics | accepted | 2026-07-04 |
| [071](adr-071-reusable-asset-trust-and-integrity-policy.md) | Reusable Asset Trust and Integrity Policy | accepted | 2026-07-05 |
| [072](adr-072-validation-and-admission-profiles.md) | Validation and Admission Profiles | proposed | 2026-07-05 |
| [073](adr-073-scoring-reward-language-scope.md) | Scoring and Reward Language Scope in the SDL | accepted | 2026-07-05 |
| [074](adr-074-experiment-authoring-input-contract-boundary.md) | Experiment Authoring-Input Contract Boundary | accepted | 2026-07-08 |
| [075](adr-075-ecosystem-versioning-deprecation-and-migration-governance.md) | Ecosystem Versioning, Deprecation, and Migration Governance | proposed | 2026-07-11 |
| [076](adr-076-portable-sdl-identifiers-and-canonical-addresses.md) | Portable SDL Identifiers and Canonical Addresses | accepted | 2026-07-11 |
| [077](adr-077-associated-artifact-manifest-boundary.md) | Associated Artifact Manifest Boundary | accepted | 2026-07-12 |
| [078](adr-078-closed-sdl-phase-contracts-and-portable-derivation-evidence.md) | Closed SDL Phase Contracts and Portable Derivation Evidence | accepted | 2026-07-12 |
| [079](adr-079-backend-neutral-proposition-and-truth-semantics.md) | Backend-Neutral Proposition and Truth Semantics | accepted | 2026-07-12 |
| [080](adr-080-revision-pinned-sdl-lineage-and-provenance-ledger.md) | Revision-Pinned SDL Lineage And Provenance Ledger | accepted | 2026-07-12 |
| [081](adr-081-behavioral-relation-taxonomy-and-claim-discipline.md) | Behavioral-Relation Taxonomy And Claim Discipline | accepted | 2026-07-13 |
| [082](adr-082-authored-identity-domain-topology.md) | Authored Identity-Domain Topology | accepted | 2026-07-13 |
| [083](adr-083-participant-tool-decision-surface-and-exposure-semantics.md) | Participant Tool, Decision-Surface, and Exposure Semantics | proposed | 2026-07-14 |
| [084](adr-084-scenario-variation-and-deterministic-trial-realization.md) | Scenario Variation And Deterministic Trial Realization | accepted | 2026-07-15 |
| [085](adr-085-participant-information-flow-and-control.md) | Participant Information-Flow And Control | accepted | 2026-07-15 |
| [086](adr-086-governed-whole-scenario-satisfiability.md) | Governed Whole-Scenario Satisfiability | accepted | 2026-07-19 |
| [087](adr-087-enterprise-identity-and-deployment-tenancy-authoring.md) | Enterprise Identity and Deployment-Tenancy Authoring | accepted | 2026-07-24 |
| [088](adr-088-initial-service-state-and-native-materialization.md) | Initial Service State and Native Materialization | accepted | 2026-07-24 |
| [090](adr-090-shared-time-domain-clock-and-progression-authority.md) | Shared Time-Domain, Clock, And Progression Authority | accepted | 2026-07-24 |
| [091](adr-091-portable-time-capability-control-and-provenance-contracts.md) | Portable Time Capability, Control, And Provenance Contracts | accepted | 2026-07-24 |
| [092](adr-092-autonomous-benign-participants-under-shared-time.md) | Autonomous Benign Participants Under Shared Time | accepted | 2026-07-24 |
| [093](adr-093-raes-rename-and-compatibility-boundaries.md) | RAES Rename and Compatibility Boundaries | superseded by ADR-096 | 2026-07-23 |
| [094](adr-094-authoritative-cross-plane-experiment-bindings.md) | Authoritative Cross-Plane Experiment Bindings | accepted | 2026-07-26 |
| [095](adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md) | Participant Decision Epoch, State-Cut, And Delivery Semantics | accepted | 2026-07-26 |
| [096](adr-096-identity-cutover-and-historical-record-boundary.md) | Identity Cutover and Historical-Record Boundary | accepted | 2026-07-26 |
| [097](adr-097-scoped-participant-resource-budgets-and-shared-service-fairness.md) | Scoped Participant Resource Budgets And Shared-Service Fairness | proposed | 2026-07-27 |
| [098](adr-098-portable-artifact-requirement-satisfaction.md) | Portable Artifact Requirement Satisfaction | accepted | 2026-07-27 |
| [099](adr-099-participant-relative-predicate-opacity.md) | Participant-Relative Predicate Opacity | accepted | 2026-07-29 |
| [100](adr-100-participant-crossing-bisimulation.md) | Proof-Bearing Participant-Crossing Bisimulation | accepted | 2026-07-29 |
| [101](adr-101-adversarial-participant-flow-control.md) | Adversarial Participant Boundary Flow Control | accepted | 2026-07-30 |
| [102](adr-102-mixed-cross-backend-participant-control.md) | Mixed Cross-Backend Participant Control | accepted | 2026-07-31 |
| [103](adr-103-branch-aware-python-coverage-policy.md) | Branch-Aware Python Coverage Policy | accepted | 2026-08-13 |
| [104](adr-104-runtime-control-plane-architecture.md) | Runtime Control-Plane Architecture | accepted | 2026-08-17 |
| [105](adr-105-recursive-partial-description-semantics.md) | Recursive Partial Description Semantics | proposed | 2026-09-05 |
| [106](adr-106-developer-package-and-artifact-management.md) | Developer Package and Artifact Management | accepted | 2026-09-05 |
| [107](adr-107-artifact-promotion-and-release-admission.md) | Artifact Promotion and Release Admission | accepted | 2026-09-05 |
| [108](adr-108-modular-participant-control-and-governed-effects.md) | Modular Participant Control and Governed Effects | accepted | 2026-09-06 |
