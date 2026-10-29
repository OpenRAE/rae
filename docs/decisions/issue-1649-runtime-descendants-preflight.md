# Issue 1649: runtime descendant rules

Architecture checks cover SEM-225, SEM-218 and ASR-532.
The starting revision was `2553c540` on 2026-10-26.
This note gives design rules. It does not claim that the feature has shipped.

## Decision

Extend materialized SDL and the existing result boundary.
The backend supplies a world report and causal receipts.
The runtime admits members and writes concern origins.
Keep author intent, physical state, conformance, ownership and observation strength separate.
Use the existing archive and snapshot store.
No new world format, inventory service or workflow engine is needed.
ADR-004, ADR-036 and ADR-078 retain their owners and closed phase rules.

## Gaps in the starting code

- Entry checks run before report checks. They reject unplanned entries and backend-written provenance.
- `PreparedNodeCollectionAuthority` permits some additions before apply. It does not cover later discovery.
- `MaterializedResourceBinding.source_node` names an author declaration. It does not name a causal parent.
- Report checks expect the complete current domain. A partial scan cannot satisfy that claim.
- Concern origins come from admitted plan authority. New members need the same runtime-owned boundary.
- `finalize_protocol_result` compares the native and accepted snapshot digests. Runtime-derived fields need a distinct accepted-state commitment.
- Credential egress checks cover submitted entries. New members must keep those checks effective.
- The planner deletes predecessor entries absent from desired state. It must retain admitted members and handle tombstones.
- A manager method alone does not supply durable claims, authenticated submission or restart behavior.

## Membership and lineage

Use canonical portable addresses and native SDL resource owners.
Keep native identity and incarnation separate from a portable name.
Names, labels and address prefixes do not grant membership.
An incidental process or container is not necessarily a scenario node.
The existing SDL owner must describe its resource kind.

Bind each report to source, target, run, producer, operation, attempt and immediate predecessor.
Bind creation to its own operation, attempt and receipt.
Creation and later reporting are distinct events.
Each causal chain must reach an admitted source.
Bound chain depth and total work.
Reject cycles, missing parents, duplicate identities, collisions and replacement.
Keep qualified module names and replica identities.
Causal ancestry does not establish placement, dependency order or ownership.

## Authority and conformance

Reuse the original recursive relation and namespace-specific collection grant.
Keep exact leaves, required siblings, bounds, absence rules and closed scopes binding.
A node-local open concern cannot open its containing collection.
An open import cannot reopen a closed imported scope.
Keep native profile, capability, reference and cardinality checks.
The report cannot become a new desired-state plan.
Do not fabricate submitted plan nodes.
A reported deviation cannot grant permission or produce conforming inventory.

Reconcile the existing preparation, augmentation and attestation contracts explicitly.
Unknown identities need an admitted bounded structural scope.
That scope cannot excuse unknown impacts or closed collection rules.
Initial materialization still needs its applicable prospective checks.
Read-only reporting cannot conceal a new collector, retention operation or export.

## Refresh and lifecycle

Refresh changes accepted knowledge. It is an admitted mutation, not a snapshot read.
Use the existing administrative role, target/run scope and request limits.
A typed public request must select refresh without replaying apply.
Both manager and control-plane calls use the same report admission rules.
Do not rely on private caller state for lineage or replay protection.

Name the covered scope, collection cut, sequence, completeness and unavailable evidence.
Omission from a partial scan means unknown.
It does not mean removed, terminated or never present.
Termination, disappearance and autoremove need their own scoped evidence.
An exited resource can remain in inventory.
Keep trusted lineage and earlier concern origins.
Reject an excessive complete claim; truncation cannot establish completeness.
Preserve other producers and domains. Reject conflicting overlap.
Replanning and teardown must consume accepted inventory.
Workflow authority does not grant provisioning authority over a reported child.

## Concern origins and disclosure

Reuse concern descriptors and `realization_provenance_entry`.
Preserve source explicitness and author or processor origins.
A backend choice within a constrained domain has backend origin.
Equality with a template does not change that origin.
Keep the ledger value-free and derive each record from an admitted concern.
Do not write one blanket origin per resource.

Keep membership, explicitness, value origin, ownership and visibility distinct.
A creation receipt is not independent observation or experimental evidence.
ADR-066 retains disclosure, marking, comparability and evidence requirements.
A backend must not grant participant access merely by reporting a resource.

## Owners and cross-cutting checks

Paths below refer to `implementations/python/packages/`.

| Layer | Existing owners and required checks |
| --- | --- |
| Input bounds | `raes_contracts.materialization`, `json_ingress`, `runtime_value_limits`; `raes_runtime.backend_input_contracts`, `backend_call_contracts`, `backend_snapshot_contracts`. Bound bytes, depth, members and total work before copying or hashing. Preserve injected service identity. |
| SDL semantics | `raes.parse_sdl`, `materialization`, native validators; `raes_processor.compiler.materialization_origins`, `planner.materialization_admission`. Keep closed shapes, qualified names, safe omissions and full effect coverage. Do not execute the report. |
| Authority | Recursive constraints, collection relations, `plan_effects`, `plan_projection`, plan authorization and entry/effect checks. Preserve identity, domains, dependencies, profiles and honest change accounting. Empty plans do not bypass authority. |
| Scope and observation | `augmentation_admission`, `backend_augmentation`, `manager_augmentation`, `observation_admission`. Keep prospective permission, producer ownership, demand, prohibition and strength checks. |
| Support and config | `manifest_authority`, manifest DTOs, registry checks and typed configuration. Register support in the canonical closed list. Verify installed signatures and exact manifest/configuration identity. Preserve pinned offline profiles. |
| HTTP access | `control_plane_security`, API auth, guards, routes and operation context. Retain administrative mutation roles, sealed routes, bounded offload and stable redacted responses. Snapshot reads remain reads. |
| Attempts and recovery | Operation lifecycle, invocation ledger, provider execution, result finalization and reconciliation. Reuse native attempts, sequences, deduplication, generations and budgets. Do not replay creation or rewrite a terminal parent. |
| Secrets | Native value, environment and generated-value models; secret references and credential egress. Preserve `value`/`value_from` rules, classifications and safe omissions. Hashes are not substitute SDL values. Keep values out of errors and receipt locators. |
| Host and archive | `RunMaterializationArchive`, archive record and associated-artifact checks. Retain protected, contained, immutable bytes and verified readback. Never fetch backend URLs or execute reported commands. Keep credentials out of process arguments. |
| Errors and audit | Shared `Diagnostic`, refusal helpers, API responses and `record_audit`. Use bounded reason codes and correlation. Do not echo parser input, rejected values or backend exception text. |
| Store and DTOs | Runtime state, snapshot codecs, public models, terminal commit and revision CAS. Classify any new carrier and guard runtime-owned writes. Keep accepted state and archive references consistent after reload. |

Use the existing scoped `operation_evidence` owner for native provider evidence.
It does not prove physical ownership by itself.
Shared carriers and pure relations stay in `raes_contracts`.
SDL shapes stay in `raes`; admission stays in `raes_processor`.
Execution stays in `raes_runtime`; archive IO stays in `raes_operations`.
A shared contract cannot import a runtime or invoke a provider.

## Failure and commitments

An invalid success claim retains the immediate trusted predecessor.
It has empty changed addresses and no candidate details or success provenance.
This rule applies to manager, durable, supervised and reload paths.
Keep separately validated partial-failure cleanup under its incumbent contract.
A returned predecessor does not undo physical effects.
Preserve uncertainty and recovery evidence. Never replay apply automatically.

Check the raw backend proposal before deriving state.
Check derived membership, safe values, ownership and accounting before commit.
Keep the native proposal commitment distinct from the accepted-state commitment.
Do not weaken runtime-write guards or readmit a derived snapshot as a backend proposal.
Publish protected bytes before their accepted references.
File publication and store commit remain separate failure boundaries.

## Publication and checks

Published schemas remain authoritative under `contracts/schemas/`.
Keep `schema_bundle()` output identical.
Use the existing shared factoring and semantic invariant annotations.
Keep structural-only conformance claims honest.
The sharded publication ledger needs each changed schema's hash and change record.
Keep fixtures, manifests, public DTOs and migration guidance aligned.
A new support string alone is insufficient.

Use public runtime tests for a new child, a grandchild and a later child.
Cover provenance, persistence and restart.
Reject unauthorized membership, stale or foreign attempts, replay, replacement and duplicates.
Cover absent evidence, bounds, partial collection, secrets and producer conflicts.
Retain the direct-write rejection tests.
Reuse the existing #1204, #1241, #1242, provider and snapshot-CAS test patterns.

Follow `.ground-control.yaml`, `.gc/plan-rules.md` and exact requirement path ownership.
Set `RAES_REQUIREMENT_UID` when needed.
Use targeted local checks. CI owns full test, integration, fuzz and completion suites.
Record fresh source-bound research captures without editing history or baseline pins.
Release-please owns versions and changelog.
Name the first released dependency that actually provides the new contract.
The existing 7.0.0 pin cannot supply unreleased semantics.

## Non-goals

LilRAE owns native creator attribution and lifecycle receipts in downstream #1128.
This work does not add Docker discovery, host scans or operator grants.
It does not add experimental capture, retention, export or participant exposure.
It does not provide hostile-plugin containment, physical fencing or rollback.
It does not claim exactly-once effects.

Do not rewrite authored SDL or instantiation history.
Do not execute attestation as desired state or overload `source_node`.
Do not hide resources in metadata or `details`.
Do not grant authority from observed deviations.
Do not infer deletion from silence or relax direct-write refusals.
